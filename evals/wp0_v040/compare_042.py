"""Cell-by-cell comparison: published BEAR 0.1.10 values vs BEAR 0.4.2, with
attribution of every moved cell to a release change.

Inputs (run_wp0_v040.sh stage layout, root ~/tist-evals/wp0-v042):
  --pub      the artifacts repo's results/ (published files)
  --pub-e2e  evals/results/toolbench_e2e_scores.json (published e2e arrays)
  --stage    <root>/stage, with v042/, v042L/ (single legacy switch runs, steps
             named <step>_L<switch>) and v0110/ (0.1.10 controls)
  --lists    the clones' results/wp0 folders (lists_v042/, lists_v0110/,
             lists_v042L_<switch>/)

For each cell:
  status        identical | same at 3 dp | changed | changed, outside CI
  control       the 0.1.10 control under today's numerics; "reproduces" means
                it equals the published value, so the environment is not why
                the cell moved
  restored_by   the single legacy switches whose 0.4.2 run gives back the
                published value exactly; "all" is every switch at once. A cell
                that "all" does not restore moved through the mandatory rules,
                which have no switch.

Output: compare.json, compare.md.
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

NEW = "v042"
SWITCHES = ["all", "ungated_pool", "below_threshold", "ranked_resolution", "removed_acting",
            "pool_by_k", "unchecked_requires", "flat_backfill", "dropped_rows", "tie_order"]
BACKENDS = ["Qwen3-0.6B", "Qwen3-4B", "BGE-M3", "BGE", "BM25", "Hash", "Nemotron"]
CELLS: list[dict] = []


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def files(stage: Path, ver: str, step_glob: str, name_glob: str) -> list[Path]:
    return sorted(p for p in (stage / ver).glob(f"{step_glob}/**/{name_glob}")
                  if not p.name.endswith(".provenance.json"))


def v(pt, lo=None, hi=None):
    if pt is None:
        return None
    return {"pt": float(pt), "lo": None if lo is None else float(lo), "hi": None if hi is None else float(hi)}


def close(a, b):
    return a is not None and b is not None and math.isclose(a["pt"], b["pt"], rel_tol=1e-12, abs_tol=1e-12)


def status(old, new):
    if old is None or new is None:
        return "missing"
    if close(old, new):
        return "identical"
    if round(old["pt"], 3) == round(new["pt"], 3):
        return "same at 3 dp"
    if old.get("lo") is not None and not (old["lo"] - 1e-12 <= new["pt"] <= old["hi"] + 1e-12):
        return "changed, outside CI"
    return "changed"


def cell(table, row, col, old, new, ctrl=None, att=None, **extra):
    c = {"table": table, "row": row, "col": col, "v0110": old, NEW: new, "ctrl_v0110": ctrl,
         "status": status(old, new), **extra}
    if old and new:
        c["delta"] = new["pt"] - old["pt"]
    if ctrl is not None and old is not None:
        c["ctrl_reproduces_published"] = close(ctrl, old)
    if att and c["status"] not in ("identical", "missing"):
        c["restored_by"] = [sw for sw in SWITCHES if close(att.get(sw), old)]
        c["switch_values"] = {sw: att[sw]["pt"] for sw in att if att.get(sw)}
        if att.get("all") is not None and not close(att["all"], old):
            c["not_restored_by_all"] = True
    CELLS.append(c)


# ---------------------------------------------------------------------------
# Tables 3, 5, 6 (eval_toolbench)
# ---------------------------------------------------------------------------

def merge_tb(paths):
    out = {}
    for p in paths:
        for bench, exps in jload(p).items():
            if bench.startswith("_") or not isinstance(exps, dict):
                continue
            for name, e in exps.items():
                if isinstance(e, dict) and "cis" in e:
                    out.setdefault(bench, {})[name] = e
    return out


def tbv(e, m):
    if not e:
        return None
    c = e["cis"][m]
    return v(c["point_estimate"], c["ci_lower"], c["ci_upper"])


def ndiff(a, b):
    if not a or not b:
        return None
    x = np.array(a["metrics"]["recall"]), np.array(a["metrics"]["ndcg"])
    y = np.array(b["metrics"]["recall"]), np.array(b["metrics"]["ndcg"])
    if x[0].shape != y[0].shape:
        return None
    return int(np.sum((np.abs(x[0] - y[0]) > 1e-12) | (np.abs(x[1] - y[1]) > 1e-12)))


def paired(g, u, m="recall"):
    if not g or not u:
        return None
    a, b = np.asarray(g["metrics"][m]), np.asarray(u["metrics"][m])
    d = a - b
    sd = d.std(ddof=1)
    t = stats.ttest_rel(a, b) if sd > 0 else None
    return {"delta": float(d.mean()), "d": float(d.mean() / sd) if sd > 0 else 0.0,
            "t": float(t.statistic) if t else 0.0, "p": float(t.pvalue) if t else 1.0}


def external(pub: Path, stage: Path) -> dict:
    p3, p56 = jload(pub / "toolbench_eval_v0110.json"), jload(pub / "toolbench_eval_metatool_v0110.json")
    published = {"ToolBench": p3["ToolBench"], "MetaTool": p56["MetaTool"],
                 "MetaTool+Tags": p56["MetaTool+Tags"], "MetaTool+QueryTags-top5": p56["MetaTool+QueryTags-top5"]}
    new = merge_tb([p for p in files(stage, NEW, "tb*", "toolbench_eval_*.json")])
    ctrl = merge_tb(files(stage, "v0110", "tb*", "toolbench_eval_*.json"))
    att = {sw: merge_tb(files(stage, NEW + "L", f"tb_*_L{sw}", "toolbench_eval_*.json")) for sw in SWITCHES}
    tables = {"ToolBench": "Table 3", "MetaTool": "Table 5", "MetaTool+Tags": "Table 6 +Tags",
              "MetaTool+QueryTags-top5": "Table 6 +QueryTags"}
    paired_out = {}
    for bench, table in tables.items():
        for lab in BACKENDS:
            for name in (f"BEAR+{lab} (gov)", f"{lab} (no gov)", f"BEAR+{lab} (mand-only)"):
                po, ne = published[bench].get(name), new.get(bench, {}).get(name)
                if po is None and ne is None:
                    continue
                co = ctrl.get(bench, {}).get(name)
                for m in ("recall", "ndcg"):
                    a = {sw: tbv(att[sw].get(bench, {}).get(name), m) for sw in SWITCHES
                         if att[sw].get(bench, {}).get(name)}
                    cell(table, name, f"{m}@5", tbv(po, m), tbv(ne, m), tbv(co, m), a,
                         n_query_diff=ndiff(po, ne), ctrl_n_query_diff=ndiff(po, co),
                         ctrl_vs_new_n_query_diff=ndiff(co, ne))
            g, u = f"BEAR+{lab} (gov)", f"{lab} (no gov)"
            paired_out.setdefault(bench, {})[lab] = {
                "v0110": paired(published[bench].get(g), published[bench].get(u)),
                NEW: paired(new.get(bench, {}).get(g), new.get(bench, {}).get(u))}
    return paired_out


# ---------------------------------------------------------------------------
# Pet Sim
# ---------------------------------------------------------------------------

def bkey(r):
    return r.get("backend") or r.get("short") or r.get("label") or "?"


def bc_rows(paths):
    out = {}
    for p in paths:
        lexical = "_lex" in str(p)
        for r in jload(p):
            k = bkey(r)
            # The lexical runs refuse local models, so their ITR rows ran with
            # ITR's encoder and reranker missing. Take ITR from a dense run.
            if lexical and "itr" in k.lower():
                continue
            out[k] = r
    return out


def backend_comparison(pub: Path, stage: Path) -> None:
    P = bc_rows([pub / "backend_comparison.json"])
    N = bc_rows(files(stage, NEW, "backends*", "backend_comparison*.json"))
    C = bc_rows(files(stage, "v0110", "backends*_v0110", "backend_comparison*.json"))
    A = {sw: bc_rows(files(stage, NEW + "L", f"backends*_L{sw}", "backend_comparison*.json")) for sw in SWITCHES}
    for b, r in P.items():
        for k in ("strict_f1", "relaxed_f1", "para_f1", "notag_f1", "complex_f1"):
            if k not in r:
                continue

            def g(d):
                x = d.get(b)
                if not x or k not in x:
                    return None
                ci = x.get(k + "_ci") or [None, None]
                return v(x[k], ci[0], ci[1])
            if g(N) is None:
                continue
            cell("tab:governance-ablation (a)", r.get("short", b), k, g(P), g(N), g(C),
                 {sw: g(A[sw]) for sw in SWITCHES if g(A[sw]) is not None})


def gov_ablation(pub: Path, stage: Path) -> None:
    def load(paths):
        out = {}
        for p in paths:
            d = jload(p)
            for panel, qs in d.items():
                if panel.startswith("_") or not isinstance(qs, dict):
                    continue
                for q, backs in qs.items():
                    if isinstance(backs, dict):
                        for b, val in backs.items():
                            out.setdefault(panel, {}).setdefault(q, {})[b] = val
        return out
    P = load([pub / "governance_ablation.json"])
    N = load(files(stage, NEW, "gov_ablation*", "governance_ablation*.json"))
    C = load(files(stage, "v0110", "gov_ablation*_v0110", "governance_ablation*.json"))
    A = {sw: load(files(stage, NEW + "L", f"gov_ablation*_L{sw}", "governance_ablation*.json")) for sw in SWITCHES}
    for panel in ("Full governance", "Mandatory only", "No governance"):
        for q, backs in P.get(panel, {}).items():
            for b in backs:
                def g(d):
                    x = d.get(panel, {}).get(q, {}).get(b)
                    return v(x["f1"], *x["ci"]) if isinstance(x, dict) and "f1" in x else None
                if g(N) is None:
                    continue
                cell("tab:governance-ablation", f"{panel} / {b}", q, g(P), g(N), g(C),
                     {sw: g(A[sw]) for sw in SWITCHES if g(A[sw]) is not None})
    for strat in P.get("token_efficiency", {}):
        def t(d):
            x = d.get("token_efficiency", {}).get(strat)
            return v(x["tokens"]) if isinstance(x, dict) else None
        if t(N) is not None:
            cell("tab:token-compare", strat, "tokens/query", t(P), t(N), t(C))


def per_backend_rows(pub, stage, prefix, key, table, rowkey, colfmt):
    for bk in ("bge", "bge-m3", "qwen3", "qwen3-4b", "bm25"):
        fname = f"{prefix}_{bk}.json"
        if not (pub / fname).exists():
            continue
        P = jload(pub / fname)
        nf = files(stage, NEW, f"{key}*", fname)
        if not nf:
            continue
        N = jload(nf[0])
        cf = files(stage, "v0110", f"{key}*_v0110", fname)
        C = jload(cf[0]) if cf else {}
        A = {sw: (jload(x[0]) if (x := files(stage, NEW + "L", f"{key}*_L{sw}", fname)) else {}) for sw in SWITCHES}
        for row in P["rows"]:
            rk = row[rowkey]

            def g(d):
                x = next((r for r in d.get("rows", []) if (abs(r[rowkey] - rk) < 1e-9 if isinstance(rk, float)
                                                           else r[rowkey] == rk)), None)
                return v(x["mean_f1"], x["ci_lo"], x["ci_hi"]) if x else None
            cell(table, colfmt(row), bk, g(P), g(N), g(C), {sw: g(A[sw]) for sw in SWITCHES if g(A[sw])})


RETR_RE = re.compile(r"^(Full BEAR|Pure Similarity|Priority-Heavy) \(\$\\alpha=([0-9.]+)\$\):")
F1_RE = re.compile(r"(Strict|Relaxed):\s+P@10=([0-9.]+) \[([0-9.]+), ([0-9.]+)\], R@10=([0-9.]+) \[([0-9.]+), ([0-9.]+)\], F1@10=([0-9.]+) \[([0-9.]+), ([0-9.]+)\]")


def parse_retrieval(text):
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


def last_attempt(text):
    parts = text.split("### ================ attempt")
    return parts[-1]


def retrieval(pub: Path, stage: Path) -> None:
    for fname, step, lab in (("eval_retrieval_output.txt", "retrieval_hash", "Hash"),
                             ("eval_retrieval_semantic_output.txt", "retrieval_semantic", "BGE")):
        def lg(ver, st):
            p = stage / ver / st / f"{st}.log"
            return parse_retrieval(last_attempt(p.read_text(errors="replace"))) if p.exists() else {}
        P = parse_retrieval((pub / fname).read_text(errors="replace"))
        N = lg(NEW, step)
        if not N:
            continue
        C = lg("v0110", f"{step}_v0110")
        A = {sw: lg(NEW + "L", f"{step}_L{sw}") for sw in SWITCHES}
        for key in P:
            for m in ("F1", "R"):
                cell("tab:retrieval", f"{key[0]} ({lab})", f"{key[1]} {m}@10", P[key][m],
                     (N.get(key) or {}).get(m), (C.get(key) or {}).get(m),
                     {sw: (A[sw].get(key) or {}).get(m) for sw in SWITCHES if A[sw].get(key)})


# ---------------------------------------------------------------------------
# Other tables (filled once their runs exist)
# ---------------------------------------------------------------------------

def table4(pub: Path, stage: Path) -> None:
    for fname, step, lab in (("toolbench_inferred_metrics.json", "t4_inferred", "top-1"),
                             ("toolbench_multitag_metrics.json", "t4_multitag", "multi"),
                             ("toolbench_top5_metrics.json", "t4_top5", "top-5")):
        nf = files(stage, NEW, step, fname)
        if not nf:
            continue
        P, N = jload(pub / fname), jload(nf[0])
        for row in P["rows"]:
            nr = next((r for r in N["rows"] if r["condition"] == row["condition"]), None)
            for m in ("recall", "ndcg", "f1"):
                o, n = row.get(m), (nr or {}).get(m)
                cell("Table 4", f"{lab}: {row['condition']}", f"{m}@5",
                     v(o["mean"], o["ci_lo"], o["ci_hi"]) if o else None,
                     v(n["mean"], n["ci_lo"], n["ci_hi"]) if n else None)


SCALE_RE = re.compile(r"Corpus size:\s+(\d+) tools \| Precision: ([0-9.]+) .*\| Recall: ([0-9.]+) .*\| No cross-domain leaks: (\w+)")
SAVE_RE = re.compile(r"^\s+(.+?)\.{2,}\s+(\d+) tools \|\s+(\d+) tokens \| savings: (\d+)%")


def parse_scaling(text):
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
    def lg(ver, st):
        p = stage / ver / st / f"{st}.log"
        return parse_scaling(last_attempt(p.read_text(errors="replace"))) if p.exists() else {}
    po = parse_scaling((pub / "eval_tool_scaling_output.txt").read_text(errors="replace"))
    ne, co = lg(NEW, "tool_scaling"), lg("v0110", "tool_scaling_v0110")
    if not ne:
        return
    for k, val in po.items():
        table = "tab:tool-scaling" if k[0] == "scale" else "tab:token-savings"
        cell(table, k[1], k[2], v(val), v(ne.get(k)), v(co.get(k)))


def cpa(pub: Path, stage: Path) -> None:
    def rows(p):
        with open(p, newline="") as f:
            return {int(r["num_agents"]): r for r in csv.DictReader(f)}
    nf = files(stage, NEW, "baseline_comparison", "baseline_comparison_results.csv")
    if not nf:
        return
    cf = files(stage, "v0110", "baseline_comparison_v0110", "baseline_comparison_results.csv")
    P, N, C = rows(pub / "baseline_comparison_results.csv"), rows(nf[0]), (rows(cf[0]) if cf else {})
    cols = [("bear_mean_tokens", "tab:token-efficiency"), ("cpa_mean_tokens", "tab:token-efficiency"),
            ("static_tokens", "tab:token-efficiency"), ("bear_token_ratio", "tab:token-efficiency"),
            ("bear_novel_recall", "novel departments (text)"), ("cpa_novel_recall", "novel departments (text)"),
            ("bear_semantic_recall", "tab:semantic-advantage"), ("cpa_semantic_recall", "tab:semantic-advantage"),
            ("bear_persona_recall", "standard queries (text)"), ("bear_dept_recall", "standard queries (text)"),
            ("bear_safety_recall", "standard queries (text)"), ("bear_global_recall", "standard queries (text)"),
            ("bear_scope_violations", "standard queries (text)")]
    for n, r in P.items():
        for col, table in cols:
            if col not in r:
                continue

            def g(d):
                x = d.get(n)
                return v(float(x[col])) if x and x.get(col) not in (None, "") else None
            cell(table, f"N={n}", col, g(P), g(N), g(C))


def arms_metric(d, arm, metric):
    x = (d or {}).get("arms", {}).get(arm, {}).get("metrics", {}).get(metric)
    if not x:
        return None
    return v(x["mean"], *(x.get("ci") or [None, None]))


def reranker(pub: Path, stage: Path) -> None:
    for corpus in ("toolbench", "petsim"):
        for fname, step in ((f"reranker_composition_{corpus}.json", f"reranker_{corpus}"),
                            (f"framework_baseline_{corpus}.json", f"framework_{corpus}")):
            nf = files(stage, NEW, step, fname)
            if not nf or not (pub / fname).exists():
                continue
            po, ne = jload(pub / fname), jload(nf[0])
            for arm, a in po.get("arms", {}).items():
                for metric in a.get("metrics", {}):
                    if metric not in ("recall", "f1", "strict_f1", "relaxed_f1", "ndcg"):
                        continue
                    cell("tab:reranker", f"{corpus}: {a.get('label', arm)}", metric,
                         arms_metric(po, arm, metric), arms_metric(ne, arm, metric))
            for cname, c in po.get("contrasts", {}).items():
                nc = ne.get("contrasts", {}).get(cname)
                cell("tab:reranker contrasts", f"{corpus}: {cname}", c.get("metric", "?"),
                     v(c.get("delta"), *(c.get("ci") or [None, None])),
                     v(nc.get("delta"), *(nc.get("ci") or [None, None])) if nc else None,
                     d_v0110=c.get("cohens_d_paired"), d_new=(nc or {}).get("cohens_d_paired"))


def transfer(pub: Path, stage: Path) -> None:
    for corpus in ("toolbench", "metatool"):
        fname = f"backend_transfer_{corpus}_toolbench_ir_bert_based_uncased.json"
        nf = files(stage, NEW, f"transfer_{corpus}", fname)
        if not nf:
            continue
        po, ne = jload(pub / fname), jload(nf[0])
        for m in ("recall", "ndcg", "f1"):
            x, y = po["metrics"].get(m), ne.get("metrics", {}).get(m)
            cell("tab:transfer", f"ToolBench-IR on {corpus}", f"{m}@5",
                 v(x["mean"], *x["ci"]) if x else None, v(y["mean"], *y["ci"]) if y else None)
    nf = files(stage, NEW, "toolllm_both", "toolbench_toolllm_fixed.json")
    if not nf:
        return
    po, ne = jload(pub / "toolbench_toolllm_fixed.json"), jload(nf[0])
    for c in po["conditions"]:
        nc = next((x for x in ne.get("conditions", []) if x["label"] == c["label"]), None)
        for m in ("recall", "ndcg"):
            x, y = c["metrics"].get(m), (nc or {}).get("metrics", {}).get(m)
            cell("ToolBench-IR + governance (Sec. 6.3 text)", c["label"], f"{m}@5",
                 v(x["mean"], *x["ci"]) if x else None, v(y["mean"], *y["ci"]) if y else None)


def e2e_lists(lists: list[Path], pub_e2e: Path) -> dict:
    """Top-5 lists of the e2e corpus: 0.4.2 vs regenerated 0.1.10 vs the
    published per-query arrays, and which single switch gives back the 0.1.10
    list (lists_v042L_<switch>, BM25 only)."""
    pub = {s["condition"]: s for s in jload(pub_e2e)["scores"]}
    out = {}

    def arrays_vs_pub(src, name):
        ps = pub.get(name)
        if not ps:
            return None
        return {m: int(np.sum(np.abs(np.asarray(src[f"_{m}_scores"]) - np.asarray(ps[f"_{m}_scores"])) > 1e-12))
                for m in ("recall", "precision", "ndcg")}
    for root in lists:
        for p in sorted((root / f"lists_{NEW}" / "e2e").glob("*.json")):
            if p.name.endswith(".provenance.json"):
                continue
            a = jload(p)
            name = a["condition"]
            rec = {"n_queries": a["n_queries"], "backend": a.get("backend"), "source": str(p),
                   f"recall5_{NEW}": float(np.mean(a["_recall_scores"])),
                   f"{NEW}_vs_published_arrays": arrays_vs_pub(a, name)}
            q = root / "lists_v0110" / "e2e" / p.name
            if q.exists():
                b = jload(q)
                rec["ordered_diff_vs_v0110"] = sum(1 for x, y in zip(a["ids"], b["ids"]) if x != y)
                rec["set_diff_vs_v0110"] = sum(1 for x, y in zip(a["ids"], b["ids"]) if set(x) != set(y))
                rec["v0110_regen_vs_published_arrays"] = arrays_vs_pub(b, name)
                restored = {}
                for sw in SWITCHES:
                    r = next((x / f"lists_{NEW}L_{sw}" / "e2e" / p.name for x in lists
                              if (x / f"lists_{NEW}L_{sw}" / "e2e" / p.name).exists()), None)
                    if r is not None:
                        c = jload(r)
                        restored[sw] = sum(1 for x, y in zip(c["ids"], b["ids"]) if x != y)
                if restored:
                    rec["ordered_diff_vs_v0110_under_switch"] = restored
                    rec["restored_by"] = [sw for sw, n in restored.items() if n == 0]
            out[name] = rec
    return out


# ---------------------------------------------------------------------------

def fmt(x):
    if not x:
        return "n/a"
    s = f"{x['pt']:.3f}"
    if x.get("lo") is not None:
        s += f" [{x['lo']:.3f}, {x['hi']:.3f}]"
    return s


def markdown(extra) -> str:
    out = []
    counts = {}
    for c in CELLS:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    out.append("Status counts: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())))
    by = {}
    for c in CELLS:
        by.setdefault(c["table"], []).append(c)
    for t, cs in by.items():
        out.append(f"\n#### {t}\n")
        out.append("| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |")
        out.append("|---|---|---|---|---|---|---|---|")
        for c in cs:
            ctrl = ("reproduces" if c.get("ctrl_reproduces_published") else
                    (f"{c['ctrl_v0110']['pt']:.3f}" if c.get("ctrl_v0110") else ""))
            rb = ""
            if "restored_by" in c:
                rb = ", ".join(c["restored_by"]) or ("none (all: not restored)" if c.get("not_restored_by_all") else "none")
            nd = f" ({c['n_query_diff']} q)" if c.get("n_query_diff") else ""
            d = c.get("delta")
            out.append(f"| {c['row']} | {c['col']} | {fmt(c['v0110'])} | {fmt(c[NEW])} | "
                       f"{'' if d is None else f'{d:+.4f}'} | {c['status']}{nd} | {ctrl} | {rb} |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", required=True)
    ap.add_argument("--pub-e2e", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--lists", nargs="+", required=True,
                    help="results/wp0 folders of the clones (lists_v042/, lists_v0110/, lists_v042L_<sw>/)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pub, stage = Path(a.pub), Path(a.stage)
    extra, errors = {}, {}
    for name, fn in (("external", lambda: external(pub, stage)),
                     ("backend_comparison", lambda: backend_comparison(pub, stage)),
                     ("gov_ablation", lambda: gov_ablation(pub, stage)),
                     ("decomposed", lambda: per_backend_rows(pub, stage, "governance_decomposed", "decomposed",
                                                             "tab:decomposed-ablation", "condition",
                                                             lambda r: r["label"])),
                     ("alpha", lambda: per_backend_rows(pub, stage, "alpha_sweep", "alpha_sweep",
                                                        "tab:alpha-sweep", "alpha",
                                                        lambda r: f"alpha={r['alpha']:.2f}")),
                     ("retrieval", lambda: retrieval(pub, stage)),
                     ("table4", lambda: table4(pub, stage)),
                     ("cpa", lambda: cpa(pub, stage)),
                     ("tool_scaling", lambda: tool_scaling(pub, stage)),
                     ("reranker", lambda: reranker(pub, stage)),
                     ("transfer", lambda: transfer(pub, stage)),
                     ("e2e_lists", lambda: e2e_lists([Path(x) for x in a.lists], Path(a.pub_e2e)))):
        try:
            r = fn()
            if r:
                extra[name] = r
        except Exception as exc:  # noqa: BLE001
            errors[name] = repr(exc)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.json").write_text(json.dumps({"cells": CELLS, **extra, "errors": errors}, indent=1,
                                                 default=float), encoding="utf-8")
    (out / "compare.md").write_text(markdown(extra), encoding="utf-8")
    print(f"{len(CELLS)} cells; errors: {errors}")


if __name__ == "__main__":
    main()
