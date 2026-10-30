"""Budget-binding rate: how often the admissible candidate set exceeds k (WP1).

The revised formal section claims properties of the precedence order under
the context budget k (mandatory items exempt from the cut, prerequisites kept
with their dependents, nesting in k). Those claims bite only when the budget
binds, meaning the admissible candidate set is larger than k. If it almost
never is, the interaction claims are nearly vacuous. This script reports, for
every retrieval condition in the paper, the fraction of queries whose
admissible set exceeds k.

Admissible means it passes admission, before relationship resolution and the
top-k cut:

    gate(d)  and  ( soft(d)  or  sim(q, d) >= theta )      for every d
    plus every gate-admissible mandatory item

where gate(d) is required_tags within the context's tags and gate_tags, and
soft(d) is an empty soft scope or a matching one (ScopeCondition.matches).

Three measures per query:

  1. Metadata (backend-free). |{d : gate and (soft or mandatory)}|. Where no
     gate-passing optional item fails its soft scope, the threshold cannot
     act, admission does not depend on the backend, and this IS the
     admissible set. Otherwise it is a lower bound (the "floor").
  2. Trace, whole pool. The retriever's own trace, with retrieval_pool set to
     the corpus size so every row is ranked: the items admitted by search,
     the required-tags backfill or mandatory injection. This is the
     admissible set under that backend. It is what the threshold-dependent
     conditions report. Before BEAR 0.4.2, BM25 dropped zero-score rows from
     its search, so a BM25 trace admitted an ungated item only if it shared a
     term with the query. From 0.4.2 a zero-score row is a row of similarity
     0, which the threshold admits wherever theta <= 0 or the soft scope
     matches. The backend "bm25:dropped_rows" turns on
     Config.restore_dropped_rows to give the earlier search on the same BEAR.
  3. Trace, default pool. The same at the pool the paper's runs used (pool
     base 3 x default_top_k, or the whole corpus for gated queries), plus
     whether the top-k cut removed anything after relationship resolution
     ("cut binds").

Conditions (thresholds, priority weights and mandatory tags mirror the
scripts that produced each table):

    ToolBench governed / ungated (no gov) / mandatory-only   k=5   eval_toolbench.py
    MetaTool base, MetaTool+Tags, MetaTool+QueryTags          k=5   eval_toolbench.py
    Pet Sim full governance, 4 query sets                     k=10  eval_governance_ablation.py
    Procedural customer support, 6 scale points               k=25  eval_scalability.py

Backends: metadata needs none. Threshold-dependent conditions run on BM25 and
the hash embedder, and on BGE-base when --backends includes bge (forced onto
the CPU). Backend-free conditions run a hash-trace cross-check. A backend may
carry BEAR restore switches after colons, as in "bm25:dropped_rows" or
"hash:flat_backfill", each of which sets Config.restore_<switch> = True.

Only BEAR's public API is used. The trace comes from
Retriever.retrieve_with_trace (BEAR 0.4.0 and later), and the default-pool
size each query ranked is recorded from RetrievalTrace.pool.

Fractions above k carry Clopper-Pearson 95% CIs. Per-query arrays are saved
in the result JSON.

Usage:
    python evals/eval_budget_binding.py                        # bm25 + hash
    python evals/eval_budget_binding.py --backends bm25 hash bge
    python evals/eval_budget_binding.py --backends bm25 bm25:dropped_rows hash
    python evals/eval_budget_binding.py --conditions petsim cs
    BEAR_SOURCE_SHA=<sha> python evals/eval_budget_binding.py  # record the BEAR source commit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bear  # noqa: E402
from bear import Config, Context, Corpus, EmbeddingBackend, Retriever  # noqa: E402
from bear.retriever import Embedder  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

logging.getLogger("bear").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Constants (each mirrors the script that produced the paper's table)
# ---------------------------------------------------------------------------

# eval_toolbench.py
TB_K = 5
TB_PRIORITY_WEIGHT = 0.3
TB_THRESHOLD_DENSE = 0.15
TB_THRESHOLD_BM25 = 0.0
# eval_governance_ablation.py / eval_governance_decomposed.py
PS_K = 10
PS_PRIORITY_WEIGHT = 0.3
PS_THRESHOLD = 0.3
PS_MANDATORY = ["safety"]
# eval_scalability.py
CS_K = 25
CS_PRIORITY_WEIGHT = 0.3
CS_THRESHOLD = 0.3
CS_MANDATORY = ["safety", "global"]

BGE_MODEL = "BAAI/bge-base-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for retrieving relevant documents: "

MERIT = ("search", "required_tags", "mandatory")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    lo = 0.0 if x == 0 else float(stats.beta.ppf(alpha / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(stats.beta.ppf(1 - alpha / 2, x + 1, n - x))
    return lo, hi


def summarise(sizes: list[int], k: int) -> dict:
    a = np.asarray(sizes, dtype=float)
    n = len(a)
    above = int(np.sum(a > k))
    lo, hi = clopper_pearson(above, n)
    return {"n": n, "k": k,
            "mean": float(a.mean()) if n else float("nan"),
            "median": float(np.median(a)) if n else float("nan"),
            "min": float(a.min()) if n else float("nan"),
            "max": float(a.max()) if n else float("nan"),
            "n_above_k": above, "frac_above_k": above / n if n else float("nan"),
            "ci_lo": lo, "ci_hi": hi}


def summarise_flags(flags: list[bool]) -> dict:
    n = len(flags)
    x = int(sum(flags))
    lo, hi = clopper_pearson(x, n)
    return {"n": n, "count": x, "frac": x / n if n else float("nan"), "ci_lo": lo, "ci_hi": hi}


def gate_passes(inst, ctx: Context) -> bool:
    """required_tags within tags + gate_tags; a context with no tags passes no gate."""
    req = inst.scope.required_tags
    if not req:
        return True
    all_tags = set(ctx.all_tags)
    return bool(all_tags) and set(req) <= all_tags


def admission_metadata(instructions, ctx: Context, query: str,
                       mandatory_tags: list[str]) -> tuple[int, int, int]:
    """(floor, threshold-dependent, gate-passing) counts from metadata alone."""
    qctx = ctx.model_copy(update={"query": query})
    mand = set(mandatory_tags)
    floor = thr_dep = gate_n = 0
    for inst in instructions:
        if not gate_passes(inst, ctx):
            continue
        gate_n += 1
        is_mand = bool((set(inst.tags) | set(inst.scope.tags)) & mand)
        if is_mand or inst.scope.matches(qctx):
            floor += 1
        else:
            thr_dep += 1
    return floor, thr_dep, gate_n


BASE_BACKENDS = ("bm25", "hash", "bge")


def split_backend(backend: str) -> tuple[str, list[str]]:
    """'bm25:dropped_rows' -> ('bm25', ['restore_dropped_rows'])."""
    base, *switches = backend.split(":")
    return base, [f"restore_{s}" for s in switches]


def check_backend(backend: str) -> str:
    base, switches = split_backend(backend)
    if base not in BASE_BACKENDS:
        raise argparse.ArgumentTypeError(f"unknown backend {base!r}")
    missing = [s for s in switches if s not in Config.model_fields]
    if missing:
        raise argparse.ArgumentTypeError(
            f"BEAR {getattr(bear, '__version__', '?')} has no Config field {missing}")
    return backend


def make_config(backend: str, *, k: int, threshold_dense: float, threshold_bm25: float,
                priority_weight: float, mandatory_tags: list[str],
                retrieval_pool: int | None) -> Config:
    backend, switches = split_backend(backend)
    common = dict(priority_weight=priority_weight, default_top_k=k,
                  mandatory_tags=list(mandatory_tags), retrieval_pool=retrieval_pool,
                  **{s: True for s in switches})
    if backend == "bm25":
        return Config(embedding_model="bm25", embedding_backend=EmbeddingBackend.BM25,
                      embedding_dim=0, embedding_query_prefix="", embedding_passage_prefix="",
                      default_threshold=threshold_bm25, **common)
    if backend == "hash":
        return Config(embedding_model="hash", embedding_backend=EmbeddingBackend.NUMPY,
                      embedding_dim=768, embedding_query_prefix="", embedding_passage_prefix="",
                      default_threshold=threshold_dense, **common)
    if backend == "bge":
        return Config(embedding_model=BGE_MODEL, embedding_backend=EmbeddingBackend.NUMPY,
                      embedding_dim=768, embedding_query_prefix=BGE_QUERY_PREFIX,
                      embedding_passage_prefix="", embedding_device="cpu",
                      default_threshold=threshold_dense, **common)
    raise ValueError(backend)


def traced(r: Retriever, query: str, ctx: Context, k: int):
    """Results, admitted-on-merit count, whether the cut removed anything, pool."""
    out, trace = r.retrieve_with_trace(query, ctx, top_k=k)
    merit = sum(1 for h in trace.admitted.values() if h in MERIT)
    cut = any(e["reason"] == "top_k" for e in trace.excluded.values())
    return out, merit, cut, trace.pool


# ---------------------------------------------------------------------------
# Condition runner
# ---------------------------------------------------------------------------

def run_condition(key: str, label: str, corpus: Corpus, queries: list[tuple[str, Context]],
                  *, k: int, threshold_dense: float, threshold_bm25: float,
                  priority_weight: float, mandatory_tags: list[str],
                  backends: list[str], trace_check_backend: str | None = "hash",
                  always_run_backends: bool = False, note: str = "") -> dict:
    """Admission sizes for one condition. ``backends`` run when admission depends on
    the threshold, or always with ``always_run_backends`` (the pool still matters
    operationally). Otherwise ``trace_check_backend`` cross-checks the metadata."""
    t0 = time.time()
    instructions = list(corpus)
    n_corpus = len(instructions)
    floor, thr_dep, gate_n = [], [], []
    for q, ctx in queries:
        f, t, g = admission_metadata(instructions, ctx, q, mandatory_tags)
        floor.append(f)
        thr_dep.append(t)
        gate_n.append(g)
    backend_free = all(t == 0 for t in thr_dep)
    if not backend_free or always_run_backends:
        run_backends = list(backends)
    else:
        run_backends = [trace_check_backend] if trace_check_backend else []

    result = {
        "key": key, "label": label, "k": k, "n_queries": len(queries),
        "corpus_size": n_corpus, "threshold_dense": threshold_dense,
        "threshold_bm25": threshold_bm25, "priority_weight": priority_weight,
        "mandatory_tags": mandatory_tags, "backend_independent": backend_free,
        "note": note,
        "metadata": {"floor_summary": summarise(floor, k),
                     "per_query_floor": floor,
                     "per_query_threshold_dependent": thr_dep,
                     "per_query_gate_passing": gate_n},
        "backends": {},
    }

    for b in run_backends:
        kw = dict(k=k, threshold_dense=threshold_dense, threshold_bm25=threshold_bm25,
                  priority_weight=priority_weight, mandatory_tags=mandatory_tags)
        cfg_whole = make_config(b, retrieval_pool=n_corpus, **kw)
        # One embedder for both retrievers, through the public embedder
        # argument, so a dense model is loaded once. BM25 needs none.
        shared = None if split_backend(b)[0] == "bm25" else Embedder.from_config(cfg_whole)
        r_whole = Retriever(corpus, config=cfg_whole, embedder=shared)
        r_whole.build_index()
        r_def = Retriever(corpus, config=make_config(b, retrieval_pool=None, **kw),
                          embedder=shared)
        r_def.build_index()
        whole, default, cut, out_size, differ, pools = [], [], [], [], [], []
        for q, ctx in queries:
            out_w, m_w, _, _ = traced(r_whole, q, ctx, k)
            out_d, m_d, c_d, pool_d = traced(r_def, q, ctx, k)
            whole.append(m_w)
            default.append(m_d)
            cut.append(c_d)
            out_size.append(len(out_d))
            pools.append(pool_d)
            # Membership, not order: a mandatory item the search finds is scored
            # by the blend, one injected at priority/100, so order can differ
            # between pools while the set does not.
            differ.append({s.id for s in out_w} != {s.id for s in out_d})
        entry = {
            "role": ("operational" if always_run_backends and backend_free
                     else "cross-check" if backend_free else "admission"),
            "whole_pool_summary": summarise(whole, k),
            "default_pool_summary": summarise(default, k),
            "cut_binds_summary": summarise_flags(cut),
            "topk_differs_from_whole_pool": summarise_flags(differ),
            "per_query_whole_pool": whole,
            "per_query_default_pool": default,
            "per_query_cut_binds": cut,
            "per_query_output_size": out_size,
            "per_query_default_pool_size": pools,
        }
        if backend_free:
            mism = [i for i, (a, f) in enumerate(zip(whole, floor)) if a != f]
            entry["metadata_mismatches"] = len(mism)
            entry["metadata_mismatch_examples"] = mism[:10]
        result["backends"][b] = entry
    result["elapsed_s"] = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def toolbench_conditions(backends: list[str]) -> list[dict]:
    from eval_toolbench import load_toolbench_corpus_and_queries, strip_governance
    corpus, queries, _ = load_toolbench_corpus_and_queries()
    print(f"ToolBench: {len(corpus)} APIs, {len(queries)} queries")
    kw = dict(k=TB_K, threshold_dense=TB_THRESHOLD_DENSE, threshold_bm25=TB_THRESHOLD_BM25,
              mandatory_tags=[])
    out = []
    gov_q = [(q[0], Context(tags=q[1])) for q in queries]
    out.append(run_condition(
        "toolbench_gov", "ToolBench, governed", corpus, gov_q,
        priority_weight=TB_PRIORITY_WEIGHT, backends=backends, **kw,
        note="Gate on the RapidAPI category. Every gate-passing API also matches its soft scope "
             "(the category is in scope.tags), so the threshold cannot act."))
    stripped = strip_governance(corpus)
    nog_q = [(q[0], Context(tags=[])) for q in queries]
    # Ungated: the pool still matters operationally, so the lexical and hash
    # backends always run (BGE adds nothing here, since every API is admissible).
    out.append(run_condition(
        "toolbench_nogov", "ToolBench, ungated (no gov)", stripped, nog_q,
        priority_weight=0.0, backends=[b for b in backends if split_backend(b)[0] != "bge"],
        always_run_backends=True, **kw,
        note="Empty scopes match every context, so every API is admissible. The trace rows "
             "show the operational pool (base 15). Before BEAR 0.4.2 (or with "
             "restore_dropped_rows) BM25 search also drops zero-score rows."))
    out.append(run_condition(
        "toolbench_mandonly", "ToolBench, mandatory-only (supplementary)", corpus, nog_q,
        priority_weight=TB_PRIORITY_WEIGHT, backends=backends, **kw,
        note="Governed corpus, context without tags. The gate fails closed, so nothing is "
             "admissible. No mandatory tags are configured."))
    return out


def metatool_conditions(backends: list[str]) -> list[dict]:
    from eval_toolbench import (METATOOL_DIR, load_metatool_corpus, load_metatool_corpus_tagged,
                                load_metatool_queries, load_metatool_queries_from_query_tags,
                                load_metatool_queries_tagged)
    kw = dict(k=TB_K, threshold_dense=TB_THRESHOLD_DENSE, threshold_bm25=TB_THRESHOLD_BM25,
              mandatory_tags=[])
    out = []
    corpus, _ = load_metatool_corpus()
    queries = load_metatool_queries()
    print(f"MetaTool: {len(corpus)} tools, {len(queries)} queries")
    out.append(run_condition(
        "metatool_base", "MetaTool base (no tags)", corpus,
        [(q, Context(tags=t)) for q, t, _ in queries],
        priority_weight=TB_PRIORITY_WEIGHT, backends=backends, **kw,
        note="Soft scope is the tool's own name and queries carry no tags, so admission is "
             "sim >= theta alone. All priorities are 50."))
    tags_file = METATOOL_DIR / "plugin_tags.json"
    corpus_t, _ = load_metatool_corpus_tagged(tags_file)
    queries_t = load_metatool_queries_tagged(tags_file)
    out.append(run_condition(
        "metatool_tags", "MetaTool+Tags, governed", corpus_t,
        [(q, Context(tags=t)) for q, t, _ in queries_t],
        priority_weight=TB_PRIORITY_WEIGHT, backends=backends, **kw,
        note="required_tags = scope.tags = the tool's generated tags. A tool passes only if all "
             "its tags are in the query context."))
    for fname in ("query_tags.json", "query_tags_top5.json"):
        path = METATOOL_DIR / fname
        if not path.exists():
            continue
        qq = load_metatool_queries_from_query_tags(path)
        out.append(run_condition(
            f"metatool_querytags_{path.stem}", f"MetaTool+QueryTags ({fname}, supplementary)",
            corpus_t, [(q, Context(tags=t)) for q, t, _ in qq],
            priority_weight=TB_PRIORITY_WEIGHT, backends=backends, **kw))
    return out


def petsim_conditions(backends: list[str]) -> list[dict]:
    from eval_governance_decomposed import load_pet_sim_corpus
    from eval_retrieval import TEST_QUERIES
    from eval_retrieval_backends import COMPLEX_QUERIES, NO_TAG_QUERIES, PARAPHRASE_QUERIES
    corpus = load_pet_sim_corpus()
    print(f"Pet Sim: {len(corpus)} instructions")
    out = []
    for key, label, qs in (("standard", "Standard", TEST_QUERIES),
                           ("paraphrase", "Paraphrase", PARAPHRASE_QUERIES),
                           ("notag", "No-tag", NO_TAG_QUERIES),
                           ("complex", "Complex", COMPLEX_QUERIES)):
        out.append(run_condition(
            f"petsim_{key}", f"Pet Sim full governance, {label}", corpus,
            [(q, Context(tags=t)) for q, t, _ in qs],
            k=PS_K, threshold_dense=PS_THRESHOLD, threshold_bm25=PS_THRESHOLD,
            priority_weight=PS_PRIORITY_WEIGHT, mandatory_tags=PS_MANDATORY,
            backends=backends))
    return out


def cs_conditions(backends: list[str]) -> list[dict]:
    from eval_scalability import (SAMPLE_AGENTS, SCALE_POINTS, generate_corpus,
                                  generate_queries)
    out = []
    all_rows = []
    for num_agents in SCALE_POINTS:
        corpus, meta = generate_corpus(num_agents)
        sample_n = min(num_agents, SAMPLE_AGENTS)
        step = max(1, num_agents // sample_n)
        sampled = list(range(0, num_agents, step))[:sample_n]
        qs = []
        for a in sampled:
            qs.extend(generate_queries(a, meta["agents"][a]["dept_name"]))
        res = run_condition(
            f"cs_{num_agents}", f"Procedural CS, {num_agents} agents ({len(corpus)} instructions)",
            corpus, qs, k=CS_K, threshold_dense=CS_THRESHOLD, threshold_bm25=CS_THRESHOLD,
            priority_weight=CS_PRIORITY_WEIGHT, mandatory_tags=CS_MANDATORY, backends=backends)
        all_rows.append(res)
    # Pooled over scale points.
    floor = [x for r in all_rows for x in r["metadata"]["per_query_floor"]]
    pooled = {
        "key": "cs_pooled", "label": "Procedural CS, all scale points", "k": CS_K,
        "n_queries": len(floor), "backend_independent": all(r["backend_independent"] for r in all_rows),
        "metadata": {"floor_summary": summarise(floor, CS_K), "per_query_floor": floor},
        "backends": {}, "scale_points": [r["key"] for r in all_rows],
    }
    for b in all_rows[0]["backends"]:
        whole = [x for r in all_rows for x in r["backends"][b]["per_query_whole_pool"]]
        cut = [x for r in all_rows for x in r["backends"][b]["per_query_cut_binds"]]
        mism = sum(r["backends"][b].get("metadata_mismatches", 0) for r in all_rows)
        pooled["backends"][b] = {"role": all_rows[0]["backends"][b]["role"],
                                 "whole_pool_summary": summarise(whole, CS_K),
                                 "cut_binds_summary": summarise_flags(cut),
                                 "metadata_mismatches": mism}
    out.append(pooled)
    out.extend(all_rows)
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def fmt_frac(s: dict) -> str:
    return f"{s['frac_above_k']:.3f} [{s['ci_lo']:.3f}, {s['ci_hi']:.3f}]"


def print_condition(res: dict) -> None:
    k = res["k"]
    m = res["metadata"]["floor_summary"]
    basis = ("metadata (backend-free)" if res["backend_independent"]
             else "metadata floor (lower bound)")
    print(f"\n{res['label']}  [k={k}, n={res['n_queries']}, corpus={res.get('corpus_size', '-')}]")
    if res.get("note"):
        print(f"  note: {res['note']}")
    thr = res["metadata"].get("per_query_threshold_dependent")
    if thr is not None:
        print(f"  threshold-dependent gate-passing items per query: mean {np.mean(thr):.2f}, "
              f"max {max(thr)}  -> admission is "
              + ("backend-independent" if res["backend_independent"] else "backend-dependent"))
    print(f"  {'source':<34} {'mean':>8} {'median':>8} {'P(|A|>k) [95% CP CI]':>28}")
    print(f"  {basis:<34} {m['mean']:>8.2f} {m['median']:>8.1f} {fmt_frac(m):>28}")
    for b, e in res["backends"].items():
        w = e["whole_pool_summary"]
        print(f"  {b + ' trace, whole pool':<34} {w['mean']:>8.2f} {w['median']:>8.1f} {fmt_frac(w):>28}"
              + (f"   ({e['metadata_mismatches']} queries differ from metadata)"
                 if "metadata_mismatches" in e else ""))
        if "default_pool_summary" in e:
            d = e["default_pool_summary"]
            print(f"  {b + ' trace, default pool':<34} {d['mean']:>8.2f} {d['median']:>8.1f} {fmt_frac(d):>28}")
        c = e["cut_binds_summary"]
        cut_s = f"{c['frac']:.3f} [{c['ci_lo']:.3f}, {c['ci_hi']:.3f}]"
        print(f"  {b + ' cut removed >=1 item':<34} {'':>8} {'':>8} {cut_s:>28}")
        if "topk_differs_from_whole_pool" in e:
            t = e["topk_differs_from_whole_pool"]
            print(f"  {b + ' top-k differs, default vs whole pool':<34} "
                  f"{t['frac']:.3f} [{t['ci_lo']:.3f}, {t['ci_hi']:.3f}]")


def headline_rows(results: list[dict]) -> list[tuple]:
    """(label, k, n, source, summary) per condition, using the admissible set the
    condition's basis calls for."""
    rows = []
    for res in results:
        if res["key"].startswith("cs_") and res["key"] != "cs_pooled":
            continue
        if res["backend_independent"]:
            rows.append((res["label"], res["k"], res["n_queries"], "metadata",
                         res["metadata"]["floor_summary"]))
        else:
            for b, e in res["backends"].items():
                rows.append((res["label"], res["k"], res["n_queries"], b, e["whole_pool_summary"]))
    return rows


