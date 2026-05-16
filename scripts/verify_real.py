"""Verify REAL prices are in Redis."""
import sys, os, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def check():
    from arb.infra.redis_bus import get_redis
    r = get_redis()
    keys = sorted([k for k in await r.keys("arb:ticks:*")])
    print(f"Tick streams: {len(keys)}")
    for k in keys[:10]:
        item = await r.lindex(k, 0)
        if item:
            d = json.loads(item)
            bid = d.get("bid", 0); ask = d.get("ask", 0)
            src = d.get("source", "?")
            print(f"  {k}: bid=${bid:,.4f} ask=${ask:,.4f} src={src}")

    sig = await r.lindex("arb:signals", 0)
    if sig:
        d = json.loads(sig)
        print(f"\nLatest signal: {d.get('strategy')} {d.get('symbol')} "
              f"prob={d.get('probability_score')} spread_bps={d.get('spread_bps_real')}")

    ord_ = await r.lindex("arb:orders", 0)
    if ord_:
        d = json.loads(ord_)
        p = d.get("price") or d.get("exit_price") or 0
        print(f"Latest order: {d.get('event')} {d.get('symbol')} {d.get('strategy')} @ ${p:,.4f}")

    await r.aclose()

asyncio.run(check())
