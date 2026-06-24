"""ToolBench with LLM-inferred categories (Reviewer 3 #7).

Background
----------
The ToolBench results in the manuscript use the benchmark's RapidAPI
category labels as ``required_tags``. Reviewer 3 correctly observed
that this gives BEAR access to oracle category labels that ToolLLM
and other zero-shot retrievers do not have. Comparing a two-stage
oracle-filtered pipeline against a one-stage zero-shot retriever is
structurally invalid.

This script answers Reviewer 3's structural-equivalence question with
data. Instead of using the benchmark's ground-truth category label, we
ask an LLM to infer the category from the query text alone, then use
that inferred category as the ``required_tags`` for BEAR retrieval.
This is the realistic deployment condition: a runtime classifier rather
than an oracle.

We measure two things.

  1. Classifier accuracy. How often does the LLM-inferred category
     match the benchmark's ground-truth category?

  2. Downstream retrieval quality. What is BEAR's Recall@K under
     LLM-inferred categories, compared to (a) BEAR with oracle
     categories, (b) BEAR with no governance.

The expected outcome is that inferred-category retrieval lands
between the oracle and no-governance numbers. The exact magnitude of
the shrinkage is itself an interesting result and lets us state
honestly how much of BEAR's ToolBench number comes from the
oracle-category advantage.

How it works
------------
The script reuses the existing ToolBench evaluation harness in
``eval_toolbench.py``: corpus loading, retriever construction, and
the metric loop. We only intervene to swap the per-query context
tag list, replacing the ground-truth category with an LLM-inferred
one.

The LLM is queried once per unique query. By default we cache results
to disk in ``results/toolbench_inferred_categories.json`` so reruns
are free.

Requirements
------------
- An LLM endpoint reachable from the script. We default to Anthropic
  Claude Sonnet via the official Messages API.
- ``ANTHROPIC_API_KEY`` must be set in the environment (or a .env file
  in the repo root) before running.
- For an OpenAI-compatible endpoint, pass ``--base-url`` and
  ``--model`` together with an ``OPENAI_API_KEY``.

Usage
-----
Quick smoke test (50 queries, ~1 minute of API calls)::

    python evals/eval_toolbench_inferred_categories.py --max-queries 50

Full run on all queries (cache-friendly, ~30 minutes first run)::

    python evals/eval_toolbench_inferred_categories.py

Override the LLM endpoint and model::

    python evals/eval_toolbench_inferred_categories.py \
        --provider openai --base-url https://api.openai.com/v1 \
        --model gpt-5.4-mini-2026-03-17

Outputs
-------
- ``results/toolbench_inferred_categories.json`` (LLM cache + metrics)
- ``results/toolbench_inferred_output.txt`` (tee'd printed log)
- A LaTeX block printed at the end for paste into the manuscript.

Cost (approximate)
------------------
At 1,100 queries with Claude Sonnet 4.6 at $3 per million input
tokens and $15 per million output tokens, the full run costs roughly
$0.10. We cache aggressively so reruns are free.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
except ImportError:
    pass

from bear import Corpus, Context  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

# Reuse the existing ToolBench harness
from eval_toolbench import (  # noqa: E402
    DEFAULT_TOP_K,
    EMBEDDING_MODEL,
    BOOTSTRAP_ITERS,
    PRIORITY_WEIGHT,
    THRESHOLD,
    build_retriever,
    evaluate_retriever,
    load_toolbench_corpus_and_queries,
    strip_governance,
)

# stat_utils.bootstrap_ci is in the artifacts repo
try:
    from stat_utils import bootstrap_ci
except ImportError:
    # Fallback: use the bootstrap_ci from eval_retrieval_backends.py
    from eval_retrieval_backends import bootstrap_ci


RESULTS_DIR = REPO_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)
CACHE_PATH = RESULTS_DIR / "toolbench_inferred_categories.json"


# ---------------------------------------------------------------------------
# Helpers: tag <-> category-label round-trip
# ---------------------------------------------------------------------------

def cat_label_to_tag(label: str) -> str:
    """Convert 'Travel & Local' -> 'travel-local' (matches eval_toolbench)."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a strict categorical classifier.
