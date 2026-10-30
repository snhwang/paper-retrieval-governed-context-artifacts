"""Audit of the published results for BEAR 0.1.10's silent hash fallback.

0.1.10 falls back to hash embeddings when a dense model fails to load, and
logs only a warning. Its hash embedding uses the first 32 dimensions of a
SHA-256 per character trigram and applies no prefix in hash mode, so a
fallback gives exactly what the hash backend gives, whatever the dense model.
That makes an exact test possible: a dense cell that equals the hash cell of
the same condition (value and CI, or the per-query array) is a fallback.

Hash comparators:
  - the hash cell the published file itself holds, where it has one
    (Tables 3, 5, 6, Table 7 governed, the Pet Sim backend and governance
    tables, tab:retrieval, tab:token-compare)
  - otherwise a rerun of the same script on public v0.1.10 with every model
    load refused (stage v0110F, lane fallback0110), which takes the very
    fallback; also used as a second comparator where the file has a hash cell
  - for Table 7's ungated rows, the regenerated 0.1.10 hash list

Then it scans every published log for load failures, fallback warnings and
runs that stop early, and checks this run's own 0.1.10 controls the same way.

    python fallback_audit.py --pub <repo> --stage <root>/stage --lists <dir> ... --out DIR
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_042 as cmp  # noqa: E402

DENSE = ["BGE", "BGE-M3", "Qwen3-0.6B", "Qwen3-4B"]
FINDINGS: list[dict] = []
PUBLISHED: list[str] = []
FILES: dict[str, dict] = {}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def eq(a, b, tol=1e-12):
    if a is None or b is None:
        return False
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.all(np.abs(a - b) <= tol))


def trivial(a):
    a = np.asarray(a, float)
    return a.size == 0 or bool(np.all(a == a.flat[0]))


def note(file, table, cell, kind, dense, hashv, comparator, replaced=None, extra=None):
    FINDINGS.append({"file": file, "table": table, "cell": cell, "match": kind, "dense": dense,
                     "hash": hashv, "comparator": comparator, "replaced_by_042": replaced, **(extra or {})})


def checked(file, n, table, comparator):
    f = FILES.setdefault(file, {"table": table, "cells_checked": 0, "comparators": set()})
    f["cells_checked"] += n
    f["comparators"].add(comparator)


def stage_file(stage: Path, ver: str, step: str, name: str):
    hits = sorted(p for p in (stage / ver / step).glob(f"**/{name}") if not p.name.endswith(".provenance.json"))
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# Tables 3, 5, 6 (and the older eval_toolbench files)
# ---------------------------------------------------------------------------

def tables_356(pub: Path, stage: Path):
    files = {"results/toolbench_eval_v0110.json": "Table 3",
             "results/toolbench_eval_metatool_v0110.json": "Tables 5, 6",
             "results/toolbench_eval_qtags_top5_v0110.json": "Table 6 +QueryTags",
             "results/toolbench_eval_qtags_top5_v0110_regen.json": "Table 6 +QueryTags (regen)",
             "evals/results/toolbench_eval.json": "older ToolBench run",
             "evals/results/metatool_full_eval.json": "older MetaTool run"}
    for rel, table in files.items():
        p = pub / rel
        if not p.exists():
            continue
        d = jl(p)
        n = 0
        for bench, exps in d.items():
            if bench.startswith("_") or not isinstance(exps, dict):
                continue
            for lab in DENSE:
                for kind, hname in ((f"BEAR+{lab} (gov)", "BEAR+Hash (gov)"),
                                    (f"BEAR+{lab} (mand-only)", "BEAR+Hash (mand-only)"),
                                    (f"{lab} (no gov)", "Hash (no gov)")):
                    e, h = exps.get(kind), exps.get(hname)
                    if not isinstance(e, dict) or "metrics" not in e:
                        continue
                    if not isinstance(h, dict):
                        continue
                    for m, arr in e["metrics"].items():
                        harr = h.get("metrics", {}).get(m)
                        if harr is None:
                            continue
                        n += 1
                        ci_e = e.get("cis", {}).get(m, {})
                        ci_h = h.get("cis", {}).get(m, {})
                        same_ci = bool(ci_e) and all(abs(ci_e.get(k, 0) - ci_h.get(k, 1)) < 1e-12
                                                     for k in ("point_estimate", "ci_lower", "ci_upper"))
                        if eq(arr, harr):
                            if trivial(arr):
                                note(rel, table, f"{bench} / {kind} / {m}", "per-query array equal but constant "
                                     f"(all {float(np.asarray(arr).flat[0]):.3g}): uninformative", float(np.mean(arr)),
                                     float(np.mean(harr)), hname)
                            else:
                                note(rel, table, f"{bench} / {kind} / {m}", "per-query array equal to hash",
                                     float(np.mean(arr)), float(np.mean(harr)), hname)
                        elif same_ci:
                            note(rel, table, f"{bench} / {kind} / {m}", "value and CI equal to hash",
                                 ci_e.get("point_estimate"), ci_h.get("point_estimate"), hname)
        checked(rel, n, table, "the file's own hash rows (same benchmark and condition)")


# ---------------------------------------------------------------------------
# Table 4 (BGE only): v0110F reruns
# ---------------------------------------------------------------------------

def table4(pub: Path, stage: Path):
    for fname, step in (("toolbench_inferred_metrics.json", "fb_t4_inferred"),
                        ("toolbench_multitag_metrics.json", "fb_t4_multitag"),
                        ("toolbench_top5_metrics.json", "fb_t4_top5")):
        rel = f"results/{fname}"
        P = jl(pub / rel)
        fb = stage_file(stage, "v0110F", step, fname)
        if fb is None:
            FILES.setdefault(rel, {"table": "Table 4", "cells_checked": 0, "comparators": set()})["pending"] = step
            continue
        F = jl(fb)
        n = 0
        for row in P["rows"]:
            fr = next((r for r in F["rows"] if r["condition"] == row["condition"]), None)
            for m in ("recall", "ndcg", "f1"):
                o, h = row.get(m), (fr or {}).get(m)
                if not o or not h:
                    continue
                n += 1
                if all(abs(o[k] - h[k]) < 1e-12 for k in ("mean", "ci_lo", "ci_hi")):
                    note(rel, "Table 4", f"{row['condition']} / {m}", "value and CI equal to the fallback run",
                         o["mean"], h["mean"], f"v0110F {step}")
        checked(rel, n, "Table 4", "0.1.10 with model loads refused (fallback), same script")


# ---------------------------------------------------------------------------
# Table 7 (retrieval arrays of the e2e run)
# ---------------------------------------------------------------------------

def table7(pub: Path, lists: list[Path]):
    rel = "evals/results/toolbench_e2e_scores.json"
    S = {s["condition"]: s for s in jl(pub / rel)["scores"]}
    hash_gov = S.get("BEAR+Hash (gov)")
    hash_ung = None
    for d in lists:
        p = d / "lists_v0110" / "e2e" / "hash_no_gov.json"
        if p.exists():
            hash_ung = jl(p)
            break
    n = 0
    for lab in DENSE:
        for cond, h, hn in ((f"BEAR+{lab} (gov)", hash_gov, "BEAR+Hash (gov), published"),
                            (f"{lab} (no gov)", hash_ung, "Hash (no gov), regenerated on 0.1.10")):
            s = S.get(cond)
            if not s or not h:
                continue
            for m in ("_recall_scores", "_precision_scores", "_f1_scores", "_ndcg_scores"):
                if m not in s or m not in h:
                    continue
                n += 1
                if eq(s[m], h[m]) and not trivial(s[m]):
                    note(rel, "Table 7", f"{cond} / {m.strip('_')}", "per-query array equal to hash",
                         float(np.mean(s[m])), float(np.mean(h[m])), hn)
    checked(rel, n, "Table 7", "BEAR+Hash (gov) in the file; regenerated 0.1.10 Hash (no gov) list")


def tables_89(pub: Path):
    """The LLM rows store no retrieval arrays. Exact accuracy needs the gold
    tool among the 5 candidates, and with hash retrieval it is there for
    about 15% to 21% of queries, so rows far above that cannot be hash."""
    e2e = {s["condition"]: s for s in jl(pub / "evals/results/toolbench_e2e_scores.json")["scores"]}
    hx = float(np.mean(e2e["BEAR+Hash (gov)"]["_exact_scores"])) if "BEAR+Hash (gov)" in e2e else None
    # Exact accuracy needs at least one gold API among the 5 candidates, so
    # the share of queries with recall@5 > 0 bounds it.
    hr = float(np.mean(np.asarray(e2e["BEAR+Hash (gov)"]["_recall_scores"]) > 0)) if "BEAR+Hash (gov)" in e2e else None
    react = sorted(r for r in PUBLISHED if r.startswith("results/toolbench_react_metrics") and r.endswith(".json"))
    for rel in react:
        table = "Table 8" if rel.endswith("toolbench_react_metrics.json") else "Table 9 sources (Gemma 4)"
        if "cap128_superseded" in rel:
            table = "superseded (cap 128)"
        d = jl(pub / rel)
        pq = d.get("per_query_correct", {})
        rows = {}
        for k, arr in pq.items():
            if k.startswith("mono"):
                continue
            rows[k] = float(np.mean(arr))
        for r in d.get("rows", []):
            if "mono" not in str(r.get("condition", "")).lower():
                rows.setdefault(str(r.get("condition")), r.get("tool_acc"))
        for k, arr in pq.items():
            if k.startswith("mono"):
                continue
            if hx is not None and eq(arr, e2e["BEAR+Hash (gov)"]["_exact_scores"]):
                note(rel, table, k, "per-query correctness equal to the hash e2e row", rows[k], hx,
                     "Table 7 BEAR+Hash (gov)")
        FILES[rel] = {"table": table, "cells_checked": len(rows),
                      "comparators": {f"bound: hash retrieval puts at least one gold API in the prompt for "
                                      f"{hr:.3f} of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under "
                                      f"hash retrieval is at most {hr:.3f}; measured {hx:.3f} with Mistral-Nemo"},
                      "bear_rows_accuracy": rows}
        for k, acc in rows.items():
            if acc is not None and hr is not None and acc <= hr:
                note(rel, table, k, f"accuracy {acc:.3f} within the hash-retrieval bound {hr:.3f}", acc, hx,
                     "bound from Table 7 BEAR+Hash (gov)")


# ---------------------------------------------------------------------------
# Pet Sim
# ---------------------------------------------------------------------------

PET_SHORT = {"BGE-base": "bge", "BGE-M3": "bge-m3", "Qwen3-0.6B": "qwen3", "Qwen3-4B": "qwen3-4b",
             "ITR-hybrid": "itr", "ITR-standalone": "itr-standalone"}
# The ITR library has its own silent fallback: when its encoder fails to load
# it logs "Using fallback embeddings" and embeds with SHA-256 bytes. That is
# deterministic too, so the v0110F runs (models refused) give its fallback.


def backend_comparison(pub: Path, stage: Path):
    rel = "results/backend_comparison.json"
    P = {r["short"]: r for r in jl(pub / rel)}
    fbp = stage_file(stage, "v0110F", "fb_backends", "backend_comparison_fb.json")
    FB = {r["short"]: r for r in jl(fbp)} if fbp else {}
    H = P.get("Hash")
    n = 0
    for short in PET_SHORT:
        r = P.get(short)
        if not r:
            continue
        for k in ("strict_f1", "relaxed_f1", "para_f1", "notag_f1", "complex_f1"):
            if k not in r:
                continue
            for comp, src in (("Hash row", H), (f"fallback run ({short})", FB.get(short))):
                if not src or k not in src:
                    continue
                n += 1
                same = abs(r[k] - src[k]) < 1e-12 and eq(r.get(k + "_ci"), src.get(k + "_ci"))
                if same:
                    note(rel, "tab:governance-ablation (a)", f"{short} / {k}", "value and CI equal to hash",
                         r[k], src[k], comp)
    checked(rel, n, "tab:governance-ablation (a)", "the Hash row; the 0.1.10 fallback run of each backend")


def governance_ablation(pub: Path, stage: Path):
    rel = "results/governance_ablation.json"
    P = jl(pub / rel)
    fbp = stage_file(stage, "v0110F", "fb_gov_ablation", "governance_ablation_fb.json")
    FB = jl(fbp) if fbp else {}
    fbi = stage_file(stage, "v0110F", "fb_gov_ablation_itr", "governance_ablation_fb_itr.json")
    FBI = jl(fbi) if fbi else {}
    n = 0
    for panel in ("Full governance", "Mandatory only", "No governance"):
        for qs, backs in P.get(panel, {}).items():
            h = backs.get("Hash")
            for b in ("BGE-base", "BGE-M3", "Qwen3-0.6B", "Qwen3-4B", "ITR"):
                x = backs.get(b)
                if not isinstance(x, dict):
                    continue
                fbsrc = (FBI if b == "ITR" else FB).get(panel, {}).get(qs, {}).get(b)
                for comp, src in (("Hash cell", h), ("fallback run", fbsrc)):
                    if not isinstance(src, dict):
                        continue
                    n += 1
                    if abs(x["f1"] - src["f1"]) < 1e-12 and eq(x["ci"], src["ci"]):
                        note(rel, "tab:governance-ablation", f"{panel} / {qs} / {b}", "value and CI equal to hash",
                             x["f1"], src["f1"], comp)
    te = P.get("token_efficiency", {})
    h = te.get("BEAR + Hash", {}).get("tokens")
    for b in ("BEAR + BGE-base", "BEAR + BGE-M3", "BEAR + Qwen3-0.6B", "BEAR + Qwen3-4B", "ITR"):
        x = te.get(b, {}).get("tokens")
        if x is None or h is None:
            continue
        n += 1
        fbx = (FBI if b == "ITR" else FB).get("token_efficiency", {}).get(b, {}).get("tokens")
        if abs(x - h) < 1e-9 or (fbx is not None and abs(x - fbx) < 1e-9):
            note(rel, "tab:token-compare", b, "tokens equal to hash", x, h if abs(x - h) < 1e-9 else fbx,
                 "BEAR + Hash" if abs(x - h) < 1e-9 else "fallback run")
    checked(rel, n, "tab:governance-ablation, tab:token-compare", "the Hash cells; the 0.1.10 fallback run")


def retrieval_tab(pub: Path, stage: Path):
    rel = "results/eval_retrieval_semantic_output.txt"
    S = cmp.parse_retrieval((pub / rel).read_text(errors="replace"))
    Hh = cmp.parse_retrieval((pub / "results/eval_retrieval_output.txt").read_text(errors="replace"))
    fbl = stage / "v0110F" / "fb_retrieval_semantic" / "fb_retrieval_semantic.log"
    FB = cmp.parse_retrieval(cmp.last_attempt(fbl.read_text(errors="replace"))) if fbl.exists() else {}
    n = 0
    for key, cells in S.items():
        for m in ("F1", "R"):
            for comp, src in (("eval_retrieval_output.txt (hash)", Hh), ("fallback run", FB)):
                h = (src.get(key) or {}).get(m)
                if not h:
                    continue
                n += 1
                c = cells[m]
                if all(abs(c[k] - h[k]) < 1e-9 for k in ("pt", "lo", "hi")):
                    note(rel, "tab:retrieval", f"{key[0]} {key[1]} {m}", "value and CI equal to hash",
                         c["pt"], h["pt"], comp)
    checked(rel, n, "tab:retrieval (BGE half)", "eval_retrieval_output.txt (hash); the 0.1.10 fallback run")


def per_backend(pub: Path, stage: Path, prefix: str, step: str, table: str, key: str):
    for b in ("bge", "bge-m3", "qwen3", "qwen3-4b"):
        rel = f"results/{prefix}_{b}.json"
        if not (pub / rel).exists():
            continue
        P = jl(pub / rel)
        fb = stage_file(stage, "v0110F", step, f"{prefix}_{b}.json")
        if fb is None:
            FILES.setdefault(rel, {"table": table, "cells_checked": 0, "comparators": set()})["pending"] = step
            continue
        F = jl(fb)
        n = 0
        for row in P["rows"]:
            fr = next((r for r in F["rows"] if (abs(r[key] - row[key]) < 1e-9 if isinstance(row[key], float)
                                                else r[key] == row[key])), None)
            if not fr:
                continue
            n += 1
            if all(abs(row[k] - fr[k]) < 1e-12 for k in ("mean_f1", "ci_lo", "ci_hi")):
                note(rel, table, f"{key}={row[key]}", "value and CI equal to the fallback run",
                     row["mean_f1"], fr["mean_f1"], f"v0110F {step}")
        checked(rel, n, table, "0.1.10 with model loads refused (fallback), same script and backend")


def aggregates(pub: Path, stage: Path):
    """alpha_sweep_all.json and governance_decomposed(_all).json repeat the
    per-backend files; check that they agree with them."""
    for rel, table in (("results/alpha_sweep_all.json", "tab:alpha-sweep"),
                       ("results/governance_decomposed_all.json", "tab:decomposed-ablation"),
                       ("results/governance_decomposed.json", "tab:decomposed-ablation")):
        p = pub / rel
        if not p.exists():
            continue
        d = jl(p)
        items = d.items() if isinstance(d, dict) and "rows" not in d else [(d.get("backend"), d)]
        n = 0
        for b, sub in items:
            if not isinstance(sub, dict) or "rows" not in sub:
                continue
            src = pub / f"results/{'alpha_sweep' if 'alpha' in rel else 'governance_decomposed'}_{b}.json"
            if not src.exists():
                continue
            S = jl(src)
            n += 1
            if [round(r["mean_f1"], 12) for r in sub["rows"]] != [round(r["mean_f1"], 12) for r in S["rows"]]:
                note(rel, table, b, "aggregate disagrees with the per-backend file", None, None, str(src.name))
        checked(rel, n, table, "the per-backend files (consistency only)")


# ---------------------------------------------------------------------------
# Customer support, tool scaling, transfer, reranker, LlamaIndex
# ---------------------------------------------------------------------------

def cs(pub: Path, stage: Path):
    def rows(p, key="num_agents"):
        with open(p, newline="") as f:
            return {int(r[key]): r for r in csv.DictReader(f)}
    for rel, step, fname, table in (
            ("results/baseline_comparison_results.csv", "fb_baseline_comparison", "baseline_comparison_results.csv",
             "tab:token-efficiency, tab:semantic-advantage, novel departments"),
            ("results/scalability_results.csv", "fb_scalability", "scalability_results.csv", "scalability (text)")):
        fb = stage_file(stage, "v0110F", step, fname)
        if fb is None:
            FILES.setdefault(rel, {"table": table, "cells_checked": 0, "comparators": set()})["pending"] = step
            continue
        P, F = rows(pub / rel), rows(fb)
        n, same_rows = 0, 0
        for k, r in P.items():
            fr = F.get(k)
            if not fr:
                continue
            cols = [c for c in r if c.startswith("bear") or c in ("persona_recall", "dept_recall", "safety_recall",
                                                                   "global_recall", "scope_violations", "bear_tokens",
                                                                   "token_ratio")]
            cols = [c for c in cols if "latency" not in c and "_ms" not in c]
            n += len(cols)
            eqc = [c for c in cols if fr.get(c) == r.get(c)]
            if len(eqc) == len(cols):
                same_rows += 1
                note(rel, table, f"N={k}", "every BEAR column equal to the fallback run", None, None, f"v0110F {step}",
                     extra={"columns": cols})
        checked(rel, n, table, "0.1.10 with model loads refused (fallback), same script")


def tool_scaling(pub: Path, stage: Path):
    rel = "results/eval_tool_scaling_output.txt"
    P = cmp.parse_scaling((pub / rel).read_text(errors="replace"))
    fbl = stage / "v0110F" / "fb_tool_scaling" / "fb_tool_scaling.log"
    if not fbl.exists():
        FILES.setdefault(rel, {"table": "tab:tool-scaling", "cells_checked": 0, "comparators": set()})["pending"] = \
            "fb_tool_scaling"
        return
    F = cmp.parse_scaling(cmp.last_attempt(fbl.read_text(errors="replace")))
    same = [k for k in P if k in F and abs(P[k] - F[k]) < 1e-9]
    FILES[rel] = {"table": "tab:tool-scaling, tab:token-savings", "cells_checked": len(P),
                  "comparators": {"0.1.10 with model loads refused (fallback), same script"},
                  "cells_equal_to_fallback": len(same), "cells_total": len(P)}
    if len(same) == len(P):
        note(rel, "tab:tool-scaling", "all cells", "every cell equal to the fallback run", None, None, "v0110F")


def transfer(pub: Path, stage: Path):
    for corpus in ("toolbench", "metatool"):
        fname = f"backend_transfer_{corpus}_toolbench_ir_bert_based_uncased.json"
        rel = f"results/{fname}"
        fb = stage_file(stage, "v0110F", f"fb_transfer_{corpus}", fname)
        if fb is None:
            FILES.setdefault(rel, {"table": "tab:transfer", "cells_checked": 0, "comparators": set()})["pending"] = 1
            continue
        P, F = jl(pub / rel), jl(fb)
        n = 0
        for m, x in P["metrics"].items():
            y = F["metrics"].get(m)
            if not y:
                continue
            n += 1
            if abs(x["mean"] - y["mean"]) < 1e-12 and eq(x["ci"], y["ci"]):
                note(rel, "tab:transfer", f"ToolBench-IR / {m}", "value and CI equal to the fallback run",
                     x["mean"], y["mean"], "v0110F")
        checked(rel, n, "tab:transfer", "0.1.10 with model loads refused (fallback), same script")
    rel = "results/toolbench_toolllm_fixed.json"
    fb = stage_file(stage, "v0110F", "fb_toolllm", "toolbench_toolllm_fixed.json")
    if fb is None:
        FILES.setdefault(rel, {"table": "ToolBench-IR + governance (text)", "cells_checked": 0,
                               "comparators": set()})["pending"] = 1
        return
    P, F = jl(pub / rel), jl(fb)
    n = 0
    for c in P["conditions"]:
        fc = next((x for x in F["conditions"] if x["label"] == c["label"]), None)
        for m, x in c["metrics"].items():
            y = (fc or {}).get("metrics", {}).get(m)
            if not y:
                continue
            n += 1
            if abs(x["mean"] - y["mean"]) < 1e-12 and eq(x["ci"], y["ci"]):
                note(rel, "ToolBench-IR + governance (text)", f"{c['label']} / {m}",
                     "value and CI equal to the fallback run", x["mean"], y["mean"], "v0110F")
    checked(rel, n, "ToolBench-IR + governance (text)", "0.1.10 with model loads refused (fallback), same script")


def reranker(pub: Path, lists: list[Path]):
    """BEAR's first stage in the reranker and LlamaIndex files. ToolBench: the
    per-query arrays against Table 3's hash rows. Pet Sim: the F1 against the
    hash cells of the same condition."""
    T3 = jl(pub / "results/toolbench_eval_v0110.json")["ToolBench"]
    hmap = {"bi": "Hash (no gov)", "bear": "BEAR+Hash (gov)", "bear_nogov": "Hash (no gov)",
            "bear_gov": "BEAR+Hash (gov)"}
    bmap = {"bi": "BGE (no gov)", "bear": "BEAR+BGE (gov)", "bear_nogov": "BGE (no gov)", "bear_gov": "BEAR+BGE (gov)"}
    for rel in ("results/reranker_composition_toolbench.json", "results/framework_baseline_toolbench.json"):
        d = jl(pub / rel)
        n = 0
        info = {}
        for arm, hname in hmap.items():
            pq = d.get("per_query", {}).get(arm)
            if not pq or "recall" not in pq:
                continue
            n += 1
            h = T3[hname]["metrics"]["recall"]
            info[arm] = {"equals_table3_dense": eq(pq["recall"], T3[bmap[arm]]["metrics"]["recall"]),
                         "equals_table3_hash": eq(pq["recall"], h)}
            if info[arm]["equals_table3_hash"]:
                note(rel, "tab:reranker", f"{arm} recall per query", "per-query array equal to hash",
                     float(np.mean(pq["recall"])), float(np.mean(h)), f"Table 3 {hname}")
        checked(rel, n, "tab:reranker", "Table 3 hash per-query arrays (same first stage on ToolBench)")
        FILES[rel]["first_stage_vs_table3"] = info
    BC = {r["short"]: r for r in jl(pub / "results/backend_comparison.json")}
    for rel in ("results/reranker_composition_petsim.json", "results/framework_baseline_petsim.json"):
        d = jl(pub / rel)
        n = 0
        for arm in ("bear", "bear_gov"):
            a = d.get("arms", {}).get(arm)
            if not a:
                continue
            for m, hk in (("strict_f1", "strict_f1"), ("relaxed_f1", "relaxed_f1"), ("f1", "strict_f1")):
                x = a.get("metrics", {}).get(m)
                if not x:
                    continue
                n += 1
                if abs(x["mean"] - BC["Hash"][hk]) < 1e-9:
                    note(rel, "tab:reranker", f"{arm} {m}", "value equal to hash", x["mean"], BC["Hash"][hk],
                         "backend_comparison Hash")
        checked(rel, n, "tab:reranker", "backend_comparison.json Hash (Full governance, k=10)")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

LOAD_FAIL = re.compile(r"Falling back to hash|Could not load model|No ML embedding framework available|"
                       r"Using hash-based embeddings|sentence-transformers not installed|"
                       r"CUDA out of memory|OutOfMemoryError|Killed|Traceback \(most recent call last\)")
HASH_SEL = re.compile(r"Hash embeddings selected")
SECTION = re.compile(r"^(={3,}.*={3,}|\s*-{3}\s.*-{3}|.*\bbackend\s*=\s*[\w.-]+.*)$")
PROGRESS = re.compile(r"\[(\d+)/(\d+)\]")


def scan_log(path: Path, rel: str) -> dict:
    text = path.read_text(errors="replace").replace("\r", "\n")
    lines = text.splitlines()
    out = {"lines": len(lines), "load_failures": [], "hash_selected": 0, "early_stops": []}
    section = ""
    prog: dict[tuple, int] = {}
    for i, ln in enumerate(lines):
        if SECTION.match(ln) or ln.startswith("=== ") or ln.startswith("[+]"):
            section = ln.strip()[:120]
        if LOAD_FAIL.search(ln):
            out["load_failures"].append({"line": i + 1, "text": ln.strip()[:200], "section": section})
        if HASH_SEL.search(ln):
            out["hash_selected"] += 1
            if re.search(r"bge|qwen|itr|dense|semantic|nemotron", section, re.I) and not re.search(r"hash", section, re.I):
                out.setdefault("hash_selected_in_dense_section", []).append({"line": i + 1, "section": section})
        for m in PROGRESS.finditer(ln):
            a, b = int(m.group(1)), int(m.group(2))
            if 1 < b <= 200:  # step counters, not query counters
                key = (section, b)
                prog[key] = max(prog.get(key, 0), a)
    for (sec, b), a in prog.items():
        if a < b:
            out["early_stops"].append({"section": sec, "reached": f"{a}/{b}"})
    tail = [ln for ln in lines if ln.strip()][-1:] if lines else []
    out["last_line"] = tail[0][:160] if tail else ""
    return out


def logs(pub: Path, stage: Path, published: list[str]) -> dict:
    res = {}
    for rel in published:
        if not (rel.endswith(".log") or rel.endswith(".txt")) or rel.endswith("NOTES.md"):
            continue
        p = pub / rel
        if p.exists():
            res[rel] = scan_log(p, rel)
    own = {}
    for p in sorted((stage / "v0110").glob("*/*.log")):
        r = scan_log(p, str(p))
        r["load_failures"] = [x for x in r["load_failures"] if "Traceback" not in x["text"]] + \
                             [x for x in r["load_failures"] if "Traceback" in x["text"]]
        own[p.parent.name] = {"load_failures": r["load_failures"], "hash_selected": r["hash_selected"]}
    return {"published": res, "own_v0110_controls": own}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", required=True, help="artifacts repo root (published files)")
    ap.add_argument("--stage", required=True)
    ap.add_argument("--lists", nargs="*", default=[])
    ap.add_argument("--published", required=True,
                    help="file listing the published result paths (git ls-tree -r --name-only main)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pub, stage, lists = Path(a.pub), Path(a.stage), [Path(x) for x in a.lists]
    published = [x.strip() for x in Path(a.published).read_text().splitlines() if x.strip()]
    PUBLISHED[:] = published
    errors = {}
    for name, fn in (("tables_356", lambda: tables_356(pub, stage)), ("table4", lambda: table4(pub, stage)),
                     ("table7", lambda: table7(pub, lists)), ("tables_89", lambda: tables_89(pub)),
                     ("backend_comparison", lambda: backend_comparison(pub, stage)),
                     ("governance_ablation", lambda: governance_ablation(pub, stage)),
                     ("retrieval", lambda: retrieval_tab(pub, stage)),
                     ("decomposed", lambda: per_backend(pub, stage, "governance_decomposed", "fb_decomposed",
                                                        "tab:decomposed-ablation", "condition")),
                     ("alpha", lambda: per_backend(pub, stage, "alpha_sweep", "fb_alpha", "tab:alpha-sweep", "alpha")),
                     ("aggregates", lambda: aggregates(pub, stage)),
                     ("cs", lambda: cs(pub, stage)), ("tool_scaling", lambda: tool_scaling(pub, stage)),
                     ("transfer", lambda: transfer(pub, stage)), ("reranker", lambda: reranker(pub, lists))):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            import traceback
            errors[name] = traceback.format_exc()[-800:]
    L = logs(pub, stage, published)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {k: {**v, "comparators": sorted(v.get("comparators", []))} for k, v in FILES.items()}
    real = [f for f in FINDINGS if "uninformative" not in f["match"]]
    const = [f for f in FINDINGS if "uninformative" in f["match"]]
    for rel in files:
        files[rel]["flagged"] = sum(1 for f in real if f["file"] == rel)
        files[rel]["constant_array_matches"] = sum(1 for f in const if f["file"] == rel)
    unchecked = [r for r in published if r.endswith((".json", ".csv")) and r not in files]
    (out / "fallback_audit.json").write_text(json.dumps(
        {"published_commit_list": a.published, "findings": real, "constant_array_matches": const,
         "files": files, "result_files_not_compared": unchecked, "logs": L, "errors": errors},
        indent=1, default=str))
    print(f"{len(real)} findings ({len(const)} constant-array matches set aside) over {len(files)} files; "
          f"errors: {list(errors)}")
    for f in real:
        print(" ", f["file"], "|", f["cell"], "|", f["match"], "|", f["comparator"])
    for rel, v in sorted(files.items()):
        print(f"FILE {rel:70s} checked {v['cells_checked']:4d} flagged {v['flagged']} "
              f"{'PENDING ' + str(v['pending']) if v.get('pending') else ''}")
    for rel, r in L["published"].items():
        if r["load_failures"] or r["early_stops"] or r.get("hash_selected_in_dense_section"):
            print("LOG", rel, "failures", [(x["text"][:50], x["section"][:40]) for x in r["load_failures"]][:4],
                  "early", r["early_stops"][:3], "hash-in-dense", r.get("hash_selected_in_dense_section", [])[:2])
    own = {k: v for k, v in L["own_v0110_controls"].items() if v["load_failures"]}
    print("own 0.1.10 controls with load failures:", own or "none")


if __name__ == "__main__":
    main()
