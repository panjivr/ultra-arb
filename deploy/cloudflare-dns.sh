#!/usr/bin/env bash
# REYOG CAPITAL — Auto-create Cloudflare DNS records (idempotent)
#
# Automates the DNS clicks so you don't touch the dashboard. It creates/updates
# the A records that point your domain at the Oracle VM.
#
# One-time prep (only YOU can do — needs your Cloudflare login):
#   1. Add the site `pusatbanksoal.online` to Cloudflare (Free plan).
#   2. In DomaiNesia, switch Nameservers to the 2 Cloudflare NS it gives you.
#   3. Create an API token: Cloudflare dashboard → My Profile → API Tokens →
#      Create Token → template "Edit zone DNS" → Zone = pusatbanksoal.online.
#
# Then run (Pola 1 — everything on Oracle):
#   CF_API_TOKEN=xxxx ZONE=pusatbanksoal.online IP=<ORACLE_IP> \
#     bash deploy/cloudflare-dns.sh pola1
#
# Or (Pola 2 — Vercel frontend + Oracle backend on api.*):
#   CF_API_TOKEN=xxxx ZONE=pusatbanksoal.online IP=<ORACLE_IP> \
#     bash deploy/cloudflare-dns.sh pola2
#   (creates only `api` -> Oracle; the root/www CNAME to Vercel is added by
#    Vercel's own "Add Domain" flow.)
#
# Also flips SSL/TLS mode to "flexible" so the HTTP-only origin works with HTTPS.

set -euo pipefail

MODE="${1:-pola1}"
: "${CF_API_TOKEN:?set CF_API_TOKEN}"
: "${ZONE:?set ZONE (e.g. pusatbanksoal.online)}"
: "${IP:?set IP (Oracle VM public IP)}"

CF="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json")

jqget() { python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }

echo "→ Resolving zone id for $ZONE…"
ZID=$(curl -s "${AUTH[@]}" "$CF/zones?name=$ZONE" | jqget "['result'][0]['id']")
[ -n "$ZID" ] && [ "$ZID" != "None" ] || { echo "!! Zone not found. Is $ZONE added to Cloudflare & token scoped to it?"; exit 1; }
echo "  zone id: $ZID"

# upsert_a <name> <proxied:true|false>
upsert_a() {
    local name="$1" proxied="$2" fqdn
    [ "$name" = "@" ] && fqdn="$ZONE" || fqdn="$name.$ZONE"
    local existing
    existing=$(curl -s "${AUTH[@]}" "$CF/zones/$ZID/dns_records?type=A&name=$fqdn" | jqget "['result']")
    local body="{\"type\":\"A\",\"name\":\"$fqdn\",\"content\":\"$IP\",\"ttl\":1,\"proxied\":$proxied}"
    local rid
    rid=$(printf '%s' "$existing" | python3 -c "import sys,json;r=json.load(sys.stdin);print(r[0]['id'] if r else '')" 2>/dev/null || echo "")
    if [ -n "$rid" ]; then
        curl -s -X PUT "${AUTH[@]}" "$CF/zones/$ZID/dns_records/$rid" --data "$body" >/dev/null
        echo "  updated  A $fqdn -> $IP (proxied=$proxied)"
    else
        curl -s -X POST "${AUTH[@]}" "$CF/zones/$ZID/dns_records" --data "$body" >/dev/null
        echo "  created  A $fqdn -> $IP (proxied=$proxied)"
    fi
}

case "$MODE" in
    pola1)
        echo "→ Pola 1: root + www -> Oracle ($IP)"
        upsert_a "@"   true
        upsert_a "www" true
        ;;
    pola2)
        echo "→ Pola 2: api -> Oracle ($IP)  (root/www CNAME handled by Vercel)"
        upsert_a "api" true
        ;;
    *) echo "!! unknown mode '$MODE' (use pola1 or pola2)"; exit 1;;
esac

echo "→ Setting SSL/TLS mode = flexible…"
curl -s -X PATCH "${AUTH[@]}" "$CF/zones/$ZID/settings/ssl" --data '{"value":"flexible"}' >/dev/null \
    && echo "  ssl mode: flexible" || echo "  (could not set ssl mode — set it manually in dashboard)"

echo "✅ DNS done. Give it a few minutes to propagate, then open your domain."
