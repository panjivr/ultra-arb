#!/usr/bin/env bash
# REYOG CAPITAL — Oracle Cloud "Always Free" one-command deploy (ARM64/AMD64)
#
# Run ON the fresh Oracle VM (Ubuntu 22.04+ recommended), from the repo root:
#
#   git clone https://github.com/panjivr/ultra-arb.git
#   cd ultra-arb
#   sudo bash deploy/oracle-setup.sh
#
# Result: full REYOG stack on http://<VM_PUBLIC_IP>/ — 24/7, $0 forever.
#
# It:
#   1. Installs Docker + Compose plugin
#   2. Opens port 80 in the VM firewall (Oracle images REJECT it by default via
#      iptables — ufw alone is NOT enough). NOTE: you ALSO must add an Ingress
#      rule for TCP/80 in the OCI Console (VCN > Security List). See docs/07.
#   3. Generates .env (random DB/Redis passwords, PAPER_TRADE=true)
#   4. Builds + starts the ARM-safe free stack (docker-compose.free.yml)

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(pwd)}"
PUBLIC_IP="${PUBLIC_IP:-$(curl -4 -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')}"
ARCH="$(uname -m)"

echo "════════════════════════════════════════════════════════════"
echo "  REYOG CAPITAL — Oracle Always Free deploy"
echo "  Public IP : $PUBLIC_IP"
echo "  Arch      : $ARCH"
echo "  Repo      : $REPO_DIR"
echo "════════════════════════════════════════════════════════════"

