#!/usr/bin/env python3
"""
G1.3 — Autonomous 24h honest-window monitor.

Runs on the VPS host via cron (every 15 min). Fully self-contained:
no pip deps, shells out to `docker exec reyog_redis redis-cli` and
`docker`. Idempotent — safe to run repeatedly.

Responsibilities:
  - Write a full snapshot JSON at each 6h checkpoint (T+0/6/12/18/24).
  - Emergency detection every run (STEP E) -> observations log / flags.
  - At T+24h: freeze dataset (stop reyog_engine), write FINAL.md, sentinel.

Reads window bounds from logs/window_24h_start.txt.
Does NOT reset Redis. Does NOT edit code. Restarts a container only for
STEP E rule 5 (publishing stalled >30m) and logs every such action.
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

REPO = "/home/reyogcapital165/reyog-capital"
LOGS = os.path.join(REPO, "logs")
START_FILE = os.path.join(LOGS, "window_24h_start.txt")
STATE_FILE = os.path.join(LOGS, "window_24h_state.json")
OBS_FILE = os.path.join(LOGS, "window_24h_observations.txt")
EMERG_FILE = os.path.join(LOGS, "window_24h_EMERGENCY")
DONE_FILE = os.path.join(LOGS, "window_24h_DONE")

CONTAINERS = ["reyog_backend", "reyog_db", "reyog_edges", "reyog_engine",
              "reyog_frontend", "reyog_nginx", "reyog_redis", "reyog_risk"]
REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")
CHECKPOINTS = [0, 6, 12, 18, 24]


def sh(cmd: str, timeout: int = 30) -> str:
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception as e:
        return f"__ERR__ {e!r}"


def rcli(args: str, timeout: int = 30) -> str:
    return sh(f'docker exec reyog_redis redis-cli -a {REDIS_PW} '
              f'--no-auth-warning {args}', timeout)


def obs(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    with open(OBS_FILE, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {}


def save_state(s: dict) -> None:
    json.dump(s, open(STATE_FILE, "w"), indent=2)


def window_start() -> int:
    for ln in open(START_FILE):
        if ln.startswith("WINDOW_START_EPOCH="):
            return int(ln.strip().split("=", 1)[1])
    raise RuntimeError("WINDOW_START_EPOCH not found")


def restart_counts() -> dict:
    out = {}
    for c in CONTAINERS:
        v = sh(f'docker inspect -f "{{{{.RestartCount}}}}" {c}')
        out[c] = int(v) if v.isdigit() else -1
    return out


def parse_orders() -> dict:
    """Sum CLOSE pnl from arb:orders, grouped by source and strategy_id."""
    raw = rcli("LRANGE arb:orders 0 -1", timeout=60)
    by_source: dict = {}
    by_strategy: dict = {}
    n_close = 0
    if raw and not raw.startswith("__ERR__"):
        for line in raw.splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("event") != "CLOSE" or "pnl" not in o:
                continue
            n_close += 1
            pnl = float(o.get("pnl") or 0)
            src = o.get("source", "?")
            strat = o.get("strategy_id") or o.get("strategy") or "?"
            s = by_source.setdefault(src, {"n": 0, "pnl": 0.0,
                                           "wins": 0, "losses": 0})
            s["n"] += 1
            s["pnl"] += pnl
            s["wins" if pnl > 0 else "losses"] += 1
            t = by_strategy.setdefault(strat, {"n": 0, "pnl": 0.0,
                                                "wins": 0, "losses": 0})
            t["n"] += 1
            t["pnl"] += pnl
            t["wins" if pnl > 0 else "losses"] += 1
    for d in (by_source, by_strategy):
        for v in d.values():
            v["pnl"] = round(v["pnl"], 4)
    return {"close_events": n_close, "by_source": by_source,
            "by_strategy": by_strategy}


def poly_stats() -> dict:
    keys = rcli('KEYS "arb:poly:stats:*"')
    out = {}
    if keys and not keys.startswith("__ERR__"):
        for k in keys.split():
            hv = rcli(f"HGETALL {k}").split()
            out[k] = {hv[i]: hv[i + 1] for i in range(0, len(hv) - 1, 2)}
    return out


def err_count(since: str) -> dict:
    out = {}
    for c in CONTAINERS:
        logs = sh(f'docker logs {c} --since {since} 2>&1', timeout=40)
        if logs.startswith("__ERR__"):
            out[c] = -1
            continue
        n = 0
        for ln in logs.splitlines():
            low = ln.lower()
            if "errors=0" in low:
                continue
            if "traceback" in low or "exception" in low or \
               re.search(r"\berror\b", low):
                n += 1
        out[c] = n
    return out


def snapshot(elapsed_h: float) -> dict:
    halted = rcli("GET arb:risk:halted")
    dl_keys = rcli('KEYS "arb:risk:polymarket_daily_loss:*"')
    daily_loss = {}
    if dl_keys and not dl_keys.startswith("__ERR__"):
        for k in dl_keys.split():
            daily_loss[k] = rcli(f"GET {k}")
    orders = parse_orders()
    cryp = orders["by_source"].get("REAL", {})
    polp = orders["by_source"].get("polymarket", {})
    return {
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_hours": round(elapsed_h, 3),
        "counts": {
            "arb:orders": rcli("LLEN arb:orders"),
            "arb:signals": rcli("LLEN arb:signals"),
            "arb:polymarket:bets": rcli("LLEN arb:polymarket:bets"),
            "arb:poly:resolved": rcli("SCARD arb:poly:resolved"),
        },
        "poly_stats": poly_stats(),
        "risk_halted": halted if halted else "(empty)",
        "polymarket_daily_loss": daily_loss,
        "crypto_pnl": cryp,
        "polymarket_pnl": polp,
        "orders_breakdown": orders,
        "container_restarts": restart_counts(),
        "errors_last_6h": err_count("6h"),
        "redis_mem": sh('docker exec reyog_redis redis-cli -a '
                        f'{REDIS_PW} --no-auth-warning INFO memory '
                        '| grep used_memory_human'),
    }


def detect_emergencies(state: dict) -> None:
    base = state.get("restart_baseline", {})
    now_rc = restart_counts()
    prev = state.get("last_restart_check", base)
    for c in CONTAINERS:
        delta = now_rc.get(c, 0) - prev.get(c, 0)
        if delta >= 3:
            obs(f"EMERGENCY rule1: {c} restarted {delta}x since last "
                f"check (~15m). STOP-class.")
            open(EMERG_FILE, "a").write(f"rule1 {c} +{delta}\n")
    state["last_restart_check"] = now_rc

    halted = rcli("GET arb:risk:halted")
    if halted and halted not in ("(empty)", ""):
        obs(f"rule2: arb:risk:halted={halted} (drawdown breaker tripped) "
            "— SIGNAL not emergency, logged.")

    mem = sh(f'docker exec reyog_redis redis-cli -a {REDIS_PW} '
             '--no-auth-warning INFO memory | grep used_memory:')
    try:
        used = int(mem.split(":")[1])
        if used > 480 * 1024 * 1024:  # maxmemory is 512mb
            obs(f"EMERGENCY rule3: redis used_memory={used} near 512mb cap.")
            open(EMERG_FILE, "a").write(f"rule3 redis_mem {used}\n")
    except Exception:
        pass
    disk = sh("df -P / | tail -1 | awk '{print $5}'").rstrip("%")
    if disk.isdigit() and int(disk) >= 92:
        obs(f"EMERGENCY rule3: disk {disk}% full.")
        open(EMERG_FILE, "a").write(f"rule3 disk {disk}%\n")

    errs = err_count("15m")
    for c, n in errs.items():
        logs15 = sh(f'docker logs {c} --since 15m 2>&1 | wc -l')
        tot = int(logs15) if logs15.isdigit() else 0
        if tot > 50 and n / max(tot, 1) > 0.05:
            obs(f"EMERGENCY rule4: {c} error rate {n}/{tot} >5%.")
            open(EMERG_FILE, "a").write(f"rule4 {c} {n}/{tot}\n")

    # rule5: publishing liveness — compare arb:orders+signals counts vs prev
    cur = {"o": rcli("LLEN arb:orders"), "s": rcli("LLEN arb:signals"),
           "b": rcli("LLEN arb:polymarket:bets")}
    prevc = state.get("last_counts")
    prevt = state.get("last_counts_ts", 0)
    nowt = time.time()
    if prevc and (nowt - prevt) >= 1800:  # 30 min elapsed
        sig_a = int(cur["s"]) if cur["s"].isdigit() else 0
        sig_b = int(prevc.get("s", "0") or 0)
        if sig_a <= sig_b:  # signals are emitted constantly; stall = engine dead
            obs("rule5: arb:signals not advanced in >=30m — engine publishing "
                "stalled. Restarting reyog_engine.")
            r = sh("docker restart reyog_engine")
            obs(f"rule5 action: docker restart reyog_engine -> {r}")
        state["last_counts"] = cur
        state["last_counts_ts"] = nowt
    elif not prevc:
        state["last_counts"] = cur
        state["last_counts_ts"] = nowt


def best_worst(by_strategy: dict):
    if not by_strategy:
        return ("(none)", 0.0), ("(none)", 0.0)
    items = sorted(by_strategy.items(), key=lambda kv: kv[1]["pnl"])
    return ((items[-1][0], items[-1][1]["pnl"]),
            (items[0][0], items[0][1]["pnl"]))


def pct(w, l):
    t = w + l
    return round(100 * w / t, 1) if t else 0.0


def write_final(snap: dict, state: dict) -> None:
    o = snap["orders_breakdown"]
    cry = o["by_source"].get("REAL", {"n": 0, "pnl": 0, "wins": 0,
                                      "losses": 0})
    pol = o["by_source"].get("polymarket", {"n": 0, "pnl": 0, "wins": 0,
                                            "losses": 0})
    crypto_strats = {k: v for k, v in o["by_strategy"].items()
                     if k not in ("polymarket",)}
    poly_strats = {k: v for k, v in o["by_strategy"].items()
                   if k == "polymarket"}
    cb, cw = best_worst(crypto_strats)
    pb, pw = best_worst(poly_strats)
    resolved = snap["counts"].get("arb:poly:resolved", "0")
    halted_n = state.get("halted_trip_count", 0)
    restarts = sum(max(0, snap["container_restarts"].get(c, 0) -
                       state.get("restart_baseline", {}).get(c, 0))
                   for c in CONTAINERS)
    errtot = sum(v for v in snap["errors_last_6h"].values() if v > 0)
    wt = sh("grep WINDOW_START_UTC " + START_FILE).split("=")[-1]
    we = sh("grep WINDOW_END_UTC " + START_FILE).split("=")[-1]
    md = f"""## Window 24 Jam — Hasil Jujur
