import httpx
from eth_utils import to_checksum_address

wallet = to_checksum_address('0x49884F6254cE54989E45dC93E34902b3BEBd47A9')
RPC = 'https://polygon-bor-rpc.publicnode.com'

# Address that received the USDC
mystery_addr = '0x4cd00e387622c35bddb9b4c962c136462338bc31'

# Check if it's a contract (has code)
res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_getCode','params':[mystery_addr,'latest'],'id':1}, timeout=10)
code = res.json().get('result','0x')
print('Mystery addr code length:', len(code))
print('Is contract:', len(code) > 2)

# Check exchange contract balance for our wallet
# Exchange v2: 0xE111180000d2663C0091e4f400237545B87B996B
# Try balanceOf(address) - function sig: 0x70a08231
exchange_v2 = '0xE111180000d2663C0091e4f400237545B87B996B'
padded = wallet[2:].lower().zfill(64)
data = '0x70a08231' + padded
res2 = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':exchange_v2,'data':data},'latest'],'id':1}, timeout=10)
print('Exchange v2 balanceOf user:', int(res2.json().get('result','0x0'), 16) / 1e6)

# New exchange: 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
exchange_new = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'
res3 = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':exchange_new,'data':data},'latest'],'id':1}, timeout=10)
print('New exchange balanceOf user:', int(res3.json().get('result','0x0'), 16) / 1e6)

# pUSD address
pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
res4 = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':pUSD,'data':data},'latest'],'id':1}, timeout=10)
print('pUSD balance user:', int(res4.json().get('result','0x0'), 16) / 1e6)

# Check mystery contract balance of pUSD (if it's an exchange, it holds pUSD)
mystery_padded = mystery_addr[2:].lower().zfill(64)
data_mystery = '0x70a08231' + mystery_padded
res5 = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':pUSD,'data':data_mystery},'latest'],'id':1}, timeout=10)
print('Mystery addr pUSD balance:', int(res5.json().get('result','0x0'), 16) / 1e6)

# Check mystery contract USDC balance
native_usdc = '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359'
res6 = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':native_usdc,'data':data_mystery},'latest'],'id':1}, timeout=10)
print('Mystery addr USDC balance:', int(res6.json().get('result','0x0'), 16) / 1e6)

# What does Polymarket v2 API say about wallet positions?
print()
print('Checking Polymarket REST API...')
positions_res = httpx.get(
    'https://data-api.polymarket.com/positions',
    params={'user': wallet, 'limit': 5},
    timeout=15
)
print('Positions status:', positions_res.status_code)
if positions_res.status_code == 200:
    pos = positions_res.json()
    print('Positions:', pos[:2] if pos else 'empty')
