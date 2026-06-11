"""Scan ALL active crypto Up/Down markets, no filter — see what's actually available."""
import json, httpx
from datetime import datetime, timezone

KEYWORDS = ["bitcoin", "ethereum", "solana", "btc", "eth", "sol"]
UPDOWN_KW = ["up or down", "up_or_down", "above", "below", "between", "reach", "hit"]

print("=== Fetching markets (multiple sorts) ===")
all_markets = {}
# Try different sort/filter combos to maximize coverage
queries = [
    {"limit": 500, "active": "true", "closed": "false", "order": "endDate", "ascending": "true"},
    {"limit": 500, "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false"},
    {"limit": 500, "active": "true", "closed": "false", "order": "startDate", "ascending": "false"},
]
for q in queries:
    try:
        r = httpx.get("https://gamma-api.polymarket.com/markets", params=q, timeout=20)
        if r.status_code == 200:
            for m in r.json():
                cid = m.get("conditionId")
                if cid:
                    all_markets[cid] = m
            print(f"  query {q.get('order')}: +{len(r.json())} (total unique: {len(all_markets)})")
    except Exception as e:
        print(f"  err: {e}")

now = datetime.now(timezone.utc)

# Filter: question mentions crypto + has Up/Down-like structure
crypto_matches = []
for m in all_markets.values():
    q_text = (m.get("question", "") or "").lower()
    if not any(kw in q_text for kw in KEYWORDS):
        continue
    if not m.get("acceptingOrders"):
        continue

    end = m.get("endDate") or ""
    try:
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
        hours_left = (end_dt - now).total_seconds() / 3600 if end_dt else None
    except Exception:
        hours_left = None
    if hours_left is None or hours_left <= 0 or hours_left > 48:
        continue

    clob_ids = m.get("clobTokenIds", "[]")
    if isinstance(clob_ids, str):
        try: clob_ids = json.loads(clob_ids)
        except: clob_ids = []
    prices = m.get("outcomePrices", "[]")
    if isinstance(prices, str):
        try: prices = json.loads(prices)
        except: prices = []
    outcomes = m.get("outcomes", "[]")
    if isinstance(outcomes, str):
        try: outcomes = json.loads(outcomes)
        except: outcomes = []

    if len(clob_ids) != 2 or len(prices) != 2:
        continue

    p1, p2 = float(prices[0] or 0.5), float(prices[1] or 0.5)
    crypto_matches.append({
        "question": (m.get("question") or "")[:80],
        "hours_left": round(hours_left, 2),
        "outcomes": outcomes,
        "prices": [p1, p2],
        "tokens": clob_ids,
        "cid": m.get("conditionId"),
        "min_order_size": m.get("minimumOrderSize") or m.get("minimum_order_size", "?"),
        "min_tick_size": m.get("minimumTickSize") or m.get("minimum_tick_size", "?"),
        "vol24": float(m.get("volume24hr") or 0),
    })

crypto_matches.sort(key=lambda x: x["hours_left"])
print(f"\n=== Crypto markets accepting orders, ending in <48h: {len(crypto_matches)} ===")
print(f"\n{'#':<3} {'hrs':<6} {'cheap':<6} {'cost5':<6} {'minOrd':<7} {'vol24h':<8} question")
print("-" * 110)

# Show all with key info
budget_fit = []
for i, m in enumerate(crypto_matches[:60]):
    p1, p2 = m["prices"]
    cheap = min(p1, p2)
    cost5 = 5 * cheap
    print(f"{i+1:<3} {m['hours_left']:<6} {cheap:<6.3f} {cost5:<6.3f} {str(m['min_order_size']):<7} {m['vol24']:<8.0f} {m['question']}")
    # Check fit at min order of 5 OR market's own minimum
    min_o = m["min_order_size"]
    try:
        min_o_n = float(min_o)
    except:
        min_o_n = 5.0
    if min_o_n <= 0: min_o_n = 5.0
    actual_cost = min_o_n * cheap
    if actual_cost <= 0.30 and cheap >= 0.01:
        budget_fit.append({**m, "min_order_n": min_o_n, "cheap_price": cheap, "actual_cost": actual_cost})

print(f"\n=== Markets fitting $0.30/bet at their min order size: {len(budget_fit)} ===")
import json as _json
print(_json.dumps(budget_fit[:30], indent=2, default=str)[:3000])
