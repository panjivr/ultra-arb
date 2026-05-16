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
        last_ids = {s: "$" for s in self._streams}
        while True:
            try:
                results = await self._redis.xread(last_ids, count=50, block=100)
                if results:
                    for stream, messages in results:
                        for msg_id, fields in messages:
                            last_ids[stream] = msg_id
                            try:
                                data = json.loads(fields["data"])
                                tick = self._to_quote_tick(data)
                                if tick:
                                    self._handler(tick)
                            except Exception as e:
                                print(f"[redis_bridge] parse error: {e}")
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