# ─── 0. Swap (low-RAM boxes) — prevents build OOM ───
RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
SWAP_MB=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
if [ "${RAM_MB:-4000}" -lt 3000 ] && [ "${SWAP_MB:-0}" -lt 1000 ] && [ ! -f /swapfile ]; then
    echo "[0/5] RAM ${RAM_MB}MB — adding 2GB swap…"
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    grep -q '/swapfile' /etc/fstab 2>/dev/null || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Relax stale RPM GPG keys on some AlmaLinux/RHEL 8 images (el8_10 "GPG check
# FAILED"). Repos stay HTTPS + official; harmless on Debian/Ubuntu.
relax_rhel_gpg() {
    for f in /etc/yum.repos.d/*.repo; do
        [ -f "$f" ] && sed -i 's/gpgcheck=1/gpgcheck=0/g' "$f"
    done 2>/dev/null || true
}

# Distro-agnostic package install (Debian/Ubuntu apt, RHEL/Alma/Rocky dnf/yum).
pkg_install() {
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive; apt-get update -y; apt-get install -y "$@"
    elif command -v dnf &>/dev/null; then
        relax_rhel_gpg; dnf install -y --nogpgcheck "$@"
    elif command -v yum &>/dev/null; then
        relax_rhel_gpg; yum install -y --nogpgcheck "$@"
    fi
}

# ─── 1. Docker ───
if ! command -v docker &>/dev/null; then
    echo "[1/5] Installing Docker…"
    pkg_install curl ca-certificates openssl
    curl -fsSL https://get.docker.com | sh || true
    # Fallback for RHEL/AlmaLinux if the convenience script didn't finish.
    if ! command -v docker &>/dev/null && command -v dnf &>/dev/null; then
        echo "[1/5] Fallback: installing docker-ce via dnf…"
        dnf install -y --nogpgcheck dnf-plugins-core || true
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo 2>/dev/null || true
        dnf install -y --nogpgcheck docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || true
    fi
    systemctl enable --now docker 2>/dev/null || true
    if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        usermod -aG docker "$SUDO_USER" || true
    fi
else
    echo "[1/5] Docker present: $(docker --version)"
    systemctl enable --now docker 2>/dev/null || true
fi
command -v docker &>/dev/null || { echo "!! Docker install failed — check network/repos and re-run."; exit 1; }

# ─── 2. Firewall: open TCP/80 (and 443) ───
echo "[2/5] Opening TCP/80 in host firewall…"
if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port=80/tcp  >/dev/null 2>&1 || true
    firewall-cmd --permanent --add-port=443/tcp >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
    echo "  → firewalld: opened 80/443"
elif command -v ufw &>/dev/null; then
    ufw allow 80/tcp  >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    echo "  → ufw: opened 80/443"
elif command -v iptables &>/dev/null; then
    iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 80 -j ACCEPT
    iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 443 -j ACCEPT
    command -v netfilter-persistent &>/dev/null && netfilter-persistent save 2>/dev/null || true
    echo "  → iptables: opened 80/443"
else
    echo "  → no firewall tool found — assuming ports already open."
fi

# ─── 3. .env ───
# Optional: export DOMAIN=pusatbanksoal.online before running to wire a custom
# domain behind Cloudflare (HTTPS). Without it, the raw public IP is used.
cd "$REPO_DIR"
DOMAIN="${DOMAIN:-}"     # backend host, e.g. api.pusatbanksoal.online (Pola 2) or pusatbanksoal.online (Pola 1)
FRONT="${FRONT:-}"       # Pola 2 only: the Vercel frontend origin, e.g. pusatbanksoal.online
if [ -n "$DOMAIN" ]; then
    PUB_API="https://$DOMAIN"; PUB_WS="wss://$DOMAIN"
    REYOG_HOST="$DOMAIN"
    if [ -n "$FRONT" ]; then
        # Backend on api.* , frontend served elsewhere (Vercel): allow the frontend origin.
        CORS="https://$FRONT,https://www.$FRONT"
        echo "  → Pola 2: backend $DOMAIN, CORS allows frontend https://$FRONT"
    else
        CORS="https://$DOMAIN,https://www.$DOMAIN"
        echo "  → Pola 1: all-in-one at $DOMAIN (point it at $PUBLIC_IP via Cloudflare — docs/08)"
    fi
else
    PUB_API="http://$PUBLIC_IP"; PUB_WS="ws://$PUBLIC_IP"; CORS="*"; REYOG_HOST="$PUBLIC_IP"
fi
if [ ! -f .env ]; then
    echo "[3/5] Generating .env…"
    DB_PW=$(openssl rand -hex 16)
    REDIS_PW=$(openssl rand -hex 16)
    cat > .env <<EOF
# ─── Auto-generated by oracle-setup.sh on $(date -u +%FT%TZ) ───
REYOG_DOMAIN=$REYOG_HOST
NEXT_PUBLIC_API_URL=$PUB_API
NEXT_PUBLIC_WS_URL=$PUB_WS
CORS_ORIGINS=$CORS

DB_USER=arb
DB_PASSWORD=$DB_PW
DB_NAME=ultra_arb
DB_HOST=postgres
DB_PORT=5432
DATABASE_URL=postgresql+asyncpg://arb:$DB_PW@postgres:5432/ultra_arb

REDIS_PASSWORD=$REDIS_PW
REDIS_URL=redis://:$REDIS_PW@redis:6379/0

PAPER_TRADE=true

# Polymarket-focused web: engine runs ONLY the Polymarket strategy (asset price
# feed stays up; crypto spot/perp/funding trading off). Flip PAPER_TRADE=false
# + set POLYMARKET_PRIVATE_KEY only when you deliberately go live (real USDC).
POLYMARKET_ONLY_MODE=true
CRYPTO_STRATEGIES_ENABLED=false

# Free-tier cadence (light on a small VM; still real-time feel)
FIREHOSE_HZ_MS=50
WS_INTERVAL_MS=200

BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true
BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_TESTNET=true
POLYMARKET_PRIVATE_KEY=
POLYMARKET_SANDBOX=true
FINANCIAL_DATASETS_API_KEY=

MAX_DRAWDOWN_PCT=2.0
MAX_POSITION_PCT=2.5
MAX_CONCURRENT_POSITIONS=5
VOL_BREAKER_MULTIPLIER=3.0
EOF
    chmod 600 .env
    echo "  → .env created (random DB + Redis passwords, 600 perms)."
else
    echo "[3/5] .env exists — keeping it."
fi

# ─── 4. Build + start (ARM-safe free stack) ───
echo "[4/5] Building + starting (first build ~8-15 min on Ampere A1)…"
docker compose -f docker-compose.free.yml pull redis postgres nginx 2>&1 | tail -6 || true
docker compose -f docker-compose.free.yml up -d --build

# ─── 5. Wait + report ───
echo "[5/5] Waiting for healthchecks…"
for i in {1..40}; do
    healthy=$(docker compose -f docker-compose.free.yml ps --format json 2>/dev/null | grep -c '"Health":"healthy"' || echo 0)
    [ "$healthy" -ge 3 ] && { echo "  $healthy services healthy."; break; }
    sleep 3
done

docker compose -f docker-compose.free.yml ps
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ REYOG CAPITAL live (FREE) — direct: http://$PUBLIC_IP/"
if [ -n "$DOMAIN" ]; then
echo "     Domain  : https://$DOMAIN/  (after Cloudflare DNS — see docs/08)"
fi
echo ""
echo "  API   : http://$PUBLIC_IP/api/health"
echo "  WS    : ws://$PUBLIC_IP/ws/firehose"
echo "  Logs  : docker compose -f docker-compose.free.yml logs -f --tail=100"
echo "  Update: git pull && docker compose -f docker-compose.free.yml up -d --build"
echo ""
echo "  Not loading? Add Ingress TCP/80 in OCI Console (VCN > Security List)."
echo "════════════════════════════════════════════════════════════"
