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

# ─── git ───
if ! command -v git &>/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y && apt-get install -y git curl ca-certificates
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
