# PROJECT_STATE.md — ultra-arb (Reyog Capital)
> Generated: 2026-05-16 | Use this to bootstrap new chats

## Overview
Autonomous multi-market arbitrage trading system. Python 3.12 + Rust hot-paths. Paper trading mode, real market data. VPS: `103.31.38.106` (IDCloudHost, AlmaLinux, 7 Docker services).

---

## Folder Structure

```
ultra-arb/
├── arb/                        # Main Python package
│   ├── config.py               # Pydantic settings (env vars)
│   ├── main.py                 # Async entrypoint, gathers all tasks
│   ├── infra/
│   │   ├── db.py               # SQLAlchemy async + TimescaleDB, 4 hypertables
│   │   └── redis_bus.py        # Redis Lists message bus (LPUSH/LRANGE)
│   ├── feeds/
│   │   ├── binance_feed.py     # ccxt.pro WebSocket, publishes ticks + funding
│   │   ├── bybit_feed.py       # same pattern for Bybit
│   │   ├── polymarket_feed.py  # REST polling 500ms, Gamma API
│   │   └── feed_runner.py      # asyncio.gather all 3
│   ├── strategies/
│   │   ├── base_strategy.py    # ArbitrageSignal(12 fields), is_tradeable()
│   │   ├── cross_exchange.py   # Binance vs Bybit spread arb
│   │   ├── funding_rate.py     # Delta-neutral carry
│   │   ├── basis.py            # Spot-perp basis
│   │   └── polymarket_arb.py   # YES+NO complement arb, mispricing >5%
│   ├── models/
│   │   ├── hmm.py              # GaussianHMM 3-state regime (refit 15min)
│   │   ├── kalman_filter.py    # KalmanSpreadTracker (Rust fallback to Python)
│   │   ├── cointegration.py    # Johansen test, hedge ratio (refit 1h)
│   │   ├── bayesian.py         # PyMC Beta-Binomial win-rate
│   │   └── model_runner.py     # APScheduler refit scheduler
│   ├── risk/
│   │   ├── sizing.py           # Kelly criterion, half-Kelly, regime scaling
│   │   ├── circuit_breakers.py # DrawdownBreaker (-2%/day), VolBreaker (3x avg)
│   │   ├── position_manager.py # Max 5 concurrent positions
│   │   └── risk_runner.py      # 10s async check loop
│   ├── execution/
│   │   ├── live_executor.py    # Consumes arb:signals; paper or live orders
│   │   └── paper_trader.py     # NautilusTrader BacktestEngine wrapper
│   ├── edges/                  # 6 AI edge detectors (run in parallel)
│   │   ├── yesno_arb.py        # YES+NO sum < $1 (30s)
│   │   ├── smart_money.py      # Whale copy-trade $25-$5000 (120s)
│   │   ├── time_decay.py       # Near-expiry convergence (30s)
│   │   ├── related_markets.py  # Probability ordering violations (60s)
│   │   ├── news_reaction.py    # Breaking news bet <15s (15s)
│   │   └── basis_carry.py      # Funding APR >3% on BTC/ETH/SOL/BNB/XRP (120s)
│   └── dashboard/
│       ├── api/
│       │   ├── main.py         # FastAPI app, 14 routers
│       │   ├── deps.py         # DB/Redis DI
│       │   └── routes/         # 16 route modules (pnl, signals, positions,
│       │                       #   stats, wallet, bloomberg, markets,
│       │                       #   polymarket, edges, extended_stats,
│       │                       #   latency, firehose, financial,
│       │                       #   compounding, activity, ws)
│       └── frontend/           # Next.js 14 + Tailwind, 28 components
├── scripts/
│   ├── real_market_engine.py   # Gate.io + HTX real prices, 100ms tick emit
│   ├── edge_runner.py          # asyncio.gather all 6 edges
│   ├── auto_deploy.py          # SSH deploy via paramiko
│   ├── integration_test.py
│   ├── init_db.py
│   ├── seed_demo_data.py
│   ├── live_simulator.py
│   └── verify_real.py
├── rust/hot_paths/src/
│   ├── spread_calc.rs          # Vectorized spread math
│   ├── kelly.rs                # Kelly criterion
│   └── kalman.rs               # Kalman filter update
├── tests/
│   └── unit/                   # test_kalman, test_hmm, test_circuit_breakers
├── deploy/                     # nginx.conf, Dockerfiles, deploy.sh, SSH key
├── docs/                       # 00-original-plan, 03-vps, 04-idcloudhost, 05-deposit
├── runtime-logs/               # engine.log, fastapi.log, deploy.log
├── docker-compose.yml          # 7-service stack
├── pyproject.toml              # Python 3.12, all deps
├── Cargo.toml                  # Rust workspace
└── .env.example                # 56 env vars template
```

---

## Dependencies (pyproject.toml)

