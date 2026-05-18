# Window 24h v2 — ABORTED (Pivot ke F7+F8 Live Integration)
Generated: 2026-05-19 (Claude Code)
Aborted at: T+0.91h (55 menit setelah start)

---

## Alasan Abort

**User decision**: Stop window v2 paper trade, pivot ke F7+F8 integration.
- F7: Wallet integration (py-clob-client, real Polymarket orders)
- F8: Friction calculation (fees, gas, spread)
- Goal: Validate 1-3 real bets dengan $7 USDC di Polygon
- Modal Rp 200rb: TIDAK deploy hari ini

---

## Data Mentah Saat Abort (T+0.91h)

| Metric | Value |
|--------|-------|
| Window start | 2026-05-18T19:53:15Z |
| Abort time | 2026-05-19T~20:45Z |
| Elapsed | 0.91h of 24h |
| arb:polymarket:bets | **26** |
| arb:poly:resolved | **2** |
| arb:orders | 2 |
| arb:risk:halted | **1** (DrawdownBreaker tripped) |
| arb:risk:polymarket_daily_loss:20260518 | **$500** |

### Resolved Bets (2 total)
1. **SOL Up/Down (May 18 4:00-4:15PM ET)** — stake $500, **WON**, payout $1010.10
2. **ETH Up/Down (May 18 12:00-4:00PM ET)** — stake $500, side=Down, **LOST**, payout $0

### arb:poly:stats
- `eth_updown`: losses=1
- `sol_updown`: wins=1

### Note: Risk Halted Again
DrawdownBreaker tripped saat paper loss ETH Down $500 > 2% daily drawdown dari $10k demo capital.
Ini adalah masalah systemik paper mode: stake_usd=500 terlalu besar untuk demo capital. F6 fix needed.

### Open Bets at Abort
- 24 bets masih status="open" (termasuk BTC range $70k-$72k, end 2026-05-22)
- Tidak akan resolve (engine stopped, paper mode)

---

## Actions Taken for Abort

1. ✅ Redis state snapshot (di atas)
2. ✅ Cron `*/15 window_24h_monitor` — REMOVED
3. ✅ Cron `*/30 post_window_decision` — REMOVED
4. ✅ `docker stop reyog_engine` — STOPPED
5. Redis data: PRESERVED (tidak di-flush, untuk reference)

---

## Lessons dari Window v2

1. **Bets flow bekerja** — 26 bets dalam 55 menit setelah ensemble bypass. G2.1 fix valid.
2. **Paper stake size terlalu besar** — $500/bet dari $10k capital = 5% per bet → trip DrawdownBreaker.
3. **Edge calculation masih paper** — `our_prob=0.7` untuk semua market (hardcoded), bukan signal berbasis data.
4. **F6 fix tetap diperlukan** untuk window paper berikutnya — simulated settlement ≠ real edge.

---

## Next Step: F7+F8 Integration

Lihat: `docs/LIVE_TEST_CHECKLIST.md` (akan dibuat)
Scripts: `scripts/polymarket_live_adapter.py`, `scripts/manual_live_test.py`

---

_Abort decision oleh user. Window ini tidak representatif untuk keputusan G4._
