#!/usr/bin/env python3
"""Out-of-domain transfer of a ToolBench-fine-tuned retriever.

ToolBench-IR (ToolLLM's retriever, ToolBench/ToolBench_IR_bert_based_uncased) is
fine-tuned on ToolBench's RapidAPI corpus, where it reaches Recall@5 = 0.847.
This script measures how it transfers to a corpus it was NOT optimized for --
MetaTool (OpenAI-plugin tools, a different text distribution) -- versus
off-the-shelf general-purpose encoders.

It isolates *retriever quality* (no governance, pure similarity), to test the
claim behind BEAR's positioning: fine-tuned retrievers are corpus-specific
(strong in-domain, weak out-of-domain, needing per-corpus retraining), whereas
off-the-shelf encoders + declarative governance generalize without training.

Run from the repo root (needs the ToolBench-IR model; downloaded on first use):
    # out-of-domain: the fine-tuned retriever on MetaTool
    python evals/eval_backend_transfer.py --corpus metatool

    # in-domain reference (should reproduce ~0.847)
    python evals/eval_backend_transfer.py --corpus toolbench

    # direct off-the-shelf comparison in the same run
    python evals/eval_backend_transfer.py --corpus metatool \
        --model BAAI/bge-base-en-v1.5 \
        --query-prefix "Represent this sentence for retrieving relevant documents: "
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

from eval_toolbench import (  # noqa: E402
    load_metatool_corpus,
    load_metatool_queries,
    load_toolbench_corpus_and_queries,
    strip_governance,
    evaluate_retriever,
)
from stat_utils import bootstrap_ci  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402
from bear import Config, Retriever  # noqa: E402
from bear.config import EmbeddingBackend  # noqa: E402

DEFAULT_MODEL = "ToolBench/ToolBench_IR_bert_based_uncased"

# Off-the-shelf, no-governance references (BEAR 0.1.10, Recall@5) for context.
REFERENCE = {
    "toolbench": {"BGE": 0.574, "BGE-M3": 0.601, "Qwen3-0.6B": 0.694, "Qwen3-4B": 0.681},
    "metatool":  {"BGE": 0.723, "BGE-M3": 0.728, "Qwen3-0.6B": 0.871, "Qwen3-4B": 0.906},
}


def build_plain_retriever(corpus, model, dim, query_prefix, top_k):
    """Pure-similarity retriever (no governance, no priority weighting)."""
    config = Config(
        embedding_model=model,
        embedding_backend=EmbeddingBackend.NUMPY,
        embedding_dim=dim,
        embedding_query_prefix=query_prefix,
        embedding_passage_prefix="",
        priority_weight=0.0,
        default_threshold=0.0,
        default_top_k=top_k,
        mandatory_tags=[],
    )
    r = Retriever(corpus, config=config)
    r.build_index()
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", choices=["metatool", "toolbench"], default="metatool")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dim", type=int, default=768)
    ap.add_argument("--query-prefix", default="")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--max-queries", type=int, default=None)
    args = ap.parse_args()

    if args.corpus == "metatool":
        corpus, _ = load_metatool_corpus()
        queries = load_metatool_queries(max_queries=args.max_queries)
        domain = "OUT-of-domain (ToolBench-IR was not trained on MetaTool)"
    else:
        corpus, queries, _cat = load_toolbench_corpus_and_queries(max_queries=args.max_queries)
        domain = "IN-domain (ToolBench-IR was fine-tuned on ToolBench)"

    corpus = strip_governance(corpus)  # pure similarity, no gate
    print(f"corpus={args.corpus}  {len(list(corpus))} items  {len(queries)} queries")
    print(f"model={args.model}  ({domain})")

    t0 = time.time()
    r = build_plain_retriever(corpus, args.model, args.dim, args.query_prefix, args.top_k)
    m = evaluate_retriever(r, queries, top_k=args.top_k, use_tags=False)
    print(f"indexed + evaluated in {time.time() - t0:.0f}s\n")

    print(f"=== {args.model} on {args.corpus} (no governance, k={args.top_k}) ===")
    for metric in ("recall", "ndcg", "f1"):
        ci = bootstrap_ci(m[metric], 10000)
        mean, lo, hi = ci["point_estimate"], ci["ci_lower"], ci["ci_upper"]
        print(f"  {metric.upper():8s} {mean:.3f} [{lo:.3f}, {hi:.3f}]")

    print(f"\nOff-the-shelf no-governance references on {args.corpus} (Recall@5, BEAR 0.1.10):")
    for name, val in REFERENCE[args.corpus].items():
        print(f"  {name:12s} {val:.3f}")
    print("\nRead: on ToolBench the fine-tuned retriever should dominate (~0.847);")
    print("on MetaTool, if it falls near or below the off-the-shelf encoders, that")
    print("is the generalization gap -- fine-tuning is corpus-specific.")
    print_repro_footer()


if __name__ == "__main__":
    main()
