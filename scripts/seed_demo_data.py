"""
Seed Redis streams with realistic demo data so the dashboard shows real numbers
even when live feeds aren't running. Idempotent — clears and re-seeds on each run.

Usage: python scripts/seed_demo_data.py
"""
import asyncio
import random
import sys
import os
import time
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from arb.infra.redis_bus import publish, get_redis

    r = get_redis()
    now = int(time.time() * 1000)

    # Clear all arb:* streams first
    keys = await r.keys("arb:*")
    if keys:
        await r.delete(*keys)
        print(f"[seed] cleared {len(keys)} existing streams")

    # ───────────────────────────────────────────────────────
    # 1. Tick data — 4 exchanges × 3 symbols, realistic prices
    # ───────────────────────────────────────────────────────
    base_prices = {"BTC/USDT": 67_500.0, "ETH/USDT": 3_450.0, "SOL/USDT": 175.0}
    exchanges = ["BINANCE", "BYBIT"]
    TICKS_PER_STREAM = 600  # higher density — ~10/sec over last minute
    for symbol, base in base_prices.items():
        for ex in exchanges:
            spread_bps = random.uniform(1.5, 8.0)
            mid = base * (1 + random.uniform(-0.0005, 0.0005))
            half = mid * spread_bps / 20_000
            key = f"arb:ticks:{symbol}:USDT:{ex}"
            # Spread ticks over last 60 seconds (10/sec average)
            for i in range(TICKS_PER_STREAM):
                drift = random.gauss(0, 0.0002)
                m = mid * (1 + drift * i / TICKS_PER_STREAM)
                await publish(key, {
                    "symbol": symbol, "exchange": ex,
                    "bid": round(m - half, 2), "ask": round(m + half, 2),
                    "mid": round(m, 2),
                    "ts": now - (TICKS_PER_STREAM - i) * 100,  # 100ms cadence
                })
    print(f"[seed] {len(base_prices) * len(exchanges) * TICKS_PER_STREAM} ticks across 6 streams (~10/sec/stream)")

    # ───────────────────────────────────────────────────────
    # 2. Funding rates — Binance vs Bybit per perp
    # ───────────────────────────────────────────────────────
    funding_data = [
        ("BTC/USDT", "BINANCE", 0.0001),   # +0.01% / 8h
        ("BTC/USDT", "BYBIT", 0.00025),    # +0.025%
        ("ETH/USDT", "BINANCE", -0.00005),
        ("ETH/USDT", "BYBIT", 0.00015),
        ("SOL/USDT", "BINANCE", 0.0003),
        ("SOL/USDT", "BYBIT", -0.00008),
    ]
    for symbol, ex, rate in funding_data:
        await publish(f"arb:funding:{symbol}:{ex}", {
            "symbol": symbol, "exchange": ex, "rate": rate,
            "next_funding_ts": now + 4 * 3600 * 1000, "ts": now,
        })
    print(f"[seed] {len(funding_data)} funding rate snapshots")

    # ───────────────────────────────────────────────────────
    # 3. Signals — 30 recent with full ArbitrageSignal metadata
    # ───────────────────────────────────────────────────────
    strategies = ["CrossExchange", "FundingRate", "Basis", "PolymarketArb"]
    symbols = list(base_prices.keys()) + ["MATIC/USDT", "AVAX/USDT", "LINK/USDT"]
    N_SIGNALS = 150  # more signal flow
    for i in range(N_SIGNALS):
        strategy = random.choice(strategies)
        symbol = random.choice(symbols)
        prob = round(random.uniform(0.55, 0.92), 3)
        ev = round(random.uniform(0.001, 0.15), 4)
        regime = random.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
        await publish("arb:signals", {
            "strategy": strategy,
            "symbol": symbol,
            "probability_score": prob,
            "confidence_interval": [round(prob - 0.08, 3), round(prob + 0.08, 3)],
            "risk_reward_ratio": round(random.uniform(1.2, 4.5), 2),
            "expected_value": ev,
            "liquidity_score": round(random.uniform(0.35, 0.95), 3),
            "volatility_score": round(random.uniform(0.1, 0.85), 3),
            "slippage_estimate_bps": round(random.uniform(0.5, 12.0), 2),
            "correlation_impact": round(random.uniform(-0.3, 0.3), 3),
            "execution_feasibility": round(random.uniform(0.5, 0.98), 3),
            "failure_probability": round(random.uniform(0.02, 0.35), 3),
            "regime": regime,
            "tradeable": prob > 0.6 and ev > 0.005,
            "direction": random.choice(["long", "short"]),
            "ts": now - random.randint(0, 1_800_000),  # spread over last 30 min
        })
    print(f"[seed] {N_SIGNALS} signals with full metadata")

    # ───────────────────────────────────────────────────────
    # 4. Closed orders — HFT cadence: ~3000 trades / 24h
    # ───────────────────────────────────────────────────────
    n_trades = 3000
    equity = 10_000.0
    window_ms = 24 * 3600 * 1000  # spread trades over last 24h
    # Pre-generate ascending timestamps so equity curve flows chronologically
    timestamps = sorted([now - random.randint(0, window_ms) for _ in range(n_trades)])
    for i, ts in enumerate(timestamps):
        strategy = random.choice(strategies)
        symbol = random.choice(list(base_prices.keys()))
        is_win = random.random() < 0.605  # 60.5% win rate
        size_usd = random.uniform(40, 180)  # smaller per-trade for HFT
        if is_win:
            pnl = size_usd * random.uniform(0.002, 0.012)
        else:
            pnl = -size_usd * random.uniform(0.0015, 0.008)
        equity += pnl

        # OPEN event
        await publish("arb:orders", {
            "event": "OPEN", "strategy": strategy, "symbol": symbol,
            "exchange": random.choice(exchanges),
            "direction": random.choice(["long", "short"]),
            "size_usd": round(size_usd, 2),
            "price": base_prices[symbol] * (1 + random.uniform(-0.002, 0.002)),
            "ts": ts,
        })
        # CLOSE event
        await publish("arb:orders", {
            "event": "CLOSE", "strategy": strategy, "symbol": symbol,
            "exchange": random.choice(exchanges),
            "direction": random.choice(["long", "short"]),
            "size_usd": round(size_usd, 2),
            "exit_price": base_prices[symbol] * (1 + random.uniform(-0.002, 0.002)),
            "pnl": round(pnl, 4),
            "ts": ts + random.randint(5_000, 60_000),
        })
    print(f"[seed] {n_trades} closed orders ({n_trades/24:.0f}/hr cadence), final equity = ${equity:.2f}")

    # ───────────────────────────────────────────────────────
    # 5. Open positions — 3 active
    # ───────────────────────────────────────────────────────
    open_positions = [
        {"symbol": "BTC/USDT", "strategy": "CrossExchange", "exchange": "BINANCE",
         "direction": "long", "qty": 0.0015, "entry_price": 67_420.0,
         "mark_price": 67_580.0, "size_usd": 101.13, "ts": now - 300_000},
        {"symbol": "ETH/USDT", "strategy": "FundingRate", "exchange": "BYBIT",
         "direction": "short", "qty": 0.045, "entry_price": 3_465.0,
         "mark_price": 3_452.5, "size_usd": 155.93, "ts": now - 1_800_000},
        {"symbol": "SOL/USDT", "strategy": "Basis", "exchange": "BINANCE",
         "direction": "long", "qty": 0.62, "entry_price": 174.2,
         "mark_price": 175.85, "size_usd": 108.0, "ts": now - 600_000},
    ]
    for p in open_positions:
        await publish("arb:positions:open", p)
    print(f"[seed] {len(open_positions)} open positions")

    # ───────────────────────────────────────────────────────
    # 6. ML model state — HMM regime, Kalman, cointegration
    # ───────────────────────────────────────────────────────
    await publish("arb:models:regime", {
        "regime": 1, "confidence": 0.78,
        "transition_matrix": [[0.85, 0.12, 0.03], [0.10, 0.78, 0.12], [0.05, 0.15, 0.80]],
        "ts": now,
    })
    for symbol, base in base_prices.items():
        await publish("arb:models:kalman", {
            "symbol": symbol, "state": base * (1 + random.uniform(-0.001, 0.001)),
            "covariance": round(random.uniform(0.0001, 0.005), 6),
            "ts": now,
        })
    cointeg_pairs = [
        ("BTC/USDT-ETH/USDT", 18.45, 1.23, 0.008, "long"),
        ("ETH/USDT-SOL/USDT", 22.18, -2.45, 0.003, "short"),
        ("BTC/USDT-SOL/USDT", 385.7, 0.12, 0.142, "neutral"),
    ]
    for pair, hedge, zscore, pval, sig in cointeg_pairs:
        await publish("arb:models:cointegration", {
            "pair": pair, "hedge_ratio": hedge, "zscore": zscore,
            "pvalue": pval, "signal": sig, "ts": now,
        })
    for strategy in strategies:
        await publish("arb:models:bayesian", {
            "strategy": strategy,
            "alpha": random.uniform(15, 50), "beta": random.uniform(10, 35),
            "win_prob": round(random.uniform(0.5, 0.72), 3),
            "ts": now,
        })
    print("[seed] HMM regime, 3 Kalman states, 3 cointegration pairs, 4 Bayesian estimates")

    # ───────────────────────────────────────────────────────
    # 7. Risk breaker state
    # ───────────────────────────────────────────────────────
    await publish("arb:risk:breakers", {
        "daily_pnl_pct": round((equity - 10_000.0) / 10_000.0 * 100, 3),
        "max_drawdown_pct": 1.42,
        "vol_multiplier": 1.85,
        "ts": now,
    })
    # 2 historical alerts (not currently halted)
    await publish("arb:risk:alerts", {
        "event": "VOL_SPIKE", "reason": "ETH/USDT vol 2.4x baseline",
        "halted": False, "ts": now - 7_200_000,
    })
    await publish("arb:risk:alerts", {
        "event": "DRAWDOWN_WARNING", "reason": "Daily PnL -1.5% (threshold -2%)",
        "halted": False, "ts": now - 3_600_000,
    })
    print("[seed] risk breaker state + 2 historical alerts")

    print()
    print("=" * 50)
    print("  Demo data seeded. Refresh dashboard to see it.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
