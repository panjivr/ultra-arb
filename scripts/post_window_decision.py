#!/usr/bin/env python3
"""
post_window_decision.py — Auto-decision after window_24h_DONE sentinel.

Reads logs/window_24h_FINAL.md (written by window_24h_monitor.py at T+24h)
and the FINAL JSON snapshot, then applies the Polymarket decision tree:

  INSUFFICIENT_DATA   → < 10 bets resolved
  POLYMARKET_NEGATIVE → pnl <= 0
  POLYMARKET_PROFITABLE → pnl > 0 AND win_rate >= 0.55 AND bets >= 30
  BORDERLINE          → everything else (profitable but small sample)

Writes: logs/post_window_decision.md
Prints verdict to stdout (captured by cron).

Run:
  python scripts/post_window_decision.py              # full read
  python scripts/post_window_decision.py --force      # run even if DONE not yet
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO = "/home/reyogcapital165/reyog-capital"
LOGS = os.path.join(REPO, "logs")
DONE_FILE = os.path.join(LOGS, "window_24h_DONE")
FINAL_MD = os.path.join(LOGS, "window_24h_FINAL.md")
FINAL_JSON = os.path.join(LOGS, "window_24h_T+24h.json")
REPORT_OUT = os.path.join(LOGS, "post_window_decision.md")

# Polymarket decision thresholds
MIN_BETS_PROFITABLE = 30        # need >= 30 to call PROFITABLE
MIN_BETS_DATA = 10              # need >= 10 to have any data
MIN_WIN_RATE_PROFITABLE = 0.55  # win rate >= 55% required

REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")


def sh(cmd: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception as e:
        return f"__ERR__ {e!r}"


def rcli(args: str) -> str:
    return sh(f'docker exec reyog_redis redis-cli -a {REDIS_PW} '
              f'--no-auth-warning {args}')


def load_final_snapshot() -> dict | None:
    """Load window_24h_T+24h.json (primary) or fall back to T+18h."""
    for fname in ["window_24h_T+24h.json", "window_24h_T+18h.json",
                  "window_24h_T+12h.json"]:
        p = os.path.join(LOGS, fname)
        if os.path.exists(p):
            try:
                data = json.load(open(p))
                print(f"[decision] loaded snapshot: {fname}")
                return data
            except Exception as e:
                print(f"[decision] failed to load {fname}: {e}")
    return None


def extract_poly_metrics(snap: dict) -> dict:
    """Extract Polymarket PnL metrics from the snapshot."""
    orders = snap.get("orders_breakdown", {})
    poly = orders.get("by_source", {}).get("polymarket",
                                           {"n": 0, "pnl": 0.0,
                                            "wins": 0, "losses": 0})
    n = poly.get("n", 0)
    pnl = float(poly.get("pnl", 0))
    wins = int(poly.get("wins", 0))
    losses = int(poly.get("losses", 0))
    total = wins + losses
    win_rate = wins / total if total > 0 else 0.0
    resolved_set = snap.get("counts", {}).get("arb:poly:resolved", "0")
    return {
        "n": n,
        "pnl": round(pnl, 4),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 4),
        "resolved_set_size": int(resolved_set) if str(resolved_set).isdigit() else 0,
        "poly_stats": snap.get("poly_stats", {}),
    }


def extract_crypto_metrics(snap: dict) -> dict:
    orders = snap.get("orders_breakdown", {})
    real = orders.get("by_source", {}).get("REAL",
                                           {"n": 0, "pnl": 0.0,
                                            "wins": 0, "losses": 0})
    n = real.get("n", 0)
    pnl = float(real.get("pnl", 0))
    wins = int(real.get("wins", 0))
    total = wins + int(real.get("losses", 0))
    return {
        "n": n,
        "pnl": round(pnl, 4),
        "win_rate": round(wins / total, 4) if total > 0 else 0.0,
    }


def decide(pm: dict) -> tuple[str, str, str]:
    """
    Returns (verdict, recommendation, next_action).
    Decision tree per spec:
    """
    n = pm["n"]
    pnl = pm["pnl"]
    wr = pm["win_rate"]

    if n < MIN_BETS_DATA:
        return (
            "INSUFFICIENT_DATA",
            f"Hanya {n} bets resolved dalam 24h (minimum {MIN_BETS_DATA} untuk analisis). "
            "Kemungkinan sebab: F4 _classify_market misclassify markets, "
            "F5 samples_per_hour miscalibrated, atau Polymarket API tidak menemukan "
            "market yang sesuai threshold. Rekomendasi: apply F4/F5 modeling fix "
            "atau extend monitoring window 24h tambahan.",
            "DO_NOT_LIVE",
        )
    elif pnl <= 0:
        return (
            "POLYMARKET_NEGATIVE",
            f"Polymarket PnL = ${pnl:.4f} (negatif/zero) dari {n} bets, "
            f"win rate {wr*100:.1f}%. Sebelum live: apply F4 (_classify_market fix), "
            "F5 (_updown_probability calibration). Kemungkinan edge hanya simulasi "
            "(F6: settlement pakai feed sendiri, bukan real Polymarket settlement).",
            "DO_NOT_LIVE",
        )
    elif pnl > 0 and wr >= MIN_WIN_RATE_PROFITABLE and n >= MIN_BETS_PROFITABLE:
        return (
            "POLYMARKET_PROFITABLE",
            f"Polymarket PnL = ${pnl:.4f}, win rate {wr*100:.1f}%, {n} bets. "
            "Semua threshold terpenuhi. Eligible untuk G4 live micro Rp 200rb. "
            "CATATAN: settlement masih simulated (F6) — profit ini bisa berbeda "
            "di live real. Treat G4 sebagai experiment validation, bukan profit guarantee.",
            "GENERATE_G4_ARTIFACTS",
        )
    else:
        extra = []
        if wr < MIN_WIN_RATE_PROFITABLE:
            extra.append(f"win rate {wr*100:.1f}% < {MIN_WIN_RATE_PROFITABLE*100:.0f}% required")
        if n < MIN_BETS_PROFITABLE:
            extra.append(f"only {n} bets < {MIN_BETS_PROFITABLE} required")
        return (
            "BORDERLINE",
            f"Polymarket PnL = ${pnl:.4f} (positif), tapi: {'; '.join(extra)}. "
            "Profit ada tapi sample/confidence belum cukup untuk live confident. "
            "Pilihan: extend window 24h tambahan, atau live micro dengan extra caution "
            "(cut stop-loss ke 25% = Rp 50rb).",
            "MANUAL_REVIEW",
        )


def write_report(pm: dict, crypto: dict, verdict: str,
                 recommendation: str, next_action: str,
                 snap: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap_ts = snap.get("ts_utc", "unknown")
    elapsed = snap.get("elapsed_hours", "?")
    halted_n = sum(1 for ln in open(os.path.join(LOGS, "window_24h_observations.txt"))
                   if "halted" in ln.lower()) if os.path.exists(
        os.path.join(LOGS, "window_24h_observations.txt")) else "?"

    verdict_emoji = {
        "POLYMARKET_PROFITABLE": "✅",
        "BORDERLINE": "🟡",
        "POLYMARKET_NEGATIVE": "❌",
        "INSUFFICIENT_DATA": "⚪",
    }.get(verdict, "❓")

    crypto_note = (
        f"Disabled at G2 (Pilihan B). Last known: {crypto['n']} trades, "
        f"PnL ${crypto['pnl']:.4f}, win rate {crypto['win_rate']*100:.1f}%."
    )

    g4_block = ""
    if next_action == "GENERATE_G4_ARTIFACTS":
        g4_block = """
