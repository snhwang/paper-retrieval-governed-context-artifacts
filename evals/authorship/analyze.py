#!/usr/bin/env python3
"""Authorship ablation, step 4: agreement between the taggers, and the retrieval results under each.

    python evals/authorship/analyze.py --qwen-tags DIR --runs-root ROOT --out DIR
        [--toolbench-eval DIR/evaluate_toolbench_bge.json] [--sonnet-q4b-step tb_auth_q4b_sonnet]

Model-free, CPU only, no network. Writes authorship.json and authorship.md to --out.

1. Agreement (Sonnet 4.6 against the second tagger), through
   authorship_regenerate.py compare (per-tool Jaccard and exact set agreement,
   first-tag agreement, query-tag Jaccard, the gate-pass ceiling under the four
   tool/query tagger combinations, ToolBench category agreement and accuracy
   against the oracle category), plus Cohen's kappa per tag: for every tag of
   the closed vocabulary, its presence on each tool (or query) under the two
   taggers. Top-1 ToolBench categories get one kappa over the category labels.
2. Retrieval (MetaTool+Tags and MetaTool+QueryTags-top5, every backend that
   has both runs): governed Recall@5 and NDCG@5 under each tagger with 95%
   bootstrap CIs, the paired difference second tagger minus Sonnet, the
   governed-minus-ungated effect under each tagger, and the difference of the
   two effects. MetaTool+Tags pairs queries by position (the same 21,111 in the
   same order). MetaTool+QueryTags-top5 pairs them by (query, tools), since each
   tagger's file lists the queries in its own order and may lack failed items.
   Tests are a paired bootstrap (10,000 resamples, seed 42), the paired t-test
   and the Wilcoxon signed-rank test, with d = mean(diff) / sd(diff).
3. ToolBench inferred categories (Table 7, BGE): the oracle, Sonnet, second
   tagger and ungoverned arms from authorship_regenerate.py evaluate, if given.
The Sonnet runs are the WP0 step files the kit made (tb_bge, tb_bgem3, ...),
the second tagger's are the tb_auth_* steps of reproduce/65_authorship.sh.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
REPO = EVALS.parent
for _p in (str(REPO), str(EVALS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import authorship_regenerate as ar  # noqa: E402

# label -> (Sonnet step, second-tagger step). Qwen3-4B's Sonnet step is chosen at run time.
BACKENDS = {"BGE": ("tb_bge", "tb_auth_bge"), "BGE-M3": ("tb_bgem3", "tb_auth_bgem3"),
            "Qwen3-0.6B": ("tb_qwen06", "tb_auth_qwen06"), "Qwen3-4B": (None, "tb_auth_q4b"),
            "BM25": ("tb_bm25", "tb_auth_bm25"), "Hash": ("tb_hash", "tb_auth_hash"),
            "Nemotron": ("tb_nemotron", "tb_auth_nemotron")}
CONDITIONS = ("MetaTool+Tags", "MetaTool+QueryTags-top5")
N_BOOT, SEED = 10_000, 42


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def kappa_binary(a: list[bool], b: list[bool]) -> float:
    return ar._kappa(["1" if x else "0" for x in a], ["1" if x else "0" for x in b])


def boot_mean(x, n_boot=N_BOOT, seed=SEED):
    import numpy as np
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(0, n_boot, 500):
        idx = rng.integers(0, len(x), size=(min(500, n_boot - i), len(x)))
        means[i:i + idx.shape[0]] = x[idx].mean(axis=1)
    return means


def summary(x) -> dict:
    import numpy as np
    x = np.asarray(x, float)
    m = boot_mean(x)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return {"mean": float(x.mean()), "ci": [float(lo), float(hi)], "n": int(len(x))}


def paired(a, b) -> dict:
    import numpy as np
    from scipy import stats
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    m = boot_mean(d)
    lo, hi = np.percentile(m, [2.5, 97.5])
    p_boot = float(max(2 * min((m <= 0).mean(), (m >= 0).mean()), 1 / N_BOOT))
    sd = d.std(ddof=1) if len(d) > 1 else 0.0
    t_p = float(stats.ttest_rel(a, b).pvalue) if sd > 0 else float("nan")
    nz = d[d != 0]
    w_p = float(stats.wilcoxon(nz).pvalue) if len(nz) >= 5 else float("nan")
    return {"delta": float(d.mean()), "ci": [float(lo), float(hi)], "p_bootstrap": p_boot, "p_t": t_p,
            "p_wilcoxon": w_p, "d": float(d.mean() / sd) if sd > 0 else 0.0, "n": int(len(d)),
            "queries_changed": int((d != 0).sum())}


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def load_json(p: Path):
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def find_run(root: Path, step: str) -> Path | None:
    for name in (f"toolbench_eval_{step}.json", f"toolbench_eval_{step}.json.gz"):
        hits = sorted(root.rglob(name))
        if hits:
            return hits[0]
    return None


def qt_keys(path: Path) -> list[tuple]:
    """The query keys of a query-tag file in the order the loader reads it, with an occurrence index."""
    seen: Counter = Counter()
    out = []
    for e in json.loads(path.read_text(encoding="utf-8")):
        q, tools = e.get("query", "").strip(), e.get("tools", [])
        if q and tools:
            k = (q, tuple(sorted(tools)))
            out.append(k + (seen[k],))
            seen[k] += 1
    return out


def align(keys_a: list, keys_b: list) -> tuple[list[int], list[int]]:
    pos_b = {k: i for i, k in enumerate(keys_b)}
    ia, ib = [], []
    for i, k in enumerate(keys_a):
        j = pos_b.get(k)
        if j is not None:
            ia.append(i)
            ib.append(j)
    return ia, ib


# ---------------------------------------------------------------------------
# parts
# ---------------------------------------------------------------------------

def agreement(qwen_tags: Path, out: Path) -> dict:
    import argparse as _ap
    import metatool_tagging as mt
    cmp_path = out / "compare.json"
    if cmp_path.exists():
        cmp_path.unlink()
    with ar.AnthropicToOpenAIShim(ar.DEFAULT_BASE_URL, transport=ar.deny_all):
        ar.compare(_ap.Namespace(regen_dir=str(qwen_tags), output=str(cmp_path)))
    rep = json.loads(cmp_path.read_text(encoding="utf-8"))
    extra: dict = {}
    s_tool = json.loads(ar.SONNET_FILES["tool_tags"].read_text(encoding="utf-8"))
    p = qwen_tags / ar.OUT_NAMES["tool_tags"]
    if p.exists():
        q_tool = json.loads(p.read_text(encoding="utf-8"))
        names = sorted(set(s_tool) & set(q_tool))
        per = {t: kappa_binary([t in s_tool[n] for n in names], [t in q_tool[n] for n in names])
               for t in mt.DOMAIN_NAMES}
        used = {t: k for t, k in per.items() if not math.isnan(k)}
        extra["tool_tags_kappa_per_tag"] = per
        extra["tool_tags_kappa_mean"] = sum(used.values()) / len(used) if used else float("nan")
    p = qwen_tags / ar.OUT_NAMES["query_tags_top5"]
    if p.exists():
        def by_key(entries):
            d = {}
            for e in entries:
                d.setdefault((e["query"].strip(), tuple(sorted(e.get("tools", [])))), set(e["context_tags"]))
            return d
        s = by_key(json.loads(ar.SONNET_FILES["query_tags_top5"].read_text(encoding="utf-8")))
        q = by_key(json.loads(p.read_text(encoding="utf-8")))
        keys = [k for k in s if k in q]
        per = {t: kappa_binary([t in s[k] for k in keys], [t in q[k] for k in keys]) for t in mt.QUERY_VOCAB}
        used = {t: k for t, k in per.items() if not math.isnan(k)}
        extra["query_tags_kappa_per_tag"] = per
        extra["query_tags_kappa_mean"] = sum(used.values()) / len(used) if used else float("nan")
        extra["query_tags_n_paired"] = len(keys)
    for target in ar.TB_MODULES:
        t = (rep.get("targets") or {}).get(target)
        if not t:
            continue
        pi = t["per_item"]
        if target == "toolbench_top1":
            extra[f"{target}_kappa"] = ar._kappa(list(pi["sonnet"]), list(pi["regen"]))
        else:
            cats = sorted({c for row in pi["sonnet"] + pi["regen"] for c in row})
            per = {c: kappa_binary([c in r for r in pi["sonnet"]], [c in r for r in pi["regen"]]) for c in cats}
            used = [k for k in per.values() if not math.isnan(k)]
            extra[f"{target}_kappa_per_category_mean"] = sum(used) / len(used) if used else float("nan")
    brief = {}
    for t, res in (rep.get("targets") or {}).items():
        brief[t] = {k: v for k, v in res.items() if k != "per_item"}
    return {"compare": brief, **extra}


def retrieval(runs_root: Path, qwen_tags: Path, q4b_sonnet_step: str | None) -> dict:
    out: dict = {}
    s_qt_keys = qt_keys(ar.SONNET_FILES["query_tags_top5"])
    q_path = qwen_tags / ar.OUT_NAMES["query_tags_top5"]
    q_qt_keys = qt_keys(q_path) if q_path.exists() else []
    for label, (s_step, q_step) in BACKENDS.items():
        notes = []
        if label == "Qwen3-4B":
            s_step = q4b_sonnet_step
            if s_step is None:
                s_step = "tb_auth_q4b_sonnet" if find_run(runs_root, "tb_auth_q4b_sonnet") else "tb_qwen4b"
            if s_step == "tb_qwen4b":
                notes.append("Sonnet arm is the reported tb_qwen4b run (encode batch 8). The second "
                             "tagger's run used the batch of 65_authorship.sh. A batch difference moves "
                             "values at rounding level only.")
        sp, qp = find_run(runs_root, s_step), find_run(runs_root, q_step)
        if sp is None or qp is None:
            out[label] = {"missing": [s for s, p in ((s_step, sp), (q_step, qp)) if p is None]}
            continue
        S, Q = load_json(sp), load_json(qp)
        gov, ung = f"BEAR+{label} (gov)", f"{label} (no gov)"
        res = {"sonnet_run": str(sp), "second_run": str(qp), "notes": notes}
        for cond in CONDITIONS:
            try:
                sg, su = S[cond][gov]["metrics"], S[cond][ung]["metrics"]
                qg, qu = Q[cond][gov]["metrics"], Q[cond][ung]["metrics"]
            except KeyError as e:
                res[cond] = {"missing": f"no {e} in a run"}
                continue
            n_s, n_q = len(sg["recall"]), len(qg["recall"])
            if cond == "MetaTool+Tags":
                if n_s != n_q:
                    res[cond] = {"missing": f"query sets differ ({n_s} vs {n_q})"}
                    continue
                ia = ib = list(range(n_s))
            else:
                if len(s_qt_keys) != n_s or len(q_qt_keys) != n_q:
                    res[cond] = {"missing": "the tag files do not match the runs' query counts"}
                    continue
                ia, ib = align(s_qt_keys, q_qt_keys)
            c: dict = {"n_sonnet": n_s, "n_second": n_q, "n_paired": len(ia)}
            for m in ("recall", "ndcg"):
                s_g = [sg[m][i] for i in ia]
                s_u = [su[m][i] for i in ia]
                q_g = [qg[m][j] for j in ib]
                q_u = [qu[m][j] for j in ib]
                c[m] = {
                    "sonnet_governed": summary(sg[m]), "second_governed": summary(qg[m]),
                    "sonnet_ungated": summary(su[m]), "second_ungated": summary(qu[m]),
                    "second_minus_sonnet_governed": paired(q_g, s_g),
                    "second_minus_sonnet_ungated": paired(q_u, s_u),
                    "effect_sonnet": paired(sg[m], su[m]),
                    "effect_second": paired(qg[m], qu[m]),
                    "effect_second_minus_effect_sonnet": paired([x - y for x, y in zip(q_g, q_u)],
                                                                [x - y for x, y in zip(s_g, s_u)]),
                }
            res[cond] = c
        out[label] = res
    return out


def fmt(x, nd=3):
    return "nan" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def to_md(rep: dict) -> str:
    L = ["# Authorship ablation: Sonnet 4.6 against the second tagger", "",
         f"Second tagger's files: `{rep['qwen_tags']}`. Runs: `{rep['runs_root']}`.", "", "## Agreement", ""]
    ag = rep["agreement"]
    for t, res in ag.get("compare", {}).items():
        bits = []
        for k, v in res.items():
            if isinstance(v, dict) and "mean" in v:
                bits.append(f"{k} {fmt(v['mean'])} [{fmt(v['ci'][0])}, {fmt(v['ci'][1])}]")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                bits.append(f"{k} {fmt(v) if isinstance(v, float) else v}")
        L.append(f"- **{t}**: " + ", ".join(bits))
    for k in ("tool_tags_kappa_mean", "query_tags_kappa_mean", "toolbench_top1_kappa",
              "toolbench_multi_kappa_per_category_mean", "toolbench_top5_kappa_per_category_mean"):
        if k in ag:
            L.append(f"- {k}: {fmt(ag[k])}")
    L += ["", "## Retrieval under each tagger", "",
          "| Backend | Condition | Metric | Governed, Sonnet | Governed, second | Second minus Sonnet [95% CI], p | "
          "Effect, Sonnet | Effect, second | Effect difference [95% CI], p |",
          "|---|---|---|---|---|---|---|---|---|"]
    for b, res in rep["retrieval"].items():
        if "missing" in res:
            L.append(f"| {b} | | | missing: {', '.join(res['missing'])} | | | | | |")
            continue
        for cond in CONDITIONS:
            c = res.get(cond) or {}
            if "missing" in c:
                L.append(f"| {b} | {cond} | | {c['missing']} | | | | | |")
                continue
            for m in ("recall", "ndcg"):
                x = c[m]
                sg, qg = x["sonnet_governed"], x["second_governed"]
                d, es, eq, dd = (x["second_minus_sonnet_governed"], x["effect_sonnet"], x["effect_second"],
                                 x["effect_second_minus_effect_sonnet"])
                L.append(f"| {b} | {cond} | {m}@5 | {fmt(sg['mean'])} [{fmt(sg['ci'][0])}, {fmt(sg['ci'][1])}] | "
                         f"{fmt(qg['mean'])} [{fmt(qg['ci'][0])}, {fmt(qg['ci'][1])}] | "
                         f"{d['delta']:+.3f} [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}], p {d['p_bootstrap']:.2g} | "
                         f"{es['delta']:+.3f} (d {es['d']:.2f}) | {eq['delta']:+.3f} (d {eq['d']:.2f}) | "
                         f"{dd['delta']:+.3f} [{dd['ci'][0]:+.3f}, {dd['ci'][1]:+.3f}], p {dd['p_bootstrap']:.2g} |")
        for n in res.get("notes", []):
            L.append(f"| {b} | note | | {n} | | | | | |")
    tb = rep.get("toolbench")
    if tb:
        L += ["", "## ToolBench inferred categories (Table 7, BGE)", "",
              "| Condition | Arm | Recall@5 [95% CI] | NDCG@5 [95% CI] |", "|---|---|---|---|"]
        for cond, e in (tb.get("conditions") or {}).items():
            for arm, v in e["arms"].items():
                r, n = v["recall"], v["ndcg"]
                L.append(f"| {cond} | {arm} | {fmt(r['mean'])} [{fmt(r['ci'][0])}, {fmt(r['ci'][1])}] | "
                         f"{fmt(n['mean'])} [{fmt(n['ci'][0])}, {fmt(n['ci'][1])}] |")
            for k, v in e["contrasts"].items():
                r = v["recall"]
                L.append(f"| {cond} | {k} (recall) | {r['delta']:+.3f} [{r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}], "
                         f"p {r['p_bootstrap']:.2g}, d {r['cohens_d_paired']:.2f} | |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qwen-tags", type=Path, required=True)
    ap.add_argument("--runs-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--toolbench-eval", type=Path, default=None)
    ap.add_argument("--sonnet-q4b-step", default=None)
    ap.add_argument("--skip-agreement", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    rep = {"qwen_tags": str(a.qwen_tags), "runs_root": str(a.runs_root), "n_boot": N_BOOT, "seed": SEED}
    rep["agreement"] = {} if a.skip_agreement else agreement(a.qwen_tags, a.out)
    rep["retrieval"] = retrieval(a.runs_root, a.qwen_tags, a.sonnet_q4b_step)
    if a.toolbench_eval and a.toolbench_eval.exists():
        tb = json.loads(a.toolbench_eval.read_text(encoding="utf-8"))
        for e in (tb.get("conditions") or {}).values():
            for v in e.get("arms", {}).values():
                v.pop("per_query", None)
            e.pop("queries", None)
        rep["toolbench"] = tb
    (a.out / "authorship.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    (a.out / "authorship.md").write_text(to_md(rep), encoding="utf-8")
    missing = [b for b, r in rep["retrieval"].items() if "missing" in r]
    print(f"written: {a.out / 'authorship.json'} and authorship.md")
    if missing:
        print(f"note: no runs yet for {' '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
