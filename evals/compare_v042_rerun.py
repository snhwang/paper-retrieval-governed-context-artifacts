#!/usr/bin/env python3
"""Old (BEAR 0.4.0) against new (BEAR 0.4.2) for every rerun result file.

Walks each pair of JSON files and records every scalar that changed (path,
old, new) and, for per-query arrays (numeric lists longer than 20), how many
elements changed and by how much at most. Lists of records longer than 20
(per-pair or per-query records) are compared element by element as JSON.
Provenance, timing and the per-task arrays of the tag-noise sweep (whose
per-query content the summary carries) are skipped. Files that exist only
on one side are reported as such.

Usage:
    python evals/compare_v042_rerun.py --output results/v042_rerun_comparison.json \\
        --log-file results/v042_rerun_comparison_output.txt
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "results"
PAIRS = [
    ("tag_noise.json", "tag_noise_v042.json"),
    ("tag_noise_nemotron.json", "tag_noise_nemotron_v042.json"),
    ("tag_noise_overrestriction.json", "tag_noise_overrestriction_v042.json"),
    ("leakage_threat.json", "leakage_threat_v042.json"),
    ("query_giveaways.json", "query_giveaways_v042.json"),
    ("mandatory_coverage.json", "mandatory_coverage_v042.json"),
    ("metadata_filter_baseline_toolbench_bge.json", "metadata_filter_baseline_toolbench_bge_v042.json"),
    ("metadata_filter_baseline_petsim_bge.json", "metadata_filter_baseline_petsim_bge_v042.json"),
    ("metadata_filter_baseline_toolbench_nemotron.json",
     "metadata_filter_baseline_toolbench_nemotron_v042.json"),
    ("metadata_filter_baseline_petsim_nemotron.json",
     "metadata_filter_baseline_petsim_nemotron_v042.json"),
    ("cpa_maintained.json", "cpa_maintained_v042.json"),
]
SKIP = ("provenance", "elapsed", "seconds", "per_task", "timestamp", "utc", "wall")
TOL = 1e-12


def load(p: Path):
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def differ(a, b) -> bool:
    if is_num(a) and is_num(b):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return False
        return abs(a - b) > TOL
    return a != b


def walk(o, n, path: str, out: dict) -> None:
    if any(s in path.lower() for s in SKIP):
        return
    if isinstance(o, dict) and isinstance(n, dict):
        for k in sorted(set(o) | set(n), key=str):
            if k not in o:
                out["added"].append(f"{path}/{k}")
            elif k not in n:
                out["removed"].append(f"{path}/{k}")
            else:
                walk(o[k], n[k], f"{path}/{k}", out)
        return
    if isinstance(o, list) and isinstance(n, list):
        if len(o) > 20 or len(n) > 20:
            if len(o) != len(n):
                out["arrays"].append({"path": path, "len_old": len(o), "len_new": len(n)})
                return
            if all(is_num(x) for x in o) and all(is_num(x) for x in n):
                d = [abs(x - y) for x, y in zip(o, n) if differ(x, y)]
                if d:
                    out["arrays"].append({"path": path, "n": len(o), "changed": len(d),
                                          "max_abs_change": max(d)})
            else:
                c = sum(json.dumps(x, sort_keys=True, default=str) != json.dumps(y, sort_keys=True, default=str)
                        for x, y in zip(o, n))
                if c:
                    out["arrays"].append({"path": path, "n": len(o), "changed": c})
            return
        if len(o) != len(n):
            out["scalars"].append({"path": path, "old": o, "new": n})
            return
        for i, (x, y) in enumerate(zip(o, n)):
            walk(x, y, f"{path}[{i}]", out)
        return
    if differ(o, n):
        out["scalars"].append({"path": path, "old": o, "new": n})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--log-file", type=Path, required=True)
    ap.add_argument("--max-lines", type=int, default=400)
    ap.add_argument("--label", default="agent validation run",
                    help="What kind of run the new files come from, written at the top.")
    args = ap.parse_args()
    for p in (args.output, args.log_file):
        if p.exists():
            sys.exit(f"{p} exists. Results are never overwritten.")
    report = {"label": args.label}
    lines = [f"# BEAR 0.4.0 against 0.4.2, {args.label}"]
    for old_name, new_name in PAIRS:
        po, pn = R / old_name, R / new_name
        if not po.exists() or not pn.exists():
            report[new_name] = {"missing": [str(p.name) for p in (po, pn) if not p.exists()]}
            lines.append(f"\n## {old_name} -> {new_name}: MISSING {report[new_name]['missing']}")
            continue
        o, n = load(po), load(pn)
        out = {"scalars": [], "arrays": [], "added": [], "removed": []}
        walk(o, n, "", out)
        vo = (o.get("provenance") or {}).get("bear_version")
        vn = (n.get("provenance") or {}).get("bear_version")
        out["bear"] = [vo, vn, (n.get("provenance") or {}).get("bear_source_sha")]
        report[new_name] = out
        lines.append(f"\n## {old_name} ({vo}) -> {new_name} ({vn}): {len(out['scalars'])} scalars and "
                     f"{len(out['arrays'])} arrays changed, {len(out['added'])} keys added, "
                     f"{len(out['removed'])} removed")
        for e in out["scalars"][:args.max_lines]:
            lines.append(f"  {e['path']}: {e['old']} -> {e['new']}")
        if len(out["scalars"]) > args.max_lines:
            lines.append(f"  ... {len(out['scalars']) - args.max_lines} more scalars in the JSON")
        for e in out["arrays"][:args.max_lines]:
            lines.append(f"  array {e}")
        for k in out["added"][:20]:
            lines.append(f"  added {k}")
        for k in out["removed"][:20]:
            lines.append(f"  removed {k}")
    text = "\n".join(lines)
    print(text)
    args.output.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    args.log_file.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
