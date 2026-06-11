import os, httpx
with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient

cl = ClobClient(
    host='https://clob.polymarket.com',
    key=os.environ['POLY_PRIVATE_KEY'],
    chain_id=137,
    signature_type=0,
    funder=os.environ['POLY_WALLET_ADDRESS'],
)
creds = cl.create_or_derive_api_key()
cl.set_api_creds(creds)

wallet = os.environ['POLY_WALLET_ADDRESS']

# Try the Gamma/Strapi API - this is the public-facing user balance API
endpoints = [
    # Gamma API
    f'https://gamma-api.polymarket.com/user?id={wallet}',
    f'https://gamma-api.polymarket.com/users/{wallet}',
    # Data API with checksummed address
    f'https://data-api.polymarket.com/value?user={wallet.lower()}',
    f'https://data-api.polymarket.com/portfolio?user={wallet.lower()}',
    # CLOB direct
    'https://clob.polymarket.com/api-keys',
    'https://clob.polymarket.com/ok',
]

for url in endpoints:
    try:
        r = httpx.get(url, timeout=10)
        print(f'{url.split("?")[0].split("/")[-1]}: {r.status_code} {r.text[:200]}')
    except Exception as e:
        print(f'error: {e}')

# Check if CLOB has a /user endpoint
print()
for ep in ['/user', '/account', '/wallet', '/collateral']:
    try:
        h = cl._l2_headers('GET', ep)
        r = httpx.get('https://clob.polymarket.com' + ep, headers=h, timeout=5)
        print(f'{ep}: {r.status_code} {r.text[:150]}')
    except Exception as e:
        print(f'{ep}: {e}')

# Try placing a small dry_run to see if order signing works
print()
print('=== Testing order signing (dry run) ===')
from py_clob_client_v2.clob_types import OrderArgs
from py_clob_client_v2.order_builder.constants import BUY

# Use a known token from trade history
token_id = '76342869644611910338562404972751458819786800879940154277190887429435484703585'
try:
    order_args = OrderArgs(
        token_id=token_id,
        price=0.05,
        size=1.0,
        side=BUY,
    )
    signed = cl.create_order(order_args)
    print('Order signing: SUCCESS')
    print('Order hash:', getattr(signed, 'hash', None) or getattr(signed, 'id', None))
except Exception as e:
    print('Order signing failed:', e)
