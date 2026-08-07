# 06 — Audit "Hemat Token" & Rencana Jalan 100% Gratisan

> Tujuan: **semua fitur REYOG CAPITAL bisa dipakai tanpa VPS berbayar** — cukup
> pakai free-tier / gratisan. Dokumen ini meng-audit setiap ketergantungan
> berbayar, memetakan alternatif gratis, dan memberi jalur eksekusi konkret.

Ringkas: proyek ini **tidak butuh LLM/AI token berbayar sama sekali** untuk
jalan. Semua "AI" di sini (HMM, Kalman, Bayesian, edge detector) itu math/quant
lokal, bukan panggilan API model. Jadi "hemat token" praktis = **hemat biaya
hosting + API data**. Kabar baik: hampir semua sudah gratis; yang berbayar
cuma **VPS** dan **1 API opsional**.

---

## 1. Audit ketergantungan — mana yang berbayar?

| Komponen | Sekarang | Biaya | Wajib? |
|---|---|---|---|
| VPS IDCloudHost (7 container 24/7) | AlmaLinux, ~Rp50-150k/bln | **BAYAR** | inti |
| PostgreSQL / **TimescaleDB** | container di VPS | gratis (self-host) | ya |
| Redis | container di VPS | gratis (self-host) | ya |
| Harga crypto (Gate.io + HTX public API) | REST publik | **GRATIS** | ya |
| Polymarket Gamma/CLOB API | REST publik | **GRATIS** | ya |
| RSS news (Cointelegraph/Decrypt/dst) | RSS publik | **GRATIS** | ya |
| Macro (DXY/Gold/VIX/Fear&Greed) | API publik | **GRATIS** | ya |
| Polygon RPC (saldo wallet) | RPC publik | **GRATIS** | ya |
| Binance/Bybit **testnet** keys | testnet | **GRATIS** | opsional |
| `financialdatasets.ai` (17k saham) | API key | **BAYAR** (ada free tier terbatas) | **opsional** |
| Model AI / LLM | — | **tidak ada** | — |

**Kesimpulan audit:** satu-satunya biaya yang benar-benar mengunci adalah
**VPS**. `financialdatasets.ai` cuma untuk panel EquityWatchlist — bisa
dimatikan tanpa kehilangan fitur trading.

---

## 2. Apa yang bikin susah "gratisan"?

Tiga hal berat yang harus muat di batas free-tier:

1. **Proses 24/7 (always-on):** `engine`, `edge_runner`, `risk`, `backend`.
   Free-tier serverless (Render free, Cloud Run) sering *tidur* saat idle →
   edge scanner & paper-engine mati. Butuh host yang benar-benar always-on.
2. **Volume perintah Redis:** `firehose.py` baca tiap **10ms (100Hz)** dan
   `ws.py` tiap **100ms**. 100Hz = ~8.6 juta perintah/hari — jauh di atas
   Upstash free (~500k/hari). Ini **harus diturunkan** kalau pakai Redis
   managed gratis.
3. **TimescaleDB:** Supabase/Neon free = Postgres biasa, **tanpa ekstensi
   TimescaleDB**. Hypertable harus jadi opsional (fallback ke tabel biasa).

---

## 3. Tiga jalur gratisan (pilih salah satu)

### 🟢 Jalur A — Oracle Cloud "Always Free" VM  *(REKOMENDASI)*

Oracle kasih VM **gratis selamanya**: Ampere ARM A1 sampai **4 vCPU / 24 GB
RAM** (atau 2× VM AMD micro). Ini VPS asli, always-on, tanpa auto-sleep.

- **Perubahan kode: NOL.** `git clone` → `docker compose up -d --build`.
  Persis stack yang sekarang, semua 7 service, semua fitur hidup 24/7.
- Ganti nginx TLS pakai domain gratis (DuckDNS / sslip.io) + Let's Encrypt.
- **Semua fitur jalan 100%**, biaya **Rp0**.

> Ini jawaban paling jujur & paling simpel untuk "semua fitur, gratis, 24/7".
> Satu-satunya ongkos: sekali setup akun Oracle (butuh verifikasi kartu, tak
> ditagih di Always Free).

### 🟡 Jalur B — Serverless free-tier terpisah (butuh sedikit ubah kode)

Kalau tak mau pakai Oracle, pecah jadi layanan gratis masing-masing:

