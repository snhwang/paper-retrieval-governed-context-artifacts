"""Download and inspect ToolBench + MetaTool data for BEAR evaluation.

This script handles two external tool-retrieval benchmarks:

1. **ToolBench** (OpenBMB, ICLR 2024 Spotlight)
   - 16,464 APIs across 49 categories from RapidAPI
   - Available via HuggingFace: tuandunghcmut/toolbench-v1 (benchmark split)
   - The benchmark config has query -> relevant_apis ground truth

2. **MetaTool** (HowieHwong, ICLR 2024)
   - 201 tools from OpenAI plugin store
   - 21,127 queries (20,630 single-tool + 497 multi-tool)
   - Data directly in the GitHub repo (small JSON/CSV files)

Usage:
    python toolbench_setup.py                  # download + summarise both
    python toolbench_setup.py --toolbench-only  # just ToolBench
    python toolbench_setup.py --metatool-only   # just MetaTool
    python toolbench_setup.py --sample 5        # show N sample conversions
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from bear.models import Instruction, InstructionType, ScopeCondition

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data" / "external_benchmarks"
TOOLBENCH_DIR = DATA_DIR / "toolbench"
METATOOL_DIR = DATA_DIR / "metatool"

# ---------------------------------------------------------------------------
# MetaTool download (small files, directly from GitHub)
# ---------------------------------------------------------------------------

METATOOL_URLS = {
    "plugin_des.json": "https://raw.githubusercontent.com/HowieHwong/MetaTool/master/dataset/plugin_des.json",
    "plugin_info.json": "https://raw.githubusercontent.com/HowieHwong/MetaTool/master/dataset/plugin_info.json",
    "multi_tool_query_golden.json": "https://raw.githubusercontent.com/HowieHwong/MetaTool/master/dataset/data/multi_tool_query_golden.json",
    "all_clean_data.csv": "https://raw.githubusercontent.com/HowieHwong/MetaTool/master/dataset/data/all_clean_data.csv",
}


def _download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Download a file from URL to dest. Returns True on success."""
    if dest.exists():
        print(f"  [cached] {desc or dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = Request(url, headers={"User-Agent": "BEAR-eval/1.0"})
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)
        size_kb = len(data) / 1024
        print(f"  [downloaded] {desc or dest.name} ({size_kb:.1f} KB)")
        return True
    except (URLError, OSError) as e:
        print(f"  [FAILED] {desc or dest.name}: {e}")
        return False


def download_metatool() -> dict[str, Path]:
    """Download MetaTool dataset files. Returns dict of name -> local path."""
    print("\n=== Downloading MetaTool data ===")
    paths = {}
    for name, url in METATOOL_URLS.items():
        dest = METATOOL_DIR / name
        if _download_file(url, dest, name):
            paths[name] = dest
    return paths


# ---------------------------------------------------------------------------
# ToolBench download (via HuggingFace datasets)
# ---------------------------------------------------------------------------

def download_toolbench() -> dict[str, Path]:
    """Download ToolBench benchmark data via HuggingFace datasets library.

    The tuandunghcmut/toolbench-v1 dataset has a 'benchmark' config with
    splits: g1_instruction, g1_category, g1_tool, g2_instruction,
            g2_category, g3_instruction

    Each row has: query, query_id, api_list, relevant_apis, split.
    """
    print("\n=== Downloading ToolBench data ===")
    TOOLBENCH_DIR.mkdir(parents=True, exist_ok=True)

    cache_file = TOOLBENCH_DIR / "benchmark_data.json"
    if cache_file.exists():
        # Check it's not a placeholder from a failed previous run
        with open(cache_file) as f:
            try:
                data = json.load(f)
                if isinstance(data, dict) and data.get("status") == "datasets_library_required":
                    print("  [stale placeholder] Removing and re-downloading...")
                    cache_file.unlink()
                else:
                    print("  [cached] benchmark_data.json")
                    return {"benchmark_data.json": cache_file}
            except Exception:
                pass  # corrupted cache, re-download

    try:
        from datasets import load_dataset
    except ImportError:
        print("  [INFO] 'datasets' library not installed.")
        print("         Install with: pip install datasets")
        print("         Then re-run this script.")
        # Write a placeholder with instructions
        info = {
            "status": "datasets_library_required",
            "install": "pip install datasets",
            "dataset_id": "tuandunghcmut/toolbench-v1",
            "config": "benchmark",
            "splits": [
                "g1_instruction", "g1_category", "g1_tool",
                "g2_instruction", "g2_category", "g3_instruction",
            ],
            "fields": ["split", "query_id", "query", "api_list", "relevant_apis"],
        }
        with open(cache_file, "w") as f:
            json.dump(info, f, indent=2)
        return {"benchmark_data.json": cache_file}

    print("  Loading tuandunghcmut/toolbench-v1 (benchmark config)...")
    all_rows = {}
    splits = [
        "g1_instruction", "g1_category", "g1_tool",
        "g2_instruction", "g2_category", "g3_instruction",
    ]
    for split_name in splits:
        try:
            ds = load_dataset(
                "tuandunghcmut/toolbench-v1",
                name="benchmark",
                split=split_name,
                trust_remote_code=True,
            )
            rows = []
            for row in ds:
                rows.append({
                    "query_id": row.get("query_id", ""),
                    "query": row.get("query", ""),
                    "api_list": row.get("api_list", ""),
                    "relevant_apis": row.get("relevant_apis", ""),
                    "split": split_name,
                })
            all_rows[split_name] = rows
            print(f"  [loaded] {split_name}: {len(rows)} queries")
        except Exception as e:
            print(f"  [FAILED] {split_name}: {e}")

    with open(cache_file, "w") as f:
        json.dump(all_rows, f, indent=2, default=str)
    print(f"  Saved to {cache_file}")
    return {"benchmark_data.json": cache_file}


