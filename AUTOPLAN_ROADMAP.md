# Ultra-Arb v2.0 — Profitable Live Trading Upgrade Plan
> Plan file for /autoplan review | Created: 2026-05-16 | Branch: main

<!-- /autoplan restore point: ~/.gstack/projects/ultra-arb/main-autoplan-restore-20260516.md -->

## Problem Statement

Reyog Capital has a working paper-trading arbitrage system (ultra-arb) deployed to a VPS running 24/7. Real prices flow from Gate.io/HTX, 6 edge detectors scan Polymarket, risk controls are active. The system has NOT yet produced real profit because:

1. Still in paper mode — no capital deployed
2. Strategy edge not validated with real backtests
3. Polymarket execution blocked (sandbox mode, no live private key)
4. Cross-exchange arb (Binance/Bybit) relies on stale logic without proper backtest validation
5. No mechanism to prove which strategies have positive expectancy BEFORE going live
6. The "AI ensemble" for Polymarket bets fires on insufficient signal agreement
7. No Monte Carlo simulation to stress-test under adverse conditions
8. Up/Down betting without ensemble currently ~50/50 — not profitable

## Current System State (2026-05-16)

| Component | Status | Gap |
|-----------|--------|-----|
| Market data feeds | LIVE (Gate.io/HTX REST, Binance/Bybit WS) | None |
| 6 edge detectors | RUNNING (Polymarket 24/7) | Need ensemble gating |
| Risk engine | ACTIVE (Kelly, DrawdownBreaker, VolBreaker) | Daily loss circuit breaker missing |
| Dashboard | 28 components, 100Hz WebSocket | None major |
| Rust hot-paths | PYTHON FALLBACK (not compiled) | Need `maturin develop` |
| Polymarket execution | SANDBOX only | Need live CLOB private key |
| Backtesting | NONE (paper_trader is NautilusTrader wrapper) | Critical gap |
| Strategy validation | NONE (no historical edge proof) | Critical gap |
| Integration tests | NOT VERIFIED end-to-end | Need to run |

## Core Premise

The system architecture is sound. The gap is between "running in paper mode" and "profitable in live mode." The path is: **validate edge historically → prove with forward paper testing → flip live with confirmed strategies only**.

Trying to go live without historical edge validation is gambling, not trading.

## Proposed Upgrade Phases

### Phase A: Edge Validation Engine (CRITICAL, do this first)
Build a proper backtesting engine using historical OHLCV + orderbook data to measure:
- Strategy expectancy (expected profit per trade after fees/slippage)
- Sharpe ratio per strategy
- Max drawdown per strategy
- Win rate and profit factor

**What to build:**
- `arb/backtest/engine.py` — vectorized event-driven backtester
- `arb/backtest/data_loader.py` — fetch historical OHLCV from Binance API (free)
- `arb/backtest/metrics.py` — Sharpe, Sortino, Calmar, expectancy, profit factor
- `arb/backtest/monte_carlo.py` — 1000-run Monte Carlo to find drawdown distribution

**Gate to live:** Strategy must show positive expectancy AND Sharpe > 0.5 AND max drawdown < 15% across 6 months of historical data BEFORE any capital is deployed.

### Phase B: Polymarket AI Ensemble (HIGH VALUE, fast to implement)
Current `emit_polymarket_bets()` fires on weak signals. Need 3+ independent signals agreeing before a bet.

**What to build:**
- `arb/edges/ensemble.py` — signal aggregator: GBM/momentum + smart_money + news_sentiment + funding direction
- Per-asset hit-rate tracker in Redis (track WIN/LOSS per market type)
- `POLYMARKET_ONLY=true` env mode in `real_market_engine.py` (suppress noisy spot/perp signals)
- Daily loss circuit breaker for Polymarket: stop if daily Polymarket loss > 3%

**Gate to live Polymarket:** Hit rate > 55% on last 100 paper trades per market type.

### Phase C: Statistical Arbitrage Upgrades (MEDIUM)
Improve signal quality for crypto arb:
- `arb/strategies/liquidity_sweep.py` — detect large-order sweeps that predict direction
- `arb/strategies/momentum_reversion.py` — momentum entry + mean-reversion exit hybrid
- `arb/models/cointegration.py` — add Engle-Granger test as fallback to Johansen
- Improve `cross_exchange.py` — add orderbook depth weighting, not just best bid/ask

### Phase D: Rust Hot-Paths Compilation (QUICK WIN)
- `maturin develop` in `rust/hot_paths/` to compile PyO3 module
- Benchmark Python vs Rust Kelly calculation (expect ~50x speedup)
- Add `spread_calc_batch()` function for vectorized spread history processing

### Phase E: Self-Improving Mechanism (ADVANCED)
- `arb/optimization/bayesian_optimizer.py` — Bayesian hyperparameter search using Optuna
- Auto-retune strategy parameters weekly based on rolling 30-day performance
- Per-strategy parameter versioning with rollback if performance degrades
- Reinforcement learning signal weighting (multi-armed bandit for strategy selection)

