"""
Regression tests for the live-order safety gate (scripts/live_safety_checks.py).

Covers the pure pre-flight checks, plus the money-critical fix: bet metadata
containing shell-hostile characters (apostrophes, semicolons, quotes — common in
Polymarket questions) must be recorded verbatim AND must reliably increment the
daily-spend counter, so the daily cap can never be bypassed by a quoting failure.
"""
import importlib.util
import os
import shutil
import subprocess
import uuid

import pytest

_spec = importlib.util.spec_from_file_location(
    "live_safety_checks",
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "live_safety_checks.py"),
)
lsc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lsc)


# ── Pure checks (no redis) ────────────────────────────────────────────────────

def test_bet_size_caps():
    assert lsc.check_bet_size(1.0)[0] is True
    assert lsc.check_bet_size(0)[0] is False
    assert lsc.check_bet_size(lsc.MAX_BET_USD + 0.01)[0] is False


def test_market_open_window():
    from datetime import datetime, timezone, timedelta
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    now = datetime.now(timezone.utc)
    assert lsc.check_market_open((now - timedelta(hours=1)).strftime(fmt))[0] is False  # ended
    assert lsc.check_market_open((now + timedelta(minutes=10)).strftime(fmt))[0] is False  # too soon
    assert lsc.check_market_open((now + timedelta(days=30)).strftime(fmt))[0] is False  # too far
    assert lsc.check_market_open((now + timedelta(hours=24)).strftime(fmt))[0] is True


def test_friction_and_wallet_checks():
    assert lsc.check_friction(None)[0] is False
    assert lsc.check_friction(lsc.MAX_FRICTION_PCT)[0] is False
    assert lsc.check_friction(1.0)[0] is True
    assert lsc.check_wallet_balance(5.0, 1.0)[0] is True
    assert lsc.check_wallet_balance(0.5, 1.0)[0] is False  # 0.5 < 1.0 + 0.10 gas


# ── Redis-backed record + daily cap (skips if no local redis) ─────────────────

def _redis_available() -> bool:
    if not shutil.which("redis-cli"):
        return False
    try:
        out = subprocess.run(["redis-cli", "-p", "6379", "ping"],
                             capture_output=True, text=True, timeout=3).stdout.strip()
        return out.upper() == "PONG"
    except Exception:
        return False


@pytest.mark.skipif(not _redis_available(), reason="no local redis-cli on :6379")
def test_record_live_bet_survives_hostile_meta_and_tracks_cap(monkeypatch):
    monkeypatch.setattr(lsc, "_REDIS_CLI_OVERRIDE", "redis-cli -p 6379")
    key = lsc._today_key()
    tag = uuid.uuid4().hex[:8]
    subprocess.run(["redis-cli", "-p", "6379", "DEL", key, "arb:live:orders"], capture_output=True)

    hostile = {"question": f"Will Trump's 'deal'; drop? \"BTC\" {tag}", "note": "a;b|c`d$e"}
    lsc.record_live_bet(order_id=f"ord-{tag}", size_usdc=1.25, meta=hostile)

    import json
    raw = subprocess.run(["redis-cli", "-p", "6379", "LINDEX", "arb:live:orders", "0"],
                         capture_output=True, text=True).stdout.strip()
    d = json.loads(raw)  # must be valid JSON
    assert d["question"] == hostile["question"]  # verbatim, uncorrupted
    assert d["note"] == hostile["note"]

    spend = subprocess.run(["redis-cli", "-p", "6379", "GET", key],
                           capture_output=True, text=True).stdout.strip()
    assert abs(float(spend) - 1.25) < 1e-9  # cap counter incremented despite hostile meta

    # Cap enforcement reads the same counter back.
    assert lsc.check_daily_limit(lsc.DAILY_LIMIT_USD)[0] is False   # 1.25 + 5.0 > 5.0
    assert lsc.check_daily_limit(0.5)[0] is True                    # 1.25 + 0.5 < 5.0
    subprocess.run(["redis-cli", "-p", "6379", "DEL", key, "arb:live:orders"], capture_output=True)