| Bagian | Host gratis | Catatan |
|---|---|---|
| Frontend Next.js | **Vercel** / Cloudflare Pages | drop-in, gratis |
| Backend API + WS | **Fly.io** / Koyeb / HF Spaces | free allowance always-on |
| Worker 24/7 (engine+edges+risk) | **Fly.io** VM (free) | perlu 1 VM kecil |
| Redis | **Upstash** free | WAJIB turunkan cadence (lihat §4) |
| Postgres | **Supabase** / **Neon** free | TimescaleDB → Postgres biasa (§4) |

Fitur tetap lengkap, tapi butuh 3 patch kecil di §4 supaya muat batas gratis.

### 🔵 Jalur C — Lokal saja (laptop/PC), 0 cloud

`docker compose up -d` di PC sendiri. Online hanya saat PC nyala. Mau diakses
dari HP? Pasang **Cloudflare Tunnel** (gratis) → dapat URL publik tanpa buka
port. Cocok buat paper-trading & pantau, tanpa daftar cloud apa pun.

---

## 4. Patch yang dibutuhkan untuk Jalur B/C (biar muat free-tier)

Ini kecil & aman (tidak mengubah logika trading). Bisa saya kerjakan begitu
Anda pilih jalurnya:

1. **Turunkan cadence firehose/WS** via env (default tetap seperti sekarang):
   - `firehose.py`: `PUSH_INTERVAL = float(os.getenv("FIREHOSE_HZ_MS", "10"))/1000`
     → set `500` di free-tier (2Hz, bukan 100Hz). Turun ~50×.
   - `ws.py`: `PUSH_INTERVAL = float(os.getenv("WS_INTERVAL_MS", "100"))/1000`
     → set `1000`.
   - Efek: Redis command/hari turun dari ~8.6jt ke ~<200k → **muat Upstash free**.
2. **TimescaleDB opsional:** di `arb/infra/db.py` bungkus
   `create_hypertable(...)` dengan try/except (kalau ekstensi tak ada →
   tetap jalan sebagai tabel Postgres biasa). Untuk mode paper bisa juga
   `DATABASE_URL=sqlite+aiosqlite:///reyog.db` (nol server DB).
3. **Matikan panel berbayar via env:** `FINANCIAL_DATASETS_API_KEY` kosong →
   `financial.py` sudah opsional; pastikan `EquityWatchlist.tsx` sembunyi/tidak
   error saat key kosong. Semua fitur lain tak terpengaruh.

Tambahan opsional (mode super-hemat, `POLYMARKET_ONLY_MODE=true`): matikan
feed crypto perp/spot, sisakan Polymarket + harga aset. Beban turun lagi.

---

## 5. Fitur mana yang tetap hidup di tiap jalur?

| Fitur | A (Oracle) | B (serverless) | C (lokal) |
|---|---|---|---|
| Dashboard + semua panel | ✅ | ✅ | ✅ |
| Harga REAL crypto | ✅ | ✅ | ✅ |
| Polymarket auto-bet (paper) | ✅ | ✅ | ✅ |
| 6 edge detector 24/7 | ✅ | ✅ | ⚠️ hanya saat PC nyala |
| Wallet connect (Polygon) | ✅ | ✅ | ✅ |
| Macro/News/Calendar | ✅ | ✅ | ✅ |
| Firehose 100Hz penuh | ✅ | ⚠️ 2Hz (hemat) | ✅ |
| EquityWatchlist (saham) | key opsional | key opsional | key opsional |
| Biaya | Rp0 | Rp0 | Rp0 |

Tak ada fitur yang hilang total di mana pun — yang berubah cuma **cadence
firehose** di Jalur B (100Hz→2Hz, tetap real-time terasa) dan edge 24/7 di
Jalur C bergantung PC nyala.

---

## 6. Rekomendasi

1. **Mau paling gampang & semua fitur 24/7 → Jalur A (Oracle Always Free).**
   Tidak ada perubahan kode; tinggal pindah target deploy dari IDCloudHost.
2. **Tak mau daftar Oracle → Jalur B.** Saya siapkan 3 patch env di §4 +
   file config Fly.io/Vercel/Upstash.
3. **Cuma buat coba/paper di PC → Jalur C.** Paling cepat, `docker compose up`
   + Cloudflare Tunnel opsional.

Semua jalur = **Rp0** dan **tanpa token/LLM berbayar**. Tinggal pilih, nanti
saya eksekusi (patch kode + panduan langkah-langkah spesifik host-nya).
</content>
