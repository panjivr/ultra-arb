import httpx
from eth_utils import to_checksum_address

wallet = to_checksum_address('0x49884F6254cE54989E45dC93E34902b3BEBd47A9')
RPC = 'https://polygon-bor-rpc.publicnode.com'

# We know block 87099097 has the deposit
# Get block with txs to find our transaction
res = httpx.post(RPC, json={
    'jsonrpc':'2.0','method':'eth_getBlockByNumber',
    'params':['0x' + hex(87099097)[2:], True],  # true = include tx objects
    'id':1
}, timeout=30)
block = res.json().get('result', {})
txs = block.get('transactions', [])
print(f'Block 87099097 has {len(txs)} transactions')

# Find our transaction
wallet_lower = wallet.lower()
mystery = '0x4cd00e387622c35bddb9b4c962c136462338bc31'
for tx in txs:
    from_addr = tx.get('from', '').lower()
    to_addr = tx.get('to', '').lower()
    if from_addr == wallet_lower or (mystery.lower() in to_addr):
        print()
        print('FOUND TX:')
        print('  hash:', tx.get('hash'))
        print('  from:', tx.get('from'))
        print('  to:', tx.get('to'))
        print('  value:', int(tx.get('value','0x0'), 16))
        print('  input[:40]:', tx.get('input','')[:40])

# Get receipt for any matching tx
for tx in txs:
    if tx.get('from','').lower() == wallet_lower:
        tx_hash = tx.get('hash')
        print()
        print(f'Getting receipt for tx: {tx_hash}')
        receipt = httpx.post(RPC, json={
            'jsonrpc':'2.0','method':'eth_getTransactionReceipt',
            'params':[tx_hash],'id':1
        }, timeout=30).json().get('result', {})
        print('Status:', receipt.get('status'))
        print('Gas used:', int(receipt.get('gasUsed','0x0'), 16))
        logs = receipt.get('logs', [])
        print(f'Logs: {len(logs)}')
        for i, log in enumerate(logs):
            print(f'  Log {i}: contract={log["address"][:14]}')
            print(f'    topics[0]: {log["topics"][0] if log["topics"] else "none"}')
            data_preview = log.get("data","")
            if data_preview and data_preview != '0x':
                val = int(data_preview[:66] if len(data_preview) >= 66 else data_preview + '0'*(66-len(data_preview)), 16)
                print(f'    data val: {val/1e6} (as 6 dec)')
