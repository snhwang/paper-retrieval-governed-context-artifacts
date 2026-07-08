#!/usr/bin/env python3
"""End-to-end multi-step ReAct on StableToolBench: governed vs ungoverned retrieval.

A genuine reason-act-observe loop. For each ToolBench multi-tool task (the G2/G3
splits == StableToolBench I2/I3), BEAR retrieval surfaces the top-k candidate
tools (governed vs ungoverned), a ReAct agent then calls those tools against the
StableToolBench virtual API server over multiple steps, and a ToolEval-style
judge scores task success (SoPR) and head-to-head wins (SoWR).

Model roles (all OpenAI; new SDK):
  * agent   : gpt-5.4-mini  -- the multi-step reasoner (env AGENT_MODEL)
  * judge   : gpt-5.4-mini  -- SoPR / SoWR verdicts    (env JUDGE_MODEL)
  * simulator (cache-miss tool responses): gpt-4o-mini, INSIDE the sim server.

Methodology / disclosure (put in the paper):
  * The simulator (gpt-4o-mini) and judge (gpt-5.4-mini) are NOT the models used
    on the public StableToolBench leaderboard, so absolute SoPR is not comparable
    to it. The controlled comparison is governed vs ungoverned under the SAME
    simulator, agent, and judge -- those choices cancel in the delta.
  * The agent is a mid/upper-tier "mini" reasoning model on purpose: strong enough
    to use a well-scoped tool set, and if the governed-vs-ungoverned gap vanishes
    on the prototype that is evidence the agent is too capable (ceiling), not that
    governance fails. Drop to a weaker agent before concluding no effect.

Prototype first: --max-tasks 20 before any full run.
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

from eval_toolbench import (  # noqa: E402
    load_toolbench_corpus_and_queries,
    build_retriever,
    strip_governance,
)
from bear.models import Context  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# --- Config (override via env or flags) -------------------------------------
SIM_SERVER_URL = os.environ.get("SIM_SERVER_URL", "http://127.0.0.1:8080")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "gpt-5.4-mini-2026-03-17")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-5.4-mini-2026-03-17")

BENCH_PATH = EVALS_DIR / "data" / "external_benchmarks" / "toolbench" / "benchmark_data.json"
# G2 == intra-category multi-tool (I2); G3 == multi-category multi-tool (I3).
MULTISTEP_SPLITS = ["g2_instruction", "g2_category", "g3_instruction"]


# --- OpenAI JSON completion (handles reasoning-model params) -----------------
def _is_reasoning(model: str) -> bool:
    m = model.lower()
    return m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4")


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if "```" in text:
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.replace("json", "", 1).strip() if text.lstrip().startswith("json") else text
    try:
        return json.loads(text)
    except Exception:
        # last-ditch: grab the outermost {...}
        i, j = text.find("{"), text.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(text[i:j + 1])
            except Exception:
                pass
        return {}


def openai_json(messages: list, model: str, max_out: int = 2048, effort: str | None = None) -> dict:
    """One OpenAI chat completion returning parsed JSON. Branches on reasoning vs
    chat models for the incompatible params (max_completion_tokens/temperature)."""
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY (and OPENAI_BASE_URL if set)
    kwargs = dict(model=model, messages=messages,
                  response_format={"type": "json_object"})
    if _is_reasoning(model):
        kwargs["max_completion_tokens"] = max_out
        if effort:
            kwargs["reasoning_effort"] = effort
    else:
        kwargs["max_tokens"] = max_out
        kwargs["temperature"] = 0
    try:
        resp = client.chat.completions.create(**kwargs)
    except TypeError:
        kwargs.pop("reasoning_effort", None)
        resp = client.chat.completions.create(**kwargs)
    return _parse_json(resp.choices[0].message.content)


# --- ToolBench data ----------------------------------------------------------
def _api_id(api: dict) -> str:
    """Reproduce eval_toolbench's corpus id so retrieved instructions map back to
    their full API schema + the /virtual identifiers."""
    cat = api.get("category_name", "unknown")
    tool = api.get("tool_name", "unknown")
    api_name = api.get("api_name", "unknown")
    cat_tag = cat.lower().replace(" ", "_").replace("&", "and")
    return f"toolbench/{cat_tag}/{tool}/{api_name}"


def _parse_field(row: dict, key: str):
    v = row.get(key, "[]")
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v or []


def build_apiid_map() -> dict:
    """api_id -> api dict, across all splits (superset of any retrieval result)."""
    data = json.load(open(BENCH_PATH))
    out = {}
    for rows in data.values():
        for row in rows:
            for api in _parse_field(row, "api_list"):
                if isinstance(api, dict):
                    out[_api_id(api)] = api
    return out


def load_multistep_tasks(max_tasks=None, splits=None) -> list:
    """Multi-tool tasks, round-robined across splits so a small prototype sample
    stays balanced across G2/G3 rather than all-G2."""
    splits = splits or MULTISTEP_SPLITS
    data = json.load(open(BENCH_PATH))
    per_split = []
    for s in splits:
        bucket = []
        for row in data.get(s, []):
            q = row.get("query", "")
            if not q:
                continue
            bucket.append({
                "query_id": row.get("query_id"),
                "query": q,
                "api_list": _parse_field(row, "api_list"),
                "relevant_apis": _parse_field(row, "relevant_apis"),
                "split": s,
            })
        per_split.append(bucket)
    tasks = []
    for tup in zip(*per_split):          # round-robin, truncates to shortest
        tasks.extend(tup)
    for bucket in per_split:             # then append the remainder
        tasks.extend(bucket[len(tasks) // max(1, len(per_split)):])
    return tasks[:max_tasks] if max_tasks else tasks


# --- Tool execution against the sim server ----------------------------------
def execute_tool(api: dict, arguments: dict, strip: str = "truncate") -> dict:
    """POST to StableToolBench /virtual. Server standardizes the names and hits
    its cache; on a cache-miss it falls back to the gpt-4o-mini simulator (our
    patched main.py catches the dead real-API endpoint)."""
    import requests
    payload = {
        "category": api.get("category_name", ""),
        "tool_name": api.get("tool_name", ""),
        "api_name": api.get("api_name", ""),
        "tool_input": arguments if isinstance(arguments, dict) else {},
        "strip": strip,
        "toolbench_key": "",
    }
    try:
        r = requests.post(f"{SIM_SERVER_URL}/virtual", json=payload, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": f"tool call failed: {e}", "response": ""}


# --- BEAR retrieval: the candidate-tool provider ----------------------------
def build_retrievers(backend="bge"):
    corpus, queries, _ = load_toolbench_corpus_and_queries()
    gov = build_retriever(corpus, backend=backend, governance=True)
    nog = build_retriever(strip_governance(corpus), backend=backend, governance=False)
    return gov, nog, {q[0]: q for q in queries}


def retrieve_tools(retriever, query_text, tags, use_tags, top_k):
    ctx = Context(tags=tags if use_tags else [])
    return [r.instruction for r in retriever.retrieve(query_text, ctx, top_k=top_k)]


def build_tool_menu(instructions, apiid_to_api):
    """Ordered [(name, api_dict)]; disambiguate api_name collisions by tool."""
    menu, seen = [], set()
    for inst in instructions:
        api = apiid_to_api.get(inst.id)
        if not api:
            continue
        name = api.get("api_name", "tool")
        if name in seen:
            name = f"{api.get('tool_name', 'tool')} :: {name}"
        seen.add(name)
        menu.append((name, api))
    return menu


def _tool_line(name, api):
    reqs = api.get("required_parameters", []) or []
    opts = api.get("optional_parameters", []) or []
    def fmt(p):
        return f"{p.get('name')}({p.get('type','')})"
    params = ", ".join(fmt(p) for p in reqs)
    if opts:
        params += (", " if params else "") + "[optional: " + ", ".join(fmt(p) for p in opts) + "]"
    desc = (api.get("api_description", "") or "").strip().replace("\n", " ")[:200]
    return f'- "{name}": {desc}\n    params: {params or "(none)"}'


def resolve_tool(name, name_to_api):
    if name in name_to_api:
        return name_to_api[name]
    low = {k.lower(): v for k, v in name_to_api.items()}
    if name and name.lower() in low:
        return low[name.lower()]
    for k, v in name_to_api.items():           # substring fallback
        if name and (name.lower() in k.lower() or k.lower() in name.lower()):
            return v
    return None


# --- ReAct loop --------------------------------------------------------------
SYSTEM_TMPL = """You are a tool-using agent solving a user's task by calling APIs over multiple steps.

