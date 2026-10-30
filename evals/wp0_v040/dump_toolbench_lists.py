"""Dump per-query ranked retrieval lists (WP0 end-to-end decision, WP4 curves).

Runs under any BEAR the scripts support (0.1.10 or 0.4.0), using the
committed corpus loaders and ``eval_toolbench.build_retriever``, so the lists
are the ones the committed evals see.

Modes
  e2e            The corpus and conditions of eval_toolbench_e2e.py (Tables
                 7 to 9 feed these top-k lists to the LLM). k=5. Writes one
                 JSON per condition with the ordered ids, similarity and
                 final score of every retrieved item, and the per-query
                 recall, precision, F1 and NDCG computed as evaluate_e2e does.
  toolbench      The corpus and queries of eval_toolbench.py (Table 3). k=50.
  metatool-tags  MetaTool+Tags from eval_toolbench.py (Table 6). k=50.

For the two k=50 modes each condition is written as an .npz of corpus row
indices (-1 padded), similarities and final scores, plus a meta.json with the
corpus ids and each query's expected rows. A top-k prefix of these lists is
the governed or ungated top-k only if selection nests in k. The WP4 analysis
checks that against the k=5 runs.

--share-query-embeddings (0.4.0 only) embeds each query once per backend and
reuses the vector for the governed and ungated conditions. The index is built
as usual, then queries go through a cache in front of the retriever's own
embedder, so the vectors are the same ones the retriever would compute.

Conditions are written one file each and skipped when present, so an
interrupted run resumes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from bear import Context  # noqa: E402

import eval_toolbench as et  # noqa: E402
import wp0_common  # noqa: E402

BACKEND_LABEL = {
    "bge": "BGE", "bge-m3": "BGE-M3", "qwen3-0.6b": "Qwen3-0.6B",
    "qwen3-4b": "Qwen3-4B", "bm25": "BM25", "hash": "Hash", "nemotron": "Nemotron",
}


def conditions_for(backends: list[str]) -> list[dict]:
    out = []
    for b in backends:
        lab = BACKEND_LABEL[b]
        out.append({"name": f"BEAR+{lab} (gov)", "backend": b, "governance": True, "use_tags": True})
        out.append({"name": f"{lab} (no gov)", "backend": b, "governance": False, "use_tags": False})
    return out


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def build(corpus, backend: str, governance: bool):
    if backend == "nemotron":
        return wp0_common.nemotron_retriever(
            corpus, priority_weight=et.PRIORITY_WEIGHT if governance else 0.0,
            threshold=et.THRESHOLD, top_k=et.DEFAULT_TOP_K, mandatory_tags=[])
    r = et.build_retriever(corpus, backend=backend, governance=governance, mandatory_tags=[])
    wp0_common.assert_not_hash(r, backend)
    return r


class QueryCache:
    """Caches query vectors in front of a retriever's own embedder."""

    def __init__(self):
        self.store: dict[tuple[str, bool], np.ndarray] = {}
        self.hits = 0
        self.misses = 0

    def wrap(self, inner):
        cache = self

        class _Wrapped:
            def __getattr__(self, name):
                return getattr(inner, name)

            def embed_single(self, text, is_query=False):
                key = (text, bool(is_query))
                v = cache.store.get(key)
                if v is None:
                    cache.misses += 1
                    v = np.array(inner.embed_single(text, is_query=is_query), copy=True)
                    cache.store[key] = v
                else:
                    cache.hits += 1
                return v.copy()

            def embed(self, texts, is_query=False):
                return inner.embed(texts, is_query=is_query)

        return _Wrapped()


def free_gpu() -> None:
    """Collect garbage and return cached CUDA blocks. The caller drops its
    last reference to the retriever first."""
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# e2e mode
# ---------------------------------------------------------------------------

