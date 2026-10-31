#!/usr/bin/env python3
"""Offline k sweep for WP7 stage 2's C-cut arm, from stage 1's narrowing records.

Usage: ksweep_stage2.py --root STAGE1_RUN --out OUT_DIR [--registry registry/harness_registry.stage1.json]

C-cut offers the top k admissible tools, ranked by similarity (priority weight 0), plus the
always-offered ``clarify``. Stage 1 recorded, for every computed narrowing, the full ranking of
the tools the gate admitted. This script asks, for each k, how many of the tools an agent needed
would still have been offered.

Backends:
- Nemotron: the recorded ranking (stage 1 ran on Nemotron). Under ``narrow_query:
  first_plus_message`` a cell's first turn ranks the same text as under ``message``, so first
  turns are exact. Later turns (after a scripted reply) would need new embeddings, so they are
  counted only under ``message``.
- BM25: replayed exactly with BEAR's own code (``tool_corpus``, a BM25 Retriever at priority
  weight 0, ``select`` with k null), on the recorded catalog, context and query. Each rebuilt
  catalog is checked against the record's ``catalog_digest``, and the offered set against the
  recorded one. Both query modes are replayed.

Needed tools:
- needed: per task, groups of tools of which any one will do, from each grader and task statement
  (NEEDED below), in operator cells of A, C-gate and D, where every tool is admitted. A group
  counts as covered when its best-ranked member is within k in the cell's first turn.
- called: every tool the agent called in a turn that the gate admitted (clarify, bridge and
  withheld tools aside), at its rank in that turn's ranking, any role.
A tool's admissible rank is its place among ranked tools, always-offered ones aside.

Writes OUT_DIR/ksweep.json and OUT_DIR/ksweep.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

from bear.config import Config, EmbeddingBackend
from bear.corpus import Corpus
from bear.models import Context
from bear.narrowing import ToolSpec, catalog_digest, select, tool_corpus
from bear.retriever import Retriever

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from needed_tools import NEEDED  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = ("tool_search", "tool_describe", "tool_call")
ALWAYS = ("clarify",)
ARMS_USED = ("A", "C-gate", "D")  # B's records rank the registry behind the bridge
KS = list(range(1, 41))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def admissible_order(entries):
    """Tool names in rank order, always-offered and mandatory ones aside."""
    ranked = sorted((e for e in entries if isinstance(e, dict) and e.get("rank") is not None),
                    key=lambda e: e["rank"])
    return [e["name"] for e in ranked if e["name"] not in ALWAYS and e.get("path") != "mandatory"]


class Bm25:
    """BM25 rankings replayed with BEAR's own narrowing code, cached per catalog."""

    def __init__(self, root, registry_path):
        with open(registry_path, encoding="utf-8") as f:
            self.desc = {t["name"]: t.get("description", "") for t in json.load(f)["tools"]}
        with open(os.path.join(HERE, "decoys", "sample.json"), encoding="utf-8") as f:
            for d in json.load(f)["decoys"]:
                self.desc[d["name"]] = d["description"]
        self.root = root
        self.policy = {}
        self.cache = {}
        self.digest_mismatch = 0
        self.offered_mismatch = 0
        defaults = Config()
        self.config = Config(embedding_backend=EmbeddingBackend.BM25,
                             mandatory_tags=list(dict.fromkeys([*defaults.mandatory_tags, "must-have"])),
                             default_top_k=10, default_threshold=0.3, priority_weight=0.0)

    def rank(self, rec, decoys, query):
        names = rec.get("tools_before") or []
        catalog = [ToolSpec(n, self.desc.get(n, "")) for n in names]
        if catalog_digest(catalog) != rec.get("catalog_digest"):
            self.digest_mismatch += 1
            return None
        if decoys not in self.policy:
            self.policy[decoys] = list(Corpus.from_directory(os.path.join(self.root, "corpus", f"d{decoys}")))
        policy = self.policy[decoys]
        key = (rec["catalog_digest"], decoys)
        if key not in self.cache:
            insts = tool_corpus(catalog, policy, unlisted="block", bridge=BRIDGE)
            r = Retriever(Corpus.from_dicts([i.model_dump(mode="json") for i in insts]),
                          config=self.config, label="hermes-tools")
            r.build_index()
            self.cache[key] = r
        ctx = Context.model_validate(rec["context"])
        sel = select(catalog, ctx, query, policy, self.cache[key], k=None, threshold=0.0,
                     always_offer=ALWAYS, bridge=BRIDGE, unlisted="block")
        if {p.name for p in sel.offered} != {e["name"] for e in rec.get("offered") or []}:
            self.offered_mismatch += 1
        return admissible_order([p.to_dict() for p in [*sel.offered, *sel.ranked_out]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--registry", default=os.path.join(HERE, "registry", "harness_registry.stage1.json"))
    a = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(a.root))
    os.makedirs(a.out, exist_ok=True)
    bm25 = Bm25(root, a.registry)
    done = [r for r in load_jsonl(os.path.join(root, "logs", "cells.jsonl"))
            if r.get("event") == "cell_done" and r["returncode"] == 0 and r["arm"] in ARMS_USED]
    # samples[(backend, query)] -> lists of (decoys, role, rank or None) per kind
    req = defaultdict(list)
    called = defaultdict(list)
    cells_all = defaultdict(list)  # per cell: max needed rank over all turns (called tools)
    for d in done:
        recs = load_jsonl(d["audit"])
        sess = next((r.get("session_id") for r in recs if r.get("session_id")), None)
        recs = [r for r in recs if r.get("session_id") in (sess, None)]
        nar = [r for r in recs if r.get("schema") == "bear.narrowing/1"]
        comp = [r for r in nar if r.get("status") == "ok" and not r.get("reused_from")]
        if not comp:
            continue
        to_comp = {r["narrowing_id"]: (r.get("reused_from") or r["narrowing_id"]) for r in nar}
        by_id = {r["narrowing_id"]: r for r in comp}
        tools_in_turn = defaultdict(set)
        for x in recs:
            if x.get("schema") == "bear.decision/1" and x.get("narrowing_id") in to_comp:
                tools_in_turn[to_comp[x["narrowing_id"]]].add(x.get("tool"))
        dz, role, task = d["switches"]["decoys"], d["switches"]["role"], d["task"]
        first_q = comp[0].get("query") or ""
        orders = {}
        for i, r in enumerate(comp):
            q = r.get("query") or ""
            fpm = q if (i == 0 or q == first_q) else f"{first_q}\n{q}"
            orders[("nemotron", "message", r["narrowing_id"])] = admissible_order(
                [*(r.get("offered") or []), *(r.get("ranked_out") or [])])
            orders[("nemotron", "first_plus_message", r["narrowing_id"])] = (
                orders[("nemotron", "message", r["narrowing_id"])] if fpm == q else None)
            orders[("bm25", "message", r["narrowing_id"])] = bm25.rank(r, dz, q)
            orders[("bm25", "first_plus_message", r["narrowing_id"])] = (
                orders[("bm25", "message", r["narrowing_id"])] if fpm == q else bm25.rank(r, dz, fpm))
        for backend, query in (("nemotron", "message"), ("nemotron", "first_plus_message"),
                               ("bm25", "message"), ("bm25", "first_plus_message")):
            key = (backend, query)
            first = orders[(backend, query, comp[0]["narrowing_id"])]
            if role == "operator" and task in NEEDED and first is not None:
                catalog = set(comp[0].get("tools_before") or [])
                for group in NEEDED[task]:
                    if not any(t in catalog for t in group):
                        continue  # a tool this run did not expose (needed_tools.py)
                    ranks = [first.index(t) + 1 for t in group if t in first]
                    req[key].append((dz, min(ranks) if ranks else None))
            worst, complete = 0, True
            for nid, tools in tools_in_turn.items():
                order = orders.get((backend, query, nid))
                if order is None:
                    complete = False
                    continue
                for t in tools:
                    if t in ALWAYS or t in BRIDGE or t not in order:
                        continue  # always offered, a bridge call, or withheld by the gate
                    rank = order.index(t) + 1
                    called[key].append((dz, role, rank))
                    worst = max(worst, rank)
            if complete:
                cells_all[key].append((dz, role, worst))

    def cov(samples, k):
        return sum(1 for s in samples if s is not None and s <= k) / len(samples) if samples else None

    out = {"stage1_root": root, "arms": ARMS_USED, "bm25_digest_mismatches": bm25.digest_mismatch,
           "bm25_offered_set_mismatches": bm25.offered_mismatch, "curves": {}, "choice": {}}
    lines = ["# C-cut k sweep (offline, stage-1 records)", "",
             f"BM25 replays: catalog digest mismatches {bm25.digest_mismatch}, offered-set mismatches "
             f"{bm25.offered_mismatch}.", ""]
    for key in sorted(set(req) | set(called)):
        backend, query = key
        rq = [r for _dz, r in req[key]]
        cl = [r for _dz, _role, r in called[key]]
        cells = [w for _dz, _role, w in cells_all[key]]
        curve = {k: {"required": cov(rq, k), "called": cov(cl, k), "cells_all_called": cov(cells, k)}
                 for k in KS}
        by_dz = {dz: {k: {"required": cov([r for d0, r in req[key] if d0 == dz], k),
                          "called": cov([r for d0, _ro, r in called[key] if d0 == dz], k)}
                      for k in (5, 8, 10, 12, 15, 20, 25, 30)} for dz in (0, 100, 300)}
        k99 = next((k for k in KS if (curve[k]["required"] or 0) >= 0.99 and (curve[k]["called"] or 0) >= 0.95), None)
        k95 = next((k for k in KS if (curve[k]["required"] or 0) >= 0.95 and (curve[k]["called"] or 0) >= 0.95), None)
        kall = next((k for k in KS if (curve[k]["required"] or 0) >= 1.0 and (curve[k]["called"] or 0) >= 0.99), None)
        out["curves"][f"{backend}/{query}"] = {"n_required": len(rq), "n_called": len(cl), "n_cells": len(cells),
                                              "curve": curve, "by_decoys": by_dz}
        out["choice"][f"{backend}/{query}"] = {"k_req99_called95": k99, "k_req95_called95": k95,
                                               "k_req100_called99": kall}
        lines += [f"## {backend}, narrow_query {query}", "",
                  f"Needed-tool groups {len(rq)} (operator cells, first turn), called samples {len(cl)}, cells {len(cells)}.",
                  f"Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **{k99}**. With required >= 0.95: {k95}. "
                  f"With required 1.0 and called >= 0.99: {kall}.", "",
                  "| k | Needed groups covered | Called tools covered | Cells with every called tool |", "| --- | --- | --- | --- |"]
        for k in (3, 5, 8, 10, 12, 15, 20, 25, 30, 35):
            c = curve[k]
            lines.append(f"| {k} | {c['required']:.3f} | {c['called']:.3f} | {c['cells_all_called']:.3f} |")
        lines += ["", "| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |", "| --- | --- | --- | --- | --- | --- |"]
        for dz in (0, 100, 300):
            row = by_dz[dz]
            cellv = [f"{row[k]['required'] if row[k]['required'] is not None else float('nan'):.3f} / "
                     f"{row[k]['called'] if row[k]['called'] is not None else float('nan'):.3f}" for k in (8, 10, 12, 15, 20)]
            lines.append(f"| {dz} | " + " | ".join(cellv) + " |")
        lines.append("")
    with open(os.path.join(a.out, "ksweep.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    with open(os.path.join(a.out, "ksweep.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "curves"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
