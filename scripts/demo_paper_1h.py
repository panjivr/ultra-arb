#!/usr/bin/env python3
"""
demo_paper_1h.py — 1-hour paper observation → auto-verdict → G4 prep

Runs as a background process: python scripts/demo_paper_1h.py &
Does NOT reset Redis. Does NOT change strategy config.
Parallel-safe with window_24h_monitor.py (separate state files, read-only Redis).

Decision criteria for LANJUT LIVE (ALL 6 must pass):
  ✅ Container restart delta = 0 during the 1-hour window
  ✅ Error rate < 5 errors/min in any container (last 10m sample)
  ✅ arb:risk:halted NOT triggered at any point during run
  ✅ Crypto PnL delta > -$10 (source=REAL only)
  ✅ >= 30 new CLOSE events (sample size proves bot is active)
  ✅ Redis memory < 200MB (no memory leak)

Output files (all in logs/):
  demo_1h_baseline.json   — T+0  snapshot
  demo_1h_T20.json        — T+20 snapshot
  demo_1h_T40.json        — T+40 snapshot
  demo_1h_FINAL.json      — T+60 snapshot + verdict data
  demo_1h_run.log         — continuous event log
  demo_1h_FINAL_REPORT.md — human-readable verdict report

If PASS, also generates:
  G4_SETUP_CHECKLIST.md            — manual steps for user to fill
  scripts/g4_micro_activate.py     — activation script (user runs manually)
  logs/demo_1h_VERDICT_FAIL.md     — FAIL only: same report at fail path
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

REPO = "/home/reyogcapital165/reyog-capital"
LOGS = os.path.join(REPO, "logs")
RUN_LOG = os.path.join(LOGS, "demo_1h_run.log")
REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")

CONTAINERS = [
    "reyog_backend", "reyog_db", "reyog_edges", "reyog_engine",
    "reyog_frontend", "reyog_nginx", "reyog_redis", "reyog_risk",
]

# Decision thresholds
MAX_CRYPTO_DRAWDOWN = -10.0   # USD: crypto-only PnL delta must be > this
MIN_NEW_TRADES = 30           # new CLOSE events during 1h must be >= this
MAX_REDIS_MB = 200.0          # Redis memory must stay under (MB)
MAX_ERR_PER_MIN = 5.0         # errors/min per container (last 10m sample)

POLL_INTERVAL_SEC = 60        # check every 60 seconds
RUN_DURATION_SEC = 3600       # 60 minutes


# ─── helpers ────────────────────────────────────────────────────────────────

def sh(cmd: str, timeout: int = 30) -> str:
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception as e:
        return f"__ERR__ {e!r}"


def rcli(args: str, timeout: int = 30) -> str:
    return sh(
        f'docker exec reyog_redis redis-cli -a {REDIS_PW} '
        f'--no-auth-warning {args}',
        timeout,
    )


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(RUN_LOG, "a") as f:
        f.write(line + "\n")


# ─── data collectors ─────────────────────────────────────────────────────────

def restart_counts() -> dict:
    out = {}
    for c in CONTAINERS:
        v = sh(f'docker inspect -f "{{{{.RestartCount}}}}" {c}')
        out[c] = int(v) if v.isdigit() else -1
    return out


def parse_orders() -> dict:
    """
    Parse entire arb:orders list.
    Returns totals grouped by source AND overall, plus per-source breakdown.
    """
    raw = rcli("LRANGE arb:orders 0 -1", timeout=60)
    by_src: dict = {}
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
            s = by_src.setdefault(src, {"n": 0, "pnl": 0.0, "wins": 0, "losses": 0})
            s["n"] += 1
            s["pnl"] += pnl
            if pnl > 0:
                s["wins"] += 1
            else:
                s["losses"] += 1
    for s in by_src.values():
        s["pnl"] = round(s["pnl"], 4)
    return {"total_close": n_close, "by_source": by_src}


def redis_mem_mb() -> float:
    raw = sh(
        f'docker exec reyog_redis redis-cli -a {REDIS_PW} '
        '--no-auth-warning INFO memory | grep "^used_memory:"'
    )
    try:
        return round(int(raw.split(":")[1]) / (1024 * 1024), 2)
    except Exception:
        return -1.0


def err_rate_per_min(since: str = "10m") -> dict:
    """Errors in last N minutes → errors/minute per container."""
    m = re.match(r"(\d+)m", since)
    mins = int(m.group(1)) if m else 10
    out = {}
    for c in CONTAINERS:
        logs = sh(f'docker logs {c} --since {since} 2>&1', timeout=40)
        if logs.startswith("__ERR__"):
            out[c] = -1.0
            continue
        n = 0
        for ln in logs.splitlines():
            low = ln.lower()
            if "errors=0" in low:
                continue
            if ("traceback" in low or "exception" in low
                    or re.search(r"\berror\b", low)):
                n += 1
        out[c] = round(n / max(mins, 1), 2)
    return out


def take_snapshot(label: str) -> dict:
    """Capture a full state snapshot. No baseline comparison here."""
    halt = rcli("GET arb:risk:halted")
    mem = redis_mem_mb()
    rc = restart_counts()
    orders = parse_orders()
    real = orders["by_source"].get("REAL", {"n": 0, "pnl": 0.0, "wins": 0, "losses": 0})
    poly = orders["by_source"].get("polymarket", {"n": 0, "pnl": 0.0, "wins": 0, "losses": 0})
    return {
        "label": label,
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # raw totals (cumulative since Redis birth, not since this run)
        "total_close_events": orders["total_close"],
        "total_pnl_real": real["pnl"],
        "total_pnl_poly": poly["pnl"],
        "crypto_stats": real,
        "poly_stats_orders": poly,
        "orders_by_source": orders["by_source"],
        "arb_orders_len": rcli("LLEN arb:orders"),
        "arb_signals_len": rcli("LLEN arb:signals"),
        "arb_poly_bets": rcli("LLEN arb:polymarket:bets"),
        "arb_poly_resolved": rcli("SCARD arb:poly:resolved"),
        "risk_halted": halt if halt else "(empty)",
        "redis_mem_mb": mem,
        "container_restarts": rc,
        "err_rate_per_min_last10m": err_rate_per_min("10m"),
    }


def compute_delta(baseline: dict, current: dict, halted_during_run: bool) -> dict:
    """Compute per-field deltas. Returns delta dict to embed in snapshot."""
    new_trades = current["total_close_events"] - baseline["total_close_events"]
    crypto_pnl_delta = round(current["total_pnl_real"] - baseline["total_pnl_real"], 4)
    poly_pnl_delta = round(current["total_pnl_poly"] - baseline["total_pnl_poly"], 4)
    restart_delta = {
        c: current["container_restarts"].get(c, 0) - baseline["container_restarts"].get(c, 0)
        for c in CONTAINERS
    }
    return {
        "new_close_events": new_trades,
        "crypto_pnl_delta": crypto_pnl_delta,
        "poly_pnl_delta": poly_pnl_delta,
        "restart_delta": restart_delta,
        "risk_halted_during_run": halted_during_run,
    }


# ─── verdict logic ───────────────────────────────────────────────────────────

def evaluate_verdict(delta: dict, final: dict) -> tuple[bool, dict]:
    """
    Returns (passed: bool, criteria_detail: dict).
    ALL criteria must be True for PASS.
    """
    criteria = {}

    # 1. Container restarts = 0
    max_restart = max(delta["restart_delta"].values()) if delta["restart_delta"] else 0
    criteria["container_stability"] = {
        "pass": max_restart == 0,
        "value": delta["restart_delta"],
        "threshold": "delta = 0 per container",
        "note": f"max restart delta = {max_restart}",
    }

    # 2. Error rate < 5/min
    err_rates = final["err_rate_per_min_last10m"]
    valid_rates = [v for v in err_rates.values() if v >= 0]
    max_err = max(valid_rates) if valid_rates else 0.0
    criteria["error_rate"] = {
        "pass": max_err < MAX_ERR_PER_MIN,
        "value": err_rates,
        "threshold": f"< {MAX_ERR_PER_MIN:.0f} errors/min per container",
        "note": f"max = {max_err:.1f} errors/min",
    }

    # 3. Risk system NOT triggered
    criteria["risk_system"] = {
        "pass": not delta["risk_halted_during_run"],
        "value": final["risk_halted"],
        "threshold": "arb:risk:halted must stay empty",
        "note": f"halted_triggered = {delta['risk_halted_during_run']}, "
                f"current = {final['risk_halted']}",
    }

    # 4. Crypto PnL delta > -$10 (REAL source only)
    cpnl = delta["crypto_pnl_delta"]
    criteria["pnl_drawdown"] = {
        "pass": cpnl > MAX_CRYPTO_DRAWDOWN,
        "value": cpnl,
        "threshold": f"> ${MAX_CRYPTO_DRAWDOWN:.0f} crypto PnL during 1h",
        "note": f"crypto pnl delta = ${cpnl:.4f}",
    }

    # 5. At least 30 new trades
    new_t = delta["new_close_events"]
    criteria["sample_size"] = {
        "pass": new_t >= MIN_NEW_TRADES,
        "value": new_t,
        "threshold": f">= {MIN_NEW_TRADES} new CLOSE events",
        "note": f"new trades = {new_t}",
    }

    # 6. Redis memory < 200MB
    mem = final["redis_mem_mb"]
    criteria["memory"] = {
        "pass": 0 < mem < MAX_REDIS_MB,
        "value": mem,
        "threshold": f"< {MAX_REDIS_MB:.0f}MB",
        "note": f"redis = {mem:.1f}MB",
    }

    passed = all(c["pass"] for c in criteria.values())
    return passed, criteria


# ─── report writer ───────────────────────────────────────────────────────────

def write_report(baseline: dict, final: dict, delta: dict,
                 passed: bool, criteria: dict) -> str:
    def chk(k): return "✅" if criteria[k]["pass"] else "❌"

    new_poly_resolved = (
        int(final.get("arb_poly_resolved") or 0)
        - int(baseline.get("arb_poly_resolved") or 0)
    )

    verdict_line = (
        "## ✅ PASS — Sistem stabil. Siap untuk G4 micro experiment."
        if passed else
        "## ❌ FAIL — Sistem belum siap untuk live trading."
    )

    if passed:
        rec = (
            "Sistem stabil selama 1 jam observasi.\n"
            "Langkah selanjutnya:\n"
            "1. Baca G4_SETUP_CHECKLIST.md\n"
            "2. Isi wallet + API keys (MANUAL — jangan skip)\n"
            "3. Jalankan: `python scripts/g4_micro_activate.py --validate-only`\n"
            "4. Jika OK: `python scripts/g4_micro_activate.py`\n"
            "5. Pantau dashboard 30 menit pertama di https://103-31-38-106.sslip.io\n"
        )
    else:
        fails = [k for k, v in criteria.items() if not v["pass"]]
        lines = ["Masalah yang perlu diperbaiki sebelum live:\n"]
        for f in fails:
            lines.append(
                f"- **{f}**: {criteria[f]['note']} "
                f"(threshold: {criteria[f]['threshold']})\n"
            )
        lines.append("\nJangan jalankan live sampai semua criteria PASS.\n")
        rec = "".join(lines)

    md = f"""## Demo Paper 1 Jam — Hasil

