#!/usr/bin/env python3
"""SCAFFOLD: end-to-end multi-step ReAct on StableToolBench, governed vs ungoverned.

This is a skeleton, not a finished eval. It wires the parts we control and marks
the StableToolBench-specific integration points as TODO. It is NOT expected to
run until (a) the StableToolBench sim server is up and answering, and (b) the
TODOs are filled against that server's actual request/response format.

Machine layout this scaffold assumes:
  * agent LLM  : Mistral-Nemo via vLLM on the x86 main box   (AGENT_BASE_URL)
  * sim server : StableToolBench simulated API server         (SIM_SERVER_URL)
  * simulator  : Claude Sonnet 5 (Anthropic)   -- for cache-miss API responses
  * judge      : Claude Sonnet 5 (Anthropic)   -- ToolEval SoPR/SoWR
  * retrieval  : BEAR governed vs ungoverned (this repo)

Methodology note: simulator and judge are Sonnet 5 (not GPT-4), so absolute
pass rates are NOT comparable to the StableToolBench leaderboard. The controlled
comparison is governed vs ungoverned under the SAME simulator and judge, so that
choice cancels out. Disclose this in the paper.

Prototype first: run on ~20 I2/I3 tasks (--max-tasks 20) before any full run.
"""
import argparse
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

# Load .env so ANTHROPIC_API_KEY, AGENT_BASE_URL, and SIM_SERVER_URL can all be
# set there instead of exported each session. Uses the artifacts-repo .env (the
# one that already holds the Anthropic key).
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# --- Endpoints (override via env or flags) ----------------------------------
AGENT_BASE_URL = os.environ.get("AGENT_BASE_URL", "http://<MAIN-BOX-IP>:8000/v1")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "mistralai/Mistral-Nemo-Instruct-2407")
SIM_SERVER_URL = os.environ.get("SIM_SERVER_URL", "http://127.0.0.1:8080")  # StableToolBench
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


# --- Sonnet 5 client (simulator + judge roles) ------------------------------
def anthropic_call(prompt: str, *, role: str, max_tokens: int = 4096) -> str:
    """One Sonnet-5 completion. role='simulator' disables thinking (fast, cheap,
    roughly deterministic API responses); role='judge' keeps adaptive thinking
    on (better verdicts). Requires ANTHROPIC_API_KEY (loaded from .env)."""
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    kwargs = dict(model=ANTHROPIC_MODEL, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": prompt}])
    if role == "simulator":
        kwargs["thinking"] = {"type": "disabled"}
    # NOTE: max_tokens caps thinking + output on Sonnet 5; raise it for the judge
    # if verdicts come back empty.
    msg = client.messages.create(**kwargs)
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


# --- Agent LLM (Mistral-Nemo via vLLM on the main box) ----------------------
def agent_call(messages: list) -> str:
    """One turn of the ReAct agent via the OpenAI-compatible vLLM endpoint."""
    from openai import OpenAI
    client = OpenAI(base_url=AGENT_BASE_URL, api_key="EMPTY")
    resp = client.chat.completions.create(model=AGENT_MODEL, messages=messages,
                                           temperature=0.0, max_tokens=512)
    return resp.choices[0].message.content


# --- BEAR retrieval: the candidate-tool provider ----------------------------
def build_retrievers(backend="bge"):
    corpus, queries, _ = load_toolbench_corpus_and_queries()
    gov = build_retriever(corpus, backend=backend, governance=True)
    nog = build_retriever(strip_governance(corpus), backend=backend, governance=False)
    return gov, nog, {q[0]: q for q in queries}


def retrieve_tools(retriever, query_text, tags, use_tags, top_k):
    ctx = Context(tags=tags if use_tags else [])
    return [r.instruction for r in retriever.retrieve(query_text, ctx, top_k=top_k)]


# --- StableToolBench integration points (TODO) ------------------------------
def load_multistep_tasks(max_tasks=None):
    """TODO: load ToolBench I2/I3 tasks in the form StableToolBench expects.
    Return a list of task dicts (query, available tool schemas / all-tool set,
    ground-truth solution if used). The I2/I3 split is in the ToolBench test
    data already present under evals/data/external_benchmarks/toolbench/."""
    raise NotImplementedError("Fill from ToolBench I2/I3 test files.")


def execute_tool(sim_server_url, tool_name, arguments):
    """TODO: POST to the StableToolBench sim server and return the observation.
    Match the server's exact route + request/response schema (check its README).
    If the server returns a cache miss, it should fall back to the Sonnet-5
    simulator via anthropic_call(..., role='simulator')."""
    raise NotImplementedError("Match StableToolBench sim-server API.")


def react_solve(task, tools, max_steps=8):
    """Genuine multi-step reason-act-observe loop against the sim server.
    Skeleton of the control flow; prompt formatting + parsing TODO to match the
    agent and the sim server."""
    transcript = []
    # system + tool schemas -> messages ; then loop:
    #   thought/action = agent_call(messages)
    #   name, args = parse_action(thought/action)
    #   obs = execute_tool(SIM_SERVER_URL, name, args)   # <- multi-step happens here
    #   messages.append(observation=obs) ; transcript.append(...)
    #   break on final answer or max_steps
    raise NotImplementedError("Wire prompt/parse/loop against agent + sim server.")


def judge_task(task, transcript) -> dict:
    """TODO: ToolEval-style SoPR/SoWR via Sonnet 5. Build the ToolEval judge
    prompt (task + transcript), call anthropic_call(..., role='judge'), parse
    the pass/fail (and win) verdict. Same judge for both conditions."""
    raise NotImplementedError("Implement ToolEval judge prompt + parse.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", default="bge")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--max-tasks", type=int, default=20, help="Prototype small first.")
    ap.add_argument("--output", default=str(REPO_ROOT / "results" / "stabletoolbench_react.json"))
    args = ap.parse_args()

    gov, nog, qmap = build_retrievers(args.backend)
    tasks = load_multistep_tasks(max_tasks=args.max_tasks)   # TODO

    results = {"governed": [], "ungoverned": []}
    for task in tasks:
        q = task["query"]
        row = qmap.get(q)
        tags = row[1] if row else []
        for cond, retr, use_tags in [("governed", gov, True), ("ungoverned", nog, False)]:
            tools = retrieve_tools(retr, q, tags, use_tags, args.top_k)
            transcript = react_solve(task, tools)            # TODO
            verdict = judge_task(task, transcript)           # TODO
            results[cond].append({"query": q, "verdict": verdict})

    # aggregate SoPR (pass rate) per condition; compare governed vs ungoverned.
    # (write results to args.output; add bootstrap CIs + repro footer)
    print("scaffold: fill the three TODOs, then aggregate + save.")


if __name__ == "__main__":
    main()
