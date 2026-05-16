"""
Live market data — cross-exchange spreads, funding rates, regime/model state.
Reads from Redis streams populated by feed runners and model_runner.
"""
import time
from collections import defaultdict
from fastapi import APIRouter
from arb.infra.redis_bus import latest, get_redis

router = APIRouter(prefix="/api", tags=["markets"])


def _f(v, default=0.0):
    try: return float(v) if v is not None else default
    except (TypeError, ValueError): return default


@router.get("/spreads")
async def get_spreads():
    """
    Live cross-exchange spreads. Pulls latest tick per exchange per symbol
    and computes bps spread for arb opportunity detection.
    """
    r = get_redis()
    keys = await r.keys("arb:ticks:*")
    by_symbol: dict[str, dict[str, dict]] = defaultdict(dict)

    for key in keys:
        # key format: arb:ticks:{symbol}:{settle}:{exchange}
        parts = key.split(":")
        if len(parts) < 5: continue
        symbol = parts[2]
        exchange = parts[-1]
        ticks = await latest(key, count=1)
        if ticks:
            t = ticks[0]
            by_symbol[symbol][exchange] = {
                "bid": _f(t.get("bid")), "ask": _f(t.get("ask")),
                "mid": _f(t.get("mid")), "ts": t.get("ts", 0),
            }

    spreads = []
    for symbol, exchanges in by_symbol.items():
        if len(exchanges) < 2:
            for ex, data in exchanges.items():
                spreads.append({
                    "symbol": symbol, "exchanges": [ex], "spread_bps": 0.0,
                    "buy_at": data.get("ask", 0), "sell_at": data.get("bid", 0),
                    "edge_usd": 0.0,
                })
            continue
        names = list(exchanges.keys())
        best_buy_ex, best_buy_ask = None, float("inf")
        best_sell_ex, best_sell_bid = None, 0.0
        for ex, d in exchanges.items():
            if d["ask"] > 0 and d["ask"] < best_buy_ask:
                best_buy_ask = d["ask"]; best_buy_ex = ex
            if d["bid"] > best_sell_bid:
                best_sell_bid = d["bid"]; best_sell_ex = ex
        if best_buy_ask < float("inf") and best_buy_ask > 0:
            spread_bps = (best_sell_bid - best_buy_ask) / best_buy_ask * 10_000
            spreads.append({
                "symbol": symbol,
                "exchanges": names,
                "buy_at": round(best_buy_ask, 4),
                "buy_ex": best_buy_ex,
                "sell_at": round(best_sell_bid, 4),
                "sell_ex": best_sell_ex,
                "spread_bps": round(spread_bps, 2),
                "edge_usd": round((best_sell_bid - best_buy_ask), 4),
            })
    spreads.sort(key=lambda x: x["spread_bps"], reverse=True)
    return {"spreads": spreads, "count": len(spreads), "ts": int(time.time() * 1000)}


@router.get("/funding")
async def get_funding_rates():
    """Current funding rates across perps — arb opportunity = max spread."""
    r = get_redis()
    keys = await r.keys("arb:funding:*")
    rates = []
    by_symbol: dict[str, list[dict]] = defaultdict(list)

    for key in keys:
        ticks = await latest(key, count=1)
        if not ticks: continue
        t = ticks[0]
        symbol = t.get("symbol", key.split(":")[-1])
        rec = {
            "symbol": symbol,
            "exchange": t.get("exchange", "unknown"),
            "rate": _f(t.get("rate")) * 100,  # convert to %
            "next_funding_ts": t.get("next_funding_ts", 0),
            "ts": t.get("ts", 0),
        }
        rates.append(rec)
        by_symbol[symbol].append(rec)

    # Compute arb opportunity per symbol
    opportunities = []
    for symbol, entries in by_symbol.items():
        if len(entries) < 2: continue
        sorted_by_rate = sorted(entries, key=lambda x: x["rate"])
        low, high = sorted_by_rate[0], sorted_by_rate[-1]
        spread = high["rate"] - low["rate"]
        if spread > 0:
            opportunities.append({
                "symbol": symbol,
                "long_at": low["exchange"], "long_rate": round(low["rate"], 4),
                "short_at": high["exchange"], "short_rate": round(high["rate"], 4),
                "spread_pct": round(spread, 4),
                "annualized_pct": round(spread * 3 * 365, 2),  # 8h funding × 3/day × 365
            })

    return {
        "rates": sorted(rates, key=lambda x: abs(x["rate"]), reverse=True),
        "opportunities": sorted(opportunities, key=lambda x: x["spread_pct"], reverse=True),
        "count": len(rates),
    }


