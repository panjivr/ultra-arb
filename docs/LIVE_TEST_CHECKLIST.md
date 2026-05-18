# Live Test Checklist — $7 USDC Polymarket
F7+F8 Integration Validation

**Capital**: $7 USDC di Polygon wallet
**Max spend**: $5 (sisakan $2 buffer)
**Max per bet**: $2
**Daily loss limit**: $3

---

## Phase 0 — Pre-Test Setup

### Environment
- [ ] `POLY_PRIVATE_KEY` set di `.env` di VPS
- [ ] `POLY_WALLET_ADDRESS` set di `.env` di VPS
- [ ] `.env` ada di `.gitignore` (JANGAN commit private key)
- [ ] `pip install py-clob-client` berhasil di VPS

### Install & Verify
```bash
# Di VPS:
cd /home/reyogcapital165/reyog-capital
pip install py-clob-client
python3 scripts/manual_live_test.py setup
```
Expected output:
- `✅ Client initialized`
- `USDC: $7.xxxx` (balance terlihat)
- `✅ Allowance sufficient` ATAU warning tentang approval

### Token Approval (jika diperlukan)
Jika `allowance_usdc < 1.0`:
- [ ] Buka Polymarket.com di browser dengan wallet yang sama
- [ ] Coba deposit/withdraw $0 untuk trigger approval tx
- [ ] Atau: approve manual via Polygonscan (advanced)
- [ ] Re-run `setup` — allowance harus naik

### Kill-Switch Test
```bash
python3 scripts/live_kill_switch.py test
python3 scripts/live_kill_switch.py halt "test halt"
# Verify: manual_live_test.py dry_run harus block
python3 scripts/live_kill_switch.py clear
```
- [ ] Halt berhasil di-set
- [ ] dry_run menunjukkan "BLOCKED — Kill-switch active"
- [ ] Clear berhasil, status kembali "ACTIVE"

---

## Phase 1 — Find Market

### Criteria untuk market yang dipilih
- [ ] End date: **6–24 jam dari sekarang** (bukan 5 menit, bukan 7 hari)
- [ ] Market type: Yes/No atau Up/Down sederhana
- [ ] Liquidity: ada bid + ask di order book (cek via `market_info`)
- [ ] Price: antara 0.10–0.90 (hindari extreme odds)

### Commands
```bash
python3 scripts/manual_live_test.py find_market "bitcoin"
python3 scripts/manual_live_test.py find_market "ethereum"
# Pilih condition_id yang menarik

python3 scripts/manual_live_test.py market_info <condition_id>
# Catat: token_id untuk outcome yang mau dibeli
```

- [ ] Market ditemukan dengan end_date sesuai kriteria
- [ ] Order book menunjukkan ada liquidity (best_bid dan best_ask tidak None)
- [ ] Spread < 10% (cek via `dry_run`)
- [ ] **Catat**: `token_id` untuk outcome yang dipilih

---

## Phase 2 — Dry Run Test

```bash
python3 scripts/manual_live_test.py dry_run <token_id> BUY <price> 1.0
```

- [ ] Output menunjukkan semua safety checks ✅
- [ ] Friction < 10%
- [ ] "Order signed successfully (not submitted)"
- [ ] Cek Polymarket.com "My Bets" — **tidak ada order baru** (dry run = nothing submitted)

---

## Phase 3 — First Real Bet ($1)

### Pre-bet checklist
- [ ] Kill-switch clear (`kill_switch status` = ACTIVE)
- [ ] Balance ≥ $1.10 (bet + gas buffer)
- [ ] Paham market question dan outcome yang dibeli
- [ ] End date 6–24h dari sekarang
- [ ] Siap menerima loss (ini adalah test, bukan profit optimization)

### Place bet
```bash
python3 scripts/manual_live_test.py place <token_id> BUY <price> 1.0 --confirm
# Ketik YES di prompt konfirmasi
```

### Post-bet verification
- [ ] Output menunjukkan `order_id` dan `tx_hash`
- [ ] Cek Polymarket.com "My Bets" — order muncul
- [ ] Cek wallet balance — USDC turun ~$1 + gas
- [ ] Redis log: `docker exec reyog_redis redis-cli -a reyog_redis_secret LLEN arb:live:orders` = 1
- [ ] File log: `cat logs/live_bets.jsonl` — ada 1 entry

---

## Phase 4 — Order Tracking

```bash
python3 scripts/manual_live_test.py status <order_id>
```

- [ ] Status: `live` (open/pending) atau `matched` (filled)
- [ ] Jika tidak filled dalam 10 menit, cancel dan coba market order atau adjust price
- [ ] Jika need cancel: `python3 scripts/manual_live_test.py cancel <order_id>`

---

## Phase 5 — Wait for Resolution

- [ ] Market end time tercapai
- [ ] Cek Polymarket.com — market resolved (ada outcome)
- [ ] Catat hasil: **WON** atau **LOST**

### Record hasil (manual, untuk F6 tracking)
```
Market: [question]
Bet: [side] @ [price] = $[cost]
Outcome: WON/LOST
Actual payout: $[payout]
Paper prediction (our_prob): [x.xx]
Real implied prob (entry price): [x.xx]
Delta: [paper - real]
```

---

## Phase 6 — Optional Second Bet (jika Phase 3 berhasil)

- [ ] Balance masih ≥ $2.10 setelah bet pertama
- [ ] Total spent ≤ $3 (sisakan $2 dari $5 limit)
- [ ] Repeat Phase 1–5 dengan market berbeda
- [ ] Jangan bet di market yang sama (diversifikasi test)

---

## Hard Limits (enforced by code)

| Limit | Value | Enforcement |
|-------|-------|-------------|
| Max per bet | $2.00 | `live_safety_checks.py` |
| Daily total | $5.00 | Redis daily_spend counter |
| Max daily loss | $3.00 | `live_kill_switch.py` auto-halt |
| Max consec. losses | 3 | `live_kill_switch.py` auto-halt |
| Min wallet balance | $1.00 | `live_kill_switch.py` auto-halt |
| Market end min | 1h | `live_safety_checks.py` |
| Market end max | 168h | `live_safety_checks.py` |

---

## Emergency

```bash
# Cancel everything + halt immediately:
python3 scripts/manual_live_test.py emergency_stop

# Check why halted:
python3 scripts/live_kill_switch.py status

# Resume after investigating:
python3 scripts/live_kill_switch.py clear
```

---

## After Test — Document Results

Update `docs/LIVE_TEST_RESULTS.md`:

```
| # | Market | Side | Price | Size | Paper prob | Real outcome | PnL | Notes |
|---|--------|------|-------|------|-----------|--------------|-----|-------|
| 1 | ...    | BUY  | 0.45  | 1.0  | 0.70       | WON          | ... |       |
```

Calculate:
- Actual friction vs estimated (compare gas paid on Polygonscan)
- Paper PnL prediction vs real PnL
- → Input for F6 settlement fix planning

---

_Created by Claude Code for Reyog Capital F7+F8 live test phase._
