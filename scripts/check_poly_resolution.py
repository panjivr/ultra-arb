"""Inspect how a RESOLVED Polymarket crypto market looks, so we can build
a real-settlement resolver (instead of the engine's feed-based approximation)."""
import json, httpx
from datetime import datetime, timezone

now = datetime.now(timezone.utc)

# Fetch recently-closed crypto markets to see resolved structure
print("=== Fetching CLOSED crypto markets (recently resolved) ===")
r = httpx.get(
    "https://gamma-api.polymarket.com/markets",
    params={"closed": "true", "tag_id": "21", "limit": "200", "order": "endDate", "ascending": "false"},
    timeout=20,
)
markets = r.json() if r.status_code == 200 else []
print(f"Got {len(markets)} closed crypto markets")

shown = 0
for m in markets:
    q = (m.get("question") or "")
    if "up or down" not in q.lower():
        continue
    end = m.get("endDate", "")
    try:
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        hrs_ago = (now - end_dt).total_seconds() / 3600
    except Exception:
        hrs_ago = None

    prices = m.get("outcomePrices", "[]")
    if isinstance(prices, str):
        try: prices = json.loads(prices)
        except: prices = []
    outcomes = m.get("outcomes", "[]")
    if isinstance(outcomes, str):
        try: outcomes = json.loads(outcomes)
        except: outcomes = []

    print(f"\n--- {q[:70]}")
    print(f"  ended {hrs_ago:.1f}h ago" if hrs_ago else "  end?")
    print(f"  closed={m.get('closed')} active={m.get('active')}")
    print(f"  outcomes={outcomes}  outcomePrices={prices}")
    print(f"  umaResolutionStatus={m.get('umaResolutionStatus')}")
    # Show all keys that might indicate winner
    for k in ("resolvedBy", "resolutionSource", "winningOutcome", "winner", "outcome"):
        if k in m:
            print(f"  {k}={m.get(k)}")
    shown += 1
    if shown >= 5:
        break

if shown == 0:
    print("\nNo closed up/down markets found. Showing first 3 closed crypto markets raw:")
    for m in markets[:3]:
        prices = m.get("outcomePrices", "[]")
        if isinstance(prices, str):
            try: prices = json.loads(prices)
            except: pass
        print(f"\n  {m.get('question','?')[:70]}")
        print(f"  closed={m.get('closed')} outcomePrices={prices}")
        print(f"  keys with 'win'/'resolv'/'outcome': ", [k for k in m.keys() if any(s in k.lower() for s in ('win','resolv','outcome'))])
