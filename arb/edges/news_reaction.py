"""
News-reaction speed bot.

When a high-impact crypto/macro news headline drops, prediction markets
take 1-30 minutes to re-price (manual humans). A bot reading RSS every 10
seconds can react in seconds.

Pipeline:
  1. Pull latest news every 10 seconds
  2. Detect high-impact keywords (FOMC decision, ETF approval, hack, halt, etc.)
  3. Score sentiment (positive/negative for BTC/ETH)
  4. Cross-reference with active prediction markets
  5. If sentiment + market mispricing align → emit bet signal

Bot advantage: 10-second reaction time vs 5-30 min for human traders.
"""
import asyncio
import json
import re
import time
import httpx
from arb.infra.redis_bus import publish, get_redis
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(6, connect=3)

# High-impact patterns only — generic words like "rally", "partnership" generate too many
# false positives. We require more specific, market-moving language.
BULLISH_PATTERNS = re.compile(
    r"\b(etf approval|etf approved|spot etf|institutional adoption|"
    r"treasury buys|treasury adds|fed cuts rates|rate cut decision|"
    r"dovish pivot|halving|all[- ]time high reached|ath breakout|"
    r"surge \d+%|jumps \d+%|soars \d+%)\b",
    re.IGNORECASE,
)
BEARISH_PATTERNS = re.compile(
    r"\b(hack|exploit|funds drained|stolen|trading halt|"
    r"sec sues|charged with fraud|bankruptcy filing|chapter 11|"
    r"fed hikes rates|rate hike decision|hawkish surprise|"
    r"flash crash|plunges \d+%|drops \d+%|liquidat(ed|ion) cascade|capitulat)\b",
    re.IGNORECASE,
)


def _score_sentiment(title: str) -> tuple[float, list[str]]:
    """Returns (sentiment in [-1, 1], matched_keywords)."""
    bull = BULLISH_PATTERNS.findall(title)
    bear = BEARISH_PATTERNS.findall(title)
    score = (len(bull) - len(bear)) / max(len(bull) + len(bear), 1)
    return score, bull + bear


async def fetch_recent_news() -> list[dict]:
    """Read cached news from our bloomberg endpoint."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get("http://localhost:8000/api/bloomberg/news")
            if r.status_code == 200:
                return r.json().get("items", [])
        except Exception:
            return []
    return []


async def run_news_reaction_loop(interval_s: int = 15):
    """
    Every 15s:
      1. Read fresh news
      2. For new (last 5 min) items, score sentiment
      3. If strong signal (|score| >= 0.5), emit news_signal to Redis
    """
    r = get_redis()
    seen_titles: set[str] = set()

    while True:
        try:
            items = await fetch_recent_news()
            now_ms = int(time.time() * 1000)
            new_signals = 0

            for n in items[:50]:
                title = n.get("title", "")
                key = title.lower()[:120]
                if key in seen_titles or not title:
                    continue
                # Check freshness (published within 10 min)
                published = n.get("published_at", "")
                try:
                    from email.utils import parsedate_to_datetime
                    pub_ts = parsedate_to_datetime(published).timestamp() * 1000
                except Exception:
                    try:
                        from datetime import datetime
                        pub_ts = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp() * 1000
                    except Exception:
                        pub_ts = now_ms
                age_min = (now_ms - pub_ts) / 60_000
                # Only react to news < 10 min old; older news is already priced in
                if age_min > 10:
                    seen_titles.add(key)
                    continue

                score, kw = _score_sentiment(title)
                # Require strong sentiment (70%+ confidence) to reduce false signals
                if abs(score) < 0.7:
                    seen_titles.add(key)
                    continue

                # Detect mentioned asset
                t_low = title.lower()
                affected = []
                for sym, name in [("BTC", "bitcoin"), ("ETH", "ethereum"),
                                   ("SOL", "solana"), ("XRP", "xrp"), ("BNB", "binance")]:
                    if sym.lower() in t_low or name in t_low:
                        affected.append(sym)
                if not affected:
                    affected = ["BTC"]  # default to BTC for macro/Fed news

                signal = {
                    "title": title[:200],
                    "source": n.get("source", ""),
                    "url": n.get("url", ""),
                    "sentiment": round(score, 3),
                    "direction": "BULLISH" if score > 0 else "BEARISH",
                    "keywords": kw[:5],
                    "currencies": affected,
                    "age_minutes": round(age_min, 1),
                    "ts": now_ms,
                    "kind": "news_signal",
                }
                await publish("arb:edges:news_signal", signal)
                # Wire into ensemble gate — news events affect the primary asset
                for sym in affected:
                    await emit_vote(SignalVote(
                        condition_id=f"news:{sym}:{int(pub_ts/60000)}",
                        direction="yes" if score > 0 else "no",
                        confidence=round(min(abs(score), 0.95), 3),
                        source="news_reaction",
                        asset=f"{sym}/USDT",
                        kind="news_signal", ts=now_ms,
                    ))
                seen_titles.add(key)
                new_signals += 1

            if len(seen_titles) > 5000:
                seen_titles = set(list(seen_titles)[-2500:])
            if new_signals > 0:
                print(f"[news_reaction] {new_signals} fresh high-impact signals")
        except Exception as e:
            print(f"[news_reaction] error: {repr(e)[:120]}")
        await asyncio.sleep(interval_s)
