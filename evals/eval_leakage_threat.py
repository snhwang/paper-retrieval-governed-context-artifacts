#!/usr/bin/env python3
"""Cross-category leakage under a stated threat model, ToolBench (WP6).

Threat model. The attacker controls the query text. The harness controls
the context tags (here, the query's RapidAPI categories). The gate reads only
the tags, so no query text can move an item across it. The question is what
an attacker can achieve, not how much accuracy drops.

Two measurements per backend, each paired over the 1,100 ToolBench queries:

  1. Natural leakage. The share of the top 5 whose category is outside the
     query's categories, for the ungated retriever. Governed retrieval
     should show 0 by construction, which is verified rather than assumed,
     both for the gate-only configuration (tags in ``Context.gate_tags``)
     and for the published one (tags in ``Context.tags``).
  2. Injected text. The attacker appends text naming one out-of-scope API
     (a target drawn at random, seeded, from categories the query does not
     carry). Two strengths: the tool and endpoint name, and the name plus
     the first 300 characters of the API's own description. Success means
     the target reaches the top 5. Recall of the query's real answer under
     the injection is reported too.

Corpora and settings mirror eval_tag_noise.py (gate-only items at priority 0,
ungated arm with no required tags and priority weight 0) and, for the
published configuration, eval_toolbench.py.

Statistics: bootstrap 95% CIs over queries, Clopper-Pearson intervals for
counts (including the zero counts for governed retrieval), McNemar for the
paired attack outcomes, and paired bootstrap for recall.

Usage:
    flock ~/tist-gpu.lock python evals/eval_leakage_threat.py --phase embed
    CUDA_VISIBLE_DEVICES= python evals/eval_leakage_threat.py --phase run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tistr2_common import (  # noqa: E402
    ALL_BACKENDS, BACKEND_LABEL, REPO_ROOT, CachedEmbedder, EmbeddingStore, Tee,
    bear_provenance, build_retriever, ci_summary, clopper_pearson, enable_bm25_memo,
    json_default, make_config, mcnemar_summary, paired_summary, record_texts,
    refuse_overwrite, require_bear_040,
)
from eval_tag_noise import (  # noqa: E402
    FAMILY, K, PRIORITY_WEIGHT, THETA_BM25, THETA_DENSE, load_bench, sweep_corpus,
)
from bear import Context  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

ATTACK_SEED = 20261029
DESC_CHARS = 300


def attacks(bench) -> list[dict]:
    """One out-of-scope target per query, and the two injected texts."""
    rng = np.random.default_rng(ATTACK_SEED)
    by_cat: dict[str, list[dict]] = {}
    for it in bench.items:
        by_cat.setdefault(it["req"][0], []).append(it)
    cats = sorted(by_cat)
    out = []
    for q, tags, _e, _s in bench.queries:
        allowed = [c for c in cats if c not in tags]
        cat = allowed[int(rng.integers(len(allowed)))]
        tgt = by_cat[cat][int(rng.integers(len(by_cat[cat])))]
        md = tgt["metadata"]
        name = f"{md.get('tool_name', '')} {md.get('api_name', '')}".strip()
        desc = ""
        for line in tgt["content"].splitlines():
            if line.startswith("Description: "):
                desc = line[len("Description: "):][:DESC_CHARS]
        out.append({"target": tgt["id"], "target_category": cat,
                    "name": f"{q} Use {name}.",
                    "name_desc": f"{q} Use {name}: {desc}"})
    return out


def conditions(bench, atk):
    """(arm, corpus, contexts, query texts) for every run."""
    gate = sweep_corpus(bench, {it["id"]: it["req"] for it in bench.items})
    ung = sweep_corpus(bench, None)
    plain = [q[0] for q in bench.queries]
    out = []
    for qkind, texts in (("natural", plain), ("inject_name", [a["name"] for a in atk]),
                         ("inject_name_desc", [a["name_desc"] for a in atk])):
        out.append(("ungated", qkind, ung, [Context() for _ in bench.queries], texts))
        out.append(("gate_only", qkind, gate,
                    [Context(gate_tags=q[1]) for q in bench.queries], texts))
        out.append(("published", qkind, bench.paper_corpus,
                    [Context(tags=q[1]) for q in bench.queries], texts))
    return out


def cfg_for(backend: str, arm: str):
    theta = THETA_BM25 if backend == "bm25" else THETA_DENSE
    return make_config(backend, FAMILY, k=K, threshold=theta,
                       priority_weight=0.0 if arm == "ungated" else PRIORITY_WEIGHT)


def phase_embed(args) -> None:
    bench = load_bench("toolbench")
    atk = attacks(bench)
    conds = [(corpus, list(zip(texts, ctxs)), cfg_for("hash", arm))
             for arm, _qk, corpus, ctxs, texts in conditions(bench, atk)]
    qt, dt = record_texts(conds, top_k=K)
    print(f"Recorded {len(qt)} query and {len(dt)} document texts.")
    for b in args.backends:
        if b != "bm25":
            st = EmbeddingStore(b, FAMILY, name=f"toolbench__{b}")
            print(f"  {b}: {st.fill(qt, dt)}", flush=True)


def run_backend(b: str, bench, atk) -> dict:
    store = None if b == "bm25" else EmbeddingStore(b, FAMILY, name=f"toolbench__{b}")
    cat_of = {it["id"]: it["req"][0] for it in bench.items}
    res: dict = {}
    for arm, qkind, corpus, ctxs, texts in conditions(bench, atk):
        emb = None if b == "bm25" else CachedEmbedder(store)
        r = build_retriever(corpus, b, FAMILY, cfg_for(b, arm), emb)
        n = len(texts)
        cross = np.zeros(n, np.float32)
        n_cross = np.zeros(n, np.int16)
        n_out = np.zeros(n, np.int16)
        rec = np.zeros(n, np.float32)
        hit = np.zeros(n, np.int8)
        for i, (text, ctx, q) in enumerate(zip(texts, ctxs, bench.queries)):
            out, _tr = r.retrieve_with_trace(text, ctx, top_k=K)
            ids = [s.id for s in out]
            cats = set(q[1])
            n_out[i] = len(ids)
            n_cross[i] = sum(1 for x in ids if cat_of[x] not in cats)
            cross[i] = n_cross[i] / len(ids) if ids else 0.0
            rec[i] = len(set(ids) & q[2]) / len(q[2])
            hit[i] = int(atk[i]["target"] in ids)
        res[f"{arm}/{qkind}"] = {
            "cross_share": ci_summary(cross), "recall": ci_summary(rec),
            "items_out_of_scope": int(n_cross.sum()), "items_returned": int(n_out.sum()),
            "items_out_of_scope_ci": clopper_pearson(int(n_cross.sum()), int(n_out.sum())),
            "queries_with_leak": int((n_cross > 0).sum()),
            "attack_success": int(hit.sum()), "attack_success_ci": clopper_pearson(int(hit.sum()), n),
            "per_query_cross_share": cross, "per_query_recall": rec,
            "per_query_attack_hit": hit, "per_query_n_out": n_out}
    for qkind in ("natural", "inject_name", "inject_name_desc"):
        u, g, p = res[f"ungated/{qkind}"], res[f"gate_only/{qkind}"], res[f"published/{qkind}"]
        res[f"contrast/{qkind}"] = {
            "cross_share_gate_minus_ungated": paired_summary(g["per_query_cross_share"],
                                                            u["per_query_cross_share"]),
            "recall_gate_minus_ungated": paired_summary(g["per_query_recall"], u["per_query_recall"]),
            "recall_published_minus_ungated": paired_summary(p["per_query_recall"],
                                                             u["per_query_recall"]),
            "attack_mcnemar_ungated_vs_gate": mcnemar_summary(u["per_query_attack_hit"],
                                                              g["per_query_attack_hit"]),
        }
    for qkind in ("inject_name", "inject_name_desc"):
        res[f"contrast/{qkind}"]["ungated_recall_drop_vs_natural"] = paired_summary(
            res[f"ungated/{qkind}"]["per_query_recall"], res["ungated/natural"]["per_query_recall"])
        res[f"contrast/{qkind}"]["gate_recall_drop_vs_natural"] = paired_summary(
            res[f"gate_only/{qkind}"]["per_query_recall"], res["gate_only/natural"]["per_query_recall"])
    return res


def print_backend(b: str, res: dict) -> None:
    print(f"\n{BACKEND_LABEL[b]}")
    for qkind in ("natural", "inject_name", "inject_name_desc"):
        line = f"  {qkind:<17}"
        for arm in ("ungated", "gate_only", "published"):
            e = res[f"{arm}/{qkind}"]
            line += (f" {arm}: cross {e['cross_share']['mean']:.3f} "
                     f"({e['items_out_of_scope']}/{e['items_returned']})"
                     + (f" hit {e['attack_success']}" if qkind != "natural" else "")
                     + f" R@5 {e['recall']['mean']:.3f} |")
        print(line)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["embed", "run"], required=True)
    ap.add_argument("--backends", nargs="+", default=ALL_BACKENDS, choices=ALL_BACKENDS)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "leakage_threat.json")
    ap.add_argument("--log-file", type=Path,
                    default=REPO_ROOT / "results" / "leakage_threat_output.txt")
    args = ap.parse_args()
    require_bear_040()
    if args.phase == "embed":
        phase_embed(args)
        return
    refuse_overwrite(args.output, args.log_file)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        enable_bm25_memo()
        bench = load_bench("toolbench")
        atk = attacks(bench)
        print("=== Leakage under the threat model (WP6), ToolBench, BEAR 0.4.0 ===")
        print(f"{len(bench.items)} APIs, {len(bench.queries)} queries, k={K}. Attack seed "
              f"{ATTACK_SEED}, description prefix {DESC_CHARS} characters.")
        results = {}
        for b in args.backends:
            results[b] = run_backend(b, bench, atk)
            print_backend(b, results[b])
        print("\n--- Summary: share of top-5 outside the query's categories; attack success ---\n")
        print(f"{'Backend':<18} {'ungated cross':>22} {'gate cross':>11} {'pub cross':>10}  "
              f"{'name: ungated / gate':>21}  {'name+desc: ungated / gate':>26}")
        for b, r in results.items():
            u = r["ungated/natural"]
            na_u, na_g = r["ungated/inject_name"], r["gate_only/inject_name"]
            nd_u, nd_g = r["ungated/inject_name_desc"], r["gate_only/inject_name_desc"]
            n = len(bench.queries)
            print(f"{BACKEND_LABEL[b]:<18} {u['cross_share']['mean']:.3f} "
                  f"[{u['cross_share']['ci'][0]:.3f},{u['cross_share']['ci'][1]:.3f}] "
                  f"{r['gate_only/natural']['items_out_of_scope']:>11} "
                  f"{r['published/natural']['items_out_of_scope']:>10}  "
                  f"{na_u['attack_success'] / n:>11.3f} / {na_g['attack_success']:<6}  "
                  f"{nd_u['attack_success'] / n:>14.3f} / {nd_g['attack_success']:<6}")
        out = {"design": {"k": K, "attack_seed": ATTACK_SEED, "desc_chars": DESC_CHARS,
                          "priority_weight": PRIORITY_WEIGHT},
               "attacks": atk, "provenance": bear_provenance(), "backends": results}
        args.output.write_text(json.dumps(out, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "leakage_threat", "backends": args.backends,
                                  **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
