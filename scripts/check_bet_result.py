"""Check the final outcome of the Cavaliers live bet."""
import os, json, httpx
from datetime import datetime, timezone

with open("/home/reyogcapital165/reyog-capital/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

SAFE_WALLET = "0xdeda54cf47644b5181783b4d3cd8d286b93c7af0"
ORDER_ID = "0x6943e00c7c44127205a0350fef7a43502ce9d1086de147777acfe19a3af4810b"
TOKEN_CAVS = "91811271690939763569588501717168303099799014127066745654294854264052726562982"
TOKEN_KNICKS = "90341073610328513874226762002064133262679100936760740635957635490606188341771"
COND_ID = "0x8530b96422523df2024c4242021b58da538c5e94ba525e8f9893c3fc2f469160"

cl = ClobClient(
    host="https://clob.polymarket.com",
    key=os.environ["POLY_PRIVATE_KEY"],
    chain_id=137, signature_type=2, funder=SAFE_WALLET,
)
creds = cl.derive_api_key()
cl.set_api_creds(creds)

print("=== Balance NOW ===")
bal = cl.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
balance_usdc = int(bal.get("balance", 0)) / 1e6
print(f"USDC: ${balance_usdc:.4f}")
print(f"  Before bet:  $7.8920")
print(f"  After bet:   $6.2594 (paid $1.60)")
print(f"  If WIN:      $11.26 (5 shares x $1.00 = $5.00 payout)")
print(f"  If LOSE:     $6.26 (no payout)")
delta = balance_usdc - 6.2594
print(f"  Change since bet placed: ${delta:+.4f}")

print()
print("=== Market resolution ===")
try:
    m = cl.get_market(COND_ID)
    q = m.get("question", "?")
    print(f"Question: {q[:90]}")
    print(f"Active={m.get('active')} Closed={m.get('closed')} Archived={m.get('archived')}")
    print(f"Accepting orders: {m.get('accepting_orders')}")
    print(f"End date: {m.get('end_date_iso', '?')}")
    print(f"Game start time: {m.get('game_start_time', '?')}")
    for t in m.get("tokens", []):
        outcome = t.get("outcome", "?")
        price = t.get("price", "?")
        winner = t.get("winner", None)
        print(f"  {outcome}: price={price} winner={winner}")
except Exception as e:
    print(f"Market lookup error: {e}")

print()
print("=== Order final status ===")
try:
    order = cl.get_order(ORDER_ID)
    print(json.dumps(order, indent=2)[:700])
except Exception as e:
    print(f"Order lookup error: {e}")

print()
print("=== Positions (Cavaliers/Knicks only) ===")
try:
    res = httpx.get(
        "https://data-api.polymarket.com/positions",
        params={"user": SAFE_WALLET, "sizeThreshold": 0.01},
        timeout=10,
    )
    if res.status_code == 200:
        positions = res.json() if isinstance(res.json(), list) else []
        found = False
        for p in positions:
            title = (p.get("title") or "").lower()
            asset = p.get("asset", "")
            if "cavalier" in title or "knicks" in title or asset == TOKEN_CAVS or asset == TOKEN_KNICKS:
                found = True
                print(f"  TITLE: {p.get('title','?')}")
                print(f"  outcome={p.get('outcome')} size={p.get('size')} avgPrice={p.get('avgPrice')}")
                print(f"  currentValue={p.get('currentValue')} curPnl={p.get('curPnl')}")
                print(f"  realizedPnl={p.get('realizedPnl','?')} redeemable={p.get('redeemable','?')}")
                print()
        if not found:
            print("  No Cavaliers/Knicks position (may have already been redeemed)")
            # show last 3 anyway
            print("  Top 3 positions:")
            for p in positions[:3]:
                print(f"    {p.get('title','?')[:50]}: size={p.get('size')} pnl={p.get('curPnl')}")
    else:
        print(f"  status={res.status_code}")
except Exception as e:
    print(f"positions error: {e}")

print()
print(f"=== Time now (UTC) ===")
print(datetime.now(timezone.utc).isoformat())
