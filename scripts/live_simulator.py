"""
Continuous HFT simulator — keeps generating fresh ticks, signals, and trades
so the dashboard shows ~20-50 ops/sec live activity even when no real feeds are connected.

Run as: python scripts/live_simulator.py (in a separate terminal)
Stop with Ctrl+C.

This is FOR DEMO / DEVELOPMENT. Once real Binance/Bybit feeds are connected
(via `python -m arb.main`), stop this simulator.
"""
import asyncio
import random
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from arb.infra.redis_bus import publish

    print("[sim] starting HFT simulator — ~50 ops/sec target")
    print("[sim] Ctrl+C to stop")

    base_prices = {"BTC/USDT": 67_500.0, "ETH/USDT": 3_450.0, "SOL/USDT": 175.0}
    exchanges = ["BINANCE", "BYBIT"]
    strategies = ["CrossExchange", "FundingRate", "Basis", "PolymarketArb"]
    current_prices = dict(base_prices)

    tick_count = 0
    sig_count = 0
    trade_count = 0
    equity = 10_000.0
    last_status = time.time()

    async def emit_ticks():
        nonlocal tick_count
        while True:
            await asyncio.sleep(0.1)  # 10 Hz × 6 streams = 60 ticks/sec
            now = int(time.time() * 1000)
            for symbol, base in base_prices.items():
                # Random-walk price (small)
                drift = random.gauss(0, 0.0001)
                current_prices[symbol] = current_prices[symbol] * (1 + drift)
                for ex in exchanges:
                    spread_bps = random.uniform(1.0, 6.0)
                    mid = current_prices[symbol] * (1 + random.uniform(-0.0003, 0.0003))
                    half = mid * spread_bps / 20_000
                    await publish(f"arb:ticks:{symbol}:USDT:{ex}", {
                        "symbol": symbol, "exchange": ex,
                        "bid": round(mid - half, 2), "ask": round(mid + half, 2),
                        "mid": round(mid, 2), "ts": now,
                    })
                    tick_count += 1

    async def emit_signals():
        nonlocal sig_count
        while True:
            await asyncio.sleep(random.uniform(0.5, 2.0))  # ~1 signal/sec
            strategy = random.choice(strategies)
            symbol = random.choice(list(base_prices.keys()))
            prob = round(random.uniform(0.55, 0.92), 3)
            ev = round(random.uniform(0.001, 0.15), 4)
            regime = random.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
            await publish("arb:signals", {
                "strategy": strategy, "symbol": symbol,
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
                "ts": int(time.time() * 1000),
            })
            sig_count += 1

    async def emit_trades():
        nonlocal trade_count, equity
        while True:
            # Aim for ~125 trades/hour = 1 trade every ~28s on average
            await asyncio.sleep(random.uniform(15, 45))
            strategy = random.choice(strategies)
            symbol = random.choice(list(base_prices.keys()))
            is_win = random.random() < 0.605
            size_usd = random.uniform(40, 180)
            pnl = size_usd * random.uniform(0.002, 0.012) if is_win else \
                  -size_usd * random.uniform(0.0015, 0.008)
            equity += pnl
            ts = int(time.time() * 1000)

            await publish("arb:orders", {
                "event": "OPEN", "strategy": strategy, "symbol": symbol,
                "exchange": random.choice(exchanges),
                "direction": random.choice(["long", "short"]),
                "size_usd": round(size_usd, 2),
                "price": current_prices[symbol] * (1 + random.uniform(-0.001, 0.001)),
                "ts": ts,
            })
            await asyncio.sleep(random.uniform(0.5, 3.0))
            await publish("arb:orders", {
                "event": "CLOSE", "strategy": strategy, "symbol": symbol,
                "exchange": random.choice(exchanges),
                "direction": random.choice(["long", "short"]),
                "size_usd": round(size_usd, 2),
                "exit_price": current_prices[symbol] * (1 + random.uniform(-0.001, 0.001)),
                "pnl": round(pnl, 4),
                "ts": ts + 1500,
            })
            trade_count += 1

    async def status():
        nonlocal last_status
        while True:
            await asyncio.sleep(5)
            now = time.time()
            dt = now - last_status
            print(f"[sim] +{dt:.1f}s: ticks={tick_count}, signals={sig_count}, trades={trade_count}, equity=${equity:.2f}")
            last_status = now

    await asyncio.gather(emit_ticks(), emit_signals(), emit_trades(), status())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[sim] stopped")
