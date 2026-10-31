"""Which needed groups rank beyond k under each backend (first turn, operator cells)."""
import json
import os
import sys
from collections import Counter

H = os.environ.get("WP7_HERMES_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
sys.path.insert(0, H)
import ksweep_stage2 as ks  # noqa: E402

root = os.path.join(RUNS, "stage1")
bm = ks.Bm25(root, os.path.join(ks.HERE, "registry", "harness_registry.stage1.json"))
tail = {"nemotron": Counter(), "bm25": Counter()}
for d in ks.load_jsonl(os.path.join(root, "logs", "cells.jsonl")):
    if d.get("event") != "cell_done" or d["returncode"] != 0 or d["arm"] not in ks.ARMS_USED:
        continue
    if d["switches"]["role"] != "operator" or d["task"] not in ks.NEEDED:
        continue
    recs = ks.load_jsonl(d["audit"])
    sess = next((r.get("session_id") for r in recs if r.get("session_id")), None)
    comp = [r for r in recs if r.get("schema") == "bear.narrowing/1" and r.get("session_id") == sess
            and r.get("status") == "ok" and not r.get("reused_from")]
    if not comp:
        continue
    first = comp[0]
    orders = {"nemotron": ks.admissible_order([*(first.get("offered") or []), *(first.get("ranked_out") or [])]),
              "bm25": bm.rank(first, d["switches"]["decoys"], first.get("query") or "")}
    for be, order in orders.items():
        for g in ks.NEEDED[d["task"]]:
            ranks = [order.index(t) + 1 for t in g if t in order]
            r = min(ranks) if ranks else None
            if r is None or r > 12:
                tail[be][(d["task"], "/".join(g), "d" + str(d["switches"]["decoys"]),
                          "beyond 25" if (r is None or r > 25) else "13-25")] += 1
for be, c in tail.items():
    print("==", be)
    for k, v in sorted(c.items()):
        print("  ", v, k)
