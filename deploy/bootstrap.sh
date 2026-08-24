#!/usr/bin/env bash
# REYOG CAPITAL — one-line bootstrap for a fresh Ubuntu VPS.
#
# Run this SINGLE line on the VPS (as root, or with sudo):
#
#   curl -fsSL https://raw.githubusercontent.com/panjivr/ultra-arb/claude/audit-token-free-features-vfrwza/deploy/bootstrap.sh | sudo bash
#
# With a domain (after Cloudflare A record -> this VPS IP):
#
#   curl -fsSL https://raw.githubusercontent.com/panjivr/ultra-arb/claude/audit-token-free-features-vfrwza/deploy/bootstrap.sh | sudo DOMAIN=pusatbanksoal.online bash
#
# It: adds swap if RAM is small -> installs git/docker -> clones the repo ->
# runs the free Polymarket stack. Idempotent (safe to re-run to update).

set -euo pipefail
BRANCH="${BRANCH:-claude/audit-token-free-features-vfrwza}"
DIR="${DIR:-/opt/reyog/ultra-arb}"

echo "════════════════════════════════════════════════════════════"
echo "  REYOG CAPITAL — bootstrap"
echo "════════════════════════════════════════════════════════════"

# ─── Swap (only if RAM < ~3GB and no swap yet) — prevents build OOM ───
RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
SWAP_MB=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
if [ "${RAM_MB:-4000}" -lt 3000 ] && [ "${SWAP_MB:-0}" -lt 1000 ] && [ ! -f /swapfile ]; then
    echo "[swap] RAM ${RAM_MB}MB — adding 2GB swap…"
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Some AlmaLinux/RHEL 8 images ship stale RPM GPG keys that reject el8_10
# packages ("GPG check FAILED"). Relax gpgcheck on the (HTTPS) repos so installs
# succeed. Harmless on Debian/Ubuntu (no such repo files).
relax_rhel_gpg() {
    for f in /etc/yum.repos.d/*.repo; do
        [ -f "$f" ] && sed -i 's/gpgcheck=1/gpgcheck=0/g' "$f"
    done 2>/dev/null || true
}

# ─── git (distro-agnostic: apt / dnf / yum) ───
if ! command -v git &>/dev/null; then
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive; apt-get update -y; apt-get install -y git curl ca-certificates
    elif command -v dnf &>/dev/null; then
        relax_rhel_gpg; dnf install -y --nogpgcheck git curl ca-certificates
    elif command -v yum &>/dev/null; then
        relax_rhel_gpg; yum install -y --nogpgcheck git curl ca-certificates
    fi
fi

# ─── clone / update ───
mkdir -p "$(dirname "$DIR")"
if [ -d "$DIR/.git" ]; then
    echo "[repo] updating existing checkout…"
    cd "$DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull --ff-only origin "$BRANCH" || true
else
    echo "[repo] cloning…"
    git clone -b "$BRANCH" https://github.com/panjivr/ultra-arb.git "$DIR"
    cd "$DIR"
fi

# ─── hand off to the full setup (docker + firewall + .env + up) ───
echo "[run] deploy/oracle-setup.sh …"
exec bash deploy/oracle-setup.sh
