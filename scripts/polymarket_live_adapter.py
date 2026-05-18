"""
F7 — Polymarket Live Adapter
Wrapper around py-clob-client for actual order placement on Polygon mainnet.

Usage:
  from scripts.polymarket_live_adapter import setup_client, check_wallet_balance, ...

IMPORTANT: Set env vars before use:
  POLY_PRIVATE_KEY, POLY_WALLET_ADDRESS, POLY_HOST, POLY_CHAIN_ID
"""
import json
import os
import subprocess
import time
from typing import Optional

HOST = os.environ.get("POLY_HOST", "https://clob.polymarket.com")
PRIVATE_KEY = os.environ.get("POLY_PRIVATE_KEY", "")
WALLET_ADDRESS = os.environ.get("POLY_WALLET_ADDRESS", "")
CHAIN_ID = int(os.environ.get("POLY_CHAIN_ID", "137"))

_client = None  # cached client singleton


def setup_client():
    """Initialize and return ClobClient. Cached after first call."""
    global _client
    if _client is not None:
        return _client

    # Lazy import — fails clearly if py-clob-client not installed
    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        raise ImportError(
            "py-clob-client not installed. Run: pip install py-clob-client"
        )

    if not PRIVATE_KEY:
        raise ValueError("POLY_PRIVATE_KEY not set in environment")
    if not WALLET_ADDRESS:
        raise ValueError("POLY_WALLET_ADDRESS not set in environment")

    client = ClobClient(
        host=HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=0,       # 0 = EOA (standard MetaMask wallet)
        funder=WALLET_ADDRESS,
    )
    # Auto-derive L2 API creds from L1 private key (required for order ops)
    client.set_api_creds(client.create_or_derive_api_creds())

    _client = client
    return _client


def check_wallet_balance() -> dict:
    """
    Return USDC balance and allowance from Polymarket CLOB.
    NOTE: Polymarket uses USDC.e (bridged) on Polygon: 0x2791Bca...
    Balance reported here is what Polymarket can see/use for orders.
    """
    from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

    client = setup_client()
    # Must pass BalanceAllowanceParams explicitly — default None causes AttributeError
    params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
    raw = client.get_balance_allowance(params=params)
    # USDC has 6 decimals
    balance = int(raw.get("balance", 0)) / 1_000_000
    # allowances is a dict of contract→amount in v0.34.x
    allowances_raw = raw.get("allowances", raw.get("allowance", {}))
    if isinstance(allowances_raw, dict):
        total_allowance = sum(int(v) for v in allowances_raw.values()) / 1_000_000
    else:
        total_allowance = int(allowances_raw or 0) / 1_000_000
    return {
        "balance_usdc": round(balance, 6),
        "allowance_usdc": round(total_allowance, 6),
        "allowances_per_contract": allowances_raw,
        "wallet": WALLET_ADDRESS,
        "raw": raw,
    }


def search_markets(keyword: str, limit: int = 10) -> list[dict]:
    """
    Search Polymarket markets by keyword.
    Returns simplified list sorted by end date.
    """
    client = setup_client()
    try:
        # get_markets returns paginated results; next_cursor='' for first page
        resp = client.get_markets(next_cursor="")
        markets = resp.get("data", []) if isinstance(resp, dict) else []
    except Exception as e:
        return [{"error": str(e)}]

    kw = keyword.lower()
    results = []
    for m in markets:
        question = m.get("question", "") or ""
        if kw not in question.lower():
            continue
        tokens = m.get("tokens", [])
        results.append({
            "condition_id": m.get("condition_id", ""),
            "question": question,
            "end_date_iso": m.get("end_date_iso", ""),
            "active": m.get("active", False),
            "closed": m.get("closed", False),
            "tokens": [
                {
                    "outcome": t.get("outcome", ""),
                    "token_id": t.get("token_id", ""),
                    "price": t.get("price", None),
                }
                for t in tokens
            ],
        })
        if len(results) >= limit:
            break

    return results


def get_market_details(condition_id: str) -> dict:
    """Return market info + top-of-book for a condition_id."""
    client = setup_client()
    try:
        market = client.get_market(condition_id)
    except Exception as e:
        return {"error": str(e), "condition_id": condition_id}

    tokens = market.get("tokens", []) if isinstance(market, dict) else []

    order_books = {}
    for token in tokens:
        token_id = token.get("token_id") if isinstance(token, dict) else getattr(token, "token_id", None)
        outcome = token.get("outcome") if isinstance(token, dict) else getattr(token, "outcome", str(token_id))
        if not token_id:
            continue
        try:
            ob = client.get_order_book(token_id)
            bids = ob.bids[:3] if hasattr(ob, "bids") and ob.bids else []
            asks = ob.asks[:3] if hasattr(ob, "asks") and ob.asks else []
            order_books[outcome] = {
                "token_id": token_id,
                "best_bid": float(bids[0].price) if bids else None,
                "best_ask": float(asks[0].price) if asks else None,
                "bids_top3": [(float(b.price), float(b.size)) for b in bids],
                "asks_top3": [(float(a.price), float(a.size)) for a in asks],
            }
        except Exception as e:
            order_books[outcome] = {"token_id": token_id, "error": str(e)}

    m = market if isinstance(market, dict) else {}
    return {
        "condition_id": condition_id,
        "question": m.get("question", getattr(market, "question", "")),
        "end_date_iso": m.get("end_date_iso", getattr(market, "end_date_iso", "")),
        "active": m.get("active", True),
        "tokens": [
            {
                "outcome": (t.get("outcome") if isinstance(t, dict) else getattr(t, "outcome", "")),
                "token_id": (t.get("token_id") if isinstance(t, dict) else getattr(t, "token_id", "")),
                "price": (t.get("price") if isinstance(t, dict) else getattr(t, "price", None)),
            }
            for t in tokens
        ],
        "order_books": order_books,
    }


