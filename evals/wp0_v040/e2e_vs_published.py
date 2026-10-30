"""Check regenerated ToolBench top-5 lists against the published end-to-end run.

    python e2e_vs_published.py --published evals/results/toolbench_e2e_scores.json DIR [DIR ...]

The published file (Tables 7 to 9) keeps per-query retrieval arrays (recall,
precision, F1, NDCG at 5) for each condition, computed from the top-5 lists
the LLM saw. Equal arrays do not prove equal lists, but any difference proves
a different list. For every list file in each DIR, this counts the queries
whose arrays differ from the published ones.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

NAMES = {"bge": "BGE", "bge-m3": "BGE-M3", "qwen3-0.6b": "Qwen3-0.6B", "qwen3-4b": "Qwen3-4B",
         "bm25": "BM25", "hash": "Hash", "nemotron": "Nemotron"}
METRICS = ("_recall_scores", "_precision_scores", "_f1_scores", "_ndcg_scores")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--published", required=True)
    ap.add_argument("--out")
    ap.add_argument("dirs", nargs="+")
    a = ap.parse_args()
    pub = {s["condition"]: s for s in json.loads(Path(a.published).read_text())["scores"]}
    out = {}
    for d in a.dirs:
        for f in sorted(Path(d).glob("*.json")):
            if f.name.endswith(".provenance.json"):
                continue
            L = json.loads(f.read_text())
            cond = L.get("condition")
            if cond not in pub:
                continue
            row = {}
            for m in METRICS:
                if m not in L:
                    continue
                x, y = np.asarray(L[m], float), np.asarray(pub[cond][m], float)
                row[m.strip("_").replace("_scores", "")] = int(np.sum(np.abs(x - y) > 1e-9))
            key = f"{d}/{f.name}"
            out[key] = {"condition": cond, "queries_differ": row}
            print(f"{key:70s} {cond:24s} {row}")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