Given a user query, choose the single RapidAPI category from the
provided list that best matches the API the user is asking about.
Respond with ONLY the category name from the list, exactly as written.
No explanation, no quotes, no punctuation."""


def build_user_prompt(query: str, categories: list[str]) -> str:
    cat_block = "\n".join(f"- {c}" for c in categories)
    return (
        f"Categories (use exact text from this list):\n{cat_block}\n\n"
        f"Query: {query.strip()}\n\n"
        f"Category:"
    )


def call_anthropic(prompt_user: str, model: str, api_key: str) -> str:
    """Call Anthropic Messages API with retry on transient errors."""
    payload = {
        "model": model,
        "max_tokens": 64,
        "temperature": 0.0,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt_user}],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"].strip()
            raise RuntimeError(f"No text block in response: {data!r}")
        except Exception as e:  # noqa: BLE001
            if attempt == 4:
                raise
            wait = 2 ** attempt
            print(f"  Anthropic call failed ({e!r}); retrying in {wait}s")
            time.sleep(wait)


def call_openai_compat(
    prompt_user: str, model: str, api_key: str, base_url: str
) -> str:
    payload = {
        "model": model,
        "max_tokens": 64,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_user},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            if attempt == 4:
                raise
            wait = 2 ** attempt
            print(f"  OpenAI-compat call failed ({e!r}); retrying in {wait}s")
            time.sleep(wait)


def classify_query(
    query: str,
    categories: list[str],
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
) -> str:
    """Return the LLM's category choice (raw text, may need normalization)."""
    prompt = build_user_prompt(query, categories)
    if provider == "anthropic":
        return call_anthropic(prompt, model, api_key)
    return call_openai_compat(prompt, model, api_key, base_url or "")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def gather_categories(
    queries: list[tuple[str, list[str], set[str]]],
    category_map: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Return (category_labels_for_prompt, category_tags_for_retrieval).

    We use the human-readable labels in the LLM prompt because they are
    more discriminating than the lowercased-hyphen tag versions, but we
    use the tag versions inside the retriever to match the corpus's
    required_tags.
    """
    # category_map maps api_id -> tag (e.g. 'travel-local'). We need labels.
    # Build the inverse from the queries: each query's context_tags are
    # already the tag form of the ground-truth category. We don't have the
    # original human-readable labels at hand, so we reverse-engineer them
    # from the tag form by humanizing each tag once.
    all_tags: set[str] = set()
    for q in queries:
        # Queries may be 3- or 4-tuples
        tags = q[1]
        for t in tags:
            all_tags.add(t)
    for tag in category_map.values():
        all_tags.add(tag)
    # Humanize tag -> label
    sorted_tags = sorted(all_tags)
    labels = [humanize_tag(t) for t in sorted_tags]
    return labels, sorted_tags


def humanize_tag(tag: str) -> str:
    """tag 'travel-local' -> 'Travel & Local' (approximate inverse)."""
    parts = [p.capitalize() for p in tag.split("-") if p]
    # Heuristic: join two parts with & if both look like nouns; otherwise space
    if len(parts) == 2 and all(len(p) > 2 for p in parts):
        return f"{parts[0]} & {parts[1]}"
    return " ".join(parts)


def load_cache() -> dict:
    if CACHE_PATH.exists():
        with CACHE_PATH.open() as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with CACHE_PATH.open("w") as f:
        json.dump(cache, f, indent=2)


def infer_categories(
    queries: list[tuple[str, list[str], set[str]]],
    category_labels: list[str],
    label_to_tag: dict[str, str],
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
    cache: dict,
) -> tuple[list[str], int]:
    """Return (per-query-inferred-tag, n_new_calls).

    Falls back to the empty string when the LLM produces an out-of-vocab
    label.
    """
    inferred_tags: list[str] = []
    n_new = 0
    t_lookup = {lab.lower(): lab for lab in category_labels}
    for i, qtuple in enumerate(queries):
        q = qtuple[0]
        if q in cache:
            label = cache[q]
        else:
            label = classify_query(
                q, category_labels, provider, model, api_key, base_url
            )
            cache[q] = label
            n_new += 1
            if n_new % 25 == 0:
                save_cache(cache)
                print(f"  Classified {n_new} new queries; cache saved")
        # Normalize
        chosen = label.strip().splitlines()[0].strip()
        chosen_lc = chosen.lower()
        # Best-effort match against the closed vocabulary
        if chosen in label_to_tag:
            inferred_tags.append(label_to_tag[chosen])
        elif chosen_lc in {k.lower() for k in label_to_tag}:
            for k, v in label_to_tag.items():
                if k.lower() == chosen_lc:
                    inferred_tags.append(v)
                    break
        else:
            # Try direct tag form
            tag_form = cat_label_to_tag(chosen)
            if tag_form in label_to_tag.values():
                inferred_tags.append(tag_form)
            else:
                inferred_tags.append("")  # out-of-vocab -> no required_tags
    save_cache(cache)
    return inferred_tags, n_new


def classifier_accuracy(
    queries: list[tuple[str, list[str], set[str]]],
    inferred_tags: list[str],
) -> float:
    """How often does the inferred tag equal the ground-truth tag?"""
    correct = 0
    for qtuple, inf in zip(queries, inferred_tags):
        gt_tags = qtuple[1]
        if not gt_tags:
            continue
        gt = gt_tags[0]  # primary category
        if inf == gt:
            correct += 1
    return correct / len(queries) if queries else 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Limit number of queries (for quick testing). Default: all queries.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"k for Recall@k. Default: {DEFAULT_TOP_K}.",
    )
    p.add_argument(
        "--provider",
        choices=["anthropic", "openai"],
        default="anthropic",
        help="LLM provider (default: anthropic for Claude Sonnet).",
    )
    p.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Model name. Anthropic default 'claude-sonnet-4-6'; for "
        "OpenAI-compatible endpoints pass --model gpt-5.4-mini-2026-03-17 etc.",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help="For --provider openai: base URL of the OpenAI-compatible API.",
    )
    p.add_argument(
        "--clear-cache",
        action="store_true",
        help="Ignore the cached LLM classifications and re-run all calls.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    log_path = RESULTS_DIR / "toolbench_inferred_output.txt"
    log_handle = log_path.open("w", encoding="utf-8")

    class _Tee:
        def __init__(self, *ss):
            self.ss = ss

        def write(self, d):
            for s in self.ss:
                s.write(d)
            return len(d)

        def flush(self):
            for s in self.ss:
                try:
                    s.flush()
                except Exception:  # noqa: BLE001
                    pass

        def __getattr__(self, n):
            return getattr(self.ss[0], n)

    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, log_handle)

    try:
        t0 = time.time()
        print("=== ToolBench with LLM-inferred categories ===\n")

        # API key
        if args.provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise SystemExit(
                    "ANTHROPIC_API_KEY is not set. Add it to your environment "
                    "or to a .env file in the repo root before running."
                )
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise SystemExit(
                    "OPENAI_API_KEY is not set. Add it to your environment or "
                    "to a .env file before running."
                )
            if not args.base_url:
                raise SystemExit(
                    "--base-url is required when --provider openai is used."
                )

        # Load corpus + queries
        print("Loading ToolBench corpus and queries ...")
        corpus, queries, category_map = load_toolbench_corpus_and_queries(
            max_queries=args.max_queries
        )
        print(f"Corpus: {len(corpus)} APIs, {len(queries)} queries")

        # Gather category labels for the LLM prompt
        label_list, tag_list = gather_categories(queries, category_map)
        label_to_tag = dict(zip(label_list, tag_list))
        print(f"Closed category vocabulary: {len(label_list)} categories\n")

        # Cache
        cache = {} if args.clear_cache else load_cache()
        print(f"LLM cache: {len(cache)} pre-computed classifications\n")

        print(f"Classifying {len(queries)} queries with {args.provider} {args.model} ...")
        t_clf = time.time()
        inferred_tags, n_new = infer_categories(
            queries,
            label_list,
            label_to_tag,
            args.provider,
            args.model,
            api_key,
            args.base_url,
            cache,
        )
        print(f"  {n_new} new LLM calls; {len(queries) - n_new} served from cache")
        print(f"  Classification time: {time.time() - t_clf:.1f}s\n")

        clf_acc = classifier_accuracy(queries, inferred_tags)
        print(f"Classifier top-1 accuracy vs. benchmark gold category: {clf_acc:.3f}\n")

        # Build inferred-category queries (3-tuple shape, which the patched
        # evaluate_retriever accepts alongside the original 4-tuple shape).
        inferred_queries = []
        n_oov = 0
        for qtuple, inf in zip(queries, inferred_tags):
            q = qtuple[0]
            expected = qtuple[2]
            if inf:
                inferred_queries.append((q, [inf], expected))
            else:
                inferred_queries.append((q, [], expected))
                n_oov += 1
        if n_oov:
            print(f"  OOV classifications (no required_tags applied): {n_oov}")

        # Conditions to evaluate
        print(f"\nBuilding retrievers and evaluating Recall@{args.top_k} ...")
        # build_retriever applies PRIORITY_WEIGHT internally when governance=True
        # and zero when governance=False. The bge backend matches the
        # manuscript ToolBench condition (BGE-base).
        retriever_gov = build_retriever(
            corpus, backend="bge", governance=True
        )
        retriever_no_gov = build_retriever(
            strip_governance(corpus), backend="bge", governance=False
        )

        print("  [1/3] BEAR + oracle categories (the manuscript number) ...")
        m_oracle = evaluate_retriever(retriever_gov, queries, top_k=args.top_k, use_tags=True)
        print("  [2/3] BEAR + LLM-inferred categories (the new condition) ...")
        m_infer = evaluate_retriever(retriever_gov, inferred_queries, top_k=args.top_k, use_tags=True)
        print("  [3/3] BEAR with no governance (lower bound) ...")
        m_no_gov = evaluate_retriever(retriever_no_gov, queries, top_k=args.top_k, use_tags=False)

        rows = []
        for name, m in [
            ("oracle", m_oracle),
            ("inferred", m_infer),
            ("no_governance", m_no_gov),
        ]:
            ci = {}
            for k in ("recall", "ndcg", "f1"):
                out = bootstrap_ci(m[k], BOOTSTRAP_ITERS)
                # stat_utils.bootstrap_ci returns a dict with point_estimate /
                # ci_lower / ci_upper. The fallback in eval_retrieval_backends.py
                # returns (mean, lo, hi). Accept either.
                if isinstance(out, dict):
                    mean, lo, hi = out["point_estimate"], out["ci_lower"], out["ci_upper"]
                else:
                    mean, lo, hi = out
                ci[k] = {"mean": float(mean), "ci_lo": float(lo), "ci_hi": float(hi)}
            rows.append({"condition": name, **ci})

        print(f"\n--- Recall@{args.top_k}, NDCG@{args.top_k}, F1@{args.top_k} ---\n")
        header = f"{'Condition':<22}  {'Recall@k':>20}  {'NDCG@k':>20}  {'F1@k':>20}"
        print(header)
        print("-" * len(header))
        for r in rows:
            print(
                f"{r['condition']:<22}  "
                f"{r['recall']['mean']:.3f} [{r['recall']['ci_lo']:.2f},{r['recall']['ci_hi']:.2f}]  "
                f"{r['ndcg']['mean']:.3f} [{r['ndcg']['ci_lo']:.2f},{r['ndcg']['ci_hi']:.2f}]  "
                f"{r['f1']['mean']:.3f} [{r['f1']['ci_lo']:.2f},{r['f1']['ci_hi']:.2f}]"
            )

        # LaTeX table for paste
        print("\n--- LaTeX table (paste into manuscript) ---\n")
        print(r"\begin{table}[t]")
        print(
            rf"  \caption{{ToolBench retrieval under three category-tag conditions "
            rf"(BGE-base backend, {len(queries)} queries, $k = {args.top_k}$, 95\% "
            rf"bootstrap CIs). The ``oracle'' condition uses the benchmark's "
            rf"ground-truth category labels as \texttt{{required\_tags}} (the "
            rf"original manuscript condition). The ``inferred'' condition uses "
            rf"an LLM classifier ({args.model}) to infer the category from "
            rf"query text alone with no access to ground-truth labels (top-1 "
            rf"classifier accuracy = {clf_acc:.3f}). The ``no governance'' "
            rf"condition strips all scope metadata.}}"
        )
        print(r"  \label{tab:toolbench-inferred}")
        print(r"  \centering")
        print(r"  \small")
        print(r"  \begin{tabular}{@{}l c c c@{}}")
        print(r"    \toprule")
        print(rf"    Condition & Recall@{args.top_k} & NDCG@{args.top_k} & F1@{args.top_k} \\")
        print(r"    \midrule")
        for r in rows:
            label = {
                "oracle": "Oracle categories",
                "inferred": "LLM-inferred categories",
                "no_governance": "No governance",
            }[r["condition"]]
            ci_str = lambda d: f"{d['mean']:.3f} [{d['ci_lo']:.2f},{d['ci_hi']:.2f}]"
            print(
                f"    {label} & {ci_str(r['recall'])} & "
                f"{ci_str(r['ndcg'])} & {ci_str(r['f1'])} \\\\"
            )
        print(r"    \bottomrule")
        print(r"  \end{tabular}")
        print(r"\end{table}")

        # Save JSON
        full = {
            "model": args.model,
            "provider": args.provider,
            "top_k": args.top_k,
            "n_queries": len(queries),
            "classifier_top1_accuracy": float(clf_acc),
            "n_oov_classifications": int(n_oov),
            "rows": rows,
        }
        out_path = RESULTS_DIR / "toolbench_inferred_metrics.json"
        with out_path.open("w") as f:
            json.dump(full, f, indent=2)
        print(f"\nWrote {out_path}")
        print(f"Wrote {log_path}")
        print(f"Cache: {CACHE_PATH}")
        print(f"\nElapsed: {time.time() - t0:.1f}s")

        # Reproducibility footer (captured by the tee into log_path)
        print_repro_footer(
            extra={
                "provider": args.provider,
                "model": args.model,
                "top_k": args.top_k,
                "n_queries": len(queries),
                "classifier_top1_accuracy": float(clf_acc),
                "n_new_llm_calls": int(n_new),
            }
        )

        print("\nTo commit these results to the artifacts repo:")
        print(f"  git add {out_path.relative_to(REPO_ROOT)} \\")
        print(f"          {log_path.relative_to(REPO_ROOT)} \\")
        print(f"          {CACHE_PATH.relative_to(REPO_ROOT)}")
    finally:
        sys.stdout = original_stdout
        log_handle.close()


if __name__ == "__main__":
    main()
