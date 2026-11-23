#!/usr/bin/env python3
"""Build one numbers file from your runs: every manuscript result with its source file.

    python reproduce/collect.py [--root DIR] [--committed DIR] [--out DIR] [--only ID ...]

--root       the repo-shaped tree of your outputs (default $REPRO_OUT/assembled,
             made by 70_assemble.sh)
--committed  this checkout (default: the repo that holds this script). Used only
             for items with status "Scott, previous version" (July and August
             runs that the revision keeps), and only when --root has no rerun of
             them. Items that need Scott's run are read from --root and nothing else.
--out        where numbers.json and numbers.md go (default $REPRO_OUT/numbers)

The items, their status and their files are in reproduce/lib/paper_map.py, with
the same ids as reproduce/MANIFEST.md. For each item the numbers file lists:
  - every source file, whether it was found, where, and its sha256
  - the numbers: name, value, 95% CI where the file gives one, the source file and
    the JSON path, or "computed" with the formula
  - the text blocks (output tables and logs) the item's numbers are printed in
  - what is missing
Computed numbers (the gap the numbers pass closed by hand):
  - governed minus ungated per backend (Tables 6, 8, 9): delta, paired t, p and
    Cohen's d = mean(diff) / sd(diff, ddof=1), from the per-query arrays, as
    eval_toolbench.py and the numbers pass computed them
  - cross-backend d against BEAR+BGE on ToolBench (Section 4.2 text)
  - Table 10 and the Section 4.2 text: governed vs ungated for the five backends, every row and
    the hash row against the monolithic row, and the run with the first 128 schemas
  - Supplement Table S1: the Gemma cells from the per-query scores, with McNemar exact tests
  - tab:semantic-advantage (T14, removed from the manuscript): McNemar exact p, Cohen's h and the Clopper-Pearson bound for CPA

Exit code 0 if every "needs Scott's run" item was found complete, 1 otherwise
(the files are still written). Needs numpy and scipy (the kit's venv has them).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import paper_map as pm  # noqa: E402

STATUS_TEXT = {"b": "needs Scott's run", "a": "Scott, previous version", "static": "static"}
SKIP_KEY = re.compile(r"^_|(^|_)(provenance|elapsed|seconds|s|latency|ms|time|times|timing|utc|date|wall|duration|"
                      r"host|hostname|user|path|paths|dir|argv|cwd|pid|vram|peak|fills|embedded|written|timestamp|"
                      r"versions|hooks|environment|settings|server|load|request|file)(_|$)", re.I)
MAX_NUMBERS_PER_FILE = 4000
MAX_TEXT_LINES = 600


class Ctx:
    def __init__(self, root: Path, committed: Path):
        self.root, self.committed = root, committed
        self.cache: dict = {}

    def find(self, rel: str, status: str) -> tuple[Path | None, str]:
        """The file for rel, and where it came from."""
        for base, label in ((self.root, "your run"),) + (((self.committed, "committed (previous version)"),)
                                                          if status == "a" else ()):
            for cand in (base / rel, base / (rel + ".gz")):
                if cand.exists():
                    return cand, label
        return None, ""

    def json(self, p: Path):
        if p not in self.cache:
            op = gzip.open if p.suffix == ".gz" else open
            with op(p, "rt", encoding="utf-8") as f:
                self.cache[p] = json.load(f)
        return self.cache[p]

    def text(self, p: Path) -> str:
        op = gzip.open if p.suffix == ".gz" else open
        with op(p, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def num(name, value, source, where, ci=None, **extra) -> dict:
    d = {"name": name, "value": value, "source": source, "where": where}
    if ci is not None:
        d["ci95"] = [ci[0], ci[1]]
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# Generic extractors
# ---------------------------------------------------------------------------

def label_of(o) -> str | None:
    if isinstance(o, dict):
        for k in ("name", "label", "condition", "config", "backend", "arm", "row", "variant", "alpha", "k"):
            if k in o and isinstance(o[k], (str, int, float)):
                return f"{k}={o[k]}"
    return None


def flatten(o, path: str, out: list, source: str) -> None:
    if len(out) >= MAX_NUMBERS_PER_FILE:
        return
    if isinstance(o, dict):
        ci = None
        if {"point_estimate", "ci_lower", "ci_upper"} <= set(o):
            ci = (o["ci_lower"], o["ci_upper"])
            out.append(num(path, o["point_estimate"], source, path, ci))
            for k in ("n", "std"):
                if k in o:
                    out.append(num(f"{path}/{k}", o[k], source, f"{path}/{k}"))
            return
        for k, v in o.items():
            if SKIP_KEY.search(str(k)) or str(k).startswith("_"):
                continue
            flatten(v, f"{path}/{k}", out, source)
    elif isinstance(o, list):
        if len(o) > 20 and all(isinstance(x, (int, float)) for x in o):
            return  # per-query array: the summary numbers are elsewhere in the file
        if len(o) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in o) \
                and path.lower().endswith(("ci", "ci95", "/ci")):
            out.append(num(path, list(o), source, path))
            return
        for i, x in enumerate(o):
            lab = label_of(x)
            flatten(x, f"{path}[{lab or i}]", out, source)
    elif isinstance(o, bool):
        return
    elif isinstance(o, (int, float)):
        out.append(num(path, o, source, path))


def ex_flatten(ctx, it, a, res):
    p, where = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    d = ctx.json(p)
    if a.get("under"):
        if a["under"] not in d:
            res["missing"].append(f"{a['path']} (key {a['under']})")
            return
        d = {a["under"]: d[a["under"]]}
    before = len(res["numbers"])
    flatten(d, "", res["numbers"], a["path"])
    if len(res["numbers"]) - before >= MAX_NUMBERS_PER_FILE:
        res["notes"].append(f"{a['path']}: only the first {MAX_NUMBERS_PER_FILE} numbers are listed")


def ex_text(ctx, it, a, res):
    p, where = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    lines = ctx.text(p).splitlines()
    if a.get("grep"):
        rx = re.compile(a["grep"])
        lines = [ln for ln in lines if rx.search(ln)]
    cut = len(lines) > MAX_TEXT_LINES
    res["text"].append({"source": a["path"], "lines": lines[:MAX_TEXT_LINES],
                        "note": f"first {MAX_TEXT_LINES} of {len(lines)} lines" if cut else ""})


def ex_csv(ctx, it, a, res):
    p, where = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    timing = re.compile(r"(ms|latency|time|seconds|build)", re.I)
    for i, r in enumerate(rows):
        key = next(iter(r.values()))
        for k, v in r.items():
            if timing.search(k):
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            res["numbers"].append(num(f"row {i} ({key}) {k}", x, a["path"], f"row {i}, column {k}"))


# ---------------------------------------------------------------------------
# Computed extractors
# ---------------------------------------------------------------------------

def paired(a, b) -> dict:
    import numpy as np
    from scipy import stats
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    sd = d.std(ddof=1)
    t, p = stats.ttest_rel(a, b) if sd > 0 else (float("nan"), float("nan"))
    w = float(stats.wilcoxon(d).pvalue) if (d != 0).any() else float("nan")
    return {"delta": float(d.mean()), "t": float(t), "p": float(p), "d": float(d.mean() / sd) if sd > 0 else float("nan"),
            "wilcoxon_p": w, "n": int(len(d))}


def tb_row(ctx, it, rel, bench, cond, res):
    p, _ = ctx.find(rel, it["status"])
    if p is None:
        res["missing"].append(rel)
        return None
    row = ctx.json(p).get(bench, {}).get(cond)
    if row is None:
        res["missing"].append(f"{rel}: {bench} / {cond}")
    return row


def ex_toolbench_table(ctx, it, a, res):
    bench = a["bench"]
    for b in pm.BACKENDS:
        gf, uf = pm.row_files(bench, b)
        g = tb_row(ctx, it, gf, bench, f"BEAR+{b} (gov)", res)
        u = tb_row(ctx, it, uf, bench, f"{b} (no gov)", res)
        for row, cond, f in ((g, "gov", gf), (u, "no gov", uf)):
            if row is None:
                continue
            for m, lab in (("recall", "Recall@5"), ("ndcg", "NDCG@5")):
                c = row["cis"][m]
                res["numbers"].append(num(f"{bench} {b} ({cond}) {lab}", c["point_estimate"], f,
                                          f"{bench}/{'BEAR+' + b + ' (gov)' if cond == 'gov' else b + ' (no gov)'}/cis/{m}",
                                          (c["ci_lower"], c["ci_upper"])))
        if g is not None and u is not None:
            for m, lab in (("recall", "Recall@5"), ("ndcg", "NDCG@5")):
                s = paired(g["metrics"][m], u["metrics"][m])
                res["numbers"].append(num(f"{bench} {b} governed minus ungated {lab}", s["delta"], f"{gf} and {uf}",
                                          "computed: mean(gov - ungated) over queries", None,
                                          t=s["t"], p=s["p"], d=s["d"], wilcoxon_p=s["wilcoxon_p"], n=s["n"]))
                ug = u["cis"][m]["point_estimate"]
                if ug:
                    res["numbers"].append(num(f"{bench} {b} relative gain {lab}", s["delta"] / ug, f"{gf} and {uf}",
                                              "computed: delta / ungated mean"))


def ex_cross_backend(ctx, it, a, res):
    bench = a["bench"]
    ref_f, _ = pm.row_files(bench, "BGE")
    ref = tb_row(ctx, it, ref_f, bench, "BEAR+BGE (gov)", res)
    if ref is None:
        return
    for b in pm.BACKENDS:
        if b == "BGE":
            continue
        gf, _ = pm.row_files(bench, b)
        g = tb_row(ctx, it, gf, bench, f"BEAR+{b} (gov)", res)
        if g is None:
            continue
        s = paired(g["metrics"]["recall"], ref["metrics"]["recall"])
        res["numbers"].append(num(f"{bench} BEAR+{b} (gov) minus BEAR+BGE (gov) Recall@5", s["delta"],
                                  f"{gf} and {ref_f}", "computed: paired over queries", None, t=s["t"], p=s["p"], d=s["d"]))
    bf, _ = pm.row_files(bench, "BM25")
    g = tb_row(ctx, it, bf, bench, "BEAR+BM25 (gov)", res)
    u = tb_row(ctx, it, ref_f, bench, "BGE (no gov)", res)
    if g is not None and u is not None:
        s = paired(g["metrics"]["recall"], u["metrics"]["recall"])
        res["numbers"].append(num(f"{bench} BEAR+BM25 (gov) minus BGE (no gov) Recall@5", s["delta"],
                                  f"{bf} and {ref_f}", "computed: paired over queries", None, t=s["t"], p=s["p"], d=s["d"]))


def ex_mand_only(ctx, it, a, res):
    srcs = [("BGE", pm.tb("tb_bge")), ("BM25", pm.tb("tb_bm25")), ("Hash", pm.tb("tb_hash")),
            ("BGE-M3", pm.tb("tb_bgem3_mand")), ("Qwen3-0.6B", pm.tb("tb_qwen06_mand")),
            ("Qwen3-4B", pm.tb("tb_qwen4b_mand"))]
    for b, rel in srcs:
        p, _ = ctx.find(rel, it["status"])
        if p is None:
            res["missing"].append(rel)
            continue
        d = ctx.json(p)
        for bench in ("ToolBench", "MetaTool", "MetaTool+Tags", "MetaTool+QueryTags-top5"):
            row = d.get(bench, {}).get(f"BEAR+{b} (mand-only)")
            if row:
                c = row["cis"]["recall"]
                res["numbers"].append(num(f"{bench} BEAR+{b} (mand-only) Recall@5", c["point_estimate"], rel,
                                          f"{bench}/BEAR+{b} (mand-only)/cis/recall", (c["ci_lower"], c["ci_upper"])))


E2E_ROWS = {"BEAR+Qwen3-0.6B (gov)": "bear_qwen3-0.6b_gov", "BEAR+Qwen3-4B (gov)": "bear_qwen3-4b_gov",
            "BEAR+BGE (gov)": "bear_bge_gov", "BEAR+BGE-M3 (gov)": "bear_bge-m3_gov",
            "BEAR+BM25 (gov)": "bear_bm25_gov", "Qwen3-0.6B (no gov)": "qwen3-0.6b_no_gov",
            "Qwen3-4B (no gov)": "qwen3-4b_no_gov", "BGE-M3 (no gov)": "bge-m3_no_gov",
            "BGE (no gov)": "bge_no_gov", "BM25 (no gov)": "bm25_no_gov"}
E2E_BACKENDS = ("BGE", "BGE-M3", "Qwen3-0.6B", "Qwen3-4B", "BM25")
HASH_ROW = "BEAR+Hash (gov)"


def e2e_row_numbers(cond, r, rel, res):
    for m in ("tool", "exact"):
        c = r[f"{m}_ci"]
        res["numbers"].append(num(f"{cond} {m} accuracy (rerun on 0.4.2)", r[f"{m}_accuracy"], rel,
                                  f"{m}_accuracy", (c["ci_lower"], c["ci_upper"])))
    for m in ("recall", "ndcg"):
        res["numbers"].append(num(f"{cond} retrieval {m}@5 of its list", r[m], rel, m))
    res["numbers"].append(num(f"{cond} LLM errors", r.get("llm_errors"), rel, "llm_errors"))


def ex_e2e_rerun(ctx, it, a, res):
    if a.get("rows") == "hash":
        rel = f"{pm.E2E_HASH}/bear_hash_gov.scores.json"
        p, _ = ctx.find(rel, "b")
        if p is None:
            res["missing"].append(rel)
        else:
            e2e_row_numbers(HASH_ROW, ctx.json(p), rel, res)
        return
    rows = {}
    for cond, slug in E2E_ROWS.items():
        rel = f"{pm.E2E}/{slug}.scores.json"
        p, _ = ctx.find(rel, "b")
        if p is None:
            res["missing"].append(rel)
            continue
        rows[cond] = ctx.json(p)
        e2e_row_numbers(cond, rows[cond], rel, res)
    for b in E2E_BACKENDS:
        g, u = f"BEAR+{b} (gov)", f"{b} (no gov)"
        if g in rows and u in rows:
            for m in ("tool", "exact"):
                s = paired(rows[g][f"_{m}_scores"], rows[u][f"_{m}_scores"])
                res["numbers"].append(num(f"{g} minus {u}, {m} accuracy", s["delta"], f"{pm.E2E}/*.scores.json",
                                          "computed: paired over queries", None, t=s["t"], p=s["p"], d=s["d"]))


def ex_prompt_size(ctx, it, a, res):
    rel = "results/v042/wp4/wp4_token_efficiency.json"
    p, _ = ctx.find(rel, "b")
    if p is None:
        res["missing"].append(rel)
    else:
        d = ctx.json(p)
        for k in ("toolbench_monolithic", "mistral_tokenizer", "toolbench_k5_mistral_nemo_chat_tokens"):
            if k in d:
                flatten(d[k], k, res["numbers"], rel)
    rel = "results/v042/e2e_checks/e2e_prompt_tokens.json"
    p, _ = ctx.find(rel, "b")
    if p is None:
        res["missing"].append(rel)
    else:
        d = ctx.json(p)
        for k in ("retrieval_bound_any_5_tools", "monolithic", "gemma_monolithic"):
            if k in d:
                flatten(d[k], k, res["numbers"], rel)


def ex_semantic_stats(ctx, it, a, res):
    from scipy import stats
    p, _ = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        try:
            n = int(float(r["num_semantic_queries"]))
            p1, p2 = float(r["bear_semantic_recall"]), float(r["cpa_semantic_recall"])
        except (KeyError, ValueError):
            res["notes"].append(f"{a['path']}: no semantic columns in a row")
            continue
        key = next(iter(r.values()))
        k1, k2 = round(p1 * n), round(p2 * n)
        h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
        res["numbers"].append(num(f"row {key}: Cohen's h, BEAR vs CPA semantic recall", h, a["path"],
                                  "computed: 2 asin(sqrt p1) - 2 asin(sqrt p2)"))
        if k2 == 0 or k1 == n:
            disc = k1 if k2 == 0 else n - k2
            pv = min(1.0, 2 * 0.5 ** disc)
            res["numbers"].append(num(f"row {key}: McNemar exact p", pv, a["path"],
                                      f"computed: 2 x 0.5^{disc} (one side all correct or all wrong)"))
        else:
            res["notes"].append(f"row {key}: McNemar needs per-query outcomes, which the CSV does not hold")
        ub = float(stats.beta.ppf(0.975, k2 + 1, n - k2)) if k2 < n else 1.0
        res["numbers"].append(num(f"row {key}: CPA semantic recall, Clopper-Pearson 95% upper bound", ub, a["path"],
                                  f"computed: beta.ppf(0.975, {k2}+1, {n}-{k2})"))


# ---------------------------------------------------------------------------
# Numbers that no eval script writes, computed here from the committed or
# reproduced files (MANIFEST.md, "Closed by the kit").
# ---------------------------------------------------------------------------

def boot_paired(diff, n_boot: int = 10_000, seed: int = 42) -> tuple[float, float, float]:
    """Paired bootstrap of mean(diff): 95% CI and two-sided p (share of resampled means on the far side of 0)."""
    import numpy as np
    diff = np.asarray(diff, float)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(0, n_boot, 1000):
        idx = rng.integers(0, len(diff), size=(min(1000, n_boot - i), len(diff)))
        means[i:i + idx.shape[0]] = diff[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    p = 2 * min((means <= 0).mean(), (means >= 0).mean())
    return float(lo), float(hi), float(max(p, 1 / n_boot))


def mcnemar_exact(a, b) -> dict:
    import numpy as np
    from scipy import stats
    a, b = np.asarray(a) > 0, np.asarray(b) > 0
    n10, n01 = int(np.sum(a & ~b)), int(np.sum(~a & b))
    p = float(stats.binomtest(min(n10, n01), n10 + n01, 0.5).pvalue) if n10 + n01 else 1.0
    return {"n10": n10, "n01": n01, "p": p}


def e2e_sets(ctx, it, res, extras=True):
    """Your end-to-end reruns: the ten Table 10 rows, the hash row, the monolithic row and the run with 128 schemas."""
    out = {"rows": {}, "hash": None, "mono": None, "cap128": None}
    for cond, slug in E2E_ROWS.items():
        rel = f"{pm.E2E}/{slug}.scores.json"
        p, _ = ctx.find(rel, "b")
        if p is None:
            res["missing"].append(rel)
        else:
            out["rows"][cond] = ctx.json(p)
    rel = f"{pm.E2E_HASH}/bear_hash_gov.scores.json"
    p, _ = ctx.find(rel, "b") if extras else (None, "")
    if p is not None:
        out["hash"] = ctx.json(p)
    elif extras:
        res["missing"].append(rel)
    for key, rel in (("mono", f"{pm.MONO}/toolbench_e2e_scores_partial.json"),
                     ("cap128", f"{pm.CAP128}/toolbench_e2e_scores_partial.json"))[:2 if extras else 1]:
        p, _ = ctx.find(rel, "b")
        if p is None:
            res["missing"].append(rel)
            continue
        sc = {x["condition"]: x for x in ctx.json(p)["scores"]}
        out[key] = sc.get("Monolithic (all tools)")
        out[key + "_src"] = rel
    return out


def ex_e2e_text(ctx, it, a, res):
    import numpy as np
    S = e2e_sets(ctx, it, res, extras=a["part"] == "stats")  # the hash row and the 128-schema run are text only
    rows, mono = S["rows"], S["mono"]
    if mono is None:
        return
    msrc = S["mono_src"]
    if a["part"] == "stats":
        for m in ("tool", "exact"):
            res["numbers"].append(num(f"Monolithic {m} accuracy", float(np.mean(mono[f"_{m}_scores"])), msrc,
                                      f"_{m}_scores (mean)"))
        governed = [c for c in rows if c.startswith("BEAR+")]
        if governed:
            best = max(governed, key=lambda c: np.mean(rows[c]["_tool_scores"]))
            res["notes"].append(f"best governed system by tool accuracy: {best}")
        against = dict(rows)
        if S["hash"] is not None:
            against[HASH_ROW] = S["hash"]
        for cond, sc in against.items():
            src = f"{pm.E2E_HASH if cond == HASH_ROW else pm.E2E} and {msrc}"
            for m in ("tool", "exact"):
                x, y = np.asarray(sc[f"_{m}_scores"], float), np.asarray(mono[f"_{m}_scores"], float)
                st = paired(x, y)
                lo, hi, pb = boot_paired(x - y)
                res["numbers"].append(num(f"{cond} minus Monolithic, {m} accuracy", st["delta"], src,
                                          "computed: paired over queries", (lo, hi), t=st["t"], p=st["p"], d=st["d"],
                                          bootstrap_p=pb, ratio=float(x.mean() / y.mean()) if y.mean() else float("nan")))
        q06, q4 = rows.get("BEAR+Qwen3-0.6B (gov)"), rows.get("BEAR+Qwen3-4B (gov)")
        if q06 and q4:
            for m in ("tool", "exact"):
                mc = mcnemar_exact(q06[f"_{m}_scores"], q4[f"_{m}_scores"])
                st = paired(q06[f"_{m}_scores"], q4[f"_{m}_scores"])
                res["numbers"].append(num(f"BEAR+Qwen3-0.6B vs BEAR+Qwen3-4B (gov), {m} accuracy, McNemar exact p",
                                          mc["p"], pm.E2E, "computed: binomial test on discordant pairs",
                                          None, n10=mc["n10"], n01=mc["n01"], t=st["t"], p=st["p"]))
        cap = S["cap128"]
        if cap is not None:
            r = np.asarray(cap["_recall_scores"], float)
            present = r >= 1
            res["numbers"].append(num("cap-128 monolithic: queries with the gold tool in the prompt", int(present.sum()),
                                      S["cap128_src"], "count of _recall_scores == 1"))
            res["numbers"].append(num("cap-128 monolithic: share of queries with the gold tool", float(present.mean()),
                                      S["cap128_src"], "computed"))
            for m in ("tool", "exact"):
                v = np.asarray(cap[f"_{m}_scores"], float)[present]
                res["numbers"].append(num(f"cap-128 monolithic: {m} accuracy on those queries",
                                          float(v.mean()) if len(v) else float("nan"), S["cap128_src"], "computed"))
        res["numbers"].append(num("chance rate, one of 3,225 tools", 1 / 3225, "evals/data (corpus size)", "computed"))
        return
    # part "table10": numbers over Table 10 as printed
    src = f"{pm.E2E}, {msrc}"
    me = float(np.mean(mono["_exact_scores"]))
    ungov = {c: float(np.mean(v["_exact_scores"])) for c, v in rows.items() if c.endswith("(no gov)")}
    if ungov:
        res["numbers"].append(num("ungoverned exact accuracy, lowest", min(ungov.values()), src, "computed",
                                  None, which=min(ungov, key=ungov.get)))
        res["numbers"].append(num("ungoverned exact accuracy, highest", max(ungov.values()), src, "computed",
                                  None, which=max(ungov, key=ungov.get)))
    for b in E2E_BACKENDS:
        g, u = rows.get(f"BEAR+{b} (gov)"), rows.get(f"{b} (no gov)")
        if not (g and u):
            continue
        ge, ue = float(np.mean(g["_exact_scores"])), float(np.mean(u["_exact_scores"]))
        res["numbers"].append(num(f"{b}: share of the monolithic-to-governed distance closed by ungoverned retrieval (exact)",
                                  (ue - me) / (ge - me) if ge != me else float("nan"), src,
                                  "computed: (ungov - mono) / (gov - mono)"))
        for m in ("tool", "exact"):
            st = paired(g[f"_{m}_scores"], u[f"_{m}_scores"])
            res["numbers"].append(num(f"{b}: governed minus ungoverned, {m} accuracy (Table 10 rows)", st["delta"], src,
                                      "computed: paired over queries", None, t=st["t"], p=st["p"], d=st["d"]))


S1_CELLS = {  # cell -> (run of pm.s1_file, key of per_query_correct, key of response_health)
    "monolithic under the scaffold": ("scaffold", "mono_react", "Monolithic + ReAct"),
    "governed under the scaffold": ("scaffold", "bear_react", "BEAR retrieval + ReAct"),
    "governed single-turn (scaffold batch)": ("scaffold", "bear_single", "BEAR retrieval + single-turn (reference)"),
    "monolithic, reasoning channel off": ("mono-nothink-full", "mono_react", "Monolithic + ReAct"),
    "monolithic with native reasoning": ("mono-think-full", "mono_react", "Monolithic + ReAct"),
    "governed single-turn": ("bearsingle-nothink-full", "bear_single", "BEAR retrieval + single-turn (reference)"),
    "governed with native reasoning": ("bear-full", "bear_react", "BEAR retrieval + ReAct"),
}
S1_TESTS = [  # (first cell, second cell): the second minus the first
    ("governed single-turn (scaffold batch)", "governed under the scaffold"),
    ("monolithic under the scaffold", "governed under the scaffold"),
    ("monolithic, reasoning channel off", "monolithic with native reasoning"),
    ("governed single-turn", "governed with native reasoning"),
    ("monolithic with native reasoning", "governed with native reasoning"),
]


def ex_s1_grid(ctx, it, a, res):
    """Supplement Table S1, the Gemma columns: each cell from the per-query scores, its empty answers,
    and McNemar's exact test for the paired conditions the text compares."""
    import numpy as np
    for model in ("12b", "31b"):
        cells = {}
        for cell, (run, key, health) in S1_CELLS.items():
            rel = pm.s1_file(model, run)
            p, _ = ctx.find(rel, it["status"])
            if p is None:
                continue  # the flatten entry of the same file already reports it as missing
            d = ctx.json(p)
            v = (d.get("per_query_correct") or {}).get(key)
            if v is None:
                res["missing"].append(f"{rel} (per_query_correct/{key})")
                continue
            cells[cell] = np.asarray(v, float)
            h = (d.get("response_health") or {}).get(health) or {}
            res["numbers"].append(num(f"Gemma 4 {model.upper()}, {cell}: accuracy", float(cells[cell].mean()), rel,
                                      f"per_query_correct/{key} (mean)", None, n=int(len(cells[cell])),
                                      n_empty=h.get("n_empty"), n_unparsed=h.get("n_unparsed"),
                                      accuracy_when_answered=h.get("accuracy_when_answered")))
        for x, y in S1_TESTS:
            if x in cells and y in cells:
                mc = mcnemar_exact(cells[x], cells[y])
                res["numbers"].append(num(f"Gemma 4 {model.upper()}: {y} minus {x}", float(cells[y].mean() - cells[x].mean()),
                                          f"{pm.E2E_LONG}/g{model[:2]}-*", "computed: McNemar exact on the per-query scores",
                                          None, p=mc["p"], n10=mc["n10"], n01=mc["n01"]))


