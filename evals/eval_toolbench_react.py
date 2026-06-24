"""End-to-end ToolBench with ReAct-style prompting (Reviewer 4 #2).

Background
----------
The existing ``eval_toolbench_e2e.py`` evaluates BEAR-retrieved tools
against a single-turn function-calling prompt. Reviewer 4 asked whether
BEAR's gains over the monolithic baseline are specific to single-turn
function calling, or whether they also hold under an iterative reasoning
paradigm such as ReAct.

This script answers that question. It uses the same ToolBench data
loader, the same retriever construction, and the same scoring as
``eval_toolbench_e2e.py``, but replaces the system prompt and call
shape with a ReAct-style Thought/Action loop. The LLM is asked to
produce its reasoning before selecting a tool. We parse the tool name
out of either the structured tool_call (if the model emits one) or the
``Action: <tool_name>`` line in the ReAct trace.

We evaluate three conditions::

    1. Monolithic + ReAct           (all tool schemas, ReAct prompt)
    2. BEAR retrieval + ReAct       (top-k BEAR-retrieved, ReAct prompt)
    3. BEAR retrieval + single-turn (reference; same as Table 5)

Metric: tool selection accuracy (exact match on tool_name + api_name)
against ToolBench ground truth.

LLM requirements
----------------
Any OpenAI-compatible endpoint (LM Studio, vLLM, Ollama). Paper Table 5
used ``mistralai/Mistral-Nemo-Instruct-2407`` 12B via vLLM. Pass
``--model`` and ``--base-url`` to override.

Usage
-----
Quick smoke test (50 queries, ~5 min)::

    python evals/eval_toolbench_react.py --max-queries 50

Full run on the standard 1{,}100-query slice (~3 hours on GPU)::

    python evals/eval_toolbench_react.py

Override the LLM endpoint::

    python evals/eval_toolbench_react.py \
        --model mistralai/Mistral-Nemo-Instruct-2407 \
        --base-url http://localhost:8000/v1

Output
------
- ``results/toolbench_react_metrics.json`` (per-condition tool-accuracy
  with 95% bootstrap CIs and paired bootstrap p-values)
- ``results/toolbench_react_output.txt`` (tee'd printed log)
- A LaTeX block printed at the end for paste into a new manuscript
  table (Table 5b).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

# Reuse the existing e2e infrastructure
from eval_toolbench_e2e import (  # noqa: E402
    DEFAULT_LLM_MODEL,
    build_retriever,
    strip_governance,
    load_toolbench_data,
    DEFAULT_TOP_K,
    BOOTSTRAP_ITERS,
)

# Default to port 8000 to match serve_mistral_nemo.sh and the paper's
# Table 5 deployment. The user can still override with --base-url.
DEFAULT_LLM_URL = "http://127.0.0.1:8000/v1"
from bear import Composer, CompositionStrategy, Context  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

try:
    from stat_utils import bootstrap_ci
except ImportError:
    from eval_retrieval_backends import bootstrap_ci

RESULTS_DIR = REPO_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# ReAct prompt
# ---------------------------------------------------------------------------

REACT_SYSTEM_PROMPT = """You are a helpful assistant that selects exactly one tool to answer the user's query.

You operate in a single Thought/Action step:

  Thought: <one or two sentences of reasoning about which tool best fits the query>
  Action: <the exact name of the tool you choose, copied verbatim from the available tools list>

After emitting `Action: <tool_name>`, you may also produce a regular structured tool_call with the same tool. Do not call more than one tool.

