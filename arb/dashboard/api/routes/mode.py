"""
Runtime mode: DEMO (paper) vs REAL (live money).

- Default is DEMO — safe, simulated capital, no key needed.
- REAL can only be armed when a wallet address is provided (the UI enables the
  button only after the wallet is connected). Even when armed, actual live CLOB
  execution ALSO requires the server to run with PAPER_TRADE=false and a
  POLYMARKET_PRIVATE_KEY configured; without those the engine stays paper.
  So flipping this to "real" is *intent* + a gate, never a way to move real
  money without the operator having set the key on the server.
"""
import os
from fastapi import APIRouter, Body
from arb.infra.redis_bus import get_redis

router = APIRouter(prefix="/api/mode", tags=["mode"])


async def _server_live_ready(r) -> bool:
    """Live-capable if THIS container has the key, or the executor container
    (which holds the key) has signalled arb:live:server_live_ready. Lets the
    dashboard read REAL without the private key being copied into the backend."""
    if (os.getenv("PAPER_TRADE", "true").lower() == "false"
            and bool(os.getenv("POLYMARKET_PRIVATE_KEY", "").strip())):
        return True
    try:
        return bool(await r.get("arb:live:server_live_ready"))
    except Exception:
        return False


@router.get("")
async def get_mode():
    r = get_redis()
    mode = (await r.get("arb:mode")) or "demo"
    wallet = await r.get("arb:mode:wallet")
    # Whether the server is actually capable of live execution.
    server_live_ready = await _server_live_ready(r)
    return {
        "mode": mode,
        "wallet": wallet,
        "server_live_ready": server_live_ready,
        "effective": "real" if (mode == "real" and server_live_ready) else "demo",
    }


@router.post("")
async def set_mode(body: dict = Body(...)):
    r = get_redis()
    mode = str(body.get("mode", "demo")).lower()
    wallet = (body.get("wallet") or "").strip()

    if mode == "real":
        if not wallet:
            return {"ok": False, "error": "wallet_required",
                    "message": "Connect a wallet before enabling REAL mode."}
        await r.set("arb:mode", "real")
        await r.set("arb:mode:wallet", wallet)
    else:
        await r.set("arb:mode", "demo")

    server_live_ready = await _server_live_ready(r)
    return {
        "ok": True,
        "mode": mode,
        "wallet": wallet or None,
        "server_live_ready": server_live_ready,
        "effective": "real" if (mode == "real" and server_live_ready) else "demo",
        "note": None if server_live_ready or mode != "real" else
        "REAL mode armed, but the server has no live key yet — bets stay paper "
        "until the operator sets PAPER_TRADE=false + POLYMARKET_PRIVATE_KEY.",
    }
