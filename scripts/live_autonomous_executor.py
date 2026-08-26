#!/usr/bin/env python3
"""
Autonomous LIVE Polymarket executor — places REAL money orders from the engine's
signal stream (arb:polymarket:bets), behind layered, code-enforced guards.

╔══════════════════════════════════════════════════════════════════════════════╗
║  DEFAULT-SAFE. It places NOTHING unless EVERY gate below is satisfied:        ║
║    1. env PAPER_TRADE=false                                                   ║
║    2. env POLYMARKET_PRIVATE_KEY (or POLY_PRIVATE_KEY) + POLY_WALLET_ADDRESS  ║
║    3. Redis arb:mode == "real"        (dashboard toggle)                      ║
║    4. Redis arb:live:autonomous_armed present  (explicit arm, auto-expires)   ║
║    5. Kill-switch arb:live:halted NOT set                                     ║
║  Miss any one → STANDBY: it only logs what it *would* do, and places nothing. ║
╚══════════════════════════════════════════════════════════════════════════════╝

Every individual order additionally passes run_all_checks() (kill-switch, daily
cap, per-bet cap, REAL market-open window, wallet balance, friction) AND the
executor's own caps: a lifetime TOTAL cap, max open positions, one position per
market, a rate limit, and a minimum edge. Losses feed the kill-switch, which
auto-halts on the daily-loss / consecutive-loss thresholds.

Arm / disarm / status (run wherever you can reach Redis):
    python3 scripts/live_autonomous_executor.py arm 6h
    python3 scripts/live_autonomous_executor.py disarm
    python3 scripts/live_autonomous_executor.py status
    python3 scripts/live_autonomous_executor.py run        # the loop (container)

The arm flag AUTO-EXPIRES (default 6h) — a dead-man's switch, so autonomous
trading never runs forgotten. Re-arm to continue.
"""
import os
import sys
import time
from datetime import datetime, timezone

# ── Load .env (host runs) without overriding real env ─────────────────────────
_env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis as _redis  # sync client — the adapter + safety modules are sync

# Make the sync safety modules talk to the same Redis we do (redis-py, in-container).
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LIVE_SAFETY_REDIS_URL", REDIS_URL)

# ── Keys ──────────────────────────────────────────────────────────────────────
BETS_KEY = "arb:polymarket:bets"
ARMED_KEY = "arb:live:autonomous_armed"
EXECUTED_KEY = "arb:live:executed"            # Set of bet ids we've ACTED ON (incl. skips) — dedup only
PLACED_KEY = "arb:live:placed"                # Set of bet ids we ACTUALLY placed on-chain — feeds loss/PnL
OPEN_CONDITIONS_KEY = "arb:live:open_conditions"  # Set of condition_ids with an open live position
OPEN_COUNT_KEY = "arb:live:open_count"
TOTAL_SPEND_KEY = "arb:live:total_spend"
LAST_BET_TS_KEY = "arb:live:last_bet_ts"
RESOLVED_SEEN_KEY = "arb:live:resolved_seen"  # executed bet ids already fed to kill-switch

# ── Caps (env can LOWER; a hard ceiling stops any config raising them) ─────────
def _capped(env_name: str, default: float, hard_ceiling: float) -> float:
    try:
        v = float(os.environ.get(env_name, default))
    except ValueError:
        v = default
    return max(0.0, min(v, hard_ceiling))

TOTAL_CAP_USD = _capped("LIVE_TOTAL_CAP_USD", 25.0, 100.0)   # lifetime deployment ceiling
MAX_OPEN_POSITIONS = int(_capped("LIVE_MAX_OPEN", 5, 20))
MIN_SECONDS_BETWEEN_BETS = int(_capped("LIVE_MIN_GAP_SEC", 30, 3600))
MIN_EDGE_BPS = _capped("LIVE_MIN_EDGE_BPS", 500.0, 5000.0)   # only act on ≥5% edge by default
MIN_CONVICTION = _capped("LIVE_MIN_CONVICTION", 0.60, 1.0)   # copy-trade path qualifies by conviction
MAX_SIGNAL_AGE_SEC = int(_capped("LIVE_MAX_SIGNAL_AGE_SEC", 120, 3600))
MIN_ORDER_USD = 1.0
POLL_SECONDS = int(_capped("LIVE_POLL_SEC", 8, 120))
ARM_DEFAULT_TTL_SEC = 6 * 3600

