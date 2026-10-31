"""Table 7 rerun vs July: per row exact and tool accuracy with CIs, the queries
whose outcome changed, McNemar, and the governed vs ungated tests."""
import json
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
pub_scores = {s["condition"]: s for s in json.loads(Path(sys.argv[2]).read_text())["scores"]}
pub_res = json.loads(Path(sys.argv[3]).read_text())
pub_ci = {}
for r in pub_res.get("results", []):
    name = r.get("condition") or r.get("name")
    pub_ci[name] = r
summ = json.loads((out / "rerun_summary.json").read_text())


def ci(x):
    if isinstance(x, dict):
        return x.get("ci_lower", x.get("lo")), x.get("ci_upper", x.get("hi"))
    if isinstance(x, (list, tuple)) and len(x) >= 2:
        return x[0], x[1]
    return None, None


print("| Row | Tool acc 2026-10-31 [95% CI] | Tool acc July [95% CI] | Exact acc 2026-10-31 [95% CI] | Exact acc July [95% CI] | "
      "Queries changed (tool / exact) | McNemar p (tool / exact) |")
print("|---|---|---|---|---|---|---|")
for name, r in summ["rows"].items():
    f = json.loads((out / (name.lower().replace("+", "_").replace(" ", "_").replace("(", "").replace(")", "")
                           + ".scores.json")).read_text())
    tl, th = ci(f["tool_ci"])
    el, eh = ci(f["exact_ci"])
    pc = pub_ci.get(name, {})
    ptl, pth = ci(pc.get("tool_ci"))
    pel, peh = ci(pc.get("exact_ci"))
    pt = r.get("published_tool")
    pe = r.get("published_exact")
    fmt = lambda v, lo, hi: (f"{v:.3f} [{lo:.3f}, {hi:.3f}]" if lo is not None else f"{v:.3f}") if v is not None else "n/a"
    print(f"| {name} | {fmt(r['tool'], tl, th)} | {fmt(pt, ptl, pth)} | {fmt(r['exact'], el, eh)} | {fmt(pe, pel, peh)} | "
          f"{r.get('tool_queries_changed_vs_published')} / {r.get('exact_queries_changed_vs_published')} | "
          f"{r.get('tool_mcnemar_vs_published', {}).get('p', float('nan')):.3g} / "
          f"{r.get('exact_mcnemar_vs_published', {}).get('p', float('nan')):.3g} |")
print()
for pair, v in summ["pairs"].items():
    print(f"- {pair}: tool Δ {v['tool']['delta']:+.3f} (d = {v['tool']['d']:.2f}, p = {v['tool']['p']:.2g}); "
          f"exact Δ {v['exact']['delta']:+.3f} (d = {v['exact']['d']:.2f}, p = {v['exact']['p']:.2g})")
# July's governed vs ungated for the same pairs
for g, u in (("BEAR+BM25 (gov)", "BM25 (no gov)"), ("BEAR+BGE (gov)", "BGE (no gov)")):
    if g in pub_scores and u in pub_scores:
        for m in ("_tool_scores", "_exact_scores"):
            a, b = np.asarray(pub_scores[g][m]), np.asarray(pub_scores[u][m])
            d = a - b
            print(f"- July {g} vs {u} {m.strip('_').replace('_scores', '')}: Δ {d.mean():+.3f} (d = {d.mean() / d.std(ddof=1):.2f})")