Period: {wt} -> {we}

### Crypto Path (emit_trades, source=REAL)
- Total trades (CLOSE): {cry.get('n', 0)}
- Wins: {cry.get('wins', 0)}, Losses: {cry.get('losses', 0)}
- Win rate: {pct(cry.get('wins', 0), cry.get('losses', 0))}%
- Total PnL: ${round(cry.get('pnl', 0), 2)}
- Avg per trade: ${round(cry.get('pnl', 0) / max(cry.get('n', 1), 1), 4)}
- Strategi terbaik: {cb[0]} PnL ${cb[1]}
- Strategi terburuk: {cw[0]} PnL ${cw[1]}

### Polymarket Path (emit_polymarket_bets, source=polymarket)
- Total bets resolved (CLOSE): {pol.get('n', 0)}
- Wins: {pol.get('wins', 0)}, Losses: {pol.get('losses', 0)}
- Win rate: {pct(pol.get('wins', 0), pol.get('losses', 0))}%
- Total PnL: ${round(pol.get('pnl', 0), 2)}
- Avg per bet: ${round(pol.get('pnl', 0) / max(pol.get('n', 1), 1), 4)}
- Strategi terbaik: {pb[0]} PnL ${pb[1]}
- Strategi terburuk: {pw[0]} PnL ${pw[1]}
- arb:poly:stats (per asset): {json.dumps(snap['poly_stats'])}