_rc = _redis.from_url(REDIS_URL, decode_responses=True)


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Arm / gate ────────────────────────────────────────────────────────────────
def _env_live_ready() -> tuple[bool, str]:
    if os.environ.get("PAPER_TRADE", "true").strip().lower() != "false":
        return False, "PAPER_TRADE is not false"
    if not (os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("POLY_PRIVATE_KEY")):
        return False, "no POLYMARKET_PRIVATE_KEY"
    if not os.environ.get("POLY_WALLET_ADDRESS"):
        return False, "no POLY_WALLET_ADDRESS"
    return True, "env live-ready"


def _gates() -> tuple[bool, str]:
    ok, why = _env_live_ready()
    if not ok:
        return False, why
    if (_rc.get("arb:mode") or "demo") != "real":
        return False, "arb:mode != real"
    if not _rc.get(ARMED_KEY):
        return False, "not armed (arb:live:autonomous_armed)"
    from scripts.live_kill_switch import is_halted, get_halt_reason
    if is_halted():
        return False, f"kill-switch: {get_halt_reason()}"
    return True, "ALL GATES OPEN"


def _parse_ttl(s: str) -> int:
    s = (s or "").strip().lower()
    try:
        if s.endswith("h"):
            return int(float(s[:-1]) * 3600)
        if s.endswith("m"):
            return int(float(s[:-1]) * 60)
        if s.endswith("s"):
            return int(float(s[:-1]))
        return int(float(s))
    except ValueError:
        return ARM_DEFAULT_TTL_SEC


# ── Order sizing / market resolution ──────────────────────────────────────────
_YES_LIKE = {"yes", "up", "over", "true", "long", "buy"}
_NO_LIKE = {"no", "down", "under", "false", "short", "sell"}


def _side_class(s: str) -> str:
    """Normalise an outcome/side to yes|no so copy-trade YES/NO matches an
    Up/Down market's tokens (the leader's original label was lost to YES/NO)."""
    s = (s or "").strip().lower()
    if s in _YES_LIKE:
        return "yes"
    if s in _NO_LIKE:
        return "no"
    return s


def _pick_token(market: dict, side: str):
    """Return (token_id, best_ask, end_date_iso) for the bet's outcome, or None."""
    from scripts.polymarket_live_adapter import get_market_details
    cond = market.get("condition_id")
    md = get_market_details(cond)
    if not isinstance(md, dict) or md.get("error"):
        return None
    want = _side_class(side)
    obooks = md.get("order_books", {})
    end_iso = md.get("end_date_iso") or market.get("end_date") or ""
    for tok in md.get("tokens", []):
        outcome = str(tok.get("outcome", "")).strip().lower()
        if _side_class(outcome) != want:
            continue
        ob = obooks.get(tok.get("outcome")) or obooks.get(outcome) or {}
        best_ask = ob.get("best_ask")
        return tok.get("token_id"), best_ask, end_iso
    return None


