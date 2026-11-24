#!/usr/bin/env python3
"""The Table 10 monolithic row's recall ceiling: sanitized function names that collide.

    python reproduce/derive/e2e_name_collisions.py --out DIR/e2e_name_collisions.json

The end-to-end prompt names each ToolBench API by a sanitized function name
(evals/eval_toolbench_e2e.py make_tool_schema). When two endpoints sanitize to
the same name, the monolithic prompt cannot tell them apart, which is why its
retrieval recall is 0.995 and not 1.000 (text of Section 4.2, "14 sanitized
function names that collide across 36 endpoints"). This counts those names,
with the same loader and schema code the end-to-end runs used. No model, no server.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from _common import EVALS, provenance, use_evals, write


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    use_evals()
    import eval_toolbench_e2e as e2e  # noqa: E402
    corpus, queries = e2e.load_toolbench_data()
    corpus = list(corpus)
    names = {}
    no_schema = 0
    for inst in corpus:
        s = e2e.make_tool_schema(inst)
        if s and s.get("name"):
            names[inst.id] = s["name"]
        else:
            no_schema += 1
    count = Counter(names.values())
    colliding = {n: c for n, c in count.items() if c > 1}
    ids_in_collisions = sorted(i for i, n in names.items() if n in colliding)
    gold = [g for q in queries for g in q[2]]   # (text, tags, expected_ids, api_details)
    in_collision = set(ids_in_collisions)
    gold_hit = sum(1 for g in gold if g in in_collision)
    write(a.out, {
        "endpoints": len(corpus), "endpoints_with_a_schema": len(names), "endpoints_without_a_schema": no_schema,
        "distinct_names": len(count), "colliding_names": len(colliding),
        "endpoints_in_colliding_names": sum(colliding.values()),
        "gold_apis_in_colliding_names": gold_hit, "gold_apis": len(gold),
        "colliding": dict(sorted(colliding.items())),
        "_provenance": provenance("reproduce/derive/e2e_name_collisions.py",
                                  [EVALS / "data" / "external_benchmarks" / "toolbench" / "benchmark_data.json",
                                   EVALS / "eval_toolbench_e2e.py"]),
    })


if __name__ == "__main__":
    main()