def ex_transfer_table(ctx, it, a, res):
    for corpus, bench in (("toolbench", "ToolBench"), ("metatool", "MetaTool")):
        rel = f"{pm.V}/transfer_{corpus}/backend_transfer_{corpus}_toolbench_ir_bert_based_uncased.json"
        p, _ = ctx.find(rel, it["status"])
        ref = {}
        if p is None:
            res["missing"].append(rel)
        else:
            d = ctx.json(p)
            r = d["metrics"]["recall"]
            pt = r.get("point_estimate", r.get("mean"))
            ci = (r["ci_lower"], r["ci_upper"]) if "ci_lower" in r else None
            res["numbers"].append(num(f"{bench}: ToolBench-IR (fine-tuned) Recall@5", pt, rel, "metrics/recall", ci))
            ref = d.get("offshelf_reference_recall", {})
        for b in ("BGE", "BGE-M3", "Qwen3-0.6B", "Qwen3-4B", "Nemotron", "BM25"):
            _, uf = pm.row_files(bench, b)
            row = tb_row(ctx, it, uf, bench, f"{b} (no gov)", res)
            if row is None:
                continue
            c = row["cis"]["recall"]
            extra = {}
            if b in ref:
                extra["hardcoded_in_eval_backend_transfer"] = ref[b]
                if round(ref[b], 3) != round(c["point_estimate"], 3):
                    res["notes"].append(f"{bench} {b}: the hardcoded off-the-shelf value {ref[b]} differs from the "
                                        f"0.4.2 file ({c['point_estimate']:.4f}). tab:transfer should print the file's value.")
            res["numbers"].append(num(f"{bench}: {b} (no gov) Recall@5, off-the-shelf row", c["point_estimate"], uf,
                                      f"{bench}/{b} (no gov)/cis/recall", (c["ci_lower"], c["ci_upper"]), **extra))


