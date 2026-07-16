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
    3. BEAR retrieval + single-turn (reference; same condition as the
       single-turn end-to-end table, ``tab:e2e``)

Metric: tool selection accuracy (exact match on tool_name + api_name)
against ToolBench ground truth.

LLM requirements
----------------
An OpenAI-compatible endpoint supporting ``response_format`` json_schema
(structured outputs): Ollama, vLLM, and LM Studio all qualify. Tool
selection is constrained decoding over an enum of candidate tool names;
this eval never sends ``tools=`` / ``tool_choice=``.

The paper's ReAct experiment (``tab:e2e-react``) used
``Mistral-Nemo-Instruct-2407`` 12B at Q4_0 quantization, served by Ollama
with ``OLLAMA_CONTEXT_LENGTH=32768``. Pass ``--model`` and ``--base-url``
to point elsewhere; note that other quantizations will shift the scores.

Usage
-----
Quick smoke test (50 queries, ~5 min)::

    python evals/eval_toolbench_react.py --max-queries 50

Full run on the standard 1{,}100-query slice (~3 hours on GPU)::

    python evals/eval_toolbench_react.py

Override the LLM endpoint::

    python evals/eval_toolbench_react.py \
        --model mistral-nemo \
        --base-url http://localhost:11434/v1

Output
------
- ``results/toolbench_react_metrics.json`` (per-condition tool-accuracy
  with 95% bootstrap CIs and paired bootstrap p-values)
- ``results/toolbench_react_output.txt`` (tee'd printed log)
- A LaTeX block printed at the end for paste into the manuscript's
  ReAct end-to-end table (``tab:e2e-react``).
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
    _post_with_retry,
    assert_prompt_fits,
    build_retriever,
    strip_governance,
    load_toolbench_data,
    DEFAULT_TOP_K,
    BOOTSTRAP_ITERS,
)

# Default to Ollama's port, matching the paper's end-to-end deployment
# (Mistral-Nemo-Instruct-2407 at Q4_0). Override with --base-url.
DEFAULT_LLM_URL = "http://127.0.0.1:11434/v1"
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

You operate in a single Thought/Action step. Respond with a JSON object of the form:

  {"thought": "<one or two sentences of reasoning about which tool best fits the query>",
   "action": "<the exact name of the tool you choose>"}

Constraints:
- Reason first in "thought", then commit to a single tool in "action".
- Use exactly one tool.
- The "action" value MUST be exactly one of the available tool names listed below. Do not invent tools.
"""

# Reasoning-mode prompt: used with --reasoning-mode for natively-thinking models.
# The output is NOT grammar-constrained (constrained decoding would suppress the
# model's <think> phase), so we instead ask for a final Action line and parse it
# out of the free-form (post-thinking) text.
REACT_REASONING_SYSTEM_PROMPT = """You select exactly one tool to answer the user's query.

Think step by step about which tool best fits, considering the available tools below. After your reasoning, output your final choice on its own line in exactly this format:

Action: <the exact name of one tool from the list>

