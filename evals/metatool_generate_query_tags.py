"""Generate context tags for MetaTool queries using an LLM.

This script tags each query with 1-3 domain categories based on the
query text alone — NOT using knowledge of the target tool. This is
the stronger test: if the LLM can infer the right domain from the
query, and those domain tags match the tool's tags, then the taxonomy
is coherent and governance is genuinely useful.

Usage:
    python metatool_generate_query_tags.py \
        --model claude-sonnet-4-6

Output:
    data/external_benchmarks/metatool/query_tags.json
    A list of {query, context_tags, tool} dicts.
"""

from __future__ import annotations

import argparse
import csv
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

# Same taxonomy as metatool_generate_tags.py for consistency
TAG_TAXONOMY = """
Use 1-3 tags from this taxonomy (use exact strings).
Focus on WHAT the user needs, not HOW to find it.
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
- search (general web search ONLY — always pair with a domain tag)

Rules:
1. Always include at least one domain-specific tag.
2. Base your answer ONLY on the query text — do not guess the tool name.
3. Pick the 1-3 most relevant tags. Fewer precise tags beat many vague ones.
"""

PROMPT_TEMPLATE = """You are categorizing user queries for a tool retrieval system.
Given a query, assign 1-3 domain category tags describing what the user needs.

{taxonomy}

Query: {query}

Respond with ONLY a JSON array of tag strings, e.g.: ["finance", "data"]
No explanation, no other text."""


def call_llm(prompt: str, model: str, base_url: str) -> str:
    host = urllib.parse.urlparse(base_url).hostname or ""
    if "anthropic.com" in host or "anthropic" in model:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        payload = json.dumps({
            "model": model,
            "max_tokens": 60,
            "temperature": 0.0,
            "system": "You are a precise query categorization assistant. Respond only with valid JSON.",
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

    token_param = "max_completion_tokens" if "openai.com" in host else "max_tokens"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise query categorization assistant. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        token_param: 60,
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
    response = response.strip()
    if not response.startswith("["):
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
        validated = [t.strip().lower() for t in tags
                     if isinstance(t, str) and t.strip().lower() in valid_tags]
        validated = validated[:3]
        if validated == ["search"]:
            return []
        return validated
    except json.JSONDecodeError:
        return []


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
    parser.add_argument("--base-url", default="https://api.anthropic.com/v1")
    parser.add_argument("--output", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-queries", type=int, default=None,
                        help="Limit number of queries (for testing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else DATA_DIR / "query_tags.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    queries = load_queries()
    # Shuffle before sampling to get broad tool coverage
    import random as _random
    _random.seed(42)
    _random.shuffle(queries)
    if args.max_queries:
        queries = queries[:args.max_queries]

    print(f"Total queries to tag: {len(queries)}")

    # Resume
    existing: list[dict] = []
    existing_set: set[str] = set()
    if args.resume and output_path.exists():
        with open(output_path) as f:
            existing = json.load(f)
        existing_set = {e["query"] for e in existing}
        print(f"Resuming: {len(existing)} already tagged")

    valid_tags = {
        "travel", "weather", "finance", "food", "shopping", "health",
        "news", "entertainment", "productivity", "developer", "knowledge",
        "communication", "data", "education", "security", "business",
        "image", "location", "science", "search",
    }

    if args.dry_run:
        print("\nDry run — first 5 queries:")
        for q in queries[:5]:
            print(f"  {q['query'][:100]}")
            print(f"    tools: {q['tools']}")
        return

    results = list(existing)
    errors = 0

    for i, q in enumerate(queries):
        query_text = q["query"]
        if query_text in existing_set:
            continue

        prompt = PROMPT_TEMPLATE.format(
            taxonomy=TAG_TAXONOMY,
            query=query_text,
        )

        try:
            response = call_llm(prompt, args.model, args.base_url)
            tags = parse_tags(response, valid_tags)
            entry = {
                "query": query_text,
                "context_tags": tags,
                "tools": q["tools"],
                "type": q["type"],
            }
            results.append(entry)
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(queries)}] {query_text[:60]} → {tags}")
        except Exception as e:
            print(f"  [{i+1}/{len(queries)}] ERROR: {e}")
            results.append({
                "query": query_text,
                "context_tags": [],
                "tools": q["tools"],
                "type": q["type"],
            })
            errors += 1

        if (i + 1) % 500 == 0:
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            print(f"  Saved {len(results)} queries")

        time.sleep(0.05)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    tagged = sum(1 for r in results if r["context_tags"])
    print(f"\nDone: {tagged}/{len(results)} queries tagged")
    print(f"Errors: {errors}")
    print(f"Output: {output_path}")

    from collections import Counter
    all_tags = [t for r in results for t in r["context_tags"]]
    print(f"\nQuery tag distribution:")
    for tag, count in Counter(all_tags).most_common():
        print(f"  {tag}: {count}")


if __name__ == "__main__":
    main()
