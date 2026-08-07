# 07 — Deploy GRATIS 24/7 di Oracle Cloud "Always Free"

> Jalankan **semua fitur REYOG CAPITAL** 24/7 dengan biaya **Rp0**, tanpa ubah
> kode. Oracle memberi VM gratis **selamanya** (bukan trial). Ikuti langkah ini
> sekali, lalu bot jalan terus.

Semua file yang dibutuhkan sudah ada di repo:
`docker-compose.free.yml`, `deploy/nginx.free.conf`, `deploy/oracle-setup.sh`.

---

## Kenapa Oracle?

- **Always Free** = gratis selamanya. Ampere ARM **A1: sampai 4 vCPU / 24 GB
  RAM** (atau 2× VM AMD micro 1GB). Cukup besar untuk stack 7-service ini.
- Always-on, **tidak auto-sleep** (beda dengan Render/Cloud Run free).
- Tidak butuh perubahan kode — cukup pakai compose ARM-safe yang sudah disiapkan.

Satu-satunya syarat: daftar akun Oracle butuh verifikasi kartu (untuk anti-bot).
Di tier Always Free **tidak ada tagihan**.

---

## Langkah 1 — Buat akun & VM (±10 menit)

1. Daftar di <https://www.oracle.com/cloud/free/> → pilih region terdekat
   (mis. Singapore / Jakarta).
2. Console → **Compute → Instances → Create Instance**.
3. **Image & shape:**
   - Image: **Ubuntu 22.04** (atau 24.04).
   - Shape: **Ampere (VM.Standard.A1.Flex)** → set **2 OCPU / 12 GB** (masih
     dalam Always Free). Kalau A1 "out of capacity", coba region/AD lain atau
     pakai **VM.Standard.E2.1.Micro** (AMD, 1GB — cukup untuk mode hemat).
   - Tandai label **"Always Free eligible"**.
4. **SSH keys:** upload public key Anda (atau download key yang dibuat Oracle).
5. Klik **Create**. Catat **Public IP** VM.

## Langkah 2 — Buka port 80 di jaringan Oracle (WAJIB)

Ini paling sering terlewat. Ada **dua** lapis firewall:

**a) OCI Security List (di Console):**
- VCN → Subnet VM → **Security List** → **Add Ingress Rules**:
  - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port **80**.
  - (Opsional untuk HTTPS nanti: tambah port **443**.)

**b) Firewall di dalam VM:** ditangani otomatis oleh `oracle-setup.sh`
(langkah 4). Tak perlu manual.

## Langkah 3 — Masuk ke VM & ambil kode

```bash
ssh ubuntu@<PUBLIC_IP>
git clone https://github.com/panjivr/ultra-arb.git
cd ultra-arb
```

## Langkah 4 — Satu perintah, beres

```bash
sudo bash deploy/oracle-setup.sh
```

Script akan: install Docker → buka TCP/80 di VM → buat `.env` (password DB &
Redis acak, `PAPER_TRADE=true`) → build & start `docker-compose.free.yml` →
tunggu sehat. Build pertama ±8–15 menit di A1.

Selesai → buka **`http://<PUBLIC_IP>/`** 🎉

---

## Verifikasi

```bash
docker compose -f docker-compose.free.yml ps          # semua Up/healthy
curl http://localhost/api/health                       # {"status":"ok"...}
docker compose -f docker-compose.free.yml logs -f engine   # tick mengalir
```

Panel yang harus hidup: harga REAL crypto, Polymarket auto-bet (paper), 6 edge
detector, macro/news/calendar, wallet connect, EquityWatchlist (5 ticker gratis
tanpa API key).

---

## Operasional

```bash
# Update ke versi terbaru
git pull && docker compose -f docker-compose.free.yml up -d --build

# Restart / stop
docker compose -f docker-compose.free.yml restart
docker compose -f docker-compose.free.yml down

# Lihat log semua service
docker compose -f docker-compose.free.yml logs -f --tail=100
```

**Catatan DB:** stack free pakai `postgres:16-alpine` (bukan TimescaleDB — image
Timescale tak ada build ARM). `arb/infra/db.py` otomatis fallback ke tabel
Postgres biasa; hypertable jadi tabel biasa. Untuk paper-trading tak ada beda.

**Cadence:** `.env` set `FIREHOSE_HZ_MS=50` (20Hz) & `WS_INTERVAL_MS=200` (5Hz)
— ringan di VM kecil, tetap terasa real-time. Mau firehose penuh 100Hz? Set
`FIREHOSE_HZ_MS=10` di `.env` lalu `up -d`.

---

## (Opsional) HTTPS gratis dengan domain gratis

HTTP sudah cukup untuk pakai pribadi. Kalau mau gembok HTTPS:

1. Domain gratis: **DuckDNS** (`namaanda.duckdns.org` → arahkan ke Public IP)
   atau langsung `sslip.io` (`<IP-pakai-dash>.sslip.io`).
2. Tambah Ingress **TCP/443** di Security List + `iptables -I INPUT 6 -p tcp
   --dport 443 -j ACCEPT` di VM.
3. Pakai `deploy/nginx.conf` (varian TLS) + jalankan certbot untuk domain itu,
   atau taruh VM di belakang **Cloudflare** (proxy + TLS gratis, paling gampang:
   arahkan DNS Cloudflare ke IP, aktifkan proxy, mode "Flexible").

---

## Ringkasan biaya

| Item | Biaya |
|---|---|
| VM Oracle Always Free (2 vCPU/12GB, 24/7) | Rp0 |
| Postgres, Redis (di dalam VM) | Rp0 |
| Data crypto/Polymarket/macro/news | Rp0 |
| Domain (DuckDNS/sslip.io) + TLS (Cloudflare/certbot) | Rp0 |
| **Total** | **Rp0 / bulan** |

Tanpa token/LLM berbayar. Semua fitur, 24/7, gratis.
