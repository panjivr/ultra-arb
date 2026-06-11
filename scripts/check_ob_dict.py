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

token_cavs = '91811271690939763569588501717168303099799014127066745654294854264052726562982'
token_knicks = '90341073610328513874226762002064133262679100936760740635957635490606188341771'

ob = cl.get_order_book(token_cavs)
print('Order book dict keys:', list(ob.keys()))
import json
print('Full OB:', json.dumps(ob, indent=2)[:800])
