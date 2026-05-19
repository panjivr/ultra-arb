#!/usr/bin/env python3
"""
F7+F8 Manual Live Test CLI
Hands-on tool for placing real Polymarket bets with $7 USDC.

IMPORTANT: Real money. Never place orders without understanding the market.

Commands:
  setup                                    — Test connection, show wallet balance
  find_market <keyword>                    — Search markets
  market_info <condition_id>               — Show market details + order book
  dry_run <token_id> <side> <price> <size> — Validate order (DO NOT submit)
  place <token_id> <side> <price> <size> --confirm  — ACTUAL order (real money)
  status <order_id>                        — Check order status
  cancel <order_id>                        — Cancel pending order
  emergency_stop                           — Cancel ALL open orders + halt
  kill_switch [status|halt <reason>|clear] — Manage kill-switch

Examples:
  python3 scripts/manual_live_test.py setup
  python3 scripts/manual_live_test.py find_market "bitcoin"
  python3 scripts/manual_live_test.py dry_run abc123 BUY 0.45 1.0
  python3 scripts/manual_live_test.py place abc123 BUY 0.45 1.0 --confirm

Run from: /home/reyogcapital165/reyog-capital/
Requires: pip install py-clob-client
Env vars: POLY_PRIVATE_KEY, POLY_WALLET_ADDRESS, POLY_HOST, POLY_CHAIN_ID
"""
import json
import os
import sys
from datetime import datetime, timezone

# Load .env if present (VPS deployment)
_env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() not in os.environ:  # don't override existing env vars
                    os.environ[k.strip()] = v.strip()

# Adjust path for direct script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.polymarket_live_adapter import (
    setup_client,
    check_wallet_balance,
    search_markets,
    get_market_details,
    calculate_friction,
    place_live_order,
    check_order_status,
    cancel_order,
    emergency_stop_all,
)
from scripts.live_safety_checks import run_all_checks, record_live_bet
from scripts.live_kill_switch import (
    is_halted, get_halt_reason, set_halt, clear_halt, _print_status as ks_status
)


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sep(title: str = "") -> None:
    if title:
        print(f"\n{'─'*4} {title} {'─'*(44 - len(title))}")
    else:
        print("─" * 50)


# ─── Commands ──────────────────────────────────────────────────────────────


def cmd_setup(args: list) -> None:
    """Test connection, verify credentials, show wallet balance."""
    print(f"\n{'='*50}")
    print("  F7 Live Test — Setup Check")
    print(f"{'='*50}")

    # Check env vars
    sep("Environment")
    pk = os.environ.get("POLY_PRIVATE_KEY", "")
    addr = os.environ.get("POLY_WALLET_ADDRESS", "")
    host = os.environ.get("POLY_HOST", "https://clob.polymarket.com")
    chain = os.environ.get("POLY_CHAIN_ID", "137")

    print(f"  POLY_HOST:           {host}")
    print(f"  POLY_CHAIN_ID:       {chain}")
    print(f"  POLY_WALLET_ADDRESS: {addr or '❌ NOT SET'}")
    print(f"  POLY_PRIVATE_KEY:    {'✅ SET (' + str(len(pk)) + ' chars)' if pk else '❌ NOT SET'}")

    if not pk or not addr:
        print("\n❌ POLY_PRIVATE_KEY and/or POLY_WALLET_ADDRESS missing.")
        print("   Add them to .env or export before running.")
        return

    # Test client init
    sep("Polymarket CLOB Connection")
    try:
        client = setup_client()
        print("  ✅ Client initialized")
    except Exception as e:
        print(f"  ❌ Client init failed: {e}")
        return

    # Wallet balance
    sep("Wallet Balance")
    try:
        bal = check_wallet_balance()
        print(f"  EOA (private key): {bal['wallet']}")
        if bal.get("safe_wallet"):
            print(f"  Safe wallet (funder): {bal['safe_wallet']}")
        print(f"  USDC balance:      ${bal['balance_usdc']:.4f}")
        if bal.get("relay_mode"):
            print(f"  CLOB balance: ${bal.get('clob_balance_usdc',0):.4f}  ← relay deposit (off-chain)")
            print(f"  On-chain USDC:${bal.get('wallet_usdc_onchain',0):.4f}  ← wallet remainder")
        else:
            print(f"  Allowance:         ${bal['allowance_usdc']:.4f}")
            if bal['allowance_usdc'] < 1.0:
                print("\n  ⚠️  ALLOWANCE IS LOW — may need approval for on-chain orders.")
            else:
                print("  ✅ Ready to trade")
    except Exception as e:
        print(f"  ❌ Balance check failed: {e}")
        return

    # Kill-switch
    sep("Kill-Switch")
    ks_status()

    sep()
    print("  ✅ Setup complete. Ready for test commands.")
    print(f"{'='*50}\n")


