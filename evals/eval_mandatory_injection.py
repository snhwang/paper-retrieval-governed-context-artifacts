#!/usr/bin/env python3
"""Mandatory-injection guarantee: an isolated demonstration.

Motivation. In the decomposed ablation (eval_governance_decomposed.py) the
mandatory-injection pathway stopped showing an effect once BEAR 0.1.10 widened
the gated over-fetch to the whole corpus: on a 58-instruction corpus every
gate-eligible safety rule is now surfaced by ordinary ranking, so force-inclusion
is redundant *there*. That is a property of the small, gate-friendly test, not
of the mechanism. Mandatory injection is a guarantee, and a guarantee only shows
an effect when ordinary retrieval would otherwise MISS the instruction.

This script isolates exactly that case. It runs the adversarial-safety queries
(benign surface text, no safety vocabulary, context tags that never name the
safety scope) under two corpus variants:

  * unscoped  -- safety rules carry no required_tags (the original test). On a
                 small corpus ordinary retrieval reaches them, so mandatory
                 injection is redundant (OFF ~= ON).
  * scoped    -- safety rules carry a required_tags gate the queries never
                 provide, so the scope gate excludes them from retrieval
                 entirely. Only mandatory injection can surface them. This is
                 corpus-size-independent: no over-fetch width can admit a
                 gate-excluded instruction.

Expected: unscoped OFF is high (retrieval finds them); scoped OFF = 0
(retrieval cannot); ON = 1.0 in both (the guarantee holds regardless).

Pet Simulation corpus, no LLM, deterministic. Run from the repo root:
    python evals/eval_mandatory_injection.py --backends bge bge-m3 qwen3 qwen3-4b bm25
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

from bear.corpus import Corpus  # noqa: E402
from bear.models import Context, ScopeCondition  # noqa: E402
from eval_governance_decomposed import (  # noqa: E402
    ADVERSARIAL_SAFETY_QUERIES,
    DEFAULT_BACKENDS,
    TOP_K,
    discover_safety_ids,
    load_pet_sim_corpus,
    make_retriever,
)
from repro_footer import print_repro_footer  # noqa: E402

GATE_TAG = "restricted_compliance"  # a scope tag the adversarial queries never carry


def scope_exclude_safety(corpus: Corpus, safety_ids: set[str]) -> Corpus:
    """Copy of the corpus where each safety rule carries a required_tags gate
    that the adversarial queries do not provide, so the scope gate excludes it
    from retrieval. scope.tags (incl. 'safety') are preserved so mandatory
    injection still recognizes the rule."""
    out = Corpus()
    for inst in corpus:
        ic = inst.model_copy(deep=True)
        if inst.id in safety_ids:
            ic.scope = ScopeCondition(
                tags=inst.scope.tags,
                required_tags=[GATE_TAG],
                user_roles=inst.scope.user_roles,
                domains=inst.scope.domains,
                task_types=inst.scope.task_types,
                session_phase=inst.scope.session_phase,
                trigger_patterns=inst.scope.trigger_patterns,
            )
        out.add(ic)
    return out


def safety_recall(retriever, queries, safety_ids: set[str]) -> float:
    """Mean fraction of safety instructions present in the top-k across queries."""
    if not safety_ids:
        return 0.0
    hits = []
    for qtext, tags, _ in queries:
        got = {r.id for r in retriever.retrieve(qtext, Context(tags=tags), top_k=TOP_K)}
        hits.append(len(got & safety_ids) / len(safety_ids))
    return float(np.mean(hits))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backends", nargs="+", default=["bge"],
                    help=f"Embedding backends to run. Default bge. Options: {' '.join(DEFAULT_BACKENDS)}")
    ap.add_argument("--output", default=str(REPO_ROOT / "results" / "mandatory_injection.json"))
    args = ap.parse_args()

    corpus = load_pet_sim_corpus()
    safety_ids = discover_safety_ids(corpus)
    corpus_scoped = scope_exclude_safety(corpus, safety_ids)
    queries = ADVERSARIAL_SAFETY_QUERIES

    print(f"Pet Sim corpus: {len(list(corpus))} instructions, "
          f"{len(safety_ids)} safety-tagged: {sorted(safety_ids)}")
    print(f"Adversarial-safety queries: {len(queries)} (k={TOP_K})")
    print("Query context tags never include the safety scope, so ordinary "
          "retrieval must reach the rules on semantic similarity alone.\n")

    out = {"top_k": TOP_K, "n_queries": len(queries),
           "safety_ids": sorted(safety_ids), "backends": {}}

    hdr = f"{'backend':10} | {'unscoped OFF':>12} {'unscoped ON':>11} | {'scoped OFF':>10} {'scoped ON':>9}"
    print(hdr)
    print("-" * len(hdr))
    for bk in args.backends:
        r_uns_off = make_retriever(corpus, bk, mandatory_tags=[])
        r_uns_on = make_retriever(corpus, bk, mandatory_tags=["safety"])
        r_sco_off = make_retriever(corpus_scoped, bk, mandatory_tags=[])
        r_sco_on = make_retriever(corpus_scoped, bk, mandatory_tags=["safety"])
        uo = safety_recall(r_uns_off, queries, safety_ids)
        un = safety_recall(r_uns_on, queries, safety_ids)
        so = safety_recall(r_sco_off, queries, safety_ids)
        sn = safety_recall(r_sco_on, queries, safety_ids)
        print(f"{bk:10} | {uo:12.3f} {un:11.3f} | {so:10.3f} {sn:9.3f}")
        out["backends"][bk] = {
            "unscoped": {"mandatory_off": uo, "mandatory_on": un},
            "scoped": {"mandatory_off": so, "mandatory_on": sn},
        }

    print("\nReading:")
    print("  unscoped: small corpus + no scope gate -> retrieval already finds")
    print("            the safety rule, so mandatory injection is redundant here.")
    print("  scoped:   the scope gate excludes the safety rule from retrieval")
    print("            (OFF = 0.0 at any corpus size / over-fetch width); only")
    print("            mandatory injection surfaces it (ON = 1.0). This is the")
    print("            architectural guarantee in isolation.")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")
    print_repro_footer()


if __name__ == "__main__":
    main()