def last_attempt(text: str) -> str:
    i = text.rfind("### ================ attempt")
    return text[i:] if i >= 0 else text


def ex_retrieval_log(ctx, it, a, res):
    p, _ = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    cfg = None
    found = 0
    metric = re.compile(r"([A-Za-z0-9]+@\d+)=([\d.]+) \[([\d.]+), ([\d.]+)\]")
    for ln in last_attempt(ctx.text(p)).splitlines():
        h = re.match(r"^(\S.*\(\$\\alpha\s*=\s*[\d.]+\$\)):\s*$", ln)
        if h:
            cfg = h.group(1).replace("$\\alpha", "alpha").replace("$", "")
            continue
        m = re.match(r"^\s+(Strict|Relaxed):\s+(.*)$", ln)
        if m and cfg:
            for k, v, lo, hi in metric.findall(m.group(2)):
                res["numbers"].append(num(f"{a['label']}: {cfg}, {m.group(1)} {k}", float(v), a["path"],
                                          "log line (last attempt)", (float(lo), float(hi))))
                found += 1
    if not found:
        res["notes"].append(f"{a['path']}: no metric lines found")


def ex_tool_scaling_log(ctx, it, a, res):
    p, _ = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    t = last_attempt(ctx.text(p))
    src = a["path"]
    for size, pr, plo, phi, rc, rlo, rhi, leak, scen in re.findall(
            r"Corpus size:\s*(\d+) tools \| Precision: ([\d.]+) \[([\d.]+), ([\d.]+)\] \| Recall: ([\d.]+) "
            r"\[([\d.]+), ([\d.]+)\] \| No cross-domain leaks: (\w+) \| Scenarios: (\d+)", t):
        res["numbers"].append(num(f"tool scaling: {size} tools, precision", float(pr), src, "log line", (float(plo), float(phi))))
        res["numbers"].append(num(f"tool scaling: {size} tools, recall", float(rc), src, "log line", (float(rlo), float(rhi))))
        res["numbers"].append(num(f"tool scaling: {size} tools, scenarios", int(scen), src, "log line", None,
                                  no_cross_domain_leaks=leak))
    for name, k, tok, sav in re.findall(r"^\s+(\S[^.]*?)\.{2,}\s*(\d+) tools \|\s*(\d+) tokens \| savings: (\d+)%", t, re.M):
        res["numbers"].append(num(f"token savings: {name}, tools", int(k), src, "log line"))
        res["numbers"].append(num(f"token savings: {name}, tokens", int(tok), src, "log line"))
        res["numbers"].append(num(f"token savings: {name}, savings %", int(sav), src, "log line"))
    m = re.search(r"All-tools baseline: (\d+) tools, (\d+) tokens", t)
    if m:
        res["numbers"].append(num("token savings: all-tools baseline, tokens", int(m.group(2)), src, "log line",
                                  None, tools=int(m.group(1))))
    m = re.search(r"Average token savings: (\d+)%", t)
    if m:
        res["numbers"].append(num("token savings: average savings %", int(m.group(1)), src, "log line"))


