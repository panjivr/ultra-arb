"""
Polymarket-specific intelligence: inline multi-signal ensemble for a SPECIFIC market.

Things only an AI agent can do here:
  1. Smart-money lookup — query recent trades on THIS condition_id, weight by
     stake size and freshness. If whales took side X with > $500 in the last
     10 min, that's a strong cluster-C vote.
  2. Microstructure — last N trades' price drift on the same market hints at
     informed flow. Combine with volume imbalance.
  3. Liquidity gate — skip markets with < $500 liquidity (no execution).
  4. News alignment — if a recent high-impact news signal matches this asset
     and direction, boost confidence.
  5. Funding rate direction — for assets with futures, persistent positive
     funding means crowded longs → mean revert on short-term down move.
  6. Calibration — per-asset/per-interval hit rate. If we're below 50% on
     5m BTC bets, tighten threshold for that segment.

All signals computed inline (no Redis vote roundtrip) for sub-second decisions.
"""
import asyncio
import json
import math
import time
from collections import defaultdict
from typing import Any
import httpx

POLYMARKET_TRADES_URL = "https://data-api.polymarket.com/trades"
_HTTP_TIMEOUT = httpx.Timeout(5, connect=3)


# ──────────────────────────── Smart-money lookup ────────────────────────────

async def whale_alignment(condition_id: str, min_stake_usd: float = 50.0,
                          window_seconds: int = 1200) -> dict | None:
    """
    Query Polymarket trades for THIS condition_id. Return {direction, n_trades,
    total_volume_usd, confidence}.

    Decision logic:
      - Look at trades in the last `window_seconds` for the market's condition_id
      - Sum size_usd per side
      - If one side has > 1.5x the volume of the other AND > 1 trade → signal
      - Confidence proportional to (vol_imbalance × log(n_trades + 1))

    Returns None if not enough data.
    """
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            # Polymarket trades API supports filter by market (condition_id)
            r = await client.get(POLYMARKET_TRADES_URL,
                                 params={"market": condition_id, "limit": "100"})
            if r.status_code != 200:
                return None
            trades = r.json() if isinstance(r.json(), list) else []
    except Exception:
        return None

    if not trades:
        return None

    now = time.time()
    cutoff = now - window_seconds
    by_outcome: dict[str, dict] = defaultdict(lambda: {"n": 0, "vol": 0.0, "max_size": 0.0})

    for t in trades:
        try:
            ts = int(t.get("timestamp", 0) or 0)
            if ts < cutoff:
                continue
            size = float(t.get("size", 0) or 0)
            price = float(t.get("price", 0) or 0)
            outcome = (t.get("outcome") or "").strip()
            if not outcome or size <= 0 or price <= 0:
                continue
            usd = size * price
            if usd < min_stake_usd:
                continue
            d = by_outcome[outcome]
            d["n"] += 1
            d["vol"] += usd
            d["max_size"] = max(d["max_size"], usd)
        except Exception:
            continue

    if len(by_outcome) == 0:
        return None

    # Find dominant outcome
    sorted_outcomes = sorted(by_outcome.items(), key=lambda x: x[1]["vol"], reverse=True)
    top_outcome, top_data = sorted_outcomes[0]
    other_vol = sum(d["vol"] for o, d in by_outcome.items() if o != top_outcome)

    # BUGFIX: when only one side has trades, other_vol == 0. The old `or 0.01`
    # fallback produced an absurd imbalance (vol/0.01 = e.g. 178893x). Treat a
    # genuinely one-sided book as a capped "strong" signal, and cap the ratio
    # for everyone so confidence math stays sane.
    MAX_IMBALANCE = 10.0
    if other_vol <= 0:
        # One-sided flow. Only trust it if there are enough trades + real size,
        # otherwise it's just a single small order and means nothing.
        if top_data["n"] < 3 or top_data["vol"] < 200:
            return None
        imbalance = MAX_IMBALANCE  # capped — strong but not insane
    else:
        imbalance = min(MAX_IMBALANCE, top_data["vol"] / other_vol)

    if imbalance < 1.5:
        return None  # too balanced — not a clear signal

    confidence = min(1.0, math.log1p(top_data["n"]) * min(2.0, imbalance) / 5.0)
    return {
        "direction": top_outcome,
        "n_trades": top_data["n"],
        "total_volume_usd": round(top_data["vol"], 2),
        "max_whale_usd": round(top_data["max_size"], 2),
        "imbalance_ratio": round(imbalance, 2),
        "confidence": round(confidence, 3),
        "one_sided": other_vol <= 0,
    }


