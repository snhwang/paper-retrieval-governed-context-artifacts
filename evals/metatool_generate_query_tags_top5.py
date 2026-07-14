"""Generate TOP-5 context tags for MetaTool queries (multi-label variant).

Each query is tagged with up to five domain categories inferred from the query
text alone, ranked most- to least-likely. These runtime query tags feed the
MetaTool+QueryTags condition (Table~\ref{tab:metatool-tags-results}).

Selection is forced through an Anthropic tool schema (see
``metatool_tagging.py``): the tool has a required ``primary_domain`` enum field,
so every query is guaranteed at least one in-vocabulary domain tag. There is no
free-form JSON to misparse and no path that yields an empty tag list -- the
earlier free-form generator could return ``[]`` on a parse failure or a
degenerate single-``search`` answer, and the BEAR ``required_tags`` gate then
scored those queries at recall 0 by construction.

Usage:
    python metatool_generate_query_tags_top5.py --model claude-sonnet-4-6

Output:
    data/external_benchmarks/metatool/query_tags_top5.json
    A list of {query, context_tags, tools, type} dicts. context_tags is a list
    of up to 5 ranked category strings, always with a domain tag first.
"""

from __future__ import annotations

import argparse
import csv
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from metatool_tagging import (  # noqa: E402
    DOMAIN_NAMES,
    TaggingError,
    generate_query_tags,
    require_api_key,
)

DATA_DIR = Path(__file__).resolve().parent / "data" / "external_benchmarks" / "metatool"


def load_queries() -> list[dict]:
    """Load all MetaTool queries (single + multi tool)."""
    queries = []

    csv_path = DATA_DIR / "all_clean_data.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                query_text = tool_name = ""
                for col in row:
                    if any(k in col.lower() for k in ["query", "question", "prompt"]):
                        query_text = row[col]
                    if any(k in col.lower() for k in ["tool", "plugin"]):
                        tool_name = row[col]
                if query_text and tool_name:
                    queries.append({
                        "query": query_text.strip(),
                        "tools": [tool_name.strip()],
                        "type": "single",
                    })

    multi_path = DATA_DIR / "multi_tool_query_golden.json"
    if multi_path.exists():
        with open(multi_path) as f:
            multi_data = json.load(f)
        for entry in multi_data:
            q = entry.get("query", "")
            tools = entry.get("tool", [])
            if q and tools:
                queries.append({
                    "query": q.strip(),
                    "tools": tools,
                    "type": "multi",
                })

    return queries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--output", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="Skip queries already tagged in the output file.")
    parser.add_argument("--workers", type=int, default=8,
                        help="Concurrent API requests (default 8).")
    parser.add_argument("--max-queries", type=int, default=None,
                        help="Limit number of queries (for testing).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = require_api_key()
    output_path = Path(args.output) if args.output else DATA_DIR / "query_tags_top5.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    queries = load_queries()
    # Deterministic shuffle for broad tool coverage when --max-queries samples.
    import random as _random
    _random.seed(42)
    _random.shuffle(queries)
    if args.max_queries:
        queries = queries[:args.max_queries]
    print(f"Total queries to tag: {len(queries)}")

    # Resume: keep entries already tagged, retry only the rest. (The new path
    # cannot produce empty tags, so a resumed file only ever grows.)
    done: dict[str, dict] = {}
    if args.resume and output_path.exists():
        with open(output_path) as f:
            for e in json.load(f):
                if e.get("context_tags"):
                    done[e["query"]] = e
        print(f"Resuming: {len(done)} already tagged")

    todo = [q for q in queries if q["query"] not in done]
    print(f"To tag now: {len(todo)}  (workers={args.workers}, model={args.model})")

    if args.dry_run:
        for q in todo[:5]:
            print(f"  {q['query'][:100]}  tools={q['tools']}")
        return

    results: dict[str, dict] = dict(done)
    lock = threading.Lock()
    failures: list[tuple[str, str]] = []
    n_complete = 0

    def worker(q: dict) -> dict:
        tags = generate_query_tags(q["query"], args.model, api_key, k=5)
        return {"query": q["query"], "context_tags": tags,
                "tools": q["tools"], "type": q["type"]}

    def flush() -> None:
        with open(output_path, "w") as f:
            json.dump(list(results.values()), f, indent=2)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(worker, q): q for q in todo}
        for fut in as_completed(futs):
            q = futs[fut]
            try:
                entry = fut.result()
                with lock:
                    results[entry["query"]] = entry
                    n_complete += 1
                    if n_complete % 100 == 0:
                        print(f"  [{n_complete}/{len(todo)}] {entry['query'][:55]} -> {entry['context_tags']}")
                    if n_complete % 500 == 0:
                        flush()
            except TaggingError as e:
                with lock:
                    failures.append((q["query"], str(e)))
                    print(f"  FAILED (kept out of file, not emptied): {q['query'][:55]} :: {e}")

    flush()

    tagged = sum(1 for r in results.values() if r["context_tags"])
    starved = sum(1 for r in results.values()
                  if not (set(r["context_tags"]) & set(DOMAIN_NAMES)))
    print(f"\nDone: {tagged}/{len(results)} queries tagged; starved (no domain tag): {starved}")
    if failures:
        print(f"UNRECOVERABLE calls: {len(failures)} (absent from the file, never emptied). "
              f"Re-run with --resume to retry them.")
    print(f"Output: {output_path}")

    all_tags = [t for r in results.values() for t in r["context_tags"]]
    print("\nQuery tag distribution:")
    for tag, count in Counter(all_tags).most_common():
        print(f"  {tag}: {count}")


if __name__ == "__main__":
    main()
