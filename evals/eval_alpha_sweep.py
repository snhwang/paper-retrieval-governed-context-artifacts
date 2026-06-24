"""Alpha (priority-weighting) sweep on the Pet Simulation corpus.

Follow-up to eval_governance_decomposed.py.

Background
----------
The decomposed ablation compared a single binary toggle (alpha=0.3 vs
alpha=0) and found alpha to have no measurable effect across five
backends.  That null result is narrower than ``priority weighting
doesn't matter'': two competing hypotheses remain consistent with it,

  (a) the priority field is genuinely uninformative for Pet Sim
      ranking, and any alpha in [0, 1) gives equivalent F1;

  (b) alpha=0.3 happens to be near a plateau optimum, but a larger
      alpha could yield meaningful gains or losses.

We sweep alpha over a denser grid spanning the full feasible range to
disambiguate.

Score function (from the manuscript, with default min-max normalisation):

    score(q, d) = (1 - alpha) * sim_tilde(q, d) + alpha * priority(d) / 100

so alpha = 0 -> similarity-only ranking, alpha = 1 -> priority-only
ranking (similarity entirely ignored).

What this script does
---------------------
For a single backend (default BGE) and the full Pet Simulation corpus:

  - For each alpha in ALPHA_GRID, build a retriever with full governance
    (required_tags + conflict resolution + mandatory tags ON) but with
    the chosen alpha as the priority weight.
  - Evaluate strict F1 at k=10 on the 60-query standard test set.
  - Bootstrap 95% CIs and paired bootstrap p-values vs. the default
    alpha=0.3.
  - Report the alpha that maximises F1, and characterise the shape of
    the curve (flat / peaked / monotone).

Usage
-----
    python evals/eval_alpha_sweep.py
    python evals/eval_alpha_sweep.py --backend bm25
    python evals/eval_alpha_sweep.py --backends bge bge-m3 qwen3-4b bm25
    python evals/eval_alpha_sweep.py --alphas 0.0 0.1 0.2 0.3 0.5 0.7 0.9 1.0

Output
------
  - results/alpha_sweep_<backend>.json (per backend)
  - Printed LaTeX table for inclusion in the manuscript
  - Printed plain-text summary

The script is deterministic (no LLM calls). Default backend is BGE
because the decomposed ablation showed BGE-base has the strongest
mandatory-injection effect, which makes it the backend most likely to
show a non-trivial alpha interaction.
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

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend
from eval_retrieval import TEST_QUERIES, compute_metrics
from eval_retrieval_backends import (
    BACKEND_CONFIGS,
    bootstrap_ci,
    paired_bootstrap_test,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOP_K = 10
DEFAULT_THRESHOLD = 0.3
DEFAULT_MANDATORY_TAGS = ["safety"]
BOOTSTRAP_ITERS = 10_000

# Default grid: dense around the default 0.3, plus endpoints 0.0 and 1.0
# to bracket the limiting behaviour.
DEFAULT_ALPHA_GRID = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]

# Default backend list mirrors the decomposed ablation so the full alpha
# sweep can be reproduced with a single invocation matching the
# manuscript's Table 12 backend set. To run only BGE (faster, ~100s),
# pass --backend bge explicitly.
DEFAULT_BACKENDS = ["bge", "bge-m3", "qwen3", "qwen3-4b", "bm25"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_pet_sim_corpus() -> Corpus:
    instructions_dir = project_root / "pet_sim" / "instructions"
    if not instructions_dir.exists():
        raise FileNotFoundError(
            f"Pet Sim instructions directory not found: {instructions_dir}"
        )
    return Corpus.from_directory(str(instructions_dir))


def make_retriever(corpus: Corpus, cfg_key: str, alpha: float) -> Retriever:
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
        priority_weight=alpha,
        default_threshold=DEFAULT_THRESHOLD,
        default_top_k=TOP_K,
        mandatory_tags=DEFAULT_MANDATORY_TAGS,
    )
    r = Retriever(corpus, config=config)
    r.build_index()
    return r


def evaluate(retriever: Retriever, queries) -> np.ndarray:
    out = []
    for q, tags, expected in queries:
        result = retriever.retrieve(q, Context(tags=tags), top_k=TOP_K)
        retrieved = {r.id for r in result}
        _, _, f = compute_metrics(retrieved, expected, k=TOP_K)
        out.append(f)
    return np.array(out)


def cohen_d_paired(a: np.ndarray, b: np.ndarray) -> float:
    diff = a - b
    if diff.std(ddof=1) == 0:
        return 0.0
    return float(diff.mean() / diff.std(ddof=1))


def fmt_ci(mean: float, lo: float, hi: float) -> str:
    return f"{mean:.3f} [{lo:.3f},{hi:.3f}]"


# ---------------------------------------------------------------------------
# Curve shape characterisation
# ---------------------------------------------------------------------------


def classify_curve(
    alphas: list[float],
    means: list[float],
    flat_tol: float = 0.005,
    decline_tol: float = 0.005,
) -> str:
    """Return a short qualitative label for the shape of the F1(alpha) curve.

    Diagnostics, checked in order:

      1. ``flat`` :
         The overall max-min is below ``flat_tol``.
      2. ``plateau-then-decline (plateau alpha <= X, decline starts at Y)`` :
         There is a contiguous prefix [0, X] on which max-min < flat_tol
         (the plateau), and the next alpha Y falls at least ``decline_tol``
         below the plateau mean.
      3. Same as (2) plus ``; collapse at alpha=1 (drop ...)`` when the mean
         at alpha=1 is at least 0.05 below the plateau mean.
      4. ``monotone increasing`` / ``monotone decreasing``.
      5. ``peaked at alpha=X``.
      6. ``mixed`` otherwise.

    Defaults are calibrated so the June 23 BGE sweep is labelled
    'plateau-then-decline (plateau alpha <= 0.30, decline starts at 0.50)'.
    """
    pts = sorted(zip(alphas, means), key=lambda x: x[0])
    a_arr = [a for a, _ in pts]
    m_arr = [m for _, m in pts]
    n = len(pts)

    overall_max = max(m_arr)
    overall_min = min(m_arr)

    if overall_max - overall_min < flat_tol:
        return f"flat (max-min < {flat_tol})"

    best_plateau_k = -1
    for k in range(n - 1):
        prefix = m_arr[: k + 1]
        if max(prefix) - min(prefix) >= flat_tol:
            break
        plateau_mean = sum(prefix) / len(prefix)
        if m_arr[k + 1] <= plateau_mean - decline_tol:
            best_plateau_k = k
    if best_plateau_k >= 0:
        plateau_alpha = a_arr[best_plateau_k]
        decline_alpha = a_arr[best_plateau_k + 1]
        plateau_mean = sum(m_arr[: best_plateau_k + 1]) / (best_plateau_k + 1)
        alpha_1_idx = next(
            (i for i, a in enumerate(a_arr) if a >= 1.0 - 1e-9), None
        )
        if (
            alpha_1_idx is not None
            and m_arr[alpha_1_idx] <= plateau_mean - 0.05
        ):
            drop = plateau_mean - m_arr[alpha_1_idx]
            return (
                f"plateau-then-decline (plateau alpha <= {plateau_alpha:.2f}, "
                f"decline starts at {decline_alpha:.2f}); "
                f"collapse at alpha=1 (drop {drop:+.3f})"
            )
        return (
            f"plateau-then-decline (plateau alpha <= {plateau_alpha:.2f}, "
            f"decline starts at {decline_alpha:.2f})"
        )

    diffs = [m_arr[i + 1] - m_arr[i] for i in range(n - 1)]
    if all(d >= -1e-4 for d in diffs):
        return "monotone increasing"
    if all(d <= 1e-4 for d in diffs):
        return "monotone decreasing"

    argmax = m_arr.index(overall_max)
    if (
        0 < argmax < n - 1
        and m_arr[0] <= overall_max - decline_tol
        and m_arr[-1] <= overall_max - decline_tol
    ):
        return f"peaked at alpha={a_arr[argmax]:.2f}"

    return "mixed"


# ---------------------------------------------------------------------------
# Per-backend sweep
# ---------------------------------------------------------------------------


def sweep_one_backend(
    backend_key: str,
    alphas: list[float],
    output_path: Path | None,
) -> dict:
    print(f"\n=== Alpha sweep ({backend_key}) ===\n")

    corpus = load_pet_sim_corpus()
    print(f"Corpus: {len(corpus)} instructions, {len(TEST_QUERIES)} standard queries")
    print(f"Alpha grid: {alphas}\n")

    # Cache the alpha=0.3 condition's per-query array for paired comparisons.
    f1_arrays: dict[float, np.ndarray] = {}
    for i, alpha in enumerate(alphas, 1):
        print(f"[{i}/{len(alphas)}] alpha = {alpha:.2f} ...")
        r = make_retriever(corpus, backend_key, alpha=alpha)
        f1_arrays[alpha] = evaluate(r, TEST_QUERIES)

    # Default baseline for paired comparisons
    default_alpha = 0.3 if 0.3 in f1_arrays else alphas[0]
    f1_default = f1_arrays[default_alpha]

    print(f"\n--- Results (backend = {backend_key}, paired vs. alpha = {default_alpha}) ---\n")
    header = (
        f"{'alpha':>6}  {'Strict F1 [95% CI]':<26}  {'Δ vs default':>14}  "
        f"{'Cohen d':>8}  {'p (paired)':>10}"
    )
    print(header)
    print("-" * len(header))

    rows = []
    for alpha in alphas:
        arr = f1_arrays[alpha]
        mean, lo, hi = bootstrap_ci(arr, BOOTSTRAP_ITERS)
        if alpha == default_alpha:
            delta = 0.0
            d = 0.0
            p = None
            p_str = "—"
        else:
            delta = mean - f1_default.mean()
            d = cohen_d_paired(f1_default, arr)
            p = paired_bootstrap_test(f1_default, arr, BOOTSTRAP_ITERS)
            p_str = f"<0.0001" if p < 1e-4 else f"{p:.4f}"
        print(
            f"{alpha:>6.2f}  {fmt_ci(mean, lo, hi):<26}  "
            f"{delta:+.3f}{'':<9}  {d:+.2f}{'':<3}  {p_str:>10}"
        )
        rows.append({
            "alpha": float(alpha),
            "n": len(TEST_QUERIES),
            "mean_f1": float(mean),
            "ci_lo": float(lo),
            "ci_hi": float(hi),
            "delta_vs_default": float(delta),
            "cohen_d_vs_default": float(d),
            "p_vs_default": float(p) if p is not None else None,
            "is_default": alpha == default_alpha,
        })

    means = [r["mean_f1"] for r in rows]
    best_idx = int(np.argmax(means))
    best_alpha = rows[best_idx]["alpha"]
    best_f1 = rows[best_idx]["mean_f1"]
    curve_shape = classify_curve(alphas, means)

    print(f"\nMax F1 = {best_f1:.3f} at alpha = {best_alpha:.2f}")
    print(f"Curve shape: {curve_shape}")

    result = {
        "backend": backend_key,
        "n_standard_queries": len(TEST_QUERIES),
        "top_k": TOP_K,
        "bootstrap_iters": BOOTSTRAP_ITERS,
        "threshold_default": DEFAULT_THRESHOLD,
        "mandatory_tags_default": DEFAULT_MANDATORY_TAGS,
        "default_alpha_baseline": default_alpha,
        "best_alpha": best_alpha,
        "best_f1": best_f1,
        "curve_shape": curve_shape,
        "rows": rows,
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(result, f, indent=2)
        print(f"\nWrote {output_path}")

    return result


# ---------------------------------------------------------------------------
# LaTeX rendering
# ---------------------------------------------------------------------------


def render_single_backend_latex(result: dict) -> str:
    rows = result["rows"]
    backend = result["backend"]
    default_alpha = result["default_alpha_baseline"]
    lines: list[str] = []
    lines.append(r"\begin{table}[t]")
    lines.append(
        r"  \caption{Effect of the priority-weighting coefficient $\alpha$ on "
        r"strict F1 at $k=10$ on Pet Simulation (60 standard queries, "
        + f"backend = {backend}"
        + r", full governance with all other mechanisms enabled). "
          r"The composite score is "
          r"$\operatorname{score}(q, d) = (1 - \alpha)\,\widetilde{\operatorname{sim}}(q, d) + "
          r"\alpha\,p(d)/100$. "
          r"95\% bootstrap CIs and paired bootstrap $p$-values vs.\ the default "
          r"$\alpha = " + f"{default_alpha:.1f}" + r"$ are reported.}"
    )
    lines.append(r"  \label{tab:alpha-sweep}")
    lines.append(r"  \centering")
    lines.append(r"  \small")
    lines.append(r"  \begin{tabular}{@{}c c c c c@{}}")
    lines.append(r"    \toprule")
    lines.append(r"    $\alpha$ & Strict F1 [95\% CI] & $\Delta$ vs. default & Cohen's $d$ & $p$ (paired) \\")
    lines.append(r"    \midrule")
    for r in rows:
        ci = f"{r['mean_f1']:.3f} [{r['ci_lo']:.3f},{r['ci_hi']:.3f}]"
        if r["is_default"]:
            delta = "---"
            d_str = "---"
            p_str = "---"
        else:
            delta = f"{r['delta_vs_default']:+.3f}"
            d_str = f"{r['cohen_d_vs_default']:+.2f}"
            if r["p_vs_default"] is None:
                p_str = "---"
            elif r["p_vs_default"] < 1e-4:
                p_str = r"$<$0.0001"
            else:
                p_str = f"{r['p_vs_default']:.4f}"
        lines.append(f"    {r['alpha']:.2f} & {ci} & {delta} & {d_str} & {p_str} \\\\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def render_combined_latex(per_backend: dict[str, dict]) -> str:
    backends = list(per_backend.keys())
    if not backends:
        return ""
    # Use the alpha grid from the first backend; assume all backends share it
    alphas = [r["alpha"] for r in per_backend[backends[0]]["rows"]]

    lines: list[str] = []
    lines.append(r"\begin{table}[t]")
    lines.append(
        r"  \caption{Alpha sweep across backends on Pet Simulation "
        r"(60 standard queries, $k=10$, full governance with all other "
        r"mechanisms enabled; 95\% bootstrap CIs). The composite score is "
        r"$\operatorname{score}(q, d) = (1 - \alpha)\,\widetilde{\operatorname{sim}}(q, d) + "
        r"\alpha\,p(d)/100$, where $\alpha = 0$ is similarity-only and "
        r"$\alpha = 1$ is priority-only ranking.}"
    )
    lines.append(r"  \label{tab:alpha-sweep-multi}")
    lines.append(r"  \centering")
    lines.append(r"  \small")
    lines.append(r"  \setlength{\tabcolsep}{4pt}")
    col_spec = "c " + "c " * len(backends)
    lines.append(r"  \begin{tabular}{@{}" + col_spec + r"@{}}")
    lines.append(r"    \toprule")
    header = r"    $\alpha$"
    for b in backends:
        header += f" & {b}"
    header += r" \\"
    lines.append(header)
    lines.append(r"    \midrule")

    for i, alpha in enumerate(alphas):
        cells = [f"{alpha:.2f}"]
        for b in backends:
            r = per_backend[b]["rows"][i]
            cells.append(f"{r['mean_f1']:.3f} [{r['ci_lo']:.3f},{r['ci_hi']:.3f}]")
        lines.append("    " + " & ".join(cells) + r" \\")

    lines.append(r"    \midrule")
    cells = ["best $\\alpha$"]
    for b in backends:
        cells.append(f"{per_backend[b]['best_alpha']:.2f}")
    lines.append("    " + " & ".join(cells) + r" \\")
    cells = ["curve shape"]
    for b in backends:
        cells.append(f"\\emph{{{per_backend[b]['curve_shape']}}}")
    lines.append("    " + " & ".join(cells) + r" \\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--backend",
        default=None,
        choices=list(BACKEND_CONFIGS.keys()),
        help="Single embedding backend key. Default: bge.",
    )
    p.add_argument(
        "--backends",
        nargs="+",
        default=None,
        choices=list(BACKEND_CONFIGS.keys()),
        help="List of backends to run. Overrides --backend.",
    )
    p.add_argument(
        "--alphas",
        nargs="+",
        type=float,
        default=None,
        help=(
            "Alpha grid. Default: "
            f"{' '.join(f'{a:.2f}' for a in DEFAULT_ALPHA_GRID)}."
        ),
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory to write per-backend JSON outputs.",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=Path("results/alpha_sweep_output.txt"),
        help=(
            "Tee printed output (tables + LaTeX) to this file in addition "
            "to stdout. Pass an empty string to disable."
        ),
    )
    return p.parse_args()


class _Tee:
    """Minimal stdout tee that mirrors writes into a list of streams.

    Forwards common attributes that downstream libraries (tqdm,
    transformers, sentence-transformers, etc.) probe on ``sys.stdout``
    — ``isatty``, ``fileno``, ``encoding``, ``closed``, ``buffer``,
    and so on — to the *primary* stream (the original stdout). This
    avoids ``AttributeError: '_Tee' object has no attribute 'isatty'``
    when libraries inspect stdout while building progress bars.
    """

    def __init__(self, *streams):
        # The first stream is treated as primary for attribute fall-back.
        if not streams:
            raise ValueError("_Tee needs at least one stream")
        self._streams = streams
        self._primary = streams[0]

    def write(self, data: str) -> int:  # type: ignore[override]
        for s in self._streams:
            s.write(data)
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self) -> bool:  # noqa: D401
        """Defer to the primary stream so tty-detecting code sees stdout."""
        try:
            return bool(self._primary.isatty())
        except Exception:  # noqa: BLE001
            return False

    def fileno(self) -> int:
        return self._primary.fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._primary, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._primary, "errors", None)

    @property
    def closed(self) -> bool:
        return getattr(self._primary, "closed", False)

    @property
    def buffer(self):
        return getattr(self._primary, "buffer")

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def __getattr__(self, name: str):
        # Final fallback: delegate any remaining unknown attribute to the
        # primary stream so this object is a faithful stdout-like.
        return getattr(self._primary, name)


def main() -> None:
    args = parse_args()
    if args.backends is not None:
        backends = args.backends
    elif args.backend is not None:
        backends = [args.backend]
    else:
        backends = DEFAULT_BACKENDS
    alphas = args.alphas if args.alphas is not None else DEFAULT_ALPHA_GRID

    log_handle = None
    original_stdout = sys.stdout
    if args.log_file and str(args.log_file).strip():
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log_file.open("w", encoding="utf-8")
        sys.stdout = _Tee(original_stdout, log_handle)  # type: ignore[assignment]

    try:
        t0 = time.time()
        per_backend: dict[str, dict] = {}
        for i, bk in enumerate(backends, 1):
            print(f"\n{'#' * 70}")
            print(f"#  Backend {i}/{len(backends)}: {bk}")
            print(f"{'#' * 70}")
            out_path = args.output_dir / f"alpha_sweep_{bk}.json"
            result = sweep_one_backend(bk, alphas, out_path)
            per_backend[bk] = result

        if len(backends) == 1:
            print("\n--- LaTeX table (paste into manuscript) ---\n")
            print(render_single_backend_latex(per_backend[backends[0]]))
        else:
            combined_path = args.output_dir / "alpha_sweep_all.json"
            combined_path.parent.mkdir(parents=True, exist_ok=True)
            with combined_path.open("w") as f:
                json.dump(per_backend, f, indent=2)
            print(f"\nWrote {combined_path}")
            print("\n--- COMBINED LaTeX table (paste into manuscript) ---\n")
            print(render_combined_latex(per_backend))

        print(f"\nElapsed: {time.time() - t0:.1f}s")
        if log_handle is not None:
            print(f"Full log written to {args.log_file}")
    finally:
        if log_handle is not None:
            sys.stdout = original_stdout
            log_handle.close()


if __name__ == "__main__":
    main()