def cmd_find_market(args: list) -> None:
    """Search Polymarket markets by keyword."""
    if not args:
        print("Usage: find_market <keyword>")
        print("Example: find_market bitcoin")
        return

    keyword = " ".join(args)
    print(f"\nSearching markets for '{keyword}'...")

    try:
        results = search_markets(keyword, limit=10)
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    if not results:
        print("No markets found.")
        return

    if results and "error" in results[0]:
        print(f"❌ API Error: {results[0]['error']}")
        return

    now = datetime.now(timezone.utc)
    print(f"\nFound {len(results)} markets:\n")

    for i, m in enumerate(results, 1):
        end_iso = m.get("end_date_iso", "?")
        status = "CLOSED" if m.get("closed") else ("ACTIVE" if m.get("active") else "INACTIVE")

        # Calculate hours left
        try:
            end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            h_left = (end - now).total_seconds() / 3600
            time_str = f"{h_left:.1f}h left" if h_left > 0 else f"ended {abs(h_left):.1f}h ago"
        except Exception:
            time_str = end_iso

        print(f"  [{i}] {m['question'][:70]}")
        print(f"       condition_id: {m['condition_id']}")
        print(f"       status: {status} | {time_str}")
        print(f"       tokens:")
        for t in m.get("tokens", []):
            price = t.get("price")
            price_str = f"${price:.3f}" if price is not None else "?"
            print(f"         {t['outcome']:8s} token_id={t['token_id'][:20]}... price={price_str}")
        print()


def cmd_market_info(args: list) -> None:
    """Show full market details + order book top 3."""
    if not args:
        print("Usage: market_info <condition_id>")
        return

    condition_id = args[0]
    print(f"\nFetching market {condition_id[:16]}...\n")

    try:
        m = get_market_details(condition_id)
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    if "error" in m:
        print(f"❌ {m['error']}")
        return

    print(f"Question: {m['question']}")
    print(f"Ends:     {m.get('end_date_iso', '?')}")
    print(f"Active:   {m.get('active', '?')}")
    print()

    for outcome, ob in m.get("order_books", {}).items():
        print(f"  {outcome} (token: {ob.get('token_id', '')[:20]}...)")
        print(f"    best_bid: {ob.get('best_bid', '?'):.4f}" if ob.get("best_bid") else "    best_bid: (none)")
        print(f"    best_ask: {ob.get('best_ask', '?'):.4f}" if ob.get("best_ask") else "    best_ask: (none)")
        for bid in ob.get("bids_top3", []):
            print(f"    bid: {bid[0]:.4f} × {bid[1]:.2f}")
        for ask in ob.get("asks_top3", []):
            print(f"    ask: {ask[0]:.4f} × {ask[1]:.2f}")
        print()


