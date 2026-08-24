#!/usr/bin/env bash
# REYOG CAPITAL — Run on YOUR OWN machine + expose at your domain via Cloudflare
# Tunnel (free). No VPS, no Oracle, no open ports.
#
#   Browser ─HTTPS─> Cloudflare ─Tunnel─> your PC (docker nginx:80) ─> REYOG
#
# PREREQUISITES (only you can do — needs your Cloudflare login):
#   • Cloudflare account with `pusatbanksoal.online` added, nameservers pointed
#     from DomaiNesia to Cloudflare (see docs/08).
#   • Docker installed and the stack running locally:
#       docker compose -f docker-compose.free.yml up -d --build
#
# USAGE:
#   DOMAIN=pusatbanksoal.online bash deploy/cloudflare-tunnel.sh
#
# For LIVE trading this machine must stay ON 24/7. If it sleeps, the bot stops
# placing/resolving orders.

set -euo pipefail
DOMAIN="${DOMAIN:?set DOMAIN, e.g. DOMAIN=pusatbanksoal.online}"
TUNNEL_NAME="${TUNNEL_NAME:-reyog}"
LOCAL_URL="${LOCAL_URL:-http://localhost:80}"   # the local nginx from docker-compose.free.yml

# ─── 1. Install cloudflared ───
if ! command -v cloudflared &>/dev/null; then
    echo "[1/5] Installing cloudflared…"
    OS="$(uname -s)"; ARCH="$(uname -m)"
    if [ "$OS" = "Linux" ]; then
        case "$ARCH" in
            x86_64) PKG=amd64;; aarch64|arm64) PKG=arm64;; armv7l) PKG=arm;; *) PKG=amd64;;
        esac
        curl -fsSL -o /tmp/cloudflared \
          "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$PKG"
        sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
    elif [ "$OS" = "Darwin" ]; then
        command -v brew &>/dev/null && brew install cloudflared \
          || { echo "Install Homebrew or download cloudflared manually."; exit 1; }
    else
        echo "Windows: install via 'winget install --id Cloudflare.cloudflared' then re-run in WSL/Git-Bash."; exit 1
    fi
else
    echo "[1/5] cloudflared present: $(cloudflared --version 2>/dev/null | head -1)"
fi

# ─── 2. Login (opens browser — pick the pusatbanksoal.online zone) ───
if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
    echo "[2/5] Browser login — authorize the '$DOMAIN' zone…"
    cloudflared tunnel login
else
    echo "[2/5] Already logged in (cert.pem present)."
fi

# ─── 3. Create tunnel (idempotent) ───
if ! cloudflared tunnel list 2>/dev/null | grep -q "\b$TUNNEL_NAME\b"; then
    echo "[3/5] Creating tunnel '$TUNNEL_NAME'…"
    cloudflared tunnel create "$TUNNEL_NAME"
else
    echo "[3/5] Tunnel '$TUNNEL_NAME' exists."
fi
TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | awk -v n="$TUNNEL_NAME" '$2==n{print $1}')
echo "  tunnel id: $TUNNEL_ID"

# ─── 4. Config + DNS routes ───
echo "[4/5] Writing config + routing DNS ($DOMAIN, www)…"
mkdir -p "$HOME/.cloudflared"
cat > "$HOME/.cloudflared/config.yml" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json
ingress:
  - hostname: $DOMAIN
    service: $LOCAL_URL
  - hostname: www.$DOMAIN
    service: $LOCAL_URL
  - service: http_status:404
EOF
cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN"      || true
cloudflared tunnel route dns "$TUNNEL_NAME" "www.$DOMAIN"  || true

# ─── 5. Run (systemd service if possible, else background) ───
echo "[5/5] Starting tunnel…"
CF_BIN="$(command -v cloudflared)"
CFG="$HOME/.cloudflared/config.yml"
if command -v systemctl &>/dev/null && [ "$(uname -s)" = "Linux" ]; then
    cat > /etc/systemd/system/cloudflared.service <<EOF
[Unit]
Description=cloudflared tunnel ($TUNNEL_NAME)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$CF_BIN tunnel --config $CFG run
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now cloudflared 2>/dev/null || true
    echo "  Installed as systemd service (auto-starts on boot)."
    echo "  Logs: journalctl -u cloudflared -f"
else
    pkill -f "cloudflared tunnel .* run" 2>/dev/null || true
    nohup "$CF_BIN" tunnel --config "$CFG" run > /tmp/tunnel.log 2>&1 &
    echo "  Started in background (nohup). Logs: tail -f /tmp/tunnel.log"
fi

echo ""
echo "✅ Once the stack is up, open: https://$DOMAIN/"
echo "   Reminder: keep this machine ON 24/7 for live trading."
