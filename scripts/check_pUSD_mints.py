import httpx
from eth_utils import to_checksum_address

wallet = to_checksum_address('0x49884F6254cE54989E45dC93E34902b3BEBd47A9')
RPC = 'https://polygon-bor-rpc.publicnode.com'
pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
mystery = '0x4cd00e387622c35bddb9b4c962c136462338bc31'
exchange_new = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'

transfer_topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
zero_topic = '0x' + '0' * 64  # mint from 0 address

# Get latest block
blk_res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_blockNumber','params':[],'id':1}, timeout=10)
latest = int(blk_res.json().get('result','0x0'), 16)
from_block = hex(latest - 10000)

print(f'Scanning blocks {int(from_block, 16)} - {latest}')
print()

# Check pUSD mint events (from 0x000... to exchange or user)
logs_mint = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'address': pUSD,
        'fromBlock': from_block,
        'toBlock': 'latest',
        'topics': [transfer_topic, zero_topic]
    }],'id':1}, timeout=15)
mints = logs_mint.json().get('result', [])
print(f'pUSD mint events (last 10k blocks): {len(mints)}')
for mint in mints[:5]:
    to_addr = '0x' + mint['topics'][2][-40:]
    val = int(mint['data'], 16) / 1e6
    print(f'  mint to: {to_addr} amount: {val} pUSD block: {int(mint["blockNumber"],16)}')

print()
# Check ALL pUSD transfers to user wallet
wallet_topic = '0x' + wallet[2:].lower().zfill(64)
logs_to_user = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'address': pUSD,
        'fromBlock': from_block,
        'toBlock': 'latest',
        'topics': [transfer_topic, None, wallet_topic]
    }],'id':1}, timeout=15)
to_user = logs_to_user.json().get('result', [])
print(f'pUSD transfers TO wallet: {len(to_user)}')

# Check mystery contract: what did it emit?
print()
mystery_addr = mystery
all_logs = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'address': mystery_addr,
        'fromBlock': from_block,
        'toBlock': 'latest',
    }],'id':1}, timeout=15)
mystery_logs = all_logs.json().get('result', [])
print(f'Mystery contract events (last 10k blocks): {len(mystery_logs)}')
for log in mystery_logs[:5]:
    print(f'  topics: {log.get("topics",[])}')
    print(f'  data[:40]: {log.get("data","")[:40]}')

# Check if mystery contract IS the exchange v2 depositor
print()
print('Mystery contract code snippet (first 200 bytes of bytecode):')
code_res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_getCode','params':[mystery,'latest'],'id':1}, timeout=10)
code = code_res.json().get('result','0x')
print(code[:100])
