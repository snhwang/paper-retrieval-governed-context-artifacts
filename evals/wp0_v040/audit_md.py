import json
import sys
from pathlib import Path

d = json.loads(Path(sys.argv[1]).read_text())
out = ["| File | Table | Cells compared | Comparator | Result |", "|---|---|---|---|---|"]
VERDICT = {
    "results/alpha_sweep_qwen3-4b.json": "FALLBACK: alpha 0.7, 0.9, 1.0 equal hash. Replaced by 0.4.2 (and the 0.1.10 control with the real model)",
    "results/backend_comparison.json": "1 match, uninformative: ITR-hybrid para_f1 equals its fallback, but every governed dense backend gives the same 0.637 [0.627, 0.648] there; the other 4 ITR-hybrid columns differ from the fallback",
    "results/scalability_results.csv": "all BEAR columns equal the fallback, uninformative: they also equal real BGE on 0.4.2 (recall 1.0, tokens set by the gate); the published N=10 build took 70 s, a model load",
    "results/eval_tool_scaling_output.txt": "all 38 cells equal the fallback, uninformative: they also equal real BGE on 0.4.2 (gate decides, threshold 0)",
    "results/governance_decomposed.json": "stale June BGE run (Full 0.780), not used by the table (0.653 comes from governance_decomposed_bge.json); differs from the fallback (0.841). Not a fallback",
    "results/toolbench_react_metrics_gemma4-31b-bear_partial.json": "exploratory partial (Jul 16), not in Table 9. bear_single 0.005 is empty output (max_tokens 100 before the fix), not retrieval: bear_react on the same lists is 0.820",
}
for rel, v in sorted(d["files"].items()):
    res = VERDICT.get(rel)
    if res is None:
        if v.get("pending"):
            res = f"pending ({v['pending']})"
        elif v.get("flagged"):
            res = f"{v['flagged']} flagged"
        else:
            res = "none found"
        if v.get("constant_array_matches"):
            res += f" ({v['constant_array_matches']} matches of all-zero mand-only arrays set aside)"
    comp = "; ".join(v.get("comparators", []))
    out.append(f"| {rel} | {v.get('table', '')} | {v.get('cells_checked', '')} | {comp} | {res} |")
out.append("")
out.append("Published result files not compared, and why:")
for r in d["result_files_not_compared"]:
    out.append(f"- {r}")
out.append("")
out.append("| Log (published) | Load failures, fallback warnings or tracebacks | Early stop |")
out.append("|---|---|---|")
for rel, r in sorted(d["logs"]["published"].items()):
    lf = "; ".join(f"line {x['line']}: {x['text'][:60]} [{x['section'][:40]}]" for x in r["load_failures"]) or "none"
    es = "; ".join(f"{x['section'][:40]} reached {x['reached']}" for x in r["early_stops"]) or "none"
    out.append(f"| {rel} | {lf} | {es} |")
own = d["logs"]["own_v0110_controls"]
out.append("")
out.append(f"This run's 0.1.10 control logs scanned: {len(own)}. With a load failure or fallback: "
           f"{sum(1 for v in own.values() if v['load_failures']) or 'none'}.")
Path(sys.argv[2]).write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out[:80]))
