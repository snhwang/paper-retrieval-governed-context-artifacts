"""Constrained MetaTool tag generation via Anthropic tool_use.

Single source of truth for the tag vocabulary and the forced-selection API
path shared by ``metatool_generate_tags.py`` (tool side) and
``metatool_generate_query_tags_top5.py`` (query side).

Why this exists. The earlier generators prompted for a free-form JSON array and
parsed it with ``json.loads`` inside a ``try`` whose ``except`` returned ``[]``.
A malformed response, an out-of-vocabulary tag, or the degenerate
single-``search`` answer therefore became a silent empty tag list -- and an
empty tag list is not neutral: the BEAR ``required_tags`` gate hard-excludes a
query that carries no usable tag, forcing recall to 0 by construction. That
turned a tagger failure into what looked like a governance failure.

The fix is structural, not cosmetic. Selection is forced through a tool whose
``input_schema`` enumerates the closed vocabulary, so the model cannot emit
malformed JSON or an off-vocabulary tag. The taxonomy's own rule -- "always
include at least one domain-specific tag, never only the generic search tag" --
is encoded in the schema itself: the query-side tool has a required
``primary_domain`` field drawn from the 19 domain tags, so a starved query is
impossible rather than merely discouraged. Nothing is ever silently dropped to
an empty list; an unrecoverable call raises.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# The 19 domain tags, in taxonomy order, with the exact descriptions the
# earlier prompts used. `search` is deliberately NOT a domain tag: it is the
# generic fallback and may only appear alongside a domain tag on the query
# side, and never on the tool side.
DOMAIN_TAGS: list[tuple[str, str]] = [
    ("travel", "hotels, flights, transport, destinations, accommodation, booking"),
    ("weather", "forecasts, climate, air quality, alerts, outdoor conditions"),
    ("finance", "stocks, crypto, banking, payments, currency, investment, tax"),
    ("food", "restaurants, recipes, delivery, nutrition, cooking, dining"),
    ("shopping", "products, prices, deals, ecommerce, retail, comparison"),
    ("health", "medical, fitness, wellness, symptoms, drugs, mental health"),
    ("news", "current events, articles, media, journalism, headlines"),
    ("entertainment", "games, movies, music, sports, books, streaming, events"),
    ("productivity", "calendar, tasks, notes, email, documents, scheduling"),
    ("developer", "code, APIs, databases, devtools, hosting, testing, CI/CD"),
    ("knowledge", "encyclopedias, facts, definitions, Q&A, reference"),
    ("communication", "messaging, social media, translation, chat, notifications"),
    ("data", "analytics, statistics, charts, datasets, visualization, metrics"),
    ("education", "learning, courses, tutoring, language learning, quizzes"),
    ("security", "privacy, authentication, monitoring, cybersecurity, VPN"),
    ("business", "CRM, marketing, HR, legal, real estate, contracts, B2B"),
    ("image", "photos, visual search, design, art, generation, editing"),
    ("location", "maps, places, geolocation, directions, local, nearby"),
    ("science", "research, papers, biology, chemistry, physics, space"),
]
SEARCH_DESC = "general web search or multi-domain retrieval; pair with a domain tag"

DOMAIN_NAMES: list[str] = [t for t, _ in DOMAIN_TAGS]
QUERY_VOCAB: list[str] = DOMAIN_NAMES + ["search"]


def taxonomy_text(include_search: bool) -> str:
    """The taxonomy as a human-readable bullet list for the prompt body."""
    lines = [f"- {name} ({desc})" for name, desc in DOMAIN_TAGS]
    if include_search:
        lines.append(f"- search ({SEARCH_DESC})")
    return "\n".join(lines)


class TaggingError(RuntimeError):
    """Raised when a call cannot be completed; never swallowed into empty tags."""


def _anthropic_tool_call(
    *,
    system: str,
    user: str,
    model: str,
    tool: dict,
    api_key: str,
    max_tokens: int = 300,
    max_retries: int = 6,
    timeout: int = 60,
) -> dict:
    """POST a forced tool_use request; return the tool_use ``input`` dict.

    Retries transient failures (HTTP 429/5xx, timeouts) with exponential
    backoff honoring ``Retry-After``. Raises :class:`TaggingError` on a
    non-transient failure or once retries are exhausted -- the caller must not
    convert that into an empty result.
    """
    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "system": system,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(ANTHROPIC_URL, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            for block in data.get("content", []):
                if block.get("type") == "tool_use":
                    return block["input"]
            # The model answered without calling the forced tool. This is rare
            # and usually transient (a refusal-shaped completion); retry.
            last_err = TaggingError(f"no tool_use block in response: {data.get('stop_reason')}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (429, 500, 502, 503, 529):
                retry_after = e.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(2 ** attempt, 30)
                last_err = TaggingError(f"HTTP {e.code}: {body}")
                time.sleep(wait + random.uniform(0, 0.5))
                continue
            raise TaggingError(f"HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30) + random.uniform(0, 0.5))
            continue
        else:
            continue
        time.sleep(min(2 ** attempt, 30) + random.uniform(0, 0.5))
    raise TaggingError(f"exhausted {max_retries} retries; last error: {last_err}")


# --- Tool schemas ----------------------------------------------------------

_QUERY_TOOL = {
    "name": "assign_query_categories",
    "description": (
        "Assign domain category tags describing what the user needs. Choose the "
        "single best-fitting domain as primary_domain, then up to four more "
        "categories in descending order of likelihood."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_domain": {
                "type": "string",
                "enum": DOMAIN_NAMES,
                "description": "The single best-fitting domain category.",
            },
            "additional_tags": {
                "type": "array",
                "items": {"type": "string", "enum": QUERY_VOCAB},
                "maxItems": 4,
                "description": "Up to four further categories, most likely first.",
            },
        },
        "required": ["primary_domain", "additional_tags"],
    },
}

_TOOL_TOOL = {
    "name": "assign_tool_categories",
    "description": (
        "Assign 1-3 domain category tags describing the tool's primary purpose. "
        "The tool name is the strongest signal; ignore incidental keywords."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string", "enum": DOMAIN_NAMES},
                "minItems": 1,
                "maxItems": 3,
                "description": "1-3 domain categories, most relevant first.",
            },
        },
        "required": ["tags"],
    },
}


def generate_query_tags(query: str, model: str, api_key: str, k: int = 5) -> list[str]:
    """Up to ``k`` ranked domain tags for a query; always >=1 domain tag.

    The primary domain is a required enum field, so the result can never be
    empty or search-only. Returns a deduped list of length 1..k.
    """
    system = (
        "You categorize user queries for a tool-retrieval system. Base your "
        "answer only on the query text; do not guess a tool name. Focus on what "
        "the user needs, not how a tool would find it."
    )
    user = (
        "Category taxonomy (use these exact names):\n"
        f"{taxonomy_text(include_search=True)}\n\n"
        f"Query: {query}\n\n"
        "Call assign_query_categories with the best-fitting primary domain and "
        f"up to {k - 1} additional categories in descending order of likelihood."
    )
    out = _anthropic_tool_call(system=system, user=user, model=model,
                               tool=_QUERY_TOOL, api_key=api_key)
    # Anthropic tool_use enums are a soft guide, not a hard grammar constraint,
    # so `primary_domain` occasionally comes back as the generic `search` tag
    # despite its domain-only enum. Assemble from all returned tags and promote
    # the first genuine domain tag to the front, rather than trusting the field.
    candidates = [out.get("primary_domain"), *out.get("additional_tags", [])]
    ranked: list[str] = []
    for t in candidates:
        if t in QUERY_VOCAB and t not in ranked:
            ranked.append(t)
    domain = [t for t in ranked if t in DOMAIN_NAMES]
    if not domain:
        raise TaggingError(f"no domain tag in response: {candidates!r}")
    # Ensure a domain tag leads (the taxonomy's rule); keep the rest in order.
    lead = domain[0]
    ranked = [lead] + [t for t in ranked if t != lead]
    return ranked[:k]


def generate_tool_tags(name: str, description: str, model: str, api_key: str) -> list[str]:
    """1-3 domain tags for a tool; always >=1, never the generic search tag."""
    system = (
        "You categorize API tools for a retrieval system. The tool NAME is the "
        "strongest signal; use it first and ignore incidental keywords in the "
        "description. Tag the tool's primary purpose."
    )
    user = (
        "Category taxonomy (use these exact names):\n"
        f"{taxonomy_text(include_search=False)}\n\n"
        f"Tool name: {name}\n"
        f"Description: {description}\n\n"
        "Call assign_tool_categories with the 1-3 most relevant domain "
        "categories. Fewer precise tags beat many vague ones."
    )
    out = _anthropic_tool_call(system=system, user=user, model=model,
                               tool=_TOOL_TOOL, api_key=api_key)
    tags: list[str] = []
    for t in out.get("tags", []):
        if t in DOMAIN_NAMES and t not in tags:
            tags.append(t)
        if len(tags) >= 3:
            break
    if not tags:
        raise TaggingError(f"tool {name!r} produced no valid tag")
    return tags


def require_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Put it in the repo-root .env "
            "(loaded automatically) or export it before running."
        )
    return key
