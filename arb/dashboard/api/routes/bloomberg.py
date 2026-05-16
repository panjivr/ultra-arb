"""
Bloomberg Terminal-style market intelligence endpoints.

All sources are FREE / no-API-key public endpoints:
  - CryptoPanic        — crypto news headlines (free public feed)
  - Alternative.me     — Fear & Greed Index
  - CoinGecko          — global market cap, BTC dominance, volume
  - Federal Reserve    — FOMC calendar (hardcoded major 2026 dates, publicly known)
  - DefiLlama          — TVL, stablecoin supply, on-chain volume
  - Coinglass (mirror) — liquidations, long/short ratio

Caches results in Redis to avoid hammering external APIs.
"""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import APIRouter
import httpx
from arb.infra.redis_bus import get_redis

router = APIRouter(prefix="/api/bloomberg", tags=["bloomberg"])

CACHE_TTL = {
    "news": 60,            # 1 min
    "macro": 30,           # 30s
    "fear_greed": 600,     # 10 min — index updates daily
    "calendar": 3600,      # 1 hour
    "liquidations": 60,
    "global_metrics": 60,
    "trending": 300,
}

_client_timeout = httpx.Timeout(8.0, connect=4.0)


async def _cached_get(key: str, ttl: int, fetcher) -> Any:
    """Redis-cached fetcher."""
    r = get_redis()
    cache_key = f"arb:bloomberg:cache:{key}"
    cached = await r.get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            data["_cached"] = True
            return data
        except Exception:
            pass
    try:
        fresh = await fetcher()
        fresh["_cached"] = False
        fresh["_fetched_at"] = int(time.time() * 1000)
        await r.set(cache_key, json.dumps(fresh), ex=ttl)
        return fresh
    except Exception as e:
        return {"error": str(e)[:200], "_cached": False, "_fetched_at": int(time.time() * 1000)}


# ─────────── NEWS (RSS — no API key) ───────────
import re
import xml.etree.ElementTree as ET

# Free public RSS feeds
NEWS_FEEDS = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Bitcoin.com", "https://news.bitcoin.com/feed/"),
]

# Keywords that trigger "important" classification
IMPORTANT_KEYWORDS = re.compile(
    r"\b(fed|fomc|powell|rate cut|rate hike|inflation|cpi|ppi|nfp|jobs|"
    r"sec|gensler|etf approval|approval|hack|exploit|halt|delist|"
    r"halving|fork|upgrade|partnership|launch|listing|treasury)\b",
    re.IGNORECASE,
)

# Crypto currency detector
CURRENCY_REGEX = re.compile(
    r"\b(BTC|ETH|SOL|XRP|BNB|ADA|DOGE|AVAX|MATIC|LINK|UNI|ATOM|"
    r"Bitcoin|Ethereum|Solana|Ripple|Binance|Cardano|Dogecoin)\b",
    re.IGNORECASE,
)


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _parse_rss(xml_text: str, source: str) -> list[dict]:
    """Parse RSS 2.0 / Atom feeds. Returns up to 15 newest items per source."""
    out = []
    try:
        # Clean potential BOM or weird XML
        if xml_text.startswith("﻿"):
            xml_text = xml_text[1:]
        root = ET.fromstring(xml_text)
    except Exception:
        return out

    # Find item elements (RSS 2.0)
    items = root.findall(".//item")
    if not items:
        # Atom feed
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//atom:entry", ns)
        is_atom = True
    else:
        is_atom = False

    for item in items[:15]:
        if is_atom:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            title = (item.findtext("atom:title", default="", namespaces=ns) or "").strip()
            link_el = item.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            published = item.findtext("atom:published", default="", namespaces=ns) or ""
        else:
            title = (item.findtext("title", default="") or "").strip()
            link = (item.findtext("link", default="") or "").strip()
            published = (item.findtext("pubDate", default="") or "").strip()
        title = _strip_html(title)
        if not title:
            continue
        # Detect currencies + importance
        currencies = list(set(m.group(0).upper()[:5] for m in CURRENCY_REGEX.finditer(title)))[:5]
        is_important = bool(IMPORTANT_KEYWORDS.search(title))
        out.append({
            "title": title[:240],
            "source": source,
            "url": link,
            "published_at": published,
            "currencies": currencies,
            "kind": "news",
            "votes": {
                "positive": 0,
                "negative": 0,
                "important": 1 if is_important else 0,
            },
        })
    return out


