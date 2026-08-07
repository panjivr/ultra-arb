"""
0-latency firehose WebSocket — sub-millisecond push of every tick, signal,
order, and Bloomberg event to connected dashboard clients.

Architecture:
  - Maintains last-seen index per Redis list
  - 10ms poll loop (100Hz) — effective end-to-end latency ~ 5-15ms
  - Batches messages per tick to amortize JSON overhead
  - Per-message latency tag (ms_since_publish) so frontend can show "0ms" feel
"""
import asyncio
import json
import os
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from arb.infra.redis_bus import get_redis

router = APIRouter(tags=["firehose"])

# Push cadence. Default 10ms (100Hz) preserves the original full-firehose feel.
# On command-limited free-tier Redis (e.g. Upstash), set FIREHOSE_HZ_MS=500 so
# the poll loop runs ~2Hz instead of 100Hz — cuts Redis reads ~50x while the
# feed still updates in real time. See docs/06-audit-gratisan.md.
PUSH_INTERVAL = max(0.001, float(os.getenv("FIREHOSE_HZ_MS", "10")) / 1000.0)
# Per-poll batch cap per stream — large enough to cover a burst between polls.
MAX_BATCH = 200


def _entry_ts(raw: str) -> int:
    try:
        return int(json.loads(raw).get("ts", 0) or 0)
    except Exception:
        return 0

# Streams to firehose — all REAL market data + signals + orders + alerts
WATCHED_PATTERNS = [
    "arb:ticks:*",     # all tick streams (10 streams currently)
    "arb:signals",
    "arb:orders",
    "arb:risk:alerts",
    "arb:wallet:events",
]


async def _resolve_streams(r) -> list[str]:
    """Expand wildcards to actual Redis keys."""
    streams = set()
    for pat in WATCHED_PATTERNS:
        if "*" in pat:
            keys = await r.keys(pat)
            streams.update(keys)
        else:
            streams.add(pat)
    return sorted(streams)


@router.websocket("/ws/firehose")
async def firehose(ws: WebSocket):
    """High-frequency firehose. Pushes everything, every 10ms."""
    await ws.accept()
    r = get_redis()
    streams = await _resolve_streams(r)
    # Timestamp cursor per stream (epoch ms). An index/llen cursor breaks once a
    # capped list saturates (llen stops growing while items keep flowing through
    # the head), silently killing the feed. The newest `ts` survives the cap.
    last_ts: dict[str, int] = {}
    now_ms = int(time.time() * 1000)
    for s in streams:
        head = await r.lindex(s, 0)
        # Seed to the newest existing item so we don't dump history on connect.
        last_ts[s] = _entry_ts(head) if head else now_ms

    last_refresh = time.time()
    msg_count = 0
    started = time.time()

    try:
        await ws.send_json({
            "type": "hello",
            "streams_watched": len(streams),
            "ts": int(time.time() * 1000),
        })

        while True:
            t0 = time.perf_counter_ns()
            messages = []
            for stream in streams:
                seen_ts = last_ts.get(stream, 0)
                # O(1) head peek — skip the lrange when nothing is new. Works at
                # the cap, where llen no longer changes but the head still moves.
                head = await r.lindex(stream, 0)
                if head is None:
                    continue
                head_ts = _entry_ts(head)
                if head_ts <= seen_ts:
                    continue
                # New items live at the LIST head (LPUSH); read newest-first.
                raw_items = await r.lrange(stream, 0, MAX_BATCH - 1)
                for item in raw_items:
                    try:
                        d = json.loads(item)
                    except Exception:
                        continue
                    ts = int(d.get("ts", 0) or 0)
                    if ts <= seen_ts:
                        continue
                    now_ms = int(time.time() * 1000)
                    d["_lag_ms"] = max(0, now_ms - ts) if ts else 0
                    d["_stream"] = stream
                    messages.append(d)
                last_ts[stream] = head_ts

            if messages:
                send_started = time.perf_counter_ns()
                await ws.send_json({
                    "type": "batch",
                    "ts": int(time.time() * 1000),
                    "count": len(messages),
                    "messages": messages,
                })
                send_dur_ns = time.perf_counter_ns() - send_started
                msg_count += len(messages)
                # Record ws broadcast latency for the latency endpoint
                await r.lpush("arb:latency:ws_broadcast", str(send_dur_ns))
                await r.ltrim("arb:latency:ws_broadcast", 0, 999)

            # Periodically refresh stream list (new tick streams may appear)
            if time.time() - last_refresh > 30:
                streams = await _resolve_streams(r)
                seed_ms = int(time.time() * 1000)
                for s in streams:
                    if s not in last_ts:
                        head = await r.lindex(s, 0)
                        last_ts[s] = _entry_ts(head) if head else seed_ms
                last_refresh = time.time()

            elapsed_ns = time.perf_counter_ns() - t0
            # Adaptive sleep — keep 10ms cadence
            sleep_s = max(0, PUSH_INTERVAL - elapsed_ns / 1e9)
            await asyncio.sleep(sleep_s)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "msg": str(e)[:200]})
        except Exception:
            pass
