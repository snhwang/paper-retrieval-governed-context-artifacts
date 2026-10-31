#!/usr/bin/env python3
"""WP5a, Nemotron encoder: the two BEAR rows on the installed BEAR, from cache.

eval_metadata_filter_baseline.py embeds live through the Nemotron service
(port 8360). This script reruns only the rows that depend on BEAR's
retrieval, "BEAR, governed" (bear_gov) and "BEAR, no governance"
(bear_nogov), with Nemotron vectors served from the stores in
~/.cache/tist-r2-embeddings (CachedEmbedder, which raises on a missing text).
It sends no request to the Nemotron service: TIST_NEMOTRON_URL is set to an
unreachable address before anything is imported.

The LlamaIndex arms (li_plain, li_filter and, on Pet Sim, the overlap and
containment filters with and without the safety rule) do not use BEAR's
retrieval, only BEAR's corpus loaders and gate check for the metrics. They
are taken unchanged from the 0.4.0 file, and every contrast is recomputed
from the per-query arrays.

Steps:
  1. Coverage. Record every text the two BEAR arms embed (RecordingEmbedder)
     and count what the store lacks. Anything missing stops the run.
  2. Vector check. Rerun the two arms with the 0.4.0 behavior restored
     (restore_flat_backfill, which implies restore_dropped_rows, and
     restore_tie_order) and compare the ranked lists with the lists the 0.4.0
     run saved from its live embeddings. Identical lists mean the cached
     vectors rank as the live ones did, so the BEAR and LlamaIndex rows stay
     comparable. The store's service identity (model id) is recorded too.
  3. The two arms as released, metrics, and the merged result.

Usage:
    TIST_NEMOTRON_URL=http://127.0.0.1:9 CUDA_VISIBLE_DEVICES= \\
        python evals/rerun_filter_baseline_bear_cached.py --corpus toolbench \\
        --old results/metadata_filter_baseline_toolbench_nemotron.json \\
        --output results/metadata_filter_baseline_toolbench_nemotron_v042.json \\
        --log-file results/metadata_filter_baseline_toolbench_nemotron_v042_output.txt
"""

from __future__ import annotations

import os

# Before tistr2_common is imported: no request can reach the Nemotron service.
os.environ["TIST_NEMOTRON_URL"] = os.environ.get("TIST_NEMOTRON_URL_OVERRIDE", "http://127.0.0.1:9")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bear  # noqa: E402
from bear import Context, Retriever  # noqa: E402
from bear.scope import passes_gate  # noqa: E402
import eval_metadata_filter_baseline as mf  # noqa: E402
from tistr2_common import (  # noqa: E402
    CachedEmbedder, EmbeddingStore, RecordingEmbedder, Tee, bear_provenance, ci_summary,
    fmt, fmt_delta, json_default, ndcg, paired_summary, prf, refuse_overwrite,
    store_provenance,
)
from repro_footer import print_repro_footer  # noqa: E402

BEAR_ARMS = ("bear_gov", "bear_nogov")
RESTORE_040 = {"restore_flat_backfill": True, "restore_tie_order": True}


def retrievers(corpus_name: str, corpus, embedder, extra: dict | None = None):
    cfg_g = mf.bear_config(corpus_name, "nemotron", True)
    cfg_n = mf.bear_config(corpus_name, "nemotron", False)
    if extra:
        cfg_g = cfg_g.model_copy(update=extra)
        cfg_n = cfg_n.model_copy(update=extra)
    r_gov = Retriever(corpus, config=cfg_g, embedder=embedder)
    r_gov.build_index()
    r_nogov = Retriever(mf.strip_for_nogov(corpus, corpus_name), config=cfg_n, embedder=embedder)
    r_nogov.build_index()
    return r_gov, r_nogov


def bear_lists(corpus_name: str, corpus, queries, embedder, extra=None) -> dict:
    k = mf.SETTINGS[corpus_name]["k"]
    r_gov, r_nogov = retrievers(corpus_name, corpus, embedder, extra)
    out = {a: [] for a in BEAR_ARMS}
    for q, tags, _e, _r, _s in queries:
        out["bear_gov"].append([x.id for x in r_gov.retrieve(q, Context(tags=tags), top_k=k)])
        nogov_ctx = Context(tags=tags) if corpus_name == "petsim" else Context()
        out["bear_nogov"].append([x.id for x in r_nogov.retrieve(q, nogov_ctx, top_k=k)])
    return out