def cmd_dry_run(args: list) -> None:
    """Validate order without submitting. Shows all safety checks."""
    if len(args) < 4:
        print("Usage: dry_run <token_id> <side> <price> <size>")
        print("  token_id: from find_market output")
        print("  side:     BUY or SELL")
        print("  price:    0.01–0.99 (limit price)")
        print("  size:     shares (cost = price × size USDC)")
        print("\nExample: dry_run abc123... BUY 0.45 2.0")
        return

    token_id, side, price_str, size_str = args[0], args[1], args[2], args[3]
    try:
        price = float(price_str)
        size = float(size_str)
    except ValueError:
        print("❌ price and size must be numbers")
        return

    cost_usdc = round(price * size, 4)

    print(f"\n{'='*50}")
    print(f"  DRY RUN — Not submitting")
    print(f"{'='*50}")
    print(f"  token_id: {token_id[:30]}...")
    print(f"  side:     {side}")
    print(f"  price:    {price:.4f}")
    print(f"  size:     {size:.2f} shares")
    print(f"  cost:     ${cost_usdc:.4f} USDC")
    print()

    # Check kill-switch first
    if is_halted():
        print(f"❌ Kill-switch active: {get_halt_reason()}")
        return

    # Get wallet balance
    sep("Wallet Balance")
    try:
        bal = check_wallet_balance()
        relay_mode = bal.get("relay_mode", False)
        if relay_mode:
            print(f"  Mode:    RELAY (Polymarket holds funds off-chain)")
            print(f"  On-chain:${bal.get('wallet_usdc_onchain', 0):.4f} USDC remaining in wallet")
        else:
            print(f"  Balance: ${bal['balance_usdc']:.4f} USDC")
    except Exception as e:
        print(f"  ❌ Balance check failed: {e}")
        bal = {"balance_usdc": 0.0, "relay_mode": False}
        relay_mode = False

    # Calculate friction
    sep("Friction Estimate")
    try:
        fr = calculate_friction(token_id, side, cost_usdc)
        print(f"  Spread:        {fr.get('spread_pct', '?')}%")
        print(f"  Poly fee:      {fr.get('polymarket_fee_pct', 2.0)}% of winnings")
        print(f"  Gas est:       ${fr.get('gas_est_usd', 0.03):.3f}")
        print(f"  Total friction:{fr.get('total_friction_pct', '?')}%")
        print(f"  Acceptable:    {'✅ Yes' if fr.get('acceptable') else '❌ No (>10%)'}")
    except Exception as e:
        print(f"  ❌ Friction calc failed: {e}")
        fr = {"total_friction_pct": None, "acceptable": False}

    # Would need market end_date for check — skip here, show warning
    sep("Note")
    print("  ⚠️  market_open check requires condition_id end_date.")
    print("  Use 'market_info <condition_id>' to verify end date manually.")

    # Safety checks (partial — no end_date)
    sep("Safety Checks (partial)")
    from scripts.live_safety_checks import (
        check_kill_switch, check_daily_limit, check_bet_size, check_wallet_balance as chk_bal, check_friction
    )
    checks = [
        check_kill_switch(),
        check_daily_limit(cost_usdc),
        check_bet_size(cost_usdc),
        chk_bal(bal["balance_usdc"], cost_usdc, relay_mode=relay_mode),
        check_friction(fr.get("total_friction_pct")),
    ]
    for (ok, reason) in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {reason}")

    # Simulate order creation
    sep("Order Validation")
    try:
        result = place_live_order(token_id, side, price, size, dry_run=True)
        if result.get("signed"):
            print(f"  ✅ Order signed successfully (not submitted)")
            print(f"  Would cost: ${result['would_place']['estimated_cost_usdc']:.4f} USDC")
        else:
            print(f"  ❌ Order signing failed")
    except Exception as e:
        print(f"  ❌ Signing error: {e}")

    sep()
    print("  DRY RUN complete. No order was placed.")
    print("  To place real order: add --confirm flag\n")


