# Cara Deposit & Switch ke Real Trading

> ⚠️ **PENTING — BACA SEMUA:** Sistem ini belum pernah live. Project memory mencatat aturan "30 hari paper trading dengan positive expectancy DULU sebelum sentuh modal real." Risiko kerugian total nyata. Mulai dengan **modal kecil ($100-$500)** untuk validasi sebelum scale.

---

## 1. Binance — Spot + Perpetual

### Buat akun (kalau belum)
1. Daftar di **https://www.binance.com/** (atau .me kalau di-block).
2. KYC level 1 (KTP) — wajib untuk withdraw.
3. Aktifkan **2FA Google Authenticator** (jangan SMS).

### Deposit USDT
1. **Wallet → Deposit → Pilih USDT**.
2. **Jaringan: pilih TRC20** (fee paling murah, ~$1) atau **BEP20** (fee ~$0.30).
   - ❌ **JANGAN** pakai ERC20 — fee gas Ethereum bisa $20-50.
3. Copy alamat deposit → kirim USDT dari exchange lain/bank.
4. Konfirmasi onchain: TRC20 = ~1 menit, BEP20 = ~30 detik.

### Transfer ke Futures wallet
- Setelah USDT masuk spot wallet:
- **Wallet → Transfer → From Spot → To USD-M Futures** → masukkan jumlah.
- Futures wallet ini yang dipakai untuk perpetual contracts.

### Generate API key untuk trading
1. **Akun → API Management → Create API**.
2. **Label**: `ultra-arb-trading`.
3. **Permissions** (centang):
   - ✅ Enable Reading
   - ✅ Enable Spot & Margin Trading
   - ✅ Enable Futures
   - ❌ **JANGAN** Enable Withdrawals (jangan kasih kunci withdraw ke bot!)
4. **IP Restriction**: tambahkan IP server kamu (kalau VPS) atau IP publik rumah (cek di whatismyipaddress.com).
5. Copy **API Key** + **Secret Key** — secret cuma muncul SEKALI.

---

## 2. Bybit — Perpetual

### Buat akun
1. Daftar di **https://www.bybit.com/**.
2. KYC level 1.
3. 2FA wajib.

### Deposit USDT
1. **Assets → Deposit → USDT**.
2. **Pilih TRC20** atau **BEP20**.
3. Copy alamat → transfer.

### Setup API
1. **Profile → API → Create New Key → System-generated API Keys**.
2. **API Key Permissions**:
   - ✅ Read-Write
   - ✅ Unified Trading (Spot + Derivatives)
   - ❌ **JANGAN** Withdraw
3. **IP Binding**: lock ke IP kamu.
4. Copy API Key + Secret.

---

## 3. Polymarket (opsional — prediction markets)

### Setup Polygon wallet
1. Install **MetaMask** browser extension.
2. Add Polygon network (chainId 137).
3. Buat wallet baru — simpan seed phrase OFFLINE.
4. Catat private key dari MetaMask (Export Private Key).

### Funding
1. Beli **USDC** di exchange (Binance/Bybit).
2. Withdraw USDC ke alamat MetaMask kamu, **pilih jaringan Polygon (MATIC)**.
3. Butuh ~$5 MATIC untuk gas fees.

### Polymarket API
1. **https://docs.polymarket.com/** → connect wallet.
2. Generate L2 API credentials di **app.polymarket.com → Settings → API**.

---

## 4. Update `.env` di Project

Edit file `C:\Users\Panji\Projects\ultra-arb\.env`:

