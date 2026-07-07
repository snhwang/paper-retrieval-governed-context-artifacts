#!/usr/bin/env python3
"""Is the 0.1.10 fix worse retrieval on Pet Sim, or a metric artifact?

The fix lowered Pet-Sim governed F1 (~0.78 -> ~0.65) while it RAISED the external
benchmarks. This script tests whether that drop is a genuine quality loss or an
artifact of Pet-Sim's circular, tag-defined strict ground truth.

Two lenses, per backend:

1. Strict vs relaxed F1 for three conditions:
     - governance post-fix (0.1.10, widened over-fetch)
     - governance pre-fix  (old narrow top_k*3 over-fetch, reproduced by toggling
                            the widen-when-gated flag off -> the flat-injection path)
     - pure similarity     (no gate, no priority)
   If the drop is a circular-strict-metric artifact, then (a) governance still
   beats pure similarity on BOTH metrics, and (b) the pre->post drop is smaller
   under the relaxed metric than under the strict one.

2. What the fix actually drops: for each query, compare the pre-fix top-k with
   the post-fix top-k and inspect the items pre-fix surfaced that post-fix does
   not. Their REAL similarity and priority (looked up from the post-fix full
   ranking) reveal whether they were high-priority, low-similarity filler that
   the flat-injection promoted -- i.e. the fix removing filler, not signal.

Pet Sim corpus, no LLM, deterministic. Run from the repo root:
    python evals/eval_petsim_fix_diagnosis.py --backends bge bge-m3 qwen3 qwen3-4b bm25
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

from eval_retrieval import TEST_QUERIES, RELAXED_EXTRAS, compute_metrics  # noqa: E402
from eval_toolbench import strip_governance  # noqa: E402
from eval_governance_decomposed import (  # noqa: E402
    DEFAULT_BACKENDS,
    TOP_K,
    load_pet_sim_corpus,
    make_retriever,
)
from repro_footer import print_repro_footer  # noqa: E402
from bear.models import Context  # noqa: E402


def topk_ids(retriever, qtext, tags, k, old_behavior):
    """Top-k instruction ids. old_behavior=True reproduces the pre-fix narrow
    over-fetch (flat-injection path); False is the fixed widened path."""
    retriever._has_required_tags = not old_behavior
    res = retriever.retrieve(qtext, Context(tags=tags), top_k=k)
    retriever._has_required_tags = True
    return {r.instruction.id for r in res}


def f1_for(retriever, k, old_behavior):
    strict, relaxed = [], []
    for qtext, tags, expected in TEST_QUERIES:
        got = topk_ids(retriever, qtext, tags, k, old_behavior)
        strict.append(compute_metrics(got, expected, k)[2])
        relaxed.append(compute_metrics(got, expected | RELAXED_EXTRAS.get(qtext, set()), k)[2])
    return float(np.mean(strict)), float(np.mean(relaxed))


def inspect(retriever, k):
    """Compare pre-fix vs post-fix top-k; bucket the difference with real sims."""
    buckets = {"dropped": [], "added": [], "kept": []}  # (similarity, priority)
    cls = {"in_strict_gt": 0, "in_relaxed_only": 0, "in_neither": 0}
    for qtext, tags, expected in TEST_QUERIES:
        relaxed = expected | RELAXED_EXTRAS.get(qtext, set())
        # Post-fix FULL admissible ranking -> real similarity + priority per id.
        retriever._has_required_tags = True
        full = retriever.retrieve(qtext, Context(tags=tags), top_k=10_000, threshold=0.0)
        sim = {r.instruction.id: (float(r.similarity), int(r.instruction.priority))
               for r in full}
        post = topk_ids(retriever, qtext, tags, k, old_behavior=False)
        pre = topk_ids(retriever, qtext, tags, k, old_behavior=True)
        for iid in (pre - post):
            buckets["dropped"].append(sim.get(iid, (0.0, 50)))
            if iid in expected:
                cls["in_strict_gt"] += 1
            elif iid in relaxed:
                cls["in_relaxed_only"] += 1
            else:
                cls["in_neither"] += 1
        for iid in (post - pre):
            buckets["added"].append(sim.get(iid, (0.0, 50)))
        for iid in (post & pre):
            buckets["kept"].append(sim.get(iid, (0.0, 50)))
    summary = {}
    for name, vals in buckets.items():
        if vals:
            sims = [s for s, _ in vals]
            pris = [p for _, p in vals]
            summary[name] = {"n": len(vals),
                             "mean_similarity": float(np.mean(sims)),
                             "mean_priority": float(np.mean(pris))}
        else:
            summary[name] = {"n": 0, "mean_similarity": None, "mean_priority": None}
    return summary, cls


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backends", nargs="+", default=["bge"],
                    help=f"Backends. Default bge. Options: {' '.join(DEFAULT_BACKENDS)}")
    ap.add_argument("--output", default=str(REPO_ROOT / "results" / "petsim_fix_diagnosis.json"))
    args = ap.parse_args()

    corpus = load_pet_sim_corpus()
    corpus_stripped = strip_governance(corpus)
    print(f"Pet Sim: {len(list(corpus))} instructions, {len(TEST_QUERIES)} queries, k={TOP_K}\n")

    out = {"corpus": "pet_sim", "k": TOP_K, "n_queries": len(TEST_QUERIES), "backends": {}}
    for bk in args.backends:
        gov = make_retriever(corpus, bk)                                   # full governance
        sim_only = make_retriever(corpus_stripped, bk, priority_weight=0.0,
                                  mandatory_tags=[])                        # pure similarity
        post_s, post_r = f1_for(gov, TOP_K, old_behavior=False)
        pre_s, pre_r = f1_for(gov, TOP_K, old_behavior=True)
        ps_s, ps_r = f1_for(sim_only, TOP_K, old_behavior=False)
        insp, cls = inspect(gov, TOP_K)

        out["backends"][bk] = {
            "f1": {
                "governance_postfix": {"strict": post_s, "relaxed": post_r},
                "governance_prefix":  {"strict": pre_s, "relaxed": pre_r},
                "pure_similarity":    {"strict": ps_s, "relaxed": ps_r},
            },
            "inspection": insp,
            "dropped_classification": cls,
        }

        print(f"=== {bk} ===")
        print(f"  {'condition':<22} {'strict F1':>10} {'relaxed F1':>11}")
        print(f"  {'governance (post-fix)':<22} {post_s:>10.4f} {post_r:>11.4f}")
        print(f"  {'governance (pre-fix)':<22} {pre_s:>10.4f} {pre_r:>11.4f}")
        print(f"  {'pure similarity':<22} {ps_s:>10.4f} {ps_r:>11.4f}")
        print(f"  strict drop pre->post: {pre_s - post_s:+.4f}   "
              f"relaxed drop pre->post: {pre_r - post_r:+.4f}")
        d, a, kp = insp["dropped"], insp["added"], insp["kept"]
        print(f"  items the fix DROPPED (pre-fix only): n={d['n']}, "
              f"mean sim={d['mean_similarity']}, mean priority={d['mean_priority']}")
        print(f"  items the fix ADDED   (post-fix only): n={a['n']}, "
              f"mean sim={a['mean_similarity']}, mean priority={a['mean_priority']}")
        print(f"  items KEPT by both:                    n={kp['n']}, "
              f"mean sim={kp['mean_similarity']}, mean priority={kp['mean_priority']}")
        print(f"  dropped items in strict GT / relaxed-only / neither: "
              f"{cls['in_strict_gt']} / {cls['in_relaxed_only']} / {cls['in_neither']}\n")

    print("How to read this:")
    print("  * If governance (post-fix) still beats pure similarity on BOTH strict")
    print("    and relaxed F1, the core claim survives.")
    print("  * If the pre->post drop is smaller under relaxed than strict, the drop")
    print("    is concentrated in the circular strict metric (an artifact).")
    print("  * If DROPPED items have LOW similarity and HIGH priority vs ADDED/KEPT,")
    print("    the fix removed high-priority low-similarity filler that the")
    print("    flat-injection had promoted -- more correct retrieval, not worse.")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")
    print_repro_footer()


if __name__ == "__main__":
    main()
