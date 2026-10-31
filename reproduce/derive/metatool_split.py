#!/usr/bin/env python3
"""MetaTool query counts for Section 4.2: 21,111 queries, single-tool and multi-tool.

    python reproduce/derive/metatool_split.py --out DIR/metatool_split.json

Loads the queries and the corpus with the loaders every MetaTool table uses
(evals/eval_toolbench.py: load_metatool_queries, load_metatool_corpus), and
counts queries with one expected tool and with more than one. Also counts the
rows of each source file, so the split can be read either way. No model, no server.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from _common import EVALS, provenance, use_evals, write


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    use_evals()
    from eval_toolbench import load_metatool_corpus, load_metatool_queries  # noqa: E402
    queries = load_metatool_queries()
    _corpus, instructions = load_metatool_corpus()
    corpus_ids = {i.id for i in instructions}
    single = sum(1 for q in queries if len(q[2]) == 1)
    multi = sum(1 for q in queries if len(q[2]) > 1)
    covered = sum(1 for q in queries if set(q[2]) <= corpus_ids) if corpus_ids else None
    d = EVALS / "data" / "external_benchmarks" / "metatool"
    with open(d / "all_clean_data.csv", encoding="utf-8") as f:
        csv_rows = sum(1 for _ in csv.DictReader(f))
    multi_rows = len(json.loads((d / "multi_tool_query_golden.json").read_text(encoding="utf-8")))
    write(a.out, {
        "queries": len(queries), "single_tool_queries": single, "multi_tool_queries": multi,
        "tools_in_corpus": len(corpus_ids) if corpus_ids else None,
        "queries_whose_tools_are_all_in_the_corpus": covered,
        "source_rows": {"all_clean_data.csv": csv_rows, "multi_tool_query_golden.json": multi_rows},
        "_provenance": provenance("reproduce/derive/metatool_split.py",
                                  [d / "all_clean_data.csv", d / "multi_tool_query_golden.json",
                                   d / "plugin_info.json", d / "plugin_des.json"]),
    })


if __name__ == "__main__":
    main()
