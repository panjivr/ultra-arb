# PROMPT: Eksekusi Bertahap G0 → G4 — ultra-arb Trading System

> Paste prompt ini ke Claude Code di folder C:\Users\Panji\Projects\ultra-arb
> Mode: Accept edits | Model: Opus 4.x

---

## KONTEKS SISTEM

Kamu adalah sistem eksekusi bertahap untuk project trading bot `ultra-arb` (REYOG CAPITAL).

Hasil audit sebelumnya menunjukkan kondisi nyata:
- PnL paper NEGATIF: -$348 (-3.48%) → edge belum terbukti
- TIDAK ada git → tidak ada rollback → tidak boleh live dulu
- Dependencies di-install inline di Dockerfile → build tidak reproducible
- 7 edge detector + ensemble 3-of-N semua aktif → modal disebar ke pemenang DAN pecundang sekaligus
- Polymarket edge ada → crypto edge belum terbukti

## PRINSIP INTI (JANGAN DILANGGAR)

1. **Uang sungguhan hanya boleh mengalir SETELAH edge terbukti positif** — bukan sebelum
2. **Tidak boleh loncat gerbang** — G0 harus selesai 100% sebelum G1 dimulai
3. **Setiap gerbang punya exit criteria yang terukur** — bukan opini, tapi angka
4. **Audit dulu, eksekusi kemudian** — jangan perbaiki sesuatu yang belum diukur

---

## PETA GERBANG

```
G0 Infra aman → G1 Ukur jujur → G2 Isolasi edge → G3 Edge terbukti → G4 Live mikro
(git, pin)      (atribusi        (matikan rugi,    (forward test      (modal = batas
                 per-strategi)    scale menang)      bergerbang)        rugi maksimal)
```

---

## INSTRUKSI EKSEKUSI

Mulai eksekusi bertahap dari G0 → G1 → G2 → G3 → G4.

Eksekusi DETAIL per detail dari A-Z di setiap gerbang.
JANGAN ada yang terlewat.
JANGAN berhenti sebelum semua selesai.
Gunakan /browse jika perlu cek dokumentasi.
Gunakan bash untuk eksekusi command langsung.

---

## G0 — INFRA LAYAK PEGANG UANG

**Tujuan:** Sistem tidak boleh bisa rugi tanpa rollback.

### G0.1 — Git Init + Commit Semua
```
Lakukan:
1. git init (jika belum ada)
2. Buat .gitignore yang proper (exclude: .env, __pycache__, logs/, *.pyc, node_modules/)
3. git add semua file kecuali yang di .gitignore
4. git commit -m "G0: initial commit — pre-live snapshot"
5. Verifikasi: git log --oneline (harus ada minimal 1 commit)
6. Verifikasi: git status (harus clean)
```

**Exit criteria G0.1:** `git log` menampilkan commit. `git status` = nothing to commit.

### G0.2 — Pin Semua Dependencies
```
Lakukan:
1. Baca semua import di semua file .py
2. Buat requirements.txt dengan versi EXACT (bukan >=, bukan ~=, tapi ==)
   Contoh: ccxt==4.3.89, redis==5.0.1, pandas==2.2.2
3. Jika ada Dockerfile yang install dependencies inline → pindahkan semua ke requirements.txt
4. Update Dockerfile: COPY requirements.txt . → pip install -r requirements.txt
5. Test build: docker compose build (harus 0 error)
6. git commit -m "G0: pin all dependencies to exact versions"
```

**Exit criteria G0.2:** `docker compose build` sukses. requirements.txt ada versi exact semua.

### G0.3 — Isolasi Secret Management
```
Lakukan:
1. Cek semua file .py → cari hardcoded API keys, passwords, URLs dengan credentials
2. Pindahkan SEMUA ke .env
3. Buat .env.example (tanpa nilai asli, hanya key names)
4. Tambahkan .env ke .gitignore
5. Verifikasi: git grep -r "APIKEY\|api_key\|password\|secret" --include="*.py" (harus 0 result)
6. git commit -m "G0: secrets moved to .env, no hardcoded credentials"
```

**Exit criteria G0.3:** Zero hardcoded credentials di source code.

### G0.4 — Health Check Per Service
```
Lakukan:
1. Tambahkan health check endpoint ke setiap Docker service:
   - /health → return {"status": "ok", "service": "<name>", "timestamp": "..."}
2. Update docker-compose.yml: healthcheck untuk setiap service
3. Test: curl http://localhost:<port>/health → harus return 200
4. Test: docker compose ps (semua status harus "healthy")
5. git commit -m "G0: health checks added to all services"
```

**Exit criteria G0.4:** `docker compose ps` semua services = healthy.

### G0 SELESAI — CHECKPOINT
```
Verifikasi final G0:
- git log (ada commits)
- docker compose build (sukses)
- docker compose up -d && docker compose ps (semua healthy)
- .env.example ada, .env di .gitignore
- requirements.txt dengan semua versi exact

Jika semua pass → lanjut G1.
Jika ada yang fail → selesaikan dulu. JANGAN lanjut.
```

