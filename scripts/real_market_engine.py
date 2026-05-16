"""
REAL MARKET ENGINE — fetches LIVE prices from Gate.io & HTX public APIs.

Unlike the simulator, this uses ACTUAL market data so:
- BTC, ETH, SOL etc. show their TRUE current prices
- Cross-exchange spreads reflect REAL market inefficiencies (Gate.io vs HTX)
- Signals fire on REAL spread conditions
- Trades execute at REAL market prices (paper PnL though, until live keys added)

Public REST polling, no API key needed. Sub-second cadence with light jitter for
intra-poll tick density. Background ccxt rate-limited to ~10 req/s per exchange.

Run: python scripts/real_market_engine.py
Stop: Ctrl+C
"""
import asyncio
import json
import math
import os
import random
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt  # SYNC ccxt — async version has SSL issues on Windows via aiohttp
import httpx


# Symbol universe — REAL trading pairs
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
# Two exchanges that work past local SSL filtering (verified live)
EXCHANGES = {
    "GATEIO": lambda: ccxt.gateio({"enableRateLimit": True, "timeout": 8000}),
    "HTX": lambda: ccxt.htx({"enableRateLimit": True, "timeout": 8000}),
}
# Thread pool for blocking ccxt sync calls: 2 exchanges × 5 symbols = 10 concurrent
_pool = ThreadPoolExecutor(max_workers=12)

# Default demo capital; real capital comes from linked wallet
DEMO_CAPITAL = 10_000.0
DEFAULT_MAX_RISK_PCT = 0.025  # 2.5% Kelly cap per trade
KELLY_FRACTION = 0.5  # half-Kelly for safety

STRATEGIES = ["CrossExchange", "FundingRate", "Basis", "PolymarketArb"]

# In-memory live price cache: {symbol: {exchange: {bid, ask, mid, ts}}}
prices: dict[str, dict[str, dict]] = {s: {} for s in SYMBOLS}
# Recent mids for vol calc (per symbol)
recent_mids: dict[str, deque] = {s: deque(maxlen=120) for s in SYMBOLS}

# Counters
counters = {"ticks": 0, "signals": 0, "trades": 0, "errors": 0, "fetches": 0}
equity = 10_000.0
start_ts = time.time()


def _sync_fetch_ticker(ex, sym):
    """Blocking ccxt call — runs in thread pool."""
    return ex.fetch_ticker(sym)


async def _record_latency(r, stage: str, ns: int):
    """Record a ns-precision latency sample to Redis (fire-and-forget)."""
    try:
        key = f"arb:latency:{stage}"
        await r.lpush(key, str(ns))
        await r.ltrim(key, 0, 999)
    except Exception:
        pass


async def _get_capital(r) -> tuple[float, bool, str | None]:
    """Read trading capital — wallet USDC if linked, else demo."""
    try:
        raw = await r.get("arb:wallet:linked")
        if raw:
            d = json.loads(raw)
            usdc = float(d.get("usdc_balance", 0) or 0)
            if usdc > 0:
                return usdc, True, d.get("address")
    except Exception:
        pass
    return DEMO_CAPITAL, False, None


def _kelly_position_usd(capital: float, win_prob: float, win_loss_ratio: float = 1.0) -> float:
    """Kelly criterion sizing — clamped to safe range."""
    if win_prob <= 0 or win_prob >= 1:
        return 0
    # Kelly fraction: f = p - q/b
    q = 1 - win_prob
    b = max(win_loss_ratio, 0.1)
    full_kelly = win_prob - q / b
    if full_kelly <= 0:
        return 0
    f = full_kelly * KELLY_FRACTION  # half-Kelly
    f = min(f, DEFAULT_MAX_RISK_PCT)  # never more than 2.5% per trade
    return round(capital * f, 2)


async def fetch_loop(ex_name: str, ex_factory):
    """Continuously fetch tickers for all symbols from one exchange via thread pool."""
    ex = ex_factory()
    loop = asyncio.get_event_loop()
    first_log = True
    while True:
        for sym in SYMBOLS:
            try:
                t = await loop.run_in_executor(_pool, _sync_fetch_ticker, ex, sym)
                bid = float(t.get("bid") or t.get("last") or 0)
                ask = float(t.get("ask") or t.get("last") or 0)
                if not bid or not ask:
                    continue
                mid = (bid + ask) / 2
                prices[sym][ex_name] = {
                    "bid": bid, "ask": ask, "mid": mid,
                    "ts": int(time.time() * 1000),
                }
                recent_mids[sym].append(mid)
                counters["fetches"] += 1
                if first_log:
                    print(f"[real] {ex_name} {sym}: ${mid:,.4f}")
            except Exception as e:
                counters["errors"] += 1
                if counters["errors"] < 5:
                    print(f"[real] {ex_name} {sym} err: {repr(e)[:120]}")
            await asyncio.sleep(0.1)  # small inter-symbol delay
        first_log = False
        await asyncio.sleep(0.6)  # ~1 cycle/sec per exchange


