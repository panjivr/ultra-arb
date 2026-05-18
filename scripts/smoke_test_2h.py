#!/usr/bin/env python3
"""
smoke_test_2h.py — G2.1 smoke test: 2 jam observasi post-ensemble-bypass.

Snapshots tiap 30 menit. Pass criteria:
  arb:polymarket:bets >= 10  → PASS (lanjut window 24h v2)
  arb:polymarket:bets 1-9   → BORDERLINE (extend smoke 2 jam lagi)
  arb:polymarket:bets = 0   → FAIL (investigate lagi)

Writes:
  logs/smoke_test_baseline.json
  logs/smoke_test_T+30m.json
  logs/smoke_test_T+60m.json
  logs/smoke_test_T+90m.json
  logs/smoke_test_T+120m.json (+ verdict)
  logs/smoke_test_2h_FINAL.md

Run: nohup python3 scripts/smoke_test_2h.py >> logs/smoke_test.log 2>&1 &
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = "/home/reyogcapital165/reyog-capital"
LOGS = os.path.join(REPO, "logs")
REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")

CHECKPOINTS_MIN = [0, 30, 60, 90, 120]
PASS_THRESHOLD  = 10   # bets >= 10 → PASS
BORDERLINE_MIN  = 1    # bets 1-9 → BORDERLINE


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def sh(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return (r.stdout or "").strip()
    except Exception as e:
        return f"__ERR__ {e!r}"


def rcli(args: str) -> str:
    return sh(f'docker exec reyog_redis redis-cli -a {REDIS_PW} --no-auth-warning {args}')


def snapshot(elapsed_min: float, baseline: dict) -> dict:
    orders_now   = rcli("LLEN arb:orders")
    bets_now     = rcli("LLEN arb:polymarket:bets")
    resolved_now = rcli("SCARD arb:poly:resolved")
    mem          = rcli("INFO memory")
    mem_human = next((l.split(":")[1].strip() for l in mem.splitlines()
                      if l.startswith("used_memory_human")), "?")

    # Parse recent orders for poly bets specifically
    raw_orders = sh(
        f'docker exec reyog_redis redis-cli -a {REDIS_PW} --no-auth-warning '
        f'LRANGE arb:orders 0 499'
    )
    poly_close = 0
    poly_pnl   = 0.0
    for line in raw_orders.splitlines():
        try:
            o = json.loads(line)
            if o.get("event") == "CLOSE" and o.get("source") == "polymarket":
                poly_close += 1
                poly_pnl += float(o.get("pnl", 0))
        except Exception:
            pass

    # Engine log errors
    errs = sh("docker logs reyog_engine --since 35m 2>&1 | grep -ci 'error\\|exception\\|traceback' || echo 0")

    bets_int = int(bets_now) if str(bets_now).isdigit() else 0
    baseline_bets = int(baseline.get("bets", 0))
    new_bets = bets_int - baseline_bets

    snap = {
        "ts_utc":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_min":    round(elapsed_min, 1),
        "arb_orders":     orders_now,
        "arb_poly_bets":  bets_now,
        "new_bets":       new_bets,
        "arb_resolved":   resolved_now,
        "poly_close_orders": poly_close,
        "poly_pnl":       round(poly_pnl, 4),
        "redis_mem":      mem_human,
        "engine_errors_35m": errs,
    }
    return snap


def verdict(new_bets: int) -> tuple[str, str]:
    if new_bets >= PASS_THRESHOLD:
        return "PASS", f"{new_bets} bets >= {PASS_THRESHOLD} threshold"
    elif new_bets >= BORDERLINE_MIN:
        return "BORDERLINE", f"{new_bets} bets (need {PASS_THRESHOLD} for PASS)"
    else:
        return "FAIL", f"0 bets in 2h — ensemble bypass not fixing the issue"


def write_final(snaps: list[dict], verd: str, reason: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    last = snaps[-1]

    verd_emoji = {"PASS": "✅", "BORDERLINE": "🟡", "FAIL": "❌"}.get(verd, "?")

    recommendations = {
        "PASS": (
            "Ensemble bypass berhasil! bets terjadi.\n"
            "Langkah selanjutnya:\n"
            "1. Reset baseline Redis (arb:orders, arb:polymarket:bets, arb:poly:resolved, arb:poly:stats:*)\n"
            "2. Start window 24h fresh (v2)\n"
            "3. Tunggu T+24h untuk verdict POLYMARKET_PROFITABLE / NEGATIVE\n"
            "4. Jika PROFITABLE: G4 live micro Rp 200rb\n"
            "BUTUH APPROVAL USER untuk reset + start window."
        ),
        "BORDERLINE": (
            f"Hanya {last['new_bets']} bets dalam 2 jam. Ensemble bypass bekerja tapi pasar jarang.\n"
            "Opsi:\n"
            "  A. Extend smoke test 2 jam lagi (keputusan sama)\n"
            "  B. Lanjut ke window 24h langsung (sample akan terkumpul lebih lama)\n"
            "  C. Investigasi: apakah ada pasar BTC Up/Down yang tersedia?\n"
            "BUTUH APPROVAL USER."
        ),
        "FAIL": (
            "0 bets dalam 2 jam — ensemble bypass tidak cukup.\n"
            "Kemungkinan penyebab lain:\n"
            "  1. _fetch_polymarket_crypto() tidak menemukan pasar yang lolos filter\n"
            "     (hours_left > 240 filter, yes_price bounds 0.01-0.99)\n"
            "  2. BTC Up/Down markets tidak di tag_id=21\n"
            "  3. _detect_asset() gagal match question ke asset\n"
            "Butuh investigasi lebih lanjut sebelum window 24h."
        ),
    }

    rows = ""
    for s in snaps:
        rows += f"| T+{s['elapsed_min']:.0f}m | {s['arb_poly_bets']} | {s['new_bets']} | {s['poly_pnl']:.3f} | {s['redis_mem']} |\n"

    md = f"""# Smoke Test 2h — Hasil G2.1
