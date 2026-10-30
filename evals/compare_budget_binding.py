"""Paired comparison of two budget-binding runs (eval_budget_binding.py).

Both runs hold the same queries in the same order, so each per-query array
pairs up. For every condition and backend present in the new run, this
compares the admissible-set size (trace, whole pool) and the cut-binds flag
against the old run's array for the same base backend. A backend with
restore switches ("bm25:dropped_rows") is compared with the old run's plain
backend ("bm25"), which shows whether the switch brings the old counts back.
Metadata rows (backend-free) are compared too.

Per pair: the mean difference with a paired bootstrap 95% CI, paired Cohen's
d, Wilcoxon and paired t (tistr2_common.paired_summary), the number of
queries that changed, and McNemar on the |A| > k flags.

Usage:
    python evals/compare_budget_binding.py \\
        --old results/budget_binding.json --new results/budget_binding_v042.json \\
        --output results/budget_binding_v042_vs_v040.json \\
        --log-file results/budget_binding_v042_vs_v040_output.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tistr2_common import Tee, mcnemar_summary, paired_summary  # noqa: E402

project_root = Path(__file__).resolve().parents[1]


def series(cond: dict) -> dict[str, dict]:
    """name -> {"size": per-query admissible size, "cut": per-query cut flag or None}."""
    out = {"metadata": {"size": cond["metadata"]["per_query_floor"], "cut": None}}
    for b, e in cond["backends"].items():
        if "per_query_whole_pool" in e:
            out[b] = {"size": e["per_query_whole_pool"], "cut": e.get("per_query_cut_binds")}
    return out


def compare(old: dict, new: dict) -> list[dict]:
    old_by_key = {c["key"]: c for c in old["conditions"]}
    rows = []
    for c in new["conditions"]:
        co = old_by_key.get(c["key"])
        if co is None:
            continue
        so, sn = series(co), series(c)
        k = c["k"]
        for name, s in sn.items():
            base = name.split(":")[0]
            ref = so.get(base)
            if ref is None or len(ref["size"]) != len(s["size"]):
                continue
            a = np.asarray(s["size"], dtype=float)
            b = np.asarray(ref["size"], dtype=float)
            row = {"key": c["key"], "label": c["label"], "k": k, "new": name, "old": base,
                   "n": int(len(a)), "mean_old": float(b.mean()), "mean_new": float(a.mean()),
                   "queries_changed": int(np.sum(a != b)),
                   "above_k_old": int(np.sum(b > k)), "above_k_new": int(np.sum(a > k)),
                   "size": paired_summary(a, b),
                   "above_k_mcnemar": mcnemar_summary((a > k).astype(int), (b > k).astype(int))}
            if s["cut"] is not None and ref["cut"] is not None:
                ca = np.asarray(s["cut"], dtype=int)
                cb = np.asarray(ref["cut"], dtype=int)
                row["cut_old"] = int(cb.sum())
                row["cut_new"] = int(ca.sum())
                row["cut_mcnemar"] = mcnemar_summary(ca, cb)
            rows.append(row)
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--old", type=Path, required=True)
    p.add_argument("--new", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--log-file", type=Path, required=True)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    for path in (args.output, args.log_file):
        if path.exists() and not args.overwrite:
            sys.exit(f"{path} exists. Pass --overwrite or choose another path.")
    old = json.loads(args.old.read_text())
    new = json.loads(args.new.read_text())
    log = args.log_file.open("w", encoding="utf-8")
    stdout = sys.stdout
    sys.stdout = Tee(stdout, log)
    try:
        print(f"old: {args.old.name}  BEAR {old.get('bear_version')} {old.get('bear_source_sha')}  "
              f"backends {old.get('backends')}")
        print(f"new: {args.new.name}  BEAR {new.get('bear_version')} {new.get('bear_source_sha')}  "
              f"backends {new.get('backends')}")
        rows = compare(old, new)
        print("\nAdmissible-set size (trace, whole pool; metadata rows backend-free), new minus old.")
        print("Delta: paired bootstrap 95% CI, paired Cohen's d. Changed: queries whose size differs.")
        print(f"\n{'condition':<26} {'new':<20} {'vs':<9} {'n':>6} {'old mean':>9} {'new mean':>9} "
              f"{'changed':>8}  {'delta [95% CI]':<28} {'d':>7} {'Wilcoxon p':>11}  "
              f"{'|A|>k old/new':>14} {'McNemar p':>9}")
        for r in rows:
            s = r["size"]
            d = s["cohens_d_paired"]
            w = s["wilcoxon"]["p"]
            m = r["above_k_mcnemar"]
            delta = f"{s['delta']:+8.2f} [{s['ci'][0]:+.2f}, {s['ci'][1]:+.2f}]"
            print(f"{r['key']:<26} {r['new']:<20} {r['old']:<9} {r['n']:>6} {r['mean_old']:>9.2f} "
                  f"{r['mean_new']:>9.2f} {r['queries_changed']:>8}  {delta:<28}"
                  f" {'n/a' if d is None else format(d, '+.2f'):>7} "
                  f"{'n/a' if w is None else format(w, '.1e'):>11}  "
                  f"{r['above_k_old']:>6}/{r['above_k_new']:<7} {m['p_value']:>9.3g}")
        cut_rows = [r for r in rows if "cut_mcnemar" in r and r["cut_old"] != r["cut_new"]]
        if cut_rows:
            print("\nCut binds (top-k removed >= 1 item, default pool), where the count changed:")
            for r in cut_rows:
                m = r["cut_mcnemar"]
                print(f"  {r['key']:<26} {r['new']:<20} {r['cut_old']}/{r['n']} -> {r['cut_new']}/{r['n']}  "
                      f"McNemar {m['b_a_right_b_wrong']}/{m['c_a_wrong_b_right']} p={m['p_value']:.3g}")
        args.output.write_text(json.dumps({"old": str(args.old), "new": str(args.new),
                                           "old_bear": [old.get("bear_version"), old.get("bear_source_sha")],
                                           "new_bear": [new.get("bear_version"), new.get("bear_source_sha")],
                                           "rows": rows}, indent=1, default=float))
        print(f"\nWrote {args.output}")
    finally:
        sys.stdout = stdout
        log.close()


if __name__ == "__main__":
    main()
