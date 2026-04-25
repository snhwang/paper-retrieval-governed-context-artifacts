"""Generate category tags for MetaTool tools using an LLM.

This script enriches the MetaTool corpus with structured category tags,
enabling BEAR governance on a corpus that originally has no metadata.
The experiment tests whether governance adds value when metadata is
LLM-generated rather than human-authored.

Usage:
    # Claude Sonnet (recommended)
    python metatool_generate_tags.py \
        --model claude-sonnet-4-5-20251101

    # GPT-5.4 Mini
    python metatool_generate_tags.py \
        --base-url https://api.openai.com/v1 \
        --model gpt-5.4-mini-2026-03-17

Output:
    data/external_benchmarks/metatool/plugin_tags.json
    A dict mapping tool name -> list of 1-3 category tags.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parent / "data" / "external_benchmarks" / "metatool"

# Tag taxonomy — domain-focused categories (not mechanism-focused)
# Deliberately excludes generic "search" — use the domain instead
TAG_TAXONOMY = """
Use 1-3 tags from this taxonomy (use exact strings).
Focus on WHAT the tool is about, not HOW it works.
Do NOT use "search" as a tag — use the domain instead.

- travel (hotels, flights, transport, destinations, accommodation, booking)
- weather (forecasts, climate, air quality, alerts, outdoor conditions)
- finance (stocks, crypto, banking, payments, currency, investment, tax)
- food (restaurants, recipes, delivery, nutrition, cooking, dining)
- shopping (products, prices, deals, ecommerce, retail, comparison)
- health (medical, fitness, wellness, symptoms, drugs, mental health)
- news (current events, articles, media, journalism, headlines)
- entertainment (games, movies, music, sports, books, streaming, events)
- productivity (calendar, tasks, notes, email, documents, scheduling)
- developer (code, APIs, databases, devtools, hosting, testing, CI/CD)
- knowledge (encyclopedias, facts, definitions, Q&A, reference)
- communication (messaging, social media, translation, chat, notifications)
- data (analytics, statistics, charts, datasets, visualization, metrics)
- education (learning, courses, tutoring, language learning, quizzes)
- security (privacy, authentication, monitoring, cybersecurity, VPN)
- business (CRM, marketing, HR, legal, real estate, contracts, B2B)
- image (photos, visual search, design, art, generation, editing)
- location (maps, places, geolocation, directions, local, nearby)
- science (research, papers, biology, chemistry, physics, space)
- search (general web search or multi-domain information retrieval ONLY —
  use only when no specific domain tag fits; always pair with a domain tag)

Rules:
1. Always include at least one domain-specific tag (not just "search").
2. "search" may be added as a secondary tag if the tool does general retrieval,
   but never as the only tag.
3. Pick the 1-3 most relevant tags. Fewer precise tags beat many vague ones.
"""

PROMPT_TEMPLATE = """You are categorizing API tools for a retrieval system.
Given a tool name and description, assign 1-3 category tags.

{taxonomy}

IMPORTANT: The tool NAME is the strongest signal. Use it first.
For example: "WeatherTool" → ["weather"], "FinanceTool" → ["finance"],
"keyplays_football" → ["entertainment"] (football is entertainment/sports,
not weather even if the description mentions weather as a side detail).
Do not tag incidental keywords — focus on the tool's PRIMARY purpose.

Tool name: {name}
Description: {description}