| Category | Packages |
|----------|----------|
| Trading | `nautilus_trader==1.208.0`, `ccxt[async]>=4.4.0`, `py-clob-client>=0.18.0` |
| DB | `sqlalchemy[asyncio]>=2.0.0`, `asyncpg>=0.30.0`, `alembic>=1.14.0` |
| Cache | `redis[hiredis]>=5.2.0` |
| ML | `numpy>=2.0`, `pandas>=2.2`, `scipy>=1.15`, `scikit-learn>=1.6`, `statsmodels>=0.14`, `hmmlearn>=0.3`, `pymc>=5.19` |
| API | `fastapi>=0.115`, `uvicorn[standard]>=0.34`, `httpx>=0.28`, `websockets>=13` |
| Config | `pydantic-settings>=2.7`, `python-dotenv>=1.0` |
| Scheduling | `apscheduler>=3.10` |
| Rust | `maturin>=1.7` (PyO3 build) |
| Dev | `pytest`, `mypy`, `ruff`, `pytest-asyncio`, `pytest-cov` |

---

## Main Logic Flow

```
real_market_engine.py (Gate.io + HTX)
    → Redis arb:ticks:{symbol}:USDT:{GATE|HTX}

binance_feed / bybit_feed (ccxt.pro WebSocket)
    → Redis arb:ticks:{symbol}:BINANCE|BYBIT
    → Redis arb:funding:{symbol}:{exchange}
    → DB: ticks + funding_rates hypertables

polymarket_feed (REST 500ms)
    → Redis arb:ticks:POLY:{token_id}

strategies (cross_exchange, funding_rate, polymarket_arb)
    → read ticks from Redis
    → generate ArbitrageSignal(12 fields)
    → Redis arb:signals

edges (6 detectors in edge_runner.py)
    → Redis arb:edges:{name}

model_runner (APScheduler)
    → HMM refit 15min → regime (0/1/2)
    → cointegration refit 1h → hedge ratio
    → Bayesian refit per 100 trades → win rate

risk_runner (10s loop)
    → DrawdownBreaker: halt if daily PnL ≤ -2%
    → VolBreaker: halt if 5min vol > 3x 30d avg

live_executor (consumes arb:signals)
    → risk checks (circuit breakers, position limit, Kelly sizing)
    → PAPER_TRADE=true → arb:orders (simulated)
    → PAPER_TRADE=false → ccxt live orders (Binance + Bybit)

FastAPI (dashboard/api/main.py)
    → reads Redis + DB → serves 14 routers
    → WebSocket /ws/live → 100ms cadence

Next.js frontend → 28 components, real-time charts
```

---

## Redis Bus Layout

```
arb:ticks:{symbol}:USDT:{exchange}    # tick bid/ask/mid
arb:ticks:POLY:{token_id}             # polymarket ticks
arb:funding:{symbol}:{exchange}       # funding rates
arb:signals                           # ArbitrageSignal objects
arb:orders                            # order events (paper)
arb:risk:alerts                       # circuit breaker triggers
arb:edges:yesno_arb                   # YES+NO sum opportunities
arb:edges:smart_money                 # whale signals
arb:edges:time_decay                  # near-expiry convergence
arb:edges:related_markets             # prob ordering violations
arb:edges:news_reaction               # news bet signals
arb:edges:basis_carry                 # funding APR opportunities
arb:edges:wallet_stats:{wallet}       # per-wallet PnL (24h TTL)
arb:edges:wallet_volume_24h           # sorted set top wallets
arb:edges:smart_wallets               # top-15 wallet summary
arb:latency:{stage}                   # ns-precision timing
```

---

## DB Schema (TimescaleDB, 4 hypertables, 1h chunks)

| Table | Key Columns |
|-------|-------------|
| `ticks` | time, symbol, exchange, bid, ask, mid |
| `funding_rates` | time, symbol, exchange, rate |
| `signals` | time, strategy, symbol, score, meta JSONB |
| `trades` | time, symbol, side, qty, price, pnl, strategy, exchange |

---

## Key .env Variables

```bash
PAPER_TRADE=true                   # Gate to live trading
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://redis:6379/0
BINANCE_API_KEY / SECRET           # + BINANCE_TESTNET=true
BYBIT_API_KEY / SECRET             # + BYBIT_TESTNET=true
POLYMARKET_API_KEY / SECRET / PASSPHRASE / PRIVATE_KEY  # + POLYMARKET_SANDBOX=true
FINANCIAL_DATASETS_API_KEY
MAX_DRAWDOWN_PCT=2.0
MAX_POSITION_PCT=2.5
MAX_CONCURRENT_POSITIONS=5
VOL_BREAKER_MULTIPLIER=3.0
REYOG_DOMAIN=your-domain.com
CORS_ORIGINS=...
```

---

## How to Run

### Local dev
```bash
# Backend API
.venv\Scripts\python.exe -m uvicorn arb.dashboard.api.main:app --port 8000

# Market engine (real prices)
.venv\Scripts\python.exe scripts/real_market_engine.py

# Edge detectors
.venv\Scripts\python.exe scripts/edge_runner.py

# Full trading engine
.venv\Scripts\python.exe -m arb.main

# Frontend
cd arb/dashboard/frontend && npm run dev

# Tests
.venv\Scripts\python.exe -m pytest tests/unit/
```

