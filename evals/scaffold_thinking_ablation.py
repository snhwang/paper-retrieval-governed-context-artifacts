#!/usr/bin/env python
"""Same-format native-reasoning ablation: constrained scaffold, thinking OFF vs ON.

Usage:  python evals/scaffold_thinking_ablation.py <label> [suffix]
e.g.    python evals/scaffold_thinking_ablation.py g4-31b
        python evals/scaffold_thinking_ablation.py g4-31b s42

Pairs the native-OFF scaffold run (run_model_scaffold_nothink.sh) against the
native-ON scaffold run (run_model_scaffold_thinking.sh). Because the output
format is identical in both, the difference isolates native reasoning -- unlike
the cross-format comparison (scaffold-off vs reasoning-mode-on), which confounds
reasoning with prompt format.

Also prints each run's empty-response health, so a silent-failure condition
cannot masquerade as a low score (see commit 10659ab).
"""
import json, sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stat_utils import bootstrap_ci, mcnemar

if len(sys.argv) not in (2, 3):
    sys.exit("usage: python evals/scaffold_thinking_ablation.py <label> [suffix]")
LABEL = sys.argv[1]
SUFFIX = sys.argv[2] if len(sys.argv) == 3 else "full"
R = pathlib.Path(__file__).resolve().parent.parent / "results"

def load(run_label):
    for name in (f"toolbench_react_metrics_{run_label}_partial.json",
                 f"toolbench_react_metrics_{run_label}.json"):
        p = R / name
        if p.exists():
            return json.load(open(p))
    sys.exit(f"missing results for {run_label}")

off = load(f"{LABEL}-scaffold-nothink-full")
on = load(f"{LABEL}-scaffold-thinking-{SUFFIX}")

def health(d, cond):
    h = (d.get("response_health") or {})
    for k, v in h.items():
        if cond.split("_")[0] in k.lower().replace(" ", "_") or cond in k:
            return v
    return None

for cond in ("mono_react", "bear_react"):
    a_off = np.array(off["per_query_correct"][cond])
    a_on_full = np.array(on["per_query_correct"][cond])
    idx = on.get("sample_indices")
    a_off_m = a_off[idx] if idx else a_off      # match the sampled subset
    a_on = a_on_full
    if len(a_off_m) != len(a_on):
        print(f"  {cond}: length mismatch ({len(a_off_m)} vs {len(a_on)}), skipping")
        continue
    o1 = bootstrap_ci(a_off_m.astype(float), 10000)
    o2 = bootstrap_ci(a_on.astype(float), 10000)
    mc = mcnemar(a_off_m, a_on)
    d = a_on.mean() - a_off_m.mean()
    verdict = "HELPS" if d > 0 else ("HURTS" if d < 0 else "no change")
    label = "monolithic (3,225)" if cond == "mono_react" else "BEAR top-5"
    print(f"\n=== {LABEL} {label}: constrained scaffold, thinking OFF vs ON (n={len(a_on)}) ===")
    print(f"  thinking OFF  {o1['point_estimate']:.3f} [{o1['ci_lower']:.3f}, {o1['ci_upper']:.3f}]")
    print(f"  thinking ON   {o2['point_estimate']:.3f} [{o2['ci_lower']:.3f}, {o2['ci_upper']:.3f}]")
    print(f"  => native reasoning {verdict} by {abs(d):.3f}  (McNemar p={mc['p_value']:.2e})")

print("\n--- response health (empty responses must be ~0 for these to be valid) ---")
for tag, d in (("thinking OFF", off), ("thinking ON", on)):
    h = d.get("response_health")
    print(f"  {tag}: {h if h else '(not recorded -- run predates the health instrumentation)'}")
