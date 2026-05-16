"""
Polymarket CLOB feed via py-clob-client REST polling at 500ms cadence.
Streams top-of-book → Redis arb:ticks:POLY:{token_id}
"""
import asyncio
import time
import httpx
from arb.config import settings
from arb.infra.redis_bus import publish

POLL_INTERVAL = 0.5  # seconds

# Top prediction markets to monitor (token IDs)
# In production these are fetched dynamically; these are well-known BTC/ETH markets
MARKETS: list[dict] = []

CLOB_BASE = (
    "https://clob.polymarket.com"
    if not settings.polymarket_sandbox
    else "https://clob.polymarket.com"  # sandbox uses same endpoint with test credentials
)


async def _fetch_markets(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(f"{CLOB_BASE}/markets", params={"limit": 20, "active": "true"})
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])[:10]
    except Exception as e:
        print(f"[polymarket_feed] fetch markets error: {e}")
        return []


async def _poll_market(client: httpx.AsyncClient, market: dict) -> None:
    token_id = market.get("condition_id", "")
    question = market.get("question", "")[:60]
    while True:
        try:
            resp = await client.get(f"{CLOB_BASE}/book", params={"token_id": token_id})
            if resp.status_code == 200:
                book = resp.json()
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                if bids and asks:
                    best_bid = float(bids[0]["price"])
                    best_ask = float(asks[0]["price"])
                    mid = (best_bid + best_ask) / 2
                    await publish(f"arb:ticks:POLY:{token_id}", {
                        "ts": int(time.time() * 1000),
                        "symbol": f"POLY:{token_id[:12]}",
                        "exchange": "POLYMARKET",
                        "question": question,
                        "bid": best_bid,
                        "ask": best_ask,
                        "mid": mid,
                        "spread_pct": (best_ask - best_bid) / best_ask * 100,
                    })
            await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[polymarket_feed] {token_id[:12]} poll error: {e}")
            await asyncio.sleep(2)


async def run() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        markets = await _fetch_markets(client)
        if not markets:
            print("[polymarket_feed] No markets fetched, retrying in 30s...")
            await asyncio.sleep(30)
            markets = await _fetch_markets(client)

        print(f"[polymarket_feed] Monitoring {len(markets)} markets")
        tasks = [asyncio.create_task(_poll_market(client, m)) for m in markets]
        await asyncio.gather(*tasks)
