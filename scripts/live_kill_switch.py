"""
F7 — Live Kill Switch
Manual + automatic halt for live Polymarket betting.

Manual halt:
  python scripts/live_kill_switch.py halt "my reason"
  python scripts/live_kill_switch.py clear

Auto-halt conditions (called from result tracking):
  - Daily loss > $3.00
  - 3 consecutive losses
  - Wallet balance < $1.00
  - Any Polymarket API error

Redis keys used:
  arb:live:halted              — halt flag (any non-empty = halted)
  arb:live:consecutive_losses  — counter, reset on win
  arb:live:daily_loss:{date}   — float, cumulative daily loss
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")

LIVE_HALT_KEY = "arb:live:halted"
CONSECUTIVE_LOSS_KEY = "arb:live:consecutive_losses"
DAILY_LOSS_KEY_PREFIX = "arb:live:daily_loss:"

MAX_DAILY_LOSS_USD = 3.0
MAX_CONSECUTIVE_LOSSES = 3
MIN_WALLET_BALANCE_USD = 1.0


def _rcli(args: str) -> str:
    cmd = f"docker exec reyog_redis redis-cli -a {REDIS_PW} --no-auth-warning {args}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return (r.stdout or "").strip()
    except Exception as e:
        return f"__ERR__ {e}"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


# ─── Status ────────────────────────────────────────────────────────────────


def is_halted() -> bool:
    val = _rcli(f"GET {LIVE_HALT_KEY}")
    return bool(val and val not in ("", "(nil)", "__ERR__") and val != "0")


def get_halt_reason() -> str | None:
    val = _rcli(f"GET {LIVE_HALT_KEY}")
    if val and val not in ("", "(nil)", "__ERR__", "0"):
        return val
    return None


# ─── Control ───────────────────────────────────────────────────────────────


def set_halt(reason: str = "manual") -> None:
    _rcli(f"SET {LIVE_HALT_KEY} '{reason}'")
    print(f"[kill-switch] 🔴 HALTED: {reason}")


def clear_halt() -> None:
    _rcli(f"DEL {LIVE_HALT_KEY}")
    _rcli(f"DEL {CONSECUTIVE_LOSS_KEY}")
    print("[kill-switch] ✅ Kill-switch cleared. Ready for trading.")


# ─── Auto-halt triggers ────────────────────────────────────────────────────


def record_loss(amount_usd: float) -> dict:
    """
    Call after a bet resolves as a loss.
    Returns {"halted": bool, "reason": str | None}.
    """
    today = _today()

    # Increment consecutive losses
    losses = _rcli(f"INCR {CONSECUTIVE_LOSS_KEY}")
    _rcli(f"EXPIRE {CONSECUTIVE_LOSS_KEY} 86400")
    try:
        losses = int(losses)
    except ValueError:
        losses = 1

    # Increment daily loss
    daily_key = DAILY_LOSS_KEY_PREFIX + today
    daily_loss = _rcli(f"INCRBYFLOAT {daily_key} {amount_usd}")
    _rcli(f"EXPIRE {daily_key} 172800")
    try:
        daily_loss = float(daily_loss)
    except ValueError:
        daily_loss = amount_usd

    reasons = []
    if losses >= MAX_CONSECUTIVE_LOSSES:
        reasons.append(f"{losses} consecutive losses (limit {MAX_CONSECUTIVE_LOSSES})")
    if daily_loss >= MAX_DAILY_LOSS_USD:
        reasons.append(f"daily loss ${daily_loss:.2f} >= ${MAX_DAILY_LOSS_USD:.2f}")

    if reasons:
        reason_str = "Auto-halt: " + "; ".join(reasons)
        set_halt(reason_str)
        return {"halted": True, "reason": reason_str}

    return {
        "halted": False,
        "consecutive_losses": losses,
        "daily_loss_usd": round(daily_loss, 4),
        "reason": None,
    }


def record_win() -> None:
    """Call after a bet resolves as a win — resets consecutive loss counter."""
    _rcli(f"DEL {CONSECUTIVE_LOSS_KEY}")
    print("[kill-switch] Win recorded — consecutive loss counter reset.")


def check_balance_halt(balance_usdc: float) -> bool:
    """Auto-halt if wallet balance too low. Returns True if halted."""
    if balance_usdc < MIN_WALLET_BALANCE_USD:
        set_halt(
            f"Auto-halt: balance ${balance_usdc:.4f} < minimum ${MIN_WALLET_BALANCE_USD:.2f}"
        )
        return True
    return False


# ─── CLI ───────────────────────────────────────────────────────────────────


def _print_status() -> None:
    reason = get_halt_reason()
    losses_raw = _rcli(f"GET {CONSECUTIVE_LOSS_KEY}")
    daily_raw = _rcli(f"GET {DAILY_LOSS_KEY_PREFIX + _today()}")

    print("=" * 48)
    print("  Live Kill-Switch Status")
    print("=" * 48)
    if reason:
        print(f"  Status:             🔴 HALTED")
        print(f"  Reason:             {reason}")
    else:
        print(f"  Status:             ✅ ACTIVE (not halted)")

    try:
        print(f"  Consecutive losses: {int(losses_raw) if losses_raw not in ('(nil)', '', '__ERR__') else 0}")
    except Exception:
        print(f"  Consecutive losses: 0")

    try:
        print(f"  Daily loss today:   ${float(daily_raw):.4f}" if daily_raw not in ("(nil)", "", "__ERR__") else "  Daily loss today:   $0.0000")
    except Exception:
        print(f"  Daily loss today:   $0.0000")

    print(f"  Max daily loss:     ${MAX_DAILY_LOSS_USD:.2f}")
    print(f"  Max consec. losses: {MAX_CONSECUTIVE_LOSSES}")
    print(f"  Min wallet balance: ${MIN_WALLET_BALANCE_USD:.2f}")
    print("=" * 48)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        _print_status()

    elif cmd == "halt":
        reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "manual"
        set_halt(reason)

    elif cmd == "clear":
        clear_halt()
        _print_status()

    elif cmd == "test":
        # Test Redis connectivity
        pong = _rcli("PING")
        print(f"Redis ping: {pong}")
        _print_status()

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python live_kill_switch.py [status|halt <reason>|clear|test]")
        sys.exit(1)
