"""
Risk circuit breakers.
DrawdownBreaker: halts trading if daily PnL < -max_drawdown_pct%.
VolatilityBreaker: halts if 5-min realized vol > vol_multiplier * 30d avg.
"""
import asyncio
import time
import statistics
from collections import deque
from arb.infra.redis_bus import publish
from arb.config import settings

HALTED_KEY = "arb:risk:halted"


class DrawdownBreaker:
    def __init__(self, max_drawdown_pct: float | None = None) -> None:
        self._threshold = -(max_drawdown_pct or settings.max_drawdown_pct) / 100
        self._daily_pnl: float = 0.0
        self._halted: bool = False
        self._halt_until: float = 0.0

    def record_trade(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0

    async def check(self) -> bool:
        """Returns True if breaker just triggered. Check externally.

        daily_pnl is in fraction-of-account units (negative = loss).
        threshold is e.g. -0.02 for 2% max drawdown.
        """
        if self._halted and time.time() < self._halt_until:
            return False  # already halted, not new trigger
        if self._daily_pnl < self._threshold:
            await self._halt("drawdown", self._daily_pnl)
            return True
        return False

    async def check_pct(self, daily_pnl_pct: float) -> bool:
        """Check using percentage of account (negative = loss)."""
        if daily_pnl_pct <= self._threshold:
            await self._halt("drawdown", daily_pnl_pct)
            return True
        return False

    async def _halt(self, reason: str, value: float) -> None:
        self._halted = True
        self._halt_until = time.time() + 3600  # halt for 1 hour
        alert = {
            "ts": int(time.time() * 1000),
            "event": "CIRCUIT_BREAKER_HALT",
            "reason": reason,
            "value": value,
            "threshold": self._threshold,
            "halt_until": self._halt_until,
        }
        try:
            await publish("arb:risk:alerts", alert)
        except Exception:
            pass  # Redis may not be available during tests or startup
        print(f"[circuit_breaker] HALTED: {reason}={value:.4%} threshold={self._threshold:.4%}")

    @property
    def is_halted(self) -> bool:
        if self._halted and time.time() > self._halt_until:
            self._halted = False
        return self._halted


class VolatilityBreaker:
    def __init__(
        self,
        short_window: int = 30,          # 30 ticks ≈ 5 min at 10s intervals
        long_window: int = 1296,         # 30d at 10s intervals (30*24*60*6)
        multiplier: float | None = None,
    ) -> None:
        self._mult = multiplier or settings.vol_breaker_multiplier
        self._short: deque[float] = deque(maxlen=short_window)
        self._long: deque[float] = deque(maxlen=long_window)
        self._halted: bool = False

    def add_return(self, ret: float) -> None:
        self._short.append(ret)
        self._long.append(ret)

    async def check(self) -> bool:
        if len(self._short) < 10 or len(self._long) < 30:
            return False
        # Sample standard deviation (ddof=1) — pure-Python so the risk service
        # carries NO numpy dependency. numpy 2.4.x wheels are built for the
        # x86-64-v2 baseline and crash `import numpy` on older CPUs (the VPS
        # host), which is exactly what killed the reyog_risk container. The
        # guards above guarantee >= 2 samples, so stdev() never raises.
        short_vol = statistics.stdev(self._short)
        long_vol = statistics.stdev(self._long) or 1e-9

        if short_vol > self._mult * long_vol:
            await self._halt(short_vol, long_vol)
            return True
        elif self._halted:
            self._halted = False
        return False

    async def _halt(self, short_vol: float, long_vol: float) -> None:
        if self._halted:
            return
        self._halted = True
        alert = {
            "ts": int(time.time() * 1000),
            "event": "CIRCUIT_BREAKER_HALT",
            "reason": "volatility",
            "short_vol": short_vol,
            "long_vol": long_vol,
            "multiplier": self._mult,
        }
        try:
            await publish("arb:risk:alerts", alert)
        except Exception:
            pass  # Redis may not be available during tests or startup
        print(
            f"[circuit_breaker] VOL HALT: short={short_vol:.6f} "
            f"long={long_vol:.6f} ratio={short_vol/long_vol:.1f}x"
        )

    @property
    def is_halted(self) -> bool:
        return self._halted
