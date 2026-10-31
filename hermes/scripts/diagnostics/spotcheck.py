"""Print the tool calls of guest cells whose graded token was classed read or none."""
import csv
import json
import os
import sys

rows = list(csv.DictReader(open(os.path.expanduser(sys.argv[1]))))
RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
R = os.path.join(RUNS, "stage1", "results")
n = 0
for r in rows:
    if r["role"] != "guest" or not any(k in r["str_components"] for k in ("=read", "=none")) or n >= int(sys.argv[2]):
        continue
    n += 1
    msgs = json.load(open(f"{R}/{r['cell']}.json.transcript.json"))["messages"]
    calls = {tc["id"]: (tc["function"]["name"], tc["function"]["arguments"])
             for m in msgs for tc in (m.get("tool_calls") or [])}
    print("==", r["cell"][:60], "|", r["str_components"], "|", r["score"], "->", r["score_strict"])
    for m in msgs:
        if m.get("role") == "tool":
            nm, a = calls.get(m.get("tool_call_id"), ("?", ""))
            print("   ", nm, a[:90].replace("\n", " "), "|", str(m.get("content"))[:70].replace("\n", " "))
    fa = [m for m in msgs if m.get("role") == "assistant" and (m.get("content") or "").strip()]
    print("    final answer:", (fa[-1]["content"] if fa else "")[:160].replace("\n", " "))
