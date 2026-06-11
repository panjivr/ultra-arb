import os, httpx, json
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

# Get trades
headers = cl._l2_headers('GET', '/trades')
r = httpx.get('https://clob.polymarket.com/trades', headers=headers, params={'limit':5}, timeout=15)
print('=== Trades ===')
data = r.json()
trades = data.get('data', [])
print(f'Total trades: {len(trades)}')
for trade in trades[:3]:
    print(json.dumps(trade, indent=2)[:500])
    print()

# Get open orders
headers2 = cl._l2_headers('GET', '/open-orders')
r2 = httpx.get('https://clob.polymarket.com/open-orders', headers=headers2, timeout=15)
print('=== Open Orders ===')
print(r2.status_code, r2.text[:300])

# Get deposit/withdraw history
print()
print('=== Available endpoints ===')
for ep in ['/deposit', '/deposits', '/funding', '/transactions', '/activity', '/history']:
    try:
        h = cl._l2_headers('GET', ep)
        r3 = httpx.get('https://clob.polymarket.com' + ep, headers=h, timeout=5)
        print(f'{ep}: {r3.status_code} {r3.text[:100]}')
    except Exception as e:
        print(f'{ep}: error {e}')
