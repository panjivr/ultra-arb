import httpx, json
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
print('Now UTC:', now.strftime('%Y-%m-%dT%H:%M'))

# Fetch more markets from Gamma API - try different filters
all_markets = []

# Try fetching with different sorts
for sort_field in ['volume24hr', 'volume1wk', 'liquidityClob']:
    resp = httpx.get(
        'https://gamma-api.polymarket.com/markets',
        params={
            'limit': 100,
            'active': 'true',
            'closed': 'false',
            'order': sort_field,
            'ascending': 'false',
        },
        timeout=20,
    )
    if resp.status_code == 200:
        data = resp.json()
        for m in data:
            cid = m.get('conditionId', '')
            if cid and cid not in [x.get('conditionId') for x in all_markets]:
                all_markets.append(m)

print(f'Unique active markets: {len(all_markets)}')

# Analysis
end_buckets = {'<1h': [], '1-24h': [], '1-7d': [], '>7d': [], 'no_date': []}
for m in all_markets:
    end_iso = m.get('endDateIso', '') or m.get('endDate', '')
    if not end_iso:
        end_buckets['no_date'].append(m)
        continue
    try:
        end = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
        hours = (end - now).total_seconds() / 3600
        if hours < 1: end_buckets['<1h'].append(m)
        elif hours <= 24: end_buckets['1-24h'].append(m)
        elif hours <= 168: end_buckets['1-7d'].append(m)
        else: end_buckets['>7d'].append(m)
    except:
        end_buckets['no_date'].append(m)

for k, v in end_buckets.items():
    print(f'  {k}: {len(v)} markets')

print()
print('Markets 1-7 days out:')
for m in end_buckets['1-7d'][:15]:
    end_iso = m.get('endDateIso', '') or m.get('endDate', '')
    end = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
    hours = (end - now).total_seconds() / 3600

    prices_raw = m.get('outcomePrices', '[]')
    if isinstance(prices_raw, str):
        try: prices = [float(p) for p in json.loads(prices_raw)]
        except: prices = []
    else:
        prices = [float(p) for p in prices_raw] if prices_raw else []

    token_ids_raw = m.get('clobTokenIds', '[]')
    if isinstance(token_ids_raw, str):
        try: token_ids = json.loads(token_ids_raw)
        except: token_ids = []
    else:
        token_ids = token_ids_raw or []

    accepting = m.get('acceptingOrders', '?')
    print(f'  [{hours:.0f}h] {m.get("question","")[:70]}')
    print(f'   prices: {prices} | accepting: {accepting} | vol24h: {m.get("volume24hr",0)}')
    if token_ids:
        print(f'   condition_id: {m.get("conditionId","")}')
        for i, tid in enumerate(token_ids[:2]):
            print(f'   token[{i}]: {tid}')
    print()
