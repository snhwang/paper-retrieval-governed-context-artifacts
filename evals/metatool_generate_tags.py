"""Generate category tags for MetaTool tools using an LLM.

Enriches the MetaTool corpus with structured domain tags so BEAR governance can
be evaluated on a corpus that ships with no metadata (the MetaTool+Tags and
MetaTool+QueryTags conditions).

Selection is forced through an Anthropic tool schema (see ``metatool_tagging.py``)
whose ``tags`` field enumerates the 19 domain categories, with ``minItems: 1``.
Every tool therefore receives at least one in-vocabulary domain tag; there is no
free-form JSON to misparse and no path that yields an empty tag list. The generic
``search`` tag is excluded from the tool-side vocabulary by design -- tools are
categorized by domain, per the taxonomy's own rule.

Usage:
    python metatool_generate_tags.py --model claude-sonnet-4-6

Output:
    data/external_benchmarks/metatool/plugin_tags.json
    A dict mapping tool name -> list of 1-3 domain tags.
"""

from __future__ import annotations

import argparse
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
    TaggingError,
    generate_tool_tags,
    require_api_key,
)

DATA_DIR = Path(__file__).resolve().parent / "data" / "external_benchmarks" / "metatool"


def load_tools() -> list[dict]:
    """Build the tool list from plugin_des.json -- the retrieval corpus.

    The MetaTool retrieval corpus is exactly the 199 tools in plugin_des.json,
    and every benchmark query targets one of them. We must tag that set, so the
    required_tags gate can scope every retrievable tool. plugin_info.json (388
    real-plugin entries) supplies richer descriptions where a tool appears in
    both, but 46 corpus tools (the generic single-tool targets such as
    FinanceTool, WeatherTool) exist ONLY in plugin_des; tagging plugin_info
    instead of the corpus leaves those 46 untagged, orphaning ~11k queries.
    """
    plugin_des_path = DATA_DIR / "plugin_des.json"
    plugin_info_path = DATA_DIR / "plugin_info.json"
    if not plugin_des_path.exists():
        raise SystemExit("plugin_des.json not found. Run toolbench_setup.py first.")

    with open(plugin_des_path) as f:
        des_data = json.load(f)  # {tool_name: short_description} -- the corpus

    info_lookup: dict[str, dict] = {}
    if plugin_info_path.exists():
        with open(plugin_info_path) as f:
            for item in json.load(f):
                name = (item.get("name_for_model") or "").strip()
                if name:
                    info_lookup[name] = item

    tools: list[dict] = []
    for name, short_desc in des_data.items():
        info = info_lookup.get(name.strip(), {})
        description = (info.get("description_for_model")
                      or info.get("description_for_human")
                      or short_desc or "")
        tools.append({"name": name.strip(), "description": description.strip()[:500]})
    return tools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--output", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="Skip tools already tagged in the output file.")
    parser.add_argument("--workers", type=int, default=8,
                        help="Concurrent API requests (default 8).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = require_api_key()
    output_path = Path(args.output) if args.output else DATA_DIR / "plugin_tags.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tools = load_tools()
    print(f"Unique tools to tag: {len(tools)}")

    done: dict[str, list[str]] = {}
    if args.resume and output_path.exists():
        with open(output_path) as f:
            for name, tags in json.load(f).items():
                if tags:
                    done[name] = tags
        print(f"Resuming: {len(done)} already tagged")

    todo = [t for t in tools if t["name"] not in done]
    print(f"To tag now: {len(todo)}  (workers={args.workers}, model={args.model})")

    if args.dry_run:
        for t in todo[:5]:
            print(f"  {t['name']}: {t['description'][:100]}")
        return

    results: dict[str, list[str]] = dict(done)
    lock = threading.Lock()
    failures: list[tuple[str, str]] = []
    n_complete = 0

    def worker(t: dict) -> tuple[str, list[str]]:
        return t["name"], generate_tool_tags(t["name"], t["description"], args.model, api_key)

    def flush() -> None:
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(worker, t): t for t in todo}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                name, tags = fut.result()
                with lock:
                    results[name] = tags
                    n_complete += 1
                    if n_complete % 25 == 0:
                        print(f"  [{n_complete}/{len(todo)}] {name}: {tags}")
                    if n_complete % 50 == 0:
                        flush()
            except TaggingError as e:
                with lock:
                    failures.append((t["name"], str(e)))
                    print(f"  FAILED (kept out of file, not emptied): {t['name']} :: {e}")

    flush()

    tagged = sum(1 for v in results.values() if v)
    print(f"\nDone: {tagged}/{len(results)} tools tagged")
    if failures:
        print(f"UNRECOVERABLE calls: {len(failures)} (absent from the file, never emptied). "
              f"Re-run with --resume to retry them.")
    print(f"Output: {output_path}")

    all_tags = [t for tags in results.values() for t in tags]
    print("\nTag distribution:")
    for tag, count in Counter(all_tags).most_common():
        print(f"  {tag}: {count}")


if __name__ == "__main__":
    main()
