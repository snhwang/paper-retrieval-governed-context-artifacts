#!/usr/bin/env python3
"""Do the BM25 results move under BEAR 0.4.2, and which change moves them?

BEAR 0.4.2 (bear-dev 9d085b4) changes three things a BM25 run can reach,
each with a Config switch that restores the earlier behavior:

  restore_flat_backfill   0.4.1: a gated row the search did not return is
                          backfilled at similarity 0, admitted only where its
                          soft scope matches or theta <= 0, and scored
                          priority_weight * p / 100. The switch restores the
                          0.4.0 backfill (admitted always, scored p / 100). It
                          also implies restore_dropped_rows.
  restore_dropped_rows    0.4.2: BM25 returns every row. A row with no term in
                          common with the query is a row of similarity 0, so
                          the threshold admits it where theta <= 0 or the soft
                          scope matches.
  restore_tie_order       0.4.2: exact score ties are ordered by priority and
                          then id, not by the numpy build's order.

This script reruns everything BM25 contributed to the committed 0.4.0 results
(tag noise, WP2 mandatory coverage, WP6 leakage, query giveaways; see
check_bm25_v041.py for the parts) under the installed 0.4.2, with zero or
more switches on, and compares each item with the 0.4.0 files. One run per
invocation, so each is its own job under the memory cap:

    default                    0.4.2 as released
    flat_backfill              one switch at a time
    dropped_rows
    tie_order
    flat_backfill tie_order    all three (flat_backfill implies dropped_rows),
                               which should reproduce 0.4.0 exactly

Then --summarize reads the runs and attributes every item that moved to the
switch that restores it.

The reference tag_noise.json (345 MB) is the local 0.4.0 run. Only its
printout, results/tag_noise_output.txt, is committed. The other three
references are committed.

No model is loaded. Run in WSL under the cap, with at most 8 workers:
    tist-capped --mem 12G -- env CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1 \\
        python evals/check_bm25_v042.py --switches tie_order --workers 8
    python evals/check_bm25_v042.py --summarize
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bear  # noqa: E402
from bear import Config  # noqa: E402
import tistr2_common as tc  # noqa: E402
from tistr2_common import (  # noqa: E402
    REPO_ROOT, Tee, bear_provenance, json_default, refuse_overwrite,
)
import check_bm25_v041 as v041  # noqa: E402
import eval_tag_noise as tn  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

SWITCHES = ("flat_backfill", "dropped_rows", "tie_order")
RUNS = ("default", "flat_backfill", "dropped_rows", "tie_order", "flat_backfill+tie_order")
SINGLE = ("flat_backfill", "dropped_rows", "tie_order")
ALL = "flat_backfill+tie_order"
RESULTS = REPO_ROOT / "results"


def run_name(switches: list[str]) -> str:
    return "+".join(switches) if switches else "default"


def run_paths(name: str) -> dict[str, Path]:
    stem = RESULTS / f"bm25_v042_check_{name}"
    return {"output": stem.with_suffix(".json"),
            "log_file": Path(f"{stem}_output.txt"),
            "arrays": Path(f"{stem}_recall.npz")}


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------

def one_run(args) -> None:
    if bear.__version__ != "0.4.2":
        raise SystemExit(f"BEAR {bear.__version__} is installed. This check expects 0.4.2.")
    if args.workers > 8:
        raise SystemExit("At most 8 workers (memory rule).")
    switches = list(dict.fromkeys(args.switches))
    for s in switches:
        if f"restore_{s}" not in Config.model_fields:
            raise SystemExit(f"BEAR {bear.__version__} has no Config.restore_{s}.")
    name = run_name(switches)
    paths = run_paths(name)
    for key in ("output", "log_file", "arrays"):
        if getattr(args, key) is None:
            setattr(args, key, paths[key])
    refuse_overwrite(args.output, args.log_file, args.arrays)
    for p in (args.tag_noise, args.mandatory, args.leakage, args.giveaways):
        if not p.exists():
            raise SystemExit(f"Reference result {p} is missing.")

    tc.CONFIG_OVERRIDES.clear()
    tc.CONFIG_OVERRIDES.update({f"restore_{s}": True for s in switches})
    probe = tc.make_config("bm25", tn.FAMILY, k=5, threshold=0.0, priority_weight=0.3)
    effective = {f: bool(getattr(probe, f)) for f in Config.model_fields if f.startswith("restore_")}
    assert all(effective[f"restore_{s}"] for s in switches)

    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        print(f"=== BM25 results under BEAR {bear.__version__}, run '{name}', against the "
              f"0.4.0 runs ===")
        print(f"switches on: {switches or 'none'}  (Config restore fields: "
              f"{ {f: v for f, v in effective.items() if v} or 'none'})")
        if "flat_backfill" in switches:
            print("restore_flat_backfill implies restore_dropped_rows in BEAR 0.4.2.")
        if args.smoke:
            print("SMOKE: no noise conditions, no leakage.")
        res = v041.run_check(args, log)
        recall = res["tag_noise"].pop("_differing_recall")
        keys = {f"t{i:04d}": sid for i, sid in enumerate(sorted(recall))}
        np.savez_compressed(args.arrays, **{k: recall[sid] for k, sid in keys.items()})
        res["tag_noise"]["differing_recall_arrays"] = {"file": args.arrays.name, "keys": keys}
        res["run"] = {"name": name, "switches": switches, "config_overrides": dict(tc.CONFIG_OVERRIDES),
                      "restore_fields_effective": effective, "smoke": bool(args.smoke)}
        args.output.write_text(json.dumps(res, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output} and {args.arrays}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "check_bm25_v042", "run": name, **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def _task_group(spec: dict) -> str:
    if spec["arm"] == "gate_noise":
        return f"{spec['bench']}/{spec['backend']}/gate_noise"
    p = f"/p{spec['priority']}" if "priority" in spec else ""
    return f"{spec['bench']}/{spec['backend']}/{spec['arm']}{p}"


def summarize(args) -> None:
    out_path = args.output or RESULTS / "bm25_v042_check_attribution.json"
    log_path = args.log_file or RESULTS / "bm25_v042_check_attribution_output.txt"
    refuse_overwrite(out_path, log_path)
    docs = {}
    for n in RUNS:
        p = run_paths(n)["output"]
        if not p.exists():
            raise SystemExit(f"Run '{n}' is missing ({p}).")
        docs[n] = json.loads(p.read_text(encoding="utf-8"))
        if docs[n]["run"].get("smoke"):
            raise SystemExit(f"Run '{n}' is a smoke run.")
    log = log_path.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        res = {"runs": {n: d["run"] for n, d in docs.items()},
               "provenance": docs["default"]["provenance"]}
        print("=== BM25 under BEAR 0.4.2 against 0.4.0: attribution to the restore switches ===")
        print(f"BEAR {res['provenance'].get('bear_version')} "
              f"{res['provenance'].get('bear_source_sha')}\n")
        print("A run 'restores' an item when the item is identical to 0.4.0 under that run.")
        print("'Changes' counts items whose result differs from the 0.4.2 default run.\n")

        # Tag noise, per task.
        tn_res = {}
        diff = {n: {v041.spec_id(r["spec"]): r for r in d["tag_noise"]["differing"]}
                for n, d in docs.items()}
        dig = {n: d["tag_noise"]["digests"] for n, d in docs.items()}
        tasks = sorted(dig["default"])
        groups: dict = {}
        per_task = {}
        for t in tasks:
            spec = json.loads(t)
            g = _task_group(spec)
            moved = t in diff["default"]
            restored_by = [n for n in SINGLE if moved and t not in diff[n]]
            all_restores = moved and t not in diff[ALL]
            changes = {n: dig[n].get(t) != dig["default"][t] for n in RUNS if n != "default"}
            if not moved:
                cause = "unchanged"
            elif len(restored_by) == 1:
                cause = restored_by[0]
            elif len(restored_by) > 1:
                cause = "several singles"
            elif all_restores:
                cause = "only all three together"
            else:
                cause = "not restored"
            per_task[t] = {"group": g, "moved": moved, "cause": cause,
                           "restored_by": restored_by, "all_three_restore": all_restores,
                           "changes_vs_default": changes}
            gg = groups.setdefault(g, {"tasks": 0, "moved": 0, "causes": {},
                                       "changed_by": {n: 0 for n in RUNS if n != "default"}})
            gg["tasks"] += 1
            gg["moved"] += moved
            gg["causes"][cause] = gg["causes"].get(cause, 0) + 1
            for n, c in changes.items():
                gg["changed_by"][n] += c
        tn_res["groups"] = groups
        tn_res["per_task"] = per_task
        print("--- Tag noise (tasks per group) ---")
        print(f"{'group':<40} {'tasks':>5} {'moved':>5}  cause of the move (tasks)   "
              f"| tasks each run changes vs 0.4.2")
        for g, e in sorted(groups.items()):
            causes = ", ".join(f"{c} {k}" for c, k in sorted(e["causes"].items()) if c != "unchanged")
            ch = ", ".join(f"{n} {k}" for n, k in e["changed_by"].items())
            print(f"{g:<40} {e['tasks']:>5} {e['moved']:>5}  {causes or '-':<27} | {ch}")

        # Headline arms, recall per run.
        print("\n--- Tag noise headline arms, Recall@5 (0.4.0 -> run), paired delta vs 0.4.0 ---")
        heads = [t for t in tasks if json.loads(t)["arm"] != "gate_noise"
                 and json.loads(t)["backend"] == "bm25"]
        tn_res["headline"] = {}
        for t in heads:
            row = {}
            for n in RUNS:
                r = diff[n].get(t)
                if r is None:
                    row[n] = {"identical": True}
                else:
                    row[n] = {"identical": False, "recall_old": r["recall_old"],
                              "recall_new": r["recall_new"],
                              "recall_paired": r.get("recall_paired")}
            tn_res["headline"][t] = row
            parts = []
            for n in RUNS:
                e = row[n]
                if e["identical"]:
                    parts.append(f"{n}: =0.4.0")
                else:
                    rp = e["recall_paired"]
                    parts.append(f"{n}: {e['recall_old']:.4f}->{e['recall_new']:.4f} "
                                 f"({rp['delta']:+.4f} [{rp['ci'][0]:+.4f},{rp['ci'][1]:+.4f}] "
                                 f"p={rp['p_bootstrap']:.3g})")
            print(f"  {_task_group(json.loads(t)):<34} " + " | ".join(parts))
        print("\n  Gate-only BM25 at priority 50 versus priority 0, per run:")
        tn_res["priority50"] = {}
        for n in RUNS:
            for bn, e in docs[n]["tag_noise"]["priority50"].items():
                d = e["p50_minus_p0"]
                tn_res["priority50"].setdefault(bn, {})[n] = {
                    "recall_p50": e["recall_p50"]["mean"], "recall_p0": e["recall_p0"]["mean"],
                    "p50_minus_p0": d}
                print(f"    {n:<24} {bn:<14} p50 {e['recall_p50']['mean']:.4f} p0 "
                      f"{e['recall_p0']['mean']:.4f} difference {d['delta']:+.4f} "
                      f"[{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}]")
        res["tag_noise"] = tn_res

        # WP2 mandatory coverage, per backend and arm.
        print("\n--- WP2 mandatory coverage: pairs differing from 0.4.0 (presence), per run ---")
        mc_res = {}
        for b in docs["default"]["mandatory_coverage"]:
            for arm, e0 in docs["default"]["mandatory_coverage"][b].items():
                if not isinstance(e0, dict):
                    continue
                row = {}
                for n in RUNS:
                    e = docs[n]["mandatory_coverage"][b][arm]
                    row[n] = {k: e.get(k) for k in ("pairs", "pairs_differing", "presence_differing",
                                                    "present_new", "present_old", "presence_mcnemar")}
                    row[n]["changes_vs_default"] = e.get("digest") != e0.get("digest")
                mc_res[f"{b}/{arm}"] = row
                cells = " | ".join(
                    f"{n}: {row[n]['pairs_differing']} ({row[n]['presence_differing']})"
                    + ("*" if row[n]["changes_vs_default"] else "") for n in RUNS)
                print(f"  {b}/{arm:<26} present 0.4.0 {row['default']['present_old']}/"
                      f"{row['default']['pairs']}  " + cells)
            thetas = {n: docs[n]["mandatory_coverage"][b].get("theta_b_new") for n in RUNS}
            mc_res[f"{b}/theta_b"] = {"old": docs["default"]["mandatory_coverage"][b].get("theta_b_old"),
                                     **thetas}
        print("  (* = differs from the 0.4.2 default run)")
        res["mandatory_coverage"] = mc_res

        # Leakage, per arm.
        print("\n--- WP6 leakage, BM25: identical to 0.4.0? recall, attack hits ---")
        lk_res = {}
        for key, e0 in docs["default"]["leakage"].items():
            row = {}
            for n in RUNS:
                e = docs[n]["leakage"][key]
                row[n] = {k: e.get(k) for k in ("identical", "recall_old", "recall_new",
                                                "attack_hits_old", "attack_hits_new",
                                                "cross_share_old", "cross_share_new",
                                                "recall_paired", "cross_share_paired",
                                                "attack_hit_mcnemar", "queries_differing")}
                row[n]["changes_vs_default"] = e.get("digest") != e0.get("digest")
            lk_res[key] = row
            cells = " | ".join(
                f"{n}: " + ("=0.4.0" if row[n]["identical"] else
                            f"R {row[n]['recall_new']:.4f} hits {row[n]['attack_hits_new']}")
                for n in RUNS)
            print(f"  {key:<28} 0.4.0 R {row['default']['recall_old']:.4f} hits "
                  f"{row['default']['attack_hits_old']}  " + cells)
        res["leakage"] = lk_res

        # Giveaways.
        print("\n--- Query giveaways (BM25 strata) ---")
        gw_res = {}
        for n in RUNS:
            g = docs[n]["giveaways"]
            gw_res[n] = g
            if not g.get("bm25_arrays_changed"):
                print(f"  {n:<24} BM25 arrays unchanged, strata identical to 0.4.0")
            else:
                for bn, e in g["recomputed"].items():
                    print(f"  {n:<24} {bn:<14} gate-only effect difference "
                          f"{json.dumps(e['effect_difference_old'], default=json_default)[:60]} -> "
                          f"{json.dumps(e['effect_difference_new'], default=json_default)[:60]}")
        res["giveaways"] = gw_res

        out_path.write_text(json.dumps(res, default=json_default), encoding="utf-8")
        print(f"\nWrote {out_path}")
    finally:
        sys.stdout = orig
        log.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--switches", nargs="*", default=[], choices=SWITCHES)
    ap.add_argument("--summarize", action="store_true",
                    help="Attribute the moves, from the five runs already written.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-hash", action="store_true", help="Skip the dense (hash) spot check.")
    ap.add_argument("--smoke", action="store_true",
                    help="No noise conditions and no leakage. Write to explicit paths.")
    ap.add_argument("--tag-noise", type=Path, default=RESULTS / "tag_noise.json")
    ap.add_argument("--mandatory", type=Path, default=RESULTS / "mandatory_coverage.json")
    ap.add_argument("--leakage", type=Path, default=RESULTS / "leakage_threat.json")
    ap.add_argument("--giveaways", type=Path, default=RESULTS / "query_giveaways.json")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--log-file", type=Path, default=None)
    ap.add_argument("--arrays", type=Path, default=None)
    args = ap.parse_args()
    if args.smoke and (args.output is None or args.log_file is None or args.arrays is None):
        raise SystemExit("A smoke run needs --output, --log-file and --arrays.")
    if args.summarize:
        summarize(args)
    else:
        one_run(args)


if __name__ == "__main__":
    main()