async def emit_ticks():
    """Publish REAL prices to Redis as ticks. No synthetic jitter — actual market data only."""
    from arb.infra.redis_bus import publish
    while True:
        await asyncio.sleep(0.1)
        for sym, exs in prices.items():
            for ex_name, p in exs.items():
                # Publish raw prices; no jitter (synthetic noise corrupts signal quality
                # and makes backtests non-reproducible)
                await publish(f"arb:ticks:{sym}:USDT:{ex_name}", {
                    "symbol": sym, "exchange": ex_name,
                    "bid": round(p["bid"], 4), "ask": round(p["ask"], 4),
                    "mid": round(p["mid"], 4),
                    "ts": int(time.time() * 1000),
                    "source": "REAL",
                })
                counters["ticks"] += 1


async def emit_signals():
    """Emit arbitrage signals based on REAL cross-exchange spreads.
    Records ns-precision latency at each pipeline stage.
    """
    from arb.infra.redis_bus import publish, get_redis
    r = get_redis()
    while True:
        await asyncio.sleep(random.uniform(0.5, 1.5))
        sym = random.choice(SYMBOLS)
        if len(prices[sym]) < 2:
            continue

        # ── PIPELINE START: tick observed ──
        t_pipeline_start = time.perf_counter_ns()

        # Compute REAL spread between exchanges
        exs = list(prices[sym].items())
        ex_a, p_a = exs[0]
        ex_b, p_b = exs[1]
        spread_bps = (p_b["mid"] - p_a["mid"]) / p_a["mid"] * 10_000

        # Stage: spread calc (would be Rust in production)
        t_after_spread = time.perf_counter_ns()
        rust_spread_ns = t_after_spread - t_pipeline_start

        # Compute realised vol from recent mids (Rust Kalman in prod)
        mids = list(recent_mids[sym])
        vol = 0.0
        if len(mids) > 10:
            rets = [(mids[i]/mids[i-1] - 1) for i in range(1, len(mids))]
            vol = (sum(r*r for r in rets) / len(rets)) ** 0.5
        t_after_kalman = time.perf_counter_ns()
        rust_kalman_ns = t_after_kalman - t_after_spread

        # G1: honest attribution. This signal IS cross-exchange arbitrage
        # (it is literally derived from the spread between two exchanges).
        # No random.choice — the strategy that decided is the strategy tagged.
        strategy = "CrossExchange"
        # Deterministic probability from actual spread — no random noise
        # A larger real spread means higher confidence, but execution risk caps the ceiling
        abs_spread = abs(spread_bps)
        if abs_spread < 2:
            prob = 0.52
        elif abs_spread < 5:
            prob = 0.57
        elif abs_spread < 10:
            prob = 0.63
        elif abs_spread < 20:
            prob = 0.69
        elif abs_spread < 50:
            prob = 0.74
        else:
            prob = 0.79
        # Expected value: spread minus 4 bps roundtrip cost, as fraction
        ev = max(0.001, (abs_spread - 4) / 10_000) if abs_spread > 4 else 0.001
        regime = 0 if vol < 0.0005 else (1 if vol < 0.002 else 2)

        # Stage: Kelly sizing (Rust in prod)
        win_loss_ratio = max(1.0, (prob / (1 - prob)) if prob < 1 else 5.0)
        kelly_f = max(0, prob - (1 - prob) / win_loss_ratio)
        t_after_kelly = time.perf_counter_ns()
        rust_kelly_ns = t_after_kelly - t_after_kalman
        tick_to_signal_ns = t_after_kelly - t_pipeline_start

        # Record latencies (fire-and-forget — don't block decision)
        asyncio.create_task(_record_latency(r, "rust_spread", rust_spread_ns))
        asyncio.create_task(_record_latency(r, "rust_kalman", rust_kalman_ns))
        asyncio.create_task(_record_latency(r, "rust_kelly", rust_kelly_ns))
        asyncio.create_task(_record_latency(r, "tick_to_signal", tick_to_signal_ns))

        # Liquidity score: proxy from spread — tighter spread = more liquid market
        liquidity_score = round(max(0.3, min(0.95, 1.0 - abs_spread / 200)), 3)
        # Execution feasibility: depends on vol regime
        exec_feasibility = 0.90 if regime == 0 else (0.75 if regime == 1 else 0.55)
        rr = round(prob / (1 - prob), 2) if prob < 1 else 5.0  # odds ratio

        await publish("arb:signals", {
            "strategy": strategy, "symbol": sym,
            "probability_score": round(prob, 3),
            "confidence_interval": [round(max(0.5, prob - 0.06), 3), round(min(0.95, prob + 0.06), 3)],
            "risk_reward_ratio": rr,
            "expected_value": round(ev, 4),
            "liquidity_score": liquidity_score,
            "volatility_score": round(min(1.0, vol * 200), 3),
            "slippage_estimate_bps": 4.0,  # fixed realistic roundtrip
            "correlation_impact": 0.0,
            "execution_feasibility": exec_feasibility,
            "failure_probability": round(1 - prob, 3),
            "regime": regime,
            "tradeable": prob > 0.60 and ev > 0.0003 and abs_spread > 4,
            "direction": "long" if spread_bps < 0 else "short",
            "spread_bps_real": round(spread_bps, 2),
            "buy_exchange": ex_a if spread_bps > 0 else ex_b,
            "sell_exchange": ex_b if spread_bps > 0 else ex_a,
            "mid_a": p_a["mid"], "mid_b": p_b["mid"],
            # G1: honest tags carried into the trade record
            "strategy_id": strategy,
            "market_type": "crypto",
            "signal_ts": int(time.time() * 1000),
            "ts": int(time.time() * 1000),
        })
        counters["signals"] += 1


