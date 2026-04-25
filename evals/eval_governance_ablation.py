"""Governance ablation and cross-system comparison.

Evaluates retrieval quality across:
  - 7 BEAR backends (BM25, Hash, BGE-base, BGE-M3, Qwen3-0.6B, Qwen3-4B)
  - 3 governance levels (full, mandatory-only, no governance)
  - ITR (hybrid dense+sparse, no governance)
  - Random-k (uniform sampling baseline)
  - 4 query types (standard, paraphrase, no-tag, complex)

Also computes token efficiency across all methods.

All results include 95% bootstrap CIs (10,000 iterations).

Usage:
    python eval_governance_ablation.py                    # all BEAR + ITR + random-k
    python eval_governance_ablation.py --backends bge bm25  # specific backends only
    python eval_governance_ablation.py --skip-itr          # skip ITR (faster)
"""

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

from bear import Corpus, Config, Context, Retriever, Composer, CompositionStrategy, EmbeddingBackend
from bear.models import ScopeCondition, ScoredInstruction
from eval_retrieval import TEST_QUERIES, compute_metrics
from eval_retrieval_backends import (
    PARAPHRASE_QUERIES, NO_TAG_QUERIES, COMPLEX_QUERIES,
    BACKEND_CONFIGS, bootstrap_ci, paired_bootstrap_test,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOP_K = 10
PRIORITY_WEIGHT = 0.3
THRESHOLD = 0.3
BOOTSTRAP_ITERS = 10_000
RANDOM_K_TRIALS = 1000

QUERY_SETS = [
    ("Standard", TEST_QUERIES),
    ("Paraphrase", PARAPHRASE_QUERIES),
    ("No-tag", NO_TAG_QUERIES),
    ("Complex", COMPLEX_QUERIES),
]

ROLE_PROMPTS = {
    "dog": (
        "You are a playful, loyal golden retriever named Buddy. You love balls, "
        "treats, belly rubs, and your owner. You are friendly to familiar people "
        "but cautious around strangers. You obey basic commands enthusiastically."
    ),
    "cat": (
        "You are an independent, dignified tabby cat named Whiskers. You are "
        "aloof but affectionate with those you trust. You enjoy perching on high "
        "surfaces, ignoring commands, and batting at small objects. You tolerate the dog."
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_required_tags(corpus: Corpus) -> Corpus:
    """Return a copy of the corpus with all required_tags removed."""
    stripped = Corpus()
    for inst in corpus:
        ic = inst.model_copy(deep=True)
        ic.scope = ScopeCondition(
            tags=inst.scope.tags, required_tags=[],
            user_roles=inst.scope.user_roles, domains=inst.scope.domains,
            task_types=inst.scope.task_types, session_phase=inst.scope.session_phase,
            trigger_patterns=inst.scope.trigger_patterns,
        )
        stripped.add(ic)
    return stripped


def make_retriever(corp, cfg_key, mandatory_tags):
    """Build a Retriever from a BACKEND_CONFIGS key."""
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
        priority_weight=PRIORITY_WEIGHT,
        default_threshold=THRESHOLD,
        default_top_k=TOP_K,
        mandatory_tags=mandatory_tags,
    )
    r = Retriever(corp, config=config)
    r.build_index()
    return r


def evaluate_bear(retriever, queries):
    """Return per-query F1 array."""
    f1s = []
    for q, tags, expected in queries:
        result = retriever.retrieve(q, Context(tags=tags), top_k=TOP_K)
        retrieved = {r.id for r in result}
        _, _, f = compute_metrics(retrieved, expected, k=TOP_K)
        f1s.append(f)
    return np.array(f1s)


def evaluate_itr(itr_instance, queries):
    """Return per-query F1 array for ITR."""
    f1s = []
    for q, tags, expected in queries:
        result = itr_instance.step(q)
        retrieved = {i.id for i in result.instructions}
        _, _, f = compute_metrics(retrieved, expected, k=TOP_K)
        f1s.append(f)
    return np.array(f1s)


def evaluate_random_k(corpus, queries, k=TOP_K, n_trials=RANDOM_K_TRIALS):
    """Return per-query F1 array averaged over n_trials random samples."""
    all_ids = [inst.id for inst in corpus]
    rng = np.random.default_rng(42)
    per_query_f1s = []
    for q, tags, expected in queries:
        trial_f1s = []
        for _ in range(n_trials):
            sampled = set(rng.choice(all_ids, size=k, replace=False))
            _, _, f = compute_metrics(sampled, expected, k=k)
            trial_f1s.append(f)
        per_query_f1s.append(np.mean(trial_f1s))
    return np.array(per_query_f1s)


def fmt_ci(mean, lo, hi):
    return f"{mean:.3f} [{lo:.3f},{hi:.3f}]"


# ---------------------------------------------------------------------------
# Token efficiency
# ---------------------------------------------------------------------------

def compute_token_efficiency(corpus, backends, itr_instance=None):
    """Compute average tokens per query for each method."""
    enc = tiktoken.get_encoding("cl100k_base")
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    # Monolithic
    mono_text = " ".join(inst.content for inst in corpus)
    mono_tokens = len(enc.encode(mono_text))

    results = {"Monolithic": {"tokens": mono_tokens, "instructions": len(corpus), "savings": 0.0}}

    # Role prompting
    role_tokens = np.mean([len(enc.encode(p)) for p in ROLE_PROMPTS.values()])
    results["Role prompting"] = {
        "tokens": role_tokens, "instructions": 0,
        "savings": (1 - role_tokens / mono_tokens) * 100,
    }

    # BEAR backends
    for key in backends:
        r = make_retriever(corpus, key, ["safety"])
        tokens, n_instr = [], []
        for q, tags, _ in TEST_QUERIES:
            res = r.retrieve(q, Context(tags=tags), top_k=TOP_K)
            text = str(composer.compose(res))
            tokens.append(len(enc.encode(text)))
            n_instr.append(len(res))
        avg_tok = np.mean(tokens)
        label = BACKEND_CONFIGS[key]["short"]
        results[f"BEAR + {label}"] = {
            "tokens": avg_tok, "instructions": np.mean(n_instr),
            "savings": (1 - avg_tok / mono_tokens) * 100,
        }

    # ITR
    if itr_instance is not None:
        itr_tokens = []
        for q, tags, _ in TEST_QUERIES:
            res = itr_instance.step(q)
            text = " ".join(inst.content for inst in res.instructions)
            itr_tokens.append(len(enc.encode(text)))
        avg_tok = np.mean(itr_tokens)
        results["ITR"] = {
            "tokens": avg_tok, "instructions": 10.0,
            "savings": (1 - avg_tok / mono_tokens) * 100,
        }

    # Random-k
    rng = np.random.default_rng(42)
    all_insts = list(corpus)
    rand_tokens = []
    for _ in range(1000):
        sampled = rng.choice(all_insts, size=10, replace=False)
        text = " ".join(inst.content for inst in sampled)
        rand_tokens.append(len(enc.encode(text)))
    avg_tok = np.mean(rand_tokens)
    results["Random-k"] = {
        "tokens": avg_tok, "instructions": 10.0,
        "savings": (1 - avg_tok / mono_tokens) * 100,
    }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Governance ablation evaluation.")
    parser.add_argument("--backends", nargs="+",
                        choices=list(BACKEND_CONFIGS.keys()),
                        default=["bm25", "hash", "bge", "bge-m3", "qwen3", "qwen3-4b"],
                        help="BEAR backends to evaluate.")
    parser.add_argument("--skip-itr", action="store_true",
                        help="Skip ITR evaluation (faster).")
    parser.add_argument("--output", type=str, default=None,
                        help="JSON output file.")
    args = parser.parse_args()

    backends = args.backends

    # Load corpus
    instructions_dir = project_root / "pet_sim" / "instructions"
    corpus = Corpus.from_directory(str(instructions_dir))
    stripped = strip_required_tags(corpus)
    print(f"Loaded corpus: {len(corpus)} instructions")
    print(f"Backends: {', '.join(backends)}")

    # Setup ITR
    itr_instance = None
    if not args.skip_itr:
        try:
            from itr import ITR, ITRConfig, InstructionFragment, FragmentType
            enc = tiktoken.get_encoding("cl100k_base")
            fragments = [
                InstructionFragment(
                    id=inst.id, content=inst.content,
                    token_count=len(enc.encode(inst.content)),
                    fragment_type=FragmentType.DOMAIN_SPECIFIC,
                    priority=inst.priority,
                )
                for inst in corpus
            ]
            itr_instance = ITR(config=ITRConfig(
                k_a_instructions=TOP_K, top_m_instructions=30,
                token_budget=50000, embedding_model="BAAI/bge-base-en-v1.5",
            ))
            itr_instance.add_instruction_fragments(fragments)
            print("ITR loaded")
        except ImportError:
            print("ITR not installed, skipping")

    # Governance levels
    gov_levels = [
        ("Full governance", corpus, ["safety"]),
        ("Mandatory only", stripped, ["safety"]),
        ("No governance", stripped, []),
    ]

    all_results = {}

    for gov_name, corp, mand in gov_levels:
        print(f"\n{'=' * 70}")
        print(f"  {gov_name}")
        print(f"{'=' * 70}")

        for qs_name, queries in QUERY_SETS:
            print(f"\n  {qs_name} (n={len(queries)}):")

            # BEAR backends
            for key in backends:
                r = make_retriever(corp, key, mand)
                scores = evaluate_bear(r, queries)
                mean, lo, hi = bootstrap_ci(scores)
                label = BACKEND_CONFIGS[key]["short"]
                print(f"    {label:<20} {fmt_ci(mean, lo, hi)}")
                all_results.setdefault(gov_name, {}).setdefault(qs_name, {})[label] = {
                    "f1": mean, "ci": [lo, hi],
                }

            # ITR (same for all governance levels — it has none)
            if itr_instance is not None:
                scores = evaluate_itr(itr_instance, queries)
                mean, lo, hi = bootstrap_ci(scores)
                print(f"    {'ITR':<20} {fmt_ci(mean, lo, hi)}")
                all_results.setdefault(gov_name, {}).setdefault(qs_name, {})["ITR"] = {
                    "f1": mean, "ci": [lo, hi],
                }

            # Random-k
            scores = evaluate_random_k(corpus, queries)
            mean, lo, hi = bootstrap_ci(scores)
            print(f"    {'Random-k':<20} {fmt_ci(mean, lo, hi)}")
            all_results.setdefault(gov_name, {}).setdefault(qs_name, {})["Random-k"] = {
                "f1": mean, "ci": [lo, hi],
            }

    # Token efficiency
    print(f"\n{'=' * 70}")
    print("  Token Efficiency")
    print(f"{'=' * 70}")
    tok_results = compute_token_efficiency(corpus, backends, itr_instance)
    print(f"\n  {'Strategy':<25} {'Tokens':>8} {'Instr':>6} {'Savings':>8}")
    print("  " + "-" * 49)
    for name, data in tok_results.items():
        print(f"  {name:<25} {data['tokens']:>8.0f} {data['instructions']:>6.1f} "
              f"{data['savings']:>7.1f}%")

    all_results["token_efficiency"] = {
        k: {"tokens": v["tokens"], "savings": v["savings"]}
        for k, v in tok_results.items()
    }

    # Save JSON
    output_path = args.output or str(
        project_root / "results" / "governance_ablation.json"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=float)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
