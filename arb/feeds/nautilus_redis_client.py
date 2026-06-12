"""
Bridge between Redis tick streams and NautilusTrader's data engine.
Reads arb:ticks:* streams and emits QuoteTick objects into NautilusTrader.
"""
import asyncio
import json
from decimal import Decimal
import redis.asyncio as aioredis
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.common.component import LiveClock
from arb.config import settings

# Map stream prefixes to NautilusTrader venue names
STREAM_VENUE_MAP = {
    "BINANCE": "BINANCE",
    "BYBIT": "BYBIT",
    "POLYMARKET": "POLYMARKET",
}


class RedisTickBridge:
    """
    Subscribes to Redis tick streams and converts payloads to NautilusTrader QuoteTick objects.
    Inject the data handler from the NautilusTrader engine or strategy.
    """

    def __init__(self, handler, streams: list[str] | None = None) -> None:
        self._handler = handler
        self._streams = streams or [
            "arb:ticks:BTC/USDT:USDT:BINANCE",
            "arb:ticks:BTC/USDT:USDT:BYBIT",
        ]
        self._redis: aioredis.Redis | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._redis:
            await self._redis.aclose()

    async def _run(self) -> None:
        # arb:ticks:* are Redis LISTs (redis_bus.publish → LPUSH), NOT Streams.
        # The old r.xread() raised WRONGTYPE on every poll. Poll the lists with a
        # per-stream timestamp cursor: an O(1) head peek (lindex 0) skips the
        # lrange when nothing is new, and `ts` survives the 50k list cap.
        last_ts = {s: 0 for s in self._streams}
        while True:
            try:
                for stream in self._streams:
                    head = await self._redis.lindex(stream, 0)
                    if head is None:
                        continue
                    try:
                        head_ts = int(json.loads(head).get("ts", 0) or 0)
                    except Exception:
                        head_ts = 0
                    if head_ts <= last_ts[stream]:
                        continue
                    raw_items = await self._redis.lrange(stream, 0, 49)  # newest-first
                    # Emit oldest-first so the data engine sees ticks in order.
                    for raw in reversed(raw_items):
                        try:
                            data = json.loads(raw)
                        except Exception as e:
                            print(f"[redis_bridge] parse error: {e}")
                            continue
                        if int(data.get("ts", 0) or 0) <= last_ts[stream]:
                            continue
                        tick = self._to_quote_tick(data)
                        if tick:
                            self._handler(tick)
                    last_ts[stream] = head_ts
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[redis_bridge] error: {e}")
                await asyncio.sleep(1)

    @staticmethod
    def _to_quote_tick(data: dict) -> QuoteTick | None:
        try:
            symbol_str = data["symbol"].replace("/", "-").replace(":", "-")
            exchange = data["exchange"]
            instrument_id = InstrumentId(Symbol(symbol_str), Venue(exchange))
            return QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(Decimal(str(data["bid"])), precision=2),
                ask_price=Price(Decimal(str(data["ask"])), precision=2),
                bid_size=Quantity(Decimal("1"), precision=3),
                ask_size=Quantity(Decimal("1"), precision=3),
                ts_event=data["ts"] * 1_000_000,
                ts_init=data["ts"] * 1_000_000,
            )
        except Exception:
            return None