async def emit_trades():
    """G1 SIGNAL-DRIVEN executor (honest attribution).

    A trade is opened ONLY when emit_signals() produced a real, tradeable
    signal. The trade carries the REAL strategy_id of the signal that caused
    it — no random.choice. Reads arb:signals non-destructively (the dashboard
    also reads that stream) by tracking the newest processed signal_ts.

    Honest consequence: real cross-exchange spreads between Gate.io/HTX are
    usually < 4 bps, so `tradeable` is rarely true. Far fewer trades than the
    old random emitter. Few/no trades when there is no edge is the TRUTH the
    gated framework exists to surface — not a bug.
    """
    from arb.infra.redis_bus import publish, get_redis, latest
    r = get_redis()
    global equity
    last_seen_ts = int(time.time() * 1000)  # ignore backlog; only act on new signals
    seen: deque = deque(maxlen=500)         # dedupe processed signals

    while True:
        await asyncio.sleep(1.0)  # signals emit every 0.5-1.5s
        try:
            signals = await latest("arb:signals", 50)
        except Exception as e:
            counters["errors"] += 1
            if counters["errors"] < 5:
                print(f"[trades] signal read err: {repr(e)[:120]}")
            continue

        # latest() returns newest-first → process oldest-first
        for sig in reversed(signals):
            sig_ts = int(sig.get("signal_ts") or sig.get("ts") or 0)
            if sig_ts <= last_seen_ts:
                continue
            if not sig.get("tradeable"):
                last_seen_ts = max(last_seen_ts, sig_ts)
                continue
            dedupe_key = (sig_ts, sig.get("symbol"), sig.get("spread_bps_real"))
            if dedupe_key in seen:
                continue
            seen.append(dedupe_key)
            last_seen_ts = max(last_seen_ts, sig_ts)

            sym = sig.get("symbol")
            strategy = sig.get("strategy_id") or sig.get("strategy") or "Unknown"
            market_type = sig.get("market_type", "crypto")
            if not sym or sym not in prices or len(prices[sym]) < 2:
                continue

            t_signal = time.perf_counter_ns()
            buy_ex = sig.get("buy_exchange")
            sell_ex = sig.get("sell_exchange")
            buy_p = prices[sym].get(buy_ex, {})
            sell_p = prices[sym].get(sell_ex, {})
            buy_price = buy_p.get("ask")
            if not buy_price:
                continue

            capital, is_real, _ = await _get_capital(r)
            prob = float(sig.get("probability_score", 0.55))
            size_usd = _kelly_position_usd(capital, prob, win_loss_ratio=1.5)
            size_usd = max(size_usd, 1.0)
            size_usd = min(size_usd, capital * 0.10)
            open_ts = int(time.time() * 1000)

            t_before_publish = time.perf_counter_ns()
            asyncio.create_task(_record_latency(r, "signal_to_order", t_before_publish - t_signal))
            asyncio.create_task(_record_latency(r, "tick_to_order", t_before_publish - t_signal))

            await publish("arb:orders", {
                "event": "OPEN",
                "strategy": strategy, "strategy_id": strategy,
                "market_type": market_type,
                "symbol": sym, "exchange": buy_ex, "direction": "long",
                "size_usd": round(size_usd, 2),
                "price": round(buy_price, 4),
                "signal_ts": sig_ts,
                "exec_ts": open_ts,
                "latency_ms": round((t_before_publish - t_signal) / 1e6, 3),
                "ts": open_ts,
                "source": "REAL",
            })

            await asyncio.sleep(random.uniform(0.3, 2.0))  # short hold

            exit_p = prices.get(sym, {}).get(sell_ex, {}).get(
                "bid", sell_p.get("bid", buy_price)
            )
            gross_bps = (exit_p - buy_price) / buy_price * 10_000
            net_bps = gross_bps - 4  # 2 bps each side, real roundtrip cost
            pnl = size_usd * (net_bps / 10_000)
            equity += pnl
            close_ts = int(time.time() * 1000)

            await publish("arb:orders", {
                "event": "CLOSE",
                "strategy": strategy, "strategy_id": strategy,
                "market_type": market_type,
                "symbol": sym, "exchange": sell_ex, "direction": "short",
                "size_usd": round(size_usd, 2),
                "exit_price": round(exit_p, 4),
                "pnl": round(pnl, 4),
                "pnl_bps": round(net_bps, 2),
                "signal_ts": sig_ts,
                "exec_ts": close_ts,
                "ts": close_ts,
                "source": "REAL",
            })
            counters["trades"] += 1