### VPS production
```bash
# On VPS: docker compose up -d --build
# Auto-deploy from local:
.venv\Scripts\python.exe scripts/auto_deploy.py 103.31.38.106 <password> reyogcapital165

# Check status
docker compose ps
docker compose logs -f engine
```

---

## Architecture Notes

- **NautilusTrader decoupled from ccxt via Redis** — avoids venue adapter protocol
- **Polymarket outside NautilusTrader** — py-clob-client is REST-only
- **Redis Lists (not Streams)** — compatibility with Redis 3.x+
- **Rust PyO3 hot-paths are stateless** — GIL-safe, callable from any thread; Python fallback if not compiled
- **12-field ArbitrageSignal** — prob, confidence, EV, liquidity, volatility, execution_feasibility, regime, direction + more
- **is_tradeable() gate**: prob > 0.55 AND EV > 0 AND liquidity > 0.3 AND feasibility > 0.5
- **Half-Kelly sizing** — max 2.5%, regime-scaled (regime 0→1x, 1→0.7x, 2→0.3x)
- **Paper-first** — PAPER_TRADE=true; flip to false only when ready for live

---

## Current State (2026-05-16)

| Item | Status |
|------|--------|
| Mode | PAPER TRADE (safe) |
| VPS | 7/7 services healthy, 24/7 |
| Data | REAL prices (Gate.io + HTX public APIs) |
| Edge detectors | 6 active, scanning Polymarket 24/7 |
| Dashboard | 28 components, 14 routers, 100Hz WebSocket |
| Tests | Unit tests pass (Kalman, HMM, circuit breakers) |
| Next step | Connect real wallet → verify signals → flip PAPER_TRADE=false |

---

## Known Issues / TODOs

- Rust hot-paths need `maturin develop` compile before use (Python fallback active if missing)
- Polymarket private key required for live CLOB execution (sandbox mode until set)
- `scripts/integration_test.py` — verify end-to-end before going live
- Monitor latency endpoint (`/api/latency`) target: tick→decision ~77μs

---

## G1.1-poly / G1.1-prod hardening (2026-05-17)

**Polymarket accounting fixed (was structurally broken).**

- **Audit verdict:** `emit_polymarket_bets` signal generation is honest &
  data-driven (no random/fake, unlike the old `emit_trades`). But result
  accounting was 100% broken by an `arb:orders` List-vs-Stream type collision.
- **F1 (`scripts/real_market_engine.py`):** `resolve_polymarket_bets` used
  `r.xadd("arb:orders",…)` on a Redis **List** → WRONGTYPE every resolution,
  silently killing all accounting after it. Now `publish()` (List API) wrapped
  in try/except.
- **F2 (`arb/risk/risk_runner.py`):** `_trade_monitor_loop` used
  `r.xread({"arb:orders":…})` → WRONGTYPE every poll; DrawdownBreaker never
  saw a trade. Rewired to the G1.1 List pattern (`latest()` + last-seen-ts +
  dedupe).
- **F3:** per-asset stats + daily-loss tracking moved ABOVE the bridge so
  they update even if the bridge fails.
- **Double-count fix:** `arb:polymarket:bets` is append-only; the original
  `status:"open"` entry was immortal and re-resolved every cycle. Added an
  authoritative restart-surviving resolved-id set `arb:poly:resolved`
  (7-day TTL); idempotent.
- **Baseline reset:** `arb:orders`/`arb:signals`/daily-loss cleared via
  `reset_paper_baseline.py`; additionally cleared `arb:polymarket:bets`
  (8453 stale May-15 bets), `arb:poly:stats:*`, `arb:poly:seen:*` (script
  does NOT cover these — clear manually on future resets).

**F2 deployed as RiskRunner-only service (NOT full `arb.main`)** to avoid
LiveExecutor/feeds_main conflict with the engine — full arb.main would
double-execute `arb:signals` (LiveExecutor vs `emit_trades`) and duplicate
price feeds, re-polluting the honest window. New `reyog_risk` container
(`scripts/risk_main.py`, `Dockerfile.backend`, `/health` on :8001).
`emit_trades` remains the single honest `arb:orders` writer; reyog_risk
read-only.

**Deferred to G2 (modeling — need 24h honest data first):**
- LiveExecutor latent WRONGTYPE bug at `live_executor.py:52` (not used in
  production currently — no container runs arb.main).
- F4: `_classify_market` misclassifies 5m/15m windows as "4h".
- F5: `_updown_probability` `samples_per_hour=3600` miscalibrated.
- F6: resolution uses our own price feed (simulated settlement, not true
  Polymarket settlement) — fine for paper, don't treat as real-edge proof.
- Pre-existing double-count had inflated all historical Polymarket stats.

**Prod parity note:** VPS `Dockerfile.backend` + `requirements.txt` were
still pre-G0 (no numpy; only reyog_risk was rebuilt with the G0 pinned
`requirements.txt`). engine/edges/backend still run pre-G0 images (deploys
were always `docker cp`, never rebuilt). Full G0 image rollout to those
services is still pending.

**Status:** F1–F3 + double-count + RiskRunner service deployed & verified
on VPS (paper). Awaiting approval to start the ≥24h honest data window.
