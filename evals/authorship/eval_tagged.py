#!/usr/bin/env python3
"""Authorship ablation, step 3: MetaTool+Tags and MetaTool+QueryTags-top5 with other tag files.

    python evals/authorship/eval_tagged.py --tool-tags PATH --query-tags PATH/query_tags_top5.json \
        --backends "BEAR+BGE (gov)" "BGE (no gov)" --output results/wp0/toolbench_eval_<step>.json

Runs evals/wp0_v040/eval_toolbench_v040.py (eval_toolbench.main with the
Nemotron backend and the hash-fallback guard) exactly as the WP0 lanes run it
for Tables 8 and 9, with two changes:
- the MetaTool+Tags and MetaTool+QueryTags-top5 conditions read the tool tags
  from --tool-tags instead of the committed plugin_tags.json (both the corpus
  and, for MetaTool+Tags, the query context derived from the target tools).
  --query-tags names the query-tag file, which eval_toolbench already takes.
  Keep its name query_tags_top5.json, so the result key stays
  MetaTool+QueryTags-top5.
- base MetaTool and ToolBench are not run. They do not depend on the tagger.
The output has the same layout as the WP0 step files, so the analysis pairs
them query by query. Its provenance records both tag files with their sha256.
Exit 3 when a requested experiment is missing from the output, as the WP0
wrapper does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
for _p in (str(EVALS.parent), str(EVALS), str(EVALS / "wp0_v040")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool-tags", type=Path, required=True)
    ap.add_argument("--query-tags", type=Path, required=True)
    ap.add_argument("--backends", nargs="+", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--max-queries", type=int, default=None, help="smoke runs only")
    a = ap.parse_args(argv)
    if a.query_tags.stem != "query_tags_top5":
        raise SystemExit("--query-tags must be named query_tags_top5.json (the result key follows the name)")
    for p in (a.tool_tags, a.query_tags):
        if not p.exists():
            raise SystemExit(f"missing {p}")

    import eval_toolbench_v040 as v040   # patches eval_toolbench: Nemotron backend, hash guard
    import wp0_common
    et = v040.et
    tool_tags = a.tool_tags.resolve()
    orig_corpus, orig_queries, orig_run = (et.load_metatool_corpus_tagged, et.load_metatool_queries_tagged,
                                           et.run_benchmark)

    def corpus_tagged(tags_path=None):
        return orig_corpus(tool_tags)

    def queries_tagged(tags_path=None, max_queries=None):
        return orig_queries(tool_tags, max_queries=max_queries)

    def run_benchmark(name, *args, **kw):
        if name == "MetaTool":
            print("  base MetaTool skipped: it does not depend on the tagger")
            # An empty result, not None. eval_toolbench.main's closing summary iterates every
            # benchmark's results, and None stopped it after the results were saved (job 168,
            # 17 Nov 2026). The empty entry is dropped below with the other "MetaTool" key.
            return {}
        return orig_run(name, *args, **kw)

    et.load_metatool_corpus_tagged = corpus_tagged
    et.load_metatool_queries_tagged = queries_tagged
    et.run_benchmark = run_benchmark
    argv_main = [sys.argv[0], "--metatool-only", "--top-k", str(a.top_k),
                 "--metatool-query-tags-file", str(a.query_tags), "--output", str(a.output),
                 "--backends", *a.backends]
    if a.max_queries:
        argv_main += ["--max-queries", str(a.max_queries)]
    print(f"tool tags {tool_tags} ({sha256(tool_tags)[:12]}), query tags {a.query_tags} ({sha256(a.query_tags)[:12]})")
    old = sys.argv
    sys.argv = argv_main
    try:
        et.main()
    finally:
        sys.argv = old
    if not a.output.exists():
        print(f"no output written to {a.output}")
        return 3
    data = json.loads(a.output.read_text(encoding="utf-8"))
    data = {k: v for k, v in data.items() if v is not None and k != "MetaTool"}
    a.output.write_text(json.dumps(data, indent=1), encoding="utf-8")
    wp0_common.stamp_json(str(a.output), {"script": "evals/authorship/eval_tagged.py",
                                          "tool_tags": {"path": str(tool_tags), "sha256": sha256(tool_tags)},
                                          "query_tags": {"path": str(a.query_tags.resolve()),
                                                         "sha256": sha256(a.query_tags)}})
    want = ("MetaTool+Tags", "MetaTool+QueryTags-top5")
    data = json.loads(a.output.read_text(encoding="utf-8"))
    missing = [(b, n) for b in want for n in a.backends if n not in (data.get(b) or {})]
    if missing:
        print(f"MISSING EXPERIMENTS: {missing}")
        return 3
    print(f"written: {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
