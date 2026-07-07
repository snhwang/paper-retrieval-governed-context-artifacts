#!/usr/bin/env python3
"""Does governance's advantage compound with task complexity? (Tier 0)

Compounding hypothesis: a multi-tool task succeeds only if *all* its required
tools are retrieved, so per-tool recall gains multiply. Prediction at the
retrieval level: the governed advantage in FULL-COVERAGE RATE (every
ground-truth tool present in the top-k) grows as the number of ground-truth
tools per query grows.

This tests that deterministically on ToolBench, with no LLM and no agent loop.
Full-coverage rate is computed for governed (scope gate + oracle category tags)
vs ungoverned (pure similarity) retrieval, bucketed by ground-truth tool count
|GT| in {1, 2, 3+}. A gap that grows with |GT| supports the mechanism; a flat
gap falsifies it.

Run from the repo root (GPU env recommended):
    python evals/eval_compounding_coverage.py --backends bge qwen3-0.6b
"""
import argparse
import collections
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

from eval_toolbench import (  # noqa: E402
    load_toolbench_corpus_and_queries,
    build_retriever,
    strip_governance,
)
from repro_footer import print_repro_footer  # noqa: E402
from bear.models import Context  # noqa: E402


def bucket(n):
    return "1" if n == 1 else ("2" if n == 2 else "3+")


def coverage(retriever, queries, use_tags, k):
    """Per query: (|GT| bucket, 1.0 if all GT in top-k else 0.0, per-tool recall)."""
    out = []
    for q in queries:
        qtext, tags, gt = q[0], q[1], set(q[2])
        ctx = Context(tags=tags if use_tags else [])
        got = {r.id for r in retriever.retrieve(qtext, ctx, top_k=k)}
        full = 1.0 if gt <= got else 0.0
        rec = len(gt & got) / len(gt) if gt else 0.0
        out.append((bucket(len(gt)), full, rec))
    return out


def aggregate(rows):
    agg = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for b, full, rec in rows:
        agg[b][0] += 1
        agg[b][1] += full
        agg[b][2] += rec
    return {b: {"n": agg[b][0], "full_coverage": agg[b][1] / agg[b][0],
                "recall": agg[b][2] / agg[b][0]} for b in agg}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backends", nargs="+", default=["bge"])
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--output", default=str(REPO_ROOT / "results" / "compounding_coverage.json"))
    args = ap.parse_args()

    corpus, queries, _ = load_toolbench_corpus_and_queries()
    corpus_ng = strip_governance(corpus)
    print(f"ToolBench: {len(list(corpus))} APIs, {len(queries)} queries, k={args.top_k}\n")

    out = {"top_k": args.top_k, "n_queries": len(queries), "backends": {}}
    for bk in args.backends:
        gov = aggregate(coverage(build_retriever(corpus, backend=bk, governance=True),
                                 queries, use_tags=True, k=args.top_k))
        nog = aggregate(coverage(build_retriever(corpus_ng, backend=bk, governance=False),
                                 queries, use_tags=False, k=args.top_k))
        out["backends"][bk] = {"governed": gov, "ungoverned": nog}
        print(f"=== {bk}: full-coverage rate (all GT in top-{args.top_k}) ===")
        print(f"  {'|GT|':>5} {'n':>5} {'governed':>10} {'ungoverned':>11} {'gap':>7}")
        for b in ["1", "2", "3+"]:
            if b in gov:
                g, u = gov[b]["full_coverage"], nog[b]["full_coverage"]
                print(f"  {b:>5} {gov[b]['n']:>5} {g:>10.3f} {u:>11.3f} {g - u:>+7.3f}")
        print()

    print("Compounding holds if the governed-minus-ungoverned gap grows from "
          "|GT|=1 to 2 to 3+.")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Saved to {out_path}")
    print_repro_footer()


if __name__ == "__main__":
    main()