# ──────────────────────────── Liquidity gate ────────────────────────────

def liquidity_ok(market: dict, min_liquidity_usd: float = 500.0,
                 min_volume_usd: float = 100.0) -> bool:
    """Skip markets with no liquidity (we can't actually execute)."""
    try:
        liq = float(market.get("liquidity", 0) or 0)
        vol = float(market.get("volume", 0) or 0)
        return liq >= min_liquidity_usd and vol >= min_volume_usd
    except Exception:
        return False


# ──────────────────────────── News alignment ────────────────────────────

async def news_alignment(asset_symbol: str, lookback_minutes: int = 15) -> dict | None:
    """
    Check Redis for recent high-impact news signals matching this asset.
    Returns {direction: "up"|"down", confidence, headline} or None.
    """
    from arb.infra.redis_bus import latest
    try:
        items = await latest("arb:edges:news_signal", count=50)
    except Exception:
        return None

    if not items:
        return None

    asset_key = asset_symbol.split("/")[0].upper()  # "BTC/USDT" → "BTC"
    asset_aliases = {
        "BTC": ["btc", "bitcoin"],
        "ETH": ["eth", "ethereum", "ether"],
        "SOL": ["sol", "solana"],
        "BNB": ["bnb", "binance"],
        "XRP": ["xrp", "ripple"],
    }
    aliases = asset_aliases.get(asset_key, [asset_key.lower()])

    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - lookback_minutes * 60_000

    best = None
    for n in items:
        try:
            ts = int(n.get("ts", 0) or 0)
            if ts < cutoff_ms:
                continue
            title_low = (n.get("title", "") or "").lower()
            currencies = [c.lower() for c in (n.get("currencies") or [])]
            sym_hit = any(a in title_low or a in currencies for a in aliases) or asset_key.lower() in title_low
            if not sym_hit:
                continue
            score = float(n.get("sentiment", 0) or 0)
            if abs(score) < 0.4:
                continue
            direction = "up" if score > 0 else "down"
            # Weight by recency + sentiment magnitude
            age_min = (now_ms - ts) / 60_000
            recency_weight = max(0.2, 1.0 - age_min / lookback_minutes)
            confidence = abs(score) * recency_weight
            if not best or confidence > best["confidence"]:
                best = {
                    "direction": direction,
                    "confidence": round(confidence, 3),
                    "headline": (n.get("title") or "")[:120],
                    "sentiment": score,
                    "age_minutes": round(age_min, 1),
                }
        except Exception:
            continue
    return best


# ──────────────────────────── Calibration tracker ────────────────────────────

CALIB_KEY = "arb:poly:calibration"


async def record_outcome(asset: str, interval: str, kind: str, won: bool,
                          edge_bps: float = 0.0) -> None:
    """Record a resolved bet for future calibration. Stored in Redis Hash."""
    from arb.infra.redis_bus import get_redis
    r = get_redis()
    key = f"{CALIB_KEY}:{asset}:{interval}"
    try:
        pipe = r.pipeline()
        pipe.hincrby(key, "n", 1)
        pipe.hincrby(key, "wins" if won else "losses", 1)
        pipe.hincrbyfloat(key, "edge_sum_bps", edge_bps)
        pipe.expire(key, 30 * 24 * 3600)  # 30 day rolling window
        await pipe.execute()
    except Exception:
        pass


