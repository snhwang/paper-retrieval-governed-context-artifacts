#!/usr/bin/env python3
"""Demonstration: BEAR composing with mechanisms from the cited tool-selection
literature, through the composition layer (composition.py), with no changes to
BEAR core.

This is an ILLUSTRATION, not an evaluation. It runs a handful of ToolBench
queries through governed retrieval and shows how each post-stage reorders the
governed candidate set:

    governed          BEAR alone (gate + similarity + priority)
    + reranker        released cross-encoder (measured in the paper, Table 21)
    + outcome         OATS-inspired outcome reweighting; priors here are
                      derived from the OTHER benchmark queries' ground truth
                      (an item's prior = fraction of other queries whose
                      ground truth includes it), standing in for the
                      deployment success logs a real system would use
    + groups          Tool-to-Agent-inspired hierarchy grouping; sibling APIs
                      of a strongly matched parent tool surface together

The point being demonstrated: each mechanism operates on the governed
candidate set and cannot admit what the gate excluded, so these methods
compose with governance rather than replace it. Quantitative claims about
reranking live in eval_reranker_composition.py; no numbers here should be
quoted as results.

Usage (from the repo root, inside the project venv):
    python evals/demo_composition.py
    python evals/demo_composition.py --queries 5 --top-k 5
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
evals_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(evals_dir))

from bear import Context  # noqa: E402
from eval_reranker_composition import (  # noqa: E402
    CORPUS_SETTINGS,
    load_corpus,
    document_texts,
    build_retriever,
)
from composition import (  # noqa: E402
    ComposedRetriever,
    CrossEncoderReranker,
    OutcomeReweightStage,
    GroupBoostStage,
    toolbench_parent_tool,
)
from repro_footer import print_repro_footer  # noqa: E402


def outcome_priors(queries, exclude_index: int) -> dict[str, float]:
    """Illustrative success priors from the other queries' ground truth.

    counts[item] = number of OTHER queries whose expected set contains the
    item, normalized by the max count. A deployment would use real outcome
    logs; the ground truth of held-out queries plays that role here.
    """
    counts: dict[str, int] = defaultdict(int)
    for i, (_q, _t, expected) in enumerate(queries):
        if i == exclude_index:
            continue
        for item in expected:
            counts[item] += 1
    if not counts:
        return {}
    mx = max(counts.values())
    return {k: v / mx for k, v in counts.items()}


def show(label: str, ids: list[str], expected: set[str]) -> None:
    print(f"  {label}:")
    for rank, cid in enumerate(ids, 1):
        mark = "*" if cid in expected else " "
        print(f"    {rank}. [{mark}] {cid}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", type=int, default=3)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--overfetch", type=int, default=50)
    args = ap.parse_args()

    settings = CORPUS_SETTINGS["toolbench"]
    corpus, queries = load_corpus("toolbench", None)
    texts = document_texts(corpus)
    print(f"ToolBench: {len(corpus)} items, showing {args.queries} queries, "
          f"top-{args.top_k} of a governed top-{args.overfetch}")
    print("[*] marks items in the query's ground truth\n")

    retriever = build_retriever(corpus, settings, governed=True)
    reranker = CrossEncoderReranker()
    reranker.set_texts(texts)
    groups = GroupBoostStage(toolbench_parent_tool)

    for qi in range(args.queries):
        query_text, tags, expected = queries[qi]
        ctx = Context(tags=list(tags))
        outcome = OutcomeReweightStage(outcome_priors(queries, qi), weight=0.3)

        print(f"Query {qi + 1}: {query_text[:100]}...")
        base = ComposedRetriever(retriever, None, overfetch=args.overfetch)
        governed = base.retrieve_ids(query_text, ctx, top_k=args.top_k)
        candidates = base.candidate_ids(query_text, ctx)
        show("governed (BEAR alone)", governed, expected)
        for label, stage in (("+ reranker (cross-encoder)", reranker),
                             ("+ outcome (OATS-inspired)", outcome),
                             ("+ groups (Tool-to-Agent-inspired)", groups)):
            reordered = stage(query_text, candidates)[:args.top_k]
            show(label, reordered, expected)
        print()

    print("Every arm above draws from the same governed candidate set; the")
    print("stages reorder within it and cannot admit what the gate excluded.")
    print_repro_footer(extra={"demo": "composition", "queries": args.queries})


if __name__ == "__main__":
    main()
