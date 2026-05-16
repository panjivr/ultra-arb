"""
Risk engine runner — checks circuit breakers every 10 seconds.
"""
import asyncio
import time
from arb.risk.circuit_breakers import DrawdownBreaker, VolatilityBreaker
from arb.risk.position_manager import PortfolioRiskManager
from arb.infra.redis_bus import get_redis, publish
import json

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
        """Consume arb:orders stream to update balance and vol breaker."""
        r = get_redis()
        last_id = "$"
        while True:
            try:
                results = await r.xread({"arb:orders": last_id}, count=20, block=200)
                if results:
                    for _, messages in results:
                        for msg_id, fields in messages:
                            last_id = msg_id
                            data = json.loads(fields["data"])
                            if data.get("event") == "CLOSE" and "pnl" in data:
                                pnl = float(data["pnl"])
                                self._current_balance += pnl
                                self.drawdown_breaker.record_trade(pnl)
                                ret = pnl / self._daily_start_balance
                                self.vol_breaker.add_return(ret)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[risk_runner] trade monitor error: {e}")
                await asyncio.sleep(1)
