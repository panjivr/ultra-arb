"""
Live trading executor.
PAPER_TRADE=true → SimulatedExchangeConfig (no real orders).
PAPER_TRADE=false → real exchange execution via CCXT.
"""
import asyncio
import time
import json
import ccxt.async_support as ccxt_async
from arb.config import settings
from arb.risk.risk_runner import RiskRunner
from arb.risk.sizing import KellyPositionSizer
from arb.infra.redis_bus import get_redis, publish


class LiveExecutor:
    def __init__(self, risk_runner: RiskRunner) -> None:
        self._risk = risk_runner
        self._sizer = KellyPositionSizer(10_000.0)
        self._binance: ccxt_async.binanceusdm | None = None
        self._bybit: ccxt_async.bybit | None = None

    async def start(self) -> None:
        if not settings.paper_trade:
            await self._init_exchanges()
        print(
            f"[live_executor] Started in {'PAPER' if settings.paper_trade else 'LIVE'} mode."
        )
        await self._signal_consumer()

    async def _init_exchanges(self) -> None:
        self._binance = ccxt_async.binanceusdm({
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_api_secret,
            "options": {"defaultType": "future"},
        })
        if settings.binance_testnet:
            self._binance.set_sandbox_mode(True)

        self._bybit = ccxt_async.bybit({
            "apiKey": settings.bybit_api_key,
            "secret": settings.bybit_api_secret,
        })
        if settings.bybit_testnet:
            self._bybit.set_sandbox_mode(True)

    async def _signal_consumer(self) -> None:
        r = get_redis()
        last_id = "$"
        while True:
            try:
                results = await r.xread({"arb:signals": last_id}, count=10, block=200)
                if results:
                    for _, messages in results:
                        for msg_id, fields in messages:
                            last_id = msg_id
                            data = json.loads(fields["data"])
                            if data.get("tradeable") and not self._risk.is_halted:
                                await self._execute(data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[live_executor] error: {e}")
                await asyncio.sleep(1)

    async def _execute(self, signal: dict) -> None:
        strategy = signal.get("strategy", "")
        symbol = signal.get("symbol", "")
        prob = signal.get("probability_score", 0.5)
        rr = signal.get("risk_reward", 1.0)
        regime = signal.get("regime", 1)
        liq = signal.get("liquidity_score", 0.7)

        sizing = self._sizer.compute(prob, rr, regime, liq)
        pos_usd = sizing["position_usd"]

        if settings.paper_trade:
            await publish("arb:orders", {
                "ts": int(time.time() * 1000),
                "event": "PAPER_TRADE",
                "strategy": strategy,
                "symbol": symbol,
                "direction": signal.get("direction", "UNKNOWN"),
                "size_usd": pos_usd,
                "probability": prob,
                "regime": regime,
            })
            print(
                f"[live_executor] PAPER {strategy} {symbol} "
                f"${pos_usd:.2f} P={prob:.2f} regime={regime}"
            )
        else:
            await self._place_real_order(signal, pos_usd)

    async def _place_real_order(self, signal: dict, size_usd: float) -> None:
        """Real order placement — only executes when PAPER_TRADE=false."""
        symbol = signal.get("symbol", "")
        direction = signal.get("direction", "")
        side = "buy" if "LONG" in direction or "BUY" in direction else "sell"
        exchange_name = "BINANCE" if "BINANCE" in direction else "BYBIT"
        exchange = self._binance if exchange_name == "BINANCE" else self._bybit
        if not exchange:
            return

        try:
            ticker = await exchange.fetch_ticker(symbol)
            price = ticker["last"]
            qty = size_usd / price
            order = await exchange.create_market_order(symbol, side, qty)
            print(f"[live_executor] LIVE ORDER: {exchange_name} {side} {qty:.6f} {symbol} → {order['id']}")
        except Exception as e:
            print(f"[live_executor] order error: {e}")

    async def stop(self) -> None:
        if self._binance:
            await self._binance.close()
        if self._bybit:
            await self._bybit.close()
