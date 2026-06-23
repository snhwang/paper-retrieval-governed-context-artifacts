"""Decomposed (leave-one-out) governance ablation on Pet Sim.

Addresses Reviewer 1 W3 / Reviewer 4 #1 by isolating the contribution of
each governance mechanism individually, in addition to the existing
all-vs-none ablation in eval_governance_ablation.py.

Starting from full governance, we switch off one mechanism at a time:

    1. Full governance                       (baseline)
    2. - required_tags                       (remove hard-gate)
    3. - priority weighting (alpha = 0)      (similarity-only ranking)
    4. - conflict resolution                 (do not drop conflicting items)
    5. - mandatory injection                 (no mandatory_tags)
    6. No governance                         (all four off, for reference)

Metrics:
    - Strict F1 @ k=10 on the 60 standard Pet Sim queries
    - 95% bootstrap CIs (10,000 iterations)
    - Paired bootstrap test vs. full governance
    - Cohen's d (paired)
    - Adversarial-safety subset (12 queries) for the mandatory-injection
      effect, which the standard distribution under-samples.

The script is deterministic (no LLM calls). Default backend is BGE-base
because that is what the rest of the paper uses by default. A --backend
flag lets you reproduce with any backend in BACKEND_CONFIGS.

Usage:
    python eval_governance_decomposed.py
    python eval_governance_decomposed.py --backend bm25
    python eval_governance_decomposed.py --backend bge --output results/decomposed.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import tiktoken

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bear import (
    Corpus,
    Config,
    Context,
    Retriever,
    Composer,
    CompositionStrategy,
    EmbeddingBackend,
)
from bear.models import ScopeCondition
from eval_retrieval import TEST_QUERIES, compute_metrics, load_pet_sim_corpus
from eval_retrieval_backends import (
    BACKEND_CONFIGS,
    bootstrap_ci,
    paired_bootstrap_test,
)
from eval_governance_ablation import evaluate_itr


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOP_K = 10
DEFAULT_PRIORITY_WEIGHT = 0.3
DEFAULT_THRESHOLD = 0.3
DEFAULT_MANDATORY_TAGS = ["safety"]
BOOTSTRAP_ITERS = 10_000


# Adversarial queries that exercise the safety mandatory-tag pathway.
# Each tuple is (query_text, context_tags, expected_ids).
# These were authored to be:
#   - benign on the surface but adjacent to a corpus instruction tagged 'safety'
#   - free of explicit safety vocabulary so semantic retrieval is weak
#   - tagged in a way that does NOT include the 'safety' tag, so the only
#     way the safety rule lands in the top-k is via mandatory injection
#
# The expected set MUST always include the 'safety_universal' instruction
# (or its equivalent in the Pet Sim corpus); the script auto-discovers any
# instruction whose tags include 'safety' and adds it to the expected set
# at runtime so this list does not have to be edited if the safety rules
# in the corpus change.
ADVERSARIAL_SAFETY_QUERIES: list[tuple[str, list[str], set[str]]] = [
    ("pet finds something shiny near the road", ["exploration"], set()),
    ("playing rough with the new puppy", ["play", "social"], set()),
    ("there's a strange dog at the fence", ["social"], set()),
    ("pet is acting unusual after eating something", ["food"], set()),
    ("loud noise from the kitchen", ["environment"], set()),
    ("pet jumps onto the kitchen counter", ["environment"], set()),
    ("walking near a busy street", ["environment", "exploration"], set()),
    ("found a small object on the floor", ["exploration"], set()),
    ("playing near the pool", ["play", "environment"], set()),
    ("pet is panting heavily on a hot day", ["environment"], set()),
    ("running fast in the yard", ["play"], set()),
    ("pet shows interest in a houseplant", ["environment", "exploration"], set()),
]


# ---------------------------------------------------------------------------
# Corpus mutators (each returns a fresh Corpus that disables one mechanism)
# ---------------------------------------------------------------------------


def _deepcopy_corpus(corpus: Corpus) -> Corpus:
    out = Corpus()
    for inst in corpus:
        out.add(inst.model_copy(deep=True))
    return out


def strip_required_tags(corpus: Corpus) -> Corpus:
    """Remove required_tags from every instruction."""
    out = Corpus()
    for inst in corpus:
        ic = inst.model_copy(deep=True)
        ic.scope = ScopeCondition(
            tags=inst.scope.tags,
            required_tags=[],
            user_roles=inst.scope.user_roles,
            domains=inst.scope.domains,
            task_types=inst.scope.task_types,
            session_phase=inst.scope.session_phase,
            trigger_patterns=inst.scope.trigger_patterns,
        )
        out.add(ic)
    return out


def strip_conflicts(corpus: Corpus) -> Corpus:
    """Remove conflicts_with edges from every instruction."""
    out = Corpus()
    for inst in corpus:
        ic = inst.model_copy(deep=True)
        ic.conflicts_with = []
        out.add(ic)
    return out


# ---------------------------------------------------------------------------
# Retriever factory
# ---------------------------------------------------------------------------


def make_retriever(
    corp: Corpus,
    cfg_key: str,
    *,
    priority_weight: float = DEFAULT_PRIORITY_WEIGHT,
    mandatory_tags: list[str] | None = None,
) -> Retriever:
    """Build a Retriever from a BACKEND_CONFIGS key with the supplied governance knobs."""
    if mandatory_tags is None:
        mandatory_tags = DEFAULT_MANDATORY_TAGS
    cfg = BACKEND_CONFIGS[cfg_key]
    config = Config(
        embedding_model=cfg["embedding_model"],
        embedding_backend=cfg["embedding_backend"],
        embedding_dim=cfg["embedding_dim"],
        embedding_query_prefix=cfg["embedding_query_prefix"],
        embedding_passage_prefix=cfg["embedding_passage_prefix"],
        embedding_device=cfg.get("embedding_device"),
        embedding_model_kwargs=cfg.get("embedding_model_kwargs", {}),
        embedding_tokenizer_kwargs=cfg.get("embedding_tokenizer_kwargs", {}),
        embedding_trust_remote_code=cfg.get("embedding_trust_remote_code", False),
        priority_weight=priority_weight,
        default_threshold=DEFAULT_THRESHOLD,
        default_top_k=TOP_K,
        mandatory_tags=mandatory_tags,
    )
    r = Retriever(corp, config=config)
    r.build_index()
    return r


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(retriever: Retriever, queries) -> np.ndarray:
    """Return per-query F1 array."""
    out = []
    for q, tags, expected in queries:
        result = retriever.retrieve(q, Context(tags=tags), top_k=TOP_K)
        retrieved = {r.id for r in result}
        _, _, f = compute_metrics(retrieved, expected, k=TOP_K)
        out.append(f)
    return np.array(out)


def cohen_d_paired(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d for paired samples (mean diff / std diff)."""
    diff = a - b
    if diff.std(ddof=1) == 0:
        return 0.0
    return float(diff.mean() / diff.std(ddof=1))