def ex_novel_mcnemar(ctx, it, a, res):
    """Novel-department recall, BEAR vs CPA. McNemar as evals/compute_petsim_stats.py computes it
    (counts from the rates, maximum concordance, continuity-corrected chi-square), here from the CSV."""
    from scipy import stats
    p, _ = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        n = int(float(r["num_novel_queries"]))
        br, cr = float(r["bear_novel_recall"]), float(r["cpa_novel_recall"])
        bk, ck = round(br * n), round(cr * n)
        ov = min(bk, ck)
        b, c = bk - ov, ck - ov
        if b + c:
            chi2 = (abs(b - c) - 1) ** 2 / (b + c)
            pv = float(1 - stats.chi2.cdf(chi2, df=1))
        else:
            chi2, pv = float("nan"), float("nan")
        h = 2 * math.asin(math.sqrt(br)) - 2 * math.asin(math.sqrt(max(cr, 1e-9)))
        res["numbers"].append(num(f"N={r['num_agents']}: novel recall BEAR {br:.3f} vs CPA {cr:.3f}, McNemar p", pv,
                                  a["path"], "computed as evals/compute_petsim_stats.py (max concordance, continuity)",
                                  None, n=n, b=b, c=c, chi2=chi2, cohens_h=h))


def ex_latency(ctx, it, a, res):
    """Machine-dependent timings, listed so the text can quote your machine's values."""
    p, _ = ctx.find(a["path"], it["status"])
    if p is None:
        res["missing"].append(a["path"])
        return
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for col in a["columns"]:
            if col in r:
                res["numbers"].append(num(f"N={r['num_agents']}: {col} (timing, machine-dependent)", float(r[col]),
                                          a["path"], f"column {col}"))


