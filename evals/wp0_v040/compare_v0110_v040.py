"""Compare every rerun table cell: published BEAR 0.1.10 value vs BEAR 0.4.0.

Inputs
  --pub     the artifacts repo's results/ (published files, unchanged)
  --pub-e2e evals/results/toolbench_e2e_scores.json (published e2e per-query arrays)
  --stage   the runner's stage dir, with v040/<step>/ and v0110/<step>/
  --lists   results/wp0 in the run clone (lists_v040/, lists_v0110/)

Output: compare.json (every cell) and compare.md (tables for the report).

A cell's status:
  identical           same value to machine precision
  same at 3 dp        differs below the third decimal
  changed             differs at 3 dp but inside the published 95% CI
  changed, outside CI the 0.4.0 point lies outside the published CI
Where a 0.1.10 control under the same numerics exists (same device, same
cached embeddings), the cell also says whether the control reproduces the
published value (then numerics are not the cause) and whether it equals the
0.4.0 value (then the BEAR version is not the cause).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy import stats

BACKENDS = ["Qwen3-0.6B", "Qwen3-4B", "BGE-M3", "BGE", "BM25", "Hash", "Nemotron"]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def find(stage: Path, ver: str, step_glob: str, name: str) -> list[Path]:
    return sorted((stage / ver).glob(f"{step_glob}/**/{name}"))


def merge_toolbench(paths: list[Path]) -> dict:
    out: dict = {}
    for p in paths:
        d = jload(p)
        for bench, exps in d.items():
            if bench.startswith("_") or not isinstance(exps, dict):
                continue
            for name, e in exps.items():
                if isinstance(e, dict) and "cis" in e:
                    e = dict(e)
                    e["_file"] = str(p)
                    out.setdefault(bench, {})[name] = e
    return out


def step_of(path: str) -> str:
    parts = Path(path).parts
    for i, s in enumerate(parts):
        if s in ("v040", "v0110") and i + 1 < len(parts):
            return parts[i + 1]
    return "?"


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

CELLS: list[dict] = []


def status_of(old, new) -> str:
    if old is None or new is None or old.get("pt") is None or new.get("pt") is None:
        return "missing"
    a, b = old["pt"], new["pt"]
    if math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12):
        return "identical"
    if round(a, 3) == round(b, 3):
        return "same at 3 dp"
    lo, hi = old.get("lo"), old.get("hi")
    if lo is not None and hi is not None and not (lo - 1e-12 <= b <= hi + 1e-12):
        return "changed, outside CI"
    return "changed"


def cell(table, row, col, old, new, ctrl=None, **extra) -> dict:
    c = {"table": table, "row": row, "col": col, "v0110": old, "v040": new,
         "ctrl_v0110": ctrl, "status": status_of(old, new)}
    if old and new and old.get("pt") is not None and new.get("pt") is not None:
        c["delta"] = new["pt"] - old["pt"]
    if ctrl and old and ctrl.get("pt") is not None and old.get("pt") is not None:
        c["ctrl_reproduces_published"] = math.isclose(ctrl["pt"], old["pt"], abs_tol=1e-12)
        if new and new.get("pt") is not None:
            c["ctrl_equals_v040"] = math.isclose(ctrl["pt"], new["pt"], abs_tol=1e-12)
    c.update(extra)
    CELLS.append(c)
    return c


def v(pt, lo=None, hi=None, **kw):
    if pt is None:
        return None
    d = {"pt": float(pt), "lo": None if lo is None else float(lo), "hi": None if hi is None else float(hi)}
    d.update(kw)
    return d


def tb_val(e, metric):
    if not e:
        return None
    ci = e["cis"][metric]
    return v(ci["point_estimate"], ci["ci_lower"], ci["ci_upper"], step=step_of(e.get("_file", "")))


def n_query_diff(a, b, metrics=("recall", "ndcg")) -> int | None:
    if not a or not b:
        return None
    diff = np.zeros(len(a["metrics"]["recall"]), dtype=bool)
    for m in metrics:
        x, y = np.asarray(a["metrics"][m]), np.asarray(b["metrics"][m])
        if x.shape != y.shape:
            return None
        diff |= np.abs(x - y) > 1e-12
    return int(diff.sum())


def paired(gov, nogov, metric="recall") -> dict | None:
    if not gov or not nogov:
        return None
    a, b = np.asarray(gov["metrics"][metric]), np.asarray(nogov["metrics"][metric])
    d = a - b
    sd = d.std(ddof=1)
    t = stats.ttest_rel(a, b) if sd > 0 else None
    nz = d[d != 0]
    w = stats.wilcoxon(nz) if len(nz) >= 5 else None
    return {"delta": float(d.mean()), "d": float(d.mean() / sd) if sd > 0 else 0.0,
            "t": float(t.statistic) if t else 0.0, "p": float(t.pvalue) if t else 1.0,
            "wilcoxon_p": float(w.pvalue) if w else None}


# ---------------------------------------------------------------------------
# External benchmarks: Tables 3, 5, 6 (and Nemotron rows)
# ---------------------------------------------------------------------------

def external(pub: Path, stage: Path) -> dict:
    pub3 = jload(pub / "toolbench_eval_v0110.json")
    pub56 = jload(pub / "toolbench_eval_metatool_v0110.json")
    published = {"ToolBench": pub3["ToolBench"], "MetaTool": pub56["MetaTool"],
                 "MetaTool+Tags": pub56["MetaTool+Tags"],
                 "MetaTool+QueryTags-top5": pub56["MetaTool+QueryTags-top5"]}
    new = merge_toolbench(find(stage, "v040", "tb*", "toolbench_eval_*.json"))
    ctrl = merge_toolbench(find(stage, "v0110", "tb*", "toolbench_eval_*.json"))
    tables = {"ToolBench": "Table 3 (tab:toolbench-results)", "MetaTool": "Table 5 (tab:metatool-results)",
              "MetaTool+Tags": "Table 6 (tab:metatool-tags-results) +Tags",
              "MetaTool+QueryTags-top5": "Table 6 (tab:metatool-tags-results) +QueryTags"}
    stats_out = {}
    for bench, table in tables.items():
        for lab in BACKENDS:
            names = [f"BEAR+{lab} (gov)", f"{lab} (no gov)", f"BEAR+{lab} (mand-only)"]
            for name in names:
                if bench == "MetaTool+QueryTags-top5" and "(no gov)" in name:
                    pass
                po = published[bench].get(name)
                ne = new.get(bench, {}).get(name)
                co = ctrl.get(bench, {}).get(name)
                if po is None and ne is None:
                    continue
                for m in ("recall", "ndcg"):
                    cell(table, name, f"{m}@5", tb_val(po, m), tb_val(ne, m), tb_val(co, m),
                         n_query_diff=n_query_diff(po, ne),
                         ctrl_n_query_diff_vs_pub=n_query_diff(po, co),
                         ctrl_n_query_diff_vs_v040=n_query_diff(co, ne))
            g, u = f"BEAR+{lab} (gov)", f"{lab} (no gov)"
            stats_out.setdefault(bench, {})[lab] = {
                "v0110": paired(published[bench].get(g), published[bench].get(u)),
                "v040": paired(new.get(bench, {}).get(g), new.get(bench, {}).get(u)),
                "v0110_ndcg": paired(published[bench].get(g), published[bench].get(u), "ndcg"),
                "v040_ndcg": paired(new.get(bench, {}).get(g), new.get(bench, {}).get(u), "ndcg"),
            }
    return {"paired_gov_vs_nogov": stats_out}


# ---------------------------------------------------------------------------
# Table 4
# ---------------------------------------------------------------------------

def table4(pub: Path, stage: Path) -> None:
    for fname, step, lab in (("toolbench_inferred_metrics.json", "t4_inferred", "top-1"),
                             ("toolbench_multitag_metrics.json", "t4_multitag", "multi"),
                             ("toolbench_top5_metrics.json", "t4_top5", "top-5")):
        po = jload(pub / fname)
        hits = find(stage, "v040", step, fname)
        ne = jload(hits[0]) if hits else None
        for row in po["rows"]:
            cond = row["condition"]
            nrow = next((r for r in (ne or {}).get("rows", []) if r["condition"] == cond), None)
            for m in ("recall", "ndcg", "f1"):
                o = row.get(m)
                n = (nrow or {}).get(m)
                cell("Table 4 (tab:toolbench-inferred)", f"{lab}: {cond}", f"{m}@5",
                     v(o["mean"], o["ci_lo"], o["ci_hi"]) if o else None,
                     v(n["mean"], n["ci_lo"], n["ci_hi"]) if n else None)
        if ne:
            for k in ("classifier_top1_accuracy", "set_accuracy", "mean_categories_per_query"):
                if k in po:
                    cell("Table 4 (tab:toolbench-inferred)", f"{lab}: classifier", k,
                         v(po[k]), v(ne.get(k)))


# ---------------------------------------------------------------------------
# Pet Sim
# ---------------------------------------------------------------------------

RETR_RE = re.compile(r"^(Full BEAR|Pure Similarity|Priority-Heavy) \(\$\\alpha=([0-9.]+)\$\):")
F1_RE = re.compile(r"(Strict|Relaxed):\s+P@10=([0-9.]+) \[([0-9.]+), ([0-9.]+)\], R@10=([0-9.]+) \[([0-9.]+), ([0-9.]+)\], F1@10=([0-9.]+) \[([0-9.]+), ([0-9.]+)\]")


def parse_retrieval(text: str) -> dict:
    out, cur = {}, None
    for line in text.splitlines():
        m = RETR_RE.match(line.strip())
        if m:
            cur = m.group(1)
            continue
        m = F1_RE.search(line)
        if m and cur and (cur, m.group(1)) not in out:
            g = [float(x) for x in m.groups()[1:]]
            out[(cur, m.group(1))] = {"R": v(g[3], g[4], g[5]), "F1": v(g[6], g[7], g[8])}
    return out


def retrieval_table(pub: Path, stage: Path) -> None:
    for fname, step, lab in (("eval_retrieval_output.txt", "retrieval_hash", "Hash"),
                             ("eval_retrieval_semantic_output.txt", "retrieval_semantic", "BGE")):
        po = parse_retrieval((pub / fname).read_text(encoding="utf-8", errors="replace"))
        logs = list((stage / "v040" / step).glob("*.log"))
        ne = parse_retrieval(logs[0].read_text(errors="replace")) if logs else {}
        clog = list((stage / "v0110" / f"{step}_v0110").glob("*.log"))
        co = parse_retrieval(clog[0].read_text(errors="replace")) if clog else {}
        for key in po:
            for m in ("F1", "R"):
                cell("tab:retrieval", f"{key[0]} ({lab})", f"{key[1]} {m}@10",
                     po[key][m], (ne.get(key) or {}).get(m), (co.get(key) or {}).get(m))


def gov_ablation(pub: Path, stage: Path) -> None:
    po = jload(pub / "governance_ablation.json")
    hits = find(stage, "v040", "gov_ablation", "governance_ablation.json")
    ne = jload(hits[0]) if hits else {}
    chits = find(stage, "v0110", "gov_ablation_v0110", "governance_ablation.json")
    co = jload(chits[0]) if chits else {}
    for panel in ("Full governance", "Mandatory only", "No governance"):
        for qs, backs in po.get(panel, {}).items():
            for b, val in backs.items():
                def g(d):
                    x = d.get(panel, {}).get(qs, {}).get(b)
                    return v(x["f1"], *x["ci"]) if x else None
                cell("tab:governance-ablation", f"{panel} / {b}", qs, g(po), g(ne), g(co))
    for strat, val in po.get("token_efficiency", {}).items():
        def t(d, k):
            x = d.get("token_efficiency", {}).get(strat)
            return v(x[k]) if x else None
        cell("tab:token-compare", strat, "tokens/query", t(po, "tokens"), t(ne, "tokens"), t(co, "tokens"))
        cell("tab:token-compare", strat, "instructions", t(po, "instructions"), t(ne, "instructions"),
             t(co, "instructions"))


def _bk(r: dict) -> str:
    return r.get("backend") or r.get("short") or r.get("label") or "?"


def backend_comparison(pub: Path, stage: Path) -> None:
    po = {_bk(r): r for r in jload(pub / "backend_comparison.json")}
    hits = find(stage, "v040", "backends", "backend_comparison.json")
    ne = {_bk(r): r for r in jload(hits[0])} if hits else {}
    chits = find(stage, "v0110", "backends_v0110", "backend_comparison.json")
    co = {_bk(r): r for r in jload(chits[0])} if chits else {}
    for b, r in po.items():
        for k in ("strict_f1", "relaxed_f1", "para_f1", "notag_f1", "complex_f1"):
            if k not in r:
                continue
            def g(d):
                x = d.get(b)
                if not x or k not in x:
                    return None
                ci = x.get(k + "_ci") or [None, None]
                return v(x[k], ci[0], ci[1])
            cell("tab:governance-ablation (a) via backend_comparison", r.get("short", b), k, g(po), g(ne), g(co))
        for k in ("avg_query_ms",):
            if k in r:
                cell("tab:governance-ablation (a) via backend_comparison", r.get("short", b), k,
                     v(r[k]), v((ne.get(b) or {}).get(k)), None)


def decomposed(pub: Path, stage: Path) -> None:
    for bk in ("bge", "bge-m3", "qwen3", "qwen3-4b", "bm25"):
        fname = f"governance_decomposed_{bk}.json"
        po = jload(pub / fname)
        hits = find(stage, "v040", "decomposed", fname)
        ne = jload(hits[0]) if hits else {}
        chits = find(stage, "v0110", "decomposed_v0110", fname)
        co = jload(chits[0]) if chits else {}
        for row in po["rows"]:
            def g(d):
                x = next((r for r in d.get("rows", []) if r["condition"] == row["condition"]), None)
                return v(x["mean_f1"], x["ci_lo"], x["ci_hi"]) if x else None
            cell("tab:decomposed-ablation", row["label"], bk, g(po), g(ne), g(co))


def alpha(pub: Path, stage: Path) -> None:
    for bk in ("bge", "bge-m3", "qwen3", "qwen3-4b", "bm25"):
        fname = f"alpha_sweep_{bk}.json"
        po = jload(pub / fname)
        hits = find(stage, "v040", "alpha_sweep", fname)
        ne = jload(hits[0]) if hits else {}
        chits = find(stage, "v0110", "alpha_sweep_v0110", fname)
        co = jload(chits[0]) if chits else {}
        for row in po["rows"]:
            def g(d):
                x = next((r for r in d.get("rows", []) if abs(r["alpha"] - row["alpha"]) < 1e-9), None)
                return v(x["mean_f1"], x["ci_lo"], x["ci_hi"]) if x else None
            cell("tab:alpha-sweep", f"alpha={row['alpha']:.2f}", bk, g(po), g(ne), g(co))


# ---------------------------------------------------------------------------
# Tool scaling, CPA
# ---------------------------------------------------------------------------

SCALE_RE = re.compile(r"Corpus size:\s+(\d+) tools \| Precision: ([0-9.]+) .*\| Recall: ([0-9.]+) .*\| No cross-domain leaks: (\w+)")
SAVE_RE = re.compile(r"^\s+(.+?)\.{2,}\s+(\d+) tools \|\s+(\d+) tokens \| savings: (\d+)%")


def parse_scaling(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = SCALE_RE.search(line)
        if m:
            out[("scale", m.group(1), "precision")] = float(m.group(2))
            out[("scale", m.group(1), "recall")] = float(m.group(3))
            out[("scale", m.group(1), "no_leaks")] = 1.0 if m.group(4) == "True" else 0.0
        m = SAVE_RE.match(line)
        if m:
            out[("savings", m.group(1), "tools")] = float(m.group(2))
            out[("savings", m.group(1), "tokens")] = float(m.group(3))
            out[("savings", m.group(1), "savings%")] = float(m.group(4))
        m = re.search(r"All-tools baseline: (\d+) tools, (\d+) tokens", line)
        if m:
            out[("savings", "All-tools baseline", "tokens")] = float(m.group(2))
        m = re.search(r"Average token savings: (\d+)%", line)
        if m:
            out[("savings", "Average", "savings%")] = float(m.group(1))
    return out


def tool_scaling(pub: Path, stage: Path) -> None:
    po = parse_scaling((pub / "eval_tool_scaling_output.txt").read_text(errors="replace"))
    logs = list((stage / "v040" / "tool_scaling").glob("*.log"))
    ne = parse_scaling(logs[0].read_text(errors="replace")) if logs else {}
    clogs = list((stage / "v0110" / "tool_scaling_v0110").glob("*.log"))
    co = parse_scaling(clogs[0].read_text(errors="replace")) if clogs else {}
    for k, val in po.items():
        table = "tab:tool-scaling" if k[0] == "scale" else "tab:token-savings"
        cell(table, k[1], k[2], v(val), v(ne.get(k)), v(co.get(k)))


def cpa(pub: Path, stage: Path) -> None:
    def rows(p):
        with open(p, newline="") as f:
            return {int(r["num_agents"]): r for r in csv.DictReader(f)}
    po = rows(pub / "baseline_comparison_results.csv")
    hits = find(stage, "v040", "baseline_comparison", "baseline_comparison_results.csv")
    ne = rows(hits[0]) if hits else {}
    chits = find(stage, "v0110", "baseline_comparison_v0110", "baseline_comparison_results.csv")
    co = rows(chits[0]) if chits else {}
    cols = [("bear_mean_tokens", "tab:token-efficiency"), ("cpa_mean_tokens", "tab:token-efficiency"),
            ("static_tokens", "tab:token-efficiency"), ("bear_token_ratio", "tab:token-efficiency"),
            ("bear_novel_recall", "novel departments (text)"), ("cpa_novel_recall", "novel departments (text)"),
            ("bear_semantic_recall", "tab:semantic-advantage"), ("cpa_semantic_recall", "tab:semantic-advantage"),
            ("bear_persona_recall", "standard queries (text)"), ("bear_dept_recall", "standard queries (text)"),
            ("bear_safety_recall", "standard queries (text)"), ("bear_global_recall", "standard queries (text)"),
            ("bear_scope_violations", "standard queries (text)")]
    for n, r in po.items():
        for col, table in cols:
            if col not in r:
                continue
            def g(d):
                x = d.get(n)
                return v(float(x[col])) if x and x.get(col) not in (None, "") else None
            cell(table, f"N={n}", col, g(po), g(ne), g(co))


# ---------------------------------------------------------------------------
# Reranker, LlamaIndex, transfer, ToolBench-IR composition
# ---------------------------------------------------------------------------

def arms_metric(d, arm, metric):
    x = (d or {}).get("arms", {}).get(arm, {}).get("metrics", {}).get(metric)
    if not x:
        return None
    return v(x["mean"], *(x.get("ci") or [None, None]))


def reranker(pub: Path, stage: Path) -> None:
    for corpus in ("toolbench", "petsim"):
        for fname, step in ((f"reranker_composition_{corpus}.json", f"reranker_{corpus}"),
                            (f"framework_baseline_{corpus}.json", f"framework_{corpus}")):
            po = jload(pub / fname)
            hits = find(stage, "v040", step, fname)
            ne = jload(hits[0]) if hits else None
            for arm, a in po.get("arms", {}).items():
                for metric in a.get("metrics", {}):
                    if metric not in ("recall", "f1", "strict_f1", "relaxed_f1", "ndcg"):
                        continue
                    cell("tab:reranker", f"{corpus}: {a.get('label', arm)}", metric,
                         arms_metric(po, arm, metric), arms_metric(ne, arm, metric))
            for cname, c in po.get("contrasts", {}).items():
                nc = (ne or {}).get("contrasts", {}).get(cname)
                cell("tab:reranker contrasts", f"{corpus}: {cname}", c.get("metric", "?"),
                     v(c.get("delta"), *(c.get("ci") or [None, None])),
                     v(nc.get("delta"), *(nc.get("ci") or [None, None])) if nc else None,
                     d_v0110=c.get("cohens_d_paired"), d_v040=(nc or {}).get("cohens_d_paired"))


def transfer(pub: Path, stage: Path) -> None:
    for corpus in ("toolbench", "metatool"):
        fname = f"backend_transfer_{corpus}_toolbench_ir_bert_based_uncased.json"
        po = jload(pub / fname)
        hits = find(stage, "v040", f"transfer_{corpus}", fname)
        ne = jload(hits[0]) if hits else None
        for m in ("recall", "ndcg", "f1"):
            x = po["metrics"].get(m)
            y = (ne or {}).get("metrics", {}).get(m)
            cell("tab:transfer", f"ToolBench-IR on {corpus}", f"{m}@5",
                 v(x["mean"], *x["ci"]) if x else None, v(y["mean"], *y["ci"]) if y else None)
    po = jload(pub / "toolbench_toolllm_fixed.json")
    hits = find(stage, "v040", "toolllm_both", "toolbench_toolllm_fixed.json")
    ne = jload(hits[0]) if hits else {}
    for c in po["conditions"]:
        nc = next((x for x in ne.get("conditions", []) if x["label"] == c["label"]), None)
        for m in ("recall", "ndcg"):
            x, y = c["metrics"].get(m), (nc or {}).get("metrics", {}).get(m)
            cell("ToolBench-IR + governance (Sec. 6.3 text)", c["label"], f"{m}@5",
                 v(x["mean"], *x["ci"]) if x else None, v(y["mean"], *y["ci"]) if y else None)


# ---------------------------------------------------------------------------
# End-to-end lists
# ---------------------------------------------------------------------------

def e2e_lists(lists: Path, pub_e2e: Path) -> dict:
    pub = {s["condition"]: s for s in jload(pub_e2e)["scores"]}
    out = {}
    d040, d0110 = lists / "lists_v040" / "e2e", lists / "lists_v0110" / "e2e"
    for p in sorted(d040.glob("*.json")):
        a = jload(p)
        name = a["condition"]
        rec = {"n_queries": a["n_queries"], "backend": a["backend"]}
        b_path = d0110 / p.name
        if b_path.exists():
            b = jload(b_path)
            ordered = sum(1 for x, y in zip(a["ids"], b["ids"]) if x != y)
            asset = sum(1 for x, y in zip(a["ids"], b["ids"]) if set(x) != set(y))
            rec.update({"v0110_vs_v040_ordered_diff": ordered, "v0110_vs_v040_set_diff": asset,
                        "examples": [{"q": i, "v0110": y, "v040": x}
                                     for i, (x, y) in enumerate(zip(a["ids"], b["ids"])) if x != y][:5]})
            ps = pub.get(name)
            if ps:
                for lab, src in (("v0110_regen", b), ("v040", a)):
                    rec[f"{lab}_matches_published_arrays"] = {
                        m: int(np.sum(np.abs(np.asarray(src[f"_{m}_scores"]) - np.asarray(ps[f"_{m}_scores"])) > 1e-12))
                        for m in ("recall", "precision", "ndcg")}
        else:
            ps = pub.get(name)
            if ps:
                rec["v040_matches_published_arrays"] = {
                    m: int(np.sum(np.abs(np.asarray(a[f"_{m}_scores"]) - np.asarray(ps[f"_{m}_scores"])) > 1e-12))
                    for m in ("recall", "precision", "ndcg")}
        rec["recall5_v040"] = float(np.mean(a["_recall_scores"]))
        if name in pub:
            rec["recall5_published"] = float(np.mean(pub[name]["_recall_scores"]))
        out[name] = rec
    return out


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def fmt(x, nd=3):
    if not x or x.get("pt") is None:
        return "n/a"
    s = f"{x['pt']:.{nd}f}"
    if x.get("lo") is not None and x.get("hi") is not None:
        s += f" [{x['lo']:.{nd}f}, {x['hi']:.{nd}f}]"
    return s


def markdown(extra: dict) -> str:
    lines = []
    by_table: dict = {}
    for c in CELLS:
        by_table.setdefault(c["table"], []).append(c)
    counts: dict = {}
    for c in CELLS:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    lines.append("Status counts: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())))
    for table, cells in by_table.items():
        lines.append(f"\n#### {table}\n")
        lines.append("| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |")
        lines.append("|---|---|---|---|---|---|---|")
        for c in cells:
            notes = []
            if c.get("n_query_diff") is not None:
                notes.append(f"{c['n_query_diff']} queries differ")
            if "ctrl_reproduces_published" in c:
                notes.append("0.1.10 control " + ("reproduces published" if c["ctrl_reproduces_published"]
                                                  else f"= {c['ctrl_v0110']['pt']:.4f}"))
                if "ctrl_equals_v040" in c:
                    notes.append("control = 0.4.0" if c["ctrl_equals_v040"] else "control ≠ 0.4.0")
            if c.get("v040") and c["v040"].get("step"):
                notes.append(f"step {c['v040']['step']}")
            nd = 3 if c["col"] not in ("tokens/query", "tokens", "instructions") else 1
            d = c.get("delta")
            lines.append(f"| {c['row']} | {c['col']} | {fmt(c['v0110'], nd)} | {fmt(c['v040'], nd)} | "
                         f"{'' if d is None else f'{d:+.4f}'} | {c['status']} | {'; '.join(notes)} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", required=True)
    ap.add_argument("--pub-e2e", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--lists", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    pub, stage = Path(args.pub), Path(args.stage)
    extra = {}
    sections = [("external", lambda: external(pub, stage)), ("table4", lambda: table4(pub, stage)),
                ("retrieval", lambda: retrieval_table(pub, stage)),
                ("gov_ablation", lambda: gov_ablation(pub, stage)),
                ("backend_comparison", lambda: backend_comparison(pub, stage)),
                ("decomposed", lambda: decomposed(pub, stage)), ("alpha", lambda: alpha(pub, stage)),
                ("tool_scaling", lambda: tool_scaling(pub, stage)), ("cpa", lambda: cpa(pub, stage)),
                ("reranker", lambda: reranker(pub, stage)), ("transfer", lambda: transfer(pub, stage)),
                ("e2e_lists", lambda: e2e_lists(Path(args.lists), Path(args.pub_e2e)))]
    errors = {}
    for name, fn in sections:
        try:
            r = fn()
            if r:
                extra[name] = r
        except Exception as exc:  # noqa: BLE001
            errors[name] = repr(exc)
            print(f"section {name} failed: {exc!r}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.json").write_text(json.dumps({"cells": CELLS, **extra, "errors": errors},
                                                 indent=1, default=float), encoding="utf-8")
    (out / "compare.md").write_text(markdown(extra), encoding="utf-8")
    print(f"{len(CELLS)} cells; errors: {errors}")


if __name__ == "__main__":
    main()