### Window
- Start: {baseline['ts_utc']}
- End: {final['ts_utc']}
- Duration: ~60 menit

### Observasi
- New trades (CLOSE events): {delta['new_close_events']}
- New poly bets resolved: {new_poly_resolved}
- Crypto PnL delta (source=REAL): ${delta['crypto_pnl_delta']:.4f}
- Poly PnL delta: ${delta['poly_pnl_delta']:.4f}
- Container restarts delta: {sum(max(0, v) for v in delta['restart_delta'].values())}
- Error rate (last 10m): {criteria['error_rate']['note']}
- Risk halted during run: {delta['risk_halted_during_run']}
- Redis memory (final): {final['redis_mem_mb']:.1f}MB

### Verdict
{verdict_line}

### Detail per Criteria
| Criteria | Result | Value | Threshold |
|----------|--------|-------|-----------|
| Container stability | {chk('container_stability')} | {criteria['container_stability']['note']} | {criteria['container_stability']['threshold']} |
| Error rate | {chk('error_rate')} | {criteria['error_rate']['note']} | {criteria['error_rate']['threshold']} |
| Risk system | {chk('risk_system')} | {criteria['risk_system']['note']} | {criteria['risk_system']['threshold']} |
| PnL drawdown | {chk('pnl_drawdown')} | {criteria['pnl_drawdown']['note']} | {criteria['pnl_drawdown']['threshold']} |
| Sample size | {chk('sample_size')} | {criteria['sample_size']['note']} | {criteria['sample_size']['threshold']} |
| Memory | {chk('memory')} | {criteria['memory']['note']} | {criteria['memory']['threshold']} |

