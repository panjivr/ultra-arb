"""
On-chain intelligence — whale tracking, insider detection, meme coin signals.

Tracks:
  1. Hyperliquid top traders — large positions, pre-news positioning (insider signals)
  2. DexScreener trending — meme coins gaining traction on SOL/BSC
  3. Large wallet movements — whale transfers signaling direction

All signals published to arb:edges:onchain_intel Redis stream.
"""
import asyncio
import json
import time
from collections import defaultdict

import httpx

from arb.infra.redis_bus import publish, get_redis
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(10, connect=5)

# ─── Hyperliquid ──────────────────────────────────────────────────────────────

HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"

# Known whale addresses on Hyperliquid (public leaderboard traders).
# Refreshed dynamically from the leaderboard every cycle.
HL_WATCHED_WALLETS: list[str] = []

# Previous position snapshots keyed by address for delta detection
_prev_hl_positions: dict[str, dict[str, dict]] = {}

# Minimum notional to flag as a conviction signal
HL_MIN_NOTIONAL = 50_000  # $50k


async def _hl_post(payload: dict) -> dict | list | None:
    """POST helper for Hyperliquid info API."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(
                HYPERLIQUID_API,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return None


async def fetch_hl_all_mids() -> dict[str, float]:
    """Fetch all market mid prices. Returns {coin: mid_price}."""
    data = await _hl_post({"type": "allMids"})
    if not isinstance(data, dict):
        return {}
    result: dict[str, float] = {}
    for coin, price_str in data.items():
        try:
            result[coin] = float(price_str)
        except (ValueError, TypeError):
            continue
    return result


async def fetch_hl_leaderboard() -> list[dict]:
    """
    Fetch Hyperliquid leaderboard to find top traders.
    Updates HL_WATCHED_WALLETS with top addresses.
    """
    # The leaderboard endpoint returns a list of top performers
    data = await _hl_post({"type": "leaderboard"})
    if not data:
        return []

    # data is expected to be {"leaderboardRows": [...]}
    rows = []
    if isinstance(data, dict):
        rows = data.get("leaderboardRows", [])
    elif isinstance(data, list):
        rows = data

    wallets: list[str] = []
    results: list[dict] = []
    for row in rows[:50]:  # top 50 traders
        addr = ""
        pnl = 0.0
        if isinstance(row, dict):
            addr = row.get("ethAddress", "") or row.get("user", "")
            pnl = float(row.get("accountValue", 0) or row.get("pnl", 0))
        if addr:
            wallets.append(addr)
            results.append({"address": addr, "pnl": pnl})

    # Update global watchlist
    global HL_WATCHED_WALLETS
    if wallets:
        HL_WATCHED_WALLETS = wallets
    return results


async def fetch_hl_positions(address: str) -> list[dict]:
    """Fetch open positions for a Hyperliquid address."""
    data = await _hl_post({"type": "clearinghouseState", "user": address})
    if not isinstance(data, dict):
        return []
    # clearinghouseState returns {"assetPositions": [...], "marginSummary": {...}}
    asset_positions = data.get("assetPositions", [])
    positions: list[dict] = []
    for ap in asset_positions:
        pos = ap.get("position", ap) if isinstance(ap, dict) else ap
        if not isinstance(pos, dict):
            continue
        coin = pos.get("coin", "")
        szi = pos.get("szi", "0")  # signed size
        entry_px = pos.get("entryPx", "0")
        unrealized_pnl = pos.get("unrealizedPnl", "0")
        try:
            size_f = float(szi)
            entry_f = float(entry_px)
            notional = abs(size_f * entry_f)
        except (ValueError, TypeError):
            notional = 0.0
        positions.append({
            "coin": coin,
            "size": float(szi) if szi else 0.0,
            "entry_px": float(entry_px) if entry_px else 0.0,
            "notional": notional,
            "unrealized_pnl": float(unrealized_pnl) if unrealized_pnl else 0.0,
            "direction": "long" if float(szi or 0) > 0 else "short",
        })
    return positions


async def fetch_hl_fills(address: str, limit: int = 50) -> list[dict]:
    """Fetch recent fills (trades) for a Hyperliquid address."""
    data = await _hl_post({"type": "userFills", "user": address})
    if not isinstance(data, list):
        return []
    return data[:limit]


async def scan_hyperliquid_whales() -> list[dict]:
    """
    Scan top Hyperliquid traders for large position changes.
    Detect:
      - New large positions (>$50k) = conviction signal
      - Position size increases = adding to winner
      - Coordinated positioning (multiple whales same direction) = strong signal
    """
    global _prev_hl_positions

    # Refresh leaderboard periodically (wallets list)
    if not HL_WATCHED_WALLETS:
        await fetch_hl_leaderboard()

    # If still no wallets, nothing to do
    if not HL_WATCHED_WALLETS:
        return []

    # Fetch mid prices for notional calculation
    mids = await fetch_hl_all_mids()

    signals: list[dict] = []
    # Track direction consensus across whales
    coin_direction_count: dict[str, dict[str, int]] = defaultdict(lambda: {"long": 0, "short": 0})

    # Scan a batch of wallets (limit to 10 per cycle to stay under rate limits)
    scan_batch = HL_WATCHED_WALLETS[:10]
    tasks = [fetch_hl_positions(addr) for addr in scan_batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for addr, result in zip(scan_batch, results):
        if isinstance(result, Exception) or not isinstance(result, list):
            continue

        current_map: dict[str, dict] = {p["coin"]: p for p in result if p.get("coin")}
        prev_map = _prev_hl_positions.get(addr, {})

        for coin, pos in current_map.items():
            notional = pos["notional"]
            direction = pos["direction"]

            if notional < HL_MIN_NOTIONAL:
                continue

            coin_direction_count[coin][direction] += 1

            # Check if this is a NEW position or a significant increase
            prev_pos = prev_map.get(coin)
            is_new = prev_pos is None
            size_delta = 0.0
            if prev_pos:
                size_delta = abs(pos["size"]) - abs(prev_pos.get("size", 0))

            if is_new or (size_delta > 0 and abs(size_delta * pos["entry_px"]) > HL_MIN_NOTIONAL * 0.5):
                signal_type = "new_position" if is_new else "position_increase"
                signals.append({
                    "source": "hl_whale",
                    "type": signal_type,
                    "address": addr[:10] + "...",
                    "coin": coin,
                    "direction": direction,
                    "notional": round(notional, 2),
                    "size_delta": round(size_delta, 4) if size_delta else None,
                    "entry_px": pos["entry_px"],
                    "mid_px": mids.get(coin),
                    "ts": int(time.time() * 1000),
                })

        # Save snapshot for next cycle
        _prev_hl_positions[addr] = current_map

    # Detect coordinated positioning (3+ whales same direction on same coin)
    for coin, counts in coin_direction_count.items():
        for direction in ("long", "short"):
            if counts[direction] >= 3:
                signals.append({
                    "source": "hl_whale",
                    "type": "coordinated",
                    "coin": coin,
                    "direction": direction,
                    "whale_count": counts[direction],
                    "confidence": min(0.9, 0.5 + counts[direction] * 0.1),
                    "ts": int(time.time() * 1000),
                })

    # Sort by notional descending (highest conviction first)
    signals.sort(key=lambda s: s.get("notional", 0), reverse=True)
    return signals


# ─── DexScreener (Meme Coins) ────────────────────────────────────────────────

DEXSCREENER_BOOSTS = "https://api.dexscreener.com/token-boosts/latest/v1"
DEXSCREENER_PROFILES = "https://api.dexscreener.com/token-profiles/latest/v1"
DEXSCREENER_TOKEN = "https://api.dexscreener.com/latest/dex/tokens"

# Chains we care about for meme coin signals
MEME_CHAINS = {"solana", "bsc"}

# Volume spike multiplier to flag as interesting
VOLUME_SPIKE_MULT = 5.0
# Minimum single-buy size to flag
LARGE_BUY_USD = 10_000


async def fetch_trending_tokens() -> list[dict]:
    """Fetch trending/boosted tokens from DexScreener."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        tokens: list[dict] = []
        for url in (DEXSCREENER_BOOSTS, DEXSCREENER_PROFILES):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get("data", data.get("tokens", []))
                    if isinstance(items, list):
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            chain = (item.get("chainId", "") or item.get("chain", "")).lower()
                            if chain in MEME_CHAINS:
                                tokens.append({
                                    "chain": chain,
                                    "address": item.get("tokenAddress", "") or item.get("address", ""),
                                    "description": item.get("description", ""),
                                    "url": item.get("url", ""),
                                    "icon": item.get("icon", ""),
                                    "amount": item.get("amount", 0),  # boost amount
                                })
            except Exception:
                continue
        return tokens


