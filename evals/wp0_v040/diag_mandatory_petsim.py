"""Why Pet Sim F1 moves under the mandatory rules (BEAR 0.4.x vs 0.1.10).

Runs the governance-ablation configurations of eval_governance_ablation.py
(make_retriever, the same corpus, k=10, alpha 0.3, threshold 0.3) on the four
query sets, and records per query how many items come back, which of the
mandatory ("safety") rules are among them, and F1. Run once per BEAR version
(and once per legacy switch, WP0_BEAR_LEGACY). The default lexical backends
load no model. --backends bge bge-m3 qwen3 runs the dense ones (CPU lane).

Usage:
    python evals/wp0_v040/diag_mandatory_petsim.py --out results/wp0/diag_mandatory_<ver>.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from bear import Context, Corpus  # noqa: E402

import eval_governance_ablation as ga  # noqa: E402
from eval_retrieval import compute_metrics  # noqa: E402
import wp0_common  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--backends", nargs="+", default=["bm25", "hash"])
    args = ap.parse_args()
    corpus = Corpus.from_directory(str(ga.project_root / "pet_sim" / "instructions"))
    stripped = ga.strip_required_tags(corpus)
    safety = {i.id for i in corpus if "safety" in (i.tags or [])}
    levels = [("Full governance", corpus, ["safety"]), ("Mandatory only", stripped, ["safety"])]
    out = {"n_safety_instructions": len(safety), "safety_ids": sorted(safety), "k": ga.TOP_K,
           "legacy_switches": os.environ.get("WP0_BEAR_LEGACY", ""), "rows": {}}
    for level, corp, mand in levels:
        for qs_name, queries in ga.QUERY_SETS:
            for b in args.backends:
                r = ga.make_retriever(corp, b, mand)
                wp0_common.assert_not_hash(r, b)  # 0.1.10 falls back to hash quietly
                sizes, n_mand, f1s, rel_mand, present, qtext = [], [], [], [], [], []
                for q, tags, expected in queries:
                    res = r.retrieve(q, Context(tags=tags), top_k=ga.TOP_K)
                    ids = {x.id for x in res}
                    sizes.append(len(ids))
                    n_mand.append(len(ids & safety))
                    present.append(sorted(ids & safety))
                    qtext.append(q)
                    rel_mand.append(len(ids & safety & set(expected)))
                    f1s.append(compute_metrics(ids, expected, k=ga.TOP_K)[2])
                key = f"{level} / {qs_name} / {b}"
                out["rows"][key] = {
                    "mean_returned": float(np.mean(sizes)), "max_returned": int(np.max(sizes)),
                    "frac_over_k": float(np.mean(np.asarray(sizes) > ga.TOP_K)),
                    "mean_mandatory_returned": float(np.mean(n_mand)),
                    "mean_mandatory_relevant": float(np.mean(rel_mand)),
                    "mean_f1": float(np.mean(f1s)),
                    "per_query": {"query": qtext, "returned": sizes, "mandatory": n_mand,
                                  "safety_present": present, "f1": f1s},
                }
                print(f"{key:45s} returned {np.mean(sizes):5.2f} (max {np.max(sizes)}) "
                      f"mandatory {np.mean(n_mand):4.2f} F1 {np.mean(f1s):.3f}", flush=True)
    out["_provenance"] = wp0_common.provenance({"script": "evals/wp0_v040/diag_mandatory_petsim.py"})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
