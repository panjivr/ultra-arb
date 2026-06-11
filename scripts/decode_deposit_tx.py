import httpx
from eth_utils import to_checksum_address

RPC = 'https://polygon-bor-rpc.publicnode.com'
TX_HASH = '0xb23ec5b0b977f696663bbe3c9662dcf25d4948cc71060624b5b10192f87a6f7e'

# Get full transaction
res = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_getTransactionByHash','params':[TX_HASH],'id':1}, timeout=15)
tx = res.json().get('result', {})
input_data = tx.get('input', '')
print('Input data:')
print(input_data)
print()

# Decode depositErc20(address,address,uint256,bytes32)
# Remove function selector (4 bytes = 8 hex chars)
params = input_data[10:]
chunk_size = 64
chunks = [params[i:i+chunk_size] for i in range(0, len(params), chunk_size)]
print(f'Parameter chunks ({len(chunks)} params):')
for i, chunk in enumerate(chunks):
    val = int(chunk, 16)
    # Try as address
    addr = '0x' + chunk[-40:]
    print(f'  param[{i}]: raw={chunk}')
    print(f'    as_address: {addr}')
    print(f'    as_uint256: {val}')
    print(f'    as_usdc_6dec: {val/1e6}')
    print()

# Get the receipt logs in detail
receipt = httpx.post(RPC, json={'jsonrpc':'2.0','method':'eth_getTransactionReceipt','params':[TX_HASH],'id':1}, timeout=15).json().get('result',{})
print('Receipt logs:')
for i, log in enumerate(receipt.get('logs', [])):
    print(f'Log {i}: contract={log["address"]}')
    for j, topic in enumerate(log.get('topics',[])):
        print(f'  topic[{j}]: {topic}')
    data = log.get('data','')
    if data and data != '0x':
        data_chunks = [data[2+k*64:2+(k+1)*64] for k in range(len(data[2:])//64)]
        for k, dc in enumerate(data_chunks):
            val = int(dc, 16) if dc else 0
            print(f'  data[{k}]: {dc} = {val} = {val/1e6} (6dec)')
    print()