async def fetch_token_details(address: str) -> dict | None:
    """Fetch token pair data from DexScreener for a given token address."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(f"{DEXSCREENER_TOKEN}/{address}")
            if resp.status_code != 200:
                return None
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            # Return the pair with highest liquidity
            best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            return {
                "chain": best.get("chainId", ""),
                "pair_address": best.get("pairAddress", ""),
                "base_token": best.get("baseToken", {}).get("symbol", ""),
                "quote_token": best.get("quoteToken", {}).get("symbol", ""),
                "price_usd": float(best.get("priceUsd", 0) or 0),
                "volume_h24": float(best.get("volume", {}).get("h24", 0) or 0),
                "volume_h6": float(best.get("volume", {}).get("h6", 0) or 0),
                "volume_h1": float(best.get("volume", {}).get("h1", 0) or 0),
                "price_change_h24": float(best.get("priceChange", {}).get("h24", 0) or 0),
                "price_change_h6": float(best.get("priceChange", {}).get("h6", 0) or 0),
                "price_change_h1": float(best.get("priceChange", {}).get("h1", 0) or 0),
                "liquidity_usd": float(best.get("liquidity", {}).get("usd", 0) or 0),
                "fdv": float(best.get("fdv", 0) or 0),
                "txns_h24_buys": int(best.get("txns", {}).get("h24", {}).get("buys", 0) or 0),
                "txns_h24_sells": int(best.get("txns", {}).get("h24", {}).get("sells", 0) or 0),
                "token_address": address,
            }
        except Exception:
            return None


async def scan_meme_coins() -> list[dict]:
    """
    Find meme coins with whale accumulation signals:
      - Volume spike (>5x: h1 annualized vs h24)
      - Buy/sell ratio skew (>2x more buys than sells)
      - Strong recent price action (>20% in 1h)
      - Minimum liquidity ($10k) to filter dead tokens
    Returns list of actionable signals.
    """
    trending = await fetch_trending_tokens()
    if not trending:
        return []

    # Deduplicate by address
    seen_addrs: set[str] = set()
    unique: list[dict] = []
    for t in trending:
        addr = t.get("address", "")
        if addr and addr not in seen_addrs:
            seen_addrs.add(addr)
            unique.append(t)

    # Fetch details for top trending tokens (limit to 15 to respect rate limits)
    tasks = [fetch_token_details(t["address"]) for t in unique[:15]]
    details = await asyncio.gather(*tasks, return_exceptions=True)

    signals: list[dict] = []
    for token_meta, detail in zip(unique[:15], details):
        if isinstance(detail, Exception) or detail is None:
            continue

        vol_h24 = detail["volume_h24"]
        vol_h1 = detail["volume_h1"]
        liquidity = detail["liquidity_usd"]
        price_change_h1 = detail["price_change_h1"]
        buys = detail["txns_h24_buys"]
        sells = detail["txns_h24_sells"]

        # Filter: minimum liquidity
        if liquidity < 10_000:
            continue

        score = 0.0
        reasons: list[str] = []

        # Volume spike: h1 volume annualized vs h24
        if vol_h24 > 0 and vol_h1 > 0:
            h1_annualized = vol_h1 * 24
            spike_ratio = h1_annualized / vol_h24
            if spike_ratio >= VOLUME_SPIKE_MULT:
                score += 0.3
                reasons.append(f"vol_spike_{spike_ratio:.1f}x")

        # Buy/sell ratio
        if sells > 0 and buys > 0:
            buy_sell_ratio = buys / sells
            if buy_sell_ratio >= 2.0:
                score += 0.2
                reasons.append(f"buy_ratio_{buy_sell_ratio:.1f}x")

        # Strong price action
        if price_change_h1 > 20:
            score += 0.2
            reasons.append(f"pump_{price_change_h1:.0f}%_1h")
        elif price_change_h1 < -30:
            score += 0.1
            reasons.append(f"dump_{price_change_h1:.0f}%_1h")

        # High volume relative to liquidity (high turnover)
        if liquidity > 0 and vol_h24 > 0:
            turnover = vol_h24 / liquidity
            if turnover > 5:
                score += 0.2
                reasons.append(f"turnover_{turnover:.1f}x")

        if score < 0.2:
            continue

        signals.append({
            "source": "dexscreener",
            "type": "meme_signal",
            "chain": detail["chain"],
            "token": detail["base_token"],
            "token_address": detail["token_address"],
            "price_usd": detail["price_usd"],
            "volume_h24": vol_h24,
            "volume_h1": vol_h1,
            "liquidity_usd": liquidity,
            "price_change_h1": price_change_h1,
            "price_change_h24": detail["price_change_h24"],
            "fdv": detail["fdv"],
            "buy_sell_ratio": round(buys / max(sells, 1), 2),
            "score": round(score, 2),
            "reasons": reasons,
            "ts": int(time.time() * 1000),
        })

    # Sort by score descending
    signals.sort(key=lambda s: s["score"], reverse=True)
    return signals


# ─── Main Loop ────────────────────────────────────────────────────────────────

async def run_onchain_intel_loop(interval_s: int = 60):
    """Background task: scan on-chain data every 60s."""
    r = get_redis()
    leaderboard_refresh = 0  # epoch seconds of last leaderboard fetch

    print("[onchain] on-chain intelligence loop started")

    while True:
        try:
            now = time.time()
            now_ms = int(now * 1000)

            # Refresh leaderboard every 10 minutes
            if now - leaderboard_refresh > 600:
                lb = await fetch_hl_leaderboard()
                leaderboard_refresh = now
                if lb:
                    print(f"[onchain] refreshed HL leaderboard: {len(lb)} traders")

            # 1. Hyperliquid whales
            hl_signals = await scan_hyperliquid_whales()
            for sig in hl_signals[:20]:
                await publish("arb:edges:onchain_intel", sig)
                # Emit coordinated signals to ensemble as they indicate strong conviction
                if sig.get("type") == "coordinated" and sig.get("coin"):
                    coin = sig["coin"]
                    direction = "yes" if sig["direction"] == "long" else "no"
                    await emit_vote(SignalVote(
                        condition_id=f"hl:{coin}",
                        direction=direction,
                        confidence=sig.get("confidence", 0.6),
                        source="onchain_intel",
                        asset=f"{coin}/USDT",
                        kind="updown",
                        ts=now_ms,
                    ))

            # 2. Meme coin scanner
            meme_signals = await scan_meme_coins()
            for sig in meme_signals[:10]:
                await publish("arb:edges:onchain_intel", sig)

            # Store summary for dashboard
            summary = {
                "ts": now_ms,
                "hl_signals": len(hl_signals),
                "meme_signals": len(meme_signals),
                "watched_wallets": len(HL_WATCHED_WALLETS),
                "top_hl": hl_signals[0] if hl_signals else None,
                "top_meme": meme_signals[0] if meme_signals else None,
            }
            await r.set("arb:edges:onchain_intel:summary", json.dumps(summary), ex=300)

            if hl_signals or meme_signals:
                print(f"[onchain] HL: {len(hl_signals)} signals, Meme: {len(meme_signals)} signals")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[onchain] error: {repr(e)[:120]}")

        await asyncio.sleep(interval_s)
