# REYOG CAPITAL — VPS Deployment Guide

End-to-end production deployment to any VPS (DigitalOcean, Hetzner, Linode, AWS Lightsail, Contabo, etc.) with your own domain + free SSL via Let's Encrypt.

**Stack:** 6 Docker containers (nginx, frontend, backend, engine, redis, postgres) behind nginx reverse proxy. ~700 MB RAM, runs comfortably on a $5/month VPS.

---

## Prerequisites

- A VPS with **Ubuntu 22.04+** or **Debian 12+** (1 vCPU, 1 GB RAM minimum; 2 GB recommended)
- A domain name pointed to the VPS IP (A record `@` and `www` → VPS IP)
- SSH access as a non-root user with sudo

---

## 1. Server prep (5 minutes)

```bash
# SSH in as a sudo user
ssh user@your-vps-ip

# Install Docker + Compose plugin (official method)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

# Verify
docker --version && docker compose version
```

## 2. Clone & configure (3 minutes)

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/reyog-capital.git
cd reyog-capital

# Copy env template and edit
cp .env.example .env
nano .env   # set REYOG_DOMAIN, strong DB_PASSWORD, NEXT_PUBLIC_API_URL, etc.
```

Key values to change in `.env`:
```env
REYOG_DOMAIN=reyog.yourdomain.com
NEXT_PUBLIC_API_URL=https://reyog.yourdomain.com
NEXT_PUBLIC_WS_URL=wss://reyog.yourdomain.com
CORS_ORIGINS=https://reyog.yourdomain.com
DB_PASSWORD=<a strong random password>
DATABASE_URL=postgresql+asyncpg://arb:<the password>@postgres:5432/ultra_arb
PAPER_TRADE=true   # flip to false ONLY after 30 days of positive paper PnL
```

## 3. Boot the stack (10 minutes for first build)

```bash
docker compose up -d --build
```

First build takes ~5-10 minutes (Python deps + Next.js build). Subsequent restarts: ~10 seconds.

Check everything is up:
```bash
docker compose ps
# All 6 services should show "Up (healthy)" within ~30s

# Watch logs
docker compose logs -f backend engine
```

You should see:
```
[real] starting REAL market engine — Gate.io + HTX public feeds
[real] HTX BTC/USDT: $XX,XXX.XXXX
[poly] multi-interval strategy started (5m/15m/30m/1h/4h/daily) — scan every 60s
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 4. SSL with Let's Encrypt (5 minutes)

```bash
# Open firewall
sudo ufw allow 80,443/tcp && sudo ufw enable

# Visit http://reyog.yourdomain.com in browser → confirms HTTP works.

# Install certbot
sudo apt install -y certbot

# Stop nginx briefly (port 80 conflict)
docker compose stop nginx

# Issue cert (standalone mode — uses port 80 directly)
sudo certbot certonly --standalone -d reyog.yourdomain.com \
  --non-interactive --agree-tos --email you@youremail.com

# Copy certs into the nginx volume
sudo mkdir -p deploy/certbot/conf/live/reyog.yourdomain.com
sudo cp -r /etc/letsencrypt/live/reyog.yourdomain.com/* deploy/certbot/conf/live/reyog.yourdomain.com/
sudo chown -R $USER:$USER deploy/certbot

# Edit deploy/nginx.conf — uncomment the HTTPS server block + replace your-domain.com
nano deploy/nginx.conf

# Bring nginx back up
docker compose up -d nginx
```

Visit **`https://reyog.yourdomain.com`** — dashboard should load with green padlock.

### Auto-renew SSL

```bash
# Add to crontab
echo "0 3 * * * /usr/bin/certbot renew --quiet --post-hook 'cd $(pwd) && docker compose restart nginx'" | sudo crontab -
```

## 5. Operate