```env
# Switch dari paper ke live trading
PAPER_TRADE=false

# Binance — pakai mainnet (testnet=false)
BINANCE_API_KEY=isi_dari_step_di_atas
BINANCE_API_SECRET=isi_dari_step_di_atas
BINANCE_TESTNET=false

# Bybit
BYBIT_API_KEY=isi_dari_step_di_atas
BYBIT_API_SECRET=isi_dari_step_di_atas
BYBIT_TESTNET=false

# Polymarket (opsional)
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_PRIVATE_KEY=
POLYMARKET_SANDBOX=false

# Risk limits — JANGAN naikkan terlalu agresif di awal
MAX_DRAWDOWN_PCT=2.0          # halt kalau loss harian -2%
MAX_POSITION_PCT=2.5          # max 2.5% account per posisi
MAX_CONCURRENT_POSITIONS=5
VOL_BREAKER_MULTIPLIER=3.0
```

---

## 5. Step-by-Step Launch Live Trading

### Hari 1 — Smoke test dengan $100
```powershell
# 1. Pastikan paper trading masih ON dulu untuk test
notepad .env  # confirm PAPER_TRADE=true

# 2. Pakai api key REAL tapi dengan PAPER_TRADE=true
#    Ini cuma test koneksi feed, gak ada trade real
python -m arb.main

# 3. Tonton dashboard di localhost:3000 selama 1 jam
#    Pastikan ticks masuk dari Binance/Bybit REAL
#    Pastikan signals di-generate
#    Pastikan TIDAK ada order error
```

### Hari 2 — Live dengan modal kecil ($100-$200)
```powershell
# 1. Edit .env: PAPER_TRADE=false
notepad .env

# 2. Lower posisi max untuk safety
#    MAX_POSITION_PCT=1.0  (cuma 1% per trade)
#    MAX_CONCURRENT_POSITIONS=2

# 3. Run
python -m arb.main

# 4. PANTAU CONSTANT — 24/7 untuk minggu pertama
#    Dashboard di localhost:3000
#    Buka juga aplikasi Binance/Bybit untuk cross-check
#    Set alert di HP kalau dashboard offline
```

### Hari 7-30 — Scale gradual
- Kalau win rate > 55% dan max DD < 1.5%, naikkan modal 2x setiap minggu.
- Stop kalau:
  - Drawdown harian -2% (auto-halt sudah aktif)
  - 3 hari berturut negatif
  - Bug kelihatan di logs

---

## 6. Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| **Bug di code = loss real money** | Test paper minimum 30 hari dulu |
| **API key bocor** | IP whitelist + JANGAN enable withdraw permission |
| **Exchange downtime saat punya posisi** | Sistem otomatis halt kalau feed stuck |
| **Flash crash / black swan** | Drawdown breaker stop di -2% harian |
| **Listrik mati** | Pakai VPS murah ($5/bln di Vultr/Hetzner) atau UPS |
| **Bot lupa close posisi** | `position_manager` auto-close kalau timeout |
| **Slippage besar di pair illiquid** | Tradeable threshold sudah filter liquidity > 30% |

---

## 7. Estimasi Modal vs Volume Trading

| Modal | Position size (1%) | Trades/jam realistic | Profit/hari (0.1% edge) |
|---|---|---|---|
| $500 | $5 | ~50 (HFT) | $2-5 |
| $2,000 | $20 | ~50 | $5-15 |
| $10,000 | $100 | ~100 | $20-50 |
| $50,000 | $500 | ~200 | $50-200 |

**Catatan:** angka-angka di atas asumsi sistem berjalan baik. Kerugian sama bisa terjadi kalau market regime berubah.

---

## 8. Kalau Ada Masalah

- **Order rejected**: cek API key permission, IP whitelist, balance Futures wallet.
- **Feed stuck**: restart `python -m arb.main` — sistem akan reconnect otomatis.
- **Halted**: cek `arb:risk:alerts` di Redis, atau dashboard Risk Engine panel.
- **Tidak ada signal**: regime mungkin "high vol" — sistem auto-reduce sizing.

**Log file**:
- FastAPI: `C:\Users\Panji\fastapi.log`
- Trading engine: stdout dari `python -m arb.main`
- Redis: `redis-cli MONITOR` untuk lihat semua command real-time