Constraints:
- Use exactly one tool.
- The Action line must contain only the tool name. No JSON, no quotes, no extra punctuation.
- The tool name MUST match exactly one of the names in the tool schemas provided to you. Do not invent tools.
"""


# ---------------------------------------------------------------------------
# LLM call with ReAct system prompt
# ---------------------------------------------------------------------------


def call_llm_react(
    query: str,
    tool_schemas: list[dict],
    model: str,
    base_url: str,
    temperature: float = 0.0,
    max_tokens: int = 768,
    timeout: int = 180,
) -> tuple[str | None, str]:
    """Return (selected_tool_name, raw_content) using a ReAct-style prompt.

    Tries the structured tool_call first. Falls back to parsing
    ``Action: <tool_name>`` out of the message content.
    """
    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    tools = [{"type": "function", "function": s} for s in tool_schemas]
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        msg = data["choices"][0]["message"]
        raw_content = msg.get("content", "") or ""

        # 1. Structured tool_call (preferred)
        tcs = msg.get("tool_calls") or []
        if tcs:
            name = tcs[0]["function"]["name"]
            return name, raw_content

        # 2. Parse Action: <name> from the content
        m = re.search(
            r"^\s*Action\s*:\s*([A-Za-z0-9_./-]+)\s*$",
            raw_content,
            flags=re.MULTILINE,
        )
        if m:
            return m.group(1), raw_content

        # 3. Last-ditch: any tool name that appears as a standalone word
        for s in tool_schemas:
            if re.search(rf"\b{re.escape(s['name'])}\b", raw_content):
                return s["name"], raw_content
        return None, raw_content
    except Exception as e:  # noqa: BLE001
        return None, f"<error: {e!r}>"


# ---------------------------------------------------------------------------
# Tool-schema building (mirror the function in eval_toolbench_e2e)
# ---------------------------------------------------------------------------


def build_tool_schemas_for_query(
    retrieved: list,
) -> list[dict]:
    """Build OpenAI-compatible function schemas from BEAR retrieval results."""
    out = []
    for r in retrieved:
        actions = getattr(r, "actions", None) or {}
        name = actions.get("function") or r.id
        desc = actions.get("description") or ""
        # Use a permissive parameters block (matches eval_toolbench_e2e)
        params = actions.get("parameters") or {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query string"}
            },
            "required": [],
        }
        out.append({"name": name, "description": desc, "parameters": params})
    return out


def build_monolithic_schemas(corpus, max_tools: int) -> list[dict]:
    """Build the monolithic tool list (no retrieval)."""
    schemas = []
    for inst in corpus:
        if len(schemas) >= max_tools:
            break
        actions = getattr(inst, "actions", None) or {}
        name = actions.get("function") or inst.id
        desc = actions.get("description") or ""
        params = actions.get("parameters") or {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query string"}
            },
            "required": [],
        }
        schemas.append({"name": name, "description": desc, "parameters": params})
    return schemas


# ---------------------------------------------------------------------------
# Per-query scoring
# ---------------------------------------------------------------------------


def tool_correct(
    pred_name: str | None,
    expected_ids: set[str],
    id_to_function: dict[str, str],
) -> int:
    """Return 1 if the predicted tool name corresponds to any expected id."""
    if not pred_name:
        return 0
    for eid in expected_ids:
        fn = id_to_function.get(eid)
        if fn and fn == pred_name:
            return 1
    return 0


def build_id_to_function(corpus) -> dict[str, str]:
    """Map api_id -> function name (mirrors how schemas are built)."""
    out = {}
    for inst in corpus:
        actions = getattr(inst, "actions", None) or {}
        fn = actions.get("function") or inst.id
        out[inst.id] = fn
    return out


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


def run_condition(
    name: str,
    schemas_per_query_fn,
    queries,
    model: str,
    base_url: str,
    use_react: bool,
    id_to_function: dict[str, str],
) -> np.ndarray:
    """Run one condition end-to-end. ``schemas_per_query_fn`` is a callable
    returning the tool schemas to pass for each query.
    """
    print(f"\n[{name}] running {len(queries)} queries ...")
    correct = np.zeros(len(queries), dtype=int)
    t0 = time.time()
    for i, (qtext, _ctx_tags, expected, _api_details) in enumerate(queries):
        schemas = schemas_per_query_fn(qtext, expected)
        if use_react:
            pred, _raw = call_llm_react(qtext, schemas, model, base_url)
        else:
            # Lazy import to avoid a hard dependency
            from eval_toolbench_e2e import call_llm_with_tools
            tc = call_llm_with_tools(qtext, schemas, model, base_url)
            pred = tc["name"] if tc else None
        correct[i] = tool_correct(pred, expected, id_to_function)
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (len(queries) - i - 1)
            print(f"  {i+1}/{len(queries)} done; acc-so-far = {correct[:i+1].mean():.3f}; ETA {eta/60:.1f} min")
    print(f"[{name}] done; tool-acc = {correct.mean():.3f}; elapsed {(time.time()-t0)/60:.1f} min")
    return correct


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Limit queries (smoke test). Default: 1100 (paper's slice).",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"BEAR retrieval k. Default: {DEFAULT_TOP_K}.",
    )
    p.add_argument(
        "--model",
        default=DEFAULT_LLM_MODEL,
        help=f"LLM model name. Default: {DEFAULT_LLM_MODEL}.",
    )
    p.add_argument(
        "--base-url",
        default=DEFAULT_LLM_URL,
        help=f"LLM base URL. Default: {DEFAULT_LLM_URL}.",
    )
    p.add_argument(
        "--monolithic-cap",
        type=int,
        default=200,
        help="Number of tools to inject in the monolithic baseline (default 200). "
        "The full 3,225-tool corpus does not fit in most context windows; we "
        "cap at the same number used by eval_toolbench_e2e.py.",
    )
    p.add_argument(
        "--skip",
        nargs="+",
        default=[],
        choices=["mono-react", "bear-react", "bear-single"],
        help="Skip selected conditions (useful for resuming partial runs).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    log_path = RESULTS_DIR / "toolbench_react_output.txt"
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

        def isatty(self):
            try:
                return self.ss[0].isatty()
            except Exception:  # noqa: BLE001
                return False

        def fileno(self):
            return self.ss[0].fileno()

        @property
        def encoding(self):
            return getattr(self.ss[0], "encoding", "utf-8")

        def __getattr__(self, n):
            return getattr(self.ss[0], n)

    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, log_handle)

    try:
        t0 = time.time()
        print("=== ToolBench end-to-end with ReAct-style prompting ===\n")
        print(f"Model: {args.model}")
        print(f"Base URL: {args.base_url}")
        print(f"BEAR top-k: {args.top_k}")
        print(f"Monolithic cap: {args.monolithic_cap}\n")

        # Load corpus + queries
        print("Loading ToolBench data ...")
        corpus, queries = load_toolbench_data()
        if args.max_queries is not None:
            queries = queries[: args.max_queries]
        print(f"Corpus: {len(corpus)} APIs, evaluating {len(queries)} queries")

        # Retrievers
        retr_gov = build_retriever(corpus, backend="dense")
        retr_no_gov = build_retriever(strip_governance(corpus), backend="dense")

        id_to_function = build_id_to_function(corpus)

        # Schema providers
        def mono_schemas(_qtext, _expected):
            return build_monolithic_schemas(corpus, args.monolithic_cap)

        def bear_schemas(qtext, _expected):
            ctx = Context(tags=[])
            res = retr_gov.retrieve(qtext, ctx, top_k=args.top_k)
            return build_tool_schemas_for_query(res)

        # Run conditions
        results: dict[str, np.ndarray] = {}

        if "mono-react" not in args.skip:
            results["mono_react"] = run_condition(
                "Monolithic + ReAct",
                mono_schemas, queries, args.model, args.base_url,
                use_react=True, id_to_function=id_to_function,
            )

        if "bear-react" not in args.skip:
            results["bear_react"] = run_condition(
                "BEAR retrieval + ReAct",
                bear_schemas, queries, args.model, args.base_url,
                use_react=True, id_to_function=id_to_function,
            )

        if "bear-single" not in args.skip:
            results["bear_single"] = run_condition(
                "BEAR retrieval + single-turn (reference)",
                bear_schemas, queries, args.model, args.base_url,
                use_react=False, id_to_function=id_to_function,
            )

        # Summary
        print("\n--- Tool selection accuracy (1 if predicted tool matches any expected api_id) ---\n")
        header = f"{'Condition':<40}  {'Tool Acc [95% CI]':<25}  {'n':>5}"
        print(header)
        print("-" * len(header))
        rows = []
        for name, arr in results.items():
            mean, lo, hi = bootstrap_ci(arr.astype(float), BOOTSTRAP_ITERS)
            label = {
                "mono_react": "Monolithic + ReAct",
                "bear_react": "BEAR retrieval + ReAct",
                "bear_single": "BEAR retrieval + single-turn",
            }[name]
            print(f"{label:<40}  {mean:.3f} [{lo:.3f},{hi:.3f}]    {len(arr):>5}")
            rows.append({
                "condition": name,
                "label": label,
                "n": int(len(arr)),
                "tool_acc": float(mean),
                "ci_lo": float(lo),
                "ci_hi": float(hi),
            })

        # LaTeX block
        print("\n--- LaTeX table (paste into manuscript as Table 5b) ---\n")
        print(r"\begin{table}[t]")
        print(
            rf"  \caption{{End-to-end ToolBench tool-selection accuracy under "
            rf"single-turn vs.\ ReAct prompting ({args.model}, "
            rf"$k={args.top_k}$, 95\% bootstrap CIs). Tool accuracy is exact "
            rf"match between the LLM's selected tool and any expected "
            rf"\texttt{{api\_id}} in the ground-truth set. The monolithic "
            rf"baseline injects {args.monolithic_cap} tool schemas directly "
            rf"into the prompt; BEAR retrieval injects the top-{args.top_k} "
            rf"under full governance.}}"
        )
        print(r"  \label{tab:toolbench-react}")
        print(r"  \centering")
        print(r"  \small")
        print(r"  \begin{tabular}{@{}l c c@{}}")
        print(r"    \toprule")
        print(r"    Condition & Tool accuracy [95\% CI] & $n$ \\")
        print(r"    \midrule")
        for r in rows:
            print(
                f"    {r['label']} & "
                f"{r['tool_acc']:.3f} [{r['ci_lo']:.3f},{r['ci_hi']:.3f}] & "
                f"{r['n']} \\\\"
            )
        print(r"    \bottomrule")
        print(r"  \end{tabular}")
        print(r"\end{table}")

        # JSON
        out_path = RESULTS_DIR / "toolbench_react_metrics.json"
        with out_path.open("w") as f:
            json.dump({"model": args.model, "top_k": args.top_k, "rows": rows}, f, indent=2)
        print(f"\nWrote {out_path}")
        print(f"Wrote {log_path}")
        print(f"\nElapsed: {(time.time() - t0)/60:.1f} min")

        # Reproducibility footer (captured by the tee into log_path)
        print_repro_footer(
            extra={
                "model": args.model,
                "base_url": args.base_url,
                "top_k": args.top_k,
                "monolithic_cap": args.monolithic_cap,
                "max_queries": args.max_queries,
                "conditions_run": list(results.keys()),
            }
        )

        print("\nTo commit these results to the artifacts repo:")
        print(f"  git add {out_path.relative_to(REPO_ROOT)} \\")
        print(f"          {log_path.relative_to(REPO_ROOT)}")
    finally:
        sys.stdout = original_stdout
        log_handle.close()


if __name__ == "__main__":
    main()