TASK:
{query}

AVAILABLE TOOLS (you may ONLY call these):
{tools}

Work step by step. At EACH step respond with a SINGLE JSON object and nothing else:
  To call a tool:   {{"thought": "...", "action": "call_tool", "tool": "<exact tool name>", "arguments": {{...}}}}
  To finish:        {{"thought": "...", "action": "finish", "answer": "<final answer to the user>"}}

Rules:
- Use the tool results (observations) to build your answer; do not invent API outputs.
- Call one tool per step. Gather everything the task needs before finishing.
- Finish within {max_steps} steps with a concrete answer."""


def react_solve(task, instructions, apiid_to_api, model, max_steps=8):
    menu = build_tool_menu(instructions, apiid_to_api)
    name_to_api = {n: a for n, a in menu}
    tools_str = "\n".join(_tool_line(n, a) for n, a in menu) or "(no tools available)"
    system = SYSTEM_TMPL.format(query=task["query"], tools=tools_str, max_steps=max_steps)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Begin. Respond with your first JSON step."},
    ]
    transcript, answer = [], None
    for _ in range(max_steps):
        out = openai_json(messages, model, max_out=2048, effort="low")
        thought = out.get("thought", "")
        if out.get("action") == "finish" or ("answer" in out and out.get("action") != "call_tool"):
            answer = out.get("answer", "")
            transcript.append({"thought": thought, "action": "finish", "answer": answer})
            break
        tool = out.get("tool", "")
        args = out.get("arguments", {}) or {}
        api = resolve_tool(tool, name_to_api)
        if api is None:
            obs = {"error": f"No such tool '{tool}'. Valid tools: {list(name_to_api)}", "response": ""}
        else:
            obs = execute_tool(api, args)
        obs_str = json.dumps(obs)[:1500]
        transcript.append({"thought": thought, "tool": tool, "arguments": args, "observation": obs_str})
        messages.append({"role": "assistant", "content": json.dumps(out)})
        messages.append({"role": "user", "content": f"Observation: {obs_str}\nRespond with your next JSON step."})
    return {"transcript": transcript, "answer": answer, "steps": len(transcript),
            "num_tools": len(menu)}


def format_transcript(result) -> str:
    lines = []
    for i, s in enumerate(result["transcript"], 1):
        if s.get("action") == "finish":
            lines.append(f"Step {i}: FINISH\n  Answer: {s.get('answer','')}")
        else:
            lines.append(f"Step {i}:\n  Thought: {s.get('thought','')}\n"
                         f"  Tool: {s.get('tool','')}  Args: {json.dumps(s.get('arguments',{}))}\n"
                         f"  Observation: {s.get('observation','')[:600]}")
    if result.get("answer") is None:
        lines.append("(agent did not produce a final answer within the step budget)")
    return "\n".join(lines) or "(empty transcript)"


# --- ToolEval-style judge (SoPR + SoWR) -------------------------------------
SOPR_TMPL = """You are ToolEval, an impartial judge of tool-using agents.

