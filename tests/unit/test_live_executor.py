"""
Tests for the autonomous live executor's per-bet decision (_act_on_bet).

Every real-order dependency (market lookup, balance, friction, order placement)
is monkeypatched, so nothing hits the network or places an order. These pin the
money-critical guarantees: idempotency, the stale/low-edge/one-per-market gates,
the lifetime total cap, and that a placed order goes through with the right args.

Skips when no local redis is on :6379 (the executor + safety modules need it).
"""
import importlib
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LIVE_SAFETY_REDIS_URL", "redis://localhost:6379/0")


def _redis_up() -> bool:
    if not shutil.which("redis-cli"):
        return False
    try:
        return subprocess.run(["redis-cli", "-p", "6379", "ping"],
                              capture_output=True, text=True, timeout=3).stdout.strip().upper() == "PONG"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_up(), reason="no local redis on :6379")

exe = importlib.import_module("scripts.live_autonomous_executor")
adapter = importlib.import_module("scripts.polymarket_live_adapter")


@pytest.fixture
def clean(monkeypatch):
    # wipe executor + safety state
    for k in ("arb:live:executed", "arb:live:open_conditions", "arb:live:open_count",
              "arb:live:total_spend", "arb:live:last_bet_ts", "arb:live:resolved_seen",
              "arb:live:halted", "arb:live:consecutive_losses"):
        exe._rc.delete(k)
    exe._rc.delete("arb:live:daily_spend:" + datetime.now(timezone.utc).strftime("%Y%m%d"))
    exe._rc.delete("arb:live:orders")

    placed = []

    def fake_market(cond):
        return {
            "condition_id": cond,
            "end_date_iso": (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tokens": [{"outcome": "Up", "token_id": "tok-up"},
                       {"outcome": "Down", "token_id": "tok-down"}],
            "order_books": {"Up": {"best_ask": 0.55}, "Down": {"best_ask": 0.45}},
        }

    def fake_place(token_id, side, price, size, dry_run=True):
        placed.append({"token_id": token_id, "side": side, "price": price, "size": size, "dry_run": dry_run})
        return {"order_id": f"ord-{uuid.uuid4().hex[:6]}", "dry_run": dry_run, "status": "submitted"}

    monkeypatch.setattr(adapter, "get_market_details", fake_market)
    monkeypatch.setattr(adapter, "check_wallet_balance",
                        lambda: {"balance_usdc": 50.0, "relay_mode": False})
    monkeypatch.setattr(adapter, "calculate_friction",
                        lambda *a, **k: {"total_friction_pct": 2.0})
    monkeypatch.setattr(adapter, "place_live_order", fake_place)
    return placed


def _bet(**over):
    b = {"id": f"bet-{uuid.uuid4().hex[:8]}", "ts": exe._now_ms(),
         "condition_id": "0x" + uuid.uuid4().hex, "side": "Up",
         "stake_usd": 1.5, "edge_bps": 700, "status": "open", "source": "window_lag"}
    b.update(over)
    return b


def test_happy_path_places_once_and_is_idempotent(clean):
    placed = clean
    bet = _bet()
    msg = exe._act_on_bet(bet)
    assert msg.startswith("✅ PLACED"), msg
    assert len(placed) == 1
    p = placed[0]
    assert p["side"] == "BUY" and p["token_id"] == "tok-up" and p["dry_run"] is False
    assert abs(p["price"] - 0.55) < 1e-9
    assert exe._rc.sismember("arb:live:executed", bet["id"])
    assert int(exe._rc.get("arb:live:open_count")) == 1
    assert float(exe._rc.get("arb:live:total_spend")) > 0
    # second pass: no duplicate order
    assert exe._act_on_bet(bet) == ""
    assert len(placed) == 1


def test_stale_and_low_edge_skipped(clean):
    placed = clean
    stale = _bet(ts=exe._now_ms() - (exe.MAX_SIGNAL_AGE_SEC + 60) * 1000)
    assert "stale" in exe._act_on_bet(stale)
    weak = _bet(edge_bps=100)
    assert "edge" in exe._act_on_bet(weak)
    assert len(placed) == 0


def test_one_position_per_market(clean):
    placed = clean
    cond = "0x" + uuid.uuid4().hex
    exe._act_on_bet(_bet(condition_id=cond))
    assert len(placed) == 1
    # a fresh bet id on the SAME market must not place a second order
    msg = exe._act_on_bet(_bet(condition_id=cond))
    assert "already have a live position" in msg
    assert len(placed) == 1


def test_total_cap_halts_and_blocks(clean, monkeypatch):
    placed = clean
    monkeypatch.setattr(exe, "MIN_SECONDS_BETWEEN_BETS", 0)  # ignore rate limit here
    exe._rc.set("arb:live:total_spend", exe.TOTAL_CAP_USD - 0.5)  # only $0.50 head-room
    msg = exe._act_on_bet(_bet(stake_usd=1.5))
    assert "total cap" in msg.lower()
    assert len(placed) == 0
    assert exe._rc.get("arb:live:halted")  # kill-switch tripped


def test_failing_friction_check_does_not_place(clean, monkeypatch):
    placed = clean
    monkeypatch.setattr(adapter, "calculate_friction", lambda *a, **k: {"total_friction_pct": 25.0})
    msg = exe._act_on_bet(_bet())
    assert "checks" in msg.lower()
    assert len(placed) == 0
