"""Check the status of the Cavaliers live bet."""
import httpx, json
from datetime import datetime, timezone

SAFE_WALLET = "0xdeda54cf47644b5181783b4d3cd8d286b93c7af0"
ORDER_ID = "0x6943e00c7c44127205a0350fef7a43502ce9d1086de147777acfe19a3af4810b"
MARKET_ID = "0x8530b96422523df2024c4242021b58da538c5e94ba525e8f9893c3fc2f469160"

print("=== Bet Status: Cavaliers at $0.32 ===")
print(f"Order: {ORDER_ID}")
print(f"Safe wallet: {SAFE_WALLET}")
print()

# Check positions on data API
print("--- Positions ---")
res = httpx.get(
    "https://data-api.polymarket.com/positions",
    params={"user": SAFE_WALLET, "limit": 10},
    timeout=10
)
print("Status:", res.status_code)
positions = res.json() if res.status_code == 200 else []
if positions:
    for p in (positions if isinstance(positions, list) else []):
        question = p.get("title") or p.get("question") or p.get("market") or "?"
        outcome = p.get("outcome", "?")
        size = p.get("size", "?")
        avg_price = p.get("avgPrice") or p.get("price", "?")
        value = p.get("currentValue") or p.get("value", "?")
        pnl = p.get("curPnl") or p.get("pnl", "?")
        print(f"  {question[:60]}: {outcome}, {size} shares @ {avg_price}")
        print(f"  value={value}, pnl={pnl}")
        print()
else:
    print("  No positions found (might take time to appear)")

# Check market
print("--- Market ---")
res2 = httpx.get(
    "https://gamma-api.polymarket.com/markets",
    params={"conditionId": MARKET_ID},
    timeout=10
)
if res2.status_code == 200:
    markets = res2.json()
    m = markets[0] if isinstance(markets, list) and markets else {}
    question = m.get("question", "?")
    end_date = m.get("endDate", "?")
    active = m.get("active")
    closed = m.get("closed")
    print(f"  Question: {question}")
    print(f"  End date: {end_date}")
    print(f"  Active: {active}, Closed: {closed}")

    if end_date and end_date != "?":
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_left = (end_dt - now).total_seconds() / 3600
            print(f"  Now (UTC): {now.strftime('%Y-%m-%d %H:%M UTC')}")
            print(f"  Hours left: {hours_left:.1f}h")
        except Exception as e:
            print(f"  Date parse error: {e}")

print()
print("=== Summary ===")
print("Bet: BUY 5 Cavaliers shares @ $0.32 = $1.60")
print("Win payout: 5 shares x $1.00 = $5.00 (profit $3.40)")
print("Loss: forfeit $1.60")
print("Remaining balance: ~$6.26 USDC")