USER TASK:
{query}

AGENT TRANSCRIPT:
{transcript}

Decide whether the agent SOLVED the task: the final answer must actually fulfill
the user's request using real tool observations (not fabricated). Partial or
hallucinated answers are NOT solved.

Respond with a single JSON object: {{"solved": true|false, "reason": "<brief>"}}"""

SOWR_TMPL = """You are ToolEval, comparing two agents on the SAME task.

USER TASK:
{query}

--- AGENT A ---
{ta}

--- AGENT B ---
{tb}

Which agent better solved the task (more complete, more grounded in real tool
observations)? If truly indistinguishable, answer "tie".

Respond with a single JSON object: {{"winner": "A"|"B"|"tie", "reason": "<brief>"}}"""


def judge_solved(task, result, model):
    out = openai_json([{"role": "user",
                        "content": SOPR_TMPL.format(query=task["query"],
                                                    transcript=format_transcript(result))}],
                      model, max_out=1024, effort="medium")
    return bool(out.get("solved", False)), out.get("reason", "")


def judge_pairwise(task, res_gov, res_nog, model, gov_is_a: bool):
    """SoWR. gov_is_a alternates governed's A/B slot per task to cancel position bias."""
    ta = res_gov if gov_is_a else res_nog
    tb = res_nog if gov_is_a else res_gov
    out = openai_json([{"role": "user",
                        "content": SOWR_TMPL.format(query=task["query"],
                                                    ta=format_transcript(ta),
                                                    tb=format_transcript(tb))}],
                      model, max_out=1024, effort="medium")
    w = str(out.get("winner", "tie")).strip().upper()
    if w == "A":
        return "governed" if gov_is_a else "ungoverned"
    if w == "B":
        return "ungoverned" if gov_is_a else "governed"
    return "tie"


# --- Aggregation -------------------------------------------------------------
def _bootstrap_ci(vals, n=2000, seed=0):
    import random
    if not vals:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        s = [vals[rng.randrange(len(vals))] for _ in vals]
        means.append(sum(s) / len(s))
    means.sort()
    return (means[int(0.025 * n)], means[int(0.975 * n)])


