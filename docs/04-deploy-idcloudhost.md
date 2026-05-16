# REYOG CAPITAL — Deploy ke IDCloudHost VPS

Panduan **step-by-step** untuk deploy REYOG CAPITAL ke IDCloudHost Cloud Server.
**Target waktu: 15 menit dari nol sampai dashboard live di IP publik.**

## Yang anda perlukan

- [x] Cloud VPS IDCloudHost (4 GB RAM ✓)
- [x] IP publik VPS (sudah dapat dari email/dashboard IDCloudHost)
- [x] Root password atau SSH key

---

## Step 1 — Login ke VPS (2 menit)

### Cara A: SSH dari komputer
**Windows PowerShell / Mac / Linux:**
```bash
ssh root@IP_VPS_ANDA
# (paste password saat diminta)
```

### Cara B: Web Console IDCloudHost
1. Buka `https://my.idcloudhost.com`
2. Pilih Cloud Server anda
3. Klik **Console** / **Web Console** untuk SSH lewat browser

---

## Step 2 — Setup user non-root (recommended, 2 menit)

Login sebagai root pertama kali, lalu buat user untuk operasional:

```bash
# Sebagai root
adduser reyog
usermod -aG sudo reyog
mkdir -p /home/reyog/.ssh
cp ~/.ssh/authorized_keys /home/reyog/.ssh/ 2>/dev/null || true
chown -R reyog:reyog /home/reyog/.ssh

# Switch ke user reyog
su - reyog
```

Selanjutnya pakai user `reyog` (bukan root).

---

## Step 3 — Clone repo (1 menit)

```bash
# Install git jika belum ada
sudo apt update && sudo apt install -y git

# Clone proyek
cd ~
git clone <URL_REPO_ANDA> reyog-capital
# Contoh: git clone https://github.com/yourusername/reyog-capital.git

cd reyog-capital
```

Kalau belum push ke Git, anda bisa upload file dengan SCP dari komputer lokal:
```bash
# Dari komputer lokal
scp -r C:\Users\Panji\Projects\ultra-arb reyog@IP_VPS:~/reyog-capital
```

---

## Step 4 — One-Click Deploy (10 menit)

Cuma satu perintah:

```bash
sudo bash deploy/idcloudhost-deploy.sh
```

Script ini akan otomatis:
1. ✅ Install Docker + Docker Compose
2. ✅ Buka firewall port 80/443
3. ✅ Generate `.env` dengan random DB password aman
4. ✅ Auto-detect IP VPS anda
5. ✅ Build 6 container (frontend, backend, engine, redis, postgres, nginx)
6. ✅ Start semua dengan healthcheck

**Output yang anda akan lihat di akhir:**
```
════════════════════════════════════════════════════════════
  ✅ REYOG CAPITAL deployed

  Dashboard:   http://203.XXX.XXX.XXX/
  API:         http://203.XXX.XXX.XXX/api/health
  WebSocket:   ws://203.XXX.XXX.XXX/ws/firehose
════════════════════════════════════════════════════════════
```

---

## Step 5 — Akses Dashboard (selesai!)

Buka browser:
```
http://IP_VPS_ANDA/
```

Anda akan langsung melihat dashboard REYOG CAPITAL live:
- Macro intelligence bar (DXY, gold, Fear & Greed)
- Real ticker (Gate.io + HTX, harga BTC/ETH/SOL live)
- Equity curve, Polymarket bets, EdgeRadar, dll.

---

## Operasional sehari-hari

```bash
cd ~/reyog-capital

# Lihat semua container
docker compose ps

# Lihat logs real-time
docker compose logs -f --tail=100

# Lihat hanya engine
docker compose logs -f engine

# Restart 1 service
docker compose restart backend

# Update code + redeploy
git pull && docker compose up -d --build

# Stop semuanya
docker compose down

# Stop + hapus data (HATI-HATI)
docker compose down -v
```

---

## Connect wallet (Polymarket trade)

Karena anda akses via HTTP (bukan HTTPS), beberapa browser mungkin warn saat connect MetaMask:

**Workaround sementara:**
- Chrome: `chrome://flags/#unsafely-treat-insecure-origin-as-secure` → tambah `http://IP_VPS_ANDA` → relaunch
- Atau: pasang domain (Step 6 di bawah)

**Untuk pengalaman terbaik, pasang domain.**

---

## Step 6 — Pasang Domain (opsional, 10 menit)

