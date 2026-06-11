"""Find the Polymarket DepositWallet (proxy) address for our EOA."""
import os, httpx, json

with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

RELAY_CONTRACT = "0x4cd00e387622c35bddb9b4c962c136462338bc31"
EOA = os.environ['POLY_WALLET_ADDRESS'].lower()
print("EOA:", EOA)

RPCS = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.drpc.org",
    "https://polygon-mainnet.public.blastapi.io",
]

def rpc_call(rpc, method, params, timeout=15):
    res = httpx.post(rpc, json={"jsonrpc":"2.0","method":method,"params":params,"id":1}, timeout=timeout)
    return res.json()

def get_logs(rpc, address, from_block, to_block, topics=None):
    params = [{"address": address, "fromBlock": hex(from_block), "toBlock": hex(to_block)}]
    if topics:
        params[0]["topics"] = topics
    return rpc_call(rpc, "eth_getLogs", params)

# Find current block
for rpc in RPCS:
    try:
        data = rpc_call(rpc, "eth_blockNumber", [])
        if data.get("result"):
            current_block = int(data["result"], 16)
            print(f"Current block: {current_block} via {rpc}")

            # Try to get recent logs from relay contract (last ~50k blocks = ~1 day)
            from_block = current_block - 200000  # ~2-3 days
            print(f"Fetching logs from block {from_block} to {current_block}...")

            logs_data = get_logs(rpc, RELAY_CONTRACT, from_block, current_block)
            logs = logs_data.get("result", [])

            if isinstance(logs, list):
                print(f"Got {len(logs)} logs")
                # Filter for logs involving our EOA
                eoa_padded = EOA.lower().replace("0x","").zfill(64)
                for log in logs:
                    topics = log.get("topics", [])
                    data_field = log.get("data", "")
                    log_str = " ".join(topics) + " " + data_field
                    if EOA.lower()[2:] in log_str.lower():
                        print("\nFound log involving our EOA!")
                        print("  block:", log.get("blockNumber"))
                        print("  txHash:", log.get("transactionHash"))
                        print("  topics:", topics)
                        raw = data_field[2:] if data_field.startswith("0x") else data_field
                        for j in range(0, len(raw), 64):
                            chunk = raw[j:j+64]
                            if len(chunk) == 64:
                                if chunk[:24] == "0"*24:
                                    print(f"  addr[{j//64}]: 0x{chunk[24:]}")
                                else:
                                    print(f"  val[{j//64}]: {int(chunk, 16)}")
                break
            else:
                print("Error:", logs_data.get("error"))
    except Exception as e:
        print(f"RPC {rpc}: {e}")

# Also try computing the Gnosis Safe address for our EOA
# Polymarket uses Gnosis Safe v1.3.0 proxy
print("\n--- Computing Gnosis Safe address ---")
try:
    from eth_utils import keccak, to_checksum_address
    from eth_abi import encode

    # Gnosis Safe Proxy Factory 1.3.0 on Polygon
    FACTORY = "0xa6B71E26C5e0845f74c812102Ca7114b6a896AB2"
    # GnosisSafe mastercopy 1.3.0 on Polygon
    SINGLETON = "0xd9Db270c1B5E3Bd161E8c8503c55cEABeE709552"

    # The salt for Polymarket Safes is typically keccak(owners_array, threshold)
    # With single owner = EOA, threshold = 1
    # initializer = setupCall(owners=[EOA], threshold=1, ...)

    # Actually Polymarket might use a different deployment pattern
    # Let's try to compute the proxy address using standard Gnosis Safe CREATE2 formula

    # initCode = concat(proxyCreationCode, abi.encode(singleton))
    # On Gnosis Safe Proxy Factory 1.3.0, proxy creation code is fixed
    # The salt in CREATE2 is keccak(initializer, saltNonce)

    print("Would need factory proxy creation code to compute address")
    print("Trying alternative: query Polymarket CLOB for registered address")

    # The API key we derive is linked to an address. Let's see what that address is
    # by checking the create_api_key request body
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.headers.headers import create_level_1_headers
    import inspect

    cl = ClobClient(
        host="https://clob.polymarket.com",
        key=os.environ['POLY_PRIVATE_KEY'],
        chain_id=137,
        signature_type=2,
        funder=os.environ['POLY_WALLET_ADDRESS'],
    )

    print("\ncl.builder.funder:", cl.builder.funder)
    print("cl.builder.signature_type:", cl.builder.signature_type)
    print("cl.signer.address():", cl.signer.address())

    # Get L1 headers to see what address is used in auth
    headers = cl._l1_headers()
    print("\nL1 auth headers:")
    for k, v in headers.items():
        if k.lower() in ("poly-address", "poly-signature", "poly-timestamp", "poly-nonce"):
            print(f"  {k}: {v[:80]}")

except Exception as e:
    print("Error:", e)
    import traceback; traceback.print_exc()
