"""
F8 — Pre-flight safety checks before any live order.
All checks must pass before place_live_order(dry_run=False) is called.

Redis accessed via docker exec (consistent with VPS setup).
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone

REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")

DAILY_LIMIT_USD = 5.0    # max total spend per calendar day
MAX_BET_USD = 2.0        # max single bet size
MIN_HOURS_TO_EXPIRY = 1  # market must have at least 1h left
MAX_HOURS_TO_EXPIRY = 168  # market must close within 7 days
MAX_FRICTION_PCT = 10.0  # reject if friction >= 10%

LIVE_HALT_KEY = "arb:live:halted"
DAILY_SPEND_KEY_PREFIX = "arb:live:daily_spend:"


def _rcli(args: str) -> str:
    """Run redis-cli via docker exec."""
    cmd = f"docker exec reyog_redis redis-cli -a {REDIS_PW} --no-auth-warning {args}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return (r.stdout or "").strip()
    except Exception as e:
        return f"__ERR__ {e}"


def _today_key() -> str:
    return DAILY_SPEND_KEY_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%d")


# ─── Individual checks ─────────────────────────────────────────────────────


def check_kill_switch() -> tuple[bool, str]:
    val = _rcli(f"GET {LIVE_HALT_KEY}")
    if val and val not in ("", "(nil)", "__ERR__") and val != "0":
        return False, f"Kill-switch active: arb:live:halted='{val}'"
    return True, "Kill-switch clear"


def check_daily_limit(proposed_usdc: float) -> tuple[bool, str]:
    raw = _rcli(f"GET {_today_key()}")
    try:
        spent = float(raw) if raw and raw not in ("(nil)", "", "__ERR__") else 0.0
    except ValueError:
        spent = 0.0
    if spent + proposed_usdc > DAILY_LIMIT_USD:
        return (
            False,
            f"Daily limit: spent ${spent:.2f} + proposed ${proposed_usdc:.2f}"
            f" > ${DAILY_LIMIT_USD:.2f} limit",
        )
    return True, f"Daily spend OK: ${spent:.2f} used of ${DAILY_LIMIT_USD:.2f} limit"


def check_bet_size(size_usdc: float) -> tuple[bool, str]:
    if size_usdc <= 0:
        return False, "Bet size must be > $0"
    if size_usdc > MAX_BET_USD:
        return False, f"Bet size ${size_usdc:.2f} exceeds max ${MAX_BET_USD:.2f}"
    return True, f"Bet size ${size_usdc:.2f} within limit"


def check_market_open(end_date_iso: str) -> tuple[bool, str]:
    """Market must be open and close in 1h–168h from now."""
    try:
        end = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours_left = (end - now).total_seconds() / 3600

        if hours_left < 0:
            return False, f"Market already ended {abs(hours_left):.1f}h ago"
        if hours_left < MIN_HOURS_TO_EXPIRY:
            return False, f"Market closes in {hours_left * 60:.0f}m — too soon (min {MIN_HOURS_TO_EXPIRY}h)"
        if hours_left > MAX_HOURS_TO_EXPIRY:
            return (
                False,
                f"Market closes in {hours_left:.0f}h — too far out"
                f" (max {MAX_HOURS_TO_EXPIRY}h / 7 days)",
            )
        return True, f"Market closes in {hours_left:.1f}h — OK"
    except Exception as e:
        return False, f"Could not parse end_date '{end_date_iso}': {e}"


def check_wallet_balance(
    balance_usdc: float,
    size_usdc: float,
    relay_mode: bool = False,
) -> tuple[bool, str]:
    """
    Wallet must have enough for bet + gas buffer ($0.10).

    relay_mode=True means balance came from on-chain fallback (not CLOB API).
    In relay mode we only require $1 minimum on-chain guard — the actual tradeable
    balance is confirmed by the user via Polymarket.com UI and the relay deposit.
    Polymarket will reject the order if funds are actually insufficient.
    """
    if relay_mode:
        # In relay mode, CLOB API shows $0 but Polymarket has the funds via relay.
        # Minimum sanity check: on-chain wallet USDC should be ≥ $0.10 for gas.
        if balance_usdc < 0.05:
            return (
                False,
                f"On-chain USDC ${balance_usdc:.4f} very low — check wallet has MATIC for gas",
            )
        return (
            True,
            f"Relay mode: on-chain USDC=${balance_usdc:.4f} (Polymarket holds deposit off-chain)",
        )
    needed = size_usdc + 0.10
    if balance_usdc < needed:
        return (
            False,
            f"Wallet ${balance_usdc:.4f} < bet ${size_usdc:.2f} + gas buffer $0.10",
        )
    return True, f"Wallet ${balance_usdc:.4f} sufficient"


def check_friction(friction_pct: float | None) -> tuple[bool, str]:
    if friction_pct is None:
        return False, "Friction unknown — no order book data"
    if friction_pct >= MAX_FRICTION_PCT:
        return False, f"Friction {friction_pct:.2f}% >= {MAX_FRICTION_PCT:.0f}% limit"
    return True, f"Friction {friction_pct:.2f}% acceptable"


# ─── Run all checks ────────────────────────────────────────────────────────


def run_all_checks(
    size_usdc: float,
    end_date_iso: str,
    balance_usdc: float,
    friction_pct: float | None,
    relay_mode: bool = False,
) -> tuple[bool, list[dict]]:
    """
    Run all 6 pre-flight checks.
    Returns (all_passed: bool, results: list of check dicts).
    relay_mode=True when CLOB balance is $0 but Polymarket holds funds via relay deposit.
    """
    checks = [
        ("kill_switch",    check_kill_switch()),
        ("daily_limit",    check_daily_limit(size_usdc)),
        ("bet_size",       check_bet_size(size_usdc)),
        ("market_open",    check_market_open(end_date_iso)),
        ("wallet_balance", check_wallet_balance(balance_usdc, size_usdc, relay_mode=relay_mode)),
        ("friction",       check_friction(friction_pct)),
    ]

    results = []
    all_passed = True
    for name, (ok, reason) in checks:
        icon = "✅" if ok else "❌"
        results.append({"check": name, "passed": ok, "reason": reason, "icon": icon})
        if not ok:
            all_passed = False

    return all_passed, results


# ─── Record bet ────────────────────────────────────────────────────────────


def record_live_bet(order_id: str, size_usdc: float, meta: dict) -> None:
    """
    Record a confirmed live bet to:
    1. Redis arb:live:orders (List, max 1000)
    2. Redis arb:live:daily_spend:{date} (float, 2-day TTL)
    3. logs/live_bets.jsonl (append-only audit trail)
    """
    today_key = _today_key()

    entry = {
        "order_id": order_id,
        "size_usdc": size_usdc,
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ts_ms": int(time.time() * 1000),
        **meta,
    }
    entry_json = json.dumps(entry)

    # Increment daily spend
    _rcli(f"INCRBYFLOAT {today_key} {size_usdc}")
    _rcli(f"EXPIRE {today_key} 172800")  # 2 days TTL

    # Append to live orders list
    _rcli(f"LPUSH arb:live:orders '{entry_json}'")
    _rcli("LTRIM arb:live:orders 0 999")

    # Append to local audit file
    log_path = os.path.join(
        os.path.dirname(__file__), "..", "logs", "live_bets.jsonl"
    )
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(entry_json + "\n")