Use exactly one tool. The name after "Action:" must match one of the available tool names below exactly, character for character.
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
    reasoning_mode: bool = False,
    top_p: float | None = None,
    top_k: int | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str | None, str]:
    """Return (selected_tool_name, raw_content) using a ReAct-style prompt.

    The reply is produced under constrained decoding: a JSON schema requires a
    free-text ``thought`` followed by an ``action`` restricted to an enum of the
    candidate tool names. The Thought step (the scaffold under test) is
    preserved, while a malformed or out-of-vocabulary action is impossible, so
    this condition records no parse failures.

    The single-turn reference condition selects tools with the same constrained
    mechanism (``call_llm_with_tools`` from the end-to-end eval), so the two
    conditions differ only by the presence of the Thought. That is what makes
    the ReAct-vs-single-turn contrast a clean test of the reasoning scaffold
    rather than of the model's output formatting.
    """
    tool_names = [s.get("name", "") for s in tool_schemas if s.get("name")]
    if not tool_names:
        return None, ""

    # The candidate tools are listed in the prompt rather than passed as an
    # OpenAI ``tools`` array: the array invites a structured tool_call whose
    # arguments the server must parse, and a malformed one fails the whole
    # request, discarding an otherwise valid action.
    tool_list = "\n".join(
        f"- {s['name']}: {(s.get('description') or '').strip()[:400]}"
        for s in tool_schemas if s.get("name")
    )
    if reasoning_mode:
        # Natively-thinking model: no grammar constraint (it would gag the
        # <think> phase). Ask for a final Action line and give a generous token
        # budget for the reasoning tokens.
        messages = [
            {"role": "system",
             "content": REACT_REASONING_SYSTEM_PROMPT + "\nAvailable tools:\n" + tool_list},
            {"role": "user", "content": query},
        ]
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max(max_tokens, 8192),
        }
        if top_p is not None:
            body["top_p"] = top_p
        if top_k is not None:
            body["top_k"] = top_k
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort
    else:
        messages = [
            {"role": "system",
             "content": REACT_SYSTEM_PROMPT + "\nAvailable tools:\n" + tool_list},
            {"role": "user", "content": query},
        ]
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "react_step",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "thought": {"type": "string"},
                        "action": {"type": "string", "enum": tool_names},
                    },
                    "required": ["thought", "action"],
                    "additionalProperties": False,
                },
            },
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
        }
        if top_p is not None:
            body["top_p"] = top_p
        if top_k is not None:
            body["top_k"] = top_k
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        data = _post_with_retry(req, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        # Surface transport-level failures so a misconfigured endpoint does
        # not silently produce an all-zero run. Counters track per-process.
        call_llm_react._fail_count = getattr(call_llm_react, "_fail_count", 0) + 1
        n = call_llm_react._fail_count
        if n <= 5 or n % 50 == 0:
            print(
                f"  LLM call failed (#{n}) at {base_url}: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
        if n == 20 and getattr(call_llm_react, "_success_count", 0) == 0:
            print(
                f"\nFATAL: 20 consecutive LLM calls failed with zero successes.\n"
                f"  Base URL: {base_url}\n"
                f"  Model:    {model}\n"
                f"  Aborting to prevent an all-zero result. Check the vLLM\n"
                f"  server URL and --base-url flag.",
                file=sys.stderr,
            )
            sys.exit(1)
        return None, f"<error: {e!r}>"

    call_llm_react._success_count = getattr(call_llm_react, "_success_count", 0) + 1
    msg = data["choices"][0]["message"]
    raw_content = msg.get("content", "") or ""

    if reasoning_mode:
        # The model reasoned freely. Its thinking may name many tools while
        # weighing options, so parse the post-reasoning answer preferentially.
        # Ollama returns the thinking in a separate `reasoning` field and the
        # final answer (with the Action line) in `content`; strip any inline
        # <think> block for models that embed it instead. Fall back to the
        # reasoning field only if `content` yields nothing.
        answer = re.sub(r"<think>.*?</think>", "", raw_content,
                        flags=re.DOTALL | re.IGNORECASE)
        reasoning_field = msg.get("reasoning") or ""
        for text in (answer, reasoning_field):
            if not text:
                continue
            # Prefer the explicit final Action line.
            m = re.search(r"Action\s*:\s*([A-Za-z0-9_./-]+)", text, flags=re.IGNORECASE)
            if m and m.group(1) in tool_names:
                return m.group(1), raw_content
            # Otherwise, the LAST tool name mentioned (the conclusion, not an
            # option weighed earlier).
            last = None
            for s in tool_schemas:
                if s.get("name") and re.search(rf"\b{re.escape(s['name'])}\b", text):
                    pos = text.rfind(s["name"])
                    if last is None or pos > last[1]:
                        last = (s["name"], pos)
            if last:
                return last[0], raw_content
        return None, raw_content

    # 1. Constrained JSON: {"thought": ..., "action": <one of tool_names>}.
    #    Under strict schema decoding this parses on every call.
    try:
        parsed = json.loads(raw_content)
        action = parsed.get("action")
        if action in tool_names:
            return action, raw_content
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Fallback, reachable only if the server ignored response_format:
    #    parse an ``Action: <name>`` line out of free-form text.
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


# ---------------------------------------------------------------------------
# Tool-schema building (mirror the function in eval_toolbench_e2e)
# ---------------------------------------------------------------------------


# Mistral's tool-call validator restricts function names to
# ^[A-Za-z0-9_-]{1,64}$ (see mistral_common.protocol.instruct.validator.
# _validate_function). ToolBench api_ids look like
# 'toolbench/data/ASIN Data/Category', which contain slashes, spaces, and
# frequently exceed 64 characters. Without sanitization vLLM rejects every
# chat-completion request with InvalidToolException and the eval scores 0.
#
# We sanitize once and cache the mapping so the same instruction always
# yields the same function name. The scoring step requires this stability
# so the predicted function name can be compared against the expected
# api_id's sanitized form.
_MISTRAL_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
_MISTRAL_MAX_NAME_LEN = 64


def _derive_function_name(raw_name: str, used: dict) -> str:
    """Sanitize raw_name to fit Mistral's tool-name regex.

    Maintains a stable raw -> sanitized mapping in ``used`` so the same
    input always produces the same output and disambiguates collisions.
    """
    if raw_name in used:
        return used[raw_name]
    s = _MISTRAL_NAME_RE.sub("_", raw_name).strip("_")
    s = re.sub(r"_+", "_", s) or "tool"
    if len(s) > _MISTRAL_MAX_NAME_LEN:
        s = s[:_MISTRAL_MAX_NAME_LEN]
    # Disambiguate if this sanitized form is already taken by a different raw
    existing_values = set(used.values())
    if s in existing_values:
        base = s[: _MISTRAL_MAX_NAME_LEN - 5]
        i = 1
        while f"{base}_{i}" in existing_values:
            i += 1
        s = f"{base}_{i}"
    used[raw_name] = s
    return s


def _extract_function_schema(inst_or_scored):
    """Return the OpenAI function-schema dict from an instruction, or None.

    ToolBench corpora come in two action shapes depending on the loader.

      (a) toolbench_setup.py:
          actions = {'function': {'name': ..., 'description': ...,
                                  'parameters': ...}}

      (b) eval_toolbench_e2e.py's older loader:
          actions = {func_name: {'name': func_name, 'description': ...,
                                  'parameters': ...}}

    We handle both. Returns None when the instruction carries no schema.
    """
    actions = getattr(inst_or_scored, "actions", None) or {}
    if not actions:
        return None
    schema = actions.get("function")
    if isinstance(schema, dict):
        return schema
    first = next(iter(actions.values()), None)
    if isinstance(first, dict):
        return first
    return None


def _schema_to_openai_tool(schema, fallback_name, name_map):
    """Convert an extracted function-schema dict to an OpenAI tool entry.

    Sanitises the name to satisfy Mistral's validator. fallback_name is
    used when the schema lacks a name field.
    """
    raw_name = schema.get("name") or fallback_name
    name = _derive_function_name(raw_name, name_map)
    desc = schema.get("description") or ""
    params = schema.get("parameters") or {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query string"}
        },
        "required": [],
    }
    return {"name": name, "description": desc, "parameters": params}


def build_tool_schemas_for_query(
    retrieved: list,
    name_map: dict,
) -> list[dict]:
    """Build OpenAI-compatible function schemas from BEAR retrieval results.

    Instructions without an OpenAI schema are skipped.
    """
    out = []
    for r in retrieved:
        schema = _extract_function_schema(r)
        if schema is None:
            continue
        out.append(_schema_to_openai_tool(schema, r.id, name_map))
    return out


def build_monolithic_schemas(
    corpus, max_tools: int, name_map: dict
) -> list[dict]:
    """Build the monolithic tool list (no retrieval).

    Skips instructions without an OpenAI schema. The cap reflects valid
    tools emitted, not positions walked in the corpus. ``max_tools <= 0``
    means the whole corpus, matching ``eval_toolbench_e2e.py``.
    """
    if max_tools <= 0:
        max_tools = len(corpus)
    schemas = []
    for inst in corpus:
        if len(schemas) >= max_tools:
            break
        schema = _extract_function_schema(inst)
        if schema is None:
            continue
        schemas.append(_schema_to_openai_tool(schema, inst.id, name_map))
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


def build_id_to_function(corpus, name_map: dict) -> dict[str, str]:
    """Map api_id -> sanitized function name (mirrors how schemas are built).

    Walks the corpus the same way build_*_schemas() does, so the sanitized
    names produced here exactly match the names the LLM sees. Instructions
    without a schema are mapped to the sanitized form of their api_id; this
    keeps tool_correct() safe when the model emits the raw id even though
    no schema was offered.
    """
    out = {}
    for inst in corpus:
        schema = _extract_function_schema(inst)
        raw_name = (schema.get("name") if schema else None) or inst.id
        out[inst.id] = _derive_function_name(raw_name, name_map)
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
    debug_dump_n: int = 0,
    debug_dump_path = None,
    reasoning_mode: bool = False,
    temperature: float = 0.0,
    top_p: float | None = None,
    top_k: int | None = None,
    reasoning_effort: str | None = None,
):
    """Run one condition end-to-end. ``schemas_per_query_fn`` is a callable
    returning the tool schemas to pass for each query.

    When ``debug_dump_n > 0``, saves the first N (qtext, schemas, raw,
    pred, expected) tuples to ``debug_dump_path`` so failures can be
    inspected without rerunning the full eval. Returns (correct, dump_rows).
    """
    print(f"\n[{name}] running {len(queries)} queries ...")
    correct = np.zeros(len(queries), dtype=int)
    dump_rows = []
    t0 = time.time()
    for i, (qtext, ctx_tags, expected, _api_details) in enumerate(queries):
        schemas = schemas_per_query_fn(qtext, ctx_tags, expected)
        if use_react:
            pred, raw = call_llm_react(qtext, schemas, model, base_url,
                                       temperature=temperature, top_p=top_p, top_k=top_k,
                                       reasoning_mode=reasoning_mode,
                                       reasoning_effort=reasoning_effort)
        else:
            from eval_toolbench_e2e import call_llm_with_tools
            tc = call_llm_with_tools(qtext, schemas, model, base_url,
                                     temperature=temperature, top_p=top_p, top_k=top_k)
            pred = tc["name"] if tc else None
            raw = json.dumps(tc) if tc else "<no tool call>"
        correct[i] = tool_correct(pred, expected, id_to_function)
        if i < debug_dump_n:
            dump_rows.append({
                "condition": name,
                "index": i,
                "query": qtext,
                "n_schemas_offered": len(schemas),
                "first_few_schema_names": [s["name"] for s in schemas[:5]],
                "raw_response": (raw or "")[:2000],
                "predicted_name": pred,
                "expected_ids": sorted(expected),
                "expected_function_names": sorted(
                    {id_to_function.get(eid, "<missing>") for eid in expected}
                ),
                "correct": int(correct[i]),
            })
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (len(queries) - i - 1)
            print(f"  {i+1}/{len(queries)} done; acc-so-far = {correct[:i+1].mean():.3f}; ETA {eta/60:.1f} min")
    print(f"[{name}] done; tool-acc = {correct.mean():.3f}; elapsed {(time.time()-t0)/60:.1f} min")
    if dump_rows and debug_dump_path is not None:
        # Append-only so repeated conditions accumulate into one file
        existing = []
        if debug_dump_path.exists():
            try:
                existing = json.loads(debug_dump_path.read_text())
            except Exception:
                existing = []
        debug_dump_path.write_text(
            json.dumps(existing + dump_rows, indent=2)
        )
        print(f"  Debug dump appended: {debug_dump_path} (+{len(dump_rows)} rows)")
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
        default=0,
        help="Tools injected in the monolithic baseline; 0 = the whole corpus "
        "(default), matching eval_toolbench_e2e.py. Capping truncates the corpus, "
        "so the gold tool is often absent from the prompt and accuracy then "
        "measures coverage rather than the model's ability to select. The full "
        "3,225-tool corpus costs ~82k prompt tokens in the compact "
        "'name: description' form and needs a server context window to match "
        "(OLLAMA_CONTEXT_LENGTH=131072).",
    )
    p.add_argument(
        "--skip",
        nargs="+",
        default=[],
        choices=["mono-react", "bear-react", "bear-single"],
        help="Skip selected conditions (useful for resuming partial runs).",
    )
    p.add_argument(
        "--debug-dump-n",
        type=int,
        default=0,
        help="If >0, save the first N (query, schemas, raw, pred, expected) "
        "tuples per condition to results/toolbench_react_debug.json for "
        "inspecting what the model and the eval are actually doing. Set to "
        "5 or 10 when running --max-queries 20 for a quick correctness check.",
    )
    p.add_argument(
        "--run-label",
        type=str,
        default="",
        help="Tag inserted into the output filenames, e.g. --run-label gemma4-31b "
        "writes results/toolbench_react_metrics_gemma4-31b.json. Use it to keep "
        "different models' results from overwriting each other.",
    )
    p.add_argument("--temperature", type=float, default=0.0,
                   help="LLM sampling temperature (default 0.0 = greedy). Thinking "
                   "models expect their own recommended sampling, e.g. Gemma 4 "
                   "wants --temperature 1.0 --llm-top-p 0.95 --llm-top-k 64.")
    p.add_argument("--llm-top-p", type=float, default=None,
                   help="LLM nucleus sampling top_p (default: unset). Distinct "
                   "from the retrieval --top-k.")
    p.add_argument("--llm-top-k", type=int, default=None,
                   help="LLM top_k sampling (default: unset). Honored by Ollama's "
                   "OpenAI-compatible endpoint. Distinct from the retrieval --top-k.")
    p.add_argument(
        "--reasoning-mode",
        action="store_true",
        help="For natively-thinking models: drop the constrained {thought, action} "
        "schema (which would suppress the model's own reasoning) and instead let it "
        "reason freely, parsing the tool from a final 'Action:' line. Affects the "
        "ReAct conditions (mono-react, bear-react); the single-turn reference stays "
        "constrained. Use a run-label to keep these results separate.",
    )
    p.add_argument("--reasoning-effort", type=str, default=None,
                   choices=["none", "low", "medium", "high"],
                   help="OpenAI-standard reasoning_effort, honored by Ollama for "
                   "thinking models. Use 'none' to DISABLE a thinking model's "
                   "reasoning (Gemma 4 thinks by default), enabling a clean "
                   "thinking-on vs thinking-off ablation on the same model.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Namespace the output files so different models/runs do not clobber each
    # other. --run-label gives an explicit tag (e.g. a model name); a partial
    # run (subset of queries, or conditions skipped) is additionally suffixed so
    # it never overwrites the canonical full-run file.
    import re as _re
    label = ""
    if args.run_label:
        safe = _re.sub(r"[^A-Za-z0-9._-]+", "-", args.run_label).strip("-")
        label = f"_{safe}"
    partial = bool(args.max_queries) or bool(args.skip)
    suffix = f"{label}{'_partial' if partial else ''}"
    if suffix:
        print(f"NOTE: writing to results/toolbench_react_*{suffix}.* "
              "(run-label and/or partial-run suffix), leaving the canonical "
              "full-run results untouched.\n")

    log_path = RESULTS_DIR / f"toolbench_react_output{suffix}.txt"
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

        # Retrievers. build_retriever applies PRIORITY_WEIGHT internally when
        # governance=True and zero when governance=False. The bge backend
        # matches the manuscript ToolBench condition (BGE-base).
        retr_gov = build_retriever(corpus, backend="bge", governance=True)
        retr_no_gov = build_retriever(
            strip_governance(corpus), backend="bge", governance=False
        )

        # Shared name_map. _derive_function_name() updates it lazily as
        # schemas are built. Pre-seeding by passing the whole corpus through
        # build_id_to_function ensures the id->name mapping is complete
        # before any condition runs and that scoring agrees with what the
        # LLM sees.
        name_map: dict = {}
        id_to_function = build_id_to_function(corpus, name_map)

        # Sanity: how many instructions in the corpus carry a real OpenAI
        # function schema. The eval can only score correctly when the
        # number is close to the corpus size; a large gap means many
        # instructions had no req/opt parameters and were created with
        # actions={} by toolbench_setup.py.
        n_with_schema = sum(
            1 for inst in corpus if _extract_function_schema(inst) is not None
        )
        print(
            f"Corpus schema coverage: {n_with_schema}/{len(corpus)} "
            f"({100.0 * n_with_schema / max(len(corpus), 1):.1f}%) "
            f"instructions have an OpenAI function schema."
        )

        # Schema providers. The BEAR provider passes the query's
        # ground-truth category tags as Context.tags, matching the
        # end-to-end deployment in eval_toolbench.py:
        # ToolBench tools carry required_tags=[cat_tag], so an empty
        # context-tag set would exclude every tool. The monolithic
        # provider is tag-agnostic by design.
        # Fail loudly rather than let the server truncate the tool list; a
        # truncated monolithic prompt scores near zero for reasons that have
        # nothing to do with the model.
        if "mono-react" not in args.skip:
            _mono = build_monolithic_schemas(corpus, args.monolithic_cap, name_map)
            assert_prompt_fits(
                args.base_url,
                sum(len(s["name"]) + len((s.get("description") or "")[:400]) + 4
                    for s in _mono if s.get("name")),
                f"monolithic ({len(_mono)} tools)",
                model=args.model,
            )

        def mono_schemas(_qtext, _ctx_tags, _expected):
            return build_monolithic_schemas(
                corpus, args.monolithic_cap, name_map
            )

        def bear_schemas(qtext, ctx_tags, _expected):
            ctx = Context(tags=list(ctx_tags) if ctx_tags else [])
            res = retr_gov.retrieve(qtext, ctx, top_k=args.top_k)
            return build_tool_schemas_for_query(res, name_map)

        # Run conditions
        results: dict[str, np.ndarray] = {}

        # Optional debug dump (first N queries per condition)
        debug_dump_path = RESULTS_DIR / "toolbench_react_debug.json" if args.debug_dump_n > 0 else None
        if debug_dump_path is not None and debug_dump_path.exists():
            # Start fresh so dumps from old runs don't pile up.
            debug_dump_path.unlink()

        if "mono-react" not in args.skip:
            results["mono_react"] = run_condition(
                "Monolithic + ReAct",
                mono_schemas, queries, args.model, args.base_url,
                use_react=True, id_to_function=id_to_function,
                debug_dump_n=args.debug_dump_n,
                debug_dump_path=debug_dump_path,
                reasoning_mode=args.reasoning_mode,
                temperature=args.temperature, top_p=args.llm_top_p, top_k=args.llm_top_k,
                reasoning_effort=args.reasoning_effort,
            )

        if "bear-react" not in args.skip:
            results["bear_react"] = run_condition(
                "BEAR retrieval + ReAct",
                bear_schemas, queries, args.model, args.base_url,
                use_react=True, id_to_function=id_to_function,
                debug_dump_n=args.debug_dump_n,
                debug_dump_path=debug_dump_path,
                reasoning_mode=args.reasoning_mode,
                temperature=args.temperature, top_p=args.llm_top_p, top_k=args.llm_top_k,
                reasoning_effort=args.reasoning_effort,
            )

        if "bear-single" not in args.skip:
            results["bear_single"] = run_condition(
                "BEAR retrieval + single-turn (reference)",
                bear_schemas, queries, args.model, args.base_url,
                use_react=False, id_to_function=id_to_function,
                debug_dump_n=args.debug_dump_n,
                debug_dump_path=debug_dump_path,
                temperature=args.temperature, top_p=args.llm_top_p, top_k=args.llm_top_k,
                reasoning_effort=args.reasoning_effort,
            )

        # Summary
        print("\n--- Tool selection accuracy (1 if predicted tool matches any expected api_id) ---\n")
        header = f"{'Condition':<40}  {'Tool Acc [95% CI]':<25}  {'n':>5}"
        print(header)
        print("-" * len(header))
        rows = []
        for name, arr in results.items():
            out = bootstrap_ci(arr.astype(float), BOOTSTRAP_ITERS)
            # stat_utils.bootstrap_ci returns a dict; eval_retrieval_backends
            # fallback returns a 3-tuple. Accept either shape.
            if isinstance(out, dict):
                mean, lo, hi = out["point_estimate"], out["ci_lower"], out["ci_upper"]
            else:
                mean, lo, hi = out
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

        # Paired significance between conditions run on the same queries.
        # CI overlap on the marginals is the wrong test here; these conditions
        # share the 1,100 queries, so we report McNemar (exact) plus a paired
        # bootstrap on the delta.
        try:
            from stat_utils import mcnemar, paired_bootstrap
        except ImportError:
            mcnemar = paired_bootstrap = None
        comparisons = []
        if mcnemar is not None:
            pairs = [("bear_single", "bear_react"),   # does the ReAct scaffold help or hurt?
                     ("bear_react", "mono_react")]     # does governed retrieval beat monolithic?
            print("\n--- Paired comparisons (same queries; McNemar + paired bootstrap) ---\n")
            for hi_name, lo_name in pairs:
                if hi_name in results and lo_name in results:
                    a, b = results[hi_name], results[lo_name]
                    mc = mcnemar(a, b)
                    pb = paired_bootstrap(a.astype(float), b.astype(float), BOOTSTRAP_ITERS)
                    print(f"  {hi_name} vs {lo_name}: "
                          f"Δ={pb['delta']:+.3f} [{pb['ci_lower']:+.3f}, {pb['ci_upper']:+.3f}], "
                          f"McNemar p={mc['p_value']:.2e} "
                          f"(discordant {mc['b_a_right_b_wrong']}/{mc['c_a_wrong_b_right']})")
                    comparisons.append({
                        "higher": hi_name, "lower": lo_name,
                        "delta": pb["delta"], "delta_ci_lo": pb["ci_lower"],
                        "delta_ci_hi": pb["ci_upper"],
                        "paired_bootstrap_p": pb["p_value"],
                        "mcnemar_p": mc["p_value"],
                        "discordant_hi_only": mc["b_a_right_b_wrong"],
                        "discordant_lo_only": mc["c_a_wrong_b_right"],
                    })

        # LaTeX block
        print("\n--- LaTeX table (paste into manuscript as tab:e2e-react) ---\n")
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

        # JSON. Persist per-query 0/1 arrays alongside the aggregates so the
        # paired tests are reproducible from disk without re-running the eval.
        out_path = RESULTS_DIR / f"toolbench_react_metrics{suffix}.json"
        with out_path.open("w") as f:
            json.dump({"model": args.model, "top_k": args.top_k,
                       "monolithic_cap": args.monolithic_cap, "rows": rows,
                       "comparisons": comparisons,
                       "per_query_correct": {k: v.astype(int).tolist()
                                             for k, v in results.items()}},
                      f, indent=2)
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
