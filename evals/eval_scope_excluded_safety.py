#!/usr/bin/env python3
"""Scope-excluded safety subset: measure the mandatory-injection guarantee.

The decomposed ablation's adversarial subset showed mandatory ON and OFF both at
recall 1.000, because Pet Sim's three safety constraints have an EMPTY scope and
therefore match every context: with mandatory injection off they are still
admitted through the soft path and ranked in by priority. That subset therefore
does not isolate mandatory injection.

This script constructs the scope-EXCLUDED variant the manuscript describes: the
three safety-tagged constraints are given a required tag (``safety_review``)
that none of the 12 adversarial query contexts carries. Under the retriever's
admission semantics a gated instruction whose required tags are unsatisfied is
excluded regardless of similarity, so the only remaining path into the top-k is
mandatory injection, which bypasses the gate. Expected outcome: recall 1.000
with mandatory injection on, 0.000 with it off, on every backend. The point of
running rather than asserting it is that the table reports measured values.

Deterministic, CPU-only. Run from the repo root:
    python evals/eval_scope_excluded_safety.py --backends bge bge-m3 qwen3 qwen3-4b bm25
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
sys.path.insert(0, str(EVALS_DIR))

from bear import Context, Corpus  # noqa: E402
from bear.models import ScopeCondition  # noqa: E402
from eval_governance_decomposed import (  # noqa: E402
    ADVERSARIAL_SAFETY_QUERIES,
    TOP_K,
    _deepcopy_corpus,
    load_pet_sim_corpus,
    make_retriever,
)
from repro_footer import print_repro_footer  # noqa: E402

EXCLUSION_TAG = "safety_review"  # carried by no adversarial query context


def scope_exclude_safety(corpus: Corpus) -> tuple[Corpus, list[str]]:
    """Return a corpus variant whose safety instructions are hard scope-excluded.

    Every instruction whose tags include 'safety' gets
    scope.required_tags=[EXCLUSION_TAG]. No adversarial context carries that
    tag, so the gate excludes them and similarity cannot override it.
    """
    out = Corpus()
    safety_ids: list[str] = []
    for inst in corpus:
        ic = inst.model_copy(deep=True)
        if "safety" in (set(ic.tags) | set(ic.scope.tags)):
            ic.scope = ScopeCondition(
                tags=ic.scope.tags,
                required_tags=[EXCLUSION_TAG],
                user_roles=ic.scope.user_roles,
                domains=ic.scope.domains,
                task_types=ic.scope.task_types,
                trigger_patterns=ic.scope.trigger_patterns,
                session_phase=ic.scope.session_phase,
            )
            safety_ids.append(ic.id)
        out.add(ic)
    return out, safety_ids


def recall_over_queries(retriever, safety_ids: list[str]) -> tuple[float, list[float]]:
    per_query: list[float] = []
    for q, tags, _expected in ADVERSARIAL_SAFETY_QUERIES:
        result = retriever.retrieve(q, Context(tags=tags), top_k=TOP_K)
        got = {s.instruction.id for s in result}
        hit = sum(1 for sid in safety_ids if sid in got)
        per_query.append(hit / len(safety_ids))
    return sum(per_query) / len(per_query), per_query


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--backends", nargs="+",
                   default=["bge", "bge-m3", "qwen3", "qwen3-4b", "bm25"])
    p.add_argument("--out", type=Path,
                   default=REPO_ROOT / "results" / "scope_excluded_safety.json")
    args = p.parse_args()

    base = load_pet_sim_corpus()
    variant, safety_ids = scope_exclude_safety(base)
    print(f"Corpus: {sum(1 for _ in base)} instructions; "
          f"scope-excluded safety ids: {safety_ids}")
    print(f"Queries: {len(ADVERSARIAL_SAFETY_QUERIES)} adversarial, k={TOP_K}, "
          f"exclusion tag: {EXCLUSION_TAG!r}\n")

    results: dict[str, dict] = {}
    for bk in args.backends:
        corp = _deepcopy_corpus(variant)
        r_on = make_retriever(corp, bk)                      # mandatory ['safety']
        r_off = make_retriever(corp, bk, mandatory_tags=[])  # mandatory disabled
        on, per_on = recall_over_queries(r_on, safety_ids)
        off, per_off = recall_over_queries(r_off, safety_ids)
        results[bk] = {"mandatory_on_recall": on, "mandatory_off_recall": off,
                       "per_query_on": per_on, "per_query_off": per_off}
        print(f"  {bk:10s} mandatory ON recall = {on:.3f}   OFF recall = {off:.3f}")

    payload = {
        "n_queries": len(ADVERSARIAL_SAFETY_QUERIES),
        "top_k": TOP_K,
        "exclusion_tag": EXCLUSION_TAG,
        "safety_ids": safety_ids,
        "backends": results,
    }
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")
    print_repro_footer(extra={"eval": "scope_excluded_safety",
                              "backends": args.backends})


if __name__ == "__main__":
    main()
