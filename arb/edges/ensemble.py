"""
Polymarket Signal Ensemble — 3-of-ACTIVE gate.

Architecture:
  Each edge detector emits SignalVote dicts to Redis Stream arb:edges:votes.
  This module buffers votes by condition_id (30-second window) and gates:
    - Minimum 4 signals must have an opinion
    - At least 3 must agree on the same direction
    - Correlated price-derived signals count as ONE vote cluster

Signal independence rules (prevents false confidence):
  Cluster A — price-derived (momentum/GBM, basis_carry): max 1 vote
  Cluster B — market-structure (yesno_arb, related_markets): max 1 vote
  Cluster C — behavioral (smart_money, time_decay): max 1 vote
  Cluster D — external (news_reaction): max 1 vote

So max 4 independent votes. Gate: 3-of-4 independent clusters agree.

Each detector publishes to arb:edges:votes via emit_vote().
"""
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Literal

from arb.infra.redis_bus import get_redis

VOTE_STREAM = "arb:edges:votes"
APPROVED_STREAM = "arb:edges:approved"
WINDOW_SECONDS = 30          # votes older than this are stale
MIN_ACTIVE_CLUSTERS = 3      # need opinions from at least 3 independent clusters
MIN_AGREEING = 3             # at least 3 clusters must agree on same direction

# Map each source to its independence cluster
SOURCE_CLUSTER = {
    "basis_carry":      "A",  # price-derived carry
    "momentum":         "A",  # price-derived momentum (future)
    "yesno_arb":        "B",  # market-structure math arb
    "related_markets":  "B",  # market-structure ordering
    "smart_money":      "C",  # behavioral whale copy
    "time_decay":       "C",  # behavioral near-expiry
    "news_reaction":    "D",  # external event-driven
    "onchain_intel":    "E",  # on-chain whale/insider signals
}


@dataclass
class SignalVote:
    condition_id: str
    direction: Literal["yes", "no"]   # which outcome to bet on
    confidence: float                  # 0–1
    source: str                        # detector name (must be in SOURCE_CLUSTER)
    asset: str                         # e.g. "BTC/USDT"
    kind: str                          # "updown" | "range" | "yesno"
    ts: int                            # epoch ms


async def emit_vote(vote: SignalVote) -> None:
    """Detectors call this to register a vote. Fire-and-forget."""
    r = get_redis()
    await r.xadd(VOTE_STREAM, {"data": json.dumps(asdict(vote))}, maxlen=5000)


async def _read_recent_votes(r, condition_id: str) -> list[SignalVote]:
    """Read last 5000 votes and return those matching condition_id within window."""
    cutoff_ms = (time.time() - WINDOW_SECONDS) * 1000
    try:
        entries = await r.xrevrange(VOTE_STREAM, count=2000)
    except Exception:
        return []

    votes: list[SignalVote] = []
    for _msg_id, fields in entries:
        try:
            d = json.loads(fields[b"data"] if b"data" in fields else fields["data"])
            if d.get("condition_id") != condition_id:
                continue
            if d.get("ts", 0) < cutoff_ms:
                continue
            votes.append(SignalVote(**d))
        except Exception:
            continue
    return votes


def _apply_cluster_rule(votes: list[SignalVote]) -> dict[str, SignalVote]:
    """
    Deduplicate within each cluster — keep highest confidence vote per cluster.
    Returns {cluster: best_vote}.
    """
    best: dict[str, SignalVote] = {}
    for v in votes:
        cluster = SOURCE_CLUSTER.get(v.source)
        if cluster is None:
            continue
        if cluster not in best or v.confidence > best[cluster].confidence:
            best[cluster] = v
    return best


def check_gate(votes: list[SignalVote]) -> tuple[bool, str, dict]:
    """
    Apply the 3-of-ACTIVE independent-cluster gate.

    Returns (approved, direction, meta):
      approved  — True if gate passes
      direction — "yes" | "no" | ""
      meta      — debug info (cluster breakdown, confidence, etc.)
    """
    cluster_votes = _apply_cluster_rule(votes)
    active = len(cluster_votes)

    if active < MIN_ACTIVE_CLUSTERS:
        return False, "", {"reason": f"only {active} active clusters, need {MIN_ACTIVE_CLUSTERS}",
                           "clusters": list(cluster_votes.keys())}

    yes_clusters = [c for c, v in cluster_votes.items() if v.direction == "yes"]
    no_clusters  = [c for c, v in cluster_votes.items() if v.direction == "no"]
    yes_count = len(yes_clusters)
    no_count  = len(no_clusters)

    if yes_count >= MIN_AGREEING:
        direction = "yes"
        agreeing = yes_clusters
    elif no_count >= MIN_AGREEING:
        direction = "no"
        agreeing = no_clusters
    else:
        return False, "", {
            "reason": f"no consensus (yes={yes_count}, no={no_count}, need {MIN_AGREEING})",
            "clusters": {c: v.direction for c, v in cluster_votes.items()},
        }

    avg_confidence = sum(cluster_votes[c].confidence for c in agreeing) / len(agreeing)
    return True, direction, {
        "agreeing_clusters": agreeing,
        "active_clusters": active,
        "avg_confidence": round(avg_confidence, 3),
        "yes_count": yes_count,
        "no_count": no_count,
    }


async def evaluate(condition_id: str) -> tuple[bool, str, dict]:
    """Read recent votes for a condition and apply the gate. Call before placing a bet."""
    r = get_redis()
    votes = await _read_recent_votes(r, condition_id)
    approved, direction, meta = check_gate(votes)
    return approved, direction, meta


async def run_approval_loop(interval_s: float = 5.0) -> None:
    """
    Background task: scan recent votes, emit approved bets to arb:edges:approved.
    The main betting loop reads from there instead of deciding inline.
    """
    r = get_redis()
    seen: set[str] = set()
    print("[ensemble] approval loop started")

    while True:
        try:
            await asyncio.sleep(interval_s)
            cutoff_ms = (time.time() - WINDOW_SECONDS) * 1000

            # Collect unique condition_ids from recent votes
            entries = await r.xrevrange(VOTE_STREAM, count=500)
            condition_ids: set[str] = set()
            for _msg_id, fields in entries:
                try:
                    d = json.loads(fields[b"data"] if b"data" in fields else fields["data"])
                    if d.get("ts", 0) >= cutoff_ms:
                        condition_ids.add(d["condition_id"])
                except Exception:
                    continue

            for cid in condition_ids:
                if cid in seen:
                    continue
                votes = await _read_recent_votes(r, cid)
                approved, direction, meta = check_gate(votes)
                if not approved:
                    continue

                # Find the best-matching vote for market metadata
                sample = next((v for v in votes if v.condition_id == cid), None)
                if not sample:
                    continue

                signal = {
                    "condition_id": cid,
                    "direction": direction,
                    "asset": sample.asset,
                    "kind": sample.kind,
                    "ts": int(time.time() * 1000),
                    "ensemble_meta": meta,
                }
                await r.xadd(APPROVED_STREAM, {"data": json.dumps(signal)}, maxlen=1000)
                seen.add(cid)
                print(f"[ensemble] APPROVED {cid[:8]} {direction} "
                      f"clusters={meta.get('agreeing_clusters')} "
                      f"conf={meta.get('avg_confidence')}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ensemble] error: {e}")
