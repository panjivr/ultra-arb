"""Find the DepositWallet (proxy) address via multiple methods."""
import os, httpx, json

with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

EOA = os.environ['POLY_WALLET_ADDRESS'].lower()
print("EOA:", EOA)

TX_HASH = "0x5fb6e6f53ed1aafd9c4ca9ac9e2a7bdf4da41289c69a1ccc2ccfe1b05d6bef24"
RELAY_CONTRACT = "0x4cd00e387622c35bddb9b4c962c136462338bc31"

RPCS = [
    "https://polygon.llamarpc.com",
    "https://endpoints.omniatech.io/v1/matic/mainnet/public",
    "https://1rpc.io/matic",
    "https://polygon.meowrpc.com",
    "https://polygon-pokt.nodies.app",
]

print("\n=== Getting tx receipt ===")
for rpc in RPCS:
    try:
        res = httpx.post(rpc, json={
            "jsonrpc":"2.0","method":"eth_getTransactionReceipt",
            "params":[TX_HASH],"id":1
        }, timeout=15)
        data = res.json()
        result = data.get("result")
        if result:
            print(f"RPC OK: {rpc}")
            print(f"Status: {result.get('status')}")
            print(f"BlockNumber: {int(result.get('blockNumber','0x0'),16)}")
            print(f"From: {result.get('from')}")
            print(f"To: {result.get('to')}")
            print(f"contractAddress: {result.get('contractAddress')}")
            logs = result.get("logs", [])
            print(f"Logs: {len(logs)}")
            for i, log in enumerate(logs):
                print(f"\n  Log {i}: from {log.get('address')}")
                for t in log.get("topics", []):
                    print(f"    topic: {t}")
                d = log.get("data","")
                raw = d[2:] if d.startswith("0x") else d
                for j in range(0, len(raw), 64):
                    chunk = raw[j:j+64]
                    if len(chunk) == 64:
                        if chunk[:24] == "0"*24 and chunk[24:] != "0"*40:
                            print(f"    addr[{j//64}]: 0x{chunk[24:]}")
                        else:
                            try:
                                print(f"    val[{j//64}]: {int(chunk,16)}")
                            except:
                                pass
            break
        elif data.get("error"):
            print(f"{rpc}: error {data['error']}")
        else:
            print(f"{rpc}: null result")
    except Exception as e:
        print(f"{rpc}: {e}")

print("\n=== Check relay contract getLogs wider range ===")
for rpc in RPCS:
    try:
        # Get block for tx first
        res = httpx.post(rpc, json={
            "jsonrpc":"2.0","method":"eth_getTransactionByHash",
            "params":[TX_HASH],"id":1
        }, timeout=15)
        data = res.json()
        result = data.get("result")
        if result:
            block_num = int(result.get("blockNumber","0x0"), 16)
            print(f"  Tx block: {block_num} via {rpc}")

            # Get logs from relay contract near that block
            logs_res = httpx.post(rpc, json={
                "jsonrpc":"2.0","method":"eth_getLogs",
                "params":[{
                    "address": RELAY_CONTRACT,
                    "fromBlock": hex(block_num - 2),
                    "toBlock": hex(block_num + 2),
                }],"id":2
            }, timeout=15)
            logs_data = logs_res.json()
            logs = logs_data.get("result", [])
            print(f"  Logs near tx: {len(logs)}")
            for i, log in enumerate(logs):
                print(f"\n  Log {i}: from {log.get('address')}")
                print(f"    txHash: {log.get('transactionHash')}")
                for t in log.get("topics", []):
                    print(f"    topic: {t}")
                d = log.get("data","")
                raw = d[2:] if d.startswith("0x") else d
                for j in range(0, len(raw), 64):
                    chunk = raw[j:j+64]
                    if len(chunk) == 64:
                        if chunk[:24] == "0"*24 and chunk[24:] != "0"*40:
                            print(f"    addr[{j//64}]: 0x{chunk[24:]}")
                        else:
                            try:
                                print(f"    val[{j//64}]: {int(chunk,16)}")
                            except:
                                pass
            break
        else:
            print(f"{rpc}: {data.get('error','null')}")
    except Exception as e:
        print(f"{rpc}: {e}")

print("\n=== Polymarket data API - positions for EOA ===")
try:
    res = httpx.get(
        f"https://data-api.polymarket.com/positions",
        params={"user": EOA, "limit": 5},
        timeout=10
    )
    print(f"positions status: {res.status_code}")
    if res.status_code == 200:
        print(f"positions: {res.text[:300]}")
except Exception as e:
    print(f"positions error: {e}")

print("\n=== Try CLOB /balance-allowance with different addresses ===")
try:
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

    # With sig_type=2 and no funder (defaults to EOA)
    cl = ClobClient(
        host="https://clob.polymarket.com",
        key=os.environ["POLY_PRIVATE_KEY"],
        chain_id=137,
        signature_type=2,
        funder=os.environ['POLY_WALLET_ADDRESS'],
    )
    creds = cl.derive_api_key()
    cl.set_api_creds(creds)

    # Make raw HTTP call to balance-allowance to see full response
    l2_headers = cl._l2_headers("GET", "/balance-allowance",
        body={"asset_type": "COLLATERAL"})
    print("  L2 headers POLY_ADDRESS:", l2_headers.get("POLY_ADDRESS"))

    res = httpx.get(
        "https://clob.polymarket.com/balance-allowance",
        headers={**l2_headers, "Content-Type": "application/json"},
        params={"asset_type": "COLLATERAL"},
        timeout=10
    )
    print(f"  balance raw: {res.status_code} {res.text[:500]}")
except Exception as e:
    print(f"  error: {e}")
    import traceback; traceback.print_exc()
