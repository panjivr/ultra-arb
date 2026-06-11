import httpx, json

resp = httpx.get(
    'https://gamma-api.polymarket.com/markets',
    params={'limit': 5, 'active': 'true', 'closed': 'false', 'order': 'volume24hr', 'ascending': 'false'},
    timeout=20,
)
markets = resp.json()
for m in markets[:3]:
    print('Question:', m.get('question','')[:60])
    print('endDate:', m.get('endDate'))
    print('endDateIso:', m.get('endDateIso'))
    print('acceptingOrders:', m.get('acceptingOrders'))
    print('active:', m.get('active'))
    print('closed:', m.get('closed'))
    # Check ALL date-related fields
    for k, v in m.items():
        if 'date' in k.lower() or 'time' in k.lower() or 'end' in k.lower():
            print(f'  {k}: {v}')
    print()

# Try the events API
print()
print('=== Events API ===')
resp2 = httpx.get(
    'https://gamma-api.polymarket.com/events',
    params={'limit': 5, 'active': 'true', 'closed': 'false'},
    timeout=15,
)
print('Events status:', resp2.status_code)
events = resp2.json() if resp2.status_code == 200 else []
if isinstance(events, list):
    for e in events[:2]:
        print('Event:', e.get('title','')[:60])
        print('  endDate:', e.get('endDate'))
        print('  markets:', len(e.get('markets',[])))
        if e.get('markets'):
            m0 = e['markets'][0]
            print('  market0 question:', m0.get('question','')[:60])
            print('  market0 endDate:', m0.get('endDate'))
