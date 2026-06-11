import httpx
from eth_utils import to_checksum_address

wallet = to_checksum_address('0x49884F6254cE54989E45dC93E34902b3BEBd47A9')
RPC = 'https://polygon-bor-rpc.publicnode.com'
native_usdc = '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359'

transfer_topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
from_topic = '0x' + wallet[2:].lower().zfill(64)

blk_res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_blockNumber','params':[],'id':1}, timeout=10)
latest = int(blk_res.json().get('result','0x0'), 16)
from_block = hex(latest - 10000)
print('Scanning from block', int(from_block, 16), 'to', latest)

logs_res = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'address': native_usdc,
        'fromBlock': from_block,
        'toBlock': 'latest',
        'topics': [transfer_topic, from_topic]
    }],'id':1}, timeout=15)
logs = logs_res.json().get('result', [])
print('Outgoing USDC transfers:', len(logs))
for log in logs:
    to_addr = '0x' + log['topics'][2][-40:]
    value = int(log['data'], 16) / 1e6
    print('  to:', to_addr, 'value:', value, 'USDC', 'block:', int(log['blockNumber'], 16))

# Also check incoming to wallet
to_topic = '0x' + wallet[2:].lower().zfill(64)
logs_in_res = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'fromBlock': from_block,
        'toBlock': 'latest',
        'topics': [transfer_topic, None, to_topic]
    }],'id':1}, timeout=15)
logs_in = logs_in_res.json().get('result', [])
print('Incoming transfers to wallet:', len(logs_in))
for log in logs_in[:10]:
    tok = log['address']
    from_addr = '0x' + log['topics'][1][-40:]
    value_raw = int(log['data'], 16)
    print('  token:', tok[:12], 'from:', from_addr[:12], 'raw_value:', value_raw)
