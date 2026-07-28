#!/usr/bin/env python3
"""Head-to-head and composition against a production cross-encoder reranker.

Reviewers 1 and 2 asked for empirical comparison against modern tool-selection
and reranking methods. The reranking family (Tool-to-Agent Retrieval,
Agent-as-a-Graph, ToolReAGt, GRETEL, OATS) operates *downstream* of candidate-set
construction: it reorders an already-formed candidate set. BEAR governs how that
candidate set is *constructed*. The response letter argues from this that the
informative experiment is composition rather than substitution. This script
measures that argument instead of asserting it, using the strongest released,
production-ready stand-in for the family: the BGE cross-encoder reranker
(BAAI/bge-reranker-base), which is the reranker shipped by default in LlamaIndex
and LangChain retrieval stacks.

Four arms, first-stage bi-encoder held fixed at BAAI/bge-base-en-v1.5 so the
only differences are governance and reranking:

    bi        ungoverned bi-encoder, top-k                    (paper's no-gov row)
    bi_rr     ungoverned bi-encoder, over-fetch N -> rerank -> top-k
                  "use a reranker instead of governance"
    bear      BEAR governed, top-k                            (paper's governed row)
    bear_rr   BEAR governed, over-fetch N -> rerank -> top-k
                  "governance constructs the candidate set, reranker orders it"

Reported contrasts (paired bootstrap, 95% CI, paired Cohen's d):

    bear    vs bi        governance effect (reproduces the published contrast)
    bi_rr   vs bi        what the reranker buys on its own
    bear    vs bi_rr     THE head-to-head: governance vs reranking
    bear_rr vs bear      what the reranker adds on top of governance
    bear_rr vs bi_rr     governance effect holding the reranker fixed

The reranker is a pure function of (query, candidate text): it cannot admit a
document that the first stage never surfaced. Any arm that reranks a candidate
set is therefore upper-bounded by that set's recall at the over-fetch depth,
which is the structural point the composition arms are meant to expose.

Corpora:
    petsim     60 standard queries, k=10, strict F1 primary (tag-overlap truth)
    toolbench  1,100 queries, k=5, Recall@5 primary (relevant_apis truth)

Usage (from the repo root, inside the project venv):
    python evals/eval_reranker_composition.py --corpus petsim
    python evals/eval_reranker_composition.py --corpus toolbench
    python evals/eval_reranker_composition.py --corpus toolbench --overfetch 100
    python evals/eval_reranker_composition.py --corpus petsim --reranker BAAI/bge-reranker-v2-m3

Runtime: Pet Sim is a couple of minutes. ToolBench is dominated by the
cross-encoder (2 arms x 1,100 queries x N candidates); roughly 10 min on a
CUDA GPU at N=50, considerably longer on CPU. Per-query score arrays are
written to the output JSON so the statistics can be recomputed without re-running.
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

from bear import Config, Context, Corpus, Retriever, EmbeddingBackend  # noqa: E402
from bear.models import ScopeCondition  # noqa: E402

from eval_retrieval import TEST_QUERIES, RELAXED_EXTRAS  # noqa: E402
from eval_toolbench import (  # noqa: E402
    load_toolbench_corpus_and_queries,
    strip_governance,
    recall_at_k,
    precision_at_k,
    f1_at_k,
    ndcg_at_k,
)
from stat_utils import bootstrap_ci, paired_bootstrap  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_RERANKER = "BAAI/bge-reranker-base"
BOOTSTRAP_ITERS = 10_000

# First stage is BGE-base for both corpora: the paper's default backend.
BI_ENCODER = "BAAI/bge-base-en-v1.5"
BI_ENCODER_DIM = 768
BI_ENCODER_QUERY_PREFIX = "Represent this sentence for retrieving relevant documents: "

# Per-corpus settings, matching the scripts that produced the published rows:
#   petsim    -> eval_governance_decomposed.py (k=10, alpha=0.3, thr=0.3, mand=safety)
#   toolbench -> eval_toolbench.py             (k=5,  alpha=0.3, thr=0.0, no mandatory)
CORPUS_SETTINGS = {
    "petsim": {
        "top_k": 10,
        "priority_weight": 0.3,
        "threshold": 0.3,
        "mandatory_tags": ["safety"],
        "primary": "f1",
        "primary_label": "strict F1@10",
    },
    "toolbench": {
        "top_k": 5,
        "priority_weight": 0.3,
        "threshold": 0.0,
        "mandatory_tags": [],
        "primary": "recall",
        "primary_label": "Recall@5",
    },
}

ARMS = ["bi", "bi_rr", "bear", "bear_rr"]
ARM_LABELS = {
    "bi": "Bi-encoder, no governance",
    "bi_rr": "Bi-encoder + cross-encoder reranker",
    "bear": "BEAR governed",
    "bear_rr": "BEAR governed + cross-encoder reranker",
}

# Contrasts reported at the end: (arm_a, arm_b, what it answers)
CONTRASTS = [
    ("bear", "bi", "governance effect (published contrast)"),
    ("bi_rr", "bi", "reranker alone"),
    ("bear", "bi_rr", "head-to-head: governance vs reranking"),
    ("bear_rr", "bear", "reranker added on top of governance"),
    ("bear_rr", "bi_rr", "governance effect with reranker held fixed"),
]


# ---------------------------------------------------------------------------
# Corpus / query loading
# ---------------------------------------------------------------------------

def load_petsim():
    instructions_dir = project_root / "pet_sim" / "instructions"
    if not instructions_dir.exists():
        raise FileNotFoundError(f"Pet Sim instructions not found: {instructions_dir}")
    corpus = Corpus.from_directory(str(instructions_dir))
    queries = [(q, tags, set(expected)) for q, tags, expected in TEST_QUERIES]
    return corpus, queries


def load_corpus(name: str, max_queries: int | None):
    if name == "petsim":
        if max_queries:
            corpus, queries = load_petsim()
            return corpus, queries[:max_queries]
        return load_petsim()
    corpus, queries, _cat = load_toolbench_corpus_and_queries(max_queries=max_queries)
    queries = [(q[0], q[1], q[2]) for q in queries]
    return corpus, queries


def relaxed_expected(corpus_name: str, query_text: str, expected: set[str]) -> set[str] | None:
    """Pet Sim's relaxed ground truth, or None where no relaxed truth is defined.

    Pet Sim's strict truth is tag overlap, which Reviewer 3 correctly identified
    as partly circular with the gate. The relaxed set adds the topically
    defensible instructions that a human annotator accepts for that query, so a
    mechanism that improves genuine relevance can show up even when it moves
    items out of the tag-defined strict set.
    """
    if corpus_name != "petsim":
        return None
    return expected | RELAXED_EXTRAS.get(query_text, set())


def document_texts(corpus: Corpus) -> dict[str, str]:
    """id -> text handed to the cross-encoder.

    The same string BEAR indexes for that instruction, so the reranker and the
    bi-encoder see identical document content and the only difference between
    arms is the scoring mechanism.
    """
    return {inst.id: inst.content for inst in corpus}


# ---------------------------------------------------------------------------
# Retrievers
# ---------------------------------------------------------------------------

def strip_all_governance(corpus: Corpus, drop_conflicts: bool) -> Corpus:
    """Build the ungoverned corpus. Scope always cleared; conflict edges optional.

    Two defensible definitions of "ungoverned", selected by --ungoverned:

    pure_similarity (default)
        Scope cleared, conflict edges retained, priority weighting and mandatory
        injection off in the config. This is exactly the "pure similarity"
        condition of eval_petsim_fix_diagnosis.py, so the bi-encoder arm here
        reproduces the value the paper reports (strict F1 0.168 on Pet Sim) and
        the new numbers can be checked against the published ones.

    no_mechanisms
        Also clears conflicts_with, so no governance mechanism of any kind is
        active. Slightly higher on Pet Sim (0.197), because conflict resolution
        drops items that the tag-defined strict ground truth counts as relevant.

    The two are the same corpus on ToolBench: no ToolBench item declares a
    conflict edge.
    """
    out = Corpus()
    for inst in strip_governance(corpus):
        ic = inst.model_copy(deep=True)
        if drop_conflicts:
            ic.conflicts_with = []
        out.add(ic)
    return out


def build_retriever(corpus: Corpus, settings: dict, governed: bool,
                    drop_conflicts: bool = False) -> Retriever:
    config = Config(
        embedding_model=BI_ENCODER,
        embedding_backend=EmbeddingBackend.NUMPY,
        embedding_dim=BI_ENCODER_DIM,
        embedding_query_prefix=BI_ENCODER_QUERY_PREFIX,
        embedding_passage_prefix="",
        priority_weight=settings["priority_weight"] if governed else 0.0,
        default_threshold=settings["threshold"],
        default_top_k=settings["top_k"],
        mandatory_tags=settings["mandatory_tags"] if governed else [],
    )
    r = Retriever(corpus if governed else strip_all_governance(corpus, drop_conflicts),
                  config=config)
    r.build_index()
    return r


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

BASE_METRICS = ("recall", "precision", "f1", "ndcg")
RELAXED_METRICS = ("recall_relaxed", "f1_relaxed")


def score_arm(retrieved_ordered: list[str], expected: set[str], k: int,
              expected_relaxed: set[str] | None = None) -> dict[str, float]:
    retrieved = set(retrieved_ordered[:k])
    out = {
        "recall": recall_at_k(retrieved, expected, k),
        "precision": precision_at_k(retrieved, expected, k),
        "f1": f1_at_k(retrieved, expected, k),
        "ndcg": ndcg_at_k(retrieved_ordered[:k], expected, k),
    }
    if expected_relaxed is not None:
        out["recall_relaxed"] = recall_at_k(retrieved, expected_relaxed, k)
        out["f1_relaxed"] = f1_at_k(retrieved, expected_relaxed, k)
    return out


def run_arms(corpus_name: str, corpus: Corpus, queries, reranker, overfetch: int,
             batch_size: int, drop_conflicts: bool) -> dict:
    settings = CORPUS_SETTINGS[corpus_name]
    k = settings["top_k"]
    texts = document_texts(corpus)

    print(f"Building retrievers ({BI_ENCODER}, {len(corpus)} items)...")
    t0 = time.time()
    r_gov = build_retriever(corpus, settings, governed=True)
    r_plain = build_retriever(corpus, settings, governed=False,
                              drop_conflicts=drop_conflicts)
    print(f"  indexed in {time.time() - t0:.0f}s")

    n_fetch = min(overfetch, len(corpus))
    if n_fetch < overfetch:
        print(f"  over-fetch clamped to corpus size: N={n_fetch}")
    metrics = list(BASE_METRICS)
    if corpus_name == "petsim":
        metrics += list(RELAXED_METRICS)
    scores = {arm: {m: [] for m in metrics} for arm in ARMS}
    # Diagnostics: how much of the ground truth each first stage puts inside the
    # over-fetch window. The reranked arms cannot exceed these ceilings.
    ceilings = {"bi": [], "bear": []}
    cand_counts = {"bi": [], "bear": []}

    t0 = time.time()
    for i, (query_text, tags, expected) in enumerate(queries):
        if i and i % 100 == 0:
            rate = i / (time.time() - t0)
            print(f"  {i}/{len(queries)} queries ({rate:.1f}/s)")

        expected_rel = relaxed_expected(corpus_name, query_text, expected)

        for stage, retriever, use_tags in (("bi", r_plain, False), ("bear", r_gov, True)):
            ctx = Context(tags=list(tags) if use_tags else [])
            deep = retriever.retrieve(query_text, ctx, top_k=n_fetch)
            deep_ids = [d.id for d in deep]
            cand_counts[stage].append(len(deep_ids))
            ceilings[stage].append(recall_at_k(set(deep_ids), expected, n_fetch))

            # Un-reranked arm: a native top-k request, NOT the first k of the
            # deep one. The two are not the same ranking. Dependency pull-ins
            # (relationship expansion) enter at priority/100, so a deeper
            # request admits more of them and they can outrank true matches
            # inside the first k. Retrieving at k is what the published rows
            # do, so this arm reproduces them exactly.
            shallow = retriever.retrieve(query_text, ctx, top_k=k)
            for m, v in score_arm([s.id for s in shallow], expected, k, expected_rel).items():
                scores[stage][m].append(v)

            # Reranked arm: cross-encoder orders the same candidate set.
            rr_arm = f"{stage}_rr"
            if deep_ids:
                pairs = [(query_text, texts.get(d, "")) for d in deep_ids]
                rr_scores = reranker.predict(pairs, batch_size=batch_size,
                                             show_progress_bar=False)
                order = np.argsort(-np.asarray(rr_scores, dtype=float))
                reranked = [deep_ids[j] for j in order]
            else:
                reranked = []
            for m, v in score_arm(reranked, expected, k, expected_rel).items():
                scores[rr_arm][m].append(v)

    elapsed = time.time() - t0
    print(f"  {len(queries)}/{len(queries)} queries in {elapsed:.0f}s\n")

    return {
        "scores": {arm: {m: np.array(v) for m, v in d.items()} for arm, d in scores.items()},
        "ceilings": {s: np.array(v) for s, v in ceilings.items()},
        "cand_counts": {s: np.array(v) for s, v in cand_counts.items()},
        "n_fetch": n_fetch,
        "elapsed_s": elapsed,
    }


def cohen_d_paired(a: np.ndarray, b: np.ndarray) -> float:
    diff = a - b
    if diff.std(ddof=1) == 0:
        return 0.0
    return float(diff.mean() / diff.std(ddof=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", choices=["petsim", "toolbench"], default="petsim")
    ap.add_argument("--reranker", default=DEFAULT_RERANKER)
    ap.add_argument("--overfetch", type=int, default=50,
                    help="candidate-set depth handed to the reranker (default 50)")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--max-queries", type=int, default=None)
    ap.add_argument("--device", default=None, help="cuda / cpu (default: auto)")
    ap.add_argument("--ungoverned", choices=["pure_similarity", "no_mechanisms"],
                    default="pure_similarity",
                    help="definition of the ungoverned arm (see strip_all_governance)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    settings = CORPUS_SETTINGS[args.corpus]
    corpus, queries = load_corpus(args.corpus, args.max_queries)
    print(f"\n=== Reranker head-to-head and composition: {args.corpus} ===\n")
    print(f"corpus     {len(corpus)} items")
    print(f"queries    {len(queries)}")
    print(f"first stage {BI_ENCODER}  (k={settings['top_k']}, over-fetch N={args.overfetch})")
    print(f"reranker   {args.reranker}")
    print(f"ungoverned {args.ungoverned}")

    from sentence_transformers import CrossEncoder  # imported late: heavy

    device = args.device
    if device is None:
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    print(f"device     {device}\n")
    reranker = CrossEncoder(args.reranker, device=device)

    res = run_arms(args.corpus, corpus, queries, reranker, args.overfetch,
                   args.batch_size, drop_conflicts=args.ungoverned == "no_mechanisms")
    scores, primary = res["scores"], settings["primary"]

    out = {
        "corpus": args.corpus,
        "n_items": len(corpus),
        "n_queries": len(queries),
        "top_k": settings["top_k"],
        "overfetch": res["n_fetch"],
        "bi_encoder": BI_ENCODER,
        "reranker": args.reranker,
        "device": device,
        "ungoverned_definition": args.ungoverned,
        "primary_metric": primary,
        "priority_weight": settings["priority_weight"],
        "threshold": settings["threshold"],
        "mandatory_tags": settings["mandatory_tags"],
        "elapsed_s": res["elapsed_s"],
        "arms": {},
        "contrasts": {},
        "candidate_set_diagnostics": {},
        "per_query": {},
    }

    metrics = list(scores["bi"].keys())
    has_relaxed = "f1_relaxed" in metrics
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

    print(f"\n--- Candidate sets at N={res['n_fetch']} (ceiling for the reranked arms) ---\n")
    for stage in ("bi", "bear"):
        ceil = res["ceilings"][stage]
        cnt = res["cand_counts"][stage]
        out["candidate_set_diagnostics"][stage] = {
            "recall_at_overfetch": float(ceil.mean()),
            "mean_candidates": float(cnt.mean()),
            "per_query_recall_at_overfetch": ceil.tolist(),
            "per_query_candidates": cnt.tolist(),
        }
        print(f"  {stage:5s} recall@N {ceil.mean():.3f}   mean candidates {cnt.mean():.1f}")

    contrast_metrics = [(primary, settings["primary_label"])]
    if has_relaxed:
        contrast_metrics.append(("f1_relaxed", "relaxed F1@10"))

    for metric, metric_label in contrast_metrics:
        print(f"\n--- Contrasts (paired bootstrap, {metric_label}) ---\n")
        for a, b, question in CONTRASTS:
            pb = paired_bootstrap(scores[a][metric], scores[b][metric], BOOTSTRAP_ITERS)
            d = cohen_d_paired(scores[a][metric], scores[b][metric])
            key = f"{a}_vs_{b}" if metric == primary else f"{a}_vs_{b}__{metric}"
            out["contrasts"][key] = {
                "metric": metric,
                "question": question,
                "delta": pb["delta"],
                "ci": [pb["ci_lower"], pb["ci_upper"]],
                "p_value": pb["p_value"],
                "cohens_d_paired": d,
                "n": pb["n"],
            }
            sig = "*" if pb["p_value"] < 0.05 else " "
            print(f"  {a:8s} - {b:8s} {pb['delta']:+.3f} "
                  f"[{pb['ci_lower']:+.3f}, {pb['ci_upper']:+.3f}] "
                  f"p={pb['p_value']:.4f}{sig} d={d:+.2f}   {question}")

    out_path = Path(args.output) if args.output else (
        project_root / "results" / f"reranker_composition_{args.corpus}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")

    print("\nRead: 'bear vs bi_rr' is the substitution comparison the reviewers asked")
    print("for. 'bear_rr vs bear' and 'bear_rr vs bi_rr' test whether governance and")
    print("reranking compose, which is the claim made in the response letter. A")
    print("reranker cannot recover a document that is absent from the candidate set,")
    print("so compare each reranked arm against its own recall@N ceiling above.")
    print_repro_footer(extra={"corpus": args.corpus, "queries": len(queries),
                             "overfetch": res["n_fetch"], "reranker": args.reranker})


if __name__ == "__main__":
    main()