### Rekomendasi
{rec}
### Disclaimer
Demo 1 jam BUKAN forward test valid. 60 menit adalah sampel terlalu kecil
untuk membuktikan edge statistik.

Hasil **PASS** = bot STABIL secara teknis cukup untuk live micro experiment.
Hasil **PASS** ≠ guaranteed profit di live trading.

Modal G4 (Rp 200.000) **HARUS dianggap biaya eksperimen** — bisa hilang semua.
Jika tidak siap kehilangan Rp 200.000 sepenuhnya, jangan aktifkan live.

_Generated by demo_paper_1h.py_
"""
    return md


# ─── G4 artifact writer ──────────────────────────────────────────────────────

def write_g4_artifacts() -> None:
    """Write G4_SETUP_CHECKLIST.md and scripts/g4_micro_activate.py on VPS."""

    checklist = r"""# G4 Micro Live Setup Checklist
> Auto-generated after PASS verdict — demo_paper_1h.py
> Modal: Rp 200.000 (~$12 USD) — dianggap biaya eksperimen, bisa hilang semua.

---

## STATUS: SIAP DIISI OLEH USER

---

## STEP 1 — Buat Wallet & Deposit

### Exchange: Binance
- [ ] Login / buat akun Binance
- [ ] Deposit Rp 200.000 (~$12 USDT) ke Spot wallet
- [ ] Aktifkan Futures trading (atau gunakan Spot untuk cross-exchange arb)
- [ ] Set leverage ke **1x** (no leverage untuk micro run)

