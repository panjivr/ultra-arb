"""
Aggregated trading statistics — KPIs, equity curve, Sharpe, drawdown, win rate.
Reads from Redis (live signals/orders) + PostgreSQL (historical trades).
Starting capital comes from linked wallet (real USDC balance) when connected,
otherwise falls back to $10,000 demo capital.
"""
import json
import math
import time
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from arb.dashboard.api.deps import get_db
from arb.infra.redis_bus import latest, get_redis

router = APIRouter(prefix="/api", tags=["stats"])

DEMO_ACCOUNT_START = 10_000.0


async def _account_start_capital() -> tuple[float, bool, str | None, int]:
    """Return (start_capital, is_real_wallet, wallet_addr, linked_at_ms).

    Multi-wallet schema:
      arb:wallet:active      → currently active address
      arb:wallet:linked:{a}  → JSON per wallet
      arb:wallet:list        → set of all addresses

    Sums all linked wallet balances if user has multiple connected.
    linked_at = earliest linked_at across wallets, so equity tracks since
    first wallet connect.
    """
    try:
        r = get_redis()

        # Collect ALL linked wallets
        addrs = []
        try:
            raw_addrs = await r.smembers("arb:wallet:list")
            addrs = [a.decode() if isinstance(a, bytes) else a for a in (raw_addrs or [])]
        except Exception:
            pass

        if addrs:
            total = 0.0
            first_addr = None
            earliest_linked = None
            for a in addrs:
                wraw = await r.get(f"arb:wallet:linked:{a.lower()}")
                if not wraw:
                    continue
                d = json.loads(wraw)
                total += float(d.get("usdc_balance", 0) or 0)
                if first_addr is None:
                    first_addr = d.get("address")
                la = int(d.get("linked_at", 0) or 0)
                if la and (earliest_linked is None or la < earliest_linked):
                    earliest_linked = la
            if total > 0:
                # Prefer "active" wallet address for display
                active_raw = await r.get("arb:wallet:active")
                if active_raw:
                    first_addr = active_raw.decode() if isinstance(active_raw, bytes) else active_raw
                return total, True, first_addr, earliest_linked or 0

        # Legacy fallback
        raw = await r.get("arb:wallet:linked")
        if raw:
            data = json.loads(raw)
            usdc = float(data.get("usdc_balance", 0) or 0)
            linked_at = int(data.get("linked_at", 0) or 0)
            if usdc > 0:
                return usdc, True, data.get("address"), linked_at
    except Exception:
        pass
    return DEMO_ACCOUNT_START, False, None, 0


def _safe_float(v) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def _trades_from_db(db: AsyncSession, interval: str = "30 days") -> list[dict]:
    try:
        rows = await db.execute(
            text(
                f"SELECT time, symbol, side, qty, price, pnl, strategy, exchange "
                f"FROM trades WHERE time > NOW() - INTERVAL '{interval}' "
                f"ORDER BY time ASC"
            )
        )
        return [
            {
                "time": str(r[0]), "symbol": r[1], "side": r[2],
                "qty": _safe_float(r[3]), "price": _safe_float(r[4]),
                "pnl": _safe_float(r[5]), "strategy": r[6], "exchange": r[7],
            }
            for r in rows
        ]
    except Exception:
        return []


_WINDOW_MS = {"1h": 3_600_000, "24h": 86_400_000, "7d": 604_800_000, "30d": 2_592_000_000}


async def _trades_from_redis(window: str | None = None, since_ms: int = 0) -> list[dict]:
    """Fallback when DB is unavailable — reconstruct trades from arb:orders stream.
    Optionally filter by window (1h/24h/7d/30d) and/or `since_ms` (e.g. wallet linked_at).
    """
    orders = await latest("arb:orders", count=8000)
    cutoff = 0
    if window and window in _WINDOW_MS:
        cutoff = int(time.time() * 1000) - _WINDOW_MS[window]
    # Wallet linked_at takes priority over window if it's more recent
    if since_ms > cutoff:
        cutoff = since_ms
    trades = []
    for o in orders:
        if o.get("event") != "CLOSE" or "pnl" not in o:
            continue
        ts = int(o.get("ts", 0) or 0)
        if cutoff and ts < cutoff:
            continue
        trades.append({
            "time": ts,
            "symbol": o.get("symbol", ""),
            "side": o.get("direction", ""),
            "qty": _safe_float(o.get("size_usd")),
            "price": _safe_float(o.get("exit_price") or o.get("price")),
            "pnl": _safe_float(o.get("pnl")),
            "strategy": o.get("strategy", ""),
            "exchange": o.get("exchange", ""),
        })
    trades.sort(key=lambda t: t["time"])
    return trades