def _act_on_bet(bet: dict) -> str:
    """Evaluate one bet and, if every guard passes, place a REAL order.
    Returns a short status string. Marks the bet id executed BEFORE placing so a
    crash can never double-place (we would rather miss a bet than repeat one).
    """
    from scripts.polymarket_live_adapter import check_wallet_balance, calculate_friction, place_live_order
    from scripts.live_safety_checks import run_all_checks, record_live_bet, MAX_BET_USD
    from scripts.live_kill_switch import set_halt, check_balance_halt

    bet_id = bet.get("id")
    cond = bet.get("condition_id")
    side = bet.get("side")
    if not bet_id or not cond or not side:
        return "skip: incomplete bet"
    if _rc.sismember(EXECUTED_KEY, bet_id):
        return ""  # already handled

    # Stale / weak signals are dropped (and marked, so we don't chase them).
    age_ms = _now_ms() - int(bet.get("ts", 0) or 0)
    if age_ms > MAX_SIGNAL_AGE_SEC * 1000:
        _rc.sadd(EXECUTED_KEY, bet_id)
        return "skip: stale signal"
    # Qualify by edge (engine window-lag/whale bets) OR conviction (copy-trade
    # bets carry `conviction`, not `edge_bps`). Either clears the quality bar.
    edge_bps = float(bet.get("edge_bps", 0) or 0)
    conviction = float(bet.get("conviction", 0) or 0)
    if edge_bps < MIN_EDGE_BPS and conviction < MIN_CONVICTION:
        _rc.sadd(EXECUTED_KEY, bet_id)
        return f"skip: edge {edge_bps:.0f}bps / conv {conviction:.2f} below floor"

    # One live position per market.
    if _rc.sismember(OPEN_CONDITIONS_KEY, cond):
        _rc.sadd(EXECUTED_KEY, bet_id)
        return "skip: already have a live position on this market"

    # Portfolio caps.
    if int(_rc.get(OPEN_COUNT_KEY) or 0) >= MAX_OPEN_POSITIONS:
        return "hold: max open positions reached"
    last_ts = float(_rc.get(LAST_BET_TS_KEY) or 0)
    if time.time() - last_ts < MIN_SECONDS_BETWEEN_BETS:
        return "hold: rate limit"

    # Size (never exceed the per-bet cap; the checks enforce it too).
    stake = min(float(bet.get("stake_usd", 0) or 0), MAX_BET_USD)
    if stake < MIN_ORDER_USD:
        _rc.sadd(EXECUTED_KEY, bet_id)
        return f"skip: stake ${stake:.2f} < ${MIN_ORDER_USD:.2f} min"

    # Total lifetime cap.
    total = float(_rc.get(TOTAL_SPEND_KEY) or 0)
    if total + stake > TOTAL_CAP_USD:
        set_halt(f"Auto-halt: total live spend ${total:.2f}+${stake:.2f} > cap ${TOTAL_CAP_USD:.2f}")
        return "HALT: total cap reached"

    picked = _pick_token(bet, side)
    if not picked or not picked[0] or not picked[1]:
        _rc.sadd(EXECUTED_KEY, bet_id)
        return "skip: no token/order-book for side"
    token_id, best_ask, end_iso = picked
    price = round(float(best_ask), 2)
    if not (0.02 <= price <= 0.98):
        _rc.sadd(EXECUTED_KEY, bet_id)
        return f"skip: price {price} out of range"
    shares = round(stake / price, 2)
    cost = round(price * shares, 4)
    if cost < MIN_ORDER_USD:
        _rc.sadd(EXECUTED_KEY, bet_id)
        return f"skip: cost ${cost:.2f} < min"

    # Balance + friction + the full pre-flight, now with the REAL market window.
    try:
        bal = check_wallet_balance()
    except Exception as e:
        return f"hold: balance check error {repr(e)[:80]}"
    balance_usdc = float(bal.get("balance_usdc", 0) or 0)
    relay_mode = bool(bal.get("relay_mode", False))
    if check_balance_halt(balance_usdc):
        return "HALT: balance floor"
    try:
        fr = calculate_friction(token_id, "BUY", cost)
        friction_pct = fr.get("total_friction_pct")
    except Exception:
        friction_pct = None

    all_ok, results = run_all_checks(cost, end_iso, balance_usdc, friction_pct, relay_mode=relay_mode)
    if not all_ok:
        fails = "; ".join(r["reason"] for r in results if not r["passed"])
        _rc.sadd(EXECUTED_KEY, bet_id)  # a bet that fails checks now won't pass later
        return f"skip (checks): {fails}"

    # ── Commit: mark executed BEFORE submitting (idempotent against crashes) ──
    _rc.sadd(EXECUTED_KEY, bet_id)
    try:
        res = place_live_order(token_id, "BUY", price, shares, dry_run=False)
    except Exception as e:
        return f"ERROR placing: {repr(e)[:120]}"

    order_id = res.get("order_id", "")
    record_live_bet(order_id, cost, meta={
        "bet_id": bet_id, "condition_id": cond, "side": side,
        "token_id": token_id, "price": price, "shares": shares,
        "source": bet.get("source"), "edge_bps": bet.get("edge_bps"),
    })
    _rc.sadd(PLACED_KEY, bet_id)  # ONLY real placements — the loss monitor keys off this
    _rc.incrbyfloat(TOTAL_SPEND_KEY, cost)
    _rc.incr(OPEN_COUNT_KEY)
    _rc.sadd(OPEN_CONDITIONS_KEY, cond)
    _rc.set(LAST_BET_TS_KEY, time.time())
    return f"✅ PLACED {side} {shares}@{price} = ${cost:.2f} on {cond[:10]} (order {order_id})"


def _loss_monitor():
    """Feed resolved live bets into the kill-switch and free their position slot."""
    from scripts.live_kill_switch import record_loss, record_win
    try:
        raw = _rc.lrange(BETS_KEY, 0, 400)
    except Exception:
        return
    import json
    for item in raw:
        try:
            b = json.loads(item)
        except Exception:
            continue
        status = b.get("status")
        bet_id = b.get("bet_id") or b.get("id")
        if status not in ("won", "lost") or not bet_id:
            continue
        # Only bets we ACTUALLY placed on-chain, once each. The EXECUTED set
        # also holds skipped signals; counting those as real losses is what
        # false-tripped the daily-loss auto-halt on demo/paper PnL.
        if not _rc.sismember(PLACED_KEY, bet_id):
            continue
        if _rc.sismember(RESOLVED_SEEN_KEY, bet_id):
            continue
        _rc.sadd(RESOLVED_SEEN_KEY, bet_id)
        # Free the position slot (never below zero).
        try:
            if int(_rc.get(OPEN_COUNT_KEY) or 0) > 0:
                _rc.decr(OPEN_COUNT_KEY)
        except Exception:
            pass
        cond = b.get("condition_id")
        if cond:
            _rc.srem(OPEN_CONDITIONS_KEY, cond)
        if status == "lost":
            loss = abs(float(b.get("stake_usd", 0) or 0))
            out = record_loss(loss)
            if out.get("halted"):
                print(f"[live-exec] 🔴 {out['reason']}")
        else:
            record_win()


