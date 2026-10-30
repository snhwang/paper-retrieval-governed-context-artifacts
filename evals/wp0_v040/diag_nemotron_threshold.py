"""Does the 0.15 similarity threshold explain Nemotron's governed deficit on
base MetaTool? Reruns base MetaTool governed (eval_toolbench configuration,
Nemotron through the response cache, so no new requests) at the committed
threshold 0.15 and at 0, and counts queries that return fewer than k tools.

Usage: WP0_NEMO_CACHE=<sqlite> python evals/wp0_v040/diag_nemotron_threshold.py --out <json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from bear import Context  # noqa: E402

import eval_toolbench as et  # noqa: E402
import wp0_common  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    corpus, _ = et.load_metatool_corpus()
    queries = et.load_metatool_queries()
    res = {}
    sims = []
    for thr in (et.THRESHOLD, 0.0):
        r = wp0_common.nemotron_retriever(corpus, priority_weight=et.PRIORITY_WEIGHT, threshold=thr,
                                          top_k=et.DEFAULT_TOP_K)
        rec, n_ret = [], []
        for q, _tags, exp in queries:
            out = r.retrieve(q, Context(tags=[]), top_k=5)
            ids = [x.id for x in out]
            n_ret.append(len(ids))
            rec.append(et.recall_at_k(set(ids), exp, 5))
            if thr == 0.0 and len(sims) < 2000:
                sims.extend(float(x.similarity) for x in out[:1])
        res[f"threshold={thr}"] = {"recall@5": float(np.mean(rec)), "queries_fewer_than_5": int(np.sum(np.array(n_ret) < 5))}
        print(thr, res[f"threshold={thr}"], flush=True)
    res["top1_similarity_quantiles"] = {q: float(np.quantile(sims, q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}
    print(res["top1_similarity_quantiles"])
    res["_provenance"] = wp0_common.provenance({"script": "evals/wp0_v040/diag_nemotron_threshold.py"})
    Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