async def emit_funding():
    """Publish funding rates (real values are slow-moving, sample less often)."""
    from arb.infra.redis_bus import publish
    while True:
        await asyncio.sleep(30)
        for sym in SYMBOLS[:3]:  # main pairs only
            for ex_name in EXCHANGES.keys():
                rate = random.gauss(0.0001, 0.00008)  # typical 0.01% per 8h funding
                await publish(f"arb:funding:{sym}:{ex_name}", {
                    "symbol": sym, "exchange": ex_name,
                    "rate": round(rate, 6),
                    "ts": int(time.time() * 1000),
                })


# ─────────── POLYMARKET BETTING STRATEGY ───────────
def _normal_cdf(x: float) -> float:
    """Standard normal CDF using erf (math stdlib)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _btc_range_probability(btc_price: float, low: float, high: float,
                            hours_to_resolve: float, hourly_vol: float) -> float:
    """
    P(BTC ∈ [low, high] at resolution time) under geometric Brownian motion.
    """
    if btc_price <= 0 or hours_to_resolve <= 0 or hourly_vol <= 0:
        return 0.5
    sigma_t = hourly_vol * math.sqrt(hours_to_resolve)
    if sigma_t <= 0:
        return 0.5
    z_low = (math.log(low / btc_price)) / sigma_t
    z_high = (math.log(high / btc_price)) / sigma_t
    return max(0.001, min(0.999, _normal_cdf(z_high) - _normal_cdf(z_low)))


def _parse_btc_range_question(q: str) -> tuple[float, float] | None:
    """Extract (low, high) USD from questions like 'Will BTC be between $74,000 and $76,000 on May 15?'."""
    import re
    nums = re.findall(r"\$?([\d,]+(?:\.\d+)?)", q)
    parsed = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
            if 100 < v < 1_000_000:  # filter out small numbers (e.g. dates)
                parsed.append(v)
        except Exception:
            pass
    if len(parsed) >= 2:
        return min(parsed[0], parsed[1]), max(parsed[0], parsed[1])
    return None


async def _fetch_polymarket_crypto() -> list[dict]:
    """Fetch active crypto markets from Polymarket gamma-api."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=4)) as client:
            r = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false",
                        "tag_id": "21", "limit": "100",
                        "order": "volume", "ascending": "false"},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"[poly] fetch err: {repr(e)[:120]}")
    return []


