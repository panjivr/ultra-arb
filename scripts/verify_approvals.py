import os, time
with open("/home/reyogcapital165/reyog-capital/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from eth_account import Account
from eth_utils import to_checksum_address
import httpx

RPC  = "https://polygon-bor-rpc.publicnode.com"
USDC = to_checksum_address("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359")
POLY_CONTRACTS = [
    "0xE111180000d2663C0091e4f400237545B87B996B",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
    "0xe2222d279d744050d28e00520010520000310F59",
]
acct = Account.from_key("0x" + os.environ["POLY_PRIVATE_KEY"])

def rpc(method, params):
    r = httpx.post(RPC, json={"jsonrpc":"2.0","method":method,"params":params,"id":1}, timeout=10)
    return r.json()

cur_nonce = int(rpc("eth_getTransactionCount", [acct.address, "latest"]).get("result","0x0"), 16)
print("Current confirmed nonce:", cur_nonce, "(was 12 before approvals)")
print("Approvals confirmed:", cur_nonce - 12, "of 3")
print()

# Check on-chain allowance for each Polymarket contract
print("On-chain allowances for native USDC -> Polymarket contracts:")
for c in POLY_CONTRACTS:
    owner_pad   = acct.address[2:].lower().zfill(64)
    spender_pad = c[2:].lower().zfill(64)
    data = "0xdd62ed3e" + owner_pad + spender_pad
    res  = rpc("eth_call", [{"to": USDC, "data": data}, "latest"]).get("result", "0x0")
    val  = int(res, 16)
    if val > 10**30:
        display = "MAX (unlimited)"
    else:
        display = "$%.4f" % (val / 1e6)
    print("  %s... = %s" % (c[:22], display))

print()
# Re-check Polymarket CLOB balance
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
cl = ClobClient(host="https://clob.polymarket.com",
    key=os.environ["POLY_PRIVATE_KEY"], chain_id=137,
    signature_type=0, funder=acct.address)
cl.set_api_creds(cl.create_or_derive_api_creds())
cl.update_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
time.sleep(5)
bal = cl.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
usdc = int(bal.get("balance", 0)) / 1e6
print("Polymarket CLOB sees USDC: $%.4f" % usdc)
print("Allowances per contract:", bal.get("allowances", {}))
