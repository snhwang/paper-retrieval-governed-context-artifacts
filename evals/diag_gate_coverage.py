#!/usr/bin/env python3
"""Diagnostic: does the required_tags hard gate exclude any ground-truth APIs?

The governed ToolBench-IR run loses 2.7pp recall vs the ungoverned run. If the
query's context tags cover every gold API's category, the gate can only remove
distractors (which cannot lower recall@k) -- so any drop must come from gold
APIs being gated out. This script quantifies that directly with set logic (no
model, no retrieval), telling us whether the drop is a real over-gating effect
or a construction artifact.

Run: python evals/diag_gate_coverage.py [--out counts.json]
--out also writes the counts as JSON (reproduce/ reads it for Section 5.3).
"""
import argparse
import json
from pathlib import Path

from eval_toolbench import load_toolbench_corpus_and_queries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None, help="also write the counts as JSON")
    args = ap.parse_args()
    corpus, queries, _category_map = load_toolbench_corpus_and_queries()
    # Authoritative gate tag per corpus item: its required_tags.
    id_req = {ic.id: set(ic.scope.required_tags or []) for ic in corpus}

    n_q = len(queries)
    tot_gold = 0
    q_with_drop = 0
    tot_drop = 0
    not_in_corpus = 0
    examples = []

    for q in queries:
        ctx = set(q[1])
        expected = q[2]
        tot_gold += len(expected)
        dropped = []
        for gid in expected:
            req = id_req.get(gid)
            if req is None:
                not_in_corpus += 1
                dropped.append((gid, "NOT_IN_CORPUS"))
            elif not req.issubset(ctx):
                dropped.append((gid, f"req={sorted(req)} not subset of ctx"))
        if dropped:
            q_with_drop += 1
            tot_drop += len(dropped)
            if len(examples) < 8:
                examples.append((sorted(ctx), dropped[:3]))

    print(f"queries: {n_q}   total gold APIs: {tot_gold}")
    print(f"queries with >=1 gold gated out: {q_with_drop} "
          f"({100*q_with_drop/n_q:.1f}%)")
    print(f"total gold gated out: {tot_drop} "
          f"({100*tot_drop/tot_gold:.2f}% of all gold)")
    print(f"  of which gold not present in corpus at all: {not_in_corpus}")
    if examples:
        print("\nExamples (context tags -> up to 3 gated-out gold):")
        for ctx, dropped in examples:
            print(f"  ctx={ctx}")
            for gid, why in dropped:
                print(f"      {gid}\n        {why}")
    else:
        print("\nNo gold APIs are gated out. The 2.7pp drop is NOT gold "
              "exclusion -- look to retrieval internals / scoring.")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "script": "evals/diag_gate_coverage.py", "queries": n_q, "total_gold_apis": tot_gold,
            "queries_with_gold_gated_out": q_with_drop, "gold_gated_out": tot_drop,
            "gold_not_in_corpus": not_in_corpus,
            "examples": [{"context_tags": c, "gated_out": [list(x) for x in d]} for c, d in examples]},
            indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