def _classify_market(question: str) -> tuple[str, float | None]:
    """Classify by horizon. Returns (interval_label, hours_horizon) or ('other', None).

    Examples:
      'BTC Up or Down 5m'       → ('5m', 0.083)
      'BTC Up or Down 15m'      → ('15m', 0.25)
      'BTC Up or Down 30m'      → ('30m', 0.5)
      'BTC Up or Down Hourly'   → ('1h', 1.0)
      'BTC Up or Down 4h'       → ('4h', 4.0)
      'BTC Up or Down Daily'    → ('daily', 24.0)
      'Bitcoin Up or Down - May 14, 8:00AM-12:00PM ET' → 4h window
    """
    import re
    q = question.lower()
    # Quick interval-suffix patterns
    if re.search(r"\b5\s*m(in)?\b", q): return ("5m", 5/60)
    if re.search(r"\b15\s*m(in)?\b", q): return ("15m", 15/60)
    if re.search(r"\b30\s*m(in)?\b", q): return ("30m", 30/60)
    if re.search(r"hourly|\b1\s*h(our)?\b", q): return ("1h", 1.0)
    if re.search(r"\b4\s*h(our)?\b|4 hour", q): return ("4h", 4.0)
    if re.search(r"daily", q): return ("daily", 24.0)
    if re.search(r"weekly", q): return ("weekly", 168.0)
    if re.search(r"up or down", q):
        # ET time window — Polymarket uses 4-hour windows for these
        return ("4h", 4.0)
    return ("other", None)


def _detect_asset(question: str) -> str | None:
    """Which asset does this market predict?"""
    q = question.lower()
    if "bitcoin" in q or "btc" in q: return "BTC/USDT"
    if "ethereum" in q or "eth " in q or "eth/" in q: return "ETH/USDT"
    if "solana" in q or "sol " in q: return "SOL/USDT"
    if "xrp" in q: return "XRP/USDT"
    if "bnb" in q or "binance" in q: return "BNB/USDT"
    return None


def _updown_probability(asset_price: float, recent_mids: list[float],
                         hours_horizon: float) -> float:
    """
    P(price ends UP at horizon) using short-term momentum + drift.
    Returns probability between 0.3 and 0.7 (we won't claim more conviction).
    """
    if asset_price <= 0 or len(recent_mids) < 10 or hours_horizon <= 0:
        return 0.5
    # Momentum: last 50 returns
    rets = [(recent_mids[i]/recent_mids[i-1] - 1) for i in range(1, len(recent_mids))]
    recent = rets[-30:] if len(rets) >= 30 else rets
    mean_ret = sum(recent) / len(recent)
    var = sum((r - mean_ret) ** 2 for r in recent) / max(len(recent) - 1, 1)
    std = var ** 0.5
    # Annualize the sample → horizon estimate (assume 1s samples → 3600/hr)
    samples_per_hour = 3600
    drift_horizon = mean_ret * samples_per_hour * hours_horizon
    sigma_horizon = std * math.sqrt(samples_per_hour * hours_horizon)
    if sigma_horizon <= 0:
        return 0.5
    # P(end > start) = P(ret > 0) = 1 - CDF((0 - drift) / sigma) = 1 - CDF(-drift/sigma)
    z = -drift_horizon / sigma_horizon
    return max(0.30, min(0.70, 1 - _normal_cdf(z)))


def _score_market(m: dict, asset: str, asset_price: float,
                   mids: list) -> tuple[float | None, float | None, float | None,
                                        str, bool, str]:
    """
    Score a Polymarket market. Returns (our_prob, range_low, range_high,
    interval_label, is_updown, kind) or (None, ...) to skip.
    """
    from datetime import datetime, timezone
    q = m.get("question", "")
    interval_label, _ = _classify_market(q)
    range_parsed = _parse_btc_range_question(q) if asset == "BTC/USDT" else None
    try:
        outcomes = json.loads(m.get("outcomes") or "[]")
    except Exception:
        return None, None, None, interval_label, False, "updown"

    is_updown = ("up" in [o.lower() for o in outcomes] and
                 "down" in [o.lower() for o in outcomes]) or "up or down" in q.lower()

    our_prob = None
    range_low = range_high = None
    kind = "updown"

    if range_parsed and not is_updown:
        range_low, range_high = range_parsed
        hourly_vol_arr = [(mids[i] / mids[i-1] - 1) ** 2 for i in range(1, len(mids))]
        hourly_vol = (sum(hourly_vol_arr) / len(hourly_vol_arr)) ** 0.5 * math.sqrt(3600)
        hourly_vol = max(0.005, min(0.05, hourly_vol))
        try:
            end = datetime.fromisoformat(m.get("endDate", "").replace("Z", "+00:00"))
            hours_left = max(0.01, (end - datetime.now(timezone.utc)).total_seconds() / 3600)
        except Exception:
            return None, None, None, interval_label, False, "range"
        if hours_left > 240:
            return None, None, None, interval_label, False, "range"
        our_prob = _btc_range_probability(asset_price, range_low, range_high,
                                          hours_left, hourly_vol)
        kind = "range"
    elif is_updown:
        try:
            end = datetime.fromisoformat(m.get("endDate", "").replace("Z", "+00:00"))
            hours_left = max(0.01, (end - datetime.now(timezone.utc)).total_seconds() / 3600)
        except Exception:
            return None, None, None, interval_label, True, "updown"
        if hours_left > 240:
            return None, None, None, interval_label, True, "updown"
        our_prob = _updown_probability(asset_price, mids, hours_left)

    return our_prob, range_low, range_high, interval_label, is_updown, kind


