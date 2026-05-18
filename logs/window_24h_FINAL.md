## Window 24 Jam — Hasil Jujur
Period: 2026-05-16T22:46:26Z -> 2026-05-17T22:46:26Z

### Crypto Path (emit_trades, source=REAL)
- Total trades (CLOSE): 544
- Wins: 174, Losses: 370
- Win rate: 32.0%
- Total PnL: $-26.78
- Avg per trade: $-0.0492
- Strategi terbaik: CrossExchange PnL $-26.7754
- Strategi terburuk: CrossExchange PnL $-26.7754

### Polymarket Path (emit_polymarket_bets, source=polymarket)
- Total bets resolved (CLOSE): 0
- Wins: 0, Losses: 0
- Win rate: 0.0%
- Total PnL: $0
- Avg per bet: $0.0
- Strategi terbaik: (none) PnL $0.0
- Strategi terburuk: (none) PnL $0.0
- arb:poly:stats (per asset): {}

### Risk Events
- arb:risk:halted triggered: 0 kali (lihat observations log)
- Daily loss breakers: {}
- Container restarts (delta vs baseline): 0
- Error count (last 6h sample): 10

### Verifikasi Integritas
- Double-count check: arb:poly:resolved size = 0
  (resolved bets harus = unique; tidak ada N-count)
- WRONGTYPE errors: cek observations/cron log (target 0)
- emit_trades single writer: arb:orders source breakdown =
  {"REAL": 544}
  (hanya REAL + polymarket; tidak ada PAPER_TRADE/LiveExecutor)

### Verdict Awal G1.3
- Crypto edge: NEGATIF (EV $-0.0492/trade, n=544)
- Polymarket edge: ZERO (EV $0.0/bet, n=0)
- Recommendation G2: crypto=DISABLE, polymarket=DISABLE (catatan: Polymarket resolusi = simulated settlement F6, perlu validasi nyata sebelum live)

_Generated autonomously by window_24h_monitor.py at T+24h._
