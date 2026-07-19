#!/usr/bin/env python
"""Print the Table-9 grid + paired McNemar for one model's full-1,100 runs.

Usage:  python evals/grid_from_full1100.py <label>
e.g.    python evals/grid_from_full1100.py g4-12b

Reads the four run-labelled metrics files produced by run_model_full1100.sh and
reports the four cells (monolithic reasoning off/on, BEAR single/reasoning) with
95% bootstrap CIs and the two within-model paired McNemar tests.
"""
import json, sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stat_utils import bootstrap_ci, mcnemar

if len(sys.argv) != 2:
    sys.exit("usage: python evals/grid_from_full1100.py <label>   (e.g. g4-12b)")
LABEL = sys.argv[1]
R = pathlib.Path(__file__).resolve().parent.parent / "results"

# condition -> (metrics-file run-label, per_query key)
COND = {
    "mono_off":    (f"{LABEL}-mono-nothink-full",       "mono_react"),
    "mono_on":     (f"{LABEL}-mono-think-full",         "mono_react"),
    "bear_single": (f"{LABEL}-bearsingle-nothink-full", "bear_single"),
    "bear_react":  (f"{LABEL}-bear-full",               "bear_react"),
}

def load(run_label, key):
    p = R / f"toolbench_react_metrics_{run_label}_partial.json"
    if not p.exists():
        p = R / f"toolbench_react_metrics_{run_label}.json"
    d = json.load(open(p))
    return np.array(d["per_query_correct"][key])

arr = {}
print(f"=== {LABEL}  full-1100 grid ===\n")
for name, (rl, key) in COND.items():
    try:
        a = load(rl, key); arr[name] = a
        o = bootstrap_ci(a.astype(float), 10000)
        print(f"  {name:12s} {o['point_estimate']:.3f} "
              f"[{o['ci_lower']:.3f}, {o['ci_upper']:.3f}]  n={len(a)}")
    except FileNotFoundError:
        print(f"  {name:12s} MISSING ({rl})")

print("\n=== paired McNemar ===")
for a_, b_, lab in [("mono_off", "mono_on", "monolithic reasoning OFF vs ON"),
                    ("bear_single", "bear_react", "BEAR single vs +reasoning")]:
    if a_ in arr and b_ in arr:
        mc = mcnemar(arr[a_], arr[b_]); d = arr[b_].mean() - arr[a_].mean()
        print(f"  {lab:34s} {arr[a_].mean():.3f} -> {arr[b_].mean():.3f} "
              f"({d:+.3f})  p={mc['p_value']:.2e}  "
              f"disc {mc['b_a_right_b_wrong']}/{mc['c_a_wrong_b_right']}")