def run_loop():
    import json
    print("=" * 70)
    print("  AUTONOMOUS LIVE EXECUTOR")
    print(f"  caps: bet≤${_safe_max_bet():.2f}/day≤${_safe_daily():.2f}/total≤${TOTAL_CAP_USD:.2f}"
          f" · open≤{MAX_OPEN_POSITIONS} · gap≥{MIN_SECONDS_BETWEEN_BETS}s · edge≥{MIN_EDGE_BPS:.0f}bps")
    print("  DEFAULT-SAFE: places nothing until all gates are open.")
    print("=" * 70)
    standby_note = None
    while True:
        try:
            ok, why = _gates()
            if not ok:
                if why != standby_note:
                    print(f"[live-exec] STANDBY — {why}")
                    standby_note = why
                time.sleep(POLL_SECONDS)
                continue
            if standby_note is not None:
                print(f"[live-exec] 🟢 ALL GATES OPEN — autonomous execution active")
                standby_note = None

            _loss_monitor()

            raw = _rc.lrange(BETS_KEY, 0, 200)
            bets = []
            for item in raw:
                try:
                    bets.append(json.loads(item))
                except Exception:
                    continue
            # oldest-first, only fresh open bets
            for bet in reversed(bets):
                if bet.get("status") != "open":
                    continue
                msg = _act_on_bet(bet)
                if msg:
                    print(f"[live-exec] {msg}")
                # re-check the kill-switch mid-batch (a HALT must stop us now)
                from scripts.live_kill_switch import is_halted
                if is_halted():
                    break
        except Exception as e:
            print(f"[live-exec] loop error: {repr(e)[:160]}")
        time.sleep(POLL_SECONDS)


def _safe_max_bet() -> float:
    from scripts.live_safety_checks import MAX_BET_USD
    return MAX_BET_USD


def _safe_daily() -> float:
    from scripts.live_safety_checks import DAILY_LIMIT_USD
    return DAILY_LIMIT_USD


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cmd_status():
    ok, why = _gates()
    armed_ttl = _rc.ttl(ARMED_KEY)
    print("=" * 56)
    print("  Autonomous Live Executor — status")
    print("=" * 56)
    print(f"  Gates:          {'🟢 OPEN' if ok else '⛔ CLOSED'} ({why})")
    print(f"  Armed:          {'yes, expires in ' + str(armed_ttl) + 's' if armed_ttl and armed_ttl > 0 else 'no'}")
    print(f"  arb:mode:       {_rc.get('arb:mode') or 'demo'}")
    env_ok, env_why = _env_live_ready()
    print(f"  Server live:    {'yes' if env_ok else 'no — ' + env_why}")
    print(f"  Total spent:    ${float(_rc.get(TOTAL_SPEND_KEY) or 0):.2f} / cap ${TOTAL_CAP_USD:.2f}")
    print(f"  Open positions: {int(_rc.get(OPEN_COUNT_KEY) or 0)} / {MAX_OPEN_POSITIONS}")
    print(f"  Per-bet cap:    ${_safe_max_bet():.2f}   Daily cap: ${_safe_daily():.2f}")
    print("=" * 56)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "run":
        run_loop()
    elif cmd == "arm":
        ttl = _parse_ttl(sys.argv[2]) if len(sys.argv) > 2 else ARM_DEFAULT_TTL_SEC
        env_ok, env_why = _env_live_ready()
        if not env_ok:
            print(f"⛔ Refusing to arm — server not live-ready: {env_why}")
            print("   Set PAPER_TRADE=false + POLYMARKET_PRIVATE_KEY + POLY_WALLET_ADDRESS first.")
            sys.exit(1)
        _rc.set(ARMED_KEY, f"armed@{datetime.now(timezone.utc).isoformat()}", ex=ttl)
        print(f"🟢 ARMED for {ttl}s (~{ttl/3600:.1f}h). Auto-disarms after that — re-arm to continue.")
        _cmd_status()
    elif cmd == "disarm":
        _rc.delete(ARMED_KEY)
        print("⛔ DISARMED — autonomous executor will place no orders.")
    elif cmd == "status":
        _cmd_status()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
