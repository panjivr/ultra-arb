"""Quick sanity test for the fixed _classify_market + _updown_probability."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the functions directly from the engine module
import importlib.util
spec = importlib.util.spec_from_file_location(
    "rme", os.path.join(os.path.dirname(__file__), "real_market_engine.py"))
# The module imports redis etc at top-level via functions, but module-level
# imports are light. Guard against heavy imports failing.
try:
    rme = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rme)
except Exception as e:
    print("module load issue (continuing if funcs exist):", repr(e)[:100])

classify = rme._classify_market
prob = rme._updown_probability

print("=== F4: _classify_market (horizon parsing) ===")
cases = [
    "XRP Up or Down - May 21, 7:45AM-7:50AM ET",       # 5 min
    "Bitcoin Up or Down - May 21, 4:45PM-5:00PM ET",   # 15 min
    "Ethereum Up or Down - May 21, 4:00PM-4:30PM ET",  # 30 min
    "Solana Up or Down - May 21, 11:50PM-12:05AM ET",  # 15 min (cross midnight)
    "Bitcoin Up or Down 5m",                            # suffix
    "BTC Up or Down Daily",                             # daily
]
for q in cases:
    label, hrs = classify(q)
    print(f"  {label:6} {hrs and round(hrs,3)}  <- {q}")

print("\n=== F5: _updown_probability ===")
# Build synthetic recent_mids series
def series(start, per_step_drift, noise_std, n=120, seed=1):
    """Gaussian-ish returns: realistic crypto has noise >> per-sample drift."""
    import random
    random.seed(seed)
    out = [start]
    for _ in range(n - 1):
        # sum of 3 uniforms ≈ gaussian
        noise = (random.uniform(-1, 1) + random.uniform(-1, 1) + random.uniform(-1, 1)) / 3 * noise_std
        step = per_step_drift + noise
        out.append(out[-1] * (1 + step))
    return out

# Realistic: per-sample std ~0.0005 (0.05%/sample). "Significant" drift ~0.0001.
flat = series(100, 0.0, 0.0005, seed=2)             # no drift
strong_up = series(100, 0.00012, 0.0005, seed=3)    # significant up-drift (t~2.5)
strong_dn = series(100, -0.00012, 0.0005, seed=4)   # significant down-drift
tiny_up = series(100, 0.00003, 0.0006, seed=5)      # weak drift buried in noise

scenarios = [
    ("flat/noise   5m ", flat, 5/60),
    ("strong-up    5m ", strong_up, 5/60),
    ("strong-up    15m", strong_up, 15/60),
    ("strong-up    4h ", strong_up, 4.0),     # should decay toward 0.5
    ("strong-down  5m ", strong_dn, 5/60),
    ("tiny-up      5m ", tiny_up, 5/60),       # insignificant -> 0.5
]
for name, s, hrs in scenarios:
    p = prob(s[-1], s, hrs)
    edge = p - 0.495
    fires = "BET" if abs(edge) >= (0.04 if hrs <= 0.25 else 0.05) else "skip"
    print(f"  {name}: p_up={p:.4f}  edge_vs_0.495={edge:+.4f}  -> {fires}")

print("\nExpected: flat/tiny -> 0.50 (skip); strong-up 5m/15m -> >0.5 capped 0.58;")
print("          strong-up 4h -> ~0.50 (horizon decay); strong-down -> <0.5")
