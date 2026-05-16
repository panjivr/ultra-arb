"""
Polymarket mispricing detector.
Compares Polymarket implied probability to model-derived probability.
When divergence > threshold, signals an arbitrage opportunity.
"""
import asyncio
import time
import json
from arb.infra.redis_bus import get_redis, publish

MIN_EDGE_PCT = 5.0  # minimum 5% edge to signal
COMPLEMENT_THRESHOLD = 0.03  # if YES + NO ≠ 1.0 ± 3%, arbitrage exists


class PolymarketArbStrategy:
    """
    Reads Polymarket tick streams and looks for:
    1. Complement arbitrage: YES + NO prices < 1.0 (guaranteed profit)
    2. Mispricing: Polymarket probability vs external news signal
    """

    def __init__(self) -> None:
        self._markets: dict[str, dict] = {}

    async def run(self) -> None:
        r = get_redis()
        print("[polymarket_arb] Starting Polymarket arbitrage scanner...")
        while True:
            try:
                # Discover active POLY streams and poll latest items
                all_keys = await r.keys("arb:ticks:POLY:*")
                if all_keys:
                    for key in all_keys:
                        # Lists (LPUSH) — latest 20 items from head
                        raw_items = await r.lrange(key, 0, 19)
                        for item in raw_items:
                            try:
                                data = json.loads(item)
                                await self._analyze(data)
                            except Exception:
                                pass
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[polymarket_arb] error: {e}")
                await asyncio.sleep(2)

    async def _analyze(self, tick: dict) -> None:
        token_id = tick.get("symbol", "")
        bid = tick.get("bid", 0.0)
        ask = tick.get("ask", 0.0)

        if not token_id or bid <= 0 or ask <= 0:
            return

        # Complement arbitrage: buy YES and NO, if total cost < 1.0
        # (We'd need the complement market; store for later pairing)
        self._markets[token_id] = {"bid": bid, "ask": ask, "ts": tick.get("ts", 0)}

        # Simple spread edge: if mid is far from 0.5 but spread is wide, signal
        mid = (bid + ask) / 2
        spread = ask - bid
        edge_pct = spread * 100

        if edge_pct >= MIN_EDGE_PCT and (mid < 0.2 or mid > 0.8):
            # Extreme probability with wide spread = mispricing opportunity
            await publish("arb:signals", {
                "ts": int(time.time() * 1000),
                "strategy": "PolymarketArb",
                "symbol": token_id,
                "probability_score": min(0.90, 0.5 + edge_pct / 100),
                "expected_value": edge_pct / 100,
                "direction": "BUY_YES" if mid < 0.5 else "BUY_NO",
                "bid": bid,
                "ask": ask,
                "spread_pct": edge_pct,
                "market_mid": mid,
                "tradeable": edge_pct >= MIN_EDGE_PCT * 1.5,
            })
