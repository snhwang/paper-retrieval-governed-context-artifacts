"""Anomaly look-ups for the stage-1 write-up (read-only)."""
import csv
import json
import os
from collections import Counter

RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
ANALYSIS = os.environ.get("WP7_ANALYSIS") or os.path.join(RUNS, "analysis")
rows = list(csv.DictReader(open(os.path.join(ANALYSIS, "stage1", "cells.csv"))))
R = os.path.join(RUNS, "stage1")


def res(cell):
    return json.load(open(f"{R}/results/{cell}.json"))


for r in rows:
    if r["cap_hits"] not in ("0", ""):
        print("CAP HIT", r["cell"], r["score"], r["notes"][:120])

print("--- B operator gui_onboarding d300")
for r in rows:
    if r["task"] == "gui_onboarding" and r["arm"] == "B" and r["role"] == "operator" and r["decoys"] == "300":
        x = res(r["cell"])
        print(" ", r["cell"][-3:], r["score"], "|", r["notes"][:100], "| bridge", x.get("bridge_calls"),
              "via", x["wp7"]["via_bridge"][:6], "| tools", list(x["tool_counts"])[:8])

print("--- project_mcp_setup")
x = res([r for r in rows if r["task"] == "project_mcp_setup" and r["arm"] == "A" and r["role"] == "operator"][0]["cell"])
print("  manage_connections in agent surface:", "manage_connections" in x["wp7"]["surface"]["agent_tools"],
      "| surface size", len(x["wp7"]["surface"]["agent_tools"]))
print("  notes over all cells:", Counter(r["notes"] for r in rows if r["task"] == "project_mcp_setup").most_common(4))

print("--- C-gate guest ambiguous_delete_ask")
for r in rows:
    if r["task"] == "ambiguous_delete_ask" and r["arm"] == "C-gate" and r["role"] == "guest":
        x = res(r["cell"])
        print(" ", r["cell"][-12:], r["score"], "|", r["notes"][:60], "| tools", x["tool_counts"], "| not sent",
              r["calls_not_sent"], "| op ran", r["op_exec_guest"], "| trap", r["trap_unsafe"])

print("--- per arm x role: op_exec_guest, calls_not_sent, blocked, gate_blocks")
agg = {}
for r in rows:
    k = (r["arm"], r["role"])
    a = agg.setdefault(k, Counter())
    for m in ("op_exec_guest", "calls_not_sent", "blocked", "gate_blocks", "invented", "decoy_calls"):
        a[m] += int(float(r[m])) if r[m] not in ("", "None") else 0
for k in sorted(agg):
    print(" ", k, dict(agg[k]))

print("--- timeouts")
log = [json.loads(ln) for ln in open(f"{R}/logs/cells.jsonl")]
for d in log:
    if d.get("event") == "cell_done" and d["returncode"] != 0:
        recs = [json.loads(ln) for ln in open(d["audit"])]
        mc = [x for x in recs if x.get("schema") == "bear.model_call/1"]
        sess = len({x.get("session_id") for x in mc})
        lat = sum(x.get("latency_ms") or 0 for x in mc) / 1000
        print(" ", d["cell"], "rc", d["returncode"], "| model calls", len(mc), "| sessions", sess,
              "| model s", round(lat), "| max s", round(max((x.get("latency_ms") or 0) for x in mc) / 1000) if mc else 0)
