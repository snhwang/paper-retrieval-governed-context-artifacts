#!/usr/bin/env python3
"""Mandatory-injection coverage on Pet Sim, redesigned for BEAR 0.4.0 (WP2).

Why a redesign. Under 0.1.10 a mandatory instruction bypassed the hard gate,
so the old test excluded the safety rules with a required tag no query
carried and showed mandatory ON = 1.000, OFF = 0.000. Under 0.4.0 mandatory
injection respects the gate (property P1), so that construction gives 0.000
with injection ON as well, and no longer isolates injection. The old result
was correct for the rules it ran under.

New design. The three safety rules stay gate-admissible (no required tags),
so injection may add them. Ordinary admission is closed off instead. BEAR
admits an instruction that passes its gate when its soft scope matches OR its
similarity reaches the threshold. Each safety rule is given the soft-scope tag
``safety_review``, which no query context carries, so the soft path is shut.
The similarity path is then checked, per backend, from the retriever's own
trace.

Arms (k = 10, priority weight 0.3, mandatory tag "safety", as in the
published Pet Sim rows):

  A  soft scope shut, theta = 0.3 (the paper's threshold).
     ON vs OFF. OFF recall measures how often similarity alone reaches the
     rules at the paper's threshold.
  B  soft scope shut, theta_b just above the largest similarity any safety
     rule reaches to any query under this backend (read from A's traces).
     Similarity can then reach no safety rule, which the OFF arm verifies
     (want 0 of 738 query-rule pairs). ON vs OFF isolates injection.
  C  negative control for P1. The rules also require ``safety_review``, so
     the gate fails for every query. With injection ON they must be absent,
     with trace reason "gate".
  D  partial gate. The rules require "dog". With injection ON a rule must be
     present exactly when the query context carries "dog".

Queries: all 246 Pet Sim queries (60 standard, 12 adversarial-safety,
paraphrase, no-tag and complex sets). Metric: safety recall per query (the
fraction of the 3 rules in the output). Statistics: bootstrap 95% CIs, paired
bootstrap of ON - OFF with paired Cohen's d, Wilcoxon, and McNemar on
"all three present". Per-query and per-pair arrays are saved.

Backends: bge, bge-m3, qwen3-0.6b, qwen3-4b, bm25, hash, nemotron.

Phases (see tistr2_common): ``embed`` records the texts and embeds them (run
under ``flock ~/tist-gpu.lock``), ``run`` retrieves on the CPU from the
stored vectors.

    flock ~/tist-gpu.lock python evals/eval_mandatory_coverage.py --phase embed
    CUDA_VISIBLE_DEVICES= python evals/eval_mandatory_coverage.py --phase run
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
    fmt, fmt_delta, json_default, make_config, mcnemar_summary, paired_summary,
    record_texts, refuse_overwrite, require_bear_040,
)
from bear import Context, Corpus  # noqa: E402
from bear.models import ScopeCondition  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

FAMILY = "petsim"
K = 10
THETA = 0.3
PRIORITY_WEIGHT = 0.3
MANDATORY = ["safety"]
SOFT_TAG = "safety_review"      # a soft-scope tag no query context carries
PARTIAL_GATE_TAG = "dog"        # arm D: carried by some query contexts


def load_queries() -> list[tuple[str, list[str], str]]:
    from eval_governance_decomposed import ADVERSARIAL_SAFETY_QUERIES
    from eval_retrieval import TEST_QUERIES
    from eval_retrieval_backends import COMPLEX_QUERIES, NO_TAG_QUERIES, PARAPHRASE_QUERIES
    out = []
    for name, qs in (("standard", TEST_QUERIES), ("adversarial", ADVERSARIAL_SAFETY_QUERIES),
                     ("paraphrase", PARAPHRASE_QUERIES), ("notag", NO_TAG_QUERIES),
                     ("complex", COMPLEX_QUERIES)):
        out.extend((q, list(t), name) for q, t, _ in qs)
    return out


def variant(base: Corpus, safety_ids: set[str], required: list[str]) -> Corpus:
    """Safety rules with the unreachable soft tag and the given required tags."""
    out = Corpus()
    for inst in base:
        ic = inst.model_copy(deep=True)
        if inst.id in safety_ids:
            if (set(inst.scope.tags) | set(inst.scope.required_tags) | set(inst.scope.user_roles)
                    | set(inst.scope.domains) | set(inst.scope.task_types)
                    | set(inst.scope.trigger_patterns) | set(inst.scope.session_phase)):
                raise SystemExit(f"{inst.id} already has a scope; the design assumes none.")
            ic.scope = ScopeCondition(tags=[SOFT_TAG], required_tags=list(required))
        out.add(ic)
    return out


def check_queries(queries) -> None:
    for q, tags, _ in queries:
        if SOFT_TAG in tags:
            raise SystemExit(f"Query context carries {SOFT_TAG!r}: {q!r}")


def run_arm(corpus: Corpus, backend: str, store, queries, safety_ids: list[str], *,
            theta: float, mandatory: list[str]) -> dict:
    cfg = make_config(backend, FAMILY, k=K, threshold=theta, priority_weight=PRIORITY_WEIGHT,
                      mandatory_tags=mandatory)
    emb = None if backend == "bm25" else CachedEmbedder(store)
    r = build_retriever(corpus, backend, FAMILY, cfg, emb)
    per_query, all_present, pairs = [], [], []
    for qi, (q, tags, qset) in enumerate(queries):
        out, tr = r.retrieve_with_trace(q, Context(tags=tags), top_k=K)
        got = {s.id: s for s in out}
        hits = 0
        for sid in safety_ids:
            present = sid in got
            hits += present
            ex = tr.excluded.get(sid)
            sim = (got[sid].similarity if present
                   else (ex["similarity"] if ex and ex["similarity"] is not None else None))
            pairs.append({"q": qi, "rule": sid, "present": present,
                          "admitted_by": tr.admitted.get(sid) if present else None,
                          "excluded_reason": None if present else (ex["reason"] if ex else "not_in_pool"),
                          "similarity": sim})
        per_query.append(hits / len(safety_ids))
        all_present.append(int(hits == len(safety_ids)))
    return {"theta": theta, "mandatory_tags": mandatory, "per_query_recall": per_query,
            "per_query_all_present": all_present, "pairs": pairs,
            "recall": ci_summary(per_query)}


def path_counts(pairs: list[dict]) -> dict:
    out: dict[str, int] = {}
    for p in pairs:
        key = f"in:{p['admitted_by']}" if p["present"] else f"out:{p['excluded_reason']}"
        out[key] = out.get(key, 0) + 1
    return out


def theta_above(pairs: list[dict]) -> tuple[float, float]:
    """Smallest 3-decimal threshold above every recorded safety similarity.

    A pair with no recorded similarity never entered the search pool (BM25
    drops zero-score rows), so it is unreachable at any threshold.
    """
    sims = [p["similarity"] for p in pairs if p["similarity"] is not None]
    mx = max(sims)
    return float(np.floor(mx * 1000) / 1000 + 0.001), float(mx)


def phase_embed(args, base, safety_ids, queries) -> None:
    corpus_a = variant(base, set(safety_ids), [])
    cfg = make_config("hash", FAMILY, k=K, threshold=THETA, priority_weight=PRIORITY_WEIGHT,
                      mandatory_tags=MANDATORY)
    qs = [(q, Context(tags=t)) for q, t, _ in queries]
    q_texts, d_texts = record_texts([(corpus_a, qs, cfg)], top_k=K)
    print(f"Recorded {len(q_texts)} query texts and {len(d_texts)} document texts.")
    for b in args.backends:
        if b == "bm25":
            continue
        st = EmbeddingStore(b, FAMILY)
        print(f"  {b}: {st.fill(q_texts, d_texts)}", flush=True)


def phase_run(args, base, safety_ids, queries) -> dict:
    enable_bm25_memo()
    corpus_a = variant(base, set(safety_ids), [])
    corpus_c = variant(base, set(safety_ids), [SOFT_TAG])
    corpus_d = variant(base, set(safety_ids), [PARTIAL_GATE_TAG])
    results = {}
    for b in args.backends:
        t0 = time.time()
        store = None if b == "bm25" else EmbeddingStore(b, FAMILY)
        res: dict = {"label": BACKEND_LABEL[b]}
        a_on = run_arm(corpus_a, b, store, queries, safety_ids, theta=THETA, mandatory=MANDATORY)
        a_off = run_arm(corpus_a, b, store, queries, safety_ids, theta=THETA, mandatory=[])
        # Similarities come from the OFF run: with injection ON, a rule the
        # threshold set aside is re-admitted as mandatory and its trace entry
        # (with the similarity) is replaced.
        theta_b, max_sim = theta_above(a_off["pairs"])
        b_on = run_arm(corpus_a, b, store, queries, safety_ids, theta=theta_b, mandatory=MANDATORY)
        b_off = run_arm(corpus_a, b, store, queries, safety_ids, theta=theta_b, mandatory=[])
        c_on = run_arm(corpus_c, b, store, queries, safety_ids, theta=THETA, mandatory=MANDATORY)
        d_on = run_arm(corpus_d, b, store, queries, safety_ids, theta=THETA, mandatory=MANDATORY)

        sims = np.array([p["similarity"] for p in a_off["pairs"] if p["similarity"] is not None])
        reach_a = sum(p["present"] for p in a_off["pairs"])
        reach_b = sum(p["present"] for p in b_off["pairs"])
        n_pairs = len(a_off["pairs"])
        gate_d = [PARTIAL_GATE_TAG in queries[p["q"]][1] for p in d_on["pairs"]]
        d_mismatch = sum(int(p["present"] != g) for p, g in zip(d_on["pairs"], gate_d))
        c_wrong = sum(int(p["present"] or p["excluded_reason"] != "gate") for p in c_on["pairs"])

        res.update({
            "similarity_to_queries": {"min": float(sims.min()), "median": float(np.median(sims)),
                                      "max": float(sims.max()),
                                      "frac_ge_theta": float((sims >= THETA).mean()),
                                      "n_pairs_with_similarity": int(len(sims))},
            "A_soft_shut_theta_paper": {
                "on": strip_pairs(a_on), "off": strip_pairs(a_off),
                "on_minus_off": paired_summary(a_on["per_query_recall"], a_off["per_query_recall"]),
                "mcnemar_all_present": mcnemar_summary(a_on["per_query_all_present"],
                                                       a_off["per_query_all_present"]),
                "off_reachable_pairs": reach_a, "n_pairs": n_pairs,
                "off_reachable_ci": clopper_pearson(reach_a, n_pairs),
                "on_paths": path_counts(a_on["pairs"]), "off_paths": path_counts(a_off["pairs"])},
            "B_verified_unreachable": {
                "theta_b": theta_b, "max_safety_similarity": max_sim,
                "on": strip_pairs(b_on), "off": strip_pairs(b_off),
                "on_minus_off": paired_summary(b_on["per_query_recall"], b_off["per_query_recall"]),
                "mcnemar_all_present": mcnemar_summary(b_on["per_query_all_present"],
                                                       b_off["per_query_all_present"]),
                "off_reachable_pairs": reach_b, "n_pairs": n_pairs,
                "off_reachable_ci": clopper_pearson(reach_b, n_pairs),
                "on_paths": path_counts(b_on["pairs"]), "off_paths": path_counts(b_off["pairs"])},
            "C_gate_fails_P1": {
                "on": strip_pairs(c_on), "violations": c_wrong, "n_pairs": n_pairs,
                "violation_ci": clopper_pearson(c_wrong, n_pairs),
                "on_paths": path_counts(c_on["pairs"])},
            "D_partial_gate": {
                "on": strip_pairs(d_on), "gate_tag": PARTIAL_GATE_TAG,
                "n_pairs_gate_passes": int(sum(gate_d)), "presence_mismatch": d_mismatch,
                "n_pairs": n_pairs, "mismatch_ci": clopper_pearson(d_mismatch, n_pairs),
                "on_paths": path_counts(d_on["pairs"])},
            "pairs": {"A_on": a_on["pairs"], "A_off": a_off["pairs"], "B_on": b_on["pairs"],
                      "B_off": b_off["pairs"], "C_on": c_on["pairs"], "D_on": d_on["pairs"]},
            "elapsed_s": round(time.time() - t0, 1),
        })
        results[b] = res
        print_backend(b, res)
    return results


def strip_pairs(arm: dict) -> dict:
    return {k: v for k, v in arm.items() if k != "pairs"}


def print_backend(b: str, r: dict) -> None:
    a, bb, c, d = (r["A_soft_shut_theta_paper"], r["B_verified_unreachable"],
                   r["C_gate_fails_P1"], r["D_partial_gate"])
    s = r["similarity_to_queries"]
    print(f"\n{BACKEND_LABEL[b]}  safety-rule similarity to queries: min {s['min']:.3f}, "
          f"median {s['median']:.3f}, max {s['max']:.3f}, share >= {THETA}: {s['frac_ge_theta']:.3f}")
    print(f"  A theta={THETA}:  ON {fmt(a['on']['recall'])}  OFF {fmt(a['off']['recall'])}  "
          f"ON-OFF {fmt_delta(a['on_minus_off'])}")
    print(f"      OFF reaches {a['off_reachable_pairs']}/{a['n_pairs']} pairs by similarity. "
          f"ON paths {a['on_paths']}")
    print(f"  B theta={bb['theta_b']:.3f}:  ON {fmt(bb['on']['recall'])}  OFF {fmt(bb['off']['recall'])}  "
          f"ON-OFF {fmt_delta(bb['on_minus_off'])}")
    print(f"      OFF reaches {bb['off_reachable_pairs']}/{bb['n_pairs']} pairs (want 0). "
          f"ON paths {bb['on_paths']}")
    print(f"  C gate fails, ON: recall {c['on']['recall']['mean']:.3f}, "
          f"violations {c['violations']}/{c['n_pairs']} (want 0). Paths {c['on_paths']}")
    print(f"  D gate on {d['gate_tag']!r}, ON: present-vs-gate mismatches "
          f"{d['presence_mismatch']}/{d['n_pairs']} (want 0), gate passes in "
          f"{d['n_pairs_gate_passes']} pairs. Paths {d['on_paths']}")


def print_table(results: dict) -> None:
    print("\n--- Summary: safety recall (95% bootstrap CI), 246 queries x 3 rules ---\n")
    print(f"{'Backend':<18} {'A ON':>7} {'A OFF':>7} {'A reach':>8}  {'theta_b':>7} {'B ON':>6} "
          f"{'B OFF':>6} {'B reach':>8}  {'C viol':>6} {'D mism':>6}")
    for b, r in results.items():
        a, bb, c, d = (r["A_soft_shut_theta_paper"], r["B_verified_unreachable"],
                       r["C_gate_fails_P1"], r["D_partial_gate"])
        print(f"{BACKEND_LABEL[b]:<18} {a['on']['recall']['mean']:>7.3f} {a['off']['recall']['mean']:>7.3f} "
              f"{a['off_reachable_pairs']:>4}/{a['n_pairs']:<3}  {bb['theta_b']:>7.3f} "
              f"{bb['on']['recall']['mean']:>6.3f} {bb['off']['recall']['mean']:>6.3f} "
              f"{bb['off_reachable_pairs']:>4}/{bb['n_pairs']:<3}  {c['violations']:>6} "
              f"{d['presence_mismatch']:>6}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["embed", "run"], required=True)
    ap.add_argument("--backends", nargs="+", default=ALL_BACKENDS, choices=ALL_BACKENDS)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "mandatory_coverage.json")
    ap.add_argument("--log-file", type=Path,
                    default=REPO_ROOT / "results" / "mandatory_coverage_output.txt")
    args = ap.parse_args()
    require_bear_040()

    from eval_governance_decomposed import discover_safety_ids, load_pet_sim_corpus
    base = load_pet_sim_corpus()
    safety_ids = sorted(discover_safety_ids(base))
    queries = load_queries()
    check_queries(queries)

    if args.phase == "embed":
        phase_embed(args, base, safety_ids, queries)
        return

    refuse_overwrite(args.output, args.log_file)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        print("=== Mandatory-injection coverage (WP2), Pet Sim, BEAR 0.4.0 ===")
        print(f"Corpus {len(base)} instructions. Safety rules {safety_ids}.")
        print(f"Queries {len(queries)}. k={K}, theta={THETA}, priority weight {PRIORITY_WEIGHT}, "
              f"mandatory {MANDATORY}. Soft tag {SOFT_TAG!r} carried by no query.")
        results = phase_run(args, base, safety_ids, queries)
        print_table(results)
        out = {"design": {"k": K, "theta": THETA, "priority_weight": PRIORITY_WEIGHT,
                          "mandatory_tags": MANDATORY, "soft_tag": SOFT_TAG,
                          "partial_gate_tag": PARTIAL_GATE_TAG, "safety_ids": safety_ids,
                          "n_queries": len(queries)},
               "queries": [{"query": q, "tags": t, "set": s} for q, t, s in queries],
               "provenance": bear_provenance(), "backends": results}
        args.output.write_text(json.dumps(out, indent=1, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.1f}s")
        print_repro_footer(extra={"eval": "mandatory_coverage", "backends": args.backends,
                                  **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