---

## G1 — UKUR JUJUR (ATRIBUSI PER STRATEGI)

**Tujuan:** Tahu PERSIS strategi mana yang profit, mana yang rugi. Bukan total PnL saja.

### G1.1 — Tambahkan Trade Tagging
```
Lakukan:
1. Baca semua edge detector yang aktif (7 detector + ensemble)
2. Setiap trade yang dieksekusi WAJIB diberi tag:
   - strategy_id: string (nama detector yang trigger)
   - signal_confidence: float (0-1)
   - timestamp_signal: datetime
   - timestamp_execution: datetime
   - latency_ms: int
3. Simpan tag ini ke database (PostgreSQL atau Redis)
4. git commit -m "G1: trade tagging by strategy added"
```

**Exit criteria G1.1:** Setiap trade punya strategy_id di database.

### G1.2 — Dashboard Atribusi Per Strategi
```
Lakukan:
1. Buat query/view yang menampilkan per strategy_id:
   - total trades
   - win rate
   - total PnL
   - avg PnL per trade
   - Sharpe (jika cukup data)
2. Tampilkan di dashboard REYOG atau output ke log file: /logs/strategy_performance.json
3. Update setiap 1 jam
4. git commit -m "G1: per-strategy attribution dashboard"
```

**Exit criteria G1.2:** Bisa jawab "strategi mana yang profit hari ini?" dengan angka.

### G1.3 — Pisahkan PnL Polymarket vs Crypto
```
Lakukan:
1. Tag semua trades dengan market_type: "polymarket" atau "crypto"
2. Hitung PnL terpisah untuk masing-masing
3. Konfirmasi hasil audit: crypto PnL seharusnya lebih negatif
4. Dokumentasikan temuan ke PROJECT_STATE.md
5. git commit -m "G1: market-type PnL separation"
```

**Exit criteria G1.3:** Tabel jelas: Polymarket PnL vs Crypto PnL terpisah.

### G1 SELESAI — CHECKPOINT
```
Output yang diharapkan setelah G1:
{
  "strategies": [
    {"id": "arb_v1", "pnl": +120, "trades": 45, "winrate": 0.62},
    {"id": "grid_v2", "pnl": -280, "trades": 89, "winrate": 0.34},
    ...
  ],
  "by_market": {
    "polymarket": {"pnl": +200},
    "crypto": {"pnl": -548}
  }
}

Jika output ini ada → lanjut G2.
Jika belum bisa lihat per-strategi → jangan lanjut.
```

---

## G2 — ISOLASI EDGE (MATIKAN YANG RUGI, SCALE YANG MENANG)

**Tujuan:** Hanya strategi dengan edge positif yang jalan. Yang lain dimatikan.

### G2.1 — Kill Switch Per Strategi
```
Lakukan:
1. Buat config: ENABLED_STRATEGIES di .env atau config.yaml
2. Setiap strategi cek config ini sebelum execute signal
3. Default: SEMUA strategi OFF kecuali yang akan diuji
4. Test: matikan satu strategi → verifikasi tidak ada trade dari strategi itu
5. git commit -m "G2: per-strategy kill switch"
```

**Exit criteria G2.1:** Bisa enable/disable strategi tanpa restart sistem.

### G2.2 — Matikan Strategi Negatif
```
Berdasarkan output G1:
1. Identify semua strategi dengan PnL negatif setelah minimum 50 trades
2. Set ENABLED = false untuk semua strategi negatif
3. Verifikasi di dashboard: only enabled strategies generating signals
4. git commit -m "G2: disabled negative-PnL strategies"
```

**Exit criteria G2.2:** Hanya strategi positif yang aktif.

### G2.3 — Batasi Exposure Per Pair
```
Lakukan:
1. Baca semua pair yang diperdagangkan
2. Tambahkan MAX_POSITION_PER_PAIR ke risk manager
3. Default: maksimal 10% dari total modal per pair
4. Tambahkan MAX_OPEN_POSITIONS: maksimal 3 posisi simultan
5. Test di PAPER mode: coba trigger >3 posisi → harus ditolak risk manager
6. git commit -m "G2: position limits added"
```

**Exit criteria G2.3:** Risk manager menolak trade yang melebihi batas posisi.

### G2 SELESAI — CHECKPOINT
```
Verifikasi final G2:
- Hanya strategi positif yang aktif (cek ENABLED_STRATEGIES)
- Kill switch berfungsi
- Position limits berfungsi
- PnL paper HARUS membaik setelah G2 (tunggu 24 jam paper trading)

Jika PnL membaik → lanjut G3.
Jika PnL masih negatif → kembali ke G1, ukur ulang.
```

---

## G3 — EDGE TERBUKTI (FORWARD TEST BERGERBANG)

**Tujuan:** Membuktikan edge dengan uang imajiner sebelum uang nyata.

