import httpx
from eth_utils import to_checksum_address

wallet = to_checksum_address('0x49884F6254cE54989E45dC93E34902b3BEBd47A9')
RPC = 'https://polygon-bor-rpc.publicnode.com'

# The deposit block was 87099097
deposit_block = hex(87099097)
deposit_block_end = hex(87099100)

print('Checking deposit block 87099097...')

# Get all events at that block from mystery contract
mystery = '0x4cd00e387622c35bddb9b4c962c136462338bc31'
all_logs = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'address': mystery,
        'fromBlock': deposit_block,
        'toBlock': deposit_block_end,
    }],'id':1}, timeout=30)
logs = all_logs.json().get('result', [])
print(f'Mystery contract events in deposit block: {len(logs)}')
for log in logs:
    print(f'  topics: {log.get("topics",[])}')
    print(f'  data: {log.get("data","")[:80]}')

# Get all events in that block window (no address filter)
all_wallet_logs = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getLogs',
    'params':[{
        'fromBlock': deposit_block,
        'toBlock': deposit_block_end,
    }],'id':1}, timeout=30)
all_logs_result = all_wallet_logs.json().get('result', [])
print(f'Total events in deposit block range: {len(all_logs_result)}')

# Filter for anything involving our wallet or pUSD minting
pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
wallet_lower = wallet.lower()
for log in all_logs_result:
    topics = log.get('topics', [])
    log_str = str(log).lower()
    if pUSD.lower() in log_str or wallet_lower[2:] in log_str:
        print()
        print('RELEVANT LOG:')
        print('  contract:', log.get('address'))
        print('  topics:', topics[:2])
        print('  data[:60]:', log.get('data','')[:60])
