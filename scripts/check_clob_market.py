import os
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

# Try CLOB-native market lookup for the Cavaliers market
cond_id = '0x8530b96422523df2024c4242021b58da538c5e94ba525e8f9893c3fc2f469160'

# Try get_clob_market_info
print('=== CLOB market info ===')
try:
    info = cl.get_clob_market_info(cond_id)
    print('Type:', type(info))
    print('Result:', str(info)[:500])
except Exception as e:
    print('Error:', e)

# Try get_market
print()
print('=== get_market ===')
try:
    m = cl.get_market(cond_id)
    print('Type:', type(m))
    if isinstance(m, dict):
        print('Keys:', list(m.keys()))
        print('tokens:', m.get('tokens', [])[:2])
        print('neg_risk:', m.get('neg_risk'))
    else:
        print('Result:', str(m)[:300])
except Exception as e:
    print('Error:', e)

# Try get_midpoint on one token
token = '91811271690939763569588501717168303099799014127066745654294854264052726562982'
print()
print('=== get_midpoint ===')
try:
    mid = cl.get_midpoint(token)
    print('midpoint:', mid)
except Exception as e:
    print('Error:', e)

# Try get_price
print()
print('=== get_price ===')
try:
    from py_clob_client_v2.clob_types import OrderSide
    p = cl.get_price(token, side='BUY')
    print('price BUY:', p)
except Exception as e:
    print('Error:', e)

# Try get_spread
print()
print('=== get_spread ===')
try:
    sp = cl.get_spread(token)
    print('spread:', sp)
except Exception as e:
    print('Error:', e)