# ---------------------------------------------------------------------------
# Data inspection
# ---------------------------------------------------------------------------

def inspect_metatool(paths: dict[str, Path]) -> dict:
    """Summarise MetaTool data and return stats."""
    print("\n=== MetaTool Summary ===")
    stats: dict = {}

    # Tool descriptions
    des_path = paths.get("plugin_des.json")
    if des_path and des_path.exists():
        with open(des_path) as f:
            tool_des = json.load(f)
        stats["n_tools"] = len(tool_des)
        print(f"  Tools: {len(tool_des)}")
        # Show a few tool names
        names = list(tool_des.keys())[:10]
        print(f"  Sample tools: {', '.join(names)}")

    # Tool info (detailed descriptions)
    info_path = paths.get("plugin_info.json")
    if info_path and info_path.exists():
        with open(info_path) as f:
            tool_info = json.load(f)
        stats["n_tool_info"] = len(tool_info)
        if tool_info:
            sample = tool_info[0] if isinstance(tool_info, list) else None
            if sample:
                print(f"  Tool info fields: {list(sample.keys())}")

    # Single-tool queries
    csv_path = paths.get("all_clean_data.csv")
    if csv_path and csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        stats["n_single_queries"] = len(rows)
        if rows:
            stats["csv_columns"] = list(rows[0].keys())
            print(f"  Single-tool queries: {len(rows)}")
            print(f"  CSV columns: {stats['csv_columns']}")
            # Count unique tools referenced
            tool_col = None
            for col in rows[0].keys():
                if "tool" in col.lower() or "plugin" in col.lower():
                    tool_col = col
                    break
            if tool_col:
                unique_tools = set(r[tool_col] for r in rows if r.get(tool_col))
                stats["n_unique_tools_in_queries"] = len(unique_tools)
                print(f"  Unique tools referenced: {len(unique_tools)}")

    # Multi-tool queries
    multi_path = paths.get("multi_tool_query_golden.json")
    if multi_path and multi_path.exists():
        with open(multi_path) as f:
            multi_data = json.load(f)
        stats["n_multi_queries"] = len(multi_data)
        print(f"  Multi-tool queries: {len(multi_data)}")
        if multi_data:
            sample = multi_data[0]
            print(f"  Multi-tool fields: {list(sample.keys())}")
            # Count unique tools in multi-tool queries
            all_tools = set()
            for entry in multi_data:
                tools = entry.get("tool", [])
                if isinstance(tools, list):
                    all_tools.update(tools)
            stats["n_unique_multi_tools"] = len(all_tools)
            print(f"  Unique tools in multi-tool: {len(all_tools)}")

    return stats


def inspect_toolbench(paths: dict[str, Path]) -> dict:
    """Summarise ToolBench data and return stats."""
    print("\n=== ToolBench Summary ===")
    stats: dict = {}

    bench_path = paths.get("benchmark_data.json")
    if not bench_path or not bench_path.exists():
        print("  No benchmark data available")
        return stats

    with open(bench_path) as f:
        data = json.load(f)

    if "status" in data and data.get("status") == "datasets_library_required":
        print("  Data not yet downloaded (need 'datasets' library)")
        print(f"  Install: {data.get('install', 'pip install datasets')}")
        return stats

    total_queries = 0
    all_categories = set()
    all_tools = set()
    all_apis = set()

    for split_name, rows in data.items():
        n = len(rows)
        total_queries += n
        print(f"  {split_name}: {n} queries")

        for row in rows:
            # Parse api_list (JSON string)
            api_list_str = row.get("api_list", "[]")
            try:
                api_list = json.loads(api_list_str) if isinstance(api_list_str, str) else api_list_str
            except json.JSONDecodeError:
                api_list = []

            for api in api_list:
                if isinstance(api, dict):
                    cat = api.get("category_name", "")
                    tool = api.get("tool_name", "")
                    api_name = api.get("api_name", "")
                    if cat:
                        all_categories.add(cat)
                    if tool:
                        all_tools.add(tool)
                    if api_name:
                        all_apis.add(f"{cat}/{tool}/{api_name}")

    stats["n_queries"] = total_queries
    stats["n_categories"] = len(all_categories)
    stats["n_tools"] = len(all_tools)
    stats["n_apis"] = len(all_apis)
    stats["categories"] = sorted(all_categories)

    print(f"\n  Total queries: {total_queries}")
    print(f"  Unique categories: {len(all_categories)}")
    print(f"  Unique tools: {len(all_tools)}")
    print(f"  Unique APIs: {len(all_apis)}")
    if all_categories:
        sample_cats = sorted(all_categories)[:10]
        print(f"  Sample categories: {', '.join(sample_cats)}")

    return stats


