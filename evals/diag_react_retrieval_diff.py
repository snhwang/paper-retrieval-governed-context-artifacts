#!/usr/bin/env python3
"""ReAct retrieval-diff: does the BEAR 0.1.10 over-fetch fix change the tools
the ReAct agent would see?

The ToolBench ReAct experiment (Table 5) feeds the agent the top-k tools that
BEAR retrieves per query (bge backend, governance on, ground-truth category
tags). If the fix does not change that top-k set for any query, the (expensive,
vLLM) ReAct table is provably unaffected and needs no re-run. This script
compares the fixed 0.1.10 retrieval against the old top_k*3 over-fetch behavior
(reproduced by disabling the widen-when-gated flag) for every ReAct query.
Embedding-only; no LLM / vLLM required.

Run from the repo root:
    python evals/diag_react_retrieval_diff.py --top-k 5
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

from eval_toolbench_e2e import build_retriever, load_toolbench_data, DEFAULT_TOP_K  # noqa: E402
from bear import Context  # noqa: E402


def topk_ids(retr, qtext, ctx_tags, top_k):
    ctx = Context(tags=list(ctx_tags) if ctx_tags else [])
    return [r.id for r in retr.retrieve(qtext, ctx, top_k=top_k)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--backend", default="bge",
                    help="Must match the ReAct deployment backend (bge).")
    args = ap.parse_args()

    corpus, queries = load_toolbench_data()
    print(f"corpus {len(corpus)} APIs, {len(queries)} queries, "
          f"k={args.top_k}, backend={args.backend}")
    retr = build_retriever(corpus, backend=args.backend, governance=True)

    n = changed = 0
    jac_sum = 0.0
    gold_new = gold_old = gold_total = 0
    examples = []
    for q in queries:
        qtext, ctx_tags, expected = q[0], q[1], set(q[2])
        retr._has_required_tags = True            # fixed 0.1.10 path (widened)
        new = set(topk_ids(retr, qtext, ctx_tags, args.top_k))
        retr._has_required_tags = False           # old top_k*3 over-fetch path
        old = set(topk_ids(retr, qtext, ctx_tags, args.top_k))
        retr._has_required_tags = True
        n += 1
        jac_sum += len(new & old) / (len(new | old) or 1)
        if new != old:
            changed += 1
            if len(examples) < 10:
                examples.append((qtext[:70], sorted(old - new), sorted(new - old)))
        gold_total += len(expected)
        gold_new += len(new & expected)
        gold_old += len(old & expected)

    print(f"\nqueries:                              {n}")
    print(f"queries whose top-{args.top_k} tool set CHANGED:   "
          f"{changed} ({100 * changed / n:.1f}%)")
    print(f"mean Jaccard(new, old) over top-{args.top_k}:      {jac_sum / n:.4f}")
    print(f"gold-in-top-{args.top_k} (recall proxy):           "
          f"old={gold_old / gold_total:.4f}  new={gold_new / gold_total:.4f}")

    if changed == 0:
        print("\nVERDICT: identical tool sets for every query -> the ReAct "
              "table is UNAFFECTED; no vLLM re-run needed.")
    else:
        direction = ("improved" if gold_new > gold_old
                     else "unchanged" if gold_new == gold_old else "DECREASED")
        print(f"\nVERDICT: {changed} queries change their tool set; gold "
              f"coverage {direction}. If the change is small and gold coverage "
              f"did not decrease, the end-to-end ReAct metric is very unlikely "
              f"to move; inspect the samples below before deciding on a re-run.")
        print("\nSample changes (query | dropped | added):")
        for qt, dropped, added in examples:
            print(f"  {qt!r}\n     - {dropped}\n     + {added}")

    try:
        from repro_footer import print_repro_footer
        print_repro_footer()
    except Exception:
        pass


if __name__ == "__main__":
    main()
