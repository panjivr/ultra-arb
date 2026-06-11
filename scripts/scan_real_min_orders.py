"""Get the REAL minimum_order_size from the CLOB API for crypto markets,
not the Gamma API's "?" placeholder. Then compute the true minimum bet cost.
"""
import os, json, httpx
from datetime import datetime, timezone

with open("/home/reyogcapital165/reyog-capital/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient
SAFE = "0xdeda54cf47644b5181783b4d3cd8d286b93c7af0"
cl = ClobClient(
    host="https://clob.polymarket.com",
    key=os.environ["POLY_PRIVATE_KEY"],
    chain_id=137, signature_type=2, funder=SAFE,
)
cl.set_api_creds(cl.derive_api_key())

# Sample condition IDs from earlier scan (mix of types)
sample_cids = [
    ("0x66a6ebf4e640a16a9ee27def645b48b1c50fad5fedfa52e4cc45e90097bdbdec", "BTC above 76k May20 6PM"),
]

# Also fetch fresh Gamma list and check each via CLOB
r = httpx.get("https://gamma-api.polymarket.com/markets",
    params={"limit": 500, "active":"true", "closed":"false", "order":"endDate", "ascending":"true"},
    timeout=20).json()

now = datetime.now(timezone.utc)
candidates = []
for m in r:
    q = (m.get("question") or "").lower()
    if not any(k in q for k in ["bitcoin","ethereum","solana"]):
        continue
    if not m.get("acceptingOrders"): continue
    end = m.get("endDate") or ""
    try:
        end_dt = datetime.fromisoformat(end.replace("Z","+00:00"))
        hrs = (end_dt - now).total_seconds()/3600
    except: continue
    if hrs <= 0 or hrs > 4: continue  # tight window: ending in next 4h

    cid = m.get("conditionId","")
    candidates.append({
        "cid": cid,
        "q": (m.get("question") or "")[:70],
        "hrs": round(hrs,2),
    })

print(f"Crypto markets ending in next 4h: {len(candidates)}\n")
print(f"{'hrs':<6} {'min_ord':<8} {'tick':<6} {'cheap_side':<12} {'cheap_$':<8} {'minCost':<8} question")
print("-"*120)

fit_budget = []
for c in candidates[:40]:
    try:
        m = cl.get_market(c["cid"])
        min_ord = float(m.get("minimum_order_size") or 5)
        tick = float(m.get("minimum_tick_size") or 0.01)
        tokens = m.get("tokens", [])
        if len(tokens) != 2: continue
        # find cheap side
        prices = []
        for t in tokens:
            p = float(t.get("price") or 0)
            prices.append({"outcome": t.get("outcome"), "token_id": t.get("token_id"), "price": p})
        cheap = min(prices, key=lambda x: x["price"])
        other = max(prices, key=lambda x: x["price"])
        # Actual cost at min order size at cheap price
        cost = min_ord * cheap["price"]
        print(f"{c['hrs']:<6} {min_ord:<8.1f} {tick:<6} {cheap['outcome'][:11]:<12} {cheap['price']:<8.4f} ${cost:<7.4f} {c['q']}")
        if cost <= 0.40 and cheap["price"] >= 0.01 and cheap["price"] <= 0.20:
            fit_budget.append({
                "cid": c["cid"],
                "question": c["q"],
                "hours_left": c["hrs"],
                "min_order_size": min_ord,
                "tick_size": tick,
                "cheap_outcome": cheap["outcome"],
                "cheap_token": cheap["token_id"],
                "cheap_price": cheap["price"],
                "other_price": other["price"],
                "cost": round(cost, 4),
                "potential_payout": min_ord * 1.0,  # full payout = min_ord shares x $1
                "implied_breakeven_hits": int((25 * cost) / (min_ord * 1.0)) + 1,
            })
    except Exception as e:
        print(f"  err {c['cid'][:10]}: {e}")

print(f"\n=== Markets fitting $0.40/bet AND price in [0.01, 0.20]: {len(fit_budget)} ===")
import json as _j
print(_j.dumps(fit_budget[:30], indent=2, default=str))
with open("/tmp/scalp_plan.json","w") as f:
    _j.dump(fit_budget, f, indent=2, default=str)
print(f"\nSaved: /tmp/scalp_plan.json")
print(f"Sum of cost (all candidates): ${sum(b['cost'] for b in fit_budget):.4f}")
