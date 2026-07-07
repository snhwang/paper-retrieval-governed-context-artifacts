#!/usr/bin/env python3
"""Composite-score scale audit (Pet Simulation).

BEAR ranks retrieved items by

    score = (1 - a) * cosine + a * (priority / 100)

where cosine is raw (roughly [-1, 1]) and priority/100 is [0, 1]. On corpora
with VARYING priorities (Pet Sim: 20-100), mixing those two scales could let
priority influence ranking more than the nominal weight `a` implies. External
benchmarks are immune: all tool priorities are equal, so the score is monotonic
in cosine and any rescaling leaves the ranking identical.

This audit re-ranks each query's admissible set two ways and checks whether the
F1 results actually move:

    raw  : (1 - a) * cos           + a * (priority/100)   [current behavior]
    norm : (1 - a) * ((cos+1)/2)   + a * (priority/100)   [cosine rescaled to [0,1]]

Scores are recomputed EXTERNALLY from the raw similarities BEAR returns, so no
bear code is changed. If F1_raw == F1_norm and the reorder rate is ~0, the
concern is theoretical -- keep the raw composite and document the choice. If
they diverge, the priority weighting is doing more than intended and the
decomposed / alpha-sweep tables (the only ones with varying priorities) warrant
revisiting.

Pet Sim corpus, no LLM. Run from the repo root:
    python evals/eval_composite_scale_audit.py --backends bge bge-m3 qwen3 qwen3-4b bm25
"""
import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

from eval_retrieval import TEST_QUERIES  # noqa: E402
from eval_toolbench import f1_at_k  # noqa: E402
from eval_governance_decomposed import (  # noqa: E402
    DEFAULT_BACKENDS,
    TOP_K,
    load_pet_sim_corpus,
    make_retriever,
)
from repro_footer import print_repro_footer  # noqa: E402
from bear.models import Context  # noqa: E402

ALPHAS = [0.0, 0.1, 0.3, 0.5]  # 0.0 is a sanity anchor (raw == norm by construction)


def raw_score(sim, prio, a):
    return (1 - a) * sim + a * (prio / 100.0)


def norm_score(sim, prio, a):
    return (1 - a) * ((sim + 1.0) / 2.0) + a * (prio / 100.0)


def audit_backend(retriever, queries, top_k):
    """For each alpha, return (mean F1 raw, mean F1 norm, reorder fraction)."""
    # Cache each query's full admissible candidate set once (id, raw sim, priority).
    per_query = []
    for q in queries:
        qtext, tags, expected = q[0], q[1], set(q[2])
        # threshold=0 and a huge top_k return the entire admissible set (post-gate)
        # ranked arbitrarily; we re-rank ourselves.
        cand = retriever.retrieve(qtext, Context(tags=tags),
                                  top_k=10_000, threshold=0.0)
        items = [(c.instruction.id, float(c.similarity), int(c.instruction.priority))
                 for c in cand]
        per_query.append((items, expected))

    out = {}
    for a in ALPHAS:
        f1_raw, f1_norm, reordered = [], [], 0
        for items, expected in per_query:
            raw_top = {i for i, _, _ in sorted(
                items, key=lambda it: raw_score(it[1], it[2], a), reverse=True)[:top_k]}
            norm_top = {i for i, _, _ in sorted(
                items, key=lambda it: norm_score(it[1], it[2], a), reverse=True)[:top_k]}
            f1_raw.append(f1_at_k(raw_top, expected, top_k))
            f1_norm.append(f1_at_k(norm_top, expected, top_k))
            if raw_top != norm_top:
                reordered += 1
        out[a] = (float(np.mean(f1_raw)), float(np.mean(f1_norm)),
                  reordered / len(per_query))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backends", nargs="+", default=["bge"],
                    help=f"Backends to audit. Default bge. Options: {' '.join(DEFAULT_BACKENDS)}")
    args = ap.parse_args()

    corpus = load_pet_sim_corpus()
    prios = sorted({inst.priority for inst in corpus})
    print(f"Pet Sim: {len(list(corpus))} instructions, priorities present: {prios}")
    print(f"Queries: {len(TEST_QUERIES)} standard, k={TOP_K}\n")

    worst_default = 0.0   # at alpha=0.30, the decomposed ablation's operating point
    worst_any = 0.0       # across the whole swept range (alpha-sweep relevance)
    for bk in args.backends:
        r = make_retriever(corpus, bk, mandatory_tags=[])  # isolate the composite
        res = audit_backend(r, TEST_QUERIES, TOP_K)
        print(f"=== {bk} ===")
        print(f"  {'alpha':>5} {'F1 raw':>8} {'F1 norm':>8} {'delta':>8} {'reorder%':>9}")
        for a in ALPHAS:
            fr, fn, ro = res[a]
            worst_any = max(worst_any, abs(fr - fn))
            if abs(a - 0.30) < 1e-9:
                worst_default = max(worst_default, abs(fr - fn))
            print(f"  {a:>5.2f} {fr:>8.4f} {fn:>8.4f} {fr - fn:>+8.4f} {100 * ro:>8.1f}%")
        print()

    print(f"|F1 raw - F1 norm| at alpha=0.30 (decomposed default): {worst_default:.4f}")
    print(f"|F1 raw - F1 norm| worst across swept alphas:          {worst_any:.4f}\n")

    if worst_default < 0.005:
        print("DECOMPOSED (alpha=0.30): robust to cosine scaling -- the headline")
        print("ablation numbers do not depend on the raw-vs-normalized choice; no")
        print("change and no re-run needed there.")
    else:
        print("DECOMPOSED (alpha=0.30): sensitive -- revisit the ablation numbers.")

    print("\nALPHA SWEEP: normalizing cosine compresses its range, which shifts")
    print("what a given alpha *means* (it makes priority relatively more")
    print("influential at the same alpha). So the best-alpha COORDINATE can move")
    print("even when the achievable peak F1 is comparable. The substantive")
    print("plateau/tradeoff finding is scale-invariant; the specific alpha values")
    print("are a convention of the raw-cosine scale used throughout the paper.")
    print_repro_footer()


if __name__ == "__main__":
    main()
