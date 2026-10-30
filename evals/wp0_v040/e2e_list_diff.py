"""Which ToolBench end-to-end prompts change between two BEAR versions.

    python e2e_list_diff.py --a lists_v0110/e2e --b lists_v042/e2e [--out diff.json]

The end-to-end prompt lists the top-5 tools in rank order, so a query's prompt
changes when its ordered top-5 changes. For each condition file present in
both folders, this counts the queries whose ordered list differs, the subset
whose set of tools differs, and (for order-only changes) whether the swapped
tools are tied on final score in the new version.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    res = {}
    for fa in sorted(Path(args.a).glob("*.json")):
        fb = Path(args.b) / fa.name
        if not fb.exists() or fa.name.endswith(".provenance.json"):
            continue
        A, B = json.loads(fa.read_text()), json.loads(fb.read_text())
        ia, ib = A["ids"], B["ids"]
        assert len(ia) == len(ib), fa.name
        ordered, sets, order_only_tied, idx = 0, 0, 0, []
        for q, (x, y) in enumerate(zip(ia, ib)):
            if list(x) == list(y):
                continue
            ordered += 1
            idx.append(q)
            if set(x) != set(y):
                sets += 1
            else:
                # positions that differ, and whether their new final scores tie
                fs = B["final_score"][q]
                pos = [i for i in range(len(y)) if x[i] != y[i]]
                vals = {round(fs[i], 9) for i in pos}
                if len(vals) == 1:
                    order_only_tied += 1
        res[fa.name] = {"n_queries": len(ia), "ordered_differs": ordered, "set_differs": sets,
                        "order_only": ordered - sets, "order_only_tied_in_b": order_only_tied,
                        "queries": idx}
        print(f"{fa.name:24s} n={len(ia)} ordered differs {ordered}, set differs {sets}, "
              f"order only {ordered - sets} (tied in b: {order_only_tied})")
    if args.out:
        Path(args.out).write_text(json.dumps({"a": args.a, "b": args.b, "conditions": res}, indent=1))


if __name__ == "__main__":
    main()