EXTRACTORS = {"flatten": ex_flatten, "text": ex_text, "csv": ex_csv, "toolbench_table": ex_toolbench_table,
              "cross_backend": ex_cross_backend, "mand_only": ex_mand_only, "e2e_rerun": ex_e2e_rerun,
              "s1_grid": ex_s1_grid, "prompt_size": ex_prompt_size, "semantic_stats": ex_semantic_stats,
              "e2e_text": ex_e2e_text, "transfer_table": ex_transfer_table, "retrieval_log": ex_retrieval_log,
              "tool_scaling_log": ex_tool_scaling_log, "novel_mcnemar": ex_novel_mcnemar, "latency": ex_latency}


# ---------------------------------------------------------------------------

def fmt(x) -> str:
    if isinstance(x, float):
        if math.isnan(x):
            return "nan"
        return f"{x:.4g}" if (abs(x) < 1e-3 and x != 0) or abs(x) >= 1e5 else f"{x:.4f}"
    return str(x)


def to_md(out: dict) -> str:
    L = [f"# Manuscript numbers from your runs", "",
         f"Made {out['generated_utc']} by reproduce/collect.py from `{out['root']}`.",
         "Items marked *needs Scott's run* come from that tree only. Items marked *Scott, previous version* "
         "come from it when 55_ reran them, else from the committed file of the July or August run.",
         "Ids match reproduce/MANIFEST.md.", "",
         "| Item | Status | Sources found | Numbers | Missing |", "|---|---|---|---|---|"]
    for r in out["items"]:
        L.append(f"| {r['id']} {r['label']} | {r['status_text']} | {sum(s['found'] for s in r['sources'])} of "
                 f"{len(r['sources'])} | {len(r['numbers'])} | {len(r['missing'])} |")
    for r in out["items"]:
        L += ["", f"## {r['id']}. {r['label']}", "", f"Status: **{r['status_text']}**. {r['what']}",
              f"Script: {r['script']}", ""]
        if r["sources"]:
            L += ["| Source | Found in | sha256 |", "|---|---|---|"]
            L += [f"| `{s['path']}` | {s['from'] or 'MISSING'} | {s.get('sha256', '')[:16]} |" for s in r["sources"]]
            L.append("")
        if r["numbers"]:
            L += ["| Number | Value | 95% CI | Source | Where | Test |", "|---|---|---|---|---|---|"]
            for n in r["numbers"]:
                ci = f"[{fmt(n['ci95'][0])}, {fmt(n['ci95'][1])}]" if "ci95" in n else ""
                test = ", ".join(f"{k} {fmt(n[k])}" for k in ("t", "p", "d", "wilcoxon_p", "bootstrap_p", "ratio", "n", "n10", "n01",
                                                       "b", "c", "cohens_h", "queries_changed", "which", "n_empty", "n_unparsed",
                                                       "accuracy_when_answered",
                                                       "hardcoded_in_eval_backend_transfer") if k in n)
                L.append(f"| {n['name']} | {fmt(n['value'])} | {ci} | `{n['source']}` | {n['where']} | {test} |")
            L.append("")
        for t in r["text"]:
            L += [f"From `{t['source']}`{(' (' + t['note'] + ')') if t['note'] else ''}:", "", "```"] + t["lines"] + ["```", ""]
        for m in r["missing"]:
            L.append(f"- MISSING: `{m}`")
        for n in r["notes"]:
            L.append(f"- note: {n}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    rep = Path(os.environ.get("REPRO_OUT", Path.home() / "tist-repro"))
    ap.add_argument("--root", type=Path, default=rep / "assembled")
    ap.add_argument("--committed", type=Path, default=HERE.parent)
    ap.add_argument("--out", type=Path, default=rep / "numbers")
    ap.add_argument("--only", nargs="*", default=None, help="item ids")
    a = ap.parse_args()
    if not a.root.is_dir():
        sys.exit(f"FAILED: collect: no folder {a.root} (run 70_assemble.sh first, or pass --root)")
    ctx = Ctx(a.root.resolve(), a.committed.resolve())
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "root": str(ctx.root), "committed": str(ctx.committed), "items": []}
    incomplete = []
    for it in pm.ITEMS:
        if a.only and it["id"] not in a.only:
            continue
        r = {k: it[k] for k in ("id", "label", "status", "what", "script")}
        r.update(status_text=STATUS_TEXT[it["status"]], sources=[], numbers=[], text=[], missing=[], notes=[])
        for rel in it["sources"]:
            p, where = ctx.find(rel, it["status"])
            s = {"path": rel, "found": p is not None, "from": where}
            if p is not None:
                s["sha256"] = sha256(p)
            r["sources"].append(s)
        for name, args in it["extract"]:
            try:
                EXTRACTORS[name](ctx, it, args, r)
            except Exception as exc:  # noqa: BLE001  report it in the item, keep going
                r["notes"].append(f"extractor {name} failed: {type(exc).__name__}: {exc}")
                r["missing"].append(f"(extractor {name} failed)")
        r["missing"] = list(dict.fromkeys(r["missing"]))
        if it["status"] == "b" and (r["missing"] or not all(s["found"] for s in r["sources"])):
            incomplete.append(it["id"])
        out["items"].append(r)
    out["incomplete_needs_scott"] = incomplete
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "numbers.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    (a.out / "numbers.md").write_text(to_md(out), encoding="utf-8")
    nn = sum(len(r["numbers"]) for r in out["items"])
    print(f"{len(out['items'])} items, {nn} numbers, written to {a.out}/numbers.json and numbers.md")
    if incomplete:
        print(f"FAILED: collect: items that need your run and are incomplete: {' '.join(incomplete)}")
        return 1
    print("OK: collect: every item that needs your run is complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