Saat anda sudah dapat domain (`yourdomain.com`):

### a) Setup DNS
Di registrar domain (Niagahoster/Cloudflare/Namecheap/dll):
- Buat A record: `@` → `IP_VPS_ANDA`
- Buat A record: `www` → `IP_VPS_ANDA`

Tunggu 5-30 menit untuk propagation. Test:
```bash
nslookup yourdomain.com
```

### b) Update .env di VPS
```bash
cd ~/reyog-capital
nano .env
```

Ganti:
```
REYOG_DOMAIN=yourdomain.com
NEXT_PUBLIC_API_URL=https://yourdomain.com
NEXT_PUBLIC_WS_URL=wss://yourdomain.com
CORS_ORIGINS=https://yourdomain.com
```

### c) Install SSL via Let's Encrypt
```bash
# Stop nginx sementara
docker compose stop nginx

# Install certbot
sudo apt install -y certbot

# Issue cert (standalone — pakai port 80)
sudo certbot certonly --standalone -d yourdomain.com \
  --non-interactive --agree-tos --email you@email.com

# Copy cert ke folder nginx
sudo mkdir -p deploy/certbot/conf/live/yourdomain.com
sudo cp -r /etc/letsencrypt/live/yourdomain.com/* deploy/certbot/conf/live/yourdomain.com/
sudo chown -R $USER:$USER deploy/certbot

# Edit nginx config → enable HTTPS block
nano deploy/nginx.conf
# Uncomment "HTTPS server" section + ganti your-domain.com jadi yourdomain.com
```

### d) Rebuild frontend dengan domain baru
```bash
docker compose up -d --build frontend
docker compose up -d nginx
```

Akses sekarang: **`https://yourdomain.com/`** dengan padlock hijau.

---

## Troubleshooting

### Dashboard tidak bisa diakses
```bash
# Check semua container up
docker compose ps

# Check firewall
sudo ufw status

# Check nginx logs
docker compose logs nginx
```

### Build kehabisan RAM
Edit `.env`:
```
NEXT_TELEMETRY_DISABLED=1
NODE_OPTIONS=--max-old-space-size=2048
```
Atau build offline di komputer lokal, push image ke registry, pull di VPS.

### Engine tidak place trades
```bash
docker compose logs engine | tail -50

# Cek Redis
docker compose exec redis redis-cli LLEN arb:orders
```

### Port 80 sudah dipakai
IDCloudHost biasanya tidak install Apache/nginx default. Jika ada:
```bash
sudo systemctl stop apache2 nginx
sudo systemctl disable apache2 nginx
docker compose up -d nginx
```

---

## Maintenance otomatis

### Auto-restart on reboot
Docker `restart: unless-stopped` policy sudah aktif. Setelah reboot VPS:
```bash
# Container otomatis start, tapi cek
docker compose ps
```

### Auto-update tiap minggu (opsional)
```bash
# Tambah ke crontab
crontab -e
# Tambahkan:
0 4 * * 0 cd ~/reyog-capital && git pull && docker compose up -d --build >> ~/update.log 2>&1
```

### Backup database harian
```bash
# Tambah ke crontab
0 3 * * * cd ~/reyog-capital && docker compose exec -T postgres pg_dump -U arb ultra_arb | gzip > ~/backups/db-$(date +\%F).sql.gz
```

---

## Estimated cost (IDCloudHost pricing 2026)

| Plan | RAM | Cost/bulan | Cocok untuk |
|---|---|---|---|
| Cloud Server 2GB | 2 GB | ~Rp 99k | Paper trading, demo |
| **Cloud Server 4GB** | **4 GB** | **~Rp 200k** | **Production paper + live** |
| Cloud Server 8GB | 8 GB | ~Rp 400k | High frequency, multi-strategy |

App ini ringan: idle ~700 MB RAM, peak ~1.5 GB. 4 GB sangat cukup dengan room untuk grow.

---

## Berikutnya

Setelah dashboard live:
1. Connect MetaMask/Phantom → switch ke Polygon → load USDC.e
2. Lihat EdgeRadar — bot akan auto-detect arbitrage opportunities
3. Lihat Polymarket Panel — bot taruh paper bet tiap 60s di market dengan edge ≥ 4%
4. Lihat Compounding Tracker — projection growth wallet
5. **Tunggu 30 hari** paper trading dengan positive expectancy SEBELUM flip `PAPER_TRADE=false`

Selamat trading. 🚀