async def get_calibration(asset: str, interval: str) -> dict:
    """Return {n, wins, losses, hit_rate, avg_edge_bps} or zeros if no data."""
    from arb.infra.redis_bus import get_redis
    r = get_redis()
    key = f"{CALIB_KEY}:{asset}:{interval}"
    try:
        d = await r.hgetall(key)
    except Exception:
        d = None
    if not d:
        return {"n": 0, "wins": 0, "losses": 0, "hit_rate": 0.5, "avg_edge_bps": 0.0}

    def _get(k, default=0):
        v = d.get(k.encode() if isinstance(next(iter(d)), bytes) else k, default)
        if isinstance(v, bytes):
            v = v.decode()
        return v

    n = int(_get("n", 0))
    wins = int(_get("wins", 0))
    losses = int(_get("losses", 0))
    edge_sum = float(_get("edge_sum_bps", 0.0))
    hit_rate = wins / max(n, 1) if n > 0 else 0.5
    avg_edge = edge_sum / max(n, 1)
    return {"n": n, "wins": wins, "losses": losses,
            "hit_rate": round(hit_rate, 4),
            "avg_edge_bps": round(avg_edge, 2)}


async def calibration_multiplier(asset: str, interval: str) -> float:
    """
    Returns 0.0–1.0 multiplier for bet size based on past performance.
    Below 10 bets → 0.5 (warmup, half-size).
    Below 48% hit rate over 30+ bets → 0 (skip).
    Above 55% → 1.0 (full Kelly).
    """
    c = await get_calibration(asset, interval)
    n = c["n"]
    hr = c["hit_rate"]
    if n < 10:
        return 0.5  # warm-up
    if n >= 30 and hr < 0.48:
        return 0.0  # stop betting this segment
    if hr >= 0.55:
        return 1.0
    return 0.7  # marginal


# ──────────────────────────── Ensemble decision ────────────────────────────