@router.get("/models")
async def get_model_state():
    """ML/quant model state — HMM regime, Kalman, cointegration pairs."""
    regime_msgs = await latest("arb:models:regime", count=1)
    kalman_msgs = await latest("arb:models:kalman", count=5)
    cointeg_msgs = await latest("arb:models:cointegration", count=10)
    bayesian_msgs = await latest("arb:models:bayesian", count=5)

    regime_data = regime_msgs[0] if regime_msgs else {}
    regime_label_map = {0: "LOW VOL", 1: "MED VOL", 2: "HIGH VOL"}

    return {
        "regime": {
            "state": regime_data.get("regime", 0),
            "label": regime_label_map.get(regime_data.get("regime", 0), "UNKNOWN"),
            "confidence": _f(regime_data.get("confidence"), 0.0),
            "transition_matrix": regime_data.get("transition_matrix", []),
            "ts": regime_data.get("ts", 0),
        },
        "kalman": [
            {
                "symbol": k.get("symbol", "?"),
                "state": _f(k.get("state")),
                "covariance": _f(k.get("covariance")),
                "ts": k.get("ts", 0),
            } for k in kalman_msgs
        ],
        "cointegration": [
            {
                "pair": c.get("pair", "?-?"),
                "hedge_ratio": _f(c.get("hedge_ratio")),
                "zscore": _f(c.get("zscore")),
                "pvalue": _f(c.get("pvalue")),
                "signal": c.get("signal", "neutral"),  # long/short/neutral
                "ts": c.get("ts", 0),
            } for c in cointeg_msgs
        ],
        "bayesian": [
            {
                "strategy": b.get("strategy", "?"),
                "alpha": _f(b.get("alpha")),
                "beta": _f(b.get("beta")),
                "win_prob": _f(b.get("win_prob")),
                "ts": b.get("ts", 0),
            } for b in bayesian_msgs
        ],
    }


@router.get("/risk/state")
async def get_risk_state():
    """Risk engine state — circuit breakers, exposure, position limits."""
    alerts = await latest("arb:risk:alerts", count=20)
    positions = await latest("arb:positions:open", count=20)
    breakers = await latest("arb:risk:breakers", count=1)

    # Aggregate exposure
    exposure_usd = sum(_f(p.get("size_usd")) for p in positions)
    breaker_state = breakers[0] if breakers else {}

    halted = any(a.get("halted") for a in alerts[:5])

    return {
        "halted": halted,
        "alerts": alerts[:10],
        "open_positions": len(positions),
        "max_positions": 5,
        "exposure_usd": round(exposure_usd, 2),
        "daily_pnl_pct": _f(breaker_state.get("daily_pnl_pct"), 0.0),
        "max_drawdown_pct": _f(breaker_state.get("max_drawdown_pct"), 2.0),
        "vol_multiplier": _f(breaker_state.get("vol_multiplier"), 1.0),
        "vol_threshold": 3.0,
        "drawdown_breaker": {
            "triggered": _f(breaker_state.get("daily_pnl_pct"), 0.0) <= -2.0,
            "value": _f(breaker_state.get("daily_pnl_pct"), 0.0),
            "threshold": -2.0,
        },
        "vol_breaker": {
            "triggered": _f(breaker_state.get("vol_multiplier"), 1.0) >= 3.0,
            "value": _f(breaker_state.get("vol_multiplier"), 1.0),
            "threshold": 3.0,
        },
    }


@router.get("/positions/open")
async def get_open_positions():
    """Currently-open positions with mark-to-market."""
    positions = await latest("arb:positions:open", count=50)
    out = []
    for p in positions:
        entry = _f(p.get("entry_price"))
        mark = _f(p.get("mark_price") or p.get("entry_price"))
        qty = _f(p.get("qty"))
        side = p.get("direction", "long")
        pnl_usd = (mark - entry) * qty if side == "long" else (entry - mark) * qty
        out.append({
            "symbol": p.get("symbol", "?"),
            "strategy": p.get("strategy", "?"),
            "exchange": p.get("exchange", "?"),
            "direction": side,
            "qty": qty,
            "entry_price": round(entry, 4),
            "mark_price": round(mark, 4),
            "size_usd": _f(p.get("size_usd")),
            "unrealized_pnl_usd": round(pnl_usd, 2),
            "unrealized_pnl_pct": round((pnl_usd / _f(p.get("size_usd"), 1)) * 100, 3) if _f(p.get("size_usd")) > 0 else 0,
            "opened_at": p.get("ts", 0),
        })
    return {"positions": out, "count": len(out)}