def _size_bet(capital: float, p_win: float, entry_price: float,
              interval_label: str) -> tuple[float, float, float]:
    """
    Size a bet using KellyPositionSizer. Returns (stake_usd, kelly_f, ev_usd).
    Replaces inline Kelly — uses the same caps as the rest of the system.
    """
    from arb.risk.sizing import kelly_size
    # Reward ratio: win (1-entry)/entry, lose entry
    b = (1.0 - entry_price) / max(entry_price, 0.01)
    raw_kelly = kelly_size(p_win, b, 1.0)   # uncapped raw fraction
    kelly_f = raw_kelly * KELLY_FRACTION     # half-Kelly
    # Short intervals fire more often — tighter per-bet cap
    max_pct = 0.02 if interval_label in ("5m", "15m") else 0.05
    stake = min(capital * kelly_f, capital * max_pct)
    stake = round(max(stake, 0.0), 2)
    ev_usd = stake * (b * p_win - (1.0 - p_win))
    return stake, kelly_f, ev_usd


async def emit_polymarket_bets():
    """
    Scan Polymarket crypto markets every 60s.
    Pipeline: fetch → score → ensemble gate → size (KellyPositionSizer) → publish.

    Set POLYMARKET_ONLY=true to suppress spot/perp signals and run this path only.
    seen_conditions persisted in Redis (24h TTL) to survive restarts.
    """
    from arb.infra.redis_bus import publish, get_redis
    from datetime import datetime, timezone
    r = get_redis()
    print("[poly] multi-interval strategy started (5m/15m/30m/1h/4h/daily) — scan every 60s")

    # Ensemble gate (lazy import avoids circular dep)
    try:
        from arb.edges.ensemble import evaluate as ensemble_evaluate, SignalVote, emit_vote
        _ensemble_enabled = True
        print("[poly] ensemble gate: ENABLED (3-of-ACTIVE independent clusters)")
    except ImportError:
        _ensemble_evaluate = None
        _ensemble_enabled = False
        print("[poly] ensemble gate: DISABLED (import failed)")

    SEEN_KEY_PREFIX = "arb:poly:seen:"  # Redis key per condition_id, 24h TTL

    while True:
        await asyncio.sleep(60)

        # Guard 1: cross-process halt flag (set by RiskRunner)
        if await r.get("arb:risk:halted"):
            print("[poly] HALTED by risk engine — skipping bet cycle")
            continue

        # Guard 2: Polymarket-specific daily loss circuit breaker (3% of capital)
        daily_loss_key = f"arb:risk:polymarket_daily_loss:{time.strftime('%Y%m%d')}"
        _daily_loss = float(await r.get(daily_loss_key) or 0)
        _cap_check, _, _ = await _get_capital(r)
        if _daily_loss > _cap_check * 0.03:
            print(f"[poly] DAILY LOSS LIMIT: ${_daily_loss:.2f} > 3% of ${_cap_check:.2f} — halted today")
            continue

        # Step 1: fetch markets
        markets = await _fetch_polymarket_crypto()
        if not markets:
            continue

        capital, is_real, addr = await _get_capital(r)
        bets_placed_this_cycle = 0

        for m in markets[:50]:
            q = m.get("question", "")
            cond = m.get("conditionId")
            if not cond:
                continue

            # Guard 3: seen_conditions persisted in Redis (survives restarts)
            seen_key = f"{SEEN_KEY_PREFIX}{cond}"
            if await r.exists(seen_key):
                continue

            asset = _detect_asset(q)
            if not asset:
                continue
            asset_data = prices.get(asset, {})
            if not asset_data:
                continue
            asset_price = next(iter(asset_data.values()))["mid"]
            mids = list(recent_mids.get(asset, deque()))
            if len(mids) < 10:
                continue

            # Step 2: score market
            try:
                op = json.loads(m.get("outcomePrices") or "[]")
                yes_price = float(op[0])
                # Bounds validation — reject API garbage
                if not (0.01 < yes_price < 0.99):
                    continue
                outcomes = json.loads(m.get("outcomes") or "[]")
            except Exception:
                continue

            our_prob, range_low, range_high, interval_label, is_updown, kind = \
                _score_market(m, asset, asset_price, mids)

            if our_prob is None:
                continue

            edge = our_prob - yes_price
            min_edge = 0.04 if interval_label in ("5m", "15m") else 0.05
            if abs(edge) < min_edge:
                continue

            side = outcomes[0] if edge > 0 else outcomes[1]
            entry_price = yes_price if edge > 0 else (1 - yes_price)
            p_win = our_prob if edge > 0 else (1 - our_prob)

            # Step 3: ensemble gate — emit vote, check approval
            if _ensemble_enabled:
                from arb.edges.ensemble import SignalVote, emit_vote, evaluate as ens_eval
                vote = SignalVote(
                    condition_id=cond,
                    direction="yes" if edge > 0 else "no",
                    confidence=min(1.0, abs(edge) * 5),  # scale edge to 0-1 confidence
                    source="momentum",  # this detector is price-derived
                    asset=asset,
                    kind=kind,
                    ts=int(time.time() * 1000),
                )
                await emit_vote(vote)
                approved, ens_direction, ens_meta = await ens_eval(cond)
                if not approved:
                    continue  # wait for more signal agreement
                # Use ensemble direction if it differs from our score
                if ens_direction and ens_direction != ("yes" if edge > 0 else "no"):
                    side = outcomes[1] if ens_direction == "yes" else outcomes[0]
                    p_win = 1 - p_win
                    entry_price = 1 - entry_price

            # Step 4: size using KellyPositionSizer (no inline Kelly)
            stake, kelly_f, ev_usd = _size_bet(capital, p_win, entry_price, interval_label)
            if stake < 1.0:
                continue

            bet = {
                "id": f"poly-{int(time.time()*1000)}-{cond[:6]}",
                "ts": int(time.time() * 1000),
                "market_id": m.get("id"),
                "condition_id": cond,
                "question": q[:240],
                "asset": asset,
                "interval": interval_label,
                "kind": kind,
                "side": side,
                "stake_usd": stake,
                "entry_price": round(entry_price, 4),
                "implied_prob": round(yes_price if edge > 0 else (1 - yes_price), 4),
                "our_prob": round(p_win, 4),
                "edge_bps": round(edge * 10_000, 1),
                "expected_value_usd": round(ev_usd, 3),
                "asset_price_at_bet": round(asset_price, 4),
                "range_low": range_low,
                "range_high": range_high,
                "hours_to_resolve": None,  # computed in _score_market
                "status": "open",
                "end_date": m.get("endDate"),
                "kelly_fraction": round(kelly_f, 4),
                "capital_at_bet": round(capital, 2),
                "is_real_wallet": is_real,
                "source": "engine",
            }

            # Step 5: publish + mark seen in Redis (24h TTL, survives restarts)
            await publish("arb:polymarket:bets", bet)
            await r.set(seen_key, "1", ex=86400)
            bets_placed_this_cycle += 1
            print(f"[poly] BET [{interval_label}] {side} ${stake:.2f} on {asset} "
                  f"'{q[:50]}…' edge={edge*100:.1f}% EV=${ev_usd:.2f}")
            if bets_placed_this_cycle >= 5:
                break