# ---------------------------------------------------------------------------
# Sample BEAR conversions
# ---------------------------------------------------------------------------

def convert_metatool_to_bear(
    tool_des: dict[str, str],
    tool_info: list[dict] | None = None,
) -> list[Instruction]:
    """Convert MetaTool tools to BEAR Instruction format.

    Args:
        tool_des: {tool_name: description} from plugin_des.json
        tool_info: List of dicts from plugin_info.json (optional, richer descriptions)

    Returns:
        List of BEAR Instructions.
    """
    # Build lookup from tool_info for richer descriptions
    info_lookup: dict[str, dict] = {}
    if tool_info:
        for entry in tool_info:
            key = entry.get("name_for_model", "")
            if key:
                info_lookup[key] = entry

    instructions = []
    for tool_name, short_desc in tool_des.items():
        # Use richer description from tool_info if available
        info = info_lookup.get(tool_name, {})
        model_desc = info.get("description_for_model", "")
        human_desc = info.get("description_for_human", short_desc)

        # Combine descriptions for content
        content_parts = [f"Tool: {tool_name}"]
        if human_desc:
            content_parts.append(f"Description: {human_desc}")
        if model_desc and model_desc != human_desc:
            content_parts.append(f"Usage: {model_desc}")

        content = "\n".join(content_parts)

        inst = Instruction(
            id=f"metatool/{tool_name}",
            type=InstructionType.TOOL,
            priority=50,
            content=content,
            scope=ScopeCondition(
                required_tags=[],  # MetaTool has no category hierarchy
                tags=[tool_name.lower()],
            ),
            metadata={"source": "metatool", "tool_name": tool_name},
            tags=[tool_name.lower()],
        )
        instructions.append(inst)

    return instructions


def convert_toolbench_api_to_bear(api: dict, category: str) -> Instruction:
    """Convert a single ToolBench API entry to a BEAR Instruction.

    Args:
        api: Dict with category_name, tool_name, api_name, and optionally
             api_description, required_parameters, optional_parameters.
        category: The ToolBench category name.

    Returns:
        A BEAR Instruction.
    """
    cat = api.get("category_name", category)
    tool = api.get("tool_name", "unknown")
    api_name = api.get("api_name", "unknown")
    desc = api.get("api_description", f"{tool} - {api_name}")

    # Build content from available fields
    content_parts = [f"API: {tool} / {api_name}", f"Category: {cat}"]
    if desc:
        content_parts.append(f"Description: {desc}")

    # Include parameters if available
    req_params = api.get("required_parameters", [])
    opt_params = api.get("optional_parameters", [])
    if req_params:
        param_strs = []
        for p in req_params:
            if isinstance(p, dict):
                param_strs.append(f"  - {p.get('name', '?')} ({p.get('type', '?')}): {p.get('description', '')}")
            else:
                param_strs.append(f"  - {p}")
        content_parts.append("Required parameters:\n" + "\n".join(param_strs))
    if opt_params:
        param_strs = []
        for p in opt_params:
            if isinstance(p, dict):
                param_strs.append(f"  - {p.get('name', '?')} ({p.get('type', '?')}): {p.get('description', '')}")
            else:
                param_strs.append(f"  - {p}")
        content_parts.append("Optional parameters:\n" + "\n".join(param_strs))

    content = "\n".join(content_parts)

    # Build actions in OpenAI function-calling format
    actions: dict = {}
    if req_params or opt_params:
        properties = {}
        required = []
        for p in req_params:
            if isinstance(p, dict):
                pname = p.get("name", "param")
                properties[pname] = {
                    "type": p.get("type", "string"),
                    "description": p.get("description", ""),
                }
                required.append(pname)
        for p in opt_params:
            if isinstance(p, dict):
                pname = p.get("name", "param")
                properties[pname] = {
                    "type": p.get("type", "string"),
                    "description": p.get("description", ""),
                }
        if properties:
            actions["function"] = {
                "name": f"{tool}__{api_name}",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }

    # Normalise category to a tag
    cat_tag = cat.lower().replace(" ", "_").replace("&", "and")

    inst = Instruction(
        id=f"toolbench/{cat_tag}/{tool}/{api_name}",
        type=InstructionType.TOOL,
        priority=50,
        content=content,
        actions=actions,
        scope=ScopeCondition(
            required_tags=[cat_tag],
            tags=[cat_tag, tool.lower()],
        ),
        metadata={
            "source": "toolbench",
            "category": cat,
            "tool_name": tool,
            "api_name": api_name,
        },
        tags=[cat_tag, tool.lower()],
    )
    return inst


