"""More anomaly look-ups (read-only)."""
import csv
import json
import os

RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
ANALYSIS = os.environ.get("WP7_ANALYSIS") or os.path.join(RUNS, "analysis")
rows = list(csv.DictReader(open(os.path.join(ANALYSIS, "stage1", "cells.csv"))))
R = os.path.join(RUNS, "stage1")

for r in rows:
    if r["task"] == "project_mcp_setup" and not r["notes"]:
        x = json.load(open(f"{R}/results/{r['cell']}.json"))
        print("full-score project_mcp_setup:", r["cell"], r["score"], "| tool_counts", x["tool_counts"],
              "| invented", r["invented_names"])
        msgs = json.load(open(f"{R}/results/{r['cell']}.json.transcript.json"))["messages"]
        calls = {tc["id"]: tc["function"]["name"] for m in msgs for tc in (m.get("tool_calls") or [])}
        for m in msgs:
            if m.get("role") == "tool" and calls.get(m.get("tool_call_id")) == "manage_connections":
                print("   manage_connections result:", str(m.get("content"))[:200])

for cell in ("B__layout_terminal_readout__operator__d0__nemotron__ann-off__r1",
             "B__layout_terminal_readout__operator__d0__nemotron__ann-off__r2"):
    recs = [json.loads(ln) for ln in open(f"{R}/audit/{cell}.jsonl")]
    mc = [x for x in recs if x.get("schema") == "bear.model_call/1"]
    print(cell, [(x["input_tokens"], x["output_tokens"], x["finish_reason"], round(x["latency_ms"] / 1000))
                 for x in mc])