### Polymarket (opsional, aktifkan hanya jika ingin poly bets live)
- [ ] Buat MetaMask wallet (atau gunakan yang ada)
- [ ] Bridge minimal $5 USDC ke Polygon network
- [ ] Connect ke https://polymarket.com → approve CLOB contract
- [ ] Export private key: MetaMask → Settings → Security → Export Private Key
- [ ] Simpan private key di tempat aman

---

## STEP 2 — Generate API Keys

### Binance API
- [ ] Buka: https://www.binance.com/en/my/settings/api-management
- [ ] Klik "Create API" → pilih System Generated
- [ ] Label: "reyog-vps"
- [ ] Enable: ✅ Enable Reading, ✅ Enable Spot & Margin Trading
- [ ] Restrict Access by IP: **103.31.38.106**
- [ ] Catat: API Key + Secret Key

### Bybit API (opsional — untuk cross-exchange arb Binance vs Bybit)
- [ ] Buka: https://www.bybit.com/app/user/api-management
- [ ] Buat API key → enable Trade (Derivatives + Spot)
- [ ] IP restriction: **103.31.38.106**
- [ ] Catat: API Key + Secret Key

---

## STEP 3 — Update .env di VPS

SSH ke VPS:
```bash
ssh -i deploy/deploy_key reyogcapital165@103.31.38.106
nano /home/reyogcapital165/reyog-capital/.env
```