### G3.1 — Forward Test Protocol
```
Lakukan:
1. Set PAPER_TRADE=true (sudah ada)
2. Set starting capital untuk paper: $10,000 (sudah ada di dashboard)
3. Run selama minimum 7 hari TANPA ubah konfigurasi
4. Log semua trade ke file: /logs/forward_test_results.json
5. Target minimum untuk lanjut ke G4:
   - Total trades: minimum 100
   - Win rate: minimum 55%
   - Total PnL: minimum +2% ($200 dari $10,000)
   - Max drawdown: maksimal 5% ($500)
   - Sharpe ratio: minimum 1.0
```

### G3.2 — Automated Daily Report
```
Lakukan:
1. Buat script: scripts/daily_report.py
2. Jalankan setiap hari 08:00 WIB via cron
3. Output: /logs/daily_report_YYYYMMDD.txt berisi:
   - Total PnL hari ini
   - Total PnL kumulatif
   - Win rate hari ini
   - Strategi paling profitable
   - Strategi paling rugi
   - Alert jika drawdown > 3%
4. git commit -m "G3: daily automated report"
```

### G3.3 — Gate Criteria Checker
```
Lakukan:
1. Buat script: scripts/check_gate_criteria.py
2. Script ini cek apakah semua G3 exit criteria terpenuhi
3. Output: PASS atau FAIL dengan alasan
4. Jalankan manual setiap hari
5. JANGAN lanjut ke G4 jika script ini output FAIL
6. git commit -m "G3: gate criteria checker"
```

**Exit criteria G3:** `python scripts/check_gate_criteria.py` output = PASS.

---

## G4 — LIVE MIKRO (MODAL = BATAS RUGI MAKSIMAL)

**Tujuan:** Live dengan modal minimal, naik bertahap berdasarkan performa.

> ⚠️ G4 HANYA boleh dimulai setelah G3 criteria checker output PASS

### G4.1 — Setup Wallet Bot (Hot Wallet)
```
Lakukan:
1. Buat wallet baru khusus bot (BUKAN wallet personal)
2. Transfer modal awal = jumlah yang sanggup hilang 100% tanpa masalah
   (rekomendasi: Rp 500.000 - Rp 1.000.000 untuk mulai)
3. Simpan private key di .env (bukan di kode)
4. Verifikasi: bot bisa baca balance wallet
5. JANGAN hubungkan wallet personal ke bot
6. git commit -m "G4: hot wallet configured"
```

### G4.2 — Live Mode Toggle
```
Lakukan:
1. Tambahkan LIVE_TRADE=false ke .env (default OFF)
2. Executor harus cek LIVE_TRADE sebelum kirim order ke exchange
3. Tambahkan tombol di dashboard untuk toggle LIVE_TRADE
4. Tombol harus ada konfirmasi: "Anda yakin? Ini akan menggunakan uang nyata."
5. Log setiap toggle: siapa, kapan, dari apa ke apa
6. git commit -m "G4: live trading toggle with confirmation"
```

### G4.3 — Hard Stop Loss Global
```
Lakukan:
1. Tambahkan GLOBAL_STOP_LOSS_PERCENT = 20 ke .env
   (artinya: jika modal turun 20%, sistem STOP otomatis)
2. Monitor berjalan setiap 1 menit cek kondisi ini
3. Jika triggered: LIVE_TRADE otomatis set ke false, alert dikirim
4. TIDAK bisa di-override kecuali manual restart + konfirmasi
5. git commit -m "G4: global stop loss implemented"
```

### G4.4 — Naik Bertahap
```
Protocol kenaikan modal:
- Week 1: modal awal (Rp 500.000)
- Week 2: jika profit → naik 2x (Rp 1.000.000)
- Week 3: jika profit → naik 2x (Rp 2.000.000)
- dst...

ATURAN:
- Naik HANYA jika minggu sebelumnya profit
- Turun KEMBALI ke step awal jika drawdown > 15%
- Maximum modal: tentukan sendiri sesuai kemampuan
```

---

## CHECKPOINT AKHIR — VERIFIKASI SELURUH G0-G4

```bash
# Jalankan ini untuk verifikasi keseluruhan sistem

echo "=== G0 CHECK ===" 
git log --oneline | head -5
docker compose ps
cat .env.example | wc -l

echo "=== G1 CHECK ==="
python scripts/check_strategy_attribution.py

echo "=== G2 CHECK ==="
cat config.yaml | grep ENABLED_STRATEGIES

echo "=== G3 CHECK ==="
python scripts/check_gate_criteria.py

echo "=== G4 CHECK ==="
cat .env | grep LIVE_TRADE
cat .env | grep GLOBAL_STOP_LOSS
```

**Semua harus PASS sebelum uang nyata masuk.**

---

## PERINTAH EKSEKUSI

```
Sekarang mulai eksekusi G0 sampai G4 secara berurutan.
Jangan skip step apapun.
Jangan lanjut ke gerbang berikutnya jika exit criteria belum terpenuhi.
Dokumentasikan setiap perubahan dengan git commit.
Jika menemukan masalah → selesaikan sampai tuntas.
Laporkan setiap checkpoint sebelum lanjut ke gerbang berikutnya.
```