def show_sample_conversions(n_samples: int = 3):
    """Load data and show sample BEAR conversions."""
    print(f"\n=== Sample BEAR Conversions (n={n_samples}) ===")

    # MetaTool
    des_path = METATOOL_DIR / "plugin_des.json"
    info_path = METATOOL_DIR / "plugin_info.json"
    if des_path.exists():
        with open(des_path) as f:
            tool_des = json.load(f)
        tool_info = None
        if info_path.exists():
            with open(info_path) as f:
                tool_info = json.load(f)

        instructions = convert_metatool_to_bear(tool_des, tool_info)
        print(f"\n  MetaTool -> BEAR: {len(instructions)} instructions")
        for inst in instructions[:n_samples]:
            print(f"\n  --- {inst.id} ---")
            print(f"  type: {inst.type.value}")
            print(f"  tags: {inst.tags}")
            print(f"  scope.tags: {inst.scope.tags}")
            print(f"  content (first 200 chars): {inst.content[:200]}")

    # ToolBench
    bench_path = TOOLBENCH_DIR / "benchmark_data.json"
    if bench_path.exists():
        with open(bench_path) as f:
            data = json.load(f)

        if "status" not in data:
            # Grab APIs from the first split that has data
            shown = 0
            for split_name, rows in data.items():
                if shown >= n_samples:
                    break
                for row in rows:
                    if shown >= n_samples:
                        break
                    api_list_str = row.get("api_list", "[]")
                    try:
                        api_list = json.loads(api_list_str) if isinstance(api_list_str, str) else api_list_str
                    except json.JSONDecodeError:
                        continue
                    for api in api_list[:1]:  # Just first API per query
                        if not isinstance(api, dict):
                            continue
                        cat = api.get("category_name", "unknown")
                        inst = convert_toolbench_api_to_bear(api, cat)
                        print(f"\n  --- {inst.id} ---")
                        print(f"  type: {inst.type.value}")
                        print(f"  tags: {inst.tags}")
                        print(f"  scope.required_tags: {inst.scope.required_tags}")
                        print(f"  content (first 200 chars): {inst.content[:200]}")
                        if inst.actions:
                            print(f"  actions keys: {list(inst.actions.keys())}")
                        shown += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download and inspect ToolBench + MetaTool data for BEAR evaluation."
    )
    parser.add_argument("--toolbench-only", action="store_true")
    parser.add_argument("--metatool-only", action="store_true")
    parser.add_argument("--sample", type=int, default=3,
                        help="Number of sample BEAR conversions to show")
    parser.add_argument("--no-download", action="store_true",
                        help="Skip download, only inspect cached data")
    args = parser.parse_args()

    do_toolbench = not args.metatool_only
    do_metatool = not args.toolbench_only

    # Download
    metatool_paths: dict[str, Path] = {}
    toolbench_paths: dict[str, Path] = {}

    if not args.no_download:
        if do_metatool:
            metatool_paths = download_metatool()
        if do_toolbench:
            toolbench_paths = download_toolbench()
    else:
        # Use cached paths
        if do_metatool:
            for name in METATOOL_URLS:
                p = METATOOL_DIR / name
                if p.exists():
                    metatool_paths[name] = p
        if do_toolbench:
            p = TOOLBENCH_DIR / "benchmark_data.json"
            if p.exists():
                toolbench_paths["benchmark_data.json"] = p

    # Inspect
    if do_metatool and metatool_paths:
        inspect_metatool(metatool_paths)
    if do_toolbench and toolbench_paths:
        inspect_toolbench(toolbench_paths)

    # Sample conversions
    if args.sample > 0:
        show_sample_conversions(args.sample)

    print("\n=== Setup complete ===")
    print(f"  Data directory: {DATA_DIR}")
    if metatool_paths:
        print(f"  MetaTool files: {len(metatool_paths)}")
    if toolbench_paths:
        print(f"  ToolBench files: {len(toolbench_paths)}")


if __name__ == "__main__":
    main()
