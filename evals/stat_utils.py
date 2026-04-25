"""Shared statistical utilities for BEAR evaluation scripts.

Provides bootstrap confidence intervals, hypothesis tests, and effect sizes
for use across all evaluation scripts.
"""

from __future__ import annotations

import numpy as np


def bootstrap_ci(
    values: np.ndarray | list[float],
    n_boot: int = 10000,
    alpha: float = 0.05,
    seed: int = 42,
    statistic: str = "mean",
) -> dict:
    """Bootstrap confidence interval for a statistic.

    Args:
        values: Array of per-query or per-trial metric values.
        n_boot: Number of bootstrap iterations.
        alpha: Significance level (0.05 → 95% CI).
        seed: Random seed for reproducibility.
        statistic: "mean" or "median".

    Returns:
        Dict with point_estimate, ci_lower, ci_upper, std, n.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"point_estimate": float("nan"), "ci_lower": float("nan"),
                "ci_upper": float("nan"), "std": float("nan"), "n": 0}

    rng = np.random.default_rng(seed)
    stat_fn = np.mean if statistic == "mean" else np.median
    point = float(stat_fn(arr))

    boot_stats = np.array([
        stat_fn(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    lo = float(np.percentile(boot_stats, 100 * alpha / 2))
    hi = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))

    return {
        "point_estimate": point,
        "ci_lower": lo,
        "ci_upper": hi,
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "n": len(arr),
    }


def welch_ttest(a: np.ndarray | list[float], b: np.ndarray | list[float]) -> dict:
    """Welch's t-test for independent samples."""
    from scipy import stats
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    t_stat, p_val = stats.ttest_ind(a, b, equal_var=False)
    return {
        "t_statistic": float(t_stat),
        "p_value": float(p_val),
        "mean_a": float(np.mean(a)),
        "mean_b": float(np.mean(b)),
        "n_a": len(a),
        "n_b": len(b),
    }


def mann_whitney_u(a: np.ndarray | list[float], b: np.ndarray | list[float]) -> dict:
    """Mann-Whitney U test (non-parametric)."""
    from scipy import stats
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    stat, p_val = stats.mannwhitneyu(a, b, alternative="two-sided")
    return {
        "U_statistic": float(stat),
        "p_value": float(p_val),
        "n_a": len(a),
        "n_b": len(b),
    }


def cohens_d_ind(a: np.ndarray | list[float], b: np.ndarray | list[float]) -> float:
    """Cohen's d for independent samples (pooled SD)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = len(a), len(b)
    pooled_std = np.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1))
                         / (na + nb - 2))
    if pooled_std == 0:
        return 0.0
    return float((np.mean(a) - np.mean(b)) / pooled_std)


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm-Bonferroni step-down correction for multiple comparisons.

    Args:
        p_values: Dict mapping label → raw p-value.
        alpha: Family-wise error rate.

    Returns:
        Dict mapping label → {raw_p, adjusted_p, significant, rank}.
    """
    sorted_items = sorted(p_values.items(), key=lambda x: x[1])
    m = len(sorted_items)
    results = {}
    for rank, (label, raw_p) in enumerate(sorted_items):
        adjusted_p = min(raw_p * (m - rank), 1.0)
        results[label] = {
            "raw_p": raw_p,
            "adjusted_p": adjusted_p,
            "significant": adjusted_p < alpha,
            "rank": rank + 1,
        }
    # Enforce monotonicity (adjusted p-values must be non-decreasing)
    prev = 0.0
    for label, _ in sorted_items:
        results[label]["adjusted_p"] = max(results[label]["adjusted_p"], prev)
        prev = results[label]["adjusted_p"]
        results[label]["significant"] = results[label]["adjusted_p"] < alpha
    return results


def format_ci(ci: dict, precision: int = 3) -> str:
    """Format a CI dict as a string like '0.969 [0.955, 0.982]'."""
    fmt = f"{{:.{precision}f}}"
    return (f"{fmt.format(ci['point_estimate'])} "
            f"[{fmt.format(ci['ci_lower'])}, {fmt.format(ci['ci_upper'])}]")


def format_ci_latex(ci: dict, precision: int = 3) -> str:
    """Format a CI dict for LaTeX like '0.969\\;[0.955,\\;0.982]'."""
    fmt = f"{{:.{precision}f}}"
    return (f"{fmt.format(ci['point_estimate'])}\\;"
            f"[{fmt.format(ci['ci_lower'])},\\;{fmt.format(ci['ci_upper'])}]")