def print_latex(results: list[dict]) -> None:
    print("\n--- LaTeX table (paste into manuscript) ---\n")
    print(r"\begin{table}[t]")
    print(r"  \caption{Budget-binding rate: fraction of queries whose admissible candidate set "
          r"(gate, then soft scope or threshold, before relationship resolution and the cut) "
          r"exceeds $k$. Metadata rows need no backend. Backend rows read the retriever's trace "
          r"with the whole corpus ranked. 95\% Clopper--Pearson CIs.}")
    print(r"  \label{tab:budget-binding}")
    print(r"  \centering")
    print(r"  \small")
    print(r"  \begin{tabular}{@{}l c r l c c c@{}}")
    print(r"    \toprule")
    print(r"    Condition & $k$ & $n$ & Basis & Mean $|A|$ & Median $|A|$ & $P(|A|>k)$ [95\% CI] \\")
    print(r"    \midrule")
    for label, k, n, src, s in headline_rows(results):
        lab = label.replace("_", r"\_").replace("&", r"\&")
        n_s = f"{n:,}".replace(",", "{,}")
        print(f"    {lab} & {k} & {n_s} & {src} & {s['mean']:.1f} & {s['median']:.0f} & "
              f"{s['frac_above_k']:.3f} [{s['ci_lo']:.3f}, {s['ci_hi']:.3f}] \\\\")
    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"\end{table}")


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self._streams:
            s.flush()

    def __getattr__(self, name):
        return getattr(self._streams[0], name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_CONDITIONS = ("toolbench", "metatool", "petsim", "cs")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--conditions", nargs="+", default=list(ALL_CONDITIONS),
                   choices=list(ALL_CONDITIONS))
    p.add_argument("--backends", nargs="+", default=["bm25", "hash"], type=check_backend,
                   help="Backends for threshold-dependent conditions: bm25, hash or bge, each "
                        "optionally followed by :<switch> to set Config.restore_<switch>. "
                        "bge runs on the CPU.")
    p.add_argument("--output", type=Path,
                   default=project_root / "results" / "budget_binding.json")
    p.add_argument("--log-file", type=Path,
                   default=project_root / "results" / "budget_binding_output.txt")
    p.add_argument("--overwrite", action="store_true",
                   help="Replace an existing output or log file.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    for path in (args.output, args.log_file):
        if path and str(path).strip() and path.exists() and not args.overwrite:
            sys.exit(f"{path} exists. Pass --overwrite or choose another path.")
    log_handle = None
    original_stdout = sys.stdout
    if args.log_file and str(args.log_file).strip():
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log_file.open("w", encoding="utf-8")
        sys.stdout = _Tee(original_stdout, log_handle)  # type: ignore[assignment]
    try:
        t0 = time.time()
        print("\n=== Budget-binding rate: admissible set larger than k ===\n")
        print(f"Backends for threshold-dependent conditions: {args.backends}")
        results: list[dict] = []
        runners = {"toolbench": toolbench_conditions, "metatool": metatool_conditions,
                   "petsim": petsim_conditions, "cs": cs_conditions}
        for c in args.conditions:
            t1 = time.time()
            part = runners[c](args.backends)
            results.extend(part)
            for res in part:
                if res.get("label"):
                    print_condition(res)
            print(f"  [{c}: {time.time() - t1:.1f}s]")

        print("\n--- Summary: P(admissible set > k) ---\n")
        print(f"{'Condition':<52} {'k':>3} {'n':>6} {'basis':>9} {'mean':>7} {'median':>7}  "
              f"{'P(|A|>k) [95% CP CI]'}")
        for label, k, n, src, s in headline_rows(results):
            print(f"{label[:52]:<52} {k:>3} {n:>6} {src:>9} {s['mean']:>7.1f} {s['median']:>7.0f}  {fmt_frac(s)}")
        print_latex(results)

        out = {
            "bear_version": getattr(bear, "__version__", "?"),
            "bear_path": bear.__file__,
            "bear_source_sha": os.environ.get("BEAR_SOURCE_SHA", "(unset)"),
            "backends": args.backends,
            "conditions": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w") as f:
            json.dump(out, f, indent=1, default=float)
        print(f"\nWrote {args.output}")
        print(f"\nElapsed: {time.time() - t0:.1f}s")
        print_repro_footer(extra={
            "conditions": args.conditions, "backends": args.backends,
            "bear_path": bear.__file__,
            "bear_source_sha": os.environ.get("BEAR_SOURCE_SHA", "(unset)")})
    finally:
        if log_handle is not None:
            sys.stdout = original_stdout
            log_handle.close()


if __name__ == "__main__":
    main()
