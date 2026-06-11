import httpx

mystery = '0x4cd00e387622c35bddb9b4c962c136462338bc31'

# Try 4byte.directory for function selector
sel = 'e8017952'
r = httpx.get(f'https://www.4byte.directory/api/v1/signatures/?hex_signature=0x{sel}', timeout=10)
print('4byte function selector:', r.status_code, r.text[:300])

# Try 4byte for event selector
event_topic = '0x49fed1d0b752ce30eee63c7a81133f3363b532fec5d4d7dd1ccfd005de4555e1'
r2 = httpx.get(f'https://www.4byte.directory/api/v1/event-signatures/?hex_signature={event_topic}', timeout=10)
print('4byte event sig:', r2.status_code, r2.text[:300])

# Polygonscan contract lookup (no API key needed for basic info)
r3 = httpx.get(
    f'https://api.polygonscan.com/api?module=contract&action=getsourcecode&address={mystery}&apikey=YourApiKeyToken',
    timeout=10
)
data = r3.json()
print('Polygonscan contract name:', data.get('result',[{}])[0].get('ContractName', 'unknown'))
print('Polygonscan compiler:', data.get('result',[{}])[0].get('CompilerVersion', 'N/A'))

# Try Polymarket API - maybe there's a /deposit endpoint
wallet = '0x49884f6254ce54989e45dc93e34902b3bebd47a9'
r4 = httpx.get(f'https://clob.polymarket.com/balance-allowance?signature_type=0&asset_type=COLLATERAL', timeout=10)
print('Unauth balance:', r4.status_code, r4.text[:100])
