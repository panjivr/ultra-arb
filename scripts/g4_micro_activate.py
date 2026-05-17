#!/usr/bin/env python3
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

    print("\n── Pre-live Validator ──────────────────────────────")

    # 1. .env exists
    if not os.path.exists(ENV_FILE):
        errors.append("❌ .env file not found at " + ENV_FILE)
        print("\n".join(errors))
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
    print("\nContainer health:")
    for c in ["reyog_engine", "reyog_redis", "reyog_backend", "reyog_risk"]:
        _, out = sh(f'docker inspect -f "{{{{.State.Running}}}}" {c}')
        if "true" in out:
            print(f"  ✅ {c} running")
        else:
            errors.append(f"❌ {c} is not running (got: {out[:60]})")

    # 5. Redis reachable + PING
    print("\nRedis:")
    _, out = sh(
        f"docker exec reyog_redis redis-cli -a {REDIS_PW} "
        "--no-auth-warning PING"
    )
    if "PONG" in out:
        print("  ✅ Redis PING → PONG")
    else:
        errors.append(f"❌ Redis unreachable: {out[:80]}")

    # 6. Risk system not halted
    print("\nRisk system:")
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
        print("\n❌ VALIDATION FAILED — Fix above issues before activating live.")
        return False
    print("✅ ALL CHECKS PASSED — system ready for G4 micro live.\n")
    return True


def apply_env_overrides(overrides: dict) -> None:
    """Safely update .env with overrides, preserving all other values."""
    lines = open(ENV_FILE).readlines()
    applied = set()
    new_lines = []
    for ln in lines:
        key = ln.split("=")[0].strip()
        if key in overrides:
            new_lines.append(f"{key}={overrides[key]}\n")
            applied.add(key)
        else:
            new_lines.append(ln)
    for k, v in overrides.items():
        if k not in applied:
            new_lines.append(f"{k}={v}\n")
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
        print("\nDibatalkan.")
        sys.exit(0)
    if confirm != "LANJUT G4":
        print(f"Konfirmasi salah (dapat: {confirm!r}). Dibatalkan.")
        sys.exit(1)

    # Apply G4 overrides
    print("\nApplying G4 position limits to .env...")
    apply_env_overrides(G4_OVERRIDES)
    for k, v in G4_OVERRIDES.items():
        print(f"  {k}={v}")

    # Restart engine to pick up new .env
    print("\nRestarting reyog_engine...")
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
    _, running = sh('docker inspect -f "{{{{.State.Running}}}}" reyog_engine')
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