def calculate_friction(token_id: str, side: str, size_usdc: float) -> dict:
    """
    Estimate total friction for a potential order.
    side: "BUY" or "SELL"
    size_usdc: order size in USDC
    """
    client = setup_client()
    spread_pct = None
    best_price = None

    try:
        ob = client.get_order_book(token_id)
        bids = ob.bids if hasattr(ob, "bids") and ob.bids else []
        asks = ob.asks if hasattr(ob, "asks") and ob.asks else []

        best_bid = float(bids[0].price) if bids else None
        best_ask = float(asks[0].price) if asks else None

        if best_bid and best_ask and best_bid > 0:
            spread = best_ask - best_bid
            mid = (best_ask + best_bid) / 2
            spread_pct = (spread / mid) * 100 if mid > 0 else 0

        best_price = best_ask if side.upper() == "BUY" else best_bid
    except Exception:
        pass

    polymarket_fee_pct = 2.0    # 2% from winnings (not from stake)
    gas_est_usd = 0.03          # ~$0.03 Polygon gas per tx

    # Total friction: half-spread (market impact) + fee as % of size
    # Fee is 2% of winnings ≈ 2% × (1/price - 1) × size, but simplified:
    # For a $1 bet at 0.50 odds: potential winnings = $1, fee = $0.02 = 2% of size
    total_friction_pct = None
    if spread_pct is not None:
        total_friction_pct = round(spread_pct / 2 + polymarket_fee_pct, 2)

    return {
        "token_id": token_id,
        "side": side,
        "size_usdc": size_usdc,
        "best_price": best_price,
        "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
        "polymarket_fee_pct": polymarket_fee_pct,
        "gas_est_usd": gas_est_usd,
        "total_friction_pct": total_friction_pct,
        "acceptable": (total_friction_pct is not None and total_friction_pct < 10.0),
    }


def place_live_order(
    token_id: str,
    side: str,          # "BUY" or "SELL"
    price: float,       # limit price 0.01–0.99
    size: float,        # order size in shares (at given price, cost = price × size USDC)
    dry_run: bool = True,
) -> dict:
    """
    Place a limit order (GTC) on Polymarket.

    dry_run=True  → validate + sign, DO NOT submit to CLOB
    dry_run=False → ACTUAL submit (only call with --confirm)

    price: 0.01–0.99 (Yes price, must match market tick_size)
    size: shares to buy (USDC cost = price × size)
    """
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY, SELL

    client = setup_client()
    side_const = BUY if side.upper() == "BUY" else SELL

    # Round price to 2 decimals (tick_size=0.01 most markets)
    price_rounded = round(price, 2)
    size_rounded = round(size, 2)
    estimated_cost = round(price_rounded * size_rounded, 4)

    order_args = OrderArgs(
        token_id=token_id,
        price=price_rounded,
        size=size_rounded,
        side=side_const,
    )
    signed_order = client.create_order(order_args)

    if dry_run:
        return {
            "dry_run": True,
            "status": "validated",
            "would_place": {
                "token_id": token_id,
                "side": side,
                "price": price_rounded,
                "size": size_rounded,
                "estimated_cost_usdc": estimated_cost,
            },
            "signed": True,
            "order_hash": getattr(signed_order, "hash", None),
        }

    # ACTUAL submit — only reached when dry_run=False
    resp = client.post_order(signed_order, OrderType.GTC)
    order_id = (
        resp.get("orderID")
        or resp.get("order_id")
        or resp.get("id")
        or ""
    )
    return {
        "dry_run": False,
        "status": "submitted",
        "order_id": order_id,
        "transaction_hash": resp.get("transactionHash"),
        "response": resp,
        "placed": {
            "token_id": token_id,
            "side": side,
            "price": price_rounded,
            "size": size_rounded,
            "estimated_cost_usdc": estimated_cost,
        },
    }


def check_order_status(order_id: str) -> dict:
    """Check status of a specific order by ID."""
    client = setup_client()
    try:
        order = client.get_order(order_id)
        if isinstance(order, dict):
            return {
                "order_id": order_id,
                "status": order.get("status", "unknown"),
                "size_matched": order.get("size_matched"),
                "price": order.get("price"),
                "side": order.get("side"),
                "raw": order,
            }
        return {
            "order_id": order_id,
            "status": getattr(order, "status", "unknown"),
            "size_matched": getattr(order, "size_matched", None),
            "price": getattr(order, "price", None),
            "side": getattr(order, "side", None),
        }
    except Exception as e:
        return {"order_id": order_id, "error": str(e)}


def cancel_order(order_id: str) -> dict:
    """Cancel a specific pending order."""
    client = setup_client()
    try:
        result = client.cancel(order_id=order_id)
        return {"status": "cancelled", "order_id": order_id, "result": result}
    except Exception as e:
        return {"status": "error", "order_id": order_id, "error": str(e)}


def emergency_stop_all() -> dict:
    """Cancel ALL open orders. Use in emergencies."""
    client = setup_client()
    try:
        result = client.cancel_all()
        return {"status": "all_cancelled", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}