### Risk Events
- arb:risk:halted triggered: {halted_n} kali (lihat observations log)
- Daily loss breakers: {json.dumps(snap['polymarket_daily_loss'])}
- Container restarts (delta vs baseline): {restarts}
- Error count (last 6h sample): {errtot}

### Verifikasi Integritas
- Double-count check: arb:poly:resolved size = {resolved}
  (resolved bets harus = unique; tidak ada N-count)
- WRONGTYPE errors: cek observations/cron log (target 0)
- emit_trades single writer: arb:orders source breakdown =
  {json.dumps({k: v['n'] for k, v in o['by_source'].items()})}
  (hanya REAL + polymarket; tidak ada PAPER_TRADE/LiveExecutor)

### Verdict Awal G1.3
- Crypto edge: {"POSITIF" if cry.get('pnl', 0) > 0 else ("ZERO" if cry.get('n', 0) == 0 else "NEGATIF")} \
(EV ${round(cry.get('pnl', 0) / max(cry.get('n', 1), 1), 4)}/trade, n={cry.get('n', 0)})
- Polymarket edge: {"POSITIF" if pol.get('pnl', 0) > 0 else ("ZERO" if pol.get('n', 0) == 0 else "NEGATIF")} \
(EV ${round(pol.get('pnl', 0) / max(pol.get('n', 1), 1), 4)}/bet, n={pol.get('n', 0)})
- Recommendation G2: crypto={"KEEP" if cry.get('pnl', 0) > 0 else "DISABLE"}, \
polymarket={"KEEP" if pol.get('pnl', 0) > 0 else "DISABLE"} \
(catatan: Polymarket resolusi = simulated settlement F6, perlu validasi nyata sebelum live)

