#!/usr/bin/env python
"""Does the constrained ReAct scaffold help or hurt, native thinking off?

Usage:  python evals/scaffold_vs_single.py <label>   (e.g. g4-31b)

Reads the single file produced by run_model_scaffold_nothink.sh (all three
constrained native-off conditions) and reports:
  - BEAR single-turn vs BEAR scaffold  (the clean, matched scaffold effect)
  - monolithic under the scaffold      (compare across models / to Mistral 0.035)
with 95% bootstrap CIs and the paired McNemar test.
"""
import json, sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stat_utils import bootstrap_ci, mcnemar

if len(sys.argv) != 2:
    sys.exit("usage: python evals/scaffold_vs_single.py <label>")
LABEL = sys.argv[1]
R = pathlib.Path(__file__).resolve().parent.parent / "results"
p = R / f"toolbench_react_metrics_{LABEL}-scaffold-nothink-full_partial.json"
if not p.exists():
    p = R / f"toolbench_react_metrics_{LABEL}-scaffold-nothink-full.json"
d = json.load(open(p))["per_query_correct"]

def ci(k):
    a = np.array(d[k]); o = bootstrap_ci(a.astype(float), 10000)
    return a, o["point_estimate"], o["ci_lower"], o["ci_upper"]

print(f"=== {LABEL}: constrained scaffold, native thinking OFF (n={len(d['bear_single'])}) ===\n")
for k, desc in [("mono_react", "monolithic (3,225) under scaffold"),
                ("bear_react", "BEAR top-5 under scaffold"),
                ("bear_single", "BEAR top-5 single-turn (baseline)")]:
    _, pe, lo, hi = ci(k)
    print(f"  {desc:38s} {pe:.3f} [{lo:.3f}, {hi:.3f}]")

bs, m_bs, *_ = ci("bear_single")
br, m_br, *_ = ci("bear_react")
mc = mcnemar(bs, br)
verdict = "HURTS" if m_br < m_bs else ("HELPS" if m_br > m_bs else "no change")
print(f"\n  Scaffold effect on BEAR (native off): single {m_bs:.3f} -> scaffold {m_br:.3f} "
      f"({m_br-m_bs:+.3f})  McNemar p={mc['p_value']:.2e}  => scaffold {verdict}")
print("  (Compare monolithic-scaffold above to Mistral's 0.035 for the scale effect.)")