def _compute_stats(trades: list[dict], start_capital: float = DEMO_ACCOUNT_START,
                   is_real_wallet: bool = False, wallet_addr: str | None = None) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "total_pnl_usd": 0.0,
            "total_pnl_pct": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "profit_factor": 0.0, "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0, "expectancy": 0.0,
            "equity_curve": [], "current_equity": start_capital,
            "start_capital": start_capital,
            "is_real_wallet": is_real_wallet,
            "wallet_addr": wallet_addr,
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = len(wins) / len(pnls) if pnls else 0.0

    # Profit factor: sum(wins) / abs(sum(losses))
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses))
    if sum_losses > 0:
        profit_factor = round(sum_wins / sum_losses, 3)
    elif sum_wins > 0:
        profit_factor = 99.99
    else:
        profit_factor = 0.0

    # Sharpe (per-trade, annualized assuming 250 trading days)
    # Skip computation for tiny samples — extreme values are misleading
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / max(len(pnls) - 1, 1)
    std = math.sqrt(var)
    if len(pnls) < 20 or std == 0:
        sharpe = 0.0  # insufficient sample
    else:
        sharpe = (mean / std) * math.sqrt(252)
        # Clamp to sensible range — anything outside is statistical noise
        sharpe = max(-10.0, min(20.0, sharpe))

    # Equity curve + max drawdown — starting from REAL wallet balance if connected
    equity = start_capital
    peak = start_capital
    max_dd_pct = 0.0
    curve = []
    for t in trades:
        equity += t["pnl"]
        peak = max(peak, equity)
        dd_pct = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd_pct = max(max_dd_pct, dd_pct)
        curve.append({"time": t["time"], "equity": round(equity, 2), "drawdown_pct": round(dd_pct, 3)})

    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate * 100, 2),
        "total_pnl_usd": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / start_capital) * 100, 3) if start_capital else 0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": profit_factor,
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "expectancy": round(mean, 3),
        "equity_curve": curve[-200:],  # last 200 points
        "current_equity": round(equity, 2),
        "start_capital": start_capital,
        "is_real_wallet": is_real_wallet,
        "wallet_addr": wallet_addr,
    }


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Aggregated trading stats — used by the top KPI bar.

    Wallet mode: only trades AFTER linked_at counted, so equity tracks the REAL
    wallet from connect time forward (no inherited demo PnL).
    """
    start_cap, is_real, addr, linked_at = await _account_start_capital()
    trades = await _trades_from_db(db)
    if not trades:
        trades = await _trades_from_redis(since_ms=linked_at if is_real else 0)
    return _compute_stats(trades, start_cap, is_real, addr)


@router.get("/equity")
async def get_equity_curve(window: str = "7d", db: AsyncSession = Depends(get_db)):
    """Equity curve with drawdown overlay — filtered by window AND wallet linked_at."""
    start_cap, is_real, addr, linked_at = await _account_start_capital()
    interval_map = {"1h": "1 hour", "24h": "1 day", "7d": "7 days", "30d": "30 days"}
    interval = interval_map.get(window, "7 days")
    trades = await _trades_from_db(db, interval)
    if not trades:
        trades = await _trades_from_redis(window=window, since_ms=linked_at if is_real else 0)
    stats = _compute_stats(trades, start_cap, is_real, addr)
    return {
        "window": window,
        "current_equity": stats["current_equity"],
        "total_pnl_pct": stats["total_pnl_pct"],
        "max_drawdown_pct": stats["max_drawdown_pct"],
        "trades_in_window": stats["total_trades"],
        "start_capital": start_cap,
        "is_real_wallet": is_real,
        "wallet_addr": addr,
        "wallet_linked_at": linked_at,
        "curve": stats["equity_curve"],
    }


@router.get("/strategies")
async def get_strategy_breakdown(db: AsyncSession = Depends(get_db)):
    """Per-strategy performance breakdown."""
    trades = await _trades_from_db(db)
    if not trades:
        trades = await _trades_from_redis()

    by_strategy = defaultdict(list)
    for t in trades:
        by_strategy[t["strategy"] or "unknown"].append(t)

    out = []
    for name, ts in by_strategy.items():
        pnls = [t["pnl"] for t in ts]
        wins = sum(1 for p in pnls if p > 0)
        out.append({
            "strategy": name,
            "trades": len(ts),
            "pnl_usd": round(sum(pnls), 2),
            "win_rate": round((wins / len(pnls)) * 100, 1) if pnls else 0.0,
            "avg_pnl": round(sum(pnls) / len(pnls), 3) if pnls else 0.0,
            "best": round(max(pnls), 2) if pnls else 0.0,
            "worst": round(min(pnls), 2) if pnls else 0.0,
        })
    out.sort(key=lambda x: x["pnl_usd"], reverse=True)
    return {"strategies": out, "count": len(out)}
