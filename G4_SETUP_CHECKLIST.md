# G4 Micro Live Setup Checklist
> Auto-generated after PASS verdict — demo_paper_1h.py
> Modal: Rp 200.000 (~$12 USD) — dianggap biaya eksperimen, bisa hilang semua.

---

## STATUS: SIAP DIISI OLEH USER

---

## STEP 1 — Buat Wallet & Deposit

### Exchange: Binance
- [ ] Login / buat akun Binance
- [ ] Deposit Rp 200.000 (~$12 USDT) ke Spot wallet
- [ ] Aktifkan Futures trading (atau gunakan Spot untuk cross-exchange arb)
- [ ] Set leverage ke **1x** (no leverage untuk micro run)

### Polymarket (opsional, aktifkan hanya jika ingin poly bets live)
- [ ] Buat MetaMask wallet (atau gunakan yang ada)
- [ ] Bridge minimal $5 USDC ke Polygon network
- [ ] Connect ke https://polymarket.com → approve CLOB contract
- [ ] Export private key: MetaMask → Settings → Security → Export Private Key
- [ ] Simpan private key di tempat aman

---

## STEP 2 — Generate API Keys

### Binance API
- [ ] Buka: https://www.binance.com/en/my/settings/api-management
- [ ] Klik "Create API" → pilih System Generated
- [ ] Label: "reyog-vps"
- [ ] Enable: ✅ Enable Reading, ✅ Enable Spot & Margin Trading
- [ ] Restrict Access by IP: **103.31.38.106**
- [ ] Catat: API Key + Secret Key

### Bybit API (opsional — untuk cross-exchange arb Binance vs Bybit)
- [ ] Buka: https://www.bybit.com/app/user/api-management
- [ ] Buat API key → enable Trade (Derivatives + Spot)
- [ ] IP restriction: **103.31.38.106**
- [ ] Catat: API Key + Secret Key

---

## STEP 3 — Update .env di VPS

SSH ke VPS:
```bash
ssh -i deploy/deploy_key reyogcapital165@103.31.38.106
nano /home/reyogcapital165/reyog-capital/.env
```

Ubah nilai berikut (jangan ubah yang lain):
```bash
# Paper → Live
PAPER_TRADE=false

# Binance (wajib)
BINANCE_API_KEY=<isi API Key dari Step 2>
BINANCE_API_SECRET=<isi Secret Key dari Step 2>
BINANCE_TESTNET=false

# Bybit (opsional)
BYBIT_API_KEY=<isi atau biarkan kosong>
BYBIT_API_SECRET=<isi atau biarkan kosong>
BYBIT_TESTNET=false

# Polymarket (opsional)
POLYMARKET_PRIVATE_KEY=<private key tanpa 0x, atau biarkan kosong>
POLYMARKET_SANDBOX=false
```

---

## STEP 4 — Validasi (WAJIB sebelum activate)

```bash
cd /home/reyogcapital165/reyog-capital
python scripts/g4_micro_activate.py --validate-only
```

Output harus: `✅ ALL CHECKS PASSED`

Jika ada ❌ — perbaiki dulu, jangan lanjut.

---

## STEP 5 — Activate Live

```bash
python scripts/g4_micro_activate.py
```

Script akan:
1. Jalankan validator (exit otomatis jika gagal)
2. Minta konfirmasi ketik `LANJUT G4`
3. Set PAPER_TRADE=false + G4 position limits di .env
4. Restart reyog_engine dengan config live

**JANGAN skip Step 4. JANGAN jalankan ini tanpa mengisi wallet + API keys.**

---

## Parameter G4 Micro

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| Total modal | Rp 200.000 (~$12) | Dianggap hilang |
| Max per posisi | 1% = ~$0.12 | MAX_POSITION_PCT=1.0 |
| Max open sekaligus | 3 posisi = ~$0.36 | MAX_CONCURRENT_POSITIONS=3 |
| Global stop loss | 50% = ~$6 | Seluruh sistem berhenti |
| Target realistis | $0.10–0.50/hari | JIKA edge positif |

---

## Emergency Stop (kapan saja)

```bash
# Dari local machine:
ssh -i deploy/deploy_key reyogcapital165@103.31.38.106 \
  "docker exec reyog_redis redis-cli -a reyog_redis_secret \
   SET arb:risk:halted MANUAL_STOP"

# Atau langsung di VPS:
docker exec reyog_redis redis-cli -a reyog_redis_secret SET arb:risk:halted MANUAL_STOP
```

---

## Monitor Dashboard

https://103-31-38-106.sslip.io

Pantau: PnL tab, Positions tab, Risk tab
