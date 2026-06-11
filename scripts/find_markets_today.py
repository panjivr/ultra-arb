import httpx, json
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
print('Now UTC:', now.strftime('%Y-%m-%dT%H:%M'))

# Fetch many markets and use full endDate (with time)
all_markets = []
for sort_field in ['volume24hr', 'volume1wk', 'volume1mo']:
    resp = httpx.get(
        'https://gamma-api.polymarket.com/markets',
        params={'limit': 100, 'active': 'true', 'closed': 'false', 'order': sort_field, 'ascending': 'false'},
        timeout=20,
    )
    if resp.status_code == 200:
        for m in resp.json():
            cid = m.get('conditionId', '')
            if cid and cid not in [x.get('conditionId') for x in all_markets]:
                all_markets.append(m)

print(f'Unique markets: {len(all_markets)}')

suitable = []
for m in all_markets:
    # Use full endDate (includes time), not endDateIso
    end_str = m.get('endDate', '')
    if not end_str:
        continue
    try:
        end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        hours = (end - now).total_seconds() / 3600

        if hours < 1 or hours > 168:
            continue

        if not m.get('acceptingOrders', False):
            continue

        prices_raw = m.get('outcomePrices', '[]')
        if isinstance(prices_raw, str):
            prices = [float(p) for p in json.loads(prices_raw)]
        else:
            prices = [float(p) for p in prices_raw] if prices_raw else []

        token_ids_raw = m.get('clobTokenIds', '[]')
        if isinstance(token_ids_raw, str):
            token_ids = json.loads(token_ids_raw)
        else:
            token_ids = token_ids_raw or []

        suitable.append({
            'question': m.get('question', '')[:80],
            'end_date': end_str,
            'hours': round(hours, 1),
            'prices': prices,
            'condition_id': m.get('conditionId', ''),
            'token_ids': token_ids,
            'vol24h': m.get('volume24hr', 0),
            'accepting': m.get('acceptingOrders', False),
        })
    except Exception as e:
        pass

suitable.sort(key=lambda x: x['hours'])
print(f'\nSuitable markets (1-168h, accepting orders): {len(suitable)}')
for s in suitable[:15]:
    p_str = ' / '.join(f'{p:.3f}' for p in s['prices'][:2])
    print()
    print(f"  [{s['hours']}h] {s['question']}")
    print(f"  prices: {p_str} | vol24h: {s['vol24h']}")
    print(f"  condition_id: {s['condition_id']}")
    for i, tid in enumerate(s['token_ids'][:2]):
        print(f"  token[{i}]: {tid}")