Respond with ONLY a JSON array of tag strings, e.g.: ["finance", "search"]
No explanation, no other text."""


def call_llm(prompt: str, model: str, base_url: str) -> str:
    """Call OpenAI-compatible or Anthropic API."""
    host = urllib.parse.urlparse(base_url).hostname or ""

    if "anthropic.com" in host or "anthropic" in model:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        payload = json.dumps({
            "model": model,
            "max_tokens": 100,
            "temperature": 0.0,
            "system": "You are a precise API categorization assistant. Respond only with valid JSON.",
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload, headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"].strip()

    # OpenAI-compatible
    token_param = "max_completion_tokens" if "openai.com" in host else "max_tokens"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise API categorization assistant. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        token_param: 100,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("OPENAI_API_KEY") if "openai.com" in host else os.environ.get("OLLAMA_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{base_url}/chat/completions", data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def parse_tags(response: str, valid_tags: set[str]) -> list[str]:
    """Parse LLM response into validated tag list."""
    # Extract JSON array
    response = response.strip()
    if not response.startswith("["):
        # Try to find JSON array in response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            response = response[start:end]
        else:
            return []
    try:
        tags = json.loads(response)
        if not isinstance(tags, list):
            return []
        # Validate against taxonomy
        validated = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip().lower() in valid_tags]
        validated = validated[:3]  # Max 3 tags
        # Enforce: search must not be the only tag
        if validated == ["search"]:
            return []
        return validated
    except json.JSONDecodeError:
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-sonnet-4-5-20251101")
    parser.add_argument("--base-url", default="https://api.anthropic.com/v1",
                        help="Not needed for Anthropic; use for OpenAI or local")
    parser.add_argument("--output", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing partial output")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show first 5 tools without calling LLM")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else DATA_DIR / "plugin_tags.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load tools from plugin_des.json (covers all ~390 tools)
    # Fall back to plugin_info.json for richer descriptions where available
    plugin_des_path = DATA_DIR / "plugin_des.json"
    plugin_info_path = DATA_DIR / "plugin_info.json"
    if not plugin_des_path.exists():
        print("ERROR: plugin_des.json not found. Run toolbench_setup.py first.")
        return

    with open(plugin_des_path) as f:
        des_data = json.load(f)  # {tool_name: short_description}

    # Build richer descriptions from plugin_info where available
    info_lookup: dict[str, dict] = {}
    if plugin_info_path.exists():
        with open(plugin_info_path) as f:
            for item in json.load(f):
                name = item.get("name_for_model", "")
                if name:
                    info_lookup[name] = item

    # Build unified tool list from plugin_des (all tools)
    unique_tools = []
    for tool_name, short_desc in des_data.items():
        info = info_lookup.get(tool_name, {})
        model_desc = info.get("description_for_model", "")
        human_desc = info.get("description_for_human", short_desc)
        # Use richest available description
        description = model_desc or human_desc or short_desc
        unique_tools.append({
            "name_for_model": tool_name,
            "description": description,
        })

    print(f"Unique tools to tag: {len(unique_tools)}")

    # Resume from existing partial output
    existing_tags: dict[str, list[str]] = {}
    if args.resume and output_path.exists():
        with open(output_path) as f:
            existing_tags = json.load(f)
        print(f"Resuming: {len(existing_tags)} already tagged")

    # Build valid tag set from taxonomy
    valid_tags = {line.split("(")[0].strip().lstrip("- ").strip()
                  for line in TAG_TAXONOMY.strip().split("\n")
                  if line.strip().startswith("-")}

    if args.dry_run:
        print("\nDry run — first 5 tools:")
        for t in unique_tools[:5]:
            name = t.get("name_for_model", "")
            desc = t.get("description_for_model", "") or t.get("description_for_human", "")
            print(f"  {name}: {desc[:100]}")
        print(f"\nValid tags: {sorted(valid_tags)}")
        return

    results = dict(existing_tags)
    errors = 0

    for i, tool in enumerate(unique_tools):
        name = tool.get("name_for_model", "").strip()
        if name in results:
            continue

        desc = (tool.get("description_for_model", "") or
                tool.get("description_for_human", "") or "").strip()[:500]

        prompt = PROMPT_TEMPLATE.format(
            taxonomy=TAG_TAXONOMY,
            name=name,
            description=desc,
        )

        try:
            response = call_llm(prompt, args.model, args.base_url)
            tags = parse_tags(response, valid_tags)
            results[name] = tags
            print(f"  [{i+1}/{len(unique_tools)}] {name}: {tags}")
        except Exception as e:
            print(f"  [{i+1}/{len(unique_tools)}] ERROR {name}: {e}")
            results[name] = []
            errors += 1

        # Save incrementally every 10 tools
        if (i + 1) % 10 == 0:
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)

        # Small delay to avoid rate limiting
        time.sleep(0.1)

    # Final save
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    tagged = sum(1 for v in results.values() if v)
    print(f"\nDone: {tagged}/{len(results)} tools tagged successfully")
    print(f"Errors: {errors}")
    print(f"Output: {output_path}")

    # Tag distribution
    from collections import Counter
    all_tags = [t for tags in results.values() for t in tags]
    print(f"\nTag distribution:")
    for tag, count in Counter(all_tags).most_common():
        print(f"  {tag}: {count}")


if __name__ == "__main__":
    main()
