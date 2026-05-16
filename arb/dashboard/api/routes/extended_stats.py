"""
Extended statistics — Sortino, Calmar, streaks, hour-of-day, day-of-week,
strategy correlation matrix, trade duration histogram, slippage analysis.
"""
import math
from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter
from arb.infra.redis_bus import latest

router = APIRouter(prefix="/api/stats", tags=["extended_stats"])

ACCOUNT_START = 10_000.0


def _f(v, default=0.0):
    try: return float(v) if v is not None else default
    except (TypeError, ValueError): return default


async def _all_trades() -> list[dict]:
    """Get all closed orders from Redis."""
    orders = await latest("arb:orders", count=5000)
    return [
        {
            "ts": o.get("ts", 0),
            "strategy": o.get("strategy", "unknown"),
            "symbol": o.get("symbol", ""),
            "pnl": _f(o.get("pnl")),
            "size_usd": _f(o.get("size_usd")),
        }
        for o in orders if o.get("event") == "CLOSE"
    ]


@router.get("/extended")
async def extended_stats():
    """Sortino, Calmar, Recovery, streaks, etc."""
    trades = await _all_trades()
    if not trades:
        return {
            "sortino_ratio": 0, "calmar_ratio": 0, "recovery_factor": 0,
            "avg_trade_duration_s": 0, "max_consec_wins": 0, "max_consec_losses": 0,
            "current_streak": 0, "current_streak_type": "neutral",
            "expectancy_per_dollar": 0, "kelly_optimal_pct": 0,
            "tail_ratio": 0, "var_95": 0, "var_99": 0,
        }

    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    mean = sum(pnls) / n
    total_pnl = sum(pnls)

    # Sortino — downside deviation only
    downside = [min(0, p - mean) for p in pnls]
    downside_var = sum(d * d for d in downside) / max(n - 1, 1)
    downside_std = math.sqrt(downside_var)
    sortino = (mean / downside_std) * math.sqrt(252) if downside_std > 0 else 0

    # Calmar — return / max DD
    equity = ACCOUNT_START
    peak = ACCOUNT_START
    max_dd = 0.0
    for t in trades:
        equity += t["pnl"]
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    annualized_return = (total_pnl / ACCOUNT_START)
    calmar = (annualized_return / max_dd) if max_dd > 0 else 0

    # Recovery factor — total_pnl / max_dd_usd
    max_dd_usd = max_dd * peak
    recovery = (total_pnl / max_dd_usd) if max_dd_usd > 0 else 0

    # Streaks
    max_wins = max_losses = cur = 0
    cur_kind = "neutral"
    longest_w = longest_l = 0
    for p in pnls:
        if p > 0:
            if cur_kind == "win": cur += 1
            else: cur, cur_kind = 1, "win"
            longest_w = max(longest_w, cur)
        elif p < 0:
            if cur_kind == "loss": cur += 1
            else: cur, cur_kind = 1, "loss"
            longest_l = max(longest_l, cur)
    max_wins, max_losses = longest_w, longest_l

    # Kelly optimal fraction
    wins = [p for p in pnls if p > 0]
    losses_abs = [abs(p) for p in pnls if p < 0]
    p_win = len(wins) / n if n > 0 else 0
    avg_w = sum(wins) / len(wins) if wins else 0
    avg_l = sum(losses_abs) / len(losses_abs) if losses_abs else 1
    b = avg_w / avg_l if avg_l > 0 else 1
    kelly = (p_win - (1 - p_win) / b) if b > 0 else 0

    # Tail ratio — 95th percentile gain / 5th percentile loss
    sorted_p = sorted(pnls)
    p95 = sorted_p[int(n * 0.95)] if n > 0 else 0
    p5 = sorted_p[int(n * 0.05)] if n > 0 else 0
    tail = abs(p95 / p5) if p5 != 0 else 0

    # VaR
    var_95 = sorted_p[int(n * 0.05)] if n > 0 else 0
    var_99 = sorted_p[int(n * 0.01)] if n > 0 else 0

    avg_size = sum(t["size_usd"] for t in trades) / n if n > 0 else 1
    expectancy_per_dollar = mean / avg_size if avg_size > 0 else 0

    return {
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "recovery_factor": round(recovery, 2),
        "max_consec_wins": max_wins,
        "max_consec_losses": max_losses,
        "current_streak": cur,
        "current_streak_type": cur_kind,
        "expectancy_per_dollar": round(expectancy_per_dollar, 5),
        "kelly_optimal_pct": round(max(0, min(kelly, 0.25)) * 100, 2),
        "tail_ratio": round(tail, 2),
        "var_95": round(var_95, 2),
        "var_99": round(var_99, 2),
        "avg_trade_size_usd": round(avg_size, 2),
        "total_volume_usd": round(sum(t["size_usd"] for t in trades), 0),
    }


@router.get("/hourly")
async def hourly_breakdown():
    """PnL & trade count by hour of day — for heatmap."""
    trades = await _all_trades()
    by_hour: dict[int, dict] = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    for t in trades:
        try:
            ts = t["ts"]
            if isinstance(ts, (int, float)):
                hour = datetime.fromtimestamp(ts / 1000).hour
            else:
                hour = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).hour
        except Exception:
            continue
        by_hour[hour]["trades"] += 1
        by_hour[hour]["pnl"] += t["pnl"]
        if t["pnl"] > 0: by_hour[hour]["wins"] += 1

    hours = []
    for h in range(24):
        d = by_hour[h]
        hours.append({
            "hour": h,
            "trades": d["trades"],
            "pnl": round(d["pnl"], 2),
            "win_rate": round((d["wins"] / d["trades"]) * 100, 1) if d["trades"] > 0 else 0,
        })
    return {"hourly": hours}


@router.get("/correlation")
async def strategy_correlation():
    """Pairwise correlation matrix between strategy PnL."""
    trades = await _all_trades()
    # Group PnL by strategy + ts-bucket (1min)
    series: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for t in trades:
        ts = t["ts"]
        bucket = (ts // 60_000) if isinstance(ts, (int, float)) else 0
        series[t["strategy"]][bucket] += t["pnl"]

    strategies = list(series.keys())
    if len(strategies) < 2:
        return {"strategies": strategies, "matrix": []}

    # Build aligned arrays
    all_buckets = sorted(set().union(*[s.keys() for s in series.values()]))
    arrs = {s: [series[s].get(b, 0.0) for b in all_buckets] for s in strategies}

    def correl(a: list[float], b: list[float]) -> float:
        if len(a) < 2: return 0
        mean_a = sum(a) / len(a)
        mean_b = sum(b) / len(b)
        num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
        var_a = sum((x - mean_a) ** 2 for x in a)
        var_b = sum((y - mean_b) ** 2 for y in b)
        denom = (var_a * var_b) ** 0.5
        return num / denom if denom > 0 else 0

    matrix = []
    for s1 in strategies:
        row = []
        for s2 in strategies:
            if s1 == s2:
                row.append(1.0)
            else:
                row.append(round(correl(arrs[s1], arrs[s2]), 3))
        matrix.append(row)

    return {"strategies": strategies, "matrix": matrix}