def main():
    ap = argparse.ArgumentParser(description="Multi-step ReAct on StableToolBench: governed vs ungoverned")
    ap.add_argument("--backend", default="bge")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--max-tasks", type=int, default=20, help="Prototype small first.")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--splits", nargs="*", default=None, help=f"default: {MULTISTEP_SPLITS}")
    ap.add_argument("--output", default=str(REPO_ROOT / "results" / "stabletoolbench_react.json"))
    args = ap.parse_args()

    print(f"[setup] agent={AGENT_MODEL} judge={JUDGE_MODEL} sim={SIM_SERVER_URL} "
          f"backend={args.backend} top_k={args.top_k}")
    gov, nog, qmap = build_retrievers(args.backend)
    apiid_to_api = build_apiid_map()
    tasks = load_multistep_tasks(max_tasks=args.max_tasks, splits=args.splits)
    print(f"[setup] {len(tasks)} tasks, {len(apiid_to_api)} known APIs")

    results = {"governed": [], "ungoverned": []}
    sopr = {"governed": [], "ungoverned": []}
    sowr = []  # winner per task

    for ti, task in enumerate(tasks):
        q = task["query"]
        row = qmap.get(q)
        tags = row[1] if row else []
        run = {}
        for cond, retr, use_tags in [("governed", gov, True), ("ungoverned", nog, False)]:
            tools = retrieve_tools(retr, q, tags, use_tags, args.top_k)
            res = react_solve(task, tools, apiid_to_api, AGENT_MODEL, max_steps=args.max_steps)
            solved, reason = judge_solved(task, res, JUDGE_MODEL)
            res["solved"], res["reason"] = solved, reason
            run[cond] = res
            sopr[cond].append(1.0 if solved else 0.0)
            results[cond].append({"query_id": task["query_id"], "query": q,
                                  "split": task["split"], "solved": solved,
                                  "steps": res["steps"], "num_tools": res["num_tools"],
                                  "answer": res["answer"], "reason": reason})
        winner = judge_pairwise(task, run["governed"], run["ungoverned"],
                                JUDGE_MODEL, gov_is_a=(ti % 2 == 0))
        sowr.append(winner)
        print(f"[{ti+1}/{len(tasks)}] {task['split']} "
              f"gov={'PASS' if run['governed']['solved'] else 'fail'} "
              f"nog={'PASS' if run['ungoverned']['solved'] else 'fail'} win={winner}")

    def rate(v):
        return sum(v) / len(v) if v else 0.0
    gov_sopr, nog_sopr = rate(sopr["governed"]), rate(sopr["ungoverned"])
    gov_wins = sum(1 for w in sowr if w == "governed")
    nog_wins = sum(1 for w in sowr if w == "ungoverned")
    ties = sum(1 for w in sowr if w == "tie")
    gov_sowr = gov_wins / len(sowr) if sowr else 0.0

    summary = {
        "config": {"agent_model": AGENT_MODEL, "judge_model": JUDGE_MODEL,
                   "simulator": "gpt-4o-mini (in sim server)", "backend": args.backend,
                   "top_k": args.top_k, "max_steps": args.max_steps,
                   "splits": args.splits or MULTISTEP_SPLITS, "n_tasks": len(tasks)},
        "SoPR": {"governed": gov_sopr, "ungoverned": nog_sopr,
                 "delta": gov_sopr - nog_sopr,
                 "governed_ci95": _bootstrap_ci(sopr["governed"]),
                 "ungoverned_ci95": _bootstrap_ci(sopr["ungoverned"])},
        "SoWR": {"governed_win_rate": gov_sowr, "governed_wins": gov_wins,
                 "ungoverned_wins": nog_wins, "ties": ties},
        "per_task": results,
        "_disclosure": ("Simulator gpt-4o-mini and judge/agent gpt-5.4-mini are not the "
                        "StableToolBench leaderboard models; absolute SoPR is not comparable. "
                        "The governed-vs-ungoverned delta holds simulator/agent/judge fixed."),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n==== SUMMARY ====")
    print(f"SoPR  governed={gov_sopr:.3f}  ungoverned={nog_sopr:.3f}  delta={gov_sopr-nog_sopr:+.3f}")
    print(f"SoWR  governed wins={gov_wins}  ungoverned wins={nog_wins}  ties={ties}  "
          f"(gov win rate={gov_sowr:.3f})")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
