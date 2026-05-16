"""
Live position and exposure tracker.
Enforces max concurrent positions and monitors per-exchange exposure.
"""
import asyncio
import time
from dataclasses import dataclass, field
from arb.infra.redis_bus import publish
from arb.config import settings


@dataclass
class Position:
    symbol: str
    exchange: str
    strategy: str
    direction: str
    size_usd: float
    entry_price: float
    open_at: float = field(default_factory=time.time)
    unrealized_pnl: float = 0.0


class PortfolioRiskManager:
    def __init__(self, max_positions: int | None = None) -> None:
        self._max_positions = max_positions or settings.max_concurrent_positions
        self._positions: dict[str, Position] = {}
        self._total_exposure: float = 0.0

    def can_open(self, symbol: str, exchange: str) -> tuple[bool, str]:
        if len(self._positions) >= self._max_positions:
            return False, f"max positions ({self._max_positions}) reached"
        key = f"{symbol}:{exchange}"
        if key in self._positions:
            return False, f"position already open for {key}"
        return True, "ok"

    async def open_position(
        self, symbol: str, exchange: str, strategy: str,
        direction: str, size_usd: float, entry_price: float,
    ) -> bool:
        ok, reason = self.can_open(symbol, exchange)
        if not ok:
            print(f"[position_manager] Cannot open {symbol}: {reason}")
            return False

        key = f"{symbol}:{exchange}"
        self._positions[key] = Position(
            symbol=symbol, exchange=exchange, strategy=strategy,
            direction=direction, size_usd=size_usd, entry_price=entry_price,
        )
        self._total_exposure += size_usd
        await publish("arb:orders", {
            "ts": int(time.time() * 1000),
            "event": "OPEN",
            "symbol": symbol,
            "exchange": exchange,
            "strategy": strategy,
            "direction": direction,
            "size_usd": size_usd,
            "entry_price": entry_price,
        })
        print(f"[position_manager] Opened {direction} {symbol} @ {entry_price} size=${size_usd:.2f}")
        return True

    async def close_position(self, symbol: str, exchange: str, exit_price: float) -> float:
        key = f"{symbol}:{exchange}"
        pos = self._positions.pop(key, None)
        if not pos:
            return 0.0

        if pos.direction.startswith("LONG"):
            pnl = (exit_price - pos.entry_price) / pos.entry_price * pos.size_usd
        else:
            pnl = (pos.entry_price - exit_price) / pos.entry_price * pos.size_usd

        self._total_exposure -= pos.size_usd
        await publish("arb:orders", {
            "ts": int(time.time() * 1000),
            "event": "CLOSE",
            "symbol": symbol,
            "exchange": exchange,
            "strategy": pos.strategy,
            "pnl": pnl,
            "exit_price": exit_price,
        })
        print(f"[position_manager] Closed {symbol} PnL=${pnl:+.2f}")
        return pnl

    def get_snapshot(self) -> dict:
        return {
            "open_positions": len(self._positions),
            "max_positions": self._max_positions,
            "total_exposure_usd": round(self._total_exposure, 2),
            "positions": [
                {
                    "symbol": p.symbol,
                    "exchange": p.exchange,
                    "strategy": p.strategy,
                    "direction": p.direction,
                    "size_usd": p.size_usd,
                    "entry_price": p.entry_price,
                    "age_s": round(time.time() - p.open_at, 1),
                }
                for p in self._positions.values()
            ],
        }
