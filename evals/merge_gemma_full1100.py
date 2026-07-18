#!/usr/bin/env python
"""Assemble Gemma4:31b full-1,100 ToolBench results from the stratified pilot
(seed42 u seed43 = 366 queries) plus the 734-query complement run.

Each query is evaluated exactly once at the same settings (gemma4:31b, temp=1.0,
top_p=0.95, top_k=64, cap=0); the pilot and complement together tile the full
standard ToolBench test set with no re-run. For the 30 queries sampled by both
seeds we keep seed 42's result. Prints the full-1,100 Table 9 grid with 95%
bootstrap CIs and the paired McNemar tests, and writes a merged per-condition
per-query file for reproducibility.
"""
import json, sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stat_utils import bootstrap_ci, mcnemar

R = pathlib.Path(__file__).resolve().parent.parent / "results"
N = 1100

# condition -> (key, seed42 file, seed43 file, complement file)
COND = {
 "mono_off":    ("mono_react",  "g4-mono-nothink-strat",        "g4-mono-nothink-s43",        "g4-mono-nothink-compl"),
 "mono_on":     ("mono_react",  "g4-mono-think-strat",          "g4-mono-think-s43",          "g4-mono-think-compl"),
 "bear_single": ("bear_single", "g4-bearsingle-nothink-strat",  "g4-bearsingle-nothink-s43",  "g4-bearsingle-nothink-compl"),
 "bear_react":  ("bear_react",  "g4-bear-strat",                "g4-bear-s43",                "g4-bear-compl"),
}

def load(label):
    p = R / f"toolbench_react_metrics_{label}_partial.json"
    return json.load(open(p))

def merge(key, f42, f43, fc):
    full = np.full(N, -1, dtype=int)
    for lbl in (f42, f43, fc):          # seed42 first -> wins the 30 overlaps
        d = load(lbl); idx = d["sample_indices"]; arr = d["per_query_correct"][key]
        assert len(idx) == len(arr), f"{lbl}: index/array length mismatch"
        for i, v in zip(idx, arr):
            if full[i] == -1:
                full[i] = v
    missing = int((full == -1).sum())
    assert missing == 0, f"{key}: {missing} queries uncovered"
    return full

def ci(a):
    o = bootstrap_ci(a.astype(float), 10000)
    return o["point_estimate"], o["ci_lower"], o["ci_upper"]

full = {}
print(f"=== Gemma4:31b FULL {N} (merged pilot 366 + complement 734) ===\n")
merged_out = {}
for name, (key, f42, f43, fc) in COND.items():
    a = merge(key, f42, f43, fc); full[name] = a; merged_out[name] = a.tolist()
    pe, lo, hi = ci(a)
    print(f"  {name:12s} {pe:.3f} [{lo:.3f}, {hi:.3f}]   n={len(a)}")

print("\n=== paired McNemar (full 1,100) ===")
for lo_, hi_, lab in [("mono_off","mono_on","monolithic reasoning OFF vs ON"),
                      ("bear_single","bear_react","BEAR single vs +reasoning")]:
    mc = mcnemar(full[lo_], full[hi_])
    d = full[hi_].mean() - full[lo_].mean()
    print(f"  {lab:34s} {full[lo_].mean():.3f} -> {full[hi_].mean():.3f}  "
          f"(delta {d:+.3f})  p={mc['p_value']:.2e}  "
          f"discordant {mc['b_a_right_b_wrong']}/{mc['c_a_wrong_b_right']}")

out = R / "toolbench_react_metrics_g4-FULL1100_merged.json"
json.dump({"model": "gemma4:31b", "n": N, "monolithic_cap": 0,
           "note": "merged pilot(seed42 u seed43)=366 + complement=734; seed42 wins 30 overlaps",
           "per_query_correct": merged_out}, open(out, "w"), indent=2)
print(f"\nWrote {out}")
