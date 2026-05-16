"""
Funding rate carry arbitrage.
When Binance and Bybit funding rates diverge significantly,
open delta-neutral positions to capture the rate differential.
"""
import asyncio
import time
import json
from arb.infra.redis_bus import get_redis
from arb.infra.redis_bus import publish
from arb.config import settings

MIN_RATE_DIFF = 0.0005  # 0.05% per 8h — minimum exploitable difference
POSITION_SIZE_FRACTION = 0.02  # 2% of capital per trade


class FundingRateStrategy:
    """
    Standalone async strategy (not NautilusTrader-based) since it operates on 8h schedules.
    Monitors funding rate streams and emits signals to arb:signals.
    """

    def __init__(self) -> None:
        self._rates: dict[str, dict] = {}

    async def run(self) -> None:
        r = get_redis()
        print("[funding_rate] Starting funding rate monitor...")
        while True:
            try:
                await self._check_rates()
                await asyncio.sleep(60)  # check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[funding_rate] error: {e}")
                await asyncio.sleep(10)

    async def _check_rates(self) -> None:
        r = get_redis()
        for symbol in ["BTC/USDT:USDT", "ETH/USDT:USDT"]:
            for exchange in ["BINANCE", "BYBIT"]:
                stream = f"arb:funding:{symbol}:{exchange}"
                # Lists (LPUSH) — latest item at index 0
                raw = await r.lrange(stream, 0, 0)
                if raw:
                    data = json.loads(raw[0])
                    self._rates[f"{symbol}:{exchange}"] = data

        for symbol in ["BTC/USDT:USDT", "ETH/USDT:USDT"]:
            k_bin = f"{symbol}:BINANCE"
            k_byt = f"{symbol}:BYBIT"
            if k_bin in self._rates and k_byt in self._rates:
                r_bin = self._rates[k_bin].get("rate", 0.0)
                r_byt = self._rates[k_byt].get("rate", 0.0)
                diff = abs(r_bin - r_byt)
                if diff >= MIN_RATE_DIFF:
                    long_ex = "BINANCE" if r_bin < r_byt else "BYBIT"
                    short_ex = "BYBIT" if long_ex == "BINANCE" else "BINANCE"
                    ev = diff * 3 * 365  # annualized (3 funding periods/day)
                    signal = {
                        "ts": int(time.time() * 1000),
                        "strategy": "FundingRate",
                        "symbol": symbol,
                        "probability_score": min(0.92, 0.7 + diff * 100),
                        "expected_value": ev,
                        "risk_reward": ev / 0.001,
                        "direction": f"LONG_{long_ex}_SHORT_{short_ex}",
                        "funding_diff": diff,
                        "annualized_yield": ev,
                        "tradeable": diff > MIN_RATE_DIFF * 2,
                    }
                    await publish("arb:signals", signal)
                    print(
                        f"[funding_rate] {symbol} diff={diff:.4%} "
                        f"→ LONG {long_ex} SHORT {short_ex} annualized={ev:.1%}"
                    )
