#!/usr/bin/env python3
"""Do the WP2 and WP6 results move under BEAR 0.4.1? (backfill fix)

BEAR 0.4.1 changes one thing these scripts can reach. The required-tags
backfill (Step 3.5 of Retriever.retrieve) adds a gated instruction the search
did not return as a row of similarity 0: admitted only where its soft scope
matches or the threshold is at most 0, and scored priority_weight * p / 100
instead of p / 100. Config.restore_flat_backfill restores 0.4.0.

Where it can act. The backfill runs only when the search returned fewer rows
than the corpus holds and the context carries a tag. A dense search returns
every row for a gated query, and an ungated query has no tags, so dense
results cannot move. BM25 returns no row that shares no term with the query,
so BM25 results can. Mandatory injection (Step 4) is unchanged.

This script reruns, under the installed BEAR, everything BM25 contributed to
the committed results and compares it item by item with the committed 0.4.0
files:

  tag noise    every BM25 task of results/tag_noise.json (both benchmarks,
               ungated, gate-only at priority 0 and 50, published config, and
               all 150 noise conditions per benchmark), per-query arrays.
  mandatory    WP2 arms A to D on BM25, per query-rule pair
               (results/mandatory_coverage.json).
  leakage      the nine BM25 arm-by-query runs (results/leakage_threat.json).
  giveaways    derived from the tag-noise arrays. Recomputed for BM25 only if
               those arrays changed.

A hash spot check (dense, cached vectors, no model) reruns the tag-noise
ungated, gate-only and published arms and the WP2 arms, which should be
identical by construction.

The headline is the BM25 gate-only arm at priority 50. Under 0.4.0 it scored
0.592 (ToolBench) and 0.795 (MetaTool+Tags), below the priority-0 order
(0.604, 0.812), because the backfill ranked zero-overlap rows first. bear-dev
predicts the priority-0 numbers under 0.4.1.

No model is loaded. Run in WSL under the memory cap, with at most 8 workers:
    systemd-run --user --scope --slice=tist.slice -p MemoryMax=24G -p MemorySwapMax=0 \\
        env CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1 python evals/check_bm25_v041.py --workers 8
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bear  # noqa: E402
from tistr2_common import (  # noqa: E402
    REPO_ROOT, EmbeddingStore, Tee, bear_provenance, ci_summary, enable_bm25_memo,
    json_default, paired_summary, refuse_overwrite, require_bear_040,
)
import eval_tag_noise as tn  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

ARRAYS = ("recall", "ndcg", "n_out", "need", "need_got", "need_gate", "adm_oos", "top_oos")
DTYPES = {"recall": np.float32, "ndcg": np.float32, "n_out": np.int16, "need": np.int16,
          "need_got": np.int16, "need_gate": np.int16, "adm_oos": np.int32,
          "top_oos": np.int16}


def spec_key(spec: dict) -> tuple:
    return tuple(sorted((k, v) for k, v in spec.items()))


def tag_noise_specs(benches, with_hash: bool) -> list[dict]:
    specs = tn.all_specs(benches, ["bm25"], list(tn.RATES), list(tn.SEEDS))
    if with_hash:
        for bn in benches:
            for arm in ("ungated", "gate_clean", "paper_governed"):
                specs.append({"bench": bn, "backend": "hash", "arm": arm})
    return specs


def compare_task(new: dict, old: dict) -> dict:
    out = {"identical": True, "arrays_differing": {}}
    for a in ARRAYS:
        x = np.asarray(new[a], dtype=DTYPES[a])
        y = np.asarray(old[a], dtype=DTYPES[a])
        if x.shape != y.shape or not np.array_equal(x, y):
            out["identical"] = False
            out["arrays_differing"][a] = int(np.sum(x != y)) if x.shape == y.shape else "shape"
    out["recall_new"] = float(np.mean(new["recall"]))
    out["recall_old"] = float(np.mean(old["recall"]))
    return out


def part_tag_noise(args, log) -> dict:
    benches = list(tn.BENCHMARKS)
    for bn in benches:
        tn.G_BENCH[bn] = tn.load_bench(bn)
        if not args.no_hash:
            tn.G_STORE[(bn, "hash")] = EmbeddingStore("hash", tn.FAMILY, name=f"{bn}__hash")
    specs = tag_noise_specs(benches, not args.no_hash)
    print(f"tag noise: {len(specs)} tasks, {args.workers} workers", flush=True)
    t0 = time.time()
    new = []
    with mp.get_context("fork").Pool(args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(tn.run_task, specs), 1):
            new.append(res)
            if i % 25 == 0 or i == len(specs):
                print(f"  {i}/{len(specs)} tasks, {time.time() - t0:.0f}s", flush=True)
    # Load the committed results only now, so the workers never hold them.
    old_doc = json.loads(args.tag_noise.read_text())
    old = {spec_key(t["spec"]): t for t in old_doc["per_task"]}
    del old_doc
    rows, n_ident, n_missing = [], 0, 0
    for res in sorted(new, key=lambda r: json.dumps(r["spec"], sort_keys=True)):
        o = old.get(spec_key(res["spec"]))
        if o is None:
            n_missing += 1
            rows.append({"spec": res["spec"], "missing_in_committed": True})
            continue
        c = compare_task(res, o)
        n_ident += c["identical"]
        rows.append({"spec": res["spec"], **c})
    del old
    out = {"n_tasks": len(new), "n_identical": n_ident, "n_missing_in_committed": n_missing,
           "differing": [r for r in rows if not r.get("identical", False)]}
    # The priority-50 gate-only arm, against priority 0, under this BEAR.
    by = {spec_key(r["spec"]): r for r in new}
    out["priority50"] = {}
    for bn in benches:
        p50 = by[spec_key({"bench": bn, "backend": "bm25", "arm": "gate_clean", "priority": 50})]
        p0 = by[spec_key({"bench": bn, "backend": "bm25", "arm": "gate_clean"})]
        out["priority50"][bn] = {
            "recall_p50": ci_summary(p50["recall"]), "recall_p0": ci_summary(p0["recall"]),
            "p50_minus_p0": paired_summary(p50["recall"], p0["recall"]),
            "ndcg_p50": ci_summary(p50["ndcg"]), "ndcg_p0": ci_summary(p0["ndcg"]),
            "queries_with_different_recall": int(np.sum(p50["recall"] != p0["recall"])),
            "per_query_recall_p50": p50["recall"]}
    # Arrays the giveaway strata use, for part_giveaways.
    out["_arrays"] = {(r["spec"]["bench"], r["spec"]["backend"], r["spec"]["arm"]): r["recall"]
                      for r in new if r["spec"]["arm"] in ("ungated", "gate_clean", "paper_governed")
                      and "priority" not in r["spec"]}
    return out


def part_mandatory(args) -> dict:
    import eval_mandatory_coverage as mc
    from eval_governance_decomposed import discover_safety_ids, load_pet_sim_corpus
    base = load_pet_sim_corpus()
    safety_ids = sorted(discover_safety_ids(base))
    queries = mc.load_queries()
    backends = ["bm25"] + ([] if args.no_hash else ["hash"])
    ns = argparse.Namespace(backends=backends)
    new = mc.phase_run(ns, base, safety_ids, queries)
    old = json.loads(args.mandatory.read_text())["backends"]
    out = {}
    for b in backends:
        e = {}
        for arm, pairs in new[b]["pairs"].items():
            op = old[b]["pairs"][arm]
            keys = ("q", "rule", "present", "admitted_by", "excluded_reason")
            diff = [i for i, (x, y) in enumerate(zip(pairs, op))
                    if any(x[k] != y[k] for k in keys)
                    or (x["similarity"] is None) != (y["similarity"] is None)
                    or (x["similarity"] is not None and abs(x["similarity"] - y["similarity"]) > 1e-9)]
            present_diff = sum(1 for x, y in zip(pairs, op) if x["present"] != y["present"])
            e[arm] = {"pairs": len(pairs), "pairs_differing": len(diff),
                      "presence_differing": present_diff,
                      "examples": [{"new": pairs[i], "old": op[i]} for i in diff[:3]]}
        e["theta_b_new"] = new[b]["B_verified_unreachable"]["theta_b"]
        e["theta_b_old"] = old[b]["B_verified_unreachable"]["theta_b"]
        out[b] = e
    return out


def part_leakage(args) -> dict:
    import eval_leakage_threat as lk
    bench = tn.load_bench("toolbench")
    atk = lk.attacks(bench)
    new = lk.run_backend("bm25", bench, atk)
    old = json.loads(args.leakage.read_text())["backends"]["bm25"]
    out = {}
    for key, e in new.items():
        if key.startswith("contrast/"):
            continue
        d = {}
        for a in ("per_query_cross_share", "per_query_recall", "per_query_attack_hit",
                  "per_query_n_out"):
            x, y = np.asarray(e[a], dtype=float), np.asarray(old[key][a], dtype=float)
            d[a] = int(np.sum(np.abs(x - y) > 1e-6))
        out[key] = {"queries_differing": d, "identical": not any(d.values()),
                    "recall_new": float(np.mean(e["per_query_recall"])),
                    "recall_old": float(np.mean(old[key]["per_query_recall"])),
                    "attack_hits_new": int(np.sum(e["per_query_attack_hit"])),
                    "attack_hits_old": int(np.sum(old[key]["per_query_attack_hit"]))}
    return out


def part_giveaways(args, arrays: dict) -> dict:
    import eval_query_giveaways as gw
    doc = json.loads(args.giveaways.read_text())
    out = {}
    for bn in tn.BENCHMARKS:
        flags = doc["benchmarks"][bn]["flags"]
        new = {arm: np.asarray(arrays[(bn, "bm25", arm)], float)
               for arm in ("ungated", "gate_clean", "paper_governed")}
        st = gw.stratify(flags, new)
        old = doc["benchmarks"][bn]["backends"]["bm25"]
        out[bn] = {"effect_difference_new": st.get("effect_difference_gate_clean"),
                   "effect_difference_old": old.get("effect_difference_gate_clean"),
                   "giveaway_paper_governed_new": st["giveaway"]["paper_governed"],
                   "giveaway_paper_governed_old": old["giveaway"]["paper_governed"],
                   "no_giveaway_paper_governed_new": st["no_giveaway"]["paper_governed"],
                   "no_giveaway_paper_governed_old": old["no_giveaway"]["paper_governed"]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-hash", action="store_true", help="Skip the dense (hash) spot check.")
    ap.add_argument("--tag-noise", type=Path, default=REPO_ROOT / "results" / "tag_noise.json")
    ap.add_argument("--mandatory", type=Path,
                    default=REPO_ROOT / "results" / "mandatory_coverage.json")
    ap.add_argument("--leakage", type=Path, default=REPO_ROOT / "results" / "leakage_threat.json")
    ap.add_argument("--giveaways", type=Path,
                    default=REPO_ROOT / "results" / "query_giveaways.json")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "bm25_v041_check.json")
    ap.add_argument("--log-file", type=Path,
                    default=REPO_ROOT / "results" / "bm25_v041_check_output.txt")
    args = ap.parse_args()
    if args.workers > 8:
        raise SystemExit("At most 8 workers (memory rule).")
    require_bear_040()
    refuse_overwrite(args.output, args.log_file)
    for p in (args.tag_noise, args.mandatory, args.leakage, args.giveaways):
        if not p.exists():
            raise SystemExit(f"Committed result {p} is missing.")
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        print(f"=== BM25 results under BEAR {bear.__version__} against the committed 0.4.0 runs ===")
        enable_bm25_memo()
        res: dict = {"provenance": bear_provenance()}
        tnr = part_tag_noise(args, log)
        arrays = tnr.pop("_arrays")
        res["tag_noise"] = tnr
        print(f"\ntag noise: {tnr['n_identical']}/{tnr['n_tasks']} tasks identical to 0.4.0 "
              f"({tnr['n_missing_in_committed']} not in the committed file)")
        for r in tnr["differing"]:
            print(f"  differs: {r['spec']}  recall {r.get('recall_old', float('nan')):.4f} -> "
                  f"{r.get('recall_new', float('nan')):.4f}  arrays {r.get('arrays_differing')}")
        for bn, e in tnr["priority50"].items():
            d = e["p50_minus_p0"]
            print(f"  {bn}: gate-only BM25 at priority 50 Recall@5 {e['recall_p50']['mean']:.4f} "
                  f"[{e['recall_p50']['ci'][0]:.4f}, {e['recall_p50']['ci'][1]:.4f}], priority 0 "
                  f"{e['recall_p0']['mean']:.4f}, difference {d['delta']:+.4f} "
                  f"[{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}], queries differing "
                  f"{e['queries_with_different_recall']}")
        res["mandatory_coverage"] = part_mandatory(args)
        print("\nmandatory coverage (pairs differing from 0.4.0, of which presence):")
        for b, e in res["mandatory_coverage"].items():
            cells = ", ".join(f"{arm} {v['pairs_differing']}/{v['pairs']} ({v['presence_differing']})"
                              for arm, v in e.items() if isinstance(v, dict))
            print(f"  {b}: {cells}; theta_b {e['theta_b_old']} -> {e['theta_b_new']}")
        res["leakage"] = part_leakage(args)
        print("\nleakage, BM25 (queries differing from 0.4.0):")
        for key, e in res["leakage"].items():
            print(f"  {key:<28} identical={e['identical']}  recall {e['recall_old']:.4f} -> "
                  f"{e['recall_new']:.4f}  attack hits {e['attack_hits_old']} -> {e['attack_hits_new']}"
                  + ("" if e["identical"] else f"  {e['queries_differing']}"))
        changed = any(r["spec"]["backend"] == "bm25" and r["spec"]["arm"] in
                      ("ungated", "gate_clean", "paper_governed") and "priority" not in r["spec"]
                      for r in tnr["differing"])
        res["giveaways"] = {"bm25_arrays_changed": changed}
        if changed:
            res["giveaways"]["recomputed"] = part_giveaways(args, arrays)
            print("\ngiveaways: BM25 arrays changed, strata recomputed (see JSON)")
        else:
            print("\ngiveaways: the BM25 arrays they use are unchanged, so the strata are too")
        args.output.write_text(json.dumps(res, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "check_bm25_v041", **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