def cmd_place(args: list) -> None:
    """Place a real live order. Requires --confirm flag."""
    if "--confirm" not in args:
        print("❌ Safety: --confirm flag required to place real order.")
        print("   Run dry_run first, then add --confirm when ready.")
        print("   Usage: place <token_id> <side> <price> <size> --confirm")
        return

    real_args = [a for a in args if a != "--confirm"]
    if len(real_args) < 4:
        print("Usage: place <token_id> <side> <price> <size> --confirm")
        return

    token_id, side, price_str, size_str = real_args[0], real_args[1], real_args[2], real_args[3]
    try:
        price = float(price_str)
        size = float(size_str)
    except ValueError:
        print("❌ price and size must be numbers")
        return

    cost_usdc = round(price * size, 4)

    print(f"\n{'='*50}")
    print(f"  ⚠️  REAL ORDER — This uses actual USDC")
    print(f"{'='*50}")
    print(f"  token_id: {token_id[:30]}...")
    print(f"  side:     {side.upper()}")
    print(f"  price:    {price:.4f}")
    print(f"  size:     {size:.2f}")
    print(f"  cost:     ${cost_usdc:.4f} USDC")
    print()

    # Kill-switch
    if is_halted():
        print(f"❌ BLOCKED — Kill-switch active: {get_halt_reason()}")
        return

    # Balance
    try:
        bal = check_wallet_balance()
        balance_usdc = bal["balance_usdc"]
        relay_mode = bal.get("relay_mode", False)
        if relay_mode:
            print(f"  Balance mode:   RELAY (Polymarket holds funds off-chain)")
            print(f"  On-chain USDC:  ${bal.get('wallet_usdc_onchain', 0):.4f} (wallet remainder)")
        else:
            print(f"  Wallet balance: ${balance_usdc:.4f} USDC")
    except Exception as e:
        print(f"❌ Balance check failed: {e}")
        return

    # Friction
    try:
        fr = calculate_friction(token_id, side, cost_usdc)
        friction_pct = fr.get("total_friction_pct")
        print(f"  Friction:       {friction_pct}%")
    except Exception:
        friction_pct = None

    # Full safety checks (market_open skipped — user verifies end_date manually)
    from datetime import datetime, timezone, timedelta
    # Use a placeholder 24h from now so market_open passes; user confirms end_date
    placeholder_end = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    all_ok, results = run_all_checks(
        size_usdc=cost_usdc,
        end_date_iso=placeholder_end,
        balance_usdc=balance_usdc,
        friction_pct=friction_pct,
        relay_mode=relay_mode,
    )

    sep("Safety Checks")
    for r in results:
        if r["check"] == "market_open":
            print(f"  ⚠️  market_open: SKIPPED — verify end date manually (use market_info)")
            continue
        print(f"  {r['icon']} {r['check']}: {r['reason']}")

    # Only block on non-market_open failures
    hard_fail = any(
        not r["passed"] for r in results if r["check"] != "market_open"
    )
    if hard_fail:
        print("\n❌ BLOCKED — One or more safety checks failed. Order NOT placed.")
        return

    # Final confirmation prompt
    print(f"\n  Ready to place REAL order:")
    print(f"  {side.upper()} {size:.2f} shares @ {price:.4f} = ${cost_usdc:.4f} USDC")
    try:
        confirm = input("\n  Type YES to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if confirm != "YES":
        print("  Cancelled (need 'YES' exactly).")
        return

    # Place order
    print("\n  Submitting order...")
    try:
        result = place_live_order(token_id, side, price, size, dry_run=False)
    except Exception as e:
        print(f"\n❌ Order submission failed: {e}")
        return

    order_id = result.get("order_id", "")
    print(f"\n  ✅ Order submitted!")
    print(f"  order_id: {order_id}")
    print(f"  tx_hash:  {result.get('transaction_hash', '(pending)')}")

    # Record bet
    record_live_bet(
        order_id=order_id,
        size_usdc=cost_usdc,
        meta={
            "token_id": token_id,
            "side": side,
            "price": price,
            "size": size,
            "submitted_at": ts(),
        },
    )
    print(f"\n  📝 Logged to Redis arb:live:orders + logs/live_bets.jsonl")
    print(f"  Check status: python3 scripts/manual_live_test.py status {order_id}\n")


def cmd_status(args: list) -> None:
    if not args:
        print("Usage: status <order_id>")
        return
    order_id = args[0]
    print(f"\nChecking order {order_id}...")
    try:
        result = check_order_status(order_id)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")


def cmd_cancel(args: list) -> None:
    if not args:
        print("Usage: cancel <order_id>")
        return
    order_id = args[0]
    print(f"\nCancelling order {order_id}...")
    try:
        result = cancel_order(order_id)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")


def cmd_emergency_stop(args: list) -> None:
    print("\n⚠️  EMERGENCY STOP — Cancelling ALL open orders + halting")
    try:
        confirm = input("Type YES to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("Cancelled.")
        return
    if confirm != "YES":
        print("Cancelled.")
        return

    set_halt("emergency_stop")
    result = emergency_stop_all()
    print(f"\nResult: {json.dumps(result, indent=2)}")
    print("Kill-switch set. Run 'kill_switch clear' when ready to resume.")


def cmd_kill_switch(args: list) -> None:
    sub = args[0] if args else "status"
    if sub == "status":
        ks_status()
    elif sub == "halt":
        reason = " ".join(args[1:]) if len(args) > 1 else "manual"
        set_halt(reason)
    elif sub == "clear":
        clear_halt()
        ks_status()
    else:
        print(f"Unknown kill_switch subcommand: {sub}")
        print("Usage: kill_switch [status|halt <reason>|clear]")


# ─── Main ──────────────────────────────────────────────────────────────────


COMMANDS = {
    "setup":          cmd_setup,
    "find_market":    cmd_find_market,
    "market_info":    cmd_market_info,
    "dry_run":        cmd_dry_run,
    "place":          cmd_place,
    "status":         cmd_status,
    "cancel":         cmd_cancel,
    "emergency_stop": cmd_emergency_stop,
    "kill_switch":    cmd_kill_switch,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    if cmd not in COMMANDS:
        print(f"❌ Unknown command: {cmd}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[cmd](rest)


if __name__ == "__main__":
    main()