Ubah nilai berikut (jangan ubah yang lain):
```bash
# Paper → Live
PAPER_TRADE=false

# Binance (wajib)
BINANCE_API_KEY=<isi API Key dari Step 2>
BINANCE_API_SECRET=<isi Secret Key dari Step 2>
BINANCE_TESTNET=false

# Bybit (opsional)
BYBIT_API_KEY=<isi atau biarkan kosong>
BYBIT_API_SECRET=<isi atau biarkan kosong>
BYBIT_TESTNET=false

# Polymarket (opsional)
POLYMARKET_PRIVATE_KEY=<private key tanpa 0x, atau biarkan kosong>
POLYMARKET_SANDBOX=false
```

---

## STEP 4 — Validasi (WAJIB sebelum activate)

```bash
cd /home/reyogcapital165/reyog-capital
python scripts/g4_micro_activate.py --validate-only
```

Output harus: `✅ ALL CHECKS PASSED`

Jika ada ❌ — perbaiki dulu, jangan lanjut.

---

## STEP 5 — Activate Live

```bash
python scripts/g4_micro_activate.py
```

Script akan:
1. Jalankan validator (exit otomatis jika gagal)
2. Minta konfirmasi ketik `LANJUT G4`
3. Set PAPER_TRADE=false + G4 position limits di .env
4. Restart reyog_engine dengan config live

**JANGAN skip Step 4. JANGAN jalankan ini tanpa mengisi wallet + API keys.**

---

## Parameter G4 Micro

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| Total modal | Rp 200.000 (~$12) | Dianggap hilang |
| Max per posisi | 1% = ~$0.12 | MAX_POSITION_PCT=1.0 |
| Max open sekaligus | 3 posisi = ~$0.36 | MAX_CONCURRENT_POSITIONS=3 |
| Global stop loss | 50% = ~$6 | Seluruh sistem berhenti |
| Target realistis | $0.10–0.50/hari | JIKA edge positif |

---

## Emergency Stop (kapan saja)

```bash
# Dari local machine:
ssh -i deploy/deploy_key reyogcapital165@103.31.38.106 \
  "docker exec reyog_redis redis-cli -a reyog_redis_secret \
   SET arb:risk:halted MANUAL_STOP"

# Atau langsung di VPS:
docker exec reyog_redis redis-cli -a reyog_redis_secret SET arb:risk:halted MANUAL_STOP
```

---

## Monitor Dashboard

https://103-31-38-106.sslip.io

Pantau: PnL tab, Positions tab, Risk tab
"""

    activate = '''#!/usr/bin/env python3
"""
G4 Micro Activate — validates config then activates live trading.

Usage:
  python scripts/g4_micro_activate.py               # validate + activate
  python scripts/g4_micro_activate.py --validate-only

What it does:
  1. Checks all prereqs (.env keys set, containers up, Redis reachable, no halt)
  2. Asks for explicit confirmation ("LANJUT G4")
  3. Writes G4 position limits to .env
  4. Restarts reyog_engine (picks up new .env)

What it does NOT do:
  - Does NOT auto-run without user confirmation
  - Does NOT change strategy code
  - Does NOT touch arb:orders / Redis data

STOP if validator fails. Fix the blocker, re-run --validate-only, then try again.
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO = "/home/reyogcapital165/reyog-capital"
ENV_FILE = os.path.join(REPO, ".env")

# G4 micro limits — applied to .env on activation
G4_OVERRIDES = {
    "PAPER_TRADE": "false",
    "MAX_POSITION_PCT": "1.0",
    "MAX_CONCURRENT_POSITIONS": "3",
    "GLOBAL_STOP_LOSS_PERCENT": "50",
}

REDIS_PW = os.environ.get("REDIS_PASSWORD", "reyog_redis_secret")