def run_e2e(args) -> None:
    import eval_toolbench_e2e as e2e
    corpus, queries = e2e.load_toolbench_data()
    if args.max_queries:
        queries = queries[:args.max_queries]
    stripped = et.strip_governance(corpus)
    k = args.top_k
    outdir = Path(args.outdir) / "e2e"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"e2e corpus {len(corpus)} APIs, {len(queries)} queries, k={k}")
    for cond in conditions_for(args.backends):
        path = outdir / f"{slug(cond['name'])}.json"
        if path.exists():
            print(f"  skip {cond['name']} (exists)")
            continue
        t0 = time.time()
        corp = corpus if cond["governance"] else stripped
        r = build(corp, cond["backend"], cond["governance"])
        ids, sims, scores = [], [], []
        rec, prec, f1, ndcg = [], [], [], []
        for q in queries:
            qtext, tags, expected = q[0], q[1], q[2]
            res = r.retrieve(qtext, Context(tags=tags if cond["use_tags"] else []), top_k=k)
            order = [x.id for x in res]
            ids.append(order)
            sims.append([float(getattr(x, "similarity", float("nan"))) for x in res])
            scores.append([float(getattr(x, "final_score", float("nan"))) for x in res])
            s = set(order)
            rec.append(et.recall_at_k(s, expected, k))
            prec.append(et.precision_at_k(s, expected, k))
            f1.append(et.f1_at_k(s, expected, k))
            ndcg.append(et.ndcg_at_k(order, expected, k))
        out = {"condition": cond["name"], "backend": cond["backend"], "top_k": k,
               "n_queries": len(queries), "ids": ids, "similarity": sims,
               "final_score": scores, "_recall_scores": rec, "_precision_scores": prec,
               "_f1_scores": f1, "_ndcg_scores": ndcg,
               "elapsed_s": time.time() - t0,
               "_provenance": wp0_common.provenance({"mode": "e2e"})}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(out), encoding="utf-8")
        os.replace(tmp, path)  # a killed run never leaves a partial file
        print(f"  {cond['name']}: recall@{k}={np.mean(rec):.4f} ({time.time() - t0:.0f}s)")
        r = None
        free_gpu()


# ---------------------------------------------------------------------------
# k=50 modes
# ---------------------------------------------------------------------------

def load_mode(mode: str):
    if mode == "toolbench":
        corpus, queries, _ = et.load_toolbench_corpus_and_queries()
    elif mode == "metatool-tags":
        tags_file = et.METATOOL_DIR / "plugin_tags.json"
        corpus, _ = et.load_metatool_corpus_tagged(tags_file)
        queries = et.load_metatool_queries_tagged(tags_file)
    else:
        raise ValueError(mode)
    return corpus, queries


