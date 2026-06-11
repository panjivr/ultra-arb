"""
Get the proxy wallet and safe wallet addresses for our EOA by calling
the CTFExchangeV2 contract directly.

CTFExchangeV2 on Polygon: 0xE111180000d2663C0091e4f400237545B87B996B
Functions:
  getProxyWalletAddress(address) -> address  (POLY_PROXY, sig_type=1)
  getSafeWalletAddress(address) -> address   (POLY_GNOSIS_SAFE, sig_type=2)
"""
import os, httpx
from eth_utils import keccak, to_checksum_address
from eth_abi import encode as abi_encode

with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

EOA = os.environ['POLY_WALLET_ADDRESS']
print("EOA:", EOA)

CTF_EXCHANGE_V2 = "0xE111180000d2663C0091e4f400237545B87B996B"

RPCS = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://1rpc.io/matic",
    "https://polygon-pokt.nodies.app",
]

def eth_call(rpc, contract, data, timeout=15):
    res = httpx.post(rpc, json={
        "jsonrpc": "2.0", "method": "eth_call",
        "params": [{"to": contract, "data": data}, "latest"],
        "id": 1
    }, timeout=timeout)
    return res.json().get("result", "0x")

def get_selector(fn_sig):
    return keccak(text=fn_sig)[:4].hex()

def encode_address_call(fn_sig, addr):
    sel = get_selector(fn_sig)
    addr_padded = addr.lower().replace("0x", "").zfill(64)
    return "0x" + sel + addr_padded

def decode_address(result):
    if result and len(result) >= 66:
        return "0x" + result[-40:]
    return None

for rpc in RPCS:
    try:
        # Test connection
        block_res = httpx.post(rpc, json={"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}, timeout=10)
        if not block_res.json().get("result"):
            print(f"{rpc}: no block number")
            continue
        print(f"\nUsing RPC: {rpc}")

        # getProxyWalletAddress(EOA)
        data = encode_address_call("getProxyWalletAddress(address)", EOA)
        result = eth_call(rpc, CTF_EXCHANGE_V2, data)
        proxy_addr = decode_address(result)
        print(f"getProxyWalletAddress({EOA[:10]}...) = {proxy_addr}")

        # getSafeWalletAddress(EOA)
        data2 = encode_address_call("getSafeWalletAddress(address)", EOA)
        result2 = eth_call(rpc, CTF_EXCHANGE_V2, data2)
        safe_addr = decode_address(result2)
        print(f"getSafeWalletAddress({EOA[:10]}...) = {safe_addr}")

        # Check if proxy wallet is deployed (has code)
        if proxy_addr:
            proxy_code = eth_call(rpc, proxy_addr, "0x")
            # Actually check code via eth_getCode
            code_res = httpx.post(rpc, json={
                "jsonrpc":"2.0","method":"eth_getCode",
                "params":[proxy_addr, "latest"],"id":2
            }, timeout=10)
            code = code_res.json().get("result","0x")
            print(f"ProxyWallet code: {code[:20]}... (len={len(code)})")
            is_deployed = len(code) > 4  # 0x + at least 1 byte
            print(f"ProxyWallet deployed: {is_deployed}")

        if safe_addr:
            code_res2 = httpx.post(rpc, json={
                "jsonrpc":"2.0","method":"eth_getCode",
                "params":[safe_addr, "latest"],"id":3
            }, timeout=10)
            code2 = code_res2.json().get("result","0x")
            print(f"SafeWallet code: {code2[:20]}... (len={len(code2)})")
            is_safe_deployed = len(code2) > 4
            print(f"SafeWallet deployed: {is_safe_deployed}")

        # Store addresses for order test
        print(f"\nProxy wallet address: {proxy_addr}")
        print(f"Safe wallet address: {safe_addr}")

        # Try placing order with sig_type=1 (POLY_PROXY) and funder=proxy_wallet
        print("\n=== Test POLY_PROXY (sig_type=1) with proxy wallet address ===")
        if proxy_addr:
            try:
                from py_clob_client_v2.client import ClobClient
                from py_clob_client_v2.clob_types import OrderArgs, OrderType
                from py_clob_client_v2.order_builder.constants import BUY

                TOKEN_CAVS = '91811271690939763569588501717168303099799014127066745654294854264052726562982'

                cl = ClobClient(
                    host="https://clob.polymarket.com",
                    key=os.environ["POLY_PRIVATE_KEY"],
                    chain_id=137,
                    signature_type=1,  # POLY_PROXY
                    funder=proxy_addr,
                )
                creds = cl.derive_api_key()
                cl.set_api_creds(creds)

                order = cl.create_order(OrderArgs(token_id=TOKEN_CAVS, price=0.32, size=5.0, side=BUY))
                print(f"  Order maker: {order.maker}")
                print(f"  Order signer: {order.signer}")
                print(f"  Order signatureType: {order.signatureType}")

                result = cl.post_order(order, OrderType.GTC)
                print(f"  SUCCESS: {result}")
            except Exception as e:
                print(f"  Error: {e}")

        # Try with safe_addr
        print("\n=== Test POLY_GNOSIS_SAFE (sig_type=2) with computed safe address ===")
        if safe_addr:
            try:
                from py_clob_client_v2.client import ClobClient
                from py_clob_client_v2.clob_types import OrderArgs, OrderType
                from py_clob_client_v2.order_builder.constants import BUY

                TOKEN_CAVS = '91811271690939763569588501717168303099799014127066745654294854264052726562982'

                cl2 = ClobClient(
                    host="https://clob.polymarket.com",
                    key=os.environ["POLY_PRIVATE_KEY"],
                    chain_id=137,
                    signature_type=2,  # POLY_GNOSIS_SAFE
                    funder=safe_addr,
                )
                creds2 = cl2.derive_api_key()
                cl2.set_api_creds(creds2)

                from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
                bal = cl2.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
                print(f"  Safe balance: {bal.get('balance')}")

                order2 = cl2.create_order(OrderArgs(token_id=TOKEN_CAVS, price=0.32, size=5.0, side=BUY))
                print(f"  Order maker: {order2.maker}")
                print(f"  Order signer: {order2.signer}")
                print(f"  Order signatureType: {order2.signatureType}")

                result2 = cl2.post_order(order2, OrderType.GTC)
                print(f"  SUCCESS: {result2}")
            except Exception as e:
                print(f"  Error: {e}")

        break
    except Exception as e:
        print(f"{rpc}: {e}")