def sh(cmd: str) -> tuple[int, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def check_env(key: str) -> bool:
    """Returns True if key is set and non-empty in .env."""
    if not os.path.exists(ENV_FILE):
        return False
    for ln in open(ENV_FILE):
        ln = ln.strip()
        if ln.startswith(f"{key}="):
            val = ln.split("=", 1)[1].strip()
            return bool(val) and not val.startswith("<")
    return False


def run_validator() -> bool:
    """Full pre-live checks. Returns True only if ALL pass."""
    errors = []
    warnings = []

    print("\\n── Pre-live Validator ──────────────────────────────")

    # 1. .env exists
    if not os.path.exists(ENV_FILE):
        errors.append("❌ .env file not found at " + ENV_FILE)
        print("\\n".join(errors))
        return False

    # 2. Required live keys
    required = ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
    for k in required:
        if not check_env(k):
            errors.append(f"❌ {k} not set or empty in .env")
        else:
            print(f"  ✅ {k} is set")

    # 3. PAPER_TRADE=false (warn if still true)
    if check_env("PAPER_TRADE"):
        for ln in open(ENV_FILE):
            if ln.strip().startswith("PAPER_TRADE="):
                val = ln.split("=", 1)[1].strip().lower()
                if val == "true":
                    warnings.append(
                        "⚠  PAPER_TRADE=true in .env — "
                        "activation will override this to false"
                    )
    print(f"  ✅ PAPER_TRADE will be set to false by activation")

    # 4. Containers running
    print("\\nContainer health:")
    for c in ["reyog_engine", "reyog_redis", "reyog_backend", "reyog_risk"]:
        _, out = sh(f\'docker inspect -f "{{{{.State.Running}}}}" {c}\')
        if "true" in out:
            print(f"  ✅ {c} running")
        else:
            errors.append(f"❌ {c} is not running (got: {out[:60]})")

    # 5. Redis reachable + PING
    print("\\nRedis:")
    _, out = sh(
        f"docker exec reyog_redis redis-cli -a {REDIS_PW} "
        "--no-auth-warning PING"
    )
    if "PONG" in out:
        print("  ✅ Redis PING → PONG")
    else:
        errors.append(f"❌ Redis unreachable: {out[:80]}")

    # 6. Risk system not halted
    print("\\nRisk system:")
    _, halted = sh(
        f"docker exec reyog_redis redis-cli -a {REDIS_PW} "
        "--no-auth-warning GET arb:risk:halted"
    )
    halted = halted.strip()
    if not halted or halted in ("", "(nil)", "(empty)"):
        print("  ✅ arb:risk:halted is clear")
    else:
        errors.append(f"❌ arb:risk:halted is SET: {halted} — clear before activating")

    # 7. arb:signals has recent data (engine publishing)
    _, sig_len = sh(
        f"docker exec reyog_redis redis-cli -a {REDIS_PW} "
        "--no-auth-warning LLEN arb:signals"
    )
    if sig_len.isdigit() and int(sig_len) > 0:
        print(f"  ✅ arb:signals has {sig_len} entries (engine active)")
    else:
        warnings.append(f"⚠  arb:signals empty or unreadable (len={sig_len})")

    print()
    for w in warnings:
        print(w)
    if errors:
        for e in errors:
            print(e)
        print("\\n❌ VALIDATION FAILED — Fix above issues before activating live.")
        return False
    print("✅ ALL CHECKS PASSED — system ready for G4 micro live.\\n")
    return True


def apply_env_overrides(overrides: dict) -> None:
    """Safely update .env with overrides, preserving all other values."""
    lines = open(ENV_FILE).readlines()
    applied = set()
    new_lines = []
    for ln in lines:
        key = ln.split("=")[0].strip()
        if key in overrides:
            new_lines.append(f"{key}={overrides[key]}\\n")
            applied.add(key)
        else:
            new_lines.append(ln)
    for k, v in overrides.items():
        if k not in applied:
            new_lines.append(f"{k}={v}\\n")
    open(ENV_FILE, "w").writelines(new_lines)


def main() -> None:
    validate_only = "--validate-only" in sys.argv

    print("=" * 56)
    print("  G4 MICRO ACTIVATE")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("  Modal: Rp 200.000 (~$12 USD)")
    print("  Max drawdown: -50% = Rp 100.000")
    print("=" * 56)

    ok = run_validator()
    if not ok:
        sys.exit(1)

    if validate_only:
        print("--validate-only mode: validation passed. NOT activating.")
        sys.exit(0)

    # Explicit confirmation
    print("⚠  PERINGATAN: Ini akan mengaktifkan LIVE TRADING dengan uang nyata.")
    print("   Modal Rp 200.000 bisa hilang semua.")
    print("   Ketik  LANJUT G4  untuk konfirmasi, atau Ctrl+C untuk batal:")
    print()
    try:
        confirm = input("> ").strip()
    except KeyboardInterrupt:
        print("\\nDibatalkan.")
        sys.exit(0)
    if confirm != "LANJUT G4":
        print(f"Konfirmasi salah (dapat: {confirm!r}). Dibatalkan.")
        sys.exit(1)

    # Apply G4 overrides
    print("\\nApplying G4 position limits to .env...")
    apply_env_overrides(G4_OVERRIDES)
    for k, v in G4_OVERRIDES.items():
        print(f"  {k}={v}")

    # Restart engine to pick up new .env
    print("\\nRestarting reyog_engine...")
    code, out = sh(
        "cd /home/reyogcapital165/reyog-capital && "
        "docker compose up -d --no-deps engine"
    )
    print(f"  -> {out[:200]}")
    if code != 0:
        print("❌ engine restart failed — check docker compose logs engine")
        sys.exit(1)

    # Confirm engine running
    import time
    time.sleep(5)
    _, running = sh(\'docker inspect -f "{{{{.State.Running}}}}" reyog_engine\')
    if "true" in running:
        print("  ✅ reyog_engine running")
    else:
        print(f"  ⚠  reyog_engine state: {running}")

    print()
    print("✅ G4 MICRO LIVE ACTIVATED")
    print("   Dashboard: https://103-31-38-106.sslip.io")
    print("   Emergency stop:")
    print("   docker exec reyog_redis redis-cli -a reyog_redis_secret "
          "SET arb:risk:halted MANUAL_STOP")


if __name__ == "__main__":
    main()
'''

    checklist_path = os.path.join(REPO, "G4_SETUP_CHECKLIST.md")
    activate_path = os.path.join(REPO, "scripts", "g4_micro_activate.py")

    with open(checklist_path, "w") as f:
        f.write(checklist)
    with open(activate_path, "w") as f:
        f.write(activate)
    os.chmod(activate_path, 0o755)

    log(f"G4 artifacts written:")
    log(f"  {checklist_path}")
    log(f"  {activate_path}")


# ─── main loop ───────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(LOGS, exist_ok=True)

    log("=" * 56)
    log("  DEMO PAPER 1H — START")
    log("  6 criteria — ALL must pass for LANJUT LIVE")
    log("  NO Redis reset. Parallel-safe with window_24h_monitor.")
    log("=" * 56)

    # ── T+0 baseline ──────────────────────────────────────────────────────────
    log("T+0: Taking baseline snapshot...")
    baseline = take_snapshot("baseline")
    with open(os.path.join(LOGS, "demo_1h_baseline.json"), "w") as f:
        json.dump(baseline, f, indent=2)
    log(
        f"T+0 baseline: close_events={baseline['total_close_events']}, "
        f"pnl_real={baseline['total_pnl_real']}, "
        f"pnl_poly={baseline['total_pnl_poly']}, "
        f"redis={baseline['redis_mem_mb']:.1f}MB"
    )

    start_time = time.time()
    cp_written = {20: False, 40: False}
    halted_during_run = False

    # ── polling loop ──────────────────────────────────────────────────────────
    while True:
        elapsed_sec = time.time() - start_time
        elapsed_min = elapsed_sec / 60.0

        # Rising-edge halt detection (accumulates for the full run)
        halt = rcli("GET arb:risk:halted")
        if halt and halt not in ("(empty)", "", "(nil)"):
            if not halted_during_run:
                log(f"⚠  arb:risk:halted triggered: {halt}")
                halted_during_run = True

        # ── T+20 checkpoint ───────────────────────────────────────────────────
        if elapsed_min >= 20 and not cp_written[20]:
            log(f"T+{elapsed_min:.0f}m: T+20 snapshot...")
            snap = take_snapshot("T+20m")
            snap["delta"] = compute_delta(baseline, snap, halted_during_run)
            with open(os.path.join(LOGS, "demo_1h_T20.json"), "w") as f:
                json.dump(snap, f, indent=2)
            d = snap["delta"]
            log(
                f"T+20: new_trades={d['new_close_events']}, "
                f"crypto_pnl_delta=${d['crypto_pnl_delta']:.4f}, "
                f"redis={snap['redis_mem_mb']:.1f}MB, "
                f"risk_halted={halted_during_run}"
            )
            cp_written[20] = True

        # ── T+40 checkpoint ───────────────────────────────────────────────────
        if elapsed_min >= 40 and not cp_written[40]:
            log(f"T+{elapsed_min:.0f}m: T+40 snapshot...")
            snap = take_snapshot("T+40m")
            snap["delta"] = compute_delta(baseline, snap, halted_during_run)
            with open(os.path.join(LOGS, "demo_1h_T40.json"), "w") as f:
                json.dump(snap, f, indent=2)
            d = snap["delta"]
            log(
                f"T+40: new_trades={d['new_close_events']}, "
                f"crypto_pnl_delta=${d['crypto_pnl_delta']:.4f}, "
                f"redis={snap['redis_mem_mb']:.1f}MB, "
                f"risk_halted={halted_during_run}"
            )
            cp_written[40] = True

        # ── T+60 FINAL ────────────────────────────────────────────────────────
        if elapsed_sec >= RUN_DURATION_SEC:
            log(f"T+60m: Final snapshot + verdict...")
            final = take_snapshot("T+60m (FINAL)")
            delta = compute_delta(baseline, final, halted_during_run)
            final["delta"] = delta
            with open(os.path.join(LOGS, "demo_1h_FINAL.json"), "w") as f:
                json.dump(final, f, indent=2)

            d = delta
            log(
                f"T+60 FINAL: new_trades={d['new_close_events']}, "
                f"crypto_pnl_delta=${d['crypto_pnl_delta']:.4f}, "
                f"poly_pnl_delta=${d['poly_pnl_delta']:.4f}, "
                f"redis={final['redis_mem_mb']:.1f}MB"
            )

            # ── Verdict ───────────────────────────────────────────────────────
            passed, criteria = evaluate_verdict(delta, final)
            verdict_str = "PASS" if passed else "FAIL"

            log(f"")
            log(f"══ VERDICT: {verdict_str} ══")
            for k, v in criteria.items():
                icon = "✅" if v["pass"] else "❌"
                log(f"  {icon} {k}: {v['note']}")
            log(f"")

            # ── Report ────────────────────────────────────────────────────────
            report = write_report(baseline, final, delta, passed, criteria)
            report_path = os.path.join(LOGS, "demo_1h_FINAL_REPORT.md")
            with open(report_path, "w") as f:
                f.write(report)
            log(f"Report: {report_path}")

            if passed:
                log("PASS — generating G4 setup artifacts...")
                write_g4_artifacts()
                log("G4_SETUP_CHECKLIST.md + scripts/g4_micro_activate.py ready.")
                log("Langkah selanjutnya:")
                log("  1. Baca G4_SETUP_CHECKLIST.md")
                log("  2. Isi wallet + API keys (MANUAL)")
                log("  3. python scripts/g4_micro_activate.py --validate-only")
                log("  4. python scripts/g4_micro_activate.py")
                log("  JANGAN otomatis activate. User harus manual.")
            else:
                fail_path = os.path.join(LOGS, "demo_1h_VERDICT_FAIL.md")
                with open(fail_path, "w") as f:
                    f.write(report)
                log(f"FAIL report: {fail_path}")
                log("STOP — jangan lanjut ke live. Perbaiki issues di atas dulu.")

            log("=" * 56)
            log(f"  DEMO 1H SELESAI — VERDICT: {verdict_str}")
            log("=" * 56)
            break

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
