"""
Inspect timing of crypto Up/Down markets: how far in the future is each
market's price window? Current 40s momentum only has predictive value for a
window that STARTS within a few minutes. This tells us whether imminent-window
markets exist (and how to filter to them).
"""
import json, httpx
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
print(f"now (UTC): {now.isoformat()}")

r = httpx.get("https://gamma-api.polymarket.com/markets",
    params={"active":"true","closed":"false","tag_id":"21","limit":"100","order":"endDate","ascending":"true"},
    timeout=20)
markets = r.json() if r.status_code == 200 else []
print(f"fetched {len(markets)} active crypto markets\n")

def parse_window_minutes(q):
    """Parse the ET window duration from the question, in minutes."""
    import re
    tw = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)\s*[-–]\s*(\d{1,2}):(\d{2})\s*(am|pm)", q.lower())
    if not tw: return None
    h1,m1,ap1,h2,m2,ap2 = tw.groups()
    def tm(h,m,ap):
        h=int(h)%12
        if ap=="pm": h+=12
        return h*60+int(m)
    d = tm(h2,m2,ap2)-tm(h1,m1,ap1)
    if d<0: d+=1440
    return d if d>0 else None

rows = []
for m in markets:
    q = m.get("question","")
    if "up or down" not in q.lower(): continue
    end = m.get("endDate","")
    try:
        end_dt = datetime.fromisoformat(end.replace("Z","+00:00"))
    except: continue
    dur_min = parse_window_minutes(q)
    if dur_min is None: continue
    # window start = end - duration
    start_dt = end_dt - timedelta(minutes=dur_min)
    mins_to_start = (start_dt - now).total_seconds()/60
    mins_to_end = (end_dt - now).total_seconds()/60
    rows.append({
        "q": q[:48], "dur": dur_min,
        "to_start_min": round(mins_to_start,1),
        "to_end_min": round(mins_to_end,1),
        "accepting": m.get("acceptingOrders"),
    })

rows.sort(key=lambda x: x["to_start_min"])
print(f"{'to_start':>9} {'to_end':>8} {'dur':>4} {'accept':>6}  question")
print("-"*90)
imminent = 0
for r_ in rows[:40]:
    flag = ""
    if -5 <= r_["to_start_min"] <= 15:
        flag = "  <-- IMMINENT (momentum relevant)"
        imminent += 1
    print(f"{r_['to_start_min']:>9} {r_['to_end_min']:>8} {r_['dur']:>4} {str(r_['accepting']):>6}  {r_['q']}{flag}")

print(f"\nTotal up/down markets: {len(rows)}")
print(f"Imminent (window starts within -5..+15 min): {imminent}")
print("\nInterpretation:")
print("  - to_start_min < 0  : window already started (momentum partly stale)")
print("  - 0..15 min         : IMMINENT — current momentum is actually relevant")
print("  - > 60 min          : future window — current momentum is NOISE for it")