async def _fetch_news() -> dict:
    """Parse RSS feeds from 4 crypto news sites — no API key required."""
    items = []
    async with httpx.AsyncClient(
        timeout=_client_timeout,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ReyogCapital/0.3)"},
        follow_redirects=True,
    ) as client:
        # Fetch all feeds in parallel
        async def fetch_one(source: str, url: str):
            try:
                r = await client.get(url)
                if r.status_code == 200 and r.text:
                    return _parse_rss(r.text, source)
            except Exception:
                pass
            return []

        results = await asyncio.gather(
            *[fetch_one(s, u) for s, u in NEWS_FEEDS],
            return_exceptions=False,
        )
        for r_items in results:
            items.extend(r_items)

    # Sort by published date (newest first), with fallback to insertion order
    def parse_ts(s: str) -> float:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(s).timestamp()
        except Exception:
            try:
                from datetime import datetime
                return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0

    items.sort(key=lambda x: parse_ts(x["published_at"]), reverse=True)
    # Dedupe by title
    seen = set()
    deduped = []
    for it in items:
        key = it["title"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    return {"items": deduped[:40], "count": len(deduped[:40]), "sources": [s for s, _ in NEWS_FEEDS]}


@router.get("/news")
async def get_news():
    return await _cached_get("news", CACHE_TTL["news"], _fetch_news)


# ─────────── FEAR & GREED INDEX ───────────
async def _fetch_fear_greed() -> dict:
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        r = await client.get("https://api.alternative.me/fng/?limit=8")
        if r.status_code != 200:
            return {"error": f"http {r.status_code}"}
        data = r.json().get("data", [])
        if not data:
            return {"error": "no data"}
        current = data[0]
        history = [{"value": int(d["value"]), "classification": d["value_classification"],
                    "timestamp": int(d["timestamp"])} for d in data]
        return {
            "value": int(current["value"]),
            "classification": current["value_classification"],
            "timestamp": int(current["timestamp"]),
            "history": history,
        }


@router.get("/fear-greed")
async def get_fear_greed():
    return await _cached_get("fear_greed", CACHE_TTL["fear_greed"], _fetch_fear_greed)


# ─────────── GLOBAL MARKET METRICS ───────────
async def _fetch_global_metrics() -> dict:
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        r = await client.get("https://api.coingecko.com/api/v3/global")
        if r.status_code != 200:
            return {"error": f"http {r.status_code}"}
        d = r.json().get("data", {})
        return {
            "total_market_cap_usd": d.get("total_market_cap", {}).get("usd", 0),
            "total_volume_24h_usd": d.get("total_volume", {}).get("usd", 0),
            "btc_dominance": d.get("market_cap_percentage", {}).get("btc", 0),
            "eth_dominance": d.get("market_cap_percentage", {}).get("eth", 0),
            "active_cryptocurrencies": d.get("active_cryptocurrencies", 0),
            "markets": d.get("markets", 0),
            "mcap_change_24h_pct": d.get("market_cap_change_percentage_24h_usd", 0),
            "updated_at": d.get("updated_at", 0),
        }


@router.get("/global")
async def get_global_metrics():
    return await _cached_get("global_metrics", CACHE_TTL["global_metrics"], _fetch_global_metrics)


# ─────────── MACRO (DXY, GOLD, OIL, US10Y proxy) ───────────
async def _fetch_macro() -> dict:
    """Use Yahoo Finance unofficial JSON for macro indicators (no key)."""
    symbols = {
        "DX-Y.NYB": "DXY (US Dollar Index)",
        "GC=F": "Gold (Futures)",
        "CL=F": "WTI Crude Oil",
        "^TNX": "US 10-Year Yield",
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ Composite",
        "^VIX": "VIX (Volatility)",
        "BTC-USD": "Bitcoin (Yahoo)",
    }
    out = []
    async with httpx.AsyncClient(timeout=_client_timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for sym, label in symbols.items():
            try:
                r = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"range": "1d", "interval": "5m"},
                )
                if r.status_code != 200:
                    continue
                result = r.json().get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                if price is None or prev is None:
                    continue
                change = price - prev
                change_pct = (change / prev) * 100 if prev else 0
                out.append({
                    "symbol": sym,
                    "label": label,
                    "price": round(price, 4),
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 3),
                    "currency": meta.get("currency", "USD"),
                })
            except Exception:
                continue
    return {"indicators": out, "count": len(out)}


