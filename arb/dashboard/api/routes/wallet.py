"""
Wallet integration — multi-wallet support.

Multiple wallets can be connected simultaneously. Each has its own Redis key.
One wallet is designated "active" (used for trade sizing).

Keys:
  arb:wallet:linked:{addr}   — per-wallet snapshot
  arb:wallet:list            — Redis Set of all linked addresses
  arb:wallet:active          — active wallet address string
"""
import asyncio
import json
import time
from fastapi import APIRouter
from pydantic import BaseModel, Field
import httpx
from arb.infra.redis_bus import get_redis, publish

router = APIRouter(prefix="/api/wallet", tags=["wallet"])

WALLET_LIST_KEY = "arb:wallet:list"
WALLET_ACTIVE_KEY = "arb:wallet:active"
REFRESH_MIN_INTERVAL_MS = 30_000

POLYGON_RPCS = [
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
    "https://polygon.llamarpc.com",
    "https://polygon-bor-rpc.publicnode.com",
]

USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"


def _wallet_key(address: str) -> str:
    return f"arb:wallet:linked:{address.lower()}"


class LinkRequest(BaseModel):
    address: str = Field(..., description="0x-prefixed wallet address")
    chain_id: int = Field(137)
    signature: str | None = None
    nonce: str | None = None
    usdc_balance: float = Field(0.0)
    matic_balance: float = Field(0.0)
    wallet_name: str | None = None
    wallet_icon: str | None = None


class SyncRequest(BaseModel):
    address: str
    usdc_balance: float
    matic_balance: float = 0.0


class SetActiveRequest(BaseModel):
    address: str


