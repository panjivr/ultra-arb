import httpx, os
from eth_utils import to_checksum_address

wallet = to_checksum_address('0x49884F6254cE54989E45dC93E34902b3BEBd47A9')
wallet_lower = wallet.lower()

# Check Polymarket data API profile/portfolio
print('=== Polymarket Data API ===')
for endpoint in [
    f'https://data-api.polymarket.com/portfolio?user={wallet}',
    f'https://data-api.polymarket.com/value?user={wallet}',
    f'https://data-api.polymarket.com/portfolio?user={wallet_lower}',
    f'https://gamma-api.polymarket.com/profile?id={wallet}',
]:
    try:
        r = httpx.get(endpoint, timeout=10)
        print(endpoint.split('?')[0].split('/')[-1], '->', r.status_code, r.text[:200])
    except Exception as e:
        print('Error:', e)

# Check mystery contract - try to decode it
print()
print('=== Mystery Contract 0x4cd0... ===')
RPC = 'https://polygon-bor-rpc.publicnode.com'

# Check if it has balanceOf mapping for user
padded = wallet[2:].lower().zfill(64)
mystery = '0x4cd00e387622c35bddb9b4c962c136462338bc31'

# Try getDeposit(address)
# Function selector: keccak256("getDeposit(address)")[:4]
# 0x9dee9a61 — common selector, let's try a few
for sig, name in [
    ('0x70a08231', 'balanceOf(address)'),
    ('0xf8b2cb4f', 'getBalance(address)'),
    ('0x27e235e3', 'balances(address)'),
]:
    data = sig + padded
    res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':mystery,'data':data},'latest'],'id':1}, timeout=10)
    result = res.json().get('result','0x')
    if result and result != '0x' and result != '0x' + '0'*64:
        val = int(result, 16)
        print(f'{name}: raw={val}, as_usdc={val/1e6}')
    else:
        print(f'{name}: 0 or empty')

# Check pUSD total supply and look for transfer events to exchange
pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
data_supply = '0x18160ddd'  # totalSupply()
res_ts = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':pUSD,'data':data_supply},'latest'],'id':1}, timeout=10)
print()
print('pUSD total supply:', int(res_ts.json().get('result','0x0'), 16) / 1e6)
