"""
Debug proxy/deposit wallet address.
Try to find the correct maker address for Polymarket orders.
"""
import os, json, traceback
import httpx

with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

EOA = os.environ['POLY_WALLET_ADDRESS']
print("EOA:", EOA)

# ====================================================================
# Approach 1: Try the order with sig_type=0 (pure EOA)
# Maybe the error is different and reveals more info
# ====================================================================
from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import OrderArgs, CreateOrderOptions, OrderType, TickSize

TOKEN_CAVS = '91811271690939763569588501717168303099799014127066745654294854264052726562982'

print("\n=== Approach 1: Test sig_type=0 (EOA) order submission ===")
cl0 = ClobClient(
    host="https://clob.polymarket.com",
    key=os.environ["POLY_PRIVATE_KEY"],
    chain_id=137,
    signature_type=0,
    funder=EOA,
)
try:
    creds0 = cl0.derive_api_key()
    cl0.set_api_creds(creds0)
    from py_clob_client_v2.order_builder.constants import BUY
    order = cl0.create_order(OrderArgs(token_id=TOKEN_CAVS, price=0.32, size=5.0, side=BUY))
    print("  Order maker:", order.maker)
    print("  Order signer:", order.signer)
    print("  Order signatureType:", order.signatureType)
    result = cl0.post_order(order, OrderType.GTC)
    print("  Result:", result)
except Exception as e:
    print("  Error:", e)

# ====================================================================
# Approach 2: Check if there's a Polymarket endpoint for wallet info
# ====================================================================
print("\n=== Approach 2: Query CLOB auth endpoints for wallet info ===")
cl2 = ClobClient(
    host="https://clob.polymarket.com",
    key=os.environ["POLY_PRIVATE_KEY"],
    chain_id=137,
    signature_type=2,
    funder=EOA,
)
try:
    creds2 = cl2.derive_api_key()
    cl2.set_api_creds(creds2)
    print("  API key:", creds2.api_key[:20])

    # Try to get the L1 headers and check POLY-ADDRESS
    headers = cl2._l1_headers()
    print("  L1 headers:")
    for k, v in headers.items():
        print(f"    {k}: {v[:80]}")

    # Check what address the balance is for
    # Try GET /auth/derive-api-key to see what the response includes
    raw_resp = httpx.get(
        "https://clob.polymarket.com/auth/derive-api-key",
        headers=headers,
        timeout=10
    )
    print("  derive-api-key raw response:", raw_resp.status_code, raw_resp.text[:300])
except Exception as e:
    print("  Error:", e)
    traceback.print_exc()

# ====================================================================
# Approach 3: Try placing order as POLY_1271 with funder=EOA
# (just to see what error we get)
# ====================================================================
print("\n=== Approach 3: Try sig_type=3 (POLY_1271) with funder=EOA ===")
cl3 = ClobClient(
    host="https://clob.polymarket.com",
    key=os.environ["POLY_PRIVATE_KEY"],
    chain_id=137,
    signature_type=3,
    funder=EOA,
)
try:
    # sig_type=3 derive_api_key
    creds3 = cl3.derive_api_key()
    cl3.set_api_creds(creds3)
    print("  API key:", creds3.api_key[:20])
    from py_clob_client_v2.order_builder.constants import BUY
    order3 = cl3.create_order(OrderArgs(token_id=TOKEN_CAVS, price=0.32, size=5.0, side=BUY))
    print("  Order maker:", order3.maker)
    print("  Order signer:", order3.signer)
    print("  Order signatureType:", order3.signatureType)
    result3 = cl3.post_order(order3, OrderType.GTC)
    print("  Result:", result3)
except Exception as e:
    print("  Error:", e)

# ====================================================================
# Approach 4: Compute Gnosis Safe address for the EOA
# Polymarket uses Gnosis Safe 1.3.0
# ====================================================================
print("\n=== Approach 4: Compute Gnosis Safe address ===")
try:
    from eth_utils import keccak, to_checksum_address
    from eth_abi import encode as abi_encode

    # Gnosis Safe 1.3.0 on Polygon
    SAFE_SINGLETON = "0xd9Db270c1B5E3Bd161E8c8503c55cEABeE709552"
    SAFE_PROXY_FACTORY = "0xa6B71E26C5e0845f74c812102Ca7114b6a896AB2"

    # Need the proxy creation code from the factory
    # The GnosisSafeProxy init code = creation code from factory
    # Standard Gnosis Safe proxy bytecode (1.3.0)
    # This is the creationCode of GnosisSafeProxy contract
    PROXY_CREATION_CODE = bytes.fromhex(
        "608060405234801561001057600080fd5b506040516101e63803806101e68339"
        "8181016040528101906100349190610072565b6000805473ffffffffffffffffffffffffffffffffffffffff"
        "19166001600160a01b038316179055506100a2565b6000815190506100738161008b565b92915050565b"
        "60006020828403121561008457600080fd5b60006100928482850161005e565b91505092915050565b"
        "6001600160a01b03811681146100a857600080fd5b50565b"
        "6100358061006a6000396000f3fe"
    )  # This might not be exactly right
    print("  Need exact proxy creation code - skipping computation")
    print("  Gnosis Safe singleton:", SAFE_SINGLETON)
    print("  Gnosis Safe proxy factory:", SAFE_PROXY_FACTORY)
except Exception as e:
    print("  Error:", e)

# ====================================================================
# Approach 5: Directly query Polygon for transactions FROM the relay contract
# to find DepositWallet creation event
# ====================================================================
print("\n=== Approach 5: Find DepositWallet from relay contract ===")
try:
    RELAY_CONTRACT = "0x4cd00e387622c35bddb9b4c962c136462338bc31"
    RPCS = [
        "https://polygon-bor-rpc.publicnode.com",
        "https://polygon.drpc.org",
        "https://polygon-mainnet.public.blastapi.io",
    ]

    # Get the relay deposit tx receipt
    TX_HASH = "0x5fb6e6f53ed1aafd9c4ca9ac9e2a7bdf4da41289c69a1ccc2ccfe1b05d6bef24"

    for rpc in RPCS:
        try:
            res = httpx.post(rpc, json={
                "jsonrpc":"2.0","method":"eth_getTransactionReceipt",
                "params":[TX_HASH],"id":1
            }, timeout=15)
            data = res.json()
            if data.get("result"):
                receipt = data["result"]
                print(f"  Got receipt via {rpc}")
                print(f"  Status: {receipt.get('status')}")
                print(f"  Logs: {len(receipt.get('logs', []))} events")
                for i, log in enumerate(receipt.get("logs", [])):
                    print(f"\n  Log {i}: contract={log.get('address')}")
                    for t in log.get("topics", []):
                        print(f"    topic: {t}")
                    d = log.get("data","")
                    raw = d[2:] if d.startswith("0x") else d
                    for j in range(0, len(raw), 64):
                        chunk = raw[j:j+64]
                        if len(chunk) == 64:
                            if chunk[:24] == "0"*24:
                                print(f"    addr[{j//64}]: 0x{chunk[24:]}")
                            else:
                                print(f"    val[{j//64}]: {int(chunk, 16)}")
                break
            else:
                err = data.get("error","no result")
                print(f"  {rpc}: {err}")
        except Exception as e2:
            print(f"  {rpc}: {e2}")
except Exception as e:
    print("  Error:", e)
