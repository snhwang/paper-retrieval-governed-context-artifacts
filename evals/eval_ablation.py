"""Parameter sensitivity analysis: vary alpha (priority weight) and theta (similarity threshold).

Usage:
    python eval_ablation.py              # hash embeddings (fast, deterministic)
    python eval_ablation.py --semantic   # sentence-transformers (slower, meaningful)
"""

import argparse
import sys
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend

# Reuse the ground-truth queries from eval_retrieval
from eval_retrieval import TEST_QUERIES, compute_metrics, EMBEDDING_MODEL
from stat_utils import bootstrap_ci, format_ci


def run_ablation(use_semantic: bool = False):
    model = EMBEDDING_MODEL if use_semantic else "hash"
    print(f"Embedding model: {model}\n")
    instructions_dir = project_root / "pet_sim" / "instructions"
    if not instructions_dir.exists():
        print(f"ERROR: Instructions directory not found: {instructions_dir}")
        sys.exit(1)

    corpus = Corpus.from_directory(str(instructions_dir))
    print(f"Loaded corpus with {len(corpus)} instructions\n")

    # --- Alpha sweep (priority weight) at K=10 ---
    print("=" * 60)
    print("Alpha sweep: priority weight from 0.0 to 1.0 (K=10)")
    print("=" * 60)

    alpha_values = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    alpha_results_k10 = {}

    for alpha in alpha_values:
        config = Config(
            embedding_model=model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=alpha,
            default_threshold=0.3,
            default_top_k=10,
            mandatory_tags=["safety"],
        )
        retriever = Retriever(corpus, config=config)
        retriever.build_index()

        all_p, all_r, all_f1 = [], [], []
        for query_text, context_tags, expected_ids in TEST_QUERIES:
            context = Context(tags=context_tags)
            retrieved = retriever.retrieve(query_text, context, top_k=10)
            retrieved_ids = {r.id for r in retrieved}
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=10)
            all_p.append(p)
            all_r.append(r)
            all_f1.append(f)

        avg_p = sum(all_p) / len(all_p)
        avg_r = sum(all_r) / len(all_r)
        avg_f1 = sum(all_f1) / len(all_f1)
        ci_f1 = bootstrap_ci(all_f1)
        alpha_results_k10[alpha] = (avg_p, avg_r, avg_f1, ci_f1)
        print(f"  alpha={alpha:.1f}: P@10={avg_p:.3f}, R@10={avg_r:.3f}, F1@10={format_ci(ci_f1)}")

    # --- Alpha sweep at K=5 (semantic only — where ordering matters) ---
    print("\n" + "=" * 60)
    print("Alpha sweep: priority weight from 0.0 to 1.0 (K=5, semantic)")
    print("=" * 60)

    alpha_results_k5 = {}
    semantic_model = EMBEDDING_MODEL

    for alpha in alpha_values:
        config = Config(
            embedding_model=semantic_model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=alpha,
            default_threshold=0.3,
            default_top_k=5,
            mandatory_tags=["safety"],
        )
        retriever = Retriever(corpus, config=config)
        retriever.build_index()

        all_p, all_r, all_f1 = [], [], []
        for query_text, context_tags, expected_ids in TEST_QUERIES:
            context = Context(tags=context_tags)
            retrieved = retriever.retrieve(query_text, context, top_k=5)
            retrieved_ids = {r.id for r in retrieved}
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=5)
            all_p.append(p)
            all_r.append(r)
            all_f1.append(f)

        avg_p = sum(all_p) / len(all_p)
        avg_r = sum(all_r) / len(all_r)
        avg_f1 = sum(all_f1) / len(all_f1)
        ci_f1 = bootstrap_ci(all_f1)
        alpha_results_k5[alpha] = (avg_p, avg_r, avg_f1, ci_f1)
        print(f"  alpha={alpha:.1f}: P@5={avg_p:.3f}, R@5={avg_r:.3f}, F1@5={format_ci(ci_f1)}")

    # --- Alpha sweep at K=5 on soft-scope queries only ---
    # These queries target the 8 instructions without required_tags (moods + safety),
    # where semantic similarity drives retrieval and alpha actually matters.
    print("\n" + "=" * 60)
    print("Alpha sweep: soft-scope queries only (K=5, semantic)")
    print("=" * 60)

    SOFT_SCOPE_QUERIES = [
        ("The dog is bouncing around excitedly", ["dog", "mood_excited"],
         {"dog-personality", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
        ("The cat is slowly falling asleep", ["cat", "mood_sleepy"],
         {"cat-personality", "mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
        ("The dog is carefully watching its surroundings", ["dog", "mood_cautious"],
         {"dog-personality", "mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
        ("The cat is in a playful mood chasing things", ["cat", "mood_playful"],
         {"cat-personality", "mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
        ("The dog seems content and relaxed", ["dog", "mood_content"],
         {"dog-personality", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ]

    alpha_results_soft = {}

    for alpha in alpha_values:
        config = Config(
            embedding_model=semantic_model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=alpha,
            default_threshold=0.3,
            default_top_k=5,
            mandatory_tags=["safety"],
        )
        retriever = Retriever(corpus, config=config)
        retriever.build_index()

        all_p, all_r, all_f1 = [], [], []
        for query_text, context_tags, expected_ids in SOFT_SCOPE_QUERIES:
            context = Context(tags=context_tags)
            retrieved = retriever.retrieve(query_text, context, top_k=5)
            retrieved_ids = {r.id for r in retrieved}
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=5)
            all_p.append(p)
            all_r.append(r)
            all_f1.append(f)

        avg_p = sum(all_p) / len(all_p)
        avg_r = sum(all_r) / len(all_r)
        avg_f1 = sum(all_f1) / len(all_f1)
        ci_f1 = bootstrap_ci(all_f1)
        alpha_results_soft[alpha] = (avg_p, avg_r, avg_f1, ci_f1)
        print(f"  alpha={alpha:.1f}: P@5={avg_p:.3f}, R@5={avg_r:.3f}, F1@5={format_ci(ci_f1)}")

    # --- Alpha sweep with required_tags stripped (all-soft corpus) ---
    # Simulates a deployment where no instructions use hard scope gates,
    # forcing all retrieval through semantic similarity + priority scoring.
    print("\n" + "=" * 60)
    print("Alpha sweep: required_tags stripped (all-soft, K=10, semantic)")
    print("=" * 60)

    import copy
    soft_corpus = Corpus()
    for inst in corpus:
        inst_copy = copy.deepcopy(inst)
        inst_copy.scope.required_tags = []
        soft_corpus.add(inst_copy)

    alpha_results_allsoft = {}

    for alpha in alpha_values:
        config = Config(
            embedding_model=semantic_model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=alpha,
            default_threshold=0.3,
            default_top_k=10,
            mandatory_tags=["safety"],
        )
        retriever = Retriever(soft_corpus, config=config)
        retriever.build_index()

        all_p, all_r, all_f1 = [], [], []
        for query_text, context_tags, expected_ids in TEST_QUERIES:
            context = Context(tags=context_tags)
            retrieved = retriever.retrieve(query_text, context, top_k=10)
            retrieved_ids = {r.id for r in retrieved}
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=10)
            all_p.append(p)
            all_r.append(r)
            all_f1.append(f)

        avg_p = sum(all_p) / len(all_p)
        avg_r = sum(all_r) / len(all_r)
        avg_f1 = sum(all_f1) / len(all_f1)
        ci_f1 = bootstrap_ci(all_f1)
        alpha_results_allsoft[alpha] = (avg_p, avg_r, avg_f1, ci_f1)
        print(f"  alpha={alpha:.1f}: P@10={avg_p:.3f}, R@10={avg_r:.3f}, F1@10={format_ci(ci_f1)}")

    # --- Theta sweep (similarity threshold) ---
    print("\n" + "=" * 60)
    print("Theta sweep: similarity threshold from 0.0 to 0.6")
    print("=" * 60)

    theta_values = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    theta_results = {}

    for theta in theta_values:
        config = Config(
            embedding_model=model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=0.3,
            default_threshold=theta,
            default_top_k=10,
            mandatory_tags=["safety"],
        )
        retriever = Retriever(corpus, config=config)
        retriever.build_index()

        all_p, all_r, all_f1 = [], [], []
        for query_text, context_tags, expected_ids in TEST_QUERIES:
            context = Context(tags=context_tags)
            retrieved = retriever.retrieve(query_text, context, top_k=10)
            retrieved_ids = {r.id for r in retrieved}
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=10)
            all_p.append(p)
            all_r.append(r)
            all_f1.append(f)

        avg_p = sum(all_p) / len(all_p)
        avg_r = sum(all_r) / len(all_r)
        avg_f1 = sum(all_f1) / len(all_f1)
        ci_f1 = bootstrap_ci(all_f1)
        theta_results[theta] = (avg_p, avg_r, avg_f1, ci_f1)
        print(f"  theta={theta:.1f}: P@10={avg_p:.3f}, R@10={avg_r:.3f}, F1@10={format_ci(ci_f1)}")

    # --- Top-K sweep ---
    print("\n" + "=" * 60)
    print("Top-K sweep: K from 3 to 20")
    print("=" * 60)

    k_values = [3, 5, 8, 10, 12, 15, 20]
    k_results = {}

    config = Config(
        embedding_model=semantic_model,
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.3,
        default_threshold=0.3,
        default_top_k=20,  # Set high, we'll truncate manually
        mandatory_tags=["safety"],
    )
    retriever = Retriever(corpus, config=config)
    retriever.build_index()

    for k in k_values:
        all_p, all_r, all_f1 = [], [], []
        for query_text, context_tags, expected_ids in TEST_QUERIES:
            context = Context(tags=context_tags)
            retrieved = retriever.retrieve(query_text, context, top_k=k)
            retrieved_ids = {r.id for r in retrieved}
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=k)
            all_p.append(p)
            all_r.append(r)
            all_f1.append(f)

        avg_p = sum(all_p) / len(all_p)
        avg_r = sum(all_r) / len(all_r)
        avg_f1 = sum(all_f1) / len(all_f1)
        ci_f1 = bootstrap_ci(all_f1)
        k_results[k] = (avg_p, avg_r, avg_f1, ci_f1)
        print(f"  K={k:2d}: P@K={avg_p:.3f}, R@K={avg_r:.3f}, F1@K={format_ci(ci_f1)}")

    # --- LaTeX tables ---
    print("\n\n% === LaTeX: Alpha Sensitivity (K=10) ===")
    print("\\begin{table}[t]")
    print("\\caption{Priority weight $\\alpha$ at $k{=}10$: with precise \\texttt{required\\_tags},")
    print("scope filtering selects $\\leq k$ instructions regardless of $\\alpha$.}")
    print("\\label{tab:alpha-k10}")
    print("\\begin{tabular}{@{}cccc@{}}")
    print("\\toprule")
    print("$\\alpha$ & P@10 & R@10 & F1@10 (95\\% CI) \\\\")
    print("\\midrule")
    for alpha in alpha_values:
        p, r, f, ci = alpha_results_k10[alpha]
        from stat_utils import format_ci_latex
        print(f"{alpha:.1f} & {p:.3f} & {r:.3f} & ${format_ci_latex(ci)}$ \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")

    print("\n% === LaTeX: Alpha Sensitivity (K=5, semantic) ===")
    print("\\begin{table}[t]")
    print("\\caption{Priority weight $\\alpha$ at $k{=}5$ with semantic embeddings.")
    print("95\\% bootstrap CIs (10,000 iterations) over queries.}")
    print("\\label{tab:alpha-k5}")
    print("\\begin{tabular}{@{}cccc@{}}")
    print("\\toprule")
    print("$\\alpha$ & P@5 & R@5 & F1@5 (95\\% CI) \\\\")
    print("\\midrule")
    for alpha in alpha_values:
        p, r, f, ci = alpha_results_k5[alpha]
        print(f"{alpha:.1f} & {p:.3f} & {r:.3f} & ${format_ci_latex(ci)}$ \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")

    print("\n% === LaTeX: Theta Sensitivity ===")
    print("\\begin{table}[t]")
    print("\\caption{Effect of similarity threshold $\\theta$ ($\\alpha=0.3$, $k=10$).")
    print("95\\% bootstrap CIs over queries.}")
    print("\\label{tab:theta}")
    print("\\begin{tabular}{@{}cccc@{}}")
    print("\\toprule")
    print("$\\theta$ & P@10 & R@10 & F1@10 (95\\% CI) \\\\")
    print("\\midrule")
    for theta in theta_values:
        p, r, f, ci = theta_results[theta]
        print(f"{theta:.1f} & {p:.3f} & {r:.3f} & ${format_ci_latex(ci)}$ \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")

    print("\n% === LaTeX: Top-K Sensitivity ===")
    print("\\begin{table}[t]")
    print("\\caption{Effect of $k$ on retrieval quality ($\\alpha=0.3$, $\\theta=0.3$).")
    print("95\\% bootstrap CIs over queries.}")
    print("\\label{tab:topk}")
    print("\\begin{tabular}{@{}cccc@{}}")
    print("\\toprule")
    print("$k$ & P@$k$ & R@$k$ & F1@$k$ (95\\% CI) \\\\")
    print("\\midrule")
    for k in k_values:
        p, r, f, ci = k_results[k]
        print(f"{k} & {p:.3f} & {r:.3f} & ${format_ci_latex(ci)}$ \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic", action="store_true",
                        help="Use sentence-transformers instead of hash embeddings")
    args = parser.parse_args()
    run_ablation(use_semantic=args.semantic)
