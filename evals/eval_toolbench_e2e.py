"""End-to-end ToolBench evaluation: retrieval → LLM tool selection → accuracy.

Measures whether BEAR's governance-aware retrieval improves the LLM's ability
to select the correct tool, not just whether the correct tool is in the
retrieved candidate set.

Pipeline per query:
  1. BEAR retrieves top-k tool schemas from the ToolBench corpus
  2. Tool schemas are composed into an OpenAI-compatible tool array
  3. The query + tools are sent to a local LLM (via LM Studio)
  4. The LLM's tool_call is compared against ToolBench ground truth

Metrics:
  - Tool selection accuracy (exact match on tool_name + api_name)
  - Tool name accuracy (correct tool, any API)
  - Recall@1 (was the LLM's first choice a relevant API?)
  - Per-condition bootstrap 95% CIs and paired statistical tests

Backends tested (configurable via --backends):
  Governed: BGE-base, BGE-M3, Qwen3-0.6B, Qwen3-4B, BM25
  Ungoverned: BGE (no gov)
  Baseline: Monolithic (all tools injected)

LLM Requirements:
  Any OpenAI-compatible endpoint (LM Studio, vLLM, Ollama). Paper Table 5
  used mistralai/Mistral-Nemo-Instruct-2407 12B via vLLM. Pass via --model
  and --base-url, or rely on the LM Studio defaults (port 1234).

Usage:
    python eval_toolbench_e2e.py                          # default: BGE gov + no-gov + monolithic
    python eval_toolbench_e2e.py --all                    # all backends
    python eval_toolbench_e2e.py --backends bge bm25      # specific backends
    python eval_toolbench_e2e.py --max-queries 100        # quick test
    python eval_toolbench_e2e.py --model mistral-nemo-instruct-2407
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bear import Corpus, Config, Context, Retriever, Composer, CompositionStrategy, EmbeddingBackend
from bear.models import Instruction, InstructionType, ScopeCondition
from stat_utils import bootstrap_ci, format_ci, format_ci_latex

# Use the same backend specs and data loading as eval_toolbench.py
from eval_toolbench import (
    BACKEND_SPECS,
    build_retriever,
    strip_governance,
    DEFAULT_TOP_K,
    PRIORITY_WEIGHT,
    THRESHOLD,
    EMBEDDING_MODEL,
    BOOTSTRAP_ITERS,
    recall_at_k,
    precision_at_k,
    f1_at_k,
    ndcg_at_k,
)

# ---------------------------------------------------------------------------
# LLM interface
# ---------------------------------------------------------------------------

try:
    from bear.utils import detect_local_llm_url
    DEFAULT_LLM_URL = detect_local_llm_url()
except ImportError:
    DEFAULT_LLM_URL = "http://127.0.0.1:1234/v1"

DEFAULT_LLM_MODEL = "mistralai/Mistral-Nemo-Instruct-2407"


def call_llm_with_tools(
    query: str,
    tool_schemas: list[dict],
    model: str,
    base_url: str,
    temperature: float = 0.0,
) -> dict | None:
    """Send query + tool schemas to LLM, return the tool_call or None."""
    import urllib.request

    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use the provided tools to answer the user's query. Call exactly one tool."},
        {"role": "user", "content": query},
    ]

    # Format tools in OpenAI function-calling format
    tools = []
    for schema in tool_schemas:
        tools.append({
            "type": "function",
            "function": schema,
        })

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": temperature,
        "max_tokens": 512,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        # Surface the first few transport-level failures so a misconfigured
        # endpoint or model name does not silently produce an all-zero run.
        # The counters are tracked on the function object so they persist
        # across calls within a single process.
        call_llm_with_tools._fail_count = getattr(call_llm_with_tools, "_fail_count", 0) + 1
        n = call_llm_with_tools._fail_count
        if n <= 5 or n % 50 == 0:
            print(
                f"  LLM call failed (#{n}) at {base_url}: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
        # Abort early on a clear all-fail pattern so we do not waste 1100
        # attempts when the server is unreachable or the model name is wrong.
        if n == 20 and getattr(call_llm_with_tools, "_success_count", 0) == 0:
            print(
                f"\nFATAL: 20 consecutive LLM calls failed with zero successes.\n"
                f"  Base URL: {base_url}\n"
                f"  Model:    {model}\n"
                f"  Aborting to prevent an all-zero result. Check the vLLM\n"
                f"  server URL and --base-url flag.",
                file=sys.stderr,
            )
            sys.exit(1)
        return None

    call_llm_with_tools._success_count = getattr(call_llm_with_tools, "_success_count", 0) + 1

    msg = data["choices"][0]["message"]
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        tc = tool_calls[0]
        return {
            "name": tc["function"]["name"],
            "arguments": tc["function"].get("arguments", "{}"),
        }
    # Some models return the tool call in content
    content = msg.get("content", "").strip()
    if content:
        # Try to parse as JSON tool call
        try:
            parsed = json.loads(content)
            if "name" in parsed:
                return {"name": parsed["name"], "arguments": json.dumps(parsed.get("arguments", {}))}
        except (json.JSONDecodeError, TypeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Data loading (reuse from eval_toolbench)
# ---------------------------------------------------------------------------

def load_toolbench_data() -> tuple[Corpus, list[tuple[str, list[str], set[str], list[dict]]]]:
    """Load ToolBench corpus and queries with ground truth and API metadata.

    Returns:
        (corpus, queries) where queries include API metadata for tool schema generation.
        Each query is (query_text, context_tags, expected_ids, api_details).
    """
    data_path = Path(__file__).resolve().parent / "data" / "external_benchmarks" / "toolbench" / "benchmark_data.json"
    if not data_path.exists():
        print("ERROR: ToolBench data not found. Run toolbench_setup.py first.")
        sys.exit(1)

    with open(data_path) as f:
        data = json.load(f)

    splits = ["g1_instruction", "g1_category", "g1_tool",
              "g2_instruction", "g2_category", "g3_instruction"]

    all_apis: dict[str, dict] = {}
    category_map: dict[str, str] = {}
    queries = []

    for split_name in splits:
        if split_name not in data:
            continue
        for row in data[split_name]:
            query_text = row.get("query", "")
            if not query_text:
                continue

            api_list_str = row.get("api_list", "[]")
            try:
                api_list = json.loads(api_list_str) if isinstance(api_list_str, str) else api_list_str
            except (json.JSONDecodeError, TypeError):
                api_list = []

            rel_str = row.get("relevant_apis", "[]")
            try:
                relevant_apis = json.loads(rel_str) if isinstance(rel_str, str) else rel_str
            except (json.JSONDecodeError, TypeError):
                relevant_apis = []

            # Build lookup from api_list
            api_cat_lookup: dict[tuple[str, str], str] = {}
            api_details: dict[str, dict] = {}
            for api in api_list:
                if isinstance(api, dict):
                    tool_name = api.get("tool_name", "unknown")
                    api_name = api.get("api_name", "unknown")
                    cat = api.get("category_name", "unknown")
                    api_cat_lookup[(tool_name, api_name)] = cat
                    cat_tag = cat.lower().replace(" ", "_").replace("&", "and")
                    api_id = f"toolbench/{cat_tag}/{tool_name}/{api_name}"
                    all_apis[api_id] = api
                    category_map[api_id] = cat_tag
                    api_details[api_id] = api

            # Build expected set
            expected_ids = set()
            query_cats = set()
            for api in relevant_apis:
                if isinstance(api, (list, tuple)) and len(api) >= 2:
                    tool_name, api_name = api[0], api[1]
                    cat = api_cat_lookup.get((tool_name, api_name), "unknown")
                elif isinstance(api, dict):
                    cat = api.get("category_name", "unknown")
                    tool_name = api.get("tool_name", "unknown")
                    api_name = api.get("api_name", "unknown")
                else:
                    continue
                cat_tag = cat.lower().replace(" ", "_").replace("&", "and")
                api_id = f"toolbench/{cat_tag}/{tool_name}/{api_name}"
                expected_ids.add(api_id)
                query_cats.add(cat_tag)
                if api_id not in all_apis:
                    all_apis[api_id] = {"category_name": cat, "tool_name": tool_name,
                                        "api_name": api_name, "api_description": ""}
                    category_map[api_id] = cat_tag

            if expected_ids:
                context_tags = sorted(query_cats)
                queries.append((query_text.strip(), context_tags, expected_ids,
                                list(api_details.values())))

    # Build BEAR corpus
    corpus = Corpus()
    for api_id, api in all_apis.items():
        cat = api.get("category_name", "unknown")
        tool_name = api.get("tool_name", "unknown")
        api_name = api.get("api_name", "unknown")
        desc = api.get("api_description", "") or ""
        cat_tag = category_map.get(api_id, "unknown")

        # Build content
        content_parts = [f"API: {tool_name} / {api_name}", f"Category: {cat}"]
        if desc:
            content_parts.append(f"Description: {desc[:500]}")

        # Parameters
        for p in api.get("required_parameters", []):
            if isinstance(p, dict):
                content_parts.append(f"Required: {p.get('name', '')} ({p.get('type', '')}): {p.get('description', '')}")
        for p in api.get("optional_parameters", []):
            if isinstance(p, dict):
                content_parts.append(f"Optional: {p.get('name', '')} ({p.get('type', '')}): {p.get('description', '')}")

        # Build action schema
        # ToolBench uses uppercase types (STRING, NUMBER); JSON Schema requires lowercase
        _VALID_TYPES = {"string", "number", "boolean", "integer", "array", "object", "null"}
        _TYPE_MAP = {"STRING": "string", "NUMBER": "number", "BOOLEAN": "boolean", "INTEGER": "integer", "ARRAY": "array", "OBJECT": "object"}
        def _norm_type(t: str) -> str:
            if not t:
                return "string"
            mapped = _TYPE_MAP.get(t, t.lower())
            return mapped if mapped in _VALID_TYPES else "string"

        params = {}
        required_params = []
        for p in api.get("required_parameters", []):
            if isinstance(p, dict):
                pname = p.get("name", "param")
                params[pname] = {"type": _norm_type(p.get("type", "string")), "description": p.get("description", "")}
                required_params.append(pname)
        for p in api.get("optional_parameters", []):
            if isinstance(p, dict):
                pname = p.get("name", "param")
                params[pname] = {"type": _norm_type(p.get("type", "string")), "description": p.get("description", "")}

        # Sanitize function name: only a-z, A-Z, 0-9, underscores, dashes allowed; max 64 chars
        import re as _re
        func_name = f"{tool_name}__{api_name}"
        func_name = _re.sub(r'[^a-zA-Z0-9_-]', '_', func_name)
        func_name = _re.sub(r'_+', '_', func_name).strip('_')[:64]

        action_schema = {
            "name": func_name,
            "description": desc[:200] if desc else f"{tool_name} - {api_name}",
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required_params,
            },
        }

        instruction = Instruction(
            id=api_id,
            type=InstructionType.TOOL,
            priority=50,
            content="\n".join(content_parts),
            tags=[cat_tag, tool_name.lower().replace(" ", "_")],
            scope=ScopeCondition(required_tags=[cat_tag]),
            actions={func_name: action_schema},
        )
        corpus.add(instruction)

    return corpus, queries


def make_tool_schema(instruction) -> dict | None:
    """Extract OpenAI function-calling schema from a BEAR tool instruction."""
    inst = instruction.instruction if hasattr(instruction, 'instruction') else instruction
    if inst.actions:
        # actions is a dict {func_name: schema}; return the first value
        return next(iter(inst.actions.values()))
    return None


# ---------------------------------------------------------------------------
# End-to-end evaluation
# ---------------------------------------------------------------------------

def evaluate_e2e(
    retriever: Retriever,
    queries: list[tuple[str, list[str], set[str], list[dict]]],
    llm_model: str,
    llm_url: str,
    top_k: int,
    use_tags: bool = True,
    condition_name: str = "",
) -> dict:
    """Run end-to-end eval: retrieve → compose tools → LLM selects → score.

    Collects both retrieval-level metrics (Recall, Precision, F1, NDCG) and
    LLM-level metrics (exact accuracy, tool accuracy) with bootstrap CIs,
    paired t-tests, Wilcoxon signed-rank tests, and Cohen's d.
    """
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    # LLM-level metrics
    exact_matches = []  # 1 if LLM picked a relevant API, 0 otherwise
    tool_matches = []   # 1 if LLM picked right tool (any API), 0 otherwise
    llm_errors = 0
    total = 0

    # Retrieval-level metrics
    recalls, precisions, f1s, ndcgs = [], [], [], []

    for i, (query_text, tags, expected_ids, _api_details) in enumerate(queries):
        ctx = Context(tags=tags if use_tags else [])
        results = retriever.retrieve(query_text, ctx, top_k=top_k)

        # Retrieval metrics
        retrieved_ordered = [r.id for r in results]
        retrieved_set = set(retrieved_ordered)
        recalls.append(recall_at_k(retrieved_set, expected_ids, top_k))
        precisions.append(precision_at_k(retrieved_set, expected_ids, top_k))
        f1s.append(f1_at_k(retrieved_set, expected_ids, top_k))
        ndcgs.append(ndcg_at_k(retrieved_ordered, expected_ids, top_k))

        # Build tool schemas from retrieved instructions
        tool_schemas = []
        id_to_schema_name: dict[str, str] = {}
        for r in results:
            schema = make_tool_schema(r)
            if schema:
                tool_schemas.append(schema)
                id_to_schema_name[r.id] = schema["name"]

        if not tool_schemas:
            exact_matches.append(0)
            tool_matches.append(0)
            total += 1
            continue

        # Call LLM
        tool_call = call_llm_with_tools(
            query_text, tool_schemas, llm_model, llm_url
        )
        total += 1

        if tool_call is None:
            llm_errors += 1
            exact_matches.append(0)
            tool_matches.append(0)
            continue

        # Check if LLM's choice matches ground truth
        chosen_name = tool_call["name"]

        # Map schema name back to instruction ID
        name_to_id = {v: k for k, v in id_to_schema_name.items()}
        chosen_id = name_to_id.get(chosen_name, "")

        # Exact match: chosen API is in expected set
        if chosen_id in expected_ids:
            exact_matches.append(1)
        else:
            exact_matches.append(0)

        # Tool match: chosen tool name matches any expected tool
        chosen_parts = chosen_id.split("/") if chosen_id else []
        expected_tools = set()
        for eid in expected_ids:
            parts = eid.split("/")
            if len(parts) >= 3:
                expected_tools.add(parts[2])  # tool_name
        if len(chosen_parts) >= 3 and chosen_parts[2] in expected_tools:
            tool_matches.append(1)
        else:
            tool_matches.append(0)

        # Progress
        if (i + 1) % 50 == 0 or i == len(queries) - 1:
            acc = np.mean(exact_matches)
            print(f"    [{i+1}/{len(queries)}] exact_acc={acc:.3f} "
                  f"tool_acc={np.mean(tool_matches):.3f} "
                  f"recall={np.mean(recalls):.3f} "
                  f"llm_errors={llm_errors}")

    arr_exact = np.array(exact_matches, dtype=float)
    arr_tool = np.array(tool_matches, dtype=float)
    arr_recall = np.array(recalls, dtype=float)
    arr_precision = np.array(precisions, dtype=float)
    arr_f1 = np.array(f1s, dtype=float)
    arr_ndcg = np.array(ndcgs, dtype=float)

    return {
        "condition": condition_name,
        "exact_accuracy": float(np.mean(arr_exact)),
        "exact_ci": bootstrap_ci(arr_exact, n_boot=BOOTSTRAP_ITERS),
        "tool_accuracy": float(np.mean(arr_tool)),
        "tool_ci": bootstrap_ci(arr_tool, n_boot=BOOTSTRAP_ITERS),
        "recall": float(np.mean(arr_recall)),
        "recall_ci": bootstrap_ci(arr_recall, n_boot=BOOTSTRAP_ITERS),
        "precision": float(np.mean(arr_precision)),
        "precision_ci": bootstrap_ci(arr_precision, n_boot=BOOTSTRAP_ITERS),
        "f1": float(np.mean(arr_f1)),
        "f1_ci": bootstrap_ci(arr_f1, n_boot=BOOTSTRAP_ITERS),
        "ndcg": float(np.mean(arr_ndcg)),
        "ndcg_ci": bootstrap_ci(arr_ndcg, n_boot=BOOTSTRAP_ITERS),
        "llm_errors": llm_errors,
        "total": total,
        "_exact_scores": arr_exact,
        "_tool_scores": arr_tool,
        "_recall_scores": arr_recall,
        "_precision_scores": arr_precision,
        "_f1_scores": arr_f1,
        "_ndcg_scores": arr_ndcg,
    }


def evaluate_monolithic(
    corpus: Corpus,
    queries: list[tuple[str, list[str], set[str], list[dict]]],
    llm_model: str,
    llm_url: str,
    top_k: int,
) -> dict:
    """Baseline: inject ALL tool schemas into every query.

    No retrieval step — all tools are injected, so retrieval metrics
    reflect the coverage of the truncated tool set rather than retrieval
    quality. Included for completeness alongside LLM metrics.
    """
    all_schemas = []
    id_to_name: dict[str, str] = {}
    for inst in corpus:
        schema = make_tool_schema(inst)
        if schema:
            all_schemas.append(schema)
            id_to_name[inst.id] = schema["name"]

    # Limit to top_k*3 tools to avoid exceeding context (3225 tools would be too many)
    # For monolithic, we inject the maximum the LLM can handle
    max_tools = min(len(all_schemas), 128)  # Most LLMs handle ~128 tools
    schemas_subset = all_schemas[:max_tools]

    # Track which IDs are in the truncated subset
    subset_ids = set()
    for schema in schemas_subset:
        name = schema["name"]
        for iid, iname in id_to_name.items():
            if iname == name:
                subset_ids.add(iid)
                break

    exact_matches = []
    tool_matches = []
    llm_errors = 0

    # Retrieval-level metrics (coverage of the static tool set)
    recalls, precisions, f1s, ndcgs = [], [], [], []

    name_to_id = {v: k for k, v in id_to_name.items()}

    for i, (query_text, tags, expected_ids, _) in enumerate(queries):
        # Retrieval metrics for the static subset
        recalls.append(recall_at_k(subset_ids, expected_ids, top_k))
        precisions.append(precision_at_k(subset_ids, expected_ids, top_k))
        f1s.append(f1_at_k(subset_ids, expected_ids, top_k))
        # NDCG: no ranking in monolithic, use arbitrary order
        ndcgs.append(ndcg_at_k(list(subset_ids)[:top_k], expected_ids, top_k))

        tool_call = call_llm_with_tools(
            query_text, schemas_subset, llm_model, llm_url
        )

        if tool_call is None:
            llm_errors += 1
            exact_matches.append(0)
            tool_matches.append(0)
            continue

        chosen_name = tool_call["name"]
        chosen_id = name_to_id.get(chosen_name, "")

        if chosen_id in expected_ids:
            exact_matches.append(1)
        else:
            exact_matches.append(0)

        chosen_parts = chosen_id.split("/") if chosen_id else []
        expected_tools = {eid.split("/")[2] for eid in expected_ids if len(eid.split("/")) >= 3}
        if len(chosen_parts) >= 3 and chosen_parts[2] in expected_tools:
            tool_matches.append(1)
        else:
            tool_matches.append(0)

        if (i + 1) % 50 == 0 or i == len(queries) - 1:
            print(f"    [{i+1}/{len(queries)}] exact_acc={np.mean(exact_matches):.3f} "
                  f"tool_acc={np.mean(tool_matches):.3f} errors={llm_errors}")

    arr_exact = np.array(exact_matches, dtype=float)
    arr_tool = np.array(tool_matches, dtype=float)
    arr_recall = np.array(recalls, dtype=float)
    arr_precision = np.array(precisions, dtype=float)
    arr_f1 = np.array(f1s, dtype=float)
    arr_ndcg = np.array(ndcgs, dtype=float)

    return {
        "condition": "Monolithic (all tools)",
        "exact_accuracy": float(np.mean(arr_exact)),
        "exact_ci": bootstrap_ci(arr_exact, n_boot=BOOTSTRAP_ITERS),
        "tool_accuracy": float(np.mean(arr_tool)),
        "tool_ci": bootstrap_ci(arr_tool, n_boot=BOOTSTRAP_ITERS),
        "recall": float(np.mean(arr_recall)),
        "recall_ci": bootstrap_ci(arr_recall, n_boot=BOOTSTRAP_ITERS),
        "precision": float(np.mean(arr_precision)),
        "precision_ci": bootstrap_ci(arr_precision, n_boot=BOOTSTRAP_ITERS),
        "f1": float(np.mean(arr_f1)),
        "f1_ci": bootstrap_ci(arr_f1, n_boot=BOOTSTRAP_ITERS),
        "ndcg": float(np.mean(arr_ndcg)),
        "ndcg_ci": bootstrap_ci(arr_ndcg, n_boot=BOOTSTRAP_ITERS),
        "llm_errors": llm_errors,
        "total": len(queries),
        "_exact_scores": arr_exact,
        "_tool_scores": arr_tool,
        "_recall_scores": arr_recall,
        "_precision_scores": arr_precision,
        "_f1_scores": arr_f1,
        "_ndcg_scores": arr_ndcg,
    }


# ---------------------------------------------------------------------------
# Experiment configurations
# ---------------------------------------------------------------------------

ALL_BACKENDS = [
    {"name": "BEAR+BGE (gov)", "backend": "bge", "governance": True, "use_tags": True},
    {"name": "BEAR+BGE-M3 (gov)", "backend": "bge-m3", "governance": True, "use_tags": True},
    {"name": "BEAR+Qwen3-0.6B (gov)", "backend": "qwen3-0.6b", "governance": True, "use_tags": True},
    {"name": "BEAR+Qwen3-4B (gov)", "backend": "qwen3-4b", "governance": True, "use_tags": True},
    {"name": "BEAR+BM25 (gov)", "backend": "bm25", "governance": True, "use_tags": True},
    {"name": "BEAR+Hash (gov)", "backend": "hash", "governance": True, "use_tags": True},
    {"name": "BGE (no gov)", "backend": "bge", "governance": False, "use_tags": False},
    {"name": "BGE-M3 (no gov)", "backend": "bge-m3", "governance": False, "use_tags": False},
    {"name": "Qwen3-0.6B (no gov)", "backend": "qwen3-0.6b", "governance": False, "use_tags": False},
    {"name": "Qwen3-4B (no gov)", "backend": "qwen3-4b", "governance": False, "use_tags": False},
    {"name": "BM25 (no gov)", "backend": "bm25", "governance": False, "use_tags": False},
]

DEFAULT_BACKENDS = ["BEAR+BGE (gov)", "BGE (no gov)"]


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def _run_statistical_tests(results: list[dict], n_queries: int) -> None:
    """Run paired statistical tests across all condition pairs and metrics."""
    if len(results) < 2:
        return

    from scipy.stats import ttest_rel, wilcoxon

    def _paired_d(a, b):
        diff = a - b
        sd = np.std(diff, ddof=1)
        return float(np.mean(diff) / sd) if sd > 0 else float('inf')

    ALL_METRICS = [
        ("recall", "_recall_scores"),
        ("ndcg", "_ndcg_scores"),
        ("f1", "_f1_scores"),
        ("exact_acc", "_exact_scores"),
        ("tool_acc", "_tool_scores"),
    ]

    print(f"\n{'=' * 60}")
    print(f"  Statistical Tests (paired t-test, Wilcoxon, Cohen's d)")
    print(f"  n={n_queries} queries")
    print(f"{'=' * 60}")

    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            a, b = results[i], results[j]
            print(f"\n  {a['condition']}  vs  {b['condition']}:")

            for metric_label, score_key in ALL_METRICS:
                a_vals = a.get(score_key, np.array([]))
                b_vals = b.get(score_key, np.array([]))
                if len(a_vals) == 0 or len(b_vals) == 0:
                    continue
                n = min(len(a_vals), len(b_vals))
                a_vals, b_vals = a_vals[:n], b_vals[:n]

                # Paired t-test
                if np.std(a_vals - b_vals) > 0:
                    t_stat, t_p = ttest_rel(a_vals, b_vals)
                else:
                    t_stat, t_p = 0.0, 1.0

                # Wilcoxon signed-rank (needs non-zero differences)
                diff = a_vals - b_vals
                nonzero = diff[diff != 0]
                if len(nonzero) >= 5:
                    w_stat, w_p = wilcoxon(nonzero)
                    w_str = f"W={w_stat:.0f}, p={w_p:.4f}"
                else:
                    w_str = "skipped (<5 non-zero diffs)"

                d = _paired_d(a_vals, b_vals)
                sig = "***" if t_p < 0.001 else ("**" if t_p < 0.01 else ("*" if t_p < 0.05 else "n.s."))
                print(f"    {metric_label:>10}: paired-t={t_stat:.3f}, "
                      f"p={t_p:.4f} {sig}, d={d:.3f}; {w_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end ToolBench evaluation: retrieval → LLM → tool selection accuracy."
    )
    parser.add_argument("--all", action="store_true", help="Run all backends")
    parser.add_argument("--backends", nargs="+", default=None,
                        help="Specific backend names to run")
    parser.add_argument("--max-queries", type=int, default=0,
                        help="Limit number of queries (0 = all)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                        help=f"Number of tools to retrieve (default: {DEFAULT_TOP_K})")
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL,
                        help=f"LLM model ID (default: {DEFAULT_LLM_MODEL})")
    parser.add_argument("--base-url", default=DEFAULT_LLM_URL,
                        help=f"LLM server URL (default: {DEFAULT_LLM_URL})")
    parser.add_argument("--skip-monolithic", action="store_true",
                        help="Skip monolithic baseline (slow with many tools)")
    parser.add_argument("--stats-only", action="store_true",
                        help="Load saved scores and compute statistical tests only (no LLM needed)")
    args = parser.parse_args()

    # --stats-only mode: reload raw scores and run statistical tests
    if args.stats_only:
        scores_path = Path(__file__).resolve().parent / "results" / "toolbench_e2e_scores.json"
        if not scores_path.exists():
            print(f"ERROR: No saved scores at {scores_path}. Run the full eval first.")
            sys.exit(1)
        with open(scores_path) as f:
            saved = json.load(f)
        print(f"Loaded scores: {saved['model']}, n={saved['n_queries']}, k={saved['top_k']}")
        results = []
        for entry in saved["scores"]:
            r = {"condition": entry["condition"]}
            for k, v in entry.items():
                if k.startswith("_"):
                    r[k] = np.array(v)
            results.append(r)
        _run_statistical_tests(results, saved["n_queries"])
        sys.exit(0)

    print(f"LLM model: {args.model}")
    print(f"LLM URL: {args.base_url}")
    print(f"Top-k: {args.top_k}")

    # Verify LLM is reachable
    import urllib.request
    try:
        urllib.request.urlopen(f"{args.base_url}/models", timeout=5)
        print("LLM server: reachable")
    except Exception:
        print(f"ERROR: LLM server not reachable at {args.base_url}")
        print("  Start LM Studio and load the model, or use --base-url")
        sys.exit(1)

    # Load data
    print("\nLoading ToolBench data...")
    corpus, queries = load_toolbench_data()
    print(f"Corpus: {len(corpus)} APIs")
    print(f"Queries: {len(queries)}")

    if args.max_queries > 0:
        queries = queries[:args.max_queries]
        print(f"Limited to {len(queries)} queries")

    stripped_corpus = strip_governance(corpus)

    # Select backends
    if args.all:
        experiments = ALL_BACKENDS
    elif args.backends:
        experiments = [e for e in ALL_BACKENDS if e["name"] in args.backends]
    else:
        experiments = [e for e in ALL_BACKENDS if e["name"] in DEFAULT_BACKENDS]

    print(f"\nConditions: {', '.join(e['name'] for e in experiments)}")

    # Run experiments
    results = []
    for exp in experiments:
        print(f"\n{'=' * 60}")
        print(f"  {exp['name']}")
        print(f"{'=' * 60}")

        corp = stripped_corpus if not exp["governance"] else corpus
        try:
            retriever = build_retriever(
                corp,
                backend=exp["backend"],
                governance=exp["governance"],
                mandatory_tags=[],
            )
        except Exception as e:
            print(f"  SKIPPED: {e}")
            continue

        result = evaluate_e2e(
            retriever, queries, args.model, args.base_url,
            args.top_k, use_tags=exp["use_tags"],
            condition_name=exp["name"],
        )
        results.append(result)

        print(f"\n  {exp['name']}:")
        print(f"    Retrieval:")
        print(f"      Recall@{args.top_k}:    {format_ci(result['recall_ci'])}")
        print(f"      NDCG@{args.top_k}:      {format_ci(result['ndcg_ci'])}")
        print(f"      F1@{args.top_k}:        {format_ci(result['f1_ci'])}")
        print(f"      Precision@{args.top_k}: {format_ci(result['precision_ci'])}")
        print(f"    LLM tool selection:")
        print(f"      Exact accuracy: {format_ci(result['exact_ci'])}")
        print(f"      Tool accuracy:  {format_ci(result['tool_ci'])}")
        print(f"      LLM errors: {result['llm_errors']}/{result['total']}")

    # Monolithic baseline
    if not args.skip_monolithic:
        print(f"\n{'=' * 60}")
        print(f"  Monolithic (all tools)")
        print(f"{'=' * 60}")
        mono_result = evaluate_monolithic(
            corpus, queries, args.model, args.base_url, args.top_k
        )
        results.append(mono_result)
        print(f"\n  Monolithic:")
        print(f"    Retrieval (static subset coverage):")
        print(f"      Recall@{args.top_k}:    {format_ci(mono_result['recall_ci'])}")
        print(f"      NDCG@{args.top_k}:      {format_ci(mono_result['ndcg_ci'])}")
        print(f"      F1@{args.top_k}:        {format_ci(mono_result['f1_ci'])}")
        print(f"    LLM tool selection:")
        print(f"      Exact accuracy: {format_ci(mono_result['exact_ci'])}")
        print(f"      Tool accuracy:  {format_ci(mono_result['tool_ci'])}")

    _run_statistical_tests(results, len(queries))

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    print(f"  {'Condition':<35} {'Recall@k':>20} {'NDCG@k':>20} {'F1@k':>20} "
          f"{'Exact Acc':>20} {'Tool Acc':>20} {'Errors':>8}")
    print(f"  {'-'*143}")
    for r in results:
        print(f"  {r['condition']:<35} "
              f"{format_ci(r['recall_ci']):>20} "
              f"{format_ci(r['ndcg_ci']):>20} "
              f"{format_ci(r['f1_ci']):>20} "
              f"{format_ci(r['exact_ci']):>20} "
              f"{format_ci(r['tool_ci']):>20} "
              f"{r['llm_errors']:>5}/{r['total']}")

    # LaTeX table
    print(f"\n\n% === LaTeX Table ===")
    print(r"\begin{table}[t]")
    print(r"\caption{End-to-end ToolBench evaluation: retrieval + LLM tool selection. "
          f"Retrieval $\\rightarrow$ LLM ({args.model}) $\\rightarrow$ tool call. "
          f"$n={len(queries)}$ queries, $k={args.top_k}$, 95\\% bootstrap CIs.}}")
    print(r"\label{tab:e2e-toolbench}")
    print(r"\centering\small")
    print(r"\begin{tabular}{@{}l ccc cc@{}}")
    print(r"\toprule")
    print(f"Condition & Recall@{args.top_k} & NDCG@{args.top_k} & F1@{args.top_k} "
          r"& Exact Acc & Tool Acc \\")
    print(r"\midrule")
    for r in results:
        print(f"{r['condition']} "
              f"& ${format_ci_latex(r['recall_ci'])}$ "
              f"& ${format_ci_latex(r['ndcg_ci'])}$ "
              f"& ${format_ci_latex(r['f1_ci'])}$ "
              f"& ${format_ci_latex(r['exact_ci'])}$ "
              f"& ${format_ci_latex(r['tool_ci'])}$ \\\\")
    print(r"\bottomrule")
    print(r"\end{tabular}")
    print(r"\end{table}")

    # Save JSON
    output_path = Path(__file__).resolve().parent / "results" / "toolbench_e2e_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_results = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]
    # Convert tuples to lists for JSON serialisation
    ci_keys = ("exact_ci", "tool_ci", "recall_ci", "precision_ci", "f1_ci", "ndcg_ci")
    for jr in json_results:
        for k in ci_keys:
            if k in jr and isinstance(jr[k], tuple):
                jr[k] = list(jr[k])
    with open(output_path, "w") as f:
        json.dump({
            "model": args.model,
            "top_k": args.top_k,
            "n_queries": len(queries),
            "results": json_results,
        }, f, indent=2, default=lambda o: float(o) if hasattr(o, 'item') else o)
    print(f"\nResults saved to {output_path}")

    # Save raw per-query scores for statistical tests
    scores_path = output_path.with_name("toolbench_e2e_scores.json")
    scores_data = []
    for r in results:
        entry = {"condition": r["condition"]}
        for k, v in r.items():
            if k.startswith("_") and hasattr(v, 'tolist'):
                entry[k] = v.tolist()
        scores_data.append(entry)
    with open(scores_path, "w") as f:
        json.dump({"model": args.model, "top_k": args.top_k,
                    "n_queries": len(queries), "scores": scores_data}, f)
    print(f"Raw scores saved to {scores_path}")


if __name__ == "__main__":
    main()
