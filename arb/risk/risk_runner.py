"""
Risk engine runner — checks circuit breakers every 10 seconds.
"""
import asyncio
import time
from arb.risk.circuit_breakers import DrawdownBreaker, VolatilityBreaker
from arb.risk.position_manager import PortfolioRiskManager
from arb.infra.redis_bus import get_redis, publish, latest
from collections import deque

CHECK_INTERVAL = 10


class RiskRunner:
    def __init__(self) -> None:
        self.drawdown_breaker = DrawdownBreaker()
        self.vol_breaker = VolatilityBreaker()
        self.position_manager = PortfolioRiskManager()
        self._daily_start_balance: float = 10_000.0
        self._current_balance: float = 10_000.0

    def update_balance(self, balance: float) -> None:
        self._current_balance = balance

    @property
    def is_halted(self) -> bool:
        return self.drawdown_breaker.is_halted or self.vol_breaker.is_halted

    async def start(self) -> None:
        print("[risk_runner] Risk engine started.")
        await asyncio.gather(
            self._check_loop(),
            self._trade_monitor_loop(),
        )

    async def _check_loop(self) -> None:
        r = get_redis()
        while True:
            try:
                daily_pnl_pct = (
                    (self._current_balance - self._daily_start_balance)
                    / self._daily_start_balance
                )
                await self.drawdown_breaker.check_pct(daily_pnl_pct)
                await self.vol_breaker.check()

                # Propagate halt state to Redis so other processes (real_market_engine)
                # can check arb:risk:halted without importing this module
                if self.is_halted:
                    await r.set("arb:risk:halted", "1", ex=3600)
                else:
                    await r.delete("arb:risk:halted")

                # Publish risk snapshot every 30s
                if int(time.time()) % 30 == 0:
                    snapshot = self.position_manager.get_snapshot()
                    snapshot.update({
                        "ts": int(time.time() * 1000),
                        "halted": self.is_halted,
                        "daily_pnl_pct": round(daily_pnl_pct, 4),
                        "balance": self._current_balance,
                    })
                    await publish("arb:risk:alerts", snapshot)

            except Exception as e:
                print(f"[risk_runner] check error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

    async def _trade_monitor_loop(self) -> None:
        """Consume arb:orders to update balance and vol breaker.

        F2 (same fix as G1.1): arb:orders is a Redis LIST (redis_bus.publish
        → lpush), not a Stream. The old r.xread() raised WRONGTYPE on every
        poll, so the DrawdownBreaker never saw a single trade. Mirror the
        emit_trades() pattern: non-destructive latest() read, track newest
        processed ts, dedupe. Ignore the backlog on startup.
        """
        last_seen_ts = int(time.time() * 1000)  # ignore backlog; only new closes
        seen: deque = deque(maxlen=1000)         # dedupe processed CLOSE events
        while True:
            try:
                orders = await latest("arb:orders", 100)
                # latest() is newest-first → process oldest-first
                for o in reversed(orders):
                    if o.get("event") != "CLOSE" or "pnl" not in o:
                        continue
                    o_ts = int(o.get("ts") or 0)
                    if o_ts <= last_seen_ts:
                        continue
                    dedupe_key = (o_ts, o.get("symbol"), o.get("pnl"),
                                  o.get("source"))
                    if dedupe_key in seen:
                        continue
                    seen.append(dedupe_key)
                    last_seen_ts = max(last_seen_ts, o_ts)

                    pnl = float(o["pnl"])
                    self._current_balance += pnl
                    self.drawdown_breaker.record_trade(pnl)
                    ret = pnl / self._daily_start_balance
                    self.vol_breaker.add_return(ret)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[risk_runner] trade monitor error: {e}")
            await asyncio.sleep(0.5)
