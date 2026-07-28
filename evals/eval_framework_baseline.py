#!/usr/bin/env python3
"""Production-framework baseline: LlamaIndex tool retrieval vs BEAR.

Reviewers 1 and 2 asked how BEAR compares against production agent frameworks.
The candidate-selection mechanism those frameworks ship (LlamaIndex
ObjectIndex/VectorStoreIndex tool retrieval, LangChain vector-store tool
selection) is embedding similarity top-k over tool/instruction descriptions.
The paper's ungoverned baseline rows implement the same mechanism, so the
letter argues they already represent framework practice. This script measures
that claim instead of asserting it: it runs the actual released package
(llama-index-core VectorStoreIndex retriever) over the same corpora, with the
same BGE-base embedding model, and scores it with the same metrics.

Expected outcome: the LlamaIndex row lands within noise of the paper's
ungoverned BEAR row (same mechanism, different implementation), and the
governed row exceeds both. Divergence would mean the framework's
implementation details (chunking, prefixing, normalization) matter and the
ungoverned rows under- or over-represent framework practice.

Arms:
    llamaindex   VectorStoreIndex.as_retriever(similarity_top_k=k), the
                 framework's released retrieval path, default settings apart
                 from the embedding model, which is pinned to BGE-base so the
                 comparison isolates the pipeline rather than the encoder
    bear_nogov   BEAR, governance off (the paper's published baseline row)
    bear_gov     BEAR, governance on  (the paper's published governed row)

Corpora:
    petsim     60 standard queries, k=10, strict F1 primary (+ relaxed F1)
    toolbench  1,100 queries, k=5, Recall@5 primary

Usage (from the repo root, inside the project venv):
    python evals/eval_framework_baseline.py --corpus petsim
    python evals/eval_framework_baseline.py --corpus toolbench

Requires llama-index-core and llama-index-embeddings-huggingface (installed
into the project venv; pinned in requirements.txt). Runtime is minutes for
Pet Sim; ToolBench is dominated by embedding 3,225 items three times and takes
roughly 10-20 minutes on GPU. Per-query score arrays are written to the output
JSON so statistics can be recomputed without re-running.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[1]
evals_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(evals_dir))

from eval_toolbench import (  # noqa: E402
    recall_at_k,
    precision_at_k,
    f1_at_k,
    ndcg_at_k,
)
from eval_reranker_composition import (  # noqa: E402
    CORPUS_SETTINGS,
    load_corpus,
    relaxed_expected,
    document_texts,
    build_retriever,
)
from bear import Context  # noqa: E402
from stat_utils import bootstrap_ci, paired_bootstrap  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

BI_ENCODER = "BAAI/bge-base-en-v1.5"
BI_ENCODER_QUERY_PREFIX = "Represent this sentence for retrieving relevant documents: "
BOOTSTRAP_ITERS = 10_000

ARMS = ["llamaindex", "bear_nogov", "bear_gov"]
ARM_LABELS = {
    "llamaindex": "LlamaIndex retriever (released package)",
    "bear_nogov": "BEAR, no governance (published baseline)",
    "bear_gov": "BEAR governed (published row)",
}

CONTRASTS = [
    ("bear_nogov", "llamaindex", "same mechanism, different implementation"),
    ("bear_gov", "llamaindex", "governance vs the framework's retrieval"),
]


def build_llamaindex_retriever(corpus, k: int):
    """The released LlamaIndex retrieval path over the same instruction text.

    VectorStoreIndex over one TextNode per instruction, retrieved with
    as_retriever(similarity_top_k=k). This is the mechanism behind LlamaIndex's
    ObjectIndex tool retrieval (ObjectIndex wraps exactly this index type and
    retriever). The embedding model is pinned to the paper's default backend so
    any difference from the BEAR arms is the framework pipeline, not the encoder.
    """
    from llama_index.core import VectorStoreIndex
    from llama_index.core.schema import TextNode
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    embed_model = HuggingFaceEmbedding(
        model_name=BI_ENCODER,
        query_instruction=BI_ENCODER_QUERY_PREFIX,
        text_instruction="",
    )
    nodes = [TextNode(text=inst.content, id_=inst.id) for inst in corpus]
    index = VectorStoreIndex(nodes=nodes, embed_model=embed_model, show_progress=True)
    return index.as_retriever(similarity_top_k=k)


def score(retrieved_ordered, expected, k, expected_rel):
    got = set(retrieved_ordered[:k])
    out = {
        "recall": recall_at_k(got, expected, k),
        "precision": precision_at_k(got, expected, k),
        "f1": f1_at_k(got, expected, k),
        "ndcg": ndcg_at_k(retrieved_ordered[:k], expected, k),
    }
    if expected_rel is not None:
        out["recall_relaxed"] = recall_at_k(got, expected_rel, k)
        out["f1_relaxed"] = f1_at_k(got, expected_rel, k)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", choices=["petsim", "toolbench"], default="petsim")
    ap.add_argument("--max-queries", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    settings = CORPUS_SETTINGS[args.corpus]
    k = settings["top_k"]
    corpus, queries = load_corpus(args.corpus, args.max_queries)

    print(f"\n=== Framework baseline (LlamaIndex) vs BEAR: {args.corpus} ===\n")
    print(f"corpus   {len(corpus)} items")
    print(f"queries  {len(queries)}")
    print(f"encoder  {BI_ENCODER} (pinned in all arms), k={k}\n")

    print("Building LlamaIndex VectorStoreIndex...")
    t0 = time.time()
    li_retriever = build_llamaindex_retriever(corpus, k)
    print(f"  built in {time.time() - t0:.0f}s")

    print("Building BEAR retrievers...")
    t0 = time.time()
    r_gov = build_retriever(corpus, settings, governed=True)
    r_plain = build_retriever(corpus, settings, governed=False)
    print(f"  built in {time.time() - t0:.0f}s\n")

    metrics = ["recall", "precision", "f1", "ndcg"]
    if args.corpus == "petsim":
        metrics += ["recall_relaxed", "f1_relaxed"]
    scores = {arm: {m: [] for m in metrics} for arm in ARMS}

    t0 = time.time()
    for i, (query_text, tags, expected) in enumerate(queries):
        if i and i % 100 == 0:
            print(f"  {i}/{len(queries)} queries ({i / (time.time() - t0):.1f}/s)")
        expected_rel = relaxed_expected(args.corpus, query_text, expected)

        li_nodes = li_retriever.retrieve(query_text)
        li_ids = [n.node.node_id for n in li_nodes]
        for m, v in score(li_ids, expected, k, expected_rel).items():
            scores["llamaindex"][m].append(v)

        # bear_nogov mirrors the published ungoverned convention per corpus
        # (see CORPUS_SETTINGS.ungoverned_use_tags in eval_reranker_composition).
        for arm, retriever, use_tags in (
                ("bear_nogov", r_plain, settings["ungoverned_use_tags"]),
                ("bear_gov", r_gov, True)):
            ctx = Context(tags=list(tags) if use_tags else [])
            res = retriever.retrieve(query_text, ctx, top_k=k)
            for m, v in score([r.id for r in res], expected, k, expected_rel).items():
                scores[arm][m].append(v)

    elapsed = time.time() - t0
    print(f"  {len(queries)}/{len(queries)} queries in {elapsed:.0f}s\n")
    scores = {arm: {m: np.array(v) for m, v in d.items()} for arm, d in scores.items()}
    primary = settings["primary"]
    has_relaxed = "f1_relaxed" in metrics

    out = {
        "corpus": args.corpus,
        "n_items": len(corpus),
        "n_queries": len(queries),
        "top_k": k,
        "encoder": BI_ENCODER,
        "primary_metric": primary,
        "elapsed_s": elapsed,
        "arms": {},
        "contrasts": {},
        "per_query": {},
    }

    print(f"--- Arms ({settings['primary_label']}, n={len(queries)}) ---\n")
    for arm in ARMS:
        out["arms"][arm] = {"label": ARM_LABELS[arm], "metrics": {}}
        for m in metrics:
            ci = bootstrap_ci(scores[arm][m], BOOTSTRAP_ITERS)
            out["arms"][arm]["metrics"][m] = {
                "mean": float(ci["point_estimate"]),
                "ci": [float(ci["ci_lower"]), float(ci["ci_upper"])],
            }
        p = out["arms"][arm]["metrics"][primary]
        line = f"  {ARM_LABELS[arm]:42s} {p['mean']:.3f} [{p['ci'][0]:.3f}, {p['ci'][1]:.3f}]"
        if has_relaxed:
            rel = out["arms"][arm]["metrics"]["f1_relaxed"]
            line += f"   relaxed {rel['mean']:.3f} [{rel['ci'][0]:.3f}, {rel['ci'][1]:.3f}]"
        print(line)
        out["per_query"][arm] = {m: scores[arm][m].tolist() for m in metrics}

    def d_paired(a, b):
        diff = a - b
        return 0.0 if diff.std(ddof=1) == 0 else float(diff.mean() / diff.std(ddof=1))

    contrast_metrics = [(primary, settings["primary_label"])]
    if has_relaxed:
        contrast_metrics.append(("f1_relaxed", "relaxed F1@10"))
    for metric, metric_label in contrast_metrics:
        print(f"\n--- Contrasts (paired bootstrap, {metric_label}) ---\n")
        for a, b, question in CONTRASTS:
            pb = paired_bootstrap(scores[a][metric], scores[b][metric], BOOTSTRAP_ITERS)
            d = d_paired(scores[a][metric], scores[b][metric])
            key = f"{a}_vs_{b}" if metric == primary else f"{a}_vs_{b}__{metric}"
            out["contrasts"][key] = {
                "metric": metric, "question": question, "delta": pb["delta"],
                "ci": [pb["ci_lower"], pb["ci_upper"]], "p_value": pb["p_value"],
                "cohens_d_paired": d, "n": pb["n"],
            }
            sig = "*" if pb["p_value"] < 0.05 else " "
            print(f"  {a:10s} - {b:10s} {pb['delta']:+.3f} "
                  f"[{pb['ci_lower']:+.3f}, {pb['ci_upper']:+.3f}] "
                  f"p={pb['p_value']:.4f}{sig} d={d:+.2f}   {question}")

    out_path = Path(args.output) if args.output else (
        project_root / "results" / f"framework_baseline_{args.corpus}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")

    print("\nRead: if 'bear_nogov vs llamaindex' is within noise, the paper's")
    print("ungoverned rows faithfully represent what production frameworks ship,")
    print("and the governed contrast carries over to them unchanged.")
    print_repro_footer(extra={"corpus": args.corpus, "queries": len(queries)})


if __name__ == "__main__":
    main()
