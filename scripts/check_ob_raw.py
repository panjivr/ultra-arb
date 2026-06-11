import os, httpx
with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient
import inspect

cl = ClobClient(
    host='https://clob.polymarket.com',
    key=os.environ['POLY_PRIVATE_KEY'],
    chain_id=137,
    signature_type=0,
    funder=os.environ['POLY_WALLET_ADDRESS'],
)
creds = cl.create_or_derive_api_key()
cl.set_api_creds(creds)

token_cavs = '91811271690939763569588501717168303099799014127066745654294854264052726562982'
cond_id = '0x8530b96422523df2024c4242021b58da538c5e94ba525e8f9893c3fc2f469160'

# Get raw get_order_book response
print('get_order_book source:')
print(inspect.getsource(cl.get_order_book))
print()

ob = cl.get_order_book(token_cavs)
print('Order book type:', type(ob))
print('Order book dir:', [a for a in dir(ob) if not a.startswith('_')])
print('Bids:', ob.bids if hasattr(ob, 'bids') else 'N/A')
print('Asks:', ob.asks if hasattr(ob, 'asks') else 'N/A')
print('Hash:', ob.hash if hasattr(ob, 'hash') else 'N/A')
if hasattr(ob, '__dict__'):
    print('Dict:', ob.__dict__)

# Also check minimum order size
m = cl.get_market(cond_id)
print()
print('minimum_order_size:', m.get('minimum_order_size'))
print('minimum_tick_size:', m.get('minimum_tick_size'))
print('accepting_orders:', m.get('accepting_orders'))
