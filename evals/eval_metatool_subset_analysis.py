"""MetaTool retained vs. excluded subset analysis (Reviewer 1 #5).

Background
----------
The MetaTool+Tags experiment in the manuscript reports results on the
10,051 queries whose ground-truth target tool received a non-empty
tag list from the LLM tag-generation pass. The other 11,060 queries
were excluded. Reviewer 1 asked whether the retained subset differs
systematically from the excluded portion, which would imply selection
bias in the reported gains.

This script answers that question by computing, for the retained and
excluded query subsets:

  (1) query length in characters and in tokens (whitespace split)
  (2) lexical overlap between query and ground-truth tool name
  (3) ground-truth tool description length
  (4) number of distinct ground-truth tools represented

For each property we report mean, std, and a two-sample t-test (Welch)
plus a Mann-Whitney U test. We also report Cohen's d so the reviewer can
judge effect size, not just significance.

Output
------
  results/metatool_subset_analysis.json   structured per-property output
  results/metatool_subset_output.txt      printed log (tee'd)

A short LaTeX block is printed for inclusion in the manuscript's
MetaTool methodology appendix.

Usage
-----
    python evals/eval_metatool_subset_analysis.py

Deterministic. No LLM calls. Runs in under 10 seconds.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "evals" / "data" / "external_benchmarks" / "metatool"
RESULTS_DIR = REPO_ROOT / "results"


def load_data():
    """Load the MetaTool corpus and tag files."""
    with (DATA_DIR / "plugin_info.json").open() as f:
        plugin_info = json.load(f)
    with (DATA_DIR / "plugin_tags.json").open() as f:
        plugin_tags = json.load(f)
    queries: list[tuple[str, str]] = []
    with (DATA_DIR / "all_clean_data.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            queries.append((row["Query"].strip(), row["Tool"].strip()))
    return plugin_info, plugin_tags, queries


def tool_description_lookup(plugin_info: list[dict]) -> dict[str, str]:
    """Build a name_for_model -> description_for_model map."""
    out: dict[str, str] = {}
    for entry in plugin_info:
        name = entry.get("name_for_model")
        if name:
            desc = entry.get("description_for_model", "") or ""
            out[name] = desc
    return out


def split_queries(
    queries: list[tuple[str, str]],
    plugin_tags: dict[str, list[str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Partition queries into retained (target tool has non-empty tags)
    and excluded (target tool has empty or missing tags).
    """
    retained: list[tuple[str, str]] = []
    excluded: list[tuple[str, str]] = []
    for q, tool in queries:
        tags = plugin_tags.get(tool, [])
        if tags:
            retained.append((q, tool))
        else:
            excluded.append((q, tool))
    return retained, excluded


def lexical_overlap(query: str, tool_name: str) -> float:
    """Fraction of whitespace-split tokens in `tool_name` (split on
    underscores and CamelCase boundaries) that appear in the query.
    """
    import re

    # Split tool name into subtokens
    parts = re.split(r"[_\s]+|(?<=[a-z])(?=[A-Z])", tool_name)
    tool_tokens = {p.lower() for p in parts if p}
    if not tool_tokens:
        return 0.0
    query_tokens = {t.lower().strip(".,?!") for t in query.split()}
    if not query_tokens:
        return 0.0
    hits = tool_tokens & query_tokens
    return len(hits) / len(tool_tokens)


