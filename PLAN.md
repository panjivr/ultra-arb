# Ultra AI Arbitrage Trading System — Implementation Plan

## Context
Building a fully autonomous multi-market arbitrage engine from scratch. Inspired by real-world Claude-powered trading systems (Twitter evidence: BTC bot $66k week-1, $500→$49k in 2 weeks, $4.2k→$187k in 9 days). Target: mathematical edge across prediction markets and crypto, not prediction or hype.

**User requirements:** Full system, Python+Rust, web dashboard, free APIs only, Windows 11.

---

## Markets & APIs (Free, No Subscription)

| Market | API | Testnet Available |
|---|---|---|
| Binance perps + spot | CCXT + `ccxt.pro` async WebSocket | ✅ `testnet.binancefuture.com` |
| Bybit perps | CCXT + `ccxt.pro` | ✅ `api-testnet.bybit.com` |
| Polymarket CLOB | `py-clob-client` (REST polling 500ms) | ✅ sandbox environment |

---

## Tech Stack

- **Python 3.12** (NautilusTrader requirement — install alongside existing 3.14)
- **NautilusTrader 1.208** — core event-driven strategy/risk framework (Rust-powered)
- **CCXT 4.4 (async)** — unified crypto exchange connectivity
- **py-clob-client 0.18** — Polymarket order book access
- **PyO3 + Maturin 1.7** — Rust hot paths (spread calc, Kelly criterion, Kalman filter)
- **TimescaleDB 2.x** (Docker) — time-series market data storage
- **Redis 7** (Docker) — inter-process message bus via Streams
- **FastAPI 0.115 + uvicorn** — dashboard API backend
- **Next.js + Tailwind + Recharts + D3** — real-time dashboard frontend

---

## Project Structure

```
C:\Users\Panji\Projects\ultra-arb\
├── .env                        # API keys, DB DSNs (never committed)
├── docker-compose.yml          # TimescaleDB (5432) + Redis (6379)
├── pyproject.toml              # all Python deps, py -3.12 venv
├── Cargo.toml                  # Rust workspace root
├── rust/
│   └── hot_paths/              # PyO3 crate
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs          # #[pymodule] registration
│           ├── spread_calc.rs  # vectorized spread/mid arithmetic
│           ├── kelly.rs        # Kelly criterion sizing
│           └── kalman.rs       # Kalman filter update step
├── arb/                        # main Python package
│   ├── config.py               # pydantic-settings, loads .env
│   ├── infra/
│   │   ├── db.py               # SQLAlchemy async + TimescaleDB hypertables
│   │   └── redis_bus.py        # XADD/XREADGROUP wrappers (central nervous system)
│   ├── feeds/
│   │   ├── binance_feed.py     # ccxt.pro WebSocket → Redis arb:ticks:BTCUSDT
│   │   ├── bybit_feed.py
│   │   ├── polymarket_feed.py  # 500ms polling → Redis arb:ticks:POLY:{id}
│   │   ├── feed_runner.py      # asyncio.gather all feeds
│   │   └── nautilus_redis_client.py  # LiveDataClient reading from Redis → NautilusTrader QuoteTick
│   ├── strategies/
│   │   ├── base_strategy.py    # ArbitrageStrategy(Strategy) base
│   │   ├── cross_exchange.py   # Binance vs Bybit BTC perp spread
│   │   ├── funding_rate.py     # funding rate carry arbitrage
│   │   ├── basis.py            # spot-perp basis spread
│   │   └── polymarket_arb.py   # Polymarket mispricing vs implied probability
│   ├── models/
│   │   ├── hmm.py              # hmmlearn 3-state regime detection
│   │   ├── cointegration.py    # statsmodels Johansen test, hedge ratio
│   │   ├── bayesian.py         # PyMC Beta-Binomial win rate estimation
│   │   ├── kalman_filter.py    # calls hot_paths.kalman_update via PyO3
│   │   └── model_runner.py     # APScheduler: HMM every 15m, cointegration every 1h
│   ├── risk/
│   │   ├── sizing.py           # KellyPositionSizer → hot_paths.kelly_size, max 2.5% per trade
│   │   ├── circuit_breakers.py # DrawdownBreaker (-2% daily), VolBreaker (3x avg)
│   │   ├── position_manager.py # live exposure tracking, max 5 concurrent positions
│   │   └── risk_runner.py      # asyncio loop, checks every 10s
│   ├── execution/
│   │   ├── paper_trader.py     # NautilusTrader BacktestEngine wrapper
│   │   └── live_executor.py    # NautilusTrader LiveTradingNode (PAPER_TRADE=true routes to sim)
│   ├── dashboard/
│   │   ├── api/
│   │   │   ├── main.py         # FastAPI app factory
│   │   │   ├── routes/pnl.py   # GET /api/pnl?window=24h
│   │   │   ├── routes/signals.py
│   │   │   ├── routes/positions.py
│   │   │   ├── routes/ws.py    # WebSocket /ws/live → Redis stream fan-out at 100ms
│   │   │   └── deps.py
│   │   └── frontend/           # npx create-next-app --typescript --tailwind --app
│   │       └── src/components/
│   │           ├── PnlChart.tsx
│   │           ├── Heatmap.tsx
│   │           ├── CorrelationMatrix.tsx
│   │           └── SignalFeed.tsx
│   └── main.py                 # entrypoint: asyncio.gather all runners
├── scripts/
│   ├── start_trading.ps1
│   └── start_dashboard.ps1
└── tests/unit/ + tests/integration/
```

