#!/usr/bin/env python3
"""Status of the stage-1 grid from its files (read-only): progress, errors, timing, memory, and
the version checks (backend, exact final-score ties, restore flags, required_tags admissions).
Usage: stage1_status.py ROOT"""
import json
import os
import sys
from collections import Counter

root = sys.argv[1]
log = [json.loads(ln) for ln in open(os.path.join(root, "logs", "cells.jsonl"))]
plan = json.load(open(os.path.join(root, "logs", "plan.json")))
done = [r for r in log if r.get("event") == "cell_done"]
errs = []
for r in done:
    bad = r["returncode"] != 0
    if not bad:
        try:
            bad = bool(json.load(open(r["out"])).get("error"))
        except Exception:
            bad = True
    if bad:
        errs.append(r["cell"])
walls = [r["wall_s"] for r in done]
refusals = sum(1 for r in log if r.get("event") == "flush_cache" and r.get("http_status") != 200)
nar = nem = bm25 = comp = ties = tie_recs = flags = rt = notret = 0
by_arm = Counter()
not_ok = Counter()
for r in done:
    if not os.path.exists(r["audit"]):
        continue
    for ln in open(r["audit"]):
        x = json.loads(ln)
        s = x.get("schema")
        if s == "bear.narrowing/1":
            nar += 1
            if x.get("status") != "ok":
                not_ok[f"{x.get('status')}:{x.get('reason') or ''}"] += 1
                continue
            nem += x.get("backend") == "remote" and "nemotron" in json.dumps(x.get("embedder") or {}).lower()
            bm25 += x.get("backend") == "bm25"
            st = x.get("settings") or {}
            flags += bool(st.get("restore_flat_backfill") or st.get("restore_below_threshold")
                          or "restore_flat_backfill" not in st)
            if not x.get("reused_from"):
                comp += 1
                c = Counter(p.get("final_score") for p in (x.get("offered") or []) + (x.get("ranked_out") or [])
                            if isinstance(p, dict) and p.get("rank") is not None)
                pairs = sum(n * (n - 1) // 2 for n in c.values() if n > 1)
                ties += pairs
                tie_recs += pairs > 0
                by_arm[r["arm"]] += pairs
            notret += sum(1 for p in (x.get("offered") or []) + (x.get("ranked_out") or [])
                          if isinstance(p, dict) and p.get("retrieved") is False)
        elif s == "bear.turn/1":
            rt += sum(1 for q in (x.get("retrievals") or []) for y in (q.get("results") or [])
                      if y.get("admitted_by") == "required_tags")
mem = None
for ln in open("/proc/meminfo"):
    if ln.startswith("MemAvailable:"):
        mem = round(int(ln.split()[1]) / 1048576, 1)
print(json.dumps({
    "done": len(done), "planned": len(plan["cells"]), "errors": len(errs), "error_cells": errs[:10],
    "mean_cell_s": round(sum(walls) / len(walls), 1) if walls else None,
    "eta_h": round((len(plan["cells"]) - len(done)) * (sum(walls) / len(walls) + 4) / 3600, 1) if walls else None,
    "flush_refusals": refusals, "mem_available_gb": mem,
    "narrowing_records": nar, "not_ok": dict(not_ok), "nemotron": nem, "bm25": bm25, "computed": comp,
    "exact_tie_pairs": ties, "records_with_ties": tie_recs, "tie_pairs_by_arm": dict(by_arm),
    "restore_flags_true_or_missing": flags, "admitted_by_required_tags": rt, "not_retrieved": notret,
    "last_event": {k: v for k, v in log[-1].items() if k != "fingerprint"},
}, indent=1, default=str))
