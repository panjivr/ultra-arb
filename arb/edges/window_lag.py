"""
Window-lag arbitrage for Polymarket "Up or Down" markets.

THE REAL EDGE (only a bot can do this):
  A market "BTC Up or Down - 8:20AM-8:25AM ET" resolves UP if the price at
  8:25 (close) is higher than at 8:20 (open). Near the END of the window, the
  outcome is largely DECIDED — if BTC is already +0.4% above the open with 30s
  left, it almost certainly resolves Up. But Polymarket's order book may still
  price it 0.55–0.65 because few humans recompute the live delta-vs-open across
  hundreds of simultaneous 5-min windows.

  A bot watching the underlying spot (Gate.io/HTX) computes the live delta vs the
  window-open price and bets the direction that has ALREADY happened, when the
  market lags. This is a genuine, defensible, AI-speed informational edge —
  unlike momentum guessing, which is a coin flip.

How probability is computed:
  - delta = (current_price - window_open_price) / window_open_price
  - time_left fraction of window remaining
  - remaining move needed to flip = -delta (price must reverse past open)
  - P(stays on current side) via Brownian: P(no reversal) given vol & time_left
  - Only bet when our P > market-implied P by a safe margin AND time_left is small
    enough that the move is hard to reverse.
"""
import math
import re
from datetime import datetime, timezone, timedelta


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def parse_window_times(question: str, end_date_iso: str | None = None) -> tuple[float, float] | None:
    """
    Parse window open/close as epoch-ms (UTC) from a title like:
      "Bitcoin Up or Down - June 2, 8:20AM-8:25AM ET"

    ET = America/New_York. June = EDT = UTC-4. (Winter EST = UTC-5; we use the
    end_date if available to anchor the correct UTC date, then apply ET offset.)

    Returns (open_ms, close_ms) or None.
    """
    m = re.search(
        r"(\d{1,2}):(\d{2})\s*(am|pm)\s*[-–]\s*(\d{1,2}):(\d{2})\s*(am|pm)",
        question, re.IGNORECASE,
    )
    if not m:
        return None
    h1, m1, ap1, h2, m2, ap2 = m.groups()

    def _to_h24(h, ap):
        h = int(h) % 12
        if ap.lower() == "pm":
            h += 12
        return h

    oh, om = _to_h24(h1, ap1), int(m1)
    ch, cm = _to_h24(h2, ap2), int(m2)

    # Anchor the date. Prefer the market's end_date (authoritative UTC).
    base_date = None
    if end_date_iso:
        try:
            base_date = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        except Exception:
            base_date = None
    if base_date is None:
        base_date = datetime.now(timezone.utc)

    # ET offset: EDT (Mar–Nov) = -4, EST = -5. Approximate by month.
    et_offset = -4 if 3 <= base_date.month <= 11 else -5

    # The close time in the title is ET; convert to UTC.
    # Build a UTC datetime for close on base_date's calendar day, then fix if the
    # title close hour disagrees (handles day-boundary crossings).
    day = base_date.date()
    close_utc = datetime(day.year, day.month, day.day, ch, cm, tzinfo=timezone.utc) - timedelta(hours=et_offset)
    open_utc = datetime(day.year, day.month, day.day, oh, om, tzinfo=timezone.utc) - timedelta(hours=et_offset)
    # If close < open (e.g. window crosses midnight), push close +1 day
    if close_utc <= open_utc:
        close_utc += timedelta(days=1)
    # If our computed close is wildly off from end_date (>2h), trust end_date for close
    if end_date_iso and base_date:
        if abs((close_utc - base_date).total_seconds()) > 7200:
            close_utc = base_date
            # recompute open as close - window_duration
            dur_min = (ch * 60 + cm) - (oh * 60 + om)
            if dur_min <= 0:
                dur_min += 24 * 60
            open_utc = close_utc - timedelta(minutes=dur_min)

    return open_utc.timestamp() * 1000, close_utc.timestamp() * 1000


def price_at(history: list, target_ms: float) -> float | None:
    """Find the mid price in history closest to target_ms (within 30s tolerance)."""
    if not history:
        return None
    best = None
    best_dt = None
    for ts, mid in history:
        dt = abs(ts - target_ms)
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = mid
    # Only trust if within 30 seconds of the target
    if best_dt is not None and best_dt <= 30_000:
        return best
    return None


def window_lag_signal(
    history: list,
    question: str,
    end_date_iso: str | None,
    current_mid: float,
    now_ms: float,
    hourly_vol: float,
    outcomes: list[str],
) -> dict | None:
    """
    Compute a directional probability from the live delta vs window-open price.

    Returns {direction, side, p_win, delta_pct, time_left_s, reason} or None.

    Gates:
      - Must be inside the window
      - time_left must be < 60% of window (we want the move to have happened)
      - |delta| must be meaningful relative to remaining-time vol
      - P(stay) must be high (> 0.62) to bet
    """
    times = parse_window_times(question, end_date_iso)
    if not times:
        return None
    open_ms, close_ms = times
    window_dur_s = (close_ms - open_ms) / 1000.0
    if window_dur_s <= 0 or window_dur_s > 4 * 3600 + 60:
        return None

    # Must be inside the window
    if now_ms < open_ms or now_ms >= close_ms:
        return None

    time_left_s = (close_ms - now_ms) / 1000.0
    elapsed_frac = 1.0 - (time_left_s / window_dur_s)
    # We want the window to be mostly over so the move is hard to reverse.
    # Require at least 40% elapsed.
    if elapsed_frac < 0.40:
        return None

    open_price = price_at(history, open_ms)
    if open_price is None or open_price <= 0:
        return None

    delta = (current_mid - open_price) / open_price
    if delta == 0:
        return None

    # Remaining-window volatility (std of return over time_left).
    # hourly_vol is per-hour σ; scale to time_left.
    sigma_remaining = hourly_vol * math.sqrt(max(time_left_s, 1) / 3600.0)
    if sigma_remaining <= 0:
        return None

    # For the side to FLIP, the return over the rest of the window must move past
    # -delta (i.e. erase the current lead). P(flip) = P(remaining_return < -delta)
    # if currently up, = Φ(-delta / sigma_remaining) ... but reversal is symmetric.
    # P(stay on current side) = 1 - P(cross back past open).
    z = abs(delta) / sigma_remaining
    p_stay = _normal_cdf(z)  # prob the move is NOT erased

    # Only bet with meaningful conviction
    if p_stay < 0.62:
        return None

    # Determine side: if currently UP vs open → bet "Up"; else "Down"
    outcomes_low = [o.lower() for o in outcomes]
    if "up" not in outcomes_low or "down" not in outcomes_low:
        return None
    up_idx = outcomes_low.index("up")
    down_idx = outcomes_low.index("down")

    if delta > 0:
        side = outcomes[up_idx]
        direction = "up"
    else:
        side = outcomes[down_idx]
        direction = "down"

    # Cap conviction — never claim >0.90 (orderbook/slippage/edge cases)
    p_win = min(0.90, p_stay)

    return {
        "direction": direction,
        "side": side,
        "p_win": round(p_win, 4),
        "delta_pct": round(delta * 100, 4),
        "time_left_s": round(time_left_s, 1),
        "elapsed_frac": round(elapsed_frac, 3),
        "z_score": round(z, 2),
        "open_price": round(open_price, 4),
        "current_price": round(current_mid, 4),
        "reason": f"delta={delta*100:+.3f}% with {time_left_s:.0f}s left, z={z:.1f}",
    }
