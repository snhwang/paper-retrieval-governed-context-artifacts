#!/usr/bin/env python3
"""Offline cost of the gate-with-reason annotation, per request, from stage 1's narrowing records.

Usage: annotation_cost_stage2.py --root STAGE1_RUN --out OUT_DIR

The annotation BEAR appends to the last user message depends only on the selection: which
tools were offered and why, and which were withheld and why. C-gate and D offer every admitted
tool (k null), so a stage-1 C-gate or D record holds exactly the selection a stage-2 cell with
annotations on would get. This script rebuilds each first-turn selection and renders it with
BEAR's own ``annotate`` at every level, counting tokens with BEAR's ``text_tokens`` (4 characters
a token, the same estimate the plugin records as ``annotation_tokens``).

Writes OUT_DIR/annotation_cost.json and OUT_DIR/annotation_cost.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from statistics import mean

from bear.narrowing import Placed, Selection, Withheld, annotate, text_tokens

LEVELS = (("none", "none", None), ("counts", "counts", None), ("names10", "names", 10),
          ("names", "names", None))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def placed(d):
    return Placed(d["name"], d["path"], d.get("rank"), d.get("rule_id", ""), d.get("similarity"),
                  d.get("final_score"), bool(d.get("mandatory")), bool(d.get("gated")),
                  tuple(d.get("required_tags") or ()), bool(d.get("retrieved", True)),
                  bool(d.get("below_threshold")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(a.root))
    os.makedirs(a.out, exist_ok=True)
    tokens = defaultdict(list)  # (role, decoys, level) -> tokens per request
    for d in load_jsonl(os.path.join(root, "logs", "cells.jsonl")):
        if d.get("event") != "cell_done" or d["returncode"] != 0 or d["arm"] not in ("C-gate", "D"):
            continue
        recs = load_jsonl(d["audit"])
        sess = next((r.get("session_id") for r in recs if r.get("session_id")), None)
        first = next((r for r in recs if r.get("schema") == "bear.narrowing/1"
                      and r.get("session_id") == sess and r.get("status") == "ok"
                      and not r.get("reused_from")), None)
        if first is None:
            continue
        sel = Selection(offered=[placed(p) for p in first.get("offered") or []],
                        withheld=[Withheld(w["name"], w["reason"], tuple(w.get("rule_ids") or ()),
                                           tuple(w.get("missing_tags") or ())) for w in first.get("withheld") or []],
                        ranked_out=[placed(p) for p in first.get("ranked_out") or []],
                        admissible=int(first.get("admissible") or 0), k=None,
                        threshold=float(first.get("threshold") or 0.0),
                        always_offer=tuple((first.get("settings") or {}).get("always_offer") or ()),
                        bridge=tuple((first.get("settings") or {}).get("bridge") or ()))
        key = (d["switches"]["role"], d["switches"]["decoys"])
        for level, disclosure, cap in LEVELS:
            tokens[key + (level,)].append(text_tokens(annotate(sel, disclosure, cap)))
    out = {f"{role}/d{dz}/{lvl}": {"n": len(v), "mean": round(mean(v), 1), "min": min(v), "max": max(v)}
           for (role, dz, lvl), v in sorted(tokens.items())}
    with open(os.path.join(a.out, "annotation_cost.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    lines = ["# Annotation cost per request (offline, stage-1 C-gate and D selections)", "",
             "Tokens BEAR's annotation adds to each request at session scope, by level. 4 characters "
             "a token (BEAR's `text_tokens`). Annotations off add 0.", "",
             "| Role | Decoys | none | counts | names10 | names |", "| --- | --- | --- | --- | --- | --- |"]
    for role in ("operator", "guest"):
        for dz in (0, 100, 300):
            vals = [out.get(f"{role}/d{dz}/{lvl}", {}).get("mean") for lvl, _d, _c in LEVELS]
            lines.append(f"| {role} | {dz} | " + " | ".join(f"{v:.0f}" if v is not None else "n/a" for v in vals) + " |")
    with open(os.path.join(a.out, "annotation_cost.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
