"""ToolLLM retriever baseline on ToolBench (same split, same metric).

Reviewer 3 #5 / #7 asked for a fair, same-metric comparison against a
fine-tuned learned retriever. This script runs ToolLLM's publicly released
ToolBench retriever (a fine-tuned dense encoder) as a plain no-governance
backend on the *identical* ToolBench evaluation used elsewhere in the paper
(same corpus, same 1,100 queries, same Recall@5 / NDCG@5 / F1@5).

It reports ToolLLM's retriever alongside the numbers we already have:
  - BEAR + BGE (oracle categories)        Recall@5 = 0.679  (Table 3)
  - BEAR + BGE, no governance             Recall@5 = 0.574  (floor)
  - BEAR + BGE, LLM-inferred categories   Recall@5 = 0.335..0.502 (Table 4)

The point is a like-for-like learned-retriever reference point: ToolLLM is
fine-tuned on ToolBench data, BEAR+BGE is an off-the-shelf encoder with a
governance layer. No oracle category access is used here (pure embedding
retrieval), so it is directly comparable to the BEAR no-governance and
LLM-inferred-category rows rather than to the oracle row.

Usage:
    # default model is ToolBench's released IR encoder
    python eval_toolbench_toolllm.py
    python eval_toolbench_toolllm.py --model ToolBench/ToolBench_IR_bert_based_uncased
    python eval_toolbench_toolllm.py --max-queries 50   # quick smoke test
    python eval_toolbench_toolllm.py --top-k 5 --output results/toolbench_toolllm.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bear import Config, Context, Retriever, EmbeddingBackend
from bear.models import ScopeCondition
from stat_utils import bootstrap_ci
from eval_toolbench import (
    load_toolbench_corpus_and_queries,
    strip_governance,
    recall_at_k,
    precision_at_k,
    f1_at_k,
    ndcg_at_k,
)
from repro_footer import print_repro_footer

# ToolBench's released fine-tuned retriever (dense encoder). Override with
# --model if the identifier changes or a local path is preferred.
DEFAULT_MODEL = "ToolBench/ToolBench_IR_bert_based_uncased"
DEFAULT_TOP_K = 5
BOOTSTRAP_ITERS = 10_000


def build_retriever(corpus, model: str, top_k: int, governed: bool,
                    threshold: float = 0.15) -> Retriever:
    """Dense retriever with ToolBench-IR embeddings.

    governed=False: pure similarity (no priority weighting; corpus is scope-
    stripped by the caller so nothing is hard-gated).
    governed=True: BEAR governance on top of the same embeddings (required_tags
    hard gate from the corpus, priority weighting, similarity threshold). Set
    threshold=0.0 to isolate the scale-free hard gate from the similarity floor
    (raw-cosine scales differ across encoders, so a fixed floor is not
    comparable between BGE and ToolBench-IR).
    """
    config = Config(
        embedding_model=model,
        embedding_backend=EmbeddingBackend.NUMPY,
        embedding_dim=768,
        embedding_query_prefix="",
        embedding_passage_prefix="",
        priority_weight=0.3 if governed else 0.0,
        default_threshold=threshold if governed else 0.0,
        default_top_k=top_k,
        mandatory_tags=[],
    )
    r = Retriever(corpus, config=config)
    r.build_index()
    return r


def evaluate(retriever: Retriever, queries, top_k: int, use_tags: bool) -> dict[str, np.ndarray]:
    recalls, precisions, f1s, ndcgs = [], [], [], []
    for q in queries:
        query_text, tags, expected = q[0], q[1], q[2]
        ctx = Context(tags=tags if use_tags else [])
        results = retriever.retrieve(query_text, ctx, top_k=top_k)
        ordered = [r.id for r in results]
        s = set(ordered)
        recalls.append(recall_at_k(s, expected, top_k))
        precisions.append(precision_at_k(s, expected, top_k))
        f1s.append(f1_at_k(s, expected, top_k))
        ndcgs.append(ndcg_at_k(ordered, expected, top_k))
    return {
        "recall": np.array(recalls),
        "precision": np.array(precisions),
        "f1": np.array(f1s),
        "ndcg": np.array(ndcgs),
    }


def run_condition(label, corpus, queries, model, top_k, governed, threshold=0.15) -> dict:
    print(f"  building [{label}] and indexing ...")
    t0 = time.time()
    r = build_retriever(corpus, model, top_k, governed, threshold)
    m = evaluate(r, queries, top_k, use_tags=governed)
    res = {"label": label, "governance": governed, "metrics": {}}
    print(f"=== {label}  (n={len(queries)}, k={top_k}, {time.time()-t0:.0f}s) ===")
    for name in ("recall", "precision", "f1", "ndcg"):
        ci = bootstrap_ci(m[name], BOOTSTRAP_ITERS)
        mean, lo, hi = ci["point_estimate"], ci["ci_lower"], ci["ci_upper"]
        res["metrics"][name] = {"mean": float(mean), "ci": [float(lo), float(hi)],
                                "n": int(len(m[name]))}
        print(f"  {name.upper():10s} {mean:.3f} [{lo:.3f}, {hi:.3f}]")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="HF id or local path of the ToolLLM/ToolBench retriever.")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--max-queries", type=int, default=None,
                    help="Limit number of queries (smoke test).")
    ap.add_argument("--mode", choices=["both", "alone", "governed"], default="both",
                    help="Which conditions to run (default both).")
    ap.add_argument("--threshold", type=float, default=0.15,
                    help="Similarity floor for the governed condition. Set 0.0 "
                         "to isolate the scale-free required_tags hard gate.")
    ap.add_argument("--output", type=str, default=None)
    args = ap.parse_args()

    print("[1/2] Loading ToolBench corpus + queries ...")
    corpus, queries, _category_map = load_toolbench_corpus_and_queries()
    if args.max_queries:
        queries = queries[: args.max_queries]
    print(f"      corpus: {len(list(corpus))} APIs   queries: {len(queries)}")

    print(f"[2/2] Running ToolBench-IR conditions ({args.mode}) ...\n")
    conditions = []
    if args.mode in ("both", "alone"):
        # No governance: strip scope so nothing is hard-gated (matches the
        # paper's no-governance / embedding-only baseline construction).
        conditions.append(run_condition(
            "ToolBench-IR alone (no governance)",
            strip_governance(corpus), queries, args.model, args.top_k, governed=False))
    if args.mode in ("both", "governed"):
        # BEAR governance on top of ToolBench-IR embeddings. Query context tags
        # are the benchmark categories (oracle for the category dimension, same
        # caveat as all governed ToolBench rows).
        label = ("BEAR governance + ToolBench-IR (oracle categories"
                 + (", hard gate only)" if args.threshold == 0.0 else ")"))
        conditions.append(run_condition(
            label, corpus, queries, args.model, args.top_k, governed=True,
            threshold=args.threshold))

    print("\nReference points (from the manuscript, same split/metric):")
    print("  BEAR+BGE oracle categories   Recall@5 = 0.679")
    print("  BEAR+BGE no governance       Recall@5 = 0.574")
    print("  BEAR+BGE inferred (best)     Recall@5 = 0.502")

    out = {"model": args.model, "top_k": args.top_k, "n_queries": len(queries),
           "conditions": conditions}
    out_path = Path(args.output) if args.output else (
        project_root / "results" / "toolbench_toolllm.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")
    print_repro_footer()


if __name__ == "__main__":
    main()