def metrics(corpus_name: str, corpus, queries, ids_per_query) -> dict:
    """The per-query metrics of eval_metadata_filter_baseline.run_encoder."""
    k = mf.SETTINGS[corpus_name]["k"]
    inst_by_id = {i.id: i for i in corpus}
    m: dict[str, list] = {"recall": [], "precision": [], "f1": [], "ndcg": [],
                          "gate_violations": [], "n_out": []}
    if corpus_name == "petsim":
        m.update(recall_relaxed=[], f1_relaxed=[])
    for (q, tags, exp, rel, _s), ids in zip(queries, ids_per_query):
        got = set(ids)
        p_, r_, f_ = prf(got, exp)
        m["recall"].append(r_)
        m["precision"].append(p_)
        m["f1"].append(f_)
        m["ndcg"].append(ndcg(ids, exp, k))
        m["n_out"].append(len(ids))
        ctx = Context(tags=tags)
        m["gate_violations"].append(sum(1 for x in ids if not passes_gate(inst_by_id[x], ctx)))
        if rel is not None:
            _, rr, fr = prf(got, rel)
            m["recall_relaxed"].append(rr)
            m["f1_relaxed"].append(fr)
    return {key: np.asarray(v, dtype=float) for key, v in m.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", choices=["toolbench", "petsim"], required=True)
    ap.add_argument("--old", type=Path, required=True, help="The 0.4.0 Nemotron result file.")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--log-file", type=Path, required=True)
    args = ap.parse_args()
    if bear.__version__ != "0.4.2":
        raise SystemExit(f"BEAR {bear.__version__} is installed, 0.4.2 is expected.")
    refuse_overwrite(args.output, args.log_file)
    old = json.loads(args.old.read_text())
    old_enc = old["encoders"]["nemotron"]
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        corpus, queries = mf.load(args.corpus)
        name = f"{args.corpus}__nemotron"
        print(f"=== WP5a {args.corpus}, Nemotron: BEAR rows on BEAR {bear.__version__} from the "
              f"cached store {name}; LlamaIndex rows from {args.old.name} ===")
        if [q[0] for q in queries] != [x["query"] for x in old["queries"]]:
            raise SystemExit("The queries differ from the 0.4.0 file.")

        # 1. Coverage, without any vectors.
        rec = RecordingEmbedder()
        bear_lists(args.corpus, corpus, queries, rec)
        store = EmbeddingStore("nemotron", args.corpus, name=name)
        mq, md = store.missing(list(rec.queries), list(rec.docs))
        sp = store_provenance(name)
        print(f"coverage: the BEAR arms embed {len(rec.queries)} query and {len(rec.docs)} document "
              f"texts; the store lacks {len(mq)} and {len(md)}")
        print(f"store: {sp.get('model')}, identity {sp.get('service_identity')}, "
              f"filled {sp.get('embedded_utc')}")
        if mq or md:
            miss = {"missing_queries": mq[:20], "missing_docs": md[:20],
                    "n_missing_queries": len(mq), "n_missing_docs": len(md)}
            args.output.with_name(args.output.stem + "_missing.json").write_text(
                json.dumps(miss, indent=1), encoding="utf-8")
            raise SystemExit("Texts missing from the cache. Not calling the service. Stopping.")
        cached = CachedEmbedder(store)

        # 2. Vector check against the live 0.4.0 lists.
        restored = bear_lists(args.corpus, corpus, queries, cached, RESTORE_040)
        check = {}
        for a in BEAR_ARMS:
            same = sum(x == y for x, y in zip(restored[a], old_enc["lists"][a]))
            same_set = sum(set(x) == set(y) for x, y in zip(restored[a], old_enc["lists"][a]))
            check[a] = {"queries": len(queries), "identical_lists": same, "identical_sets": same_set}
            print(f"vector check, {a} with 0.4.0 behavior restored: {same}/{len(queries)} lists "
                  f"identical to the live 0.4.0 run ({same_set} as sets)")
        vectors_match = all(c["identical_lists"] == c["queries"] for c in check.values())

        # 3. The two arms as released.
        new_lists = bear_lists(args.corpus, corpus, queries, cached)
        per = {a: metrics(args.corpus, corpus, queries, new_lists[a]) for a in BEAR_ARMS}
        for a in BEAR_ARMS:
            moved = sum(x != y for x, y in zip(new_lists[a], old_enc["lists"][a]))
            print(f"0.4.2 against 0.4.0, {a}: {moved}/{len(queries)} lists differ")
        li_arms = [a for a in old_enc["arms"] if a not in BEAR_ARMS]
        for a in li_arms:
            per[a] = {key: np.asarray(v, dtype=float) for key, v in old_enc["per_query"][a].items()}

        res = {"arms": {}, "contrasts": {}, "per_query": {}, "lists": {}}
        for a in list(BEAR_ARMS) + li_arms:
            if a in BEAR_ARMS:
                res["arms"][a] = {mm: ci_summary(per[a][mm]) for mm in per[a]}
                res["arms"][a]["items_failing_gate"] = int(per[a]["gate_violations"].sum())
                res["arms"][a]["items_returned"] = int(per[a]["n_out"].sum())
                res["lists"][a] = new_lists[a]
            else:
                res["arms"][a] = old_enc["arms"][a]
                res["lists"][a] = old_enc["lists"][a]
            res["per_query"][a] = per[a]
        for key in old_enc["contrasts"]:
            pair, mm = key.split("__")
            a, b = pair.split("_vs_")
            res["contrasts"][key] = paired_summary(per[a][mm], per[b][mm])
        if args.corpus == "toolbench":
            splits = sorted({q[4] for q in queries})
            res["by_split"] = {sp_: {a: float(np.mean([v for v, q in zip(per[a]["recall"], queries)
                                                        if q[4] == sp_])) for a in per} for sp_ in splits}
            res["identical_top5_li_filter_vs_bear_gov"] = int(sum(
                set(x) == set(y) for x, y in zip(res["lists"]["li_filter"], res["lists"]["bear_gov"])))
        mf.print_encoder(args.corpus, "nemotron", res)

        out = {**{k: old[k] for k in ("corpus", "settings", "llama_index_core", "n_items",
                                      "n_queries", "queries")},
               "provenance": {**bear_provenance(),
                              "bear_rows": f"rerun on BEAR {bear.__version__} with cached Nemotron "
                                           f"vectors (store {name}), no request to the service",
                              "llama_index_rows": f"reused unchanged from {args.old.name} "
                                                  f"(BEAR {old['provenance'].get('bear_version')}); "
                                                  "they do not use BEAR's retrieval",
                              "embedding_store": sp,
                              "vector_check": check, "vectors_match_live_040": vectors_match},
               "encoders": {"nemotron": res}}
        args.output.write_text(json.dumps(out, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "rerun_filter_baseline_bear_cached",
                                  "corpus": args.corpus, **bear_provenance()})
        if not vectors_match:
            print("NOTE: the cached vectors do not reproduce every live 0.4.0 list. See the vector check.")
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
