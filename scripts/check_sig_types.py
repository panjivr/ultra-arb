import os
with open('/home/reyogcapital165/reyog-capital/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

from py_clob_client_v2.client import ClobClient
import inspect

# Try different signature types
for sig_type in [0, 1, 2]:
    print(f'=== signature_type={sig_type} ===')
    try:
        cl = ClobClient(
            host='https://clob.polymarket.com',
            key=os.environ['POLY_PRIVATE_KEY'],
            chain_id=137,
            signature_type=sig_type,
            funder=os.environ['POLY_WALLET_ADDRESS'],
        )
        creds = cl.create_or_derive_api_key()
        cl.set_api_creds(creds)
        print('  Client created OK, api_key:', creds.api_key[:15] if creds and creds.api_key else 'NONE')

        # Check balance
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        bal = cl.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        print('  Balance:', bal.get('balance'))

        # Try to create an order (don't submit)
        from py_clob_client_v2.clob_types import OrderArgs
        from py_clob_client_v2.order_builder.constants import BUY
        token = '91811271690939763569588501717168303099799014127066745654294854264052726562982'
        order_args = OrderArgs(token_id=token, price=0.32, size=5.0, side=BUY)
        signed = cl.create_order(order_args)
        print('  Order signing: OK, hash:', getattr(signed, 'hash', None) or str(signed)[:50])

        # Check maker address in signed order
        if hasattr(signed, 'maker'):
            print('  Maker address:', signed.maker)
        if isinstance(signed, dict):
            print('  Order keys:', list(signed.keys()))
            print('  Maker:', signed.get('maker'))
            print('  SigType:', signed.get('signatureType'))
    except Exception as e:
        print('  Error:', e)
    print()
