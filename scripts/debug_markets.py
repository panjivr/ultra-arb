import os
with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient
import inspect, httpx

cl = ClobClient(
    host='https://clob.polymarket.com',
    key=os.environ['POLY_PRIVATE_KEY'],
    chain_id=137,
    signature_type=0,
    funder=os.environ['POLY_WALLET_ADDRESS'],
)
creds = cl.create_or_derive_api_key()
cl.set_api_creds(creds)

# Check get_markets signature
print('get_markets sig:', inspect.signature(cl.get_markets))
print()

# Try get_markets
try:
    resp = cl.get_markets(next_cursor='')
    print('Type:', type(resp))
    if isinstance(resp, dict):
        print('Keys:', list(resp.keys()))
        data = resp.get('data', [])
        print('Data length:', len(data))
        if data:
            print('First market:', data[0] if isinstance(data[0], dict) else str(data[0])[:200])
    else:
        print('Resp:', str(resp)[:200])
except Exception as e:
    print('Error:', e)

# Try get_simplified_markets
print()
print('Trying get_simplified_markets...')
try:
    resp2 = cl.get_simplified_markets(next_cursor='')
    print('Type:', type(resp2))
    if isinstance(resp2, dict):
        data2 = resp2.get('data', [])
        print('Data length:', len(data2))
        if data2:
            m = data2[0]
            if isinstance(m, dict):
                print('First market keys:', list(m.keys()))
                print('First market question:', m.get('question', '')[:100])
            else:
                print('First market:', str(m)[:200])
except Exception as e:
    print('Error:', e)

# Try direct Gamma API
print()
print('Trying Gamma API...')
r = httpx.get('https://gamma-api.polymarket.com/markets?limit=5&active=true&order=volume&ascending=false', timeout=15)
print('Status:', r.status_code)
if r.status_code == 200:
    data3 = r.json()
    print('Type:', type(data3))
    if isinstance(data3, list):
        print('Count:', len(data3))
        if data3:
            m = data3[0]
            print('Keys:', list(m.keys()) if isinstance(m, dict) else 'not dict')
            print('Question:', m.get('question', '')[:100] if isinstance(m, dict) else str(m)[:100])
