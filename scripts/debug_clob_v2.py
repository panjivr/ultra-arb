import os, time, httpx
with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

cl = ClobClient(
    host='https://clob.polymarket.com',
    key=os.environ['POLY_PRIVATE_KEY'],
    chain_id=137,
    signature_type=0,
    funder=os.environ['POLY_WALLET_ADDRESS'],
)
creds = cl.create_or_derive_api_key()
cl.set_api_creds(creds)
print('API key:', creds.api_key[:20] if creds and creds.api_key else 'NONE')
print('API secret:', creds.api_secret[:10] if creds and hasattr(creds,'api_secret') else 'N/A')
print('Funder:', cl.funder if hasattr(cl, 'funder') else 'N/A')

# Try update_balance_allowance directly via raw HTTP to see error
# Build the L2 headers manually
params_str = 'asset_type=COLLATERAL&signature_type=0'
update_url = f'https://clob.polymarket.com/balance-allowance/update?{params_str}'
upd_resp = httpx.get(update_url, timeout=15)
print('Update raw response:', upd_resp.status_code, upd_resp.text[:200])

# Try the CLOB /profile endpoint
profile_url = 'https://clob.polymarket.com/profile'
wallet = os.environ['POLY_WALLET_ADDRESS']
# This might require auth
headers = cl._l2_headers('GET', '/profile') if hasattr(cl, '_l2_headers') else {}
prof_resp = httpx.get(profile_url, headers=headers, timeout=15)
print('Profile:', prof_resp.status_code, prof_resp.text[:200])

# Check pUSD allowance for exchange contracts
from eth_utils import to_checksum_address
wallet_chk = to_checksum_address(wallet)
RPC = 'https://polygon-bor-rpc.publicnode.com'
pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'

exchange_contracts = [
    ('exchange_v2', '0xE111180000d2663C0091e4f400237545B87B996B'),
    ('neg_risk_v2', '0xe2222d279d744050d28e00520010520000310F59'),
    ('neg_risk_adapter', '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296'),
    ('new_exchange', '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'),
]
print()
print('pUSD allowances for exchange contracts:')
owner_pad = wallet_chk[2:].lower().zfill(64)
for name, contract in exchange_contracts:
    spender_pad = contract[2:].lower().zfill(64)
    data = '0xdd62ed3e' + owner_pad + spender_pad
    res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':pUSD,'data':data},'latest'],'id':1}, timeout=10)
    val = int(res.json().get('result','0x0'), 16)
    display = 'MAX' if val > 10**30 else str(val/1e6)
    print(f'  {name}: {display}')

# Also check pUSD balance
padded = wallet_chk[2:].lower().zfill(64)
pUSD_data = '0x70a08231' + padded
pUSD_res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':pUSD,'data':pUSD_data},'latest'],'id':1}, timeout=10)
print('pUSD balance in wallet:', int(pUSD_res.json().get('result','0x0'), 16) / 1e6)

# Mystery contract - decode what function was called
# Function selector: 0xe8017952
# Try to identify
print()
print('Mystery contract deposit function: 0xe8017952')
print('Possible: deposit(address), depositFor(address), etc.')