### Phase F: Onchain Analytics (OPTIONAL, add-on)
- `arb/feeds/onchain_feed.py` — Glassnode free tier for BTC/ETH on-chain metrics
- Whale wallet tracking via Etherscan/BSCScan public APIs
- Integrate into ensemble (on-chain accumulation = bullish signal bias)

## Architecture Additions

```
arb/
├── backtest/
│   ├── engine.py          # vectorized backtester
│   ├── data_loader.py     # historical OHLCV via Binance API (free)
│   ├── metrics.py         # Sharpe, Sortino, Calmar, expectancy
│   └── monte_carlo.py     # 1000-run MC stress test
├── edges/
│   └── ensemble.py        # multi-signal aggregator (3+ agree → bet)
├── optimization/
│   └── bayesian_optimizer.py  # Optuna-based hyperparameter tuning
└── strategies/
    ├── liquidity_sweep.py     # large-order detection
    └── momentum_reversion.py  # hybrid momentum + mean-reversion
```

## Risk Gates (non-negotiable)

1. **Never deploy live without** ≥6 months backtest with Sharpe > 0.5
2. **Never bet on Polymarket without** ≥3 independent signals agreeing
3. **Daily loss circuit breaker** on ALL strategies (not just crypto)
4. **Paper mode minimum 30 days** before live capital
5. **Position sizing**: half-Kelly, max 2.5% per trade, max 5 concurrent
6. **Emergency kill switch**: single env var `TRADING_ENABLED=false` halts everything

## Success Metrics

| Metric | Paper Target | Live Gate |
|--------|-------------|-----------|
| Sharpe ratio (annualized) | > 1.0 | > 0.8 |
| Max drawdown | < 10% | Halt at -2% daily |
| Win rate | > 55% | > 52% |
| Expectancy per trade | > 0.1% | > 0.05% |
| Profit factor | > 1.5 | > 1.2 |
| Monthly return | > 3% | > 1% |

## What NOT to Build

- Leveraged futures without significant paper-trade validation (high liquidation risk)
- High-frequency market making (requires co-location, >$100k inventory)
- Cross-chain DeFi arb (gas fees eat most margins, complex execution)
- Predictive price models (not arbitrage, requires forecast accuracy >55% sustained)

## Implementation Priority

1. Phase A (backtesting) — MUST HAVE before any live capital
2. Phase B (Polymarket ensemble) — can go live on Polymarket first (lower capital at risk)
3. Phase D (Rust compilation) — quick win, 30 min effort
4. Phase C (stat arb upgrades) — improves crypto edge quality
5. Phase E (self-improving) — nice to have, do after validating baseline
6. Phase F (onchain) — optional, add if crypto edge needs boost

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|---------|
| 1 | CEO | Resequence: Phase B first, Phase A only if needed | USER CHALLENGE (accepted) | P6 + real data > simulation | Backtesting OHLCV is useless for real-time pure arb; Polymarket ensemble validates in 2 weeks | Phase A first |
| 2 | CEO | Reduce success targets: Sharpe 0.5, win 52%, 1.5% monthly | Mechanical | P3 (pragmatic) | No live data to anchor higher targets; recalibrate when validated | 3%/month, Sharpe 1.0 |
| 3 | CEO | Defer RL/self-improving until positive expectancy proven | Mechanical | P2 + P4 | Building RL before edge is validated = premature optimization | Phase E now |
| 4 | CEO | Funding rate arb as safe crypto baseline (1.5-2%/month) | Mechanical | P1 (capital preservation) | Known positive expectancy, no execution speed requirement | Cross-exchange arb first |
| 5 | Eng | Use SignalVote unified interface for ensemble (XADD/XREAD) | Mechanical | P5 (explicit) | 6 detectors have different schemas; Redis Streams guarantee delivery vs pub/sub | Redis pub/sub |
| 6 | Eng | All 7 critical tests required before live | Mechanical | P1 + completeness | 3 critical bugs found; tests are the gate to live capital | Defer tests |
| 7 | Eng | Wire Polymarket PnL to arb:orders before ensemble | Mechanical | P1 (capital preservation) | DrawdownBreaker is blind to Polymarket losses; CRITICAL safety gap | Skip, add later |
| 8 | Eng | Use KellyPositionSizer everywhere, remove inline Kelly | Mechanical | P4 (DRY) | Two Kelly implementations, inline one lacks caps | Keep inline |
| 9 | Eng | Persist seen_conditions to Redis TTL key | Mechanical | P1 | In-memory set lost on restart = double bets | In-memory OK |
| 10 | Eng | CLOB private key in Docker secrets, not .env | Mechanical | P1 | Full account drain if .env exposed | .env is fine |
