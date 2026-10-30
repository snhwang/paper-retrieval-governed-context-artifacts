"""Which external-benchmark cells admit anything through the required-tags backfill.

BEAR 0.4.0's required-tags backfill (Retriever step 3.5) scores the items it
admits at p/100 instead of alpha * p/100. 0.4.1 fixes that. Only a cell with at
least one admission whose trace reason is "required_tags" can change under the
fix, so those cells are the ones to rerun on 0.4.1.

For each cell (benchmark x backend x condition) this runs
Retriever.retrieve_with_trace on every query, with the committed loaders and
eval_toolbench.build_retriever, and counts
  n_queries_backfill         queries with >= 1 "required_tags" admission
  n_queries_backfill_in_out  queries where such an item is in the returned top-k
  n_backfill_admissions      all such admissions
and checks on every query that the traced output equals retrieve()'s.

Conditions: governed and mandatory-only. Ungated ("no gov") runs strip every
scope, so no item has required_tags and the backfill cannot act.

Usage:
    python evals/wp0_v040/track_backfill.py --backends bm25 hash bge \
        --out results/wp0/backfill_tracking_external.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from bear import Context  # noqa: E402

import eval_toolbench as et  # noqa: E402
import wp0_common  # noqa: E402


def benchmarks(which: list[str]):
    if "toolbench" in which:
        c, q, _ = et.load_toolbench_corpus_and_queries()
        yield "ToolBench (Table 3)", c, q
    if "e2e" in which:
        import eval_toolbench_e2e as e2e
        c, q = e2e.load_toolbench_data()
        yield "ToolBench e2e corpus (Tables 7-9)", c, q
    if "metatool-tags" in which:
        f = et.METATOOL_DIR / "plugin_tags.json"
        c, _ = et.load_metatool_corpus_tagged(f)
        yield "MetaTool+Tags (Table 6)", c, et.load_metatool_queries_tagged(f)
    if "metatool-qt5" in which:
        f = et.METATOOL_DIR / "plugin_tags.json"
        c, _ = et.load_metatool_corpus_tagged(f)
        q = et.load_metatool_queries_from_query_tags(et.METATOOL_DIR / "query_tags_top5.json")
        yield "MetaTool+QueryTags-top5 (Table 6)", c, q


def track(r, queries, use_tags: bool, k: int = 5) -> dict:
    nq = nq_out = nadm = mismatch = 0
    for q in queries:
        ctx = Context(tags=list(q[1]) if use_tags else [])
        out, trace = r.retrieve_with_trace(q[0], ctx, top_k=k)
        ref = r.retrieve(q[0], ctx, top_k=k)
        if [x.id for x in out] != [x.id for x in ref]:
            mismatch += 1
        rt = {i for i, h in trace.admitted.items() if h == "required_tags"}
        if rt:
            nq += 1
            nadm += len(rt)
            if rt & {x.id for x in out}:
                nq_out += 1
    return {"n_queries": len(queries), "n_queries_backfill": nq,
            "n_queries_backfill_in_out": nq_out, "n_backfill_admissions": nadm,
            "trace_vs_retrieve_mismatches": mismatch}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backends", nargs="+", default=["bm25", "hash", "bge"])
    ap.add_argument("--benchmarks", nargs="+",
                    default=["toolbench", "e2e", "metatool-tags", "metatool-qt5"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = {}
    for bench, corpus, queries in benchmarks(args.benchmarks):
        for b in args.backends:
            for cond, use_tags in (("gov", True), ("mand-only", False)):
                if "e2e" in bench and cond != "gov":
                    continue
                t0 = time.time()
                r = et.build_retriever(corpus, backend=b, governance=True, mandatory_tags=[])
                wp0_common.assert_not_hash(r, b)
                rec = track(r, queries, use_tags)
                rec["elapsed_s"] = time.time() - t0
                res.setdefault(bench, {})[f"{b} ({cond})"] = rec
                print(f"{bench:36s} {b:5s} {cond:9s} backfill queries {rec['n_queries_backfill']:6d} "
                      f"in output {rec['n_queries_backfill_in_out']:6d} "
                      f"mismatch {rec['trace_vs_retrieve_mismatches']}", flush=True)
                r = None
    out = {"cells": res, "_provenance": wp0_common.provenance({"script": "evals/wp0_v040/track_backfill.py"})}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