### G4 Micro Activation (MANUAL — user harus run)
G4_SETUP_CHECKLIST.md dan scripts/g4_micro_activate.py sudah tersedia.
Adjust untuk Polymarket-only sebelum activate:
  - MAX_POSITION_USD: $1-2 per market (bukan 1% crypto sizing)
  - MAX_OPEN_POSITIONS: 5 (Polymarket bets kecil-kecil)
  - GLOBAL_STOP_LOSS_PERCENT: 50 (Rp 200rb modal → stop di Rp 100rb)

Langkah:
1. Baca G4_SETUP_CHECKLIST.md
2. Isi wallet + API keys + POLYMARKET_PRIVATE_KEY
3. python scripts/g4_micro_activate.py --validate-only
4. python scripts/g4_micro_activate.py → ketik LANJUT G4
"""
    elif next_action in ("DO_NOT_LIVE", "MANUAL_REVIEW"):
        g4_block = """
### G4 Status
Modal Rp 200rb: SAVED — tidak di-deploy.
Jangan activate live sampai verdict berubah ke POLYMARKET_PROFITABLE.
"""

    md = f"""## Post-Window Decision Report
Generated: {ts}
Snapshot: {snap_ts} (elapsed {elapsed}h)

---

## Verdict: {verdict_emoji} {verdict}
Next action: **{next_action}**