| Task | Command |
|---|---|
| View logs | `docker compose logs -f --tail=100 backend engine frontend` |
| Restart engine only | `docker compose restart engine` |
| Update code & redeploy | `git pull && docker compose up -d --build` |
| Stop everything | `docker compose down` |
| Stop + wipe data | `docker compose down -v` (⚠ deletes Redis + Postgres data) |
| Connect to Postgres | `docker compose exec postgres psql -U arb ultra_arb` |
| Connect to Redis | `docker compose exec redis redis-cli` |
| Engine status | `docker compose logs --tail=20 engine` |

## 6. Switching from PAPER → LIVE

1. Run for **30 days minimum** in paper mode. Verify positive expectancy in `/api/stats`.
2. Add testnet keys first (`BINANCE_TESTNET=true`). Run another 7 days.
3. Switch to real keys + `PAPER_TRADE=false` + `BINANCE_TESTNET=false`.
4. Restart only the engine: `docker compose restart engine`.
5. Watch first 10 trades manually — circuit breakers should engage if anything goes wrong.

## 7. Connect a wallet

The frontend (now at `https://reyog.yourdomain.com`) auto-detects EIP-6963 wallets:
- MetaMask, Phantom (EVM mode), Coinbase Wallet, Trust Wallet, OKX, Rabby, Brave.

Click **Connect Wallet** → pick wallet → auto-switch to Polygon Mainnet → sign session message. The bot then uses your **real USDC.e balance** as trading capital.

For real on-chain Polymarket bets (vs paper):
- Set `POLYMARKET_PRIVATE_KEY` to a *separate* hot wallet's key (never your main wallet)
- Fund that wallet with USDC.e on Polygon
- The engine will sign + submit orders via `py-clob-client` (requires `PAPER_TRADE=false`)

## 8. Monitoring & alerts

```bash
# Resource usage
docker stats

# Healthchecks
curl https://reyog.yourdomain.com/health   # backend
curl https://reyog.yourdomain.com/         # frontend
```

For uptime monitoring, point any free service (UptimeRobot, Better Stack, etc.) at:
- `https://reyog.yourdomain.com/health` (60s interval)

## 9. Common pitfalls

| Issue | Fix |
|---|---|
| `frontend` won't build (out of memory) | Build on a 2 GB+ VPS, or build locally and push image |
| `backend` can't reach exchange APIs | Check VPS region — some providers block Binance |
| WebSocket disconnects | nginx `proxy_read_timeout 86400s` already set; check Cloudflare timeouts if proxied |
| Postgres slow | Run on SSD; increase `shared_buffers` in `postgres.conf` |
| Engine high CPU | Adjust `PUSH_INTERVAL` in `firehose.py` (currently 10ms = 100Hz) |

## 10. Backup

```bash
# Daily Postgres dump
docker compose exec postgres pg_dump -U arb ultra_arb | gzip > backup-$(date +%F).sql.gz

# Redis snapshot
docker compose exec redis redis-cli BGSAVE
docker cp reyog_redis:/data/dump.rdb redis-backup-$(date +%F).rdb
```

Rsync these to S3 / Backblaze for off-site backup.

---

## Architecture diagram

```
                            Internet
                                │
                          ┌─────▼─────┐
                          │   nginx   │  (80/443, SSL termination)
                          └──┬─────┬──┘
                             │     │
                  ┌──────────┘     └────────┐
                  ▼                          ▼
         ┌────────────────┐         ┌───────────────┐
         │   frontend     │         │    backend    │
         │ (Next.js :3000)│         │ (FastAPI :8000)
         └────────────────┘         └───┬───────┬───┘
                                        │       │
                            ┌───────────┘       └──────────┐
                            ▼                              ▼
                     ┌─────────────┐               ┌──────────────┐
                     │    redis    │ ◄────────────►│    engine    │
                     │ (lists+pub) │               │ (real_market)│
                     └─────────────┘               └──────────────┘
                            ▲
                            │
                     ┌──────┴──────┐
                     │  postgres   │
                     │ (history)   │
                     └─────────────┘
```

That's it — you have a production REYOG CAPITAL deployment.
