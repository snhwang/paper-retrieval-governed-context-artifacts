#!/usr/bin/env python3
"""Tag-noise sweep: how governed retrieval degrades when its tags are wrong (WP6).

R2-2 and the AE ask how much BEAR depends on metadata quality. This script
corrupts the tags the gate reads and measures Recall@5 against the noise
rate, the rate at which governance falls below no governance, and how the
failures split between over-restriction and leakage.

Design: the noise changes admission only
----------------------------------------
BEAR writes ``Context.tags`` into the embedded query text and an
instruction's ``tags`` and ``scope.tags`` into its embedded text. A noise
sweep through those fields would change similarity and admission at once.
Here the tags reach the gate and nothing else:

  * query side   the (noisy) query tags go in ``Context.gate_tags``, which
                 BEAR checks at the gate and never embeds or soft-matches.
  * corpus side  the (noisy) tags are each item's ``scope.required_tags``,
                 which BEAR checks at the gate and never embeds.

Every item keeps its clean ``tags`` (embedded, as in the published corpus)
and an empty soft scope, so a gate-passing item is never removed by the
threshold. The ungated arm uses the same items with no required tags and an
empty context. Governed and ungated therefore rank by identical
similarities, and the only difference between them is the gate. Vectors
are computed once per backend (see tistr2_common).

Every item gets priority 0. These corpora give all items one priority (50),
so its value does not change the order of searched items. It does change
BEAR's required-tags backfill, which adds a gate-passing item the search
never returned at a score of priority/100. Only BM25 leaves rows out (zero
lexical overlap), and at priority 50 such an item would outrank a matched
item with normalized BM25 below 0.5. With priority 0 it ranks after every
matched item. A BM25 row at priority 50 is reported for reference. Priority
appears in BEAR's instruction header, so the embedded text reads
"[priority:0]" in both arms.

At noise 0 the script also runs the published configuration (tags in
``Context.tags``, the published corpus) as a reference row, so the gate-only
numbers can be read against Table 3 and Table 6.

Noise
-----
Two sides, each corrupted separately. Three kinds, each applied per tag
with probability p:

  drop   remove the tag.
  swap   replace it with a vocabulary tag not already present.
  add    keep it and add one vocabulary tag not already present.

Rates 0.1 to 0.5 in steps of 0.1, 5 seeds each. The noise depends on the
seed, side, kind, rate and benchmark only, so it is identical across
backends (paired). Vocabularies: the 49 RapidAPI categories (ToolBench) and
the 19 domain tags (MetaTool+Tags).

What each kind does under BEAR's gate (required_tags must all be present in
the context, and an item with none passes everywhere):

  query drop    fewer admissible categories: over-restriction. All tags gone
                means an empty context, which fails closed.
  query swap    loses the true category and admits a wrong one.
  query add     admits an extra category: leakage.
  corpus drop   an item that loses its only required tag is ungated and
                admitted in every context: leakage (fails open).
  corpus swap   the item gates on a wrong category: over-restriction for its
                own queries, leakage into another category's.
  corpus add    the item needs an extra tag: over-restriction.

Measures (per query, then averaged over seeds before bootstrapping over
queries): Recall@5, NDCG@5, and for the needed (ground-truth) items whether
each was retrieved, excluded by the gate (over-restriction) or admitted and
then cut. Leakage is measured against the clean tags: an admitted item whose
clean required tags are not all in the query's clean tags is out of scope.
We report the share of the returned top 5 that is out of scope and the mean
number of out-of-scope items admitted. All of it comes from
``Retriever.retrieve_with_trace``. The trace's gate count is exact on dense
backends (a gated query ranks the whole corpus) and a lower bound on BM25,
whose search never returns zero-overlap rows. The gatecheck phase gives the
exact, backend-free count.

Benchmarks: ToolBench (3,225 APIs, 1,100 queries, gate on the RapidAPI
category) and MetaTool+Tags (199 tools, 21,111 queries, gate on the
generated tool tags, query context = the tags of the target tools).

Backends: bm25, hash, bge, qwen3-0.6b and nemotron by default.

Over-restriction is also recomputed from metadata alone (``--phase
gatecheck``), since the trace misses BM25 rows the search never returned.

Usage:
    flock ~/tist-gpu.lock python evals/eval_tag_noise.py --phase embed
    CUDA_VISIBLE_DEVICES= python evals/eval_tag_noise.py --phase run --workers 24
    python evals/eval_tag_noise.py --phase gatecheck         --output results/tag_noise_overrestriction.json --compare results/tag_noise*.json
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tistr2_common import (  # noqa: E402
    BACKEND_LABEL, REPO_ROOT, CachedEmbedder, EmbeddingStore, Tee, bear_provenance,
    build_retriever, check_bm25_memo, ci_summary, enable_bm25_memo, json_default,
    make_config, ndcg, paired_summary, record_texts, refuse_overwrite, require_bear_040,
)
from bear import Context, Corpus  # noqa: E402
from bear.models import Instruction, InstructionType, ScopeCondition  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

FAMILY = "toolbench"
K = 5
PRIORITY_WEIGHT = 0.3
THETA_DENSE = 0.15
THETA_BM25 = 0.0
SWEEP_PRIORITY = 0
BENCHMARKS = ("toolbench", "metatool_tags")
BENCH_LABEL = {"toolbench": "ToolBench", "metatool_tags": "MetaTool+Tags"}
SIDES = ("query", "corpus")
KINDS = ("drop", "swap", "add")
RATES = (0.1, 0.2, 0.3, 0.4, 0.5)
SEEDS = (0, 1, 2, 3, 4)
DEFAULT_BACKENDS = ["bm25", "hash", "bge", "qwen3-0.6b", "nemotron"]


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

@dataclass
class Bench:
    name: str
    items: list[dict]                       # id, content, tags, req (clean)
    queries: list[tuple[str, list[str], set[str], str]]
    vocab: list[str]
    paper_corpus: Corpus
    req_clean: dict[str, frozenset] = field(default_factory=dict)


def load_bench(name: str) -> Bench:
    if name == "toolbench":
        from eval_toolbench import load_toolbench_corpus_and_queries
        corpus, queries, _ = load_toolbench_corpus_and_queries()
        qs = [(q[0], list(q[1]), set(q[2]), q[3]) for q in queries]
    else:
        from eval_toolbench import (METATOOL_DIR, load_metatool_corpus_tagged,
                                    load_metatool_queries_tagged)
        tags_file = METATOOL_DIR / "plugin_tags.json"
        corpus, _ = load_metatool_corpus_tagged(tags_file)
        raw = load_metatool_queries_tagged(tags_file)
        # The published loader builds a multi-tool query's tags by iterating a
        # set of tool ids, so their order (which BEAR writes into the embedded
        # query header) depends on the process hash seed. Rebuild them in
        # sorted tool order so every process and every run sees one text.
        tool_tags = json.loads(tags_file.read_text())
        qs = []
        for q, t, e in raw:
            canon: list[str] = []
            for tid in sorted(e):
                for tag in tool_tags.get(tid.replace("metatool/", ""), []):
                    if tag not in canon:
                        canon.append(tag)
            if set(canon) != set(t):
                raise SystemExit(f"tag rebuild mismatch for {q!r}")
            qs.append((q, canon, set(e), "multi" if len(e) > 1 else "single"))
    items = [{"id": i.id, "content": i.content, "tags": list(i.tags),
              "req": list(i.scope.required_tags), "metadata": dict(i.metadata)} for i in corpus]
    vocab = sorted({t for it in items for t in it["req"]} | {t for q in qs for t in q[1]})
    b = Bench(name=name, items=items, queries=qs, vocab=vocab, paper_corpus=corpus)
    b.req_clean = {it["id"]: frozenset(it["req"]) for it in items}
    return b


def query_sha(bench: Bench) -> str:
    """Hash of the query order, so other scripts can join per-query arrays."""
    import hashlib
    h = hashlib.sha256()
    for q in bench.queries:
        h.update(q[0].encode("utf-8") + b"" + ",".join(sorted(q[2])).encode() + b"")
    return h.hexdigest()


def sweep_corpus(bench: Bench, req: dict[str, list[str]] | None, priority: int = SWEEP_PRIORITY) -> Corpus:
    """Items with clean tags and the given required tags (None = ungated)."""
    c = Corpus()
    for it in bench.items:
        c.add(Instruction(
            id=it["id"], type=InstructionType.TOOL, priority=priority, content=it["content"],
            scope=ScopeCondition(required_tags=list(req[it["id"]]) if req is not None else []),
            tags=it["tags"], metadata=it["metadata"]))
    return c


# ---------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------

def corrupt(tags: list[str], kind: str, p: float, rng: np.random.Generator,
            vocab: list[str]) -> list[str]:
    tags = list(tags)
    if kind == "drop":
        return [t for t in tags if rng.random() >= p]
    if kind == "swap":
        out: list[str] = []
        for t in tags:
            if rng.random() < p:
                pool = [v for v in vocab if v not in tags and v not in out]
                out.append(pool[int(rng.integers(len(pool)))])
            elif t not in out:
                out.append(t)
        return out
    if kind == "add":
        out = list(tags)
        for _ in tags:
            if rng.random() < p:
                pool = [v for v in vocab if v not in out]
                out.append(pool[int(rng.integers(len(pool)))])
        return out
    raise ValueError(kind)


def noise_rng(bench: str, side: str, kind: str, rate: float, seed: int) -> np.random.Generator:
    return np.random.default_rng([seed, SIDES.index(side), KINDS.index(kind),
                                  int(round(rate * 100)), BENCHMARKS.index(bench)])


def noisy_tags(bench: Bench, side: str, kind: str, rate: float, seed: int):
    """(query tag lists, item required-tag map) for one condition."""
    rng = noise_rng(bench.name, side, kind, rate, seed)
    if side == "query":
        return [corrupt(q[1], kind, rate, rng, bench.vocab) for q in bench.queries], \
               {it["id"]: it["req"] for it in bench.items}
    return [q[1] for q in bench.queries], \
           {it["id"]: corrupt(it["req"], kind, rate, rng, bench.vocab) for it in bench.items}


def noise_stats(bench: Bench, side: str, kind: str, rate: float, seed: int) -> dict:
    qt, req = noisy_tags(bench, side, kind, rate, seed)
    if side == "query":
        changed = sum(set(a) != set(q[1]) for a, q in zip(qt, bench.queries))
        empty = sum(not a for a in qt)
        return {"changed": changed, "n": len(qt), "empty": empty}
    changed = sum(set(req[i]) != bench.req_clean[i] for i in req)
    empty = sum(not req[i] for i in req)
    return {"changed": changed, "n": len(req), "empty": empty}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

G_BENCH: dict[str, Bench] = {}
G_STORE: dict[tuple[str, str], EmbeddingStore] = {}


def task_config(backend: str, arm: str) -> "object":
    theta = THETA_BM25 if backend == "bm25" else THETA_DENSE
    pw = 0.0 if arm == "ungated" else PRIORITY_WEIGHT
    return make_config(backend, FAMILY, k=K, threshold=theta, priority_weight=pw)


def run_task(spec: dict) -> dict:
    """One condition on one backend: per-query arrays."""
    bench = G_BENCH[spec["bench"]]
    backend = spec["backend"]
    arm = spec["arm"]
    t0 = time.time()
    if arm == "ungated":
        corpus = sweep_corpus(bench, None)
        ctxs = [Context() for _ in bench.queries]
    elif arm == "paper_governed":
        corpus = bench.paper_corpus
        ctxs = [Context(tags=q[1]) for q in bench.queries]
    elif arm == "gate_clean":
        corpus = sweep_corpus(bench, {it["id"]: it["req"] for it in bench.items},
                              priority=spec.get("priority", SWEEP_PRIORITY))
        ctxs = [Context(gate_tags=q[1]) for q in bench.queries]
    elif arm == "gate_noise":
        qt, req = noisy_tags(bench, spec["side"], spec["kind"], spec["rate"], spec["seed"])
        corpus = sweep_corpus(bench, req)
        ctxs = [Context(gate_tags=t) for t in qt]
    else:
        raise ValueError(arm)

    emb = None if backend == "bm25" else CachedEmbedder(G_STORE[(spec["bench"], backend)])
    r = build_retriever(corpus, backend, FAMILY, task_config(backend, arm), emb)
    n = len(bench.queries)
    rec = np.zeros(n, np.float32)
    nd = np.zeros(n, np.float32)
    n_out = np.zeros(n, np.int16)
    need = np.zeros(n, np.int16)
    need_gate = np.zeros(n, np.int16)
    need_got = np.zeros(n, np.int16)
    adm_oos = np.zeros(n, np.int32)
    top_oos = np.zeros(n, np.int16)
    for i, ((q, clean, expected, _split), ctx) in enumerate(zip(bench.queries, ctxs)):
        out, tr = r.retrieve_with_trace(q, ctx, top_k=K)
        ids = [s.id for s in out]
        got = set(ids)
        cset = set(clean)
        rec[i] = len(got & expected) / len(expected)
        nd[i] = ndcg(ids, expected, K)
        n_out[i] = len(ids)
        need[i] = len(expected)
        need_got[i] = len(got & expected)
        need_gate[i] = sum(1 for e in expected
                           if (x := tr.excluded.get(e)) is not None and x["reason"] == "gate")
        rc = bench.req_clean
        adm_oos[i] = sum(1 for a in tr.admitted if not rc[a] <= cset)
        top_oos[i] = sum(1 for a in ids if not rc[a] <= cset)
    return {"spec": spec, "recall": rec, "ndcg": nd, "n_out": n_out, "need": need,
            "need_got": need_got, "need_gate": need_gate, "adm_oos": adm_oos,
            "top_oos": top_oos, "seconds": round(time.time() - t0, 1)}


def all_specs(benches: list[str], backends: list[str], rates, seeds) -> list[dict]:
    specs = []
    for bn in benches:
        for b in backends:
            specs.append({"bench": bn, "backend": b, "arm": "ungated"})
            specs.append({"bench": bn, "backend": b, "arm": "gate_clean"})
            specs.append({"bench": bn, "backend": b, "arm": "paper_governed"})
            if b == "bm25":
                specs.append({"bench": bn, "backend": b, "arm": "gate_clean", "priority": 50})
            for side in SIDES:
                for kind in KINDS:
                    for rate in rates:
                        for seed in seeds:
                            specs.append({"bench": bn, "backend": b, "arm": "gate_noise",
                                          "side": side, "kind": kind, "rate": rate, "seed": seed})
    # Longest first, so the pool ends evenly.
    specs.sort(key=lambda s: (s["bench"] != "metatool_tags", s["backend"] == "bm25"))
    return specs


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def failure_rates(rs: list[dict]) -> dict:
    """Pooled over seeds: needed-item fates and leakage."""
    need = sum(int(r["need"].sum()) for r in rs)
    got = sum(int(r["need_got"].sum()) for r in rs)
    gate = sum(int(r["need_gate"].sum()) for r in rs)
    n_q = sum(len(r["recall"]) for r in rs)
    top = np.concatenate([r["top_oos"] / np.maximum(r["n_out"], 1) for r in rs])
    return {
        "needed_retrieved": got / need, "needed_gate_excluded": gate / need,
        "needed_admitted_but_cut_or_other": (need - got - gate) / need,
        "queries_with_gate_excluded_needed": float(np.mean(np.concatenate(
            [(r["need_gate"] > 0) for r in rs]))),
        "leak_top5_share": float(top.mean()),
        "queries_with_leak_in_top5": float(np.mean(np.concatenate([(r["top_oos"] > 0) for r in rs]))),
        "admitted_out_of_scope_mean": float(np.mean(np.concatenate([r["adm_oos"] for r in rs]))),
        "empty_output_share": float(np.mean(np.concatenate([(r["n_out"] == 0) for r in rs]))),
        "n_query_runs": n_q,
    }


def crossover(rates: list[float], gov: list[float], ung: float) -> float | None:
    """Linear interpolation of the first rate where governed recall < ungated."""
    xs, ys = [0.0] + list(rates), list(gov)
    for i in range(1, len(xs)):
        if ys[i] < ung <= ys[i - 1]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return float(x0 + (ung - y0) * (x1 - x0) / (y1 - y0))
        if ys[i - 1] < ung:
            return float(xs[i - 1])
    return None


def summarise(results: list[dict], benches, backends, rates) -> dict:
    by = {}
    for r in results:
        s = r["spec"]
        key = (s["bench"], s["backend"], s["arm"], s.get("side"), s.get("kind"),
               s.get("rate"), s.get("priority", SWEEP_PRIORITY))
        by.setdefault(key, []).append(r)
    out: dict = {}
    for bn in benches:
        out[bn] = {}
        for b in backends:
            ung = by[(bn, b, "ungated", None, None, None, SWEEP_PRIORITY)][0]
            clean = by[(bn, b, "gate_clean", None, None, None, SWEEP_PRIORITY)][0]
            paper = by[(bn, b, "paper_governed", None, None, None, SWEEP_PRIORITY)][0]
            e: dict = {
                "ungated": {"recall": ci_summary(ung["recall"]), "ndcg": ci_summary(ung["ndcg"]),
                            "failures": failure_rates([ung]),
                            "per_query_recall": ung["recall"], "per_query_ndcg": ung["ndcg"],
                            "per_query_top_oos": ung["top_oos"], "per_query_n_out": ung["n_out"]},
                "gate_clean": {"recall": ci_summary(clean["recall"]),
                               "ndcg": ci_summary(clean["ndcg"]),
                               "failures": failure_rates([clean]),
                               "vs_ungated_recall": paired_summary(clean["recall"], ung["recall"]),
                               "vs_ungated_ndcg": paired_summary(clean["ndcg"], ung["ndcg"]),
                               "per_query_recall": clean["recall"], "per_query_ndcg": clean["ndcg"],
                               "per_query_top_oos": clean["top_oos"]},
                "paper_governed": {"recall": ci_summary(paper["recall"]),
                                   "ndcg": ci_summary(paper["ndcg"]),
                                   "failures": failure_rates([paper]),
                                   "vs_ungated_recall": paired_summary(paper["recall"], ung["recall"]),
                                   "vs_gate_clean_recall": paired_summary(paper["recall"], clean["recall"]),
                                   "per_query_recall": paper["recall"], "per_query_ndcg": paper["ndcg"],
                                   "per_query_top_oos": paper["top_oos"]},
                "sweep": {},
            }
            if b == "bm25":
                p50 = by.get((bn, b, "gate_clean", None, None, None, 50))
                if p50:
                    e["gate_clean_priority50"] = {
                        "recall": ci_summary(p50[0]["recall"]),
                        "vs_priority0": paired_summary(p50[0]["recall"], clean["recall"]),
                        "per_query_recall": p50[0]["recall"]}
            for side in SIDES:
                for kind in KINDS:
                    rows = []
                    for rate in rates:
                        rs = by[(bn, b, "gate_noise", side, kind, rate, SWEEP_PRIORITY)]
                        rs.sort(key=lambda x: x["spec"]["seed"])
                        mean_rec = np.mean([x["recall"] for x in rs], axis=0)
                        mean_nd = np.mean([x["ndcg"] for x in rs], axis=0)
                        rows.append({
                            "rate": rate, "seeds": [x["spec"]["seed"] for x in rs],
                            "recall": ci_summary(mean_rec), "ndcg": ci_summary(mean_nd),
                            "recall_seed_means": [float(x["recall"].mean()) for x in rs],
                            "recall_seed_sd": float(np.std([x["recall"].mean() for x in rs], ddof=1)),
                            "vs_ungated": paired_summary(mean_rec, ung["recall"]),
                            "vs_clean": paired_summary(mean_rec, clean["recall"]),
                            "failures": failure_rates(rs),
                            "per_query_recall_seedmean": mean_rec,
                        })
                    gov_curve = [float(clean["recall"].mean())] + [r_["recall"]["mean"] for r_ in rows]
                    sig = next((r_["rate"] for r_ in rows if r_["vs_ungated"]["ci"][1] < 0), None)
                    e["sweep"][f"{side}_{kind}"] = {
                        "rows": rows,
                        "crossover_rate_interpolated": crossover(list(rates), gov_curve,
                                                                 float(ung["recall"].mean())),
                        "first_rate_significantly_below_ungated": sig,
                    }
            out[bn][b] = e
    return out


def print_summary(summ: dict, rates) -> None:
    for bn, per_b in summ.items():
        print(f"\n=== {BENCH_LABEL[bn]}: Recall@5 against tag noise (mean over 5 seeds, "
              f"95% bootstrap CI over queries) ===")
        for b, e in per_b.items():
            u, c, p = e["ungated"]["recall"], e["gate_clean"]["recall"], e["paper_governed"]["recall"]
            print(f"\n{BACKEND_LABEL[b]}: ungated {u['mean']:.3f}  gate-only clean {c['mean']:.3f}  "
                  f"published config {p['mean']:.3f}"
                  + (f"  (BM25 gate-only at priority 50: "
                     f"{e['gate_clean_priority50']['recall']['mean']:.3f})"
                     if "gate_clean_priority50" in e else ""))
            print(f"  {'condition':<14}" + "".join(f"{r:>8.1f}" for r in rates)
                  + "   crossover  sig<ungated")
            for key, sw in e["sweep"].items():
                vals = "".join(f"{row['recall']['mean']:>8.3f}" for row in sw["rows"])
                xo = sw["crossover_rate_interpolated"]
                sg = sw["first_rate_significantly_below_ungated"]
                print(f"  {key:<14}{vals}   {('%.2f' % xo) if xo is not None else '  none':>9}"
                      f"  {('%.1f' % sg) if sg is not None else 'none':>10}")
            print(f"  failure split at rate 0.3 (needed items gate-excluded / top-5 out-of-scope share):")
            for key, sw in e["sweep"].items():
                row = next(r for r in sw["rows"] if abs(r["rate"] - 0.3) < 1e-9)
                f = row["failures"]
                print(f"    {key:<14} over-restriction {f['needed_gate_excluded']:.3f}   "
                      f"leakage@5 {f['leak_top5_share']:.3f}   "
                      f"admitted out-of-scope {f['admitted_out_of_scope_mean']:.1f}   "
                      f"empty output {f['empty_output_share']:.3f}")


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def base_conditions(bench: Bench) -> list:
    """Corpora and contexts whose texts cover every condition in the sweep."""
    cfg = make_config("hash", FAMILY, k=K, threshold=THETA_DENSE, priority_weight=PRIORITY_WEIGHT)
    gate = sweep_corpus(bench, {it["id"]: it["req"] for it in bench.items})
    return [
        (gate, [(q[0], Context(gate_tags=q[1])) for q in bench.queries], cfg),
        (bench.paper_corpus, [(q[0], Context(tags=q[1])) for q in bench.queries], cfg),
    ]


def phase_embed(args) -> None:
    for bn in args.benchmarks:
        bench = load_bench(bn)
        t0 = time.time()
        qt, dt = record_texts(base_conditions(bench), top_k=K)
        print(f"{bn}: recorded {len(qt)} query and {len(dt)} document texts "
              f"in {time.time() - t0:.0f}s", flush=True)
        for b in args.backends:
            if b == "bm25":
                continue
            st = EmbeddingStore(b, FAMILY, name=f"{bn}__{b}")
            print(f"  {b}: {st.fill(qt, dt)}", flush=True)


def phase_run(args) -> None:
    refuse_overwrite(args.output, args.log_file)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        print("=== Tag-noise sweep (WP6), BEAR 0.4.0, gate-only noise ===")
        print(f"k={K}, priority weight {PRIORITY_WEIGHT} (ungated 0), theta dense {THETA_DENSE}, "
              f"BM25 {THETA_BM25}, sweep priority {SWEEP_PRIORITY}")
        print(f"Benchmarks {args.benchmarks}, backends {args.backends}, rates {args.rates}, "
              f"seeds {args.seeds}, workers {args.workers}")
        enable_bm25_memo()
        noise_info = {}
        for bn in args.benchmarks:
            G_BENCH[bn] = load_bench(bn)
            bench = G_BENCH[bn]
            print(f"{bn}: {len(bench.items)} items, {len(bench.queries)} queries, "
                  f"vocabulary {len(bench.vocab)}")
            for b in args.backends:
                if b != "bm25":
                    G_STORE[(bn, b)] = EmbeddingStore(b, FAMILY, name=f"{bn}__{b}")
            noise_info[bn] = {f"{s}_{k}_{r}_{sd}": noise_stats(bench, s, k, r, sd)
                              for s in SIDES for k in KINDS for r in args.rates for sd in args.seeds}
        if "bm25" in args.backends:
            bench = G_BENCH[args.benchmarks[0]]
            bad = check_bm25_memo(sweep_corpus(bench, {it["id"]: it["req"] for it in bench.items}),
                                  [(q[0], Context(gate_tags=q[1])) for q in bench.queries],
                                  task_config("bm25", "gate_clean"), K)
            print(f"BM25 memo check: {bad} of 50 queries differ from uncached search (want 0)")
            if bad:
                raise SystemExit("BM25 memo is not exact.")
        specs = all_specs(args.benchmarks, args.backends, args.rates, args.seeds)
        print(f"{len(specs)} tasks", flush=True)
        results = []
        ctx = mp.get_context("fork")
        with ctx.Pool(args.workers) as pool:
            for i, res in enumerate(pool.imap_unordered(run_task, specs), 1):
                results.append(res)
                if i % 25 == 0 or i == len(specs):
                    print(f"  {i}/{len(specs)} tasks, {time.time() - t0:.0f}s", flush=True)
        summ = summarise(results, args.benchmarks, args.backends, args.rates)
        print_summary(summ, args.rates)
        raw = [{"spec": r["spec"], "seconds": r["seconds"],
                **{k: r[k] for k in ("recall", "ndcg", "n_out", "need", "need_got",
                                     "need_gate", "adm_oos", "top_oos")}} for r in results]
        out = {"design": {"k": K, "priority_weight": PRIORITY_WEIGHT, "theta_dense": THETA_DENSE,
                          "theta_bm25": THETA_BM25, "sweep_priority": SWEEP_PRIORITY,
                          "rates": args.rates, "seeds": args.seeds, "sides": SIDES,
                          "kinds": KINDS, "query_tags_channel": "Context.gate_tags",
                          "corpus_tags_channel": "scope.required_tags"},
               "benchmarks": {bn: {"n_items": len(G_BENCH[bn].items),
                                   "n_queries": len(G_BENCH[bn].queries),
                                   "vocab": G_BENCH[bn].vocab,
                                   "query_splits": [q[3] for q in G_BENCH[bn].queries],
                                   "query_sha256": query_sha(G_BENCH[bn])}
                              for bn in args.benchmarks},
               "noise_stats": noise_info, "provenance": bear_provenance(),
               "summary": summ, "per_task": raw}
        args.output.write_text(json.dumps(out, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "tag_noise", "backends": args.backends,
                                  "benchmarks": args.benchmarks, **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


def phase_gatecheck(args) -> None:
    """Over-restriction from metadata alone, with BEAR's own gate function.

    Whether a needed item passes the gate depends only on the noisy tags, not
    on the backend. The run phase counts it from the trace, which is exact on
    dense backends (a gated query ranks the whole corpus) but misses BM25 rows
    the lexical search never returned. This phase recomputes it for every
    condition with ``bear.scope.passes_gate`` and, where a run file is given,
    checks it against the dense backends' trace counts.
    """
    from types import SimpleNamespace
    from bear.scope import passes_gate
    refuse_overwrite(args.output)
    runs = [json.loads(Path(p).read_text()) for p in (args.compare or []) if Path(p).exists()]
    out: dict = {"provenance": bear_provenance(), "benchmarks": {}}
    for bn in args.benchmarks:
        bench = load_bench(bn)
        res = {}
        for side in SIDES:
            for kind in KINDS:
                for rate in args.rates:
                    per_seed = []
                    for seed in args.seeds:
                        qt, req = noisy_tags(bench, side, kind, rate, seed)
                        ex = np.zeros(len(bench.queries), np.int16)
                        for i, (q, _c, expected, _s) in enumerate(bench.queries):
                            ctx = Context(gate_tags=qt[i])
                            ex[i] = sum(1 for e in expected if not passes_gate(
                                SimpleNamespace(scope=SimpleNamespace(required_tags=req[e])), ctx))
                        per_seed.append(ex)
                    need = sum(len(q[2]) for q in bench.queries) * len(args.seeds)
                    tot = int(sum(x.sum() for x in per_seed))
                    entry = {"needed_gate_excluded": tot / need,
                             "queries_with_gate_excluded_needed": float(np.mean(
                                 np.concatenate([x > 0 for x in per_seed]))),
                             "per_seed_counts": [int(x.sum()) for x in per_seed]}
                    checks = {}
                    for run in runs:
                        for t in run["per_task"]:
                            sp = t["spec"]
                            if (sp["bench"] == bn and sp["arm"] == "gate_noise" and sp["side"] == side
                                    and sp["kind"] == kind and abs(sp["rate"] - rate) < 1e-9):
                                checks.setdefault(sp["backend"], {})[sp["seed"]] = int(np.sum(t["need_gate"]))
                    entry["trace_counts_by_backend"] = checks
                    entry["matches_trace"] = {b: [c.get(sd) for sd in args.seeds] == entry["per_seed_counts"]
                                              for b, c in checks.items()}
                    res[f"{side}_{kind}_{rate}"] = entry
        out["benchmarks"][bn] = res
        print(f"{bn}: over-restriction (share of needed items the noisy gate excludes)")
        for key, e in res.items():
            print(f"  {key:<20} {e['needed_gate_excluded']:.3f}   trace agrees: {e['matches_trace']}")
    args.output.write_text(json.dumps(out, default=json_default), encoding="utf-8")
    print(f"Wrote {args.output}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["embed", "run", "gatecheck"], required=True)
    ap.add_argument("--compare", nargs="*", default=None,
                    help="gatecheck: run files whose trace counts to check against.")
    ap.add_argument("--benchmarks", nargs="+", default=list(BENCHMARKS), choices=BENCHMARKS)
    ap.add_argument("--backends", nargs="+", default=DEFAULT_BACKENDS)
    ap.add_argument("--rates", nargs="+", type=float, default=list(RATES))
    ap.add_argument("--seeds", nargs="+", type=int, default=list(SEEDS))
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "tag_noise.json")
    ap.add_argument("--log-file", type=Path, default=REPO_ROOT / "results" / "tag_noise_output.txt")
    args = ap.parse_args()
    require_bear_040()
    if args.phase == "embed":
        phase_embed(args)
    elif args.phase == "gatecheck":
        phase_gatecheck(args)
    else:
        phase_run(args)


if __name__ == "__main__":
    main()