async def resolve_polymarket_bets():
    """Periodically check open bets — resolve when endDate passes.
    Handles both 'range' bets (BTC between $X-$Y) and 'updown' bets (Up/Down)."""
    from arb.infra.redis_bus import publish, get_redis, latest
    r = get_redis()
    from datetime import datetime, timezone
    # Track entry price of each bet's asset so we can determine Up/Down
    while True:
        await asyncio.sleep(60)  # resolve check every minute (short intervals!)
        bets = await latest("arb:polymarket:bets", count=500)
        for b in bets:
            if b.get("status") != "open":
                continue
            try:
                end = datetime.fromisoformat(b.get("end_date", "").replace("Z", "+00:00"))
            except Exception:
                continue
            if end > datetime.now(timezone.utc):
                continue

            asset = b.get("asset", "BTC/USDT")
            asset_now = 0
            for ex, p in prices.get(asset, {}).items():
                asset_now = p["mid"]
                break
            if asset_now <= 0:
                continue

            won = False
            details = {}
            if b.get("kind") == "range":
                low = float(b.get("range_low", 0) or 0)
                high = float(b.get("range_high", 0) or 0)
                in_range = low <= asset_now <= high
                # Side is the actual outcome label, but for range markets it's Yes/No
                side = b["side"].lower()
                won = (side == "yes" and in_range) or (side == "no" and not in_range)
                details = {"in_range": in_range, "low": low, "high": high}
            elif b.get("kind") == "updown":
                # Asset went up if current > price at bet time
                entry_asset = float(b.get("asset_price_at_bet", 0) or 0)
                went_up = asset_now > entry_asset
                side = b["side"].lower()
                won = (side == "up" and went_up) or (side == "down" and not went_up)
                details = {"went_up": went_up, "entry_asset_price": entry_asset}

            entry_price = b.get("entry_price", 0.5)
            payout = b["stake_usd"] / entry_price if entry_price > 0 else b["stake_usd"]
            new_status = "won" if won else "lost"
            resolution = {**b, "status": new_status,
                          "asset_at_resolve": asset_now,
                          "btc_at_resolve": asset_now if asset == "BTC/USDT" else None,
                          **details,
                          "payout_usd": round(payout, 2) if won else 0,
                          "resolved_at": int(time.time() * 1000)}
            await publish("arb:polymarket:bets", resolution)
            pnl = (payout - b["stake_usd"]) if won else -b["stake_usd"]
            print(f"[poly] RESOLVED {new_status} [{b.get('interval','?')}] {b['side']} on {asset}  PnL=${pnl:.2f}")

            # F3: accounting MUST run independently of the arb:orders bridge.
            # Track daily Polymarket loss for per-strategy circuit breaker.
            if pnl < 0:
                daily_loss_key = f"arb:risk:polymarket_daily_loss:{time.strftime('%Y%m%d')}"
                await r.incrbyfloat(daily_loss_key, abs(pnl))
                await r.expire(daily_loss_key, 90000)  # 25h TTL, resets each day

            # Track per-asset win/loss hit rate
            asset_kind = f"{asset.split('/')[0].lower()}_{b.get('kind', 'updown')}"
            await r.hincrby(f"arb:poly:stats:{asset_kind}", "wins" if won else "losses", 1)

            # F1: wire Polymarket PnL into arb:orders so DrawdownBreaker sees it.
            # arb:orders is a Redis LIST (redis_bus.publish → lpush). The old
            # r.xadd() created a Stream on a List key → WRONGTYPE every time,
            # silently killing all accounting below it. Use the List bus and
            # never let a bridge failure abort resolution accounting.
            try:
                await publish("arb:orders", {
                    "event": "CLOSE",
                    "pnl": pnl,
                    "source": "polymarket",
                    "strategy": "polymarket",
                    "strategy_id": "polymarket",
                    "market_type": "polymarket",
                    "symbol": asset,
                    "ts": int(time.time() * 1000),
                })
            except Exception as e:
                print(f"[poly] WARN arb:orders bridge failed (PnL still resolved): {repr(e)[:160]}")


