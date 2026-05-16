"""
Bybit linear perpetuals WebSocket feed via ccxt.pro.
Streams order book → Redis arb:ticks:{symbol}:BYBIT
"""
import asyncio
import time
import ccxt.pro as ccxtpro
from arb.config import settings
from arb.infra.redis_bus import publish
from arb.infra.db import engine
from sqlalchemy import text

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


def _exchange() -> ccxtpro.bybit:
    params = {
        "apiKey": settings.bybit_api_key or None,
        "secret": settings.bybit_api_secret or None,
        "options": {"defaultType": "linear"},
    }
    if settings.bybit_testnet:
        params["urls"] = {"api": {"public": "https://api-testnet.bybit.com"}}
    return ccxtpro.bybit(params)


async def _watch_orderbook(exchange: ccxtpro.bybit, symbol: str) -> None:
    stream_key = f"arb:ticks:{symbol}:BYBIT"
    while True:
        try:
            ob = await exchange.watch_order_book(symbol, limit=5)
            if ob["bids"] and ob["asks"]:
                bid = ob["bids"][0][0]
                ask = ob["asks"][0][0]
                mid = (bid + ask) / 2
                payload = {
                    "ts": int(time.time() * 1000),
                    "symbol": symbol,
                    "exchange": "BYBIT",
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                }
                await publish(stream_key, payload)
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "INSERT INTO ticks (time, symbol, exchange, bid, ask, mid) "
                            "VALUES (NOW(), :sym, :ex, :bid, :ask, :mid)"
                        ),
                        {"sym": symbol, "ex": "BYBIT", "bid": bid, "ask": ask, "mid": mid},
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[bybit_feed] {symbol} error: {e}")
            await asyncio.sleep(1)


async def _watch_funding(exchange: ccxtpro.bybit, symbol: str) -> None:
    while True:
        try:
            ticker = await exchange.fetch_funding_rate(symbol)
            rate = ticker.get("fundingRate", 0.0) or 0.0
            await publish(f"arb:funding:{symbol}:BYBIT", {
                "ts": int(time.time() * 1000),
                "symbol": symbol,
                "exchange": "BYBIT",
                "rate": rate,
            })
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[bybit_feed] funding {symbol} error: {e}")
            await asyncio.sleep(10)


async def run() -> None:
    exchange = _exchange()
    try:
        tasks = []
        for sym in SYMBOLS:
            tasks.append(asyncio.create_task(_watch_orderbook(exchange, sym)))
            tasks.append(asyncio.create_task(_watch_funding(exchange, sym)))
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()