_Generated autonomously by window_24h_monitor.py at T+24h._
"""
    open(os.path.join(LOGS, "window_24h_FINAL.md"), "w").write(md)
    obs("STEP F: window_24h_FINAL.md written.")


def main() -> None:
    os.makedirs(LOGS, exist_ok=True)
    if os.path.exists(DONE_FILE):
        return
    start = window_start()
    elapsed_h = (time.time() - start) / 3600.0
    state = load_state()
    if "restart_baseline" not in state:
        state["restart_baseline"] = restart_counts()
        save_state(state)

    detect_emergencies(state)

    # track halted trip count (rising-edge)
    halted = rcli("GET arb:risk:halted")
    is_h = bool(halted and halted not in ("(empty)", ""))
    if is_h and not state.get("was_halted"):
        state["halted_trip_count"] = state.get("halted_trip_count", 0) + 1
    state["was_halted"] = is_h

    # write any due checkpoint snapshots (idempotent)
    for cp in CHECKPOINTS:
        if elapsed_h + 0.01 >= cp:
            fn = os.path.join(LOGS, f"window_24h_T+{cp}h.json")
            if not os.path.exists(fn):
                snap = snapshot(elapsed_h)
                json.dump(snap, open(fn, "w"), indent=2)
                obs(f"checkpoint T+{cp}h written ({fn})")
                if cp == 24:
                    obs("STEP F: T+24h reached — freezing dataset "
                        "(docker stop reyog_engine), generating FINAL.")
                    obs("freeze: " + sh("docker stop reyog_engine"))
                    write_final(snap, state)
                    open(DONE_FILE, "w").write(
                        datetime.now(timezone.utc).isoformat())
    save_state(state)


if __name__ == "__main__":
    main()