async def _rpc_call(method: str, params: list) -> dict | None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with httpx.AsyncClient(timeout=httpx.Timeout(6, connect=3)) as client:
        for rpc in POLYGON_RPCS:
            try:
                r = await client.post(rpc, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    if "result" in data:
                        return data
            except Exception:
                continue
    return None


def _addr_to_hex_padded(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


async def fetch_matic_balance(address: str) -> float:
    data = await _rpc_call("eth_getBalance", [address, "latest"])
    if not data:
        return 0.0
    try:
        return int(data["result"], 16) / 1e18
    except Exception:
        return 0.0


async def fetch_usdc_balance(address: str, contract: str = USDC_E) -> float:
    call_data = "0x70a08231" + _addr_to_hex_padded(address)
    data = await _rpc_call("eth_call", [{"to": contract, "data": call_data}, "latest"])
    if not data:
        return 0.0
    try:
        return int(data["result"], 16) / 1e6
    except Exception:
        return 0.0


async def fetch_total_usdc(address: str) -> tuple[float, float]:
    a, b = await asyncio.gather(
        fetch_usdc_balance(address, USDC_E),
        fetch_usdc_balance(address, USDC_NATIVE),
        return_exceptions=True,
    )
    return float(a if not isinstance(a, Exception) else 0.0), \
           float(b if not isinstance(b, Exception) else 0.0)


async def refresh_wallet_balance(address: str, force: bool = False) -> dict | None:
    r = get_redis()
    raw = await r.get(_wallet_key(address))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None

    now_ms = int(time.time() * 1000)
    last_sync = int(data.get("last_chain_sync", 0) or 0)
    if not force and (now_ms - last_sync) < REFRESH_MIN_INTERVAL_MS:
        return data

    try:
        usdc_e, usdc_native = await fetch_total_usdc(address)
        matic = await fetch_matic_balance(address)
        total_usdc = round(usdc_e + usdc_native, 4)
        data["usdc_balance"] = total_usdc
        data["usdc_e_balance"] = round(usdc_e, 4)
        data["usdc_native_balance"] = round(usdc_native, 4)
        data["matic_balance"] = round(matic, 6)
        data["last_chain_sync"] = now_ms
        await r.set(_wallet_key(address), json.dumps(data))
    except Exception as e:
        data["refresh_error"] = str(e)[:120]
    return data


async def _get_all_wallets(r, auto_refresh: bool = False) -> list[dict]:
    """Return all linked wallets from Redis."""
    addrs = await r.smembers(WALLET_LIST_KEY)
    if not addrs:
        return []

    wallets = []
    for raw_addr in addrs:
        addr = raw_addr.decode() if isinstance(raw_addr, bytes) else raw_addr
        if auto_refresh:
            data = await refresh_wallet_balance(addr, force=False)
        else:
            raw = await r.get(_wallet_key(addr))
            data = json.loads(raw) if raw else None
        if data:
            data["linked"] = True
            wallets.append(data)

    active_raw = await r.get(WALLET_ACTIVE_KEY)
    active_addr = (active_raw.decode() if isinstance(active_raw, bytes) else active_raw) if active_raw else None

    # Mark which one is active; if none set, make the first one active
    for w in wallets:
        w["is_active"] = w["address"].lower() == (active_addr or "").lower()
    if wallets and not any(w["is_active"] for w in wallets):
        wallets[0]["is_active"] = True
        await r.set(WALLET_ACTIVE_KEY, wallets[0]["address"])

    wallets.sort(key=lambda w: (not w["is_active"], w.get("linked_at", 0)))
    return wallets


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/link")
async def link_wallet(req: LinkRequest):
    """Link a wallet. Multiple wallets supported."""
    if not req.address.startswith("0x") or len(req.address) != 42:
        return {"ok": False, "error": "invalid address"}

    addr = req.address.lower()

    try:
        usdc_e, usdc_native = await fetch_total_usdc(addr)
        matic = await fetch_matic_balance(addr)
        chain_usdc = round(usdc_e + usdc_native, 4)
        usdc_balance = chain_usdc if chain_usdc > 0 else req.usdc_balance
        matic_balance = matic if matic > 0 else req.matic_balance
    except Exception:
        usdc_balance = req.usdc_balance
        matic_balance = req.matic_balance
        usdc_e = req.usdc_balance
        usdc_native = 0.0

    payload = {
        "address": addr,
        "chain_id": req.chain_id,
        "linked_at": int(time.time() * 1000),
        "last_chain_sync": int(time.time() * 1000),
        "usdc_balance": usdc_balance,
        "usdc_e_balance": round(usdc_e, 4),
        "usdc_native_balance": round(usdc_native, 4),
        "matic_balance": matic_balance,
        "signature": req.signature,
        "nonce": req.nonce,
        "wallet_name": req.wallet_name,
        "wallet_icon": req.wallet_icon,
        "status": "linked",
    }

    r = get_redis()
    await r.set(_wallet_key(addr), json.dumps(payload))
    await r.sadd(WALLET_LIST_KEY, addr)

    # Auto-set as active if it's the first wallet
    existing_active = await r.get(WALLET_ACTIVE_KEY)
    if not existing_active:
        await r.set(WALLET_ACTIVE_KEY, addr)
        payload["is_active"] = True
    else:
        active = existing_active.decode() if isinstance(existing_active, bytes) else existing_active
        payload["is_active"] = (active == addr)

    await publish("arb:wallet:events", {
        "event": "LINK", "address": addr,
        "balance": payload["usdc_balance"], "ts": payload["linked_at"],
    })

    all_wallets = await _get_all_wallets(r)
    return {"ok": True, "wallet": payload, "all_wallets": all_wallets}


@router.get("/info")
async def get_wallet_info():
    """Return active wallet info (backwards compat)."""
    r = get_redis()
    wallets = await _get_all_wallets(r, auto_refresh=True)
    if not wallets:
        return {"linked": False}
    active = next((w for w in wallets if w.get("is_active")), wallets[0])
    return active


@router.get("/list")
async def list_wallets():
    """Return all linked wallets."""
    r = get_redis()
    wallets = await _get_all_wallets(r, auto_refresh=True)
    total_usdc = sum(w.get("usdc_balance", 0) for w in wallets)
    return {
        "wallets": wallets,
        "count": len(wallets),
        "total_usdc": round(total_usdc, 4),
    }


@router.post("/set-active")
async def set_active_wallet(req: SetActiveRequest):
    """Set which wallet is the active trading wallet."""
    r = get_redis()
    addr = req.address.lower()
    members = await r.smembers(WALLET_LIST_KEY)
    addrs = {(m.decode() if isinstance(m, bytes) else m) for m in members}
    if addr not in addrs:
        return {"ok": False, "error": "wallet not linked"}
    await r.set(WALLET_ACTIVE_KEY, addr)
    await publish("arb:wallet:events", {
        "event": "SET_ACTIVE", "address": addr, "ts": int(time.time() * 1000),
    })
    wallets = await _get_all_wallets(r)
    return {"ok": True, "active": addr, "all_wallets": wallets}


@router.post("/unlink")
async def unlink_wallet(req: SetActiveRequest | None = None):
    """Unlink a specific wallet, or all wallets if no address given."""
    r = get_redis()

    if req and req.address:
        addr = req.address.lower()
        await r.delete(_wallet_key(addr))
        await r.srem(WALLET_LIST_KEY, addr)
        # If this was active, promote next wallet
        active_raw = await r.get(WALLET_ACTIVE_KEY)
        active = (active_raw.decode() if isinstance(active_raw, bytes) else active_raw) if active_raw else None
        if active == addr:
            await r.delete(WALLET_ACTIVE_KEY)
            remaining = await r.smembers(WALLET_LIST_KEY)
            if remaining:
                next_addr = list(remaining)[0]
                next_addr = next_addr.decode() if isinstance(next_addr, bytes) else next_addr
                await r.set(WALLET_ACTIVE_KEY, next_addr)
        await publish("arb:wallet:events", {
            "event": "UNLINK", "address": addr, "ts": int(time.time() * 1000),
        })
        wallets = await _get_all_wallets(r)
        return {"ok": True, "unlinked": addr, "remaining": len(wallets), "all_wallets": wallets}
    else:
        # Unlink all
        members = await r.smembers(WALLET_LIST_KEY)
        for m in members:
            addr = m.decode() if isinstance(m, bytes) else m
            await r.delete(_wallet_key(addr))
        await r.delete(WALLET_LIST_KEY)
        await r.delete(WALLET_ACTIVE_KEY)
        await publish("arb:wallet:events", {
            "event": "UNLINK_ALL", "ts": int(time.time() * 1000),
        })
        return {"ok": True, "unlinked": "all"}


@router.post("/sync")
async def sync_balance(req: SyncRequest):
    """Frontend pushes fresh balance from its provider."""
    r = get_redis()
    addr = req.address.lower()
    raw = await r.get(_wallet_key(addr))
    if not raw:
        return {"ok": False, "error": "wallet not linked"}
    data = json.loads(raw)
    data["usdc_balance"] = req.usdc_balance
    data["matic_balance"] = req.matic_balance
    data["last_sync"] = int(time.time() * 1000)
    await r.set(_wallet_key(addr), json.dumps(data))
    asyncio.create_task(refresh_wallet_balance(addr, force=True))
    return {"ok": True, "balance": req.usdc_balance}


class PreviewRequest(BaseModel):
    address: str


@router.post("/preview-balance")
async def preview_balance(req: PreviewRequest):
    """Preview wallet balance without linking — used by connect modal."""
    addr = req.address.strip().lower()
    if not addr.startswith("0x") or len(addr) != 42:
        return {"ok": False, "error": "invalid address"}
    try:
        usdc_e, usdc_native = await fetch_total_usdc(addr)
        matic = await fetch_matic_balance(addr)
        return {
            "ok": True,
            "address": addr,
            "usdc_balance": round(usdc_e + usdc_native, 4),
            "usdc_e_balance": round(usdc_e, 4),
            "usdc_native_balance": round(usdc_native, 4),
            "matic_balance": round(matic, 6),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


@router.post("/refresh")
async def force_refresh(req: SetActiveRequest | None = None):
    """Force backend to re-fetch wallet balance from chain."""
    r = get_redis()
    if req and req.address:
        data = await refresh_wallet_balance(req.address.lower(), force=True)
    else:
        # Refresh active wallet
        active_raw = await r.get(WALLET_ACTIVE_KEY)
        if not active_raw:
            return {"ok": False, "error": "no wallet linked"}
        addr = active_raw.decode() if isinstance(active_raw, bytes) else active_raw
        data = await refresh_wallet_balance(addr, force=True)
    if not data:
        return {"ok": False, "error": "wallet not found"}
    return {"ok": True, **data}


# ─── Backwards compat: old single-wallet key migration ───────────────────────
async def _migrate_old_wallet():
    """Migrate legacy arb:wallet:linked → per-address key on startup."""
    try:
        r = get_redis()
        raw = await r.get("arb:wallet:linked")
        if raw:
            data = json.loads(raw)
            addr = data.get("address")
            if addr:
                await r.set(_wallet_key(addr), raw)
                await r.sadd(WALLET_LIST_KEY, addr)
                existing_active = await r.get(WALLET_ACTIVE_KEY)
                if not existing_active:
                    await r.set(WALLET_ACTIVE_KEY, addr)
            await r.delete("arb:wallet:linked")
    except Exception:
        pass