@router.get("/macro")
async def get_macro():
    return await _cached_get("macro", CACHE_TTL["macro"], _fetch_macro)


# ─────────── TRENDING COINS ───────────
async def _fetch_trending() -> dict:
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        r = await client.get("https://api.coingecko.com/api/v3/search/trending")
        if r.status_code != 200:
            return {"error": f"http {r.status_code}"}
        coins = r.json().get("coins", [])[:10]
        return {
            "coins": [
                {
                    "name": c["item"]["name"],
                    "symbol": c["item"]["symbol"],
                    "rank": c["item"].get("market_cap_rank"),
                    "score": c["item"].get("score", 0),
                    "price_btc": c["item"].get("price_btc", 0),
                }
                for c in coins
            ],
            "count": len(coins),
        }


@router.get("/trending")
async def get_trending():
    return await _cached_get("trending", CACHE_TTL["trending"], _fetch_trending)


# ─────────── ECONOMIC CALENDAR ───────────
# Hardcoded major US events for 2026 (publicly known FOMC schedule, CPI/PPI typical days)
# Real production system would pull from FRED, but those are public schedule dates.
@router.get("/calendar")
async def get_calendar(days: int = 30):
    """Upcoming major economic events that move crypto."""
    now = datetime.now(timezone.utc)
    # FOMC 2026 meetings (publicly announced by Federal Reserve)
    fomc_2026 = [
        ("2026-01-28", "FOMC Rate Decision", "high", "Federal Reserve interest rate decision + dot plot"),
        ("2026-03-18", "FOMC Rate Decision + SEP", "high", "Rate decision + Summary of Economic Projections"),
        ("2026-04-29", "FOMC Rate Decision", "high", "Rate decision + press conference"),
        ("2026-06-17", "FOMC Rate Decision + SEP", "high", "Rate decision + SEP"),
        ("2026-07-29", "FOMC Rate Decision", "high", "Rate decision + press conference"),
        ("2026-09-16", "FOMC Rate Decision + SEP", "high", "Rate decision + SEP"),
        ("2026-11-04", "FOMC Rate Decision", "high", "Rate decision + press conference"),
        ("2026-12-09", "FOMC Rate Decision + SEP", "high", "Rate decision + SEP"),
    ]
    # CPI releases (typical: 2nd Tue-Thu of month at 8:30 ET)
    cpi_dates = [
        ("2026-05-13", "US CPI (April)", "high", "Consumer Price Index — inflation read"),
        ("2026-06-11", "US CPI (May)", "high", "CPI report — key for Fed policy"),
        ("2026-07-15", "US CPI (June)", "high", "CPI report"),
        ("2026-08-12", "US CPI (July)", "high", "CPI report"),
    ]
    # NFP (1st Friday of each month, 8:30 ET)
    nfp_dates = [
        ("2026-06-05", "US Non-Farm Payrolls (May)", "high", "Employment report"),
        ("2026-07-02", "US Non-Farm Payrolls (June)", "high", "Employment report"),
        ("2026-08-07", "US Non-Farm Payrolls (July)", "high", "Employment report"),
    ]
    # Crypto-specific
    crypto_events = [
        ("2026-05-20", "Bitcoin Halving Anniversary", "medium", "1 year since 2024 halving"),
        ("2026-06-10", "Ethereum Pectra Upgrade Window", "medium", "Major protocol upgrade"),
    ]

    all_events = []
    for date_str, title, importance, desc in fomc_2026 + cpi_dates + nfp_dates + crypto_events:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        delta = (dt - now).days
        if delta < -1 or delta > days:
            continue
        all_events.append({
            "date": date_str,
            "title": title,
            "importance": importance,
            "description": desc,
            "days_until": delta,
            "in_past": delta < 0,
        })
    all_events.sort(key=lambda e: e["date"])
    return {"events": all_events, "count": len(all_events), "horizon_days": days}