Generated: {ts}

## Verdict: {verd_emoji} {verd}
**{reason}**

## Snapshots
| Elapsed | Bets Total | New Bets | Poly PnL | Redis Mem |
|---------|-----------|----------|----------|-----------|
{rows}
## Recommendation
{recommendations.get(verd, '')}

## Fixes Applied (G2.1)
- ✅ Ensemble gate: BYPASSED (`_ensemble_enabled = False`)
- ✅ Rule5 stall detector: pakai tick timestamp (bukan arb:signals LLEN)
- ✅ Crypto kill-switch: tetap aktif (`CRYPTO_STRATEGIES_ENABLED=false`)

_Generated by smoke_test_2h.py_
"""
    with open(os.path.join(LOGS, "smoke_test_2h_FINAL.md"), "w") as f:
        f.write(md)
    log(f"FINAL report written → logs/smoke_test_2h_FINAL.md")


def main() -> None:
    os.makedirs(LOGS, exist_ok=True)
    start_epoch = time.time()
    log("=" * 56)
    log("  SMOKE TEST 2H — G2.1 (ensemble bypassed)")
    log("  Pass criteria: arb:polymarket:bets >= 10 in 2h")
    log("=" * 56)

    # Baseline
    baseline = {
        "bets":     rcli("LLEN arb:polymarket:bets"),
        "orders":   rcli("LLEN arb:orders"),
        "resolved": rcli("SCARD arb:poly:resolved"),
        "ts":       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epoch":    int(start_epoch),
    }
    with open(os.path.join(LOGS, "smoke_test_baseline.json"), "w") as f:
        json.dump(baseline, f, indent=2)
    log(f"T+0 baseline: bets={baseline['bets']}, orders={baseline['orders']}, resolved={baseline['resolved']}")

    snaps = [snapshot(0, baseline)]
    with open(os.path.join(LOGS, "smoke_test_T+0m.json"), "w") as f:
        json.dump(snaps[-1], f, indent=2)

    next_checkpoints = [30, 60, 90, 120]  # minutes

    for cp_min in next_checkpoints:
        target = start_epoch + cp_min * 60
        wait = target - time.time()
        if wait > 0:
            log(f"Waiting {wait/60:.1f}m until T+{cp_min}m checkpoint...")
            time.sleep(wait)

        elapsed = (time.time() - start_epoch) / 60
        snap = snapshot(elapsed, baseline)
        snaps.append(snap)

        fname = os.path.join(LOGS, f"smoke_test_T+{cp_min}m.json")
        with open(fname, "w") as f:
            json.dump(snap, f, indent=2)

        log(f"T+{cp_min}m: bets_total={snap['arb_poly_bets']} new={snap['new_bets']} "
            f"poly_pnl=${snap['poly_pnl']:.3f} mem={snap['redis_mem']}")

        if cp_min == 120:
            new_bets = int(snaps[-1]["new_bets"])
            verd, reason = verdict(new_bets)
            log(f"{'='*56}")
            log(f"  SMOKE VERDICT: {verd} — {reason}")
            log(f"{'='*56}")
            write_final(snaps, verd, reason)


if __name__ == "__main__":
    main()