### Polymarket Path
| Metric | Value |
|--------|-------|
| Bets resolved (CLOSE) | {pm['n']} |
| PnL | ${pm['pnl']:.4f} |
| Wins | {pm['wins']} |
| Losses | {pm['losses']} |
| Win rate | {pm['win_rate']*100:.1f}% |
| arb:poly:resolved set | {pm['resolved_set_size']} |
| Per-asset stats | {json.dumps(pm['poly_stats'], indent=2) if pm['poly_stats'] else '(none)'} |

### Crypto Path (disabled G2)
{crypto_note}

### Risk Events
- arb:risk:halted observations: {halted_n}

### Recommendation
{recommendation}
{g4_block}
---

### Thresholds Applied
- PROFITABLE requires: pnl > 0 AND win_rate >= {MIN_WIN_RATE_PROFITABLE*100:.0f}% AND bets >= {MIN_BETS_PROFITABLE}
- DATA requires: bets >= {MIN_BETS_DATA}
- Crypto strategies: DISABLED (CRYPTO_STRATEGIES_ENABLED=false since G2)

### Disclaimer
arb:poly:resolved = idempotency set (unique resolved bets) — should equal
or be close to poly CLOSE events count. Large discrepancy = double-count bug.
F6 caveat: Polymarket settlement uses our own price feed, not real Polymarket
settlement. Paper profit may not reflect real edge. G4 = validation experiment.

_Generated by post_window_decision.py_
"""
    return md


def main() -> None:
    force = "--force" in sys.argv

    if not force and not os.path.exists(DONE_FILE):
        print(f"[decision] window_24h_DONE not found yet — window still running.")
        print(f"[decision] Re-run when done, or use --force to read current state.")
        sys.exit(0)

    print("[decision] Loading final snapshot...")
    snap = load_final_snapshot()
    if snap is None:
        print("[decision] ERROR: no snapshot found in logs/. Cannot decide.")
        sys.exit(1)

    pm = extract_poly_metrics(snap)
    crypto = extract_crypto_metrics(snap)
    verdict, recommendation, next_action = decide(pm)

    print(f"\n{'='*56}")
    print(f"  POST-WINDOW VERDICT: {verdict}")
    print(f"  Next action: {next_action}")
    print(f"{'='*56}")
    print(f"  Polymarket: {pm['n']} bets, PnL ${pm['pnl']:.4f}, "
          f"win rate {pm['win_rate']*100:.1f}%")
    print(f"  Recommendation: {recommendation[:120]}...")
    print(f"{'='*56}\n")

    report = write_report(pm, crypto, verdict, recommendation, next_action, snap)
    with open(REPORT_OUT, "w") as f:
        f.write(report)
    print(f"[decision] Report saved: {REPORT_OUT}")


if __name__ == "__main__":
    main()
