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

# Markets to check with their token IDs
markets = [
    ('Cavaliers vs. Knicks (Cavs)', '91811271690939763569588501717168303099799014127066745654294854264052726562982'),
    ('Cavaliers vs. Knicks (Knicks)', '90341073610328513874226762002064133262679100936760740635957635490606188341771'),
    ('Spurs vs. Thunder (Spurs)', '52263517794885987721295730397921579339326307520815595834678501811222224358828'),
    ('Spurs vs. Thunder (Thunder)', '115707715167373261399734260542020796347329928638142033825445370749810433822651'),
    ('Iran May24 Yes', '28593215534345447362156321620838626774652503878031452558083665828202001699551'),
    ('Iran May24 No', '70200204795647665205365524365288012592454986193501445097094459968896854757537'),
]

print('Checking order books:')
for name, token_id in markets:
    try:
        ob = cl.get_order_book(token_id)
        bids = ob.bids if hasattr(ob, 'bids') and ob.bids else []
        asks = ob.asks if hasattr(ob, 'asks') and ob.asks else []
        best_bid = float(bids[0].price) if bids else None
        best_ask = float(asks[0].price) if asks else None
        spread = round(best_ask - best_bid, 4) if best_bid and best_ask else None
        print(f'  {name}: bid={best_bid} ask={best_ask} spread={spread}')
    except Exception as e:
        print(f'  {name}: ERROR {e}')
