"""Verify engine bets use REAL Polymarket prices + REAL oracle settlement."""
import subprocess, json

REDIS_PW = "reyog_redis_secret"

def rcli(args):
    r = subprocess.run(
        f"docker exec reyog_redis redis-cli -a {REDIS_PW} --no-auth-warning {args}",
        shell=True, capture_output=True, text=True, timeout=15)
    return (r.stdout or "").strip()

raw = rcli("LRANGE arb:polymarket:bets 0 80")
bets = []
for line in raw.splitlines():
    try:
        bets.append(json.loads(line))
    except Exception:
        pass

open_bets = [b for b in bets if b.get("status") == "open"]
resolved = [b for b in bets if b.get("status") in ("won", "lost")]

print(f"Total entries: {len(bets)} | open: {len(open_bets)} | resolved: {len(resolved)}")

# Show a recent OPEN bet — verify real entry price
print("\n=== Sample OPEN bet (verify REAL entry price) ===")
if open_bets:
    b = open_bets[0]
    for k in ("question", "asset", "side", "entry_price", "implied_prob", "our_prob",
              "edge_bps", "asset_price_at_bet", "stake_usd", "is_real_wallet",
              "condition_id", "market_id", "end_date", "source"):
        print(f"  {k}: {b.get(k)}")

# Show a recent RESOLVED bet — verify NEW oracle settlement fields
print("\n=== Sample RESOLVED bets (verify polymarket_oracle settlement) ===")
oracle_count = 0
feed_count = 0
for b in resolved:
    if b.get("settlement") == "polymarket_oracle":
        oracle_count += 1
    elif "went_up" in b or "in_range" in b:
        feed_count += 1
for b in resolved[:4]:
    print(f"  {b.get('status'):5} {b.get('side'):5} {b.get('asset'):10} "
          f"settlement={b.get('settlement','OLD_FEED?')} "
          f"winning_outcome={b.get('winning_outcome','-')} "
          f"payout={b.get('payout_usd')}")

print(f"\n=== Settlement method audit ===")
print(f"  Resolved via polymarket_oracle (NEW, real): {oracle_count}")
print(f"  Resolved via feed approximation (OLD): {feed_count}")
print(f"  => {'ALL REAL ORACLE' if feed_count == 0 and oracle_count > 0 else 'MIXED/OLD present'}")

# Risk halt status
print(f"\n=== Risk halt flag ===")
halt = rcli("GET arb:risk:halted")
print(f"  arb:risk:halted = {halt!r}")
dl = rcli("KEYS arb:risk:polymarket_daily_loss:*")
print(f"  daily_loss keys: {dl}")
for k in dl.splitlines():
    if k.strip():
        print(f"    {k} = {rcli('GET ' + k.strip())}")

# Win/loss stats
print(f"\n=== Per-asset hit rate (arb:poly:stats) ===")
for sk in rcli("KEYS arb:poly:stats:*").splitlines():
    if sk.strip():
        print(f"  {sk}: {rcli('HGETALL ' + sk.strip())}")
