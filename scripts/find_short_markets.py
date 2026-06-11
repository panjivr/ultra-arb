import httpx
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
print('Now UTC:', now.strftime('%Y-%m-%dT%H:%M'))

# Fetch top active markets from Gamma API
resp = httpx.get(
    'https://gamma-api.polymarket.com/markets',
    params={
        'limit': 200,
        'active': 'true',
        'closed': 'false',
        'order': 'volume24hr',
        'ascending': 'false',
    },
    timeout=20,
)
markets = resp.json()
print(f'Total active markets: {len(markets)}')

# Filter for markets ending in 1-168 hours with price 0.10-0.90
suitable = []
for m in markets:
    try:
        end_iso = m.get('endDateIso', '') or m.get('endDate', '')
        if not end_iso:
            continue
        end = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
        hours_left = (end - now).total_seconds() / 3600

        if hours_left < 1 or hours_left > 168:
            continue

        accepting = m.get('acceptingOrders', False)
        if not accepting:
            continue

        # Check prices
        prices_raw = m.get('outcomePrices', '[]')
        if isinstance(prices_raw, str):
            import json
            prices_raw = json.loads(prices_raw)
        prices = [float(p) for p in prices_raw if p]

        # For binary markets, check if price is between 0.10 and 0.90
        if len(prices) == 2:
            p = prices[0]
            if not (0.08 <= p <= 0.92):
                continue

        suitable.append({
            'question': m.get('question', '')[:80],
            'end_iso': end_iso,
            'hours_left': round(hours_left, 1),
            'prices': prices,
            'condition_id': m.get('conditionId', ''),
            'token_ids': json.loads(m.get('clobTokenIds','[]')) if isinstance(m.get('clobTokenIds','[]'), str) else m.get('clobTokenIds',[]),
            'vol24h': m.get('volume24hr', 0),
        })
    except Exception as e:
        pass

suitable.sort(key=lambda x: x['hours_left'])
print(f'\nMarkets ending in 1-168h with price 0.10-0.90: {len(suitable)}')
for s in suitable[:10]:
    print()
    print(f"  [{s['hours_left']}h] {s['question']}")
    print(f"   condition_id: {s['condition_id']}")
    print(f"   prices: {s['prices']} | vol24h: {s['vol24h']}")
    for i, tid in enumerate(s['token_ids'][:2]):
        print(f"   token[{i}]: {tid[:30]}...")