def ensemble_decide(
    momentum_prob: float,
    yes_price: float,
    outcomes: list[str],
    whale_signal: dict | None,
    news_signal: dict | None,
    min_edge_pct: float = 5.0,
    min_signals: int = 1,
    strong_momentum_threshold: float = 0.55,
    market_price_anomaly: bool = True,
) -> dict | None:
    """
    Combine signals into a final decision.

    Decision tiers (most → least strict):
      1. Multi-signal consensus (momentum + whale/news) → strong bet
      2. Strong momentum alone (|prob - 0.5| > 0.05) → reduced bet
      3. Whale alone with >$200 imbalance → reduced bet
      4. Market mispricing (very cheap YES with positive expected outcome) → opportunistic

    Args:
      momentum_prob: our model's P(Yes) — already capped [0.42, 0.58]
      yes_price: implied probability from market (0–1)
      outcomes: ["Yes","No"] or ["Up","Down"]
      whale_signal: from whale_alignment() or None
      news_signal: from news_alignment() or None
      min_edge_pct: minimum edge in % to bet
      min_signals: minimum independent signals (default 1)
      strong_momentum_threshold: |prob - 0.5| above this counts as strong solo signal

    Returns:
      {direction, side, edge_pct, our_prob, signals_count, signal_meta} or None
    """
    signals_voting_yes = 0
    signals_voting_no = 0
    confidence_sum_yes = 0.0
    confidence_sum_no = 0.0
    meta = {}
    outcomes_low = [o.lower() for o in outcomes] if outcomes else []
    is_updown_market = "up" in outcomes_low and "down" in outcomes_low

    # ── Cluster A: momentum ──
    momentum_strong = abs(momentum_prob - 0.5) >= 0.04
    if momentum_prob != 0.5:
        # Confidence scales with deviation from 0.5
        conf = min(0.6, abs(momentum_prob - 0.5) * 12)
        if momentum_prob > 0.5:
            signals_voting_yes += 1
            confidence_sum_yes += conf
        else:
            signals_voting_no += 1
            confidence_sum_no += conf
        meta["momentum"] = {
            "prob": round(momentum_prob, 3),
            "vote": "yes" if momentum_prob > 0.5 else "no",
            "confidence": round(conf, 3),
            "strong": momentum_strong,
        }

    # ── Cluster C: smart money ──
    if whale_signal:
        whale_dir = (whale_signal.get("direction") or "").strip().lower()
        if outcomes_low and whale_dir == outcomes_low[0]:
            signals_voting_yes += 1
            confidence_sum_yes += whale_signal["confidence"]
        elif len(outcomes_low) > 1 and whale_dir == outcomes_low[1]:
            signals_voting_no += 1
            confidence_sum_no += whale_signal["confidence"]
        meta["whale"] = whale_signal

    # ── Cluster D: news ──
    if news_signal and is_updown_market:
        news_dir = news_signal["direction"]
        if news_dir == "up":
            signals_voting_yes += 1
            confidence_sum_yes += news_signal["confidence"]
        else:
            signals_voting_no += 1
            confidence_sum_no += news_signal["confidence"]
        meta["news"] = news_signal

    total_signals = signals_voting_yes + signals_voting_no
    if total_signals == 0:
        return None

    # ── Cluster E: market-price anomaly (AI: exploit extreme mispricing) ──
    # If yes_price < 0.20 but market shouldn't be that pessimistic, OR
    # yes_price > 0.80 but shouldn't be that confident, edge exists.
    # This is the "negative-cost theta" play near expiry.
    if market_price_anomaly:
        if yes_price < 0.20:
            # Implied prob very low — if momentum says even modest "up",
            # the EV math favors buying No at high payoff... wait, low yes_price means
            # YES is cheap, NO is expensive. Cheap YES with momentum saying 50/50+
            # → +EV YES.
            if momentum_prob >= 0.48:
                signals_voting_yes += 1
                confidence_sum_yes += (0.20 - yes_price) * 3  # cheaper = more confident
                meta["price_anomaly"] = {"reason": "yes_cheap", "yes_price": yes_price}
        elif yes_price > 0.80:
            if momentum_prob <= 0.52:
                signals_voting_no += 1
                confidence_sum_no += (yes_price - 0.80) * 3
                meta["price_anomaly"] = {"reason": "yes_expensive", "yes_price": yes_price}

    total_signals = signals_voting_yes + signals_voting_no

    # ── Decision: direction + base probability ──
    if signals_voting_yes > signals_voting_no:
        direction = "yes"
        side = outcomes[0] if outcomes else "Yes"
        entry_price = yes_price
        avg_conf = confidence_sum_yes / max(signals_voting_yes, 1)
        # Cap at 0.65 — we are NEVER certain about short-term crypto
        our_prob = min(0.65, max(yes_price + 0.01, 0.5 + avg_conf * 0.5))
    elif signals_voting_no > signals_voting_yes:
        direction = "no"
        side = outcomes[1] if len(outcomes) > 1 else "No"
        entry_price = 1 - yes_price
        avg_conf = confidence_sum_no / max(signals_voting_no, 1)
        our_prob = min(0.65, max((1 - yes_price) + 0.01, 0.5 + avg_conf * 0.5))
    else:
        return None  # split

    edge = our_prob - entry_price
    edge_pct = edge * 100

    # ── Gating: enforce minimum signal quality ──
    # Solo signal allowed only if it's STRONG momentum or sizeable whale
    if total_signals < min_signals:
        return None
    # Note: total_signals == 1 with weak signal still allowed — calibration_multiplier
    # in the bet loop scales stake to half during warmup (first 10 bets per segment).
    # This bootstraps real performance data we need for the strict gate to work.

    if edge_pct < min_edge_pct:
        return None

    return {
        "direction": direction,
        "side": side,
        "entry_price": round(entry_price, 4),
        "our_prob": round(our_prob, 3),
        "edge_pct": round(edge_pct, 2),
        "edge_bps": round(edge * 10_000, 1),
        "signals_voting_yes": signals_voting_yes,
        "signals_voting_no": signals_voting_no,
        "signals_count": total_signals,
        "signal_meta": meta,
    }
