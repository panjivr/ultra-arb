"""
Binance futures WebSocket feed via ccxt.pro.
Streams order book and funding rate data → Redis arb:ticks:BTC/USDT:BINANCE
"""
import asyncio
import time
import ccxt.pro as ccxtpro
from arb.config import settings
from arb.infra.redis_bus import publish
from arb.infra.db import engine
from sqlalchemy import text

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


def _exchange() -> ccxtpro.binanceusdm:
    params = {
        "apiKey": settings.binance_api_key or None,
        "secret": settings.binance_api_secret or None,
        "options": {"defaultType": "future"},
    }
    if settings.binance_testnet:
        params["urls"] = {"api": {"public": "https://testnet.binancefuture.com"}}
    return ccxtpro.binanceusdm(params)


async def _persist_tick(symbol: str, exchange: str, bid: float, ask: float, mid: float) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ticks (time, symbol, exchange, bid, ask, mid) "
                "VALUES (NOW(), :sym, :ex, :bid, :ask, :mid)"
            ),
            {"sym": symbol, "ex": exchange, "bid": bid, "ask": ask, "mid": mid},
        )


async def _watch_orderbook(exchange: ccxtpro.binanceusdm, symbol: str) -> None:
    stream_key = f"arb:ticks:{symbol}:BINANCE"
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
                    "exchange": "BINANCE",
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                }
                await publish(stream_key, payload)
                await _persist_tick(symbol, "BINANCE", bid, ask, mid)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[binance_feed] {symbol} error: {e}")
            await asyncio.sleep(1)


async def _watch_funding(exchange: ccxtpro.binanceusdm, symbol: str) -> None:
    while True:
        try:
            ticker = await exchange.fetch_funding_rate(symbol)
            rate = ticker.get("fundingRate", 0.0) or 0.0
            payload = {
                "ts": int(time.time() * 1000),
                "symbol": symbol,
                "exchange": "BINANCE",
                "rate": rate,
            }
            await publish(f"arb:funding:{symbol}:BINANCE", payload)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO funding_rates (time, symbol, exchange, rate) "
                        "VALUES (NOW(), :sym, :ex, :rate)"
                    ),
                    {"sym": symbol, "ex": "BINANCE", "rate": rate},
                )
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[binance_feed] funding {symbol} error: {e}")
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
