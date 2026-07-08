#!/usr/bin/env python3
"""Diagnostic: does retrieval even surface the ground-truth tools for the ReAct
tasks? No LLM calls -- retrieval only. If full-tool coverage@k is low, the ReAct
SoPR floor is a retrieval-coverage artifact (fixable with top_k), not the agent.

For each multi-tool task we need ALL of its relevant_apis in the top-k retrieved
set for the agent to have any chance. Reports, per k and per condition:
  * full-coverage rate: fraction of tasks with ALL ground-truth tools in top-k
  * mean per-tool recall@k
Governed vs ungoverned side by side -- if governance lifts coverage, that is the
mechanism that should turn into an SoPR gap once k is high enough to leave the floor.
"""
import argparse
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS_DIR))

from eval_stabletoolbench_react import (  # noqa: E402
    build_retrievers, load_multistep_tasks, build_apiid_map,
    retrieve_tools, MULTISTEP_SPLITS,
)


def gt_pairs(task):
    s = set()
    for a in task["relevant_apis"]:
        if isinstance(a, (list, tuple)) and len(a) >= 2:
            s.add((a[0], a[1]))
    return s


def retrieved_pairs(insts, apiid_to_api):
    out = set()
    for inst in insts:
        api = apiid_to_api.get(inst.id)
        if api:
            out.add((api.get("tool_name"), api.get("api_name")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="bge")
    ap.add_argument("--max-tasks", type=int, default=20)
    ap.add_argument("--ks", type=int, nargs="*", default=[5, 10, 15, 20, 30])
    ap.add_argument("--splits", nargs="*", default=None)
    args = ap.parse_args()

    gov, nog, qmap = build_retrievers(args.backend)
    apiid = build_apiid_map()
    tasks = load_multistep_tasks(max_tasks=args.max_tasks, splits=args.splits)
    tasks = [t for t in tasks if gt_pairs(t)]
    avg_gt = sum(len(gt_pairs(t)) for t in tasks) / len(tasks)
    print(f"[setup] {len(tasks)} tasks, avg {avg_gt:.1f} ground-truth tools/task, "
          f"backend={args.backend}, corpus={len(apiid)} APIs\n")

    for k in args.ks:
        st = {"governed": [0, 0.0], "ungoverned": [0, 0.0]}
        for task in tasks:
            gt = gt_pairs(task)
            q = task["query"]
            row = qmap.get(q)
            tags = row[1] if row else []
            for cond, retr, use_tags in [("governed", gov, True), ("ungoverned", nog, False)]:
                got = retrieved_pairs(retrieve_tools(retr, q, tags, use_tags, k), apiid)
                hit = len(gt & got)
                st[cond][0] += 1 if hit == len(gt) else 0
                st[cond][1] += hit / len(gt)
        n = len(tasks)
        print(f"top_k={k:>2}   "
              f"gov: full-cov={st['governed'][0]:>2}/{n} ({st['governed'][0]/n:.2f})  "
              f"recall={st['governed'][1]/n:.2f}   |   "
              f"nog: full-cov={st['ungoverned'][0]:>2}/{n} ({st['ungoverned'][0]/n:.2f})  "
              f"recall={st['ungoverned'][1]/n:.2f}")


if __name__ == "__main__":
    main()
