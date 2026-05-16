"""Tests for the ensemble signal gate."""
import time
import pytest
from arb.edges.ensemble import SignalVote, check_gate, _apply_cluster_rule


def _vote(source: str, direction: str, confidence: float = 0.7,
          cid: str = "cond-abc") -> SignalVote:
    return SignalVote(
        condition_id=cid,
        direction=direction,
        confidence=confidence,
        source=source,
        asset="BTC/USDT",
        kind="updown",
        ts=int(time.time() * 1000),
    )


# ── Gate: fewer than MIN_ACTIVE_CLUSTERS ──────────────────────────────────────

def test_gate_rejects_fewer_than_3_clusters():
    votes = [
        _vote("smart_money", "yes"),   # cluster C
        _vote("yesno_arb",   "yes"),   # cluster B
    ]
    approved, direction, meta = check_gate(votes)
    assert not approved
    assert "only 2 active clusters" in meta["reason"]


def test_gate_rejects_3_of_6_when_less_than_3_active():
    """Hard 3-of-6 threshold breaks when only 2 signals are active.
    Our 3-of-ACTIVE gate handles this correctly."""
    votes = [
        _vote("smart_money", "yes"),   # cluster C
        _vote("news_reaction", "yes"), # cluster D
    ]
    approved, _, _ = check_gate(votes)
    assert not approved


# ── Gate: correlated signals count as one vote ────────────────────────────────

def test_correlated_signals_count_as_one_cluster():
    """momentum + basis_carry are both cluster A — only one vote counted."""
    votes = [
        _vote("momentum",    "yes"),   # cluster A
        _vote("basis_carry", "yes"),   # cluster A — same cluster, doesn't add a vote
        _vote("smart_money", "yes"),   # cluster C
        _vote("news_reaction","yes"),  # cluster D
    ]
    cluster_votes = _apply_cluster_rule(votes)
    # momentum and basis_carry collapse to 1 (highest confidence kept)
    assert "A" in cluster_votes
    assert len([c for c in cluster_votes if c == "A"]) == 1
    # Total unique clusters = 3 (A, C, D)
    assert len(cluster_votes) == 3


def test_correlated_cluster_keeps_highest_confidence():
    votes = [
        _vote("momentum",    "yes", confidence=0.5),   # cluster A, lower
        _vote("basis_carry", "yes", confidence=0.8),   # cluster A, higher
    ]
    cluster_votes = _apply_cluster_rule(votes)
    assert cluster_votes["A"].source == "basis_carry"
    assert cluster_votes["A"].confidence == 0.8


# ── Gate: 3-of-ACTIVE approves correctly ──────────────────────────────────────

def test_gate_approves_3_of_4_clusters_yes():
    votes = [
        _vote("smart_money",    "yes"),  # C
        _vote("news_reaction",  "yes"),  # D
        _vote("yesno_arb",      "yes"),  # B
        _vote("basis_carry",    "no"),   # A — disagrees
    ]
    approved, direction, meta = check_gate(votes)
    assert approved
    assert direction == "yes"
    assert meta["yes_count"] == 3


def test_gate_approves_3_of_3_clusters_no():
    votes = [
        _vote("smart_money",   "no"),   # C
        _vote("news_reaction", "no"),   # D
        _vote("yesno_arb",     "no"),   # B
    ]
    approved, direction, meta = check_gate(votes)
    assert approved
    assert direction == "no"


def test_gate_rejects_split_2_2():
    votes = [
        _vote("smart_money",   "yes"),  # C
        _vote("news_reaction", "yes"),  # D
        _vote("yesno_arb",     "no"),   # B
        _vote("basis_carry",   "no"),   # A
    ]
    approved, _, meta = check_gate(votes)
    assert not approved
    assert "yes=2" in meta["reason"] or meta.get("yes_count", 0) < 3


# ── Stale vote filtering ───────────────────────────────────────────────────────

def test_stale_votes_are_excluded():
    """Votes older than WINDOW_SECONDS should not be counted."""
    old_ts = int((time.time() - 60) * 1000)   # 60s ago, beyond 30s window
    fresh_ts = int(time.time() * 1000)

    fresh_votes = [
        SignalVote("cond1", "yes", 0.7, "smart_money",   "BTC/USDT", "updown", fresh_ts),
        SignalVote("cond1", "yes", 0.7, "news_reaction", "BTC/USDT", "updown", fresh_ts),
        SignalVote("cond1", "yes", 0.7, "yesno_arb",     "BTC/USDT", "updown", fresh_ts),
    ]
    stale_votes = [
        SignalVote("cond1", "no",  0.9, "basis_carry",   "BTC/USDT", "updown", old_ts),
        SignalVote("cond1", "no",  0.9, "related_markets","BTC/USDT","updown", old_ts),
    ]

    # Simulate what _read_recent_votes does: filter by cutoff
    from arb.edges.ensemble import WINDOW_SECONDS
    cutoff_ms = (time.time() - WINDOW_SECONDS) * 1000
    live_votes = [v for v in (fresh_votes + stale_votes) if v.ts >= cutoff_ms]

    approved, direction, meta = check_gate(live_votes)
    assert approved
    assert direction == "yes"   # stale "no" votes excluded
