#!/usr/bin/env python3
"""
Hourly snapshot of the honest Polymarket paper run. Runs on the VPS HOST.

Appends one structured line per run to logs/poly_observation.log so we can read
the progression tomorrow: how many bets, win-rate, paper PnL, halt status.

Win/loss is REAL Polymarket oracle settlement (settlement=polymarket_oracle),
stakes are paper ($10k demo capital, is_real_wallet=false). No real money.

Cron (hourly, on host):
  0 * * * * /usr/bin/python3 /home/reyogcapital165/reyog-capital/scripts/poly_hourly_snapshot.py
"""
import json
import os
import subprocess
from datetime import datetime, timezone

REDIS_PW = "reyog_redis_secret"
LOG_PATH = "/home/reyogcapital165/reyog-capital/logs/poly_observation.log"


def rcli(args: str) -> str:
    r = subprocess.run(
        f"docker exec reyog_redis redis-cli -a {REDIS_PW} --no-auth-warning {args}",
        shell=True, capture_output=True, text=True, timeout=20)
    return (r.stdout or "").strip()


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw = rcli("LRANGE arb:polymarket:bets 0 999")
    total = open_n = won = lost = 0
    paper_pnl = 0.0
    oracle = 0
    intervals: dict = {}
    for line in raw.splitlines():
        try:
            b = json.loads(line)
        except Exception:
            continue
        st = b.get("status")
        if st == "open":
            open_n += 1
        elif st in ("won", "lost"):
            total += 1
            if b.get("settlement") == "polymarket_oracle":
                oracle += 1
            stake = float(b.get("stake_usd", 0) or 0)
            if st == "won":
                won += 1
                paper_pnl += float(b.get("payout_usd", 0) or 0) - stake
            else:
                lost += 1
                paper_pnl -= stake
            lbl = b.get("interval", "?")
            intervals[lbl] = intervals.get(lbl, 0) + 1

    halt = rcli("GET arb:risk:halted")
    win_rate = (won / (won + lost) * 100) if (won + lost) else 0.0

    line = (
        f"[{ts}] open={open_n} resolved={won + lost} (W={won} L={lost} "
        f"win_rate={win_rate:.1f}%) oracle_settled={oracle}/{won + lost} "
        f"paper_pnl=${paper_pnl:+.2f} halted={'YES' if halt else 'no'} "
        f"intervals={intervals}"
    )
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"(log write failed: {e})")


if __name__ == "__main__":
    main()