def run_ranked(args) -> None:
    mode = args.mode
    corpus, queries = load_mode(mode)
    if args.max_queries:
        queries = queries[:args.max_queries]
    stripped = et.strip_governance(corpus)
    ids = [inst.id for inst in corpus]
    row = {iid: i for i, iid in enumerate(ids)}
    K = args.top_k
    outdir = Path(args.outdir) / mode
    outdir.mkdir(parents=True, exist_ok=True)
    meta_path = outdir / "meta.json"
    if not meta_path.exists():
        meta = {"mode": mode, "top_k": K, "corpus_ids": ids,
                "queries": [{"text": q[0], "tags": list(q[1]),
                             "expected": sorted(row[e] for e in q[2] if e in row),
                             "n_expected": len(q[2]),
                             "split": q[3] if len(q) > 3 else None} for q in queries],
                "_provenance": wp0_common.provenance({"mode": mode})}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    print(f"{mode}: corpus {len(corpus)}, queries {len(queries)}, k={K}")

    caches: dict[str, QueryCache] = {}
    for cond in conditions_for(args.backends):
        path = outdir / f"{slug(cond['name'])}.npz"
        if path.exists():
            print(f"  skip {cond['name']} (exists)")
            continue
        t0 = time.time()
        corp = corpus if cond["governance"] else stripped
        r = build(corp, cond["backend"], cond["governance"])
        qc = None
        if args.share_query_embeddings and cond["backend"] not in ("bm25",):
            qc = caches.setdefault(cond["backend"], QueryCache())
            r._embedder = qc.wrap(r._embedder)
        idx = np.full((len(queries), K), -1, dtype=np.int32)
        sim = np.full((len(queries), K), np.nan, dtype=np.float32)
        sco = np.full((len(queries), K), np.nan, dtype=np.float32)
        nret = np.zeros(len(queries), dtype=np.int32)
        for i, q in enumerate(queries):
            res = r.retrieve(q[0], Context(tags=list(q[1]) if cond["use_tags"] else []), top_k=K)
            nret[i] = len(res)
            for j, x in enumerate(res[:K]):
                idx[i, j] = row[x.id]
                sim[i, j] = float(getattr(x, "similarity", np.nan))
                sco[i, j] = float(getattr(x, "final_score", np.nan))
            if args.progress and (i + 1) % args.progress == 0:
                print(f"    {cond['name']}: {i + 1}/{len(queries)} ({time.time() - t0:.0f}s)", flush=True)
        # Nesting check: retrieve again at smaller k for a seeded sample of
        # queries and compare with the prefix of the k=K list.
        nest = None
        if args.nest_check:
            rng = np.random.default_rng(20261029)
            sample = sorted(rng.choice(len(queries), size=min(args.nest_check, len(queries)),
                                       replace=False).tolist())
            ks = [k for k in (1, 2, 3, 5, 10, 15, 16, 20, 25, 30, 40, 49) if k < K]
            mism = {str(k): 0 for k in ks}
            for i in sample:
                q = queries[i]
                ctx = Context(tags=list(q[1]) if cond["use_tags"] else [])
                for k in ks:
                    got = [row[x.id] for x in r.retrieve(q[0], ctx, top_k=k)]
                    pref = [int(v) for v in idx[i, :k] if v >= 0]
                    if got != pref:
                        mism[str(k)] += 1
            nest = {"n_sample": len(sample), "k_checked": ks, "mismatches": mism}
            print(f"    nesting check: {sum(mism.values())} mismatches over "
                  f"{len(sample)} queries x {len(ks)} k", flush=True)
        side_path = path.with_suffix(".json")
        tmp = path.with_name(path.stem + ".tmp.npz")
        np.savez_compressed(tmp, idx=idx, sim=sim, score=sco, n_returned=nret)
        side = {"condition": cond["name"], "backend": cond["backend"],
                "governance": cond["governance"], "use_tags": cond["use_tags"], "top_k": K,
                "nesting_check": nest,
                "elapsed_s": time.time() - t0,
                "query_cache": ({"hits": qc.hits, "misses": qc.misses} if qc else None),
                "_provenance": wp0_common.provenance({"mode": mode})}
        side_path.write_text(json.dumps(side, indent=2), encoding="utf-8")
        os.replace(tmp, path)  # the .npz appears last, so it marks completion
        print(f"  {cond['name']}: done ({time.time() - t0:.0f}s)"
              + (f", query cache hits={qc.hits} misses={qc.misses}" if qc else ""), flush=True)
        r = None
        free_gpu()
    # caches are per backend and conditions run backend by backend
    caches.clear()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["e2e", "toolbench", "metatool-tags"], required=True)
    ap.add_argument("--backends", nargs="+", required=True, choices=list(BACKEND_LABEL))
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--share-query-embeddings", action="store_true")
    ap.add_argument("--progress", type=int, default=0)
    ap.add_argument("--max-queries", type=int, default=0, help="Smoke tests only.")
    ap.add_argument("--nest-check", type=int, default=0,
                    help="Re-retrieve this many sampled queries at smaller k and "
                         "compare with the prefix of the k=top-k list.")
    args = ap.parse_args()
    if args.top_k is None:
        args.top_k = 5 if args.mode == "e2e" else 50
    print("BEAR:", json.dumps(wp0_common.bear_identity()))
    if args.mode == "e2e":
        run_e2e(args)
    else:
        run_ranked(args)


if __name__ == "__main__":
    main()