---

## Redis Stream Layout

```
arb:ticks:{symbol}    — raw tick data (bid/ask/mid) from all feeds
arb:signals           — arbitrage signal objects with probability scores
arb:orders            — order lifecycle events
arb:risk:alerts       — circuit breaker triggers
arb:funding:{symbol}  — funding rate updates
```

**Key rule:** Redis Streams (XADD/XREADGROUP) for inter-process. NautilusTrader MessageBus for intra-process. This lets the dashboard API read live data without coupling into the trading engine process.

---

## 8 Delivery Phases

### Phase 1 — Infrastructure Scaffold
**Build:** docker-compose.yml, .env, pyproject.toml, config.py, db.py (hypertables), redis_bus.py

**Hypertables:**
- `ticks(time, symbol, exchange, bid, ask, mid)` — chunk 1h
- `funding_rates(time, symbol, exchange, rate)`
- `signals(time, strategy, symbol, score, meta JSONB)`
- `trades(time, symbol, side, qty, price, pnl)`

**Verify:** `docker compose up -d` → `asyncio.run(init_db())` creates schema → Redis XADD test message succeeds.

---

### Phase 2 — Market Data Feeds
**Build:** binance_feed.py, bybit_feed.py, polymarket_feed.py, feed_runner.py

**Pattern:** All feeds → write to Redis `arb:ticks:*` streams + persist to TimescaleDB `ticks` table.

**Key:** Binance and Bybit use `ccxt.pro.watch_order_book()` (WebSocket). Polymarket uses `py-clob-client` REST polled every 500ms in an `asyncio.Task`.

**Verify:** `python -m arb.feeds.feed_runner` → `redis-cli XLEN arb:ticks:BTC/USDT:BINANCE` > 0 within 5 seconds.

---

### Phase 3 — Rust Hot Paths (PyO3)
**Build:** `rust/hot_paths/` Cargo crate with 3 pure functions:
- `spread_calc(bid, ask) -> f64` — vectorized batch version also
- `kelly_size(win_prob, win_loss_ratio, max_fraction) -> f64`
- `kalman_update(x, p, z, q, r) -> (f64, f64)` — returns (state, covariance)

Rust deps: `pyo3 = { version = "0.22", features = ["extension-module"] }`, `ndarray = "0.16"`

**Verify:** `maturin develop` in `rust/hot_paths/` → `from hot_paths import kelly_size; kelly_size(0.6, 1.5, 0.25)` → returns float.

---

### Phase 4 — NautilusTrader Strategy Core
**Build:** `nautilus_redis_client.py` (LiveDataClient reading Redis → QuoteTick), `base_strategy.py`, `cross_exchange.py`, `funding_rate.py`, `basis.py`, `paper_trader.py`

**Architecture note:** NautilusTrader CCXT adapters are in the commercial version. Open-source approach: CCXT feeds → Redis → lightweight `LiveDataClient` subclass reads Redis and emits `QuoteTick` objects into NautilusTrader's data engine. Strategies consume these normally.

**Verify:** `python -m arb.execution.paper_trader` runs 1h synthetic backtest, prints trade count + gross PnL.

---

