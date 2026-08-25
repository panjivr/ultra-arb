# Panduan LIVE Otonom (uang asli) — mudah, langkah demi langkah

> Bot ini menaruh taruhan Polymarket **uang asli secara otomatis** dari sinyal engine.
> Default-nya **MATI**. Tidak ada satu sen pun bergerak sampai kamu sengaja
> melewati **5 gerbang**. Baca sampai bagian "Cara STOP" sebelum mulai.

---

## 0) Sebelum mulai — jujur dulu

- **Uang asli bisa hilang.** Pasar prediksi short-term itu efisien; edge-nya tipis.
- Pakai **wallet khusus** berisi **hanya yang siap hilang**. Jangan wallet utama.
- Cap bawaan sengaja sangat kecil: **$2/taruhan, $5/hari, total seumur-hidup $25.**
  Naikkan hanya setelah kamu paham & yakin.

---

## Yang melindungi kamu (dibangun di kode, bukan cuma janji)

| Lapisan | Nilai default | Bisa dinaikkan? |
|---|---|---|
| Cap per-taruhan | $2 | tidak (batas keras) |
| Cap harian | $5 | tidak (batas keras) |
| Cap total seumur-hidup | $25 | ya, s/d $100 (batas keras kode) |
| Maks posisi terbuka | 5 | ya, s/d 20 |
| Jeda antar-taruhan | 30 dtk | ya |
| Edge minimum | 5% (500 bps) | ya |
| Kill-switch loss | auto-halt: rugi $3/hari **atau** 3 kalah beruntun **atau** saldo < $1 | — |
| Cek pra-order tiap taruhan | kill-switch, cap harian, ukuran, pasar-buka, saldo, friction < 10% | — |
| **Arm auto-kadaluarsa** | 6 jam lalu mati sendiri (dead-man switch) | ya |

Kalau **satu** cek gagal → order **tidak** ditaruh.

---

## 5 gerbang (SEMUA harus terpenuhi, kalau tidak = STANDBY, tak menaruh apa pun)

1. `PAPER_TRADE=false` di server
2. `POLYMARKET_PRIVATE_KEY` + `POLY_WALLET_ADDRESS` di server
3. `arb:mode = real` (tombol REAL di dashboard, setelah connect wallet)
4. Executor **di-arm** (`arb:live:autonomous_armed`, kadaluarsa otomatis)
5. Kill-switch bersih (`arb:live:halted` kosong)

---

## Langkah-langkah

### Langkah 1 — Siapkan wallet & dana kecil
1. Buat/siapkan wallet Polygon **khusus bot** (mis. dari MetaMask).
2. Isi **USDC kecil** (mis. $10–$25) + sedikit **POL/MATIC** untuk gas.
3. Deposit USDC ke Polymarket (lewat polymarket.com, hubungkan wallet yang sama).
4. Catat **alamat wallet** (0x…) dan **private key**-nya.

> Private key = kendali penuh atas dana wallet itu. Simpan aman. Jangan pernah
> paste ke chat/screenshot. Bot hanya membacanya dari env di server.

### Langkah 2 — Set kredensial di server (SSH ke VPS)
Edit `.env` di `/opt/reyog/ultra-arb/.env`, tambahkan/ubah:
```
PAPER_TRADE=false
POLYMARKET_PRIVATE_KEY=0xPRIVATE_KEY_KAMU
POLY_WALLET_ADDRESS=0xALAMAT_WALLET_KAMU
```
(opsional, naikkan/turunkan cap:)
```
LIVE_TOTAL_CAP_USD=25
LIVE_MIN_EDGE_BPS=500
```

> ⚠️ `PAPER_TRADE=false` juga membuat engine memperlakukan mode "real". Selama
> executor belum di-arm, tetap tidak ada order yang ditaruh.

### Langkah 3 — Nyalakan container executor (opsional-in, mati by default)
```
cd /opt/reyog/ultra-arb && git pull origin claude/audit-token-free-features-vfrwza \
  && docker compose -f docker-compose.free.yml --profile live up -d --build live_executor backend engine edge_runner
```
Cek ia STANDBY (belum menaruh apa-apa):
```
docker logs reyog_live_executor --tail 10
```
Harusnya muncul `STANDBY — ...` (mis. "not armed").

### Langkah 4 — Aktifkan mode REAL
- Di dashboard: **connect wallet** lalu klik tombol **REAL**. Atau via redis:
```
docker exec reyog_redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning SET arb:mode real
```

### Langkah 5 — Cek status, lalu ARM
Cek dulu semua gerbang:
```
docker exec reyog_live_executor python scripts/live_autonomous_executor.py status
```
Kalau semua hijau kecuali "armed", **arm untuk 6 jam**:
```
docker exec reyog_live_executor python scripts/live_autonomous_executor.py arm 6h
```
Sekarang executor **aktif**. Ia auto-mati setelah 6 jam — **arm lagi** untuk lanjut.

### Langkah 6 — Pantau
```
docker logs -f reyog_live_executor
```
Baris `✅ PLACED …` = order asli ditaruh. Cek juga `logs/live_bets.jsonl` (audit).

---

## 🛑 Cara STOP (hafalkan ini)

| Mau | Perintah |
|---|---|
| **Berhenti taruhan baru** (paling cepat) | `docker exec reyog_live_executor python scripts/live_autonomous_executor.py disarm` |
| **Halt total (kill-switch)** | `docker exec reyog_live_executor python scripts/live_kill_switch.py halt "manual"` |
| **Batalkan SEMUA order terbuka + halt** | `python3 scripts/manual_live_test.py emergency_stop` (di host, dgn env POLY_*) |
| **Matikan container executor** | `docker compose -f docker-compose.free.yml stop live_executor` |
| **Kembali paper sepenuhnya** | set `PAPER_TRADE=true` di `.env` → `docker compose -f docker-compose.free.yml up -d` |
| Lepas halt (lanjut lagi) | `docker exec reyog_live_executor python scripts/live_kill_switch.py clear` |

Kill-switch **otomatis** aktif kalau: rugi harian ≥ $3, 3 kalah beruntun, atau
saldo < $1. Saat halt, executor berhenti menaruh order sampai kamu `clear`.

---

## Cara kerja singkat
Engine + copy-trade menerbitkan *sinyal* ke `arb:polymarket:bets`. Executor
membaca sinyal segar (edge ≥ 5%, umur < 2 mnt), untuk tiap sinyal: cari
token+harga di order book, jalankan semua cek pra-order, lalu taruh **limit BUY**
di best-ask (tak akan fill lebih buruk dari itu), catat ke audit + counter,
tandai sudah dieksekusi (idempoten — tak akan dobel walau restart).

## Kalau ragu
Turunkan cap (`LIVE_TOTAL_CAP_USD=5`), atau tetap paper dulu. Bot ini
memaksimalkan peluang lewat kecepatan + banyak sinyal — **bukan jaminan profit.**