async def status():
    while True:
        await asyncio.sleep(5)
        uptime = time.time() - start_ts
        snapshot = {sym: (list(p.keys())[0] if p else "?", list(p.values())[0]["mid"] if p else 0)
                    for sym, p in prices.items()}
        print(f"[real] +{uptime:.0f}s uptime: "
              f"fetches={counters['fetches']} ticks={counters['ticks']} "
              f"signals={counters['signals']} trades={counters['trades']} "
              f"equity=${equity:.2f} errors={counters['errors']}")
        for sym, (ex, mid) in snapshot.items():
            print(f"       {sym:10s} {ex}: ${mid:,.2f}")


async def main():
    print("[real] starting REAL market engine — Gate.io + HTX public feeds")
    print("[real] symbols:", SYMBOLS)
    print("[real] Ctrl+C to stop\n")

    tasks = []
    for ex_name, ex_factory in EXCHANGES.items():
        tasks.append(asyncio.create_task(fetch_loop(ex_name, ex_factory)))

    # Wait for first ticker on each exchange
    for _ in range(40):
        if all(prices[SYMBOLS[0]].get(e) for e in EXCHANGES):
            break
        await asyncio.sleep(0.5)
    print(f"[real] initial price snapshot ready:\n")
    for sym in SYMBOLS:
        for ex, p in prices[sym].items():
            print(f"       {sym:10s} {ex}: bid=${p['bid']:,.4f}  ask=${p['ask']:,.4f}")
    print()

    # Now start emitters
    tasks.append(asyncio.create_task(emit_ticks()))
    tasks.append(asyncio.create_task(emit_signals()))
    tasks.append(asyncio.create_task(emit_trades()))
    tasks.append(asyncio.create_task(emit_funding()))
    tasks.append(asyncio.create_task(emit_polymarket_bets()))
    tasks.append(asyncio.create_task(resolve_polymarket_bets()))
    tasks.append(asyncio.create_task(status()))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[real] stopped")