### Phase 5 — ML/Quant Models
**Build:** hmm.py (GaussianHMM 3-state), cointegration.py (Johansen test, hedge ratio, z-score), bayesian.py (PyMC Beta-Binomial win rate), kalman_filter.py (calls Rust), model_runner.py (APScheduler)

**Schedule:** HMM refits every 15 min on last 500 returns from TimescaleDB. Cointegration rescans every 1 hour. Bayesian model updates every 100 trades.

**Verify:** `from arb.models.hmm import RegimeDetector; r = RegimeDetector(); r.fit_synthetic(); r.current_regime()` → returns 0/1/2.

---

### Phase 6 — Risk Engine
**Build:** sizing.py (KellyPositionSizer, clamps to 2.5% account max, scales by HMM regime confidence), circuit_breakers.py (DrawdownBreaker -2%, VolBreaker 3x avg), position_manager.py (max 5 concurrent), risk_runner.py (10s loop)

**Verify:** Unit test feeds DrawdownBreaker a synthetic PnL series breaching -2% → `arb:risk:alerts` receives halt event.

---

### Phase 7 — Dashboard
**Backend:** FastAPI app, routes for `/api/pnl`, `/api/signals`, `/api/positions`, `/ws/live` (WebSocket pushes Redis stream at 100ms cadence).

**Frontend:** Next.js + Tailwind. Components:
- `PnlChart.tsx` — Recharts AreaChart from `/api/pnl`
- `Heatmap.tsx` — D3 per-hour PnL heatmap
- `CorrelationMatrix.tsx` — D3 strategy correlation grid
- `SignalFeed.tsx` — WebSocket consumer, scrolling signal table with probability scores

**Verify:** `uvicorn arb.dashboard.api.main:app` serves `/api/pnl` with data; `npm run dev` renders dashboard at localhost:3000 with live chart updates.

---

### Phase 8 — Full Integration + Paper Trade Mode
**Build:** `live_executor.py` (LiveTradingNode wiring all strategies + risk + models), `main.py` entrypoint, PowerShell start scripts

**Paper trade:** `PAPER_TRADE=true` in `.env` → orders routed to NautilusTrader SimulatedExchangeConfig. Real testnet keys used for market data only.

**Verify:** `python -m arb.main` starts without errors → dashboard shows live tick stream → after 10 minutes `/api/pnl` returns non-zero paper trade PnL.

---

## Critical Architectural Decisions

1. **Python 3.12 for this project** — NautilusTrader 1.208 requires 3.12. Use `py -3.12 -m venv .venv` even though system has 3.14.

2. **CCXT decoupled from NautilusTrader via Redis** — Avoids implementing NautilusTrader's full venue adapter protocol. Feeds write to Redis; a slim `LiveDataClient` reads Redis → NautilusTrader. Simpler, more maintainable.

3. **Polymarket outside NautilusTrader venue model** — py-clob-client is REST-only (no WebSocket). Run as a separate async poller → Redis. Strategy reads from Redis directly.

4. **PyO3 hot paths are pure/stateless** — No heap state retained between calls. Kalman covariance matrix held in Python as a float, passed in on each call. GIL-safe, callable from any thread.

5. **Paper-first, live-second** — All live execution code respects `PAPER_TRADE` flag. Never touch real capital until 30 days of paper trading shows positive expectancy.

---

## AI Decision Metadata (every signal must include)
```python
@dataclass
class ArbitrageSignal:
    probability_score: float       # 0-1
    confidence_interval: tuple     # (low, high)
    risk_reward_ratio: float
    expected_value: float
    liquidity_score: float         # 0-1
    volatility_score: float
    slippage_estimate_bps: float
    correlation_impact: float
    execution_feasibility: float   # 0-1
    failure_probability: float
    regime: int                    # HMM state 0/1/2
```

---

## Verification: End-to-End Test
1. `docker compose up -d` → TimescaleDB + Redis healthy
2. `python -m arb.feeds.feed_runner` → ticks flowing into Redis + DB
3. `maturin develop` in `rust/hot_paths/` → PyO3 module importable
4. `python -m arb.execution.paper_trader` → backtest runs, PnL printed
5. `python -m arb.main` → full system live (paper trade mode)
6. Dashboard at localhost:3000 shows live PnL, signals, positions
7. After 30 days paper trading with positive expectancy → flip `PAPER_TRADE=false` for live