def cohen_d_independent(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d for two independent samples (pooled std)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    va = a.var(ddof=1)
    vb = b.var(ddof=1)
    pooled = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def describe(name: str, ret: np.ndarray, exc: np.ndarray) -> dict:
    """Compute summary statistics + tests for one property."""
    t_stat, t_p = stats.ttest_ind(ret, exc, equal_var=False)
    try:
        u_stat, u_p = stats.mannwhitneyu(ret, exc, alternative="two-sided")
    except ValueError:
        u_stat, u_p = float("nan"), float("nan")
    d = cohen_d_independent(ret, exc)
    return {
        "property": name,
        "retained": {
            "n": int(len(ret)),
            "mean": float(ret.mean()),
            "std": float(ret.std(ddof=1)) if len(ret) > 1 else 0.0,
            "median": float(np.median(ret)),
        },
        "excluded": {
            "n": int(len(exc)),
            "mean": float(exc.mean()),
            "std": float(exc.std(ddof=1)) if len(exc) > 1 else 0.0,
            "median": float(np.median(exc)),
        },
        "welch_t": float(t_stat),
        "welch_p": float(t_p),
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p": float(u_p),
        "cohen_d": float(d),
    }


def fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "n/a"
    if p < 1e-4:
        return "<0.0001"
    return f"{p:.4f}"


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    log_path = RESULTS_DIR / "metatool_subset_output.txt"
    log_handle = log_path.open("w", encoding="utf-8")

    def out(line: str = "") -> None:
        print(line)
        log_handle.write(line + "\n")

    try:
        t0 = time.time()
        out("=== MetaTool retained vs. excluded subset analysis ===\n")

        plugin_info, plugin_tags, queries = load_data()
        out(f"Loaded {len(plugin_info)} tools, {len(plugin_tags)} tag entries, {len(queries)} queries")

        # Show how many tools have empty tag lists
        empty_tag_tools = [k for k, v in plugin_tags.items() if not v]
        out(f"Tools with empty tag list: {len(empty_tag_tools)}")

        # Tools missing from the tag file altogether
        info_names = {e.get("name_for_model") for e in plugin_info if e.get("name_for_model")}
        missing_in_tags = info_names - set(plugin_tags.keys())
        out(f"Tools in plugin_info but missing from plugin_tags: {len(missing_in_tags)}")

        retained, excluded = split_queries(queries, plugin_tags)
        out(f"\nRetained queries (target tool has non-empty tags): {len(retained)}")
        out(f"Excluded queries (target tool has empty or missing tags): {len(excluded)}")

        # Build description lookup
        desc_lookup = tool_description_lookup(plugin_info)

        # Compute per-query properties
        def query_props(pairs: list[tuple[str, str]]):
            n = len(pairs)
            qchars = np.zeros(n)
            qtoks = np.zeros(n)
            overlap = np.zeros(n)
            desc_chars = np.zeros(n)
            for i, (q, tool) in enumerate(pairs):
                qchars[i] = len(q)
                qtoks[i] = len(q.split())
                overlap[i] = lexical_overlap(q, tool)
                desc_chars[i] = len(desc_lookup.get(tool, ""))
            return qchars, qtoks, overlap, desc_chars

        ret_qchars, ret_qtoks, ret_overlap, ret_desc = query_props(retained)
        exc_qchars, exc_qtoks, exc_overlap, exc_desc = query_props(excluded)

        rows = [
            describe("Query length (characters)", ret_qchars, exc_qchars),
            describe("Query length (whitespace tokens)", ret_qtoks, exc_qtoks),
            describe("Query-name lexical overlap (fraction of tool subtokens in query)", ret_overlap, exc_overlap),
            describe("Ground-truth tool description length (characters)", ret_desc, exc_desc),
        ]

        # Distinct tool counts
        ret_tools = {t for _, t in retained}
        exc_tools = {t for _, t in excluded}
        out(f"\nDistinct ground-truth tools represented:")
        out(f"  retained: {len(ret_tools)}")
        out(f"  excluded: {len(exc_tools)}")

        out("\n=== Per-property comparison (retained vs. excluded) ===\n")
        header = (
            f"{'Property':<60}  "
            f"{'retained mean':>14}  "
            f"{'excluded mean':>14}  "
            f"{'Welch p':>10}  "
            f"{'MW p':>10}  "
            f"{'Cohen d':>9}"
        )
        out(header)
        out("-" * len(header))
        for r in rows:
            out(
                f"{r['property']:<60}  "
                f"{r['retained']['mean']:>14.3f}  "
                f"{r['excluded']['mean']:>14.3f}  "
                f"{fmt_p(r['welch_p']):>10}  "
                f"{fmt_p(r['mannwhitney_p']):>10}  "
                f"{r['cohen_d']:>+9.3f}"
            )

        # LaTeX table
        out("\n=== LaTeX table (paste into manuscript appendix) ===\n")
        out(r"\begin{table}[t]")
        out(
            r"  \caption{MetaTool retained vs.\ excluded subset comparison "
            r"(retained: 10{,}051 queries whose ground-truth target tool "
            r"received a non-empty LLM-generated tag list; excluded: "
            r"11{,}060 queries whose target tool had an empty or missing "
            r"tag list). Welch's two-sample $t$-test and Mann-Whitney $U$ "
            r"test reported. Cohen's $d$ is the standardized mean "
            r"difference (retained $-$ excluded).}"
        )
        out(r"  \label{tab:metatool-subset}")
        out(r"  \centering")
        out(r"  \small")
        out(r"  \setlength{\tabcolsep}{4pt}")
        out(r"  \begin{tabular}{@{}l c c c c c@{}}")
        out(r"    \toprule")
        out(r"    Property & Retained mean & Excluded mean & Welch $p$ & MW $p$ & Cohen $d$ \\")
        out(r"    \midrule")
        for r in rows:
            # Use a shorter label
            label_map = {
                "Query length (characters)": "Query length (chars)",
                "Query length (whitespace tokens)": "Query length (tokens)",
                "Query-name lexical overlap (fraction of tool subtokens in query)": "Query--name lexical overlap",
                "Ground-truth tool description length (characters)": "GT tool description length (chars)",
            }
            label = label_map.get(r["property"], r["property"])
            ret_m = r["retained"]["mean"]
            exc_m = r["excluded"]["mean"]
            wp = fmt_p(r["welch_p"]).replace("<", r"$<$")
            mp = fmt_p(r["mannwhitney_p"]).replace("<", r"$<$")
            out(
                f"    {label} & "
                f"{ret_m:.3f} & {exc_m:.3f} & "
                f"{wp} & {mp} & {r['cohen_d']:+.3f} \\\\"
            )
        out(r"    \bottomrule")
        out(r"  \end{tabular}")
        out(r"\end{table}")

        # JSON dump
        full_result = {
            "n_retained_queries": int(len(retained)),
            "n_excluded_queries": int(len(excluded)),
            "n_distinct_retained_tools": int(len(ret_tools)),
            "n_distinct_excluded_tools": int(len(exc_tools)),
            "n_total_tools": int(len(plugin_info)),
            "n_tools_with_empty_tags": int(len(empty_tag_tools)),
            "n_tools_missing_from_tag_file": int(len(missing_in_tags)),
            "comparisons": rows,
        }
        json_path = RESULTS_DIR / "metatool_subset_analysis.json"
        with json_path.open("w") as f:
            json.dump(full_result, f, indent=2)
        out(f"\nWrote {json_path}")
        out(f"Wrote {log_path}")
        out(f"\nElapsed: {time.time() - t0:.1f}s")

        # Reproducibility footer pipes through out() so it lands in the log.
        import io
        buf = io.StringIO()
        _orig_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_repro_footer(
                extra={
                    "n_retained_queries": int(full_result["n_retained_queries"]),
                    "n_excluded_queries": int(full_result["n_excluded_queries"]),
                }
            )
        finally:
            sys.stdout = _orig_stdout
        for line in buf.getvalue().rstrip("\n").splitlines():
            out(line)

        out("")
        out("To commit these results:")
        out(f"  git add {json_path.relative_to(REPO_ROOT)} \\")
        out(f"          {log_path.relative_to(REPO_ROOT)}")
    finally:
        log_handle.close()


if __name__ == "__main__":
    main()