# ─────────── DERIVATIVES SENTIMENT (Gate.io public — no SSL issues) ───────────
async def _fetch_liquidations() -> dict:
    """Gate.io USDT-margined futures: funding rate + open interest (public, no key)."""
    symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT"]
    data = []
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        for sym in symbols:
            try:
                r = await client.get(
                    f"https://api.gateio.ws/api/v4/futures/usdt/contracts/{sym}"
                )
                if r.status_code != 200:
                    continue
                c = r.json()
                rate = float(c.get("funding_rate_indicative", 0) or c.get("funding_rate", 0) or 0)
                mark = float(c.get("mark_price", 0) or c.get("last_price", 0) or 0)
                index = float(c.get("index_price", 0) or 0)
                # Open interest in contracts; multiplier converts to coin units
                multiplier = float(c.get("quanto_multiplier", c.get("multiplier", 1)) or 1)
                oi_size = float(c.get("position_size", c.get("trade_size", 0)) or 0)
                # Open interest USD approx = size * multiplier * mark price
                oi_usd = oi_size * multiplier * mark if mark else oi_size * multiplier
                # Funding cycle is 8 hours → 3x/day → 365 days for APR
                apr = rate * 3 * 365 * 100
                basis_bps = ((mark - index) / index * 10_000) if index else 0
                data.append({
                    "symbol": sym.replace("_", "/"),
                    "funding_rate": rate,
                    "funding_rate_pct": round(rate * 100, 4),
                    "open_interest_usd": round(oi_usd, 2),
                    "open_interest": round(oi_usd, 2),  # keep legacy field name
                    "mark_price": mark,
                    "index_price": index,
                    "basis_bps": round(basis_bps, 2),
                    "apr": round(apr, 2),
                    "ts": int(time.time() * 1000),
                })
            except Exception:
                continue
    return {"derivatives": data, "count": len(data)}


@router.get("/derivatives")
async def get_derivatives():
    return await _cached_get("liquidations", CACHE_TTL["liquidations"], _fetch_liquidations)


# ─────────── DEFI / STABLECOIN ───────────
async def _fetch_defi() -> dict:
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        try:
            tvl_r = await client.get("https://api.llama.fi/v2/historicalChainTvl")
            stable_r = await client.get("https://stablecoins.llama.fi/stablecoins")
            tvl = 0
            if tvl_r.status_code == 200:
                hist = tvl_r.json()
                if hist:
                    tvl = float(hist[-1].get("tvl", 0))
            stable_total = 0
            stable_chains = []
            if stable_r.status_code == 200:
                sd = stable_r.json().get("peggedAssets", [])
                for s in sd[:5]:
                    stable_chains.append({
                        "name": s.get("name", ""),
                        "symbol": s.get("symbol", ""),
                        "circulating": s.get("circulating", {}).get("peggedUSD", 0),
                    })
                stable_total = sum(s["circulating"] for s in stable_chains)
            return {
                "total_tvl_usd": tvl,
                "stablecoin_total_supply": stable_total,
                "top_stables": stable_chains,
            }
        except Exception as e:
            return {"error": str(e)[:200]}


@router.get("/defi")
async def get_defi():
    return await _cached_get("defi", 300, _fetch_defi)


# ─────────── COMBINED SNAPSHOT ───────────
@router.get("/snapshot")
async def get_full_snapshot():
    """One call returns everything for dashboard initial paint."""
    news, fg, glob, macro, trending, calendar, deriv = await asyncio.gather(
        get_news(), get_fear_greed(), get_global_metrics(), get_macro(),
        get_trending(), get_calendar(), get_derivatives(),
        return_exceptions=True,
    )
    return {
        "news": news if not isinstance(news, Exception) else {"error": str(news)},
        "fear_greed": fg if not isinstance(fg, Exception) else {"error": str(fg)},
        "global": glob if not isinstance(glob, Exception) else {"error": str(glob)},
        "macro": macro if not isinstance(macro, Exception) else {"error": str(macro)},
        "trending": trending if not isinstance(trending, Exception) else {"error": str(trending)},
        "calendar": calendar if not isinstance(calendar, Exception) else {"error": str(calendar)},
        "derivatives": deriv if not isinstance(deriv, Exception) else {"error": str(deriv)},
        "ts": int(time.time() * 1000),
    }
