import os, time, httpx, json
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

# Try different approaches to get balance
print('=== Approach 1: get_balance_allowance COLLATERAL ===')
bal = cl.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print('Result:', bal)

print()
print('=== Approach 2: Direct HTTP GET with auth headers ===')
# Build headers manually to see what's happening
import hashlib, hmac, base64
from eth_account import Account
from eth_account.messages import encode_defunct

# The L2 headers need to be built with the API key
api_key = creds.api_key
api_secret = creds.api_secret
api_passphrase = creds.api_passphrase if hasattr(creds, 'api_passphrase') else ''

print(f'API Key: {api_key[:20]}...')
print(f'API Secret: {api_secret[:10]}...')

# Try hitting balance endpoint directly
endpoints = [
    '/balance-allowance?asset_type=COLLATERAL&signature_type=0',
    '/balance-allowance',
    '/trading-allowance',
]
for ep in endpoints:
    headers = cl._l2_headers('GET', ep.split('?')[0]) if '?' in ep else cl._l2_headers('GET', ep)
    url = 'https://clob.polymarket.com' + ep
    r = httpx.get(url, headers=headers, timeout=10)
    print(f'{ep}: {r.status_code} {r.text[:200]}')

# Check if there's a wallet/profile endpoint
print()
print('=== Checking user-related endpoints ===')
user_endpoints = [
    '/user-market-trade-history',
    '/orders',
    '/trades',
]
for ep in user_endpoints:
    try:
        headers = cl._l2_headers('GET', ep)
        r = httpx.get('https://clob.polymarket.com' + ep, headers=headers, timeout=10)
        print(f'{ep}: {r.status_code} {r.text[:150]}')
    except Exception as e:
        print(f'{ep}: error {e}')