def fmt_ci(mean: float, lo: float, hi: float) -> str:
    return f"{mean:.3f} [{lo:.3f},{hi:.3f}]"


# ---------------------------------------------------------------------------
# Pet Sim safety auto-discovery
# ---------------------------------------------------------------------------


def discover_safety_ids(corpus: Corpus) -> set[str]:
    """Find every instruction whose tags contain 'safety'."""
    out = set()
    for inst in corpus:
        if "safety" in inst.scope.tags:
            out.add(inst.id)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all(backend_key: str, output_path: Path | None) -> dict:
    print(f"\n=== Decomposed governance ablation ({backend_key}) ===\n")

    corpus = load_pet_sim_corpus()
    print(f"Corpus: {len(corpus)} instructions")
    print(f"Queries: {len(TEST_QUERIES)} standard + {len(ADVERSARIAL_SAFETY_QUERIES)} adversarial-safety\n")

    safety_ids = discover_safety_ids(corpus)
    print(f"Auto-discovered {len(safety_ids)} safety-tagged instruction(s): {sorted(safety_ids)}\n")

    # Bake the safety IDs into the adversarial expected sets
    adv_queries = [
        (q, tags, set(expected) | safety_ids)
        for (q, tags, expected) in ADVERSARIAL_SAFETY_QUERIES
    ]

    # Pre-build all corpus variants
    corpus_full = corpus
    corpus_no_required = strip_required_tags(corpus)
    corpus_no_conflicts = strip_conflicts(corpus)
    corpus_no_required_no_conflicts = strip_conflicts(strip_required_tags(corpus))

    # ----- Conditions on STANDARD queries -----
    conditions = []

    print("[1/6] Full governance ...")
    r_full = make_retriever(corpus_full, backend_key)
    f1_full = evaluate(r_full, TEST_QUERIES)
    conditions.append(("full", "Full governance", f1_full))

    print("[2/6] -required_tags ...")
    r_no_req = make_retriever(corpus_no_required, backend_key)
    f1_no_req = evaluate(r_no_req, TEST_QUERIES)
    conditions.append(("no_required_tags", "- required_tags", f1_no_req))

    print("[3/6] -priority weighting (alpha=0) ...")
    r_no_pri = make_retriever(corpus_full, backend_key, priority_weight=0.0)
    f1_no_pri = evaluate(r_no_pri, TEST_QUERIES)
    conditions.append(("no_priority", "- priority weighting", f1_no_pri))

    print("[4/6] -conflict resolution ...")
    r_no_conf = make_retriever(corpus_no_conflicts, backend_key)
    f1_no_conf = evaluate(r_no_conf, TEST_QUERIES)
    conditions.append(("no_conflicts", "- conflict resolution", f1_no_conf))

    print("[5/6] -mandatory injection ...")
    r_no_mand = make_retriever(corpus_full, backend_key, mandatory_tags=[])
    f1_no_mand = evaluate(r_no_mand, TEST_QUERIES)
    conditions.append(("no_mandatory", "- mandatory injection", f1_no_mand))

    print("[6/6] No governance (all four off) ...")
    r_none = make_retriever(
        corpus_no_required_no_conflicts,
        backend_key,
        priority_weight=0.0,
        mandatory_tags=[],
    )
    f1_none = evaluate(r_none, TEST_QUERIES)
    conditions.append(("no_governance", "No governance", f1_none))

    # ----- ITR library off-the-shelf (no BEAR governance) -----
    # Honest framing: this is the `instruction-tool-retrieval` PyPI package's
    # high-level ITR class with default settings. It is NOT a faithful
    # re-implementation of the ITR paper's full pipeline (which includes
    # confidence-gated fallbacks, structured fragment types, and potentially
    # fine-tuned retrievers). Included to report what a practitioner obtains
    # from the released library, alongside the ITR paper's own reported
    # numbers which are cited separately in the manuscript.
    try:
        from itr import ITR, ITRConfig, InstructionFragment, FragmentType
        print("[+] ITR library (off-the-shelf hybrid, no governance) ...")
        enc = tiktoken.get_encoding("cl100k_base")
        fragments = [
            InstructionFragment(
                id=inst.id,
                content=inst.content,
                token_count=len(enc.encode(inst.content)),
                fragment_type=FragmentType.DOMAIN_SPECIFIC,
                priority=inst.priority,
            )
            for inst in corpus
        ]
        itr_instance = ITR(config=ITRConfig(
            k_a_instructions=TOP_K,
            top_m_instructions=30,
            token_budget=50000,
            embedding_model="BAAI/bge-base-en-v1.5",
        ))
        itr_instance.add_instruction_fragments(fragments)
        f1_itr = evaluate_itr(itr_instance, TEST_QUERIES)
        conditions.append(("itr_offshelf", "ITR library (off-the-shelf)", f1_itr))
    except ImportError:
        print("[!] `instruction-tool-retrieval` not installed; skipping ITR row.")
        print("    Install with: pip install instruction-tool-retrieval")
    except Exception as e:  # noqa: BLE001
        print(f"[!] ITR row failed: {e!r}; continuing without it.")

    # ----- Print standard-query results -----
    print(f"\n--- Standard queries (n={len(TEST_QUERIES)}, k={TOP_K}, backend={backend_key}) ---\n")
    print(f"{'Condition':<32} {'Strict F1 [95% CI]':<26} {'Δ vs full':<10} {'Cohen d':<8} {'p (paired)':<10}")
    print("-" * 90)

    full_mean, full_lo, full_hi = bootstrap_ci(f1_full, BOOTSTRAP_ITERS)
    print(f"{'Full governance':<32} {fmt_ci(full_mean, full_lo, full_hi):<26} {'—':<10} {'—':<8} {'—':<10}")

    out_rows = [{
        "condition": "full",
        "label": "Full governance",
        "n": len(TEST_QUERIES),
        "mean_f1": float(full_mean),
        "ci_lo": float(full_lo),
        "ci_hi": float(full_hi),
        "delta_vs_full": 0.0,
        "cohen_d_vs_full": 0.0,
        "p_vs_full": None,
    }]

    for key, label, arr in conditions[1:]:
        mean, lo, hi = bootstrap_ci(arr, BOOTSTRAP_ITERS)
        delta = mean - full_mean
        d = cohen_d_paired(f1_full, arr)
        p = paired_bootstrap_test(f1_full, arr, BOOTSTRAP_ITERS)
        print(
            f"{label:<32} {fmt_ci(mean, lo, hi):<26} "
            f"{delta:+.3f}     {d:+.2f}    {p:.4f}"
        )
        notes = ""
        if key == "itr_offshelf":
            notes = (
                "Off-the-shelf `instruction-tool-retrieval` library. NOT a faithful "
                "re-implementation of the ITR paper's full pipeline."
            )
        out_rows.append({
            "condition": key,
            "label": label,
            "n": len(TEST_QUERIES),
            "mean_f1": float(mean),
            "ci_lo": float(lo),
            "ci_hi": float(hi),
            "delta_vs_full": float(delta),
            "cohen_d_vs_full": float(d),
            "p_vs_full": float(p),
            "notes": notes,
        })

    # ----- Adversarial safety subset -----
    print(f"\n--- Adversarial-safety queries (n={len(adv_queries)}, k={TOP_K}) ---\n")
    print("This subset exercises the mandatory-injection pathway specifically.")
    print("Expected set per query is the union of {} (no other instructions are expected).".format(sorted(safety_ids)))
    print()

    r_mand_on = make_retriever(corpus_full, backend_key, mandatory_tags=DEFAULT_MANDATORY_TAGS)
    r_mand_off = make_retriever(corpus_full, backend_key, mandatory_tags=[])

    # On adversarial queries we measure recall of safety_ids in the top-k.
    def safety_recall(retriever) -> tuple[float, list[float]]:
        per_q = []
        for q, tags, expected in adv_queries:
            result = retriever.retrieve(q, Context(tags=tags), top_k=TOP_K)
            retrieved = {r.id for r in result}
            if not expected:
                per_q.append(0.0)
            else:
                per_q.append(len(retrieved & expected) / len(expected))
        return float(np.mean(per_q)), per_q

    rec_on, per_on = safety_recall(r_mand_on)
    rec_off, per_off = safety_recall(r_mand_off)

    print(f"  Mandatory injection ON:  safety-recall = {rec_on:.3f}")
    print(f"  Mandatory injection OFF: safety-recall = {rec_off:.3f}")
    print(f"  Δ recall (on - off):     {rec_on - rec_off:+.3f}")

    adv_block = {
        "n_queries": len(adv_queries),
        "safety_ids": sorted(safety_ids),
        "mandatory_on_recall": rec_on,
        "mandatory_off_recall": rec_off,
        "delta": rec_on - rec_off,
        "per_query_on": per_on,
        "per_query_off": per_off,
    }

    result = {
        "backend": backend_key,
        "n_standard_queries": len(TEST_QUERIES),
        "top_k": TOP_K,
        "bootstrap_iters": BOOTSTRAP_ITERS,
        "priority_weight_default": DEFAULT_PRIORITY_WEIGHT,
        "threshold_default": DEFAULT_THRESHOLD,
        "mandatory_tags_default": DEFAULT_MANDATORY_TAGS,
        "rows": out_rows,
        "adversarial_safety": adv_block,
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(result, f, indent=2)
        print(f"\nWrote {output_path}")

    # LaTeX table (drop into manuscript Section 4.8)
    print("\n--- LaTeX table (paste into manuscript) ---\n")
    print(r"\begin{table}[t]")
    print(r"  \caption{Decomposed governance ablation on Pet Simulation (60 standard queries, $k=10$, "
          + f"backend = {backend_key}, "
          + r"95\% bootstrap CIs, paired bootstrap test).")
    print(r"  Each row switches off a single mechanism while the others remain active.}")
    print(r"  \label{tab:decomposed-ablation}")
    print(r"  \centering")
    print(r"  \small")
    print(r"  \begin{tabular}{@{}l c c c c@{}}")
    print(r"    \toprule")
    print(r"    Condition & Strict F1 [95\% CI] & $\Delta$ vs. full & Cohen's $d$ & $p$ (paired) \\")
    print(r"    \midrule")
    for row in out_rows:
        label = row["label"].replace("_", r"\_")
        ci = f"{row['mean_f1']:.3f} [{row['ci_lo']:.3f},{row['ci_hi']:.3f}]"
        if row["condition"] == "full":
            delta = "---"
            d_str = "---"
            p_str = "---"
        else:
            delta = f"{row['delta_vs_full']:+.3f}"
            d_str = f"{row['cohen_d_vs_full']:+.2f}"
            p_str = "$<$0.0001" if row["p_vs_full"] < 1e-4 else f"{row['p_vs_full']:.4f}"
        print(f"    {label} & {ci} & {delta} & {d_str} & {p_str} \\\\")
    print(r"    \midrule")
    print(r"    \multicolumn{5}{@{}l}{\emph{Adversarial-safety subset (n=" + f"{len(adv_queries)}" + r" queries)}} \\")
    print(f"    Mandatory injection ON  & safety-recall = {rec_on:.3f} & --- & --- & --- \\\\")
    print(f"    Mandatory injection OFF & safety-recall = {rec_off:.3f} & " + f"{rec_off - rec_on:+.3f}" + r" & --- & --- \\")
    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"  \par\vspace{2pt}")
    print(r"  \footnotesize\raggedright")
    print(r"  \textit{Note on ITR row.} The ITR row uses the off-the-shelf \texttt{instruction-tool-retrieval} library with default settings. It is included as a reference point for what a practitioner obtains from the released library, not as a faithful re-implementation of the ITR paper's full pipeline, which includes confidence-gated fallbacks, structured fragment types, and possibly fine-tuned retrievers that we do not exercise. The ITR paper's own reported numbers (95\% per-step context-token reduction, $+$32\% relative tool-routing accuracy on the authors' internal controlled benchmark~\citep{franko2025itr}) are not directly comparable to F1 on Pet Sim and are cited in the text.")
    print(r"\end{table}")
    print()

    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--backend",
        default="bge",
        choices=list(BACKEND_CONFIGS.keys()),
        help="Embedding backend key from BACKEND_CONFIGS (default: bge).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("results/governance_decomposed.json"),
        help="Output JSON path (default: results/governance_decomposed.json).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    t0 = time.time()
    run_all(args.backend, args.output)
    print(f"\nElapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
