#!/usr/bin/env python3
"""Sample WP7's decoy tools from ToolBench, seeded, and write their corpus rules.

Decoy names and descriptions are ToolBench's (RapidAPI authors'), so no decoy text is ours.
Run once. The outputs are committed, and the decoy plugin and the runner read them.

Pool. Every unique (category, tool, API) in evals/data/external_benchmarks/toolbench/
benchmark_data.json, kept when:
- the API description is 20 to 600 characters after stripping,
- it has at most 8 parameters, each with a usable name and a description of at most 300
  characters,
- no text field holds a control character or an escaped-backslash run (scraping debris).
Texts are kept verbatim. Nothing is truncated or edited.

In scope (team:ops), N_IN_SCOPE decoys. For each of the real tools in IN_SCOPE_TARGETS, the
not-yet-taken pool API most similar to that tool, comparing "name: description" texts (the form
the narrowing ranks) by cosine under the Nemotron embedder on port 8360 (--near tfidf is an
offline fallback). These sit near real tools and stress relevance. The embedder identity and
every similarity are recorded in sample.json.

Out of scope, the rest. A seeded uniform shuffle of the remaining pool. Each is scoped
required_tags: [team:<RapidAPI category>], so the team:ops context never passes its gate.

Sizes nest. Size N is every in-scope decoy plus the first N - N_IN_SCOPE out-of-scope ones,
so the size-100 set is a subset of the size-300 set.

Usage: make_decoys.py [--toolbench PATH] [--seed 20261029]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from collections import Counter

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
HERMES_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(HERMES_DIR)
DEFAULT_TOOLBENCH = os.path.join(REPO, "evals", "data", "external_benchmarks", "toolbench",
                                 "benchmark_data.json")
REGISTRY = os.path.join(HERMES_DIR, "registry", "harness_registry.json")
SAMPLE_OUT = os.path.join(HERE, "sample.json")
CORPUS_OUT = os.path.join(HERMES_DIR, "corpus", "decoys")

SEED = 20261029
SIZES = (100, 300)
IN_SCOPE_TARGETS = ("search_files", "read_file", "web_search", "web_extract",
                    "image_generate", "cronjob_manage", "session_search", "process_manage")
N_IN_SCOPE = len(IN_SCOPE_TARGETS)
IN_SCOPE_TAG = "team:ops"
DECOY_PRIORITY = 60
TOOLSET = "wp7_decoys"

DESC_MIN, DESC_MAX = 20, 600
MAX_PARAMS, PARAM_DESC_MAX = 8, 300
_TYPE = {"STRING": "string", "NUMBER": "number", "INTEGER": "integer", "BOOLEAN": "boolean",
         "ARRAY": "array", "OBJECT": "object"}
_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|\\\\")
_PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are as at be by for from get gets in is it of on or the this to with "
                  "you your can will that which".split())


def _clean(s) -> str:
    return s.strip() if isinstance(s, str) else ""


def _params(api: dict):
    """A JSON schema for the API's parameters, or None if any parameter fails the filter."""
    props, required = {}, []
    plist = [(p, True) for p in api.get("required_parameters") or []] + \
            [(p, False) for p in api.get("optional_parameters") or []]
    if len(plist) > MAX_PARAMS:
        return None
    for p, req in plist:
        name = _clean(p.get("name"))
        desc = _clean(p.get("description"))
        if not _PARAM_NAME.match(name) or name in props or _BAD.search(desc) or len(desc) > PARAM_DESC_MAX:
            return None
        ptype = _TYPE.get(str(p.get("type") or "").upper(), "string")
        prop = {"type": ptype}
        if ptype == "array":
            prop["items"] = {"type": "string"}
        if desc:
            prop["description"] = desc
        props[name] = prop
        if req:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def _name(tool: str, api: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", f"{tool} {api}".lower()).strip("_")
    return base[:56].rstrip("_") or "api"


def load_pool(path: str) -> list[dict]:
    data = json.load(open(path, encoding="utf-8"))
    seen: dict[tuple, dict] = {}
    for split in sorted(data):
        for row in data[split]:
            apis = row.get("api_list")
            if isinstance(apis, str):
                apis = json.loads(apis)
            for a in apis or []:
                key = (_clean(a.get("category_name")), _clean(a.get("tool_name")),
                       _clean(a.get("api_name")))
                if all(key) and key not in seen:
                    seen[key] = a
    pool = []
    for key in sorted(seen):
        a = seen[key]
        desc = _clean(a.get("api_description"))
        if not DESC_MIN <= len(desc) <= DESC_MAX or _BAD.search(desc):
            continue
        params = _params(a)
        if params is None:
            continue
        pool.append({"category": key[0], "tool_name": key[1], "api_name": key[2],
                     "description": desc, "parameters": params})
    return pool


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def _tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    df = Counter(w for d in docs for w in set(d))
    n = len(docs)
    out = []
    for d in docs:
        tf = Counter(d)
        v = {w: (c / len(d)) * math.log((1 + n) / (1 + df[w])) for w, c in tf.items()} if d else {}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out.append({w: x / norm for w, x in v.items()})
    return out


def _cos(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def _similarities(pool_texts: list[str], target_texts: list[str], method: str,
                  embed_url: str) -> tuple[list[list[float]], dict]:
    """sims[t][i]: similarity of target t to pool item i, and how it was computed."""
    if method == "embed":
        import numpy as np
        from bear.remote_embedder import RemoteEmbedder
        emb = RemoteEmbedder(embed_url)
        p = np.asarray(emb.embed(pool_texts, is_query=False), dtype=float)
        t = np.asarray(emb.embed(target_texts, is_query=False), dtype=float)
        p /= np.linalg.norm(p, axis=1, keepdims=True)
        t /= np.linalg.norm(t, axis=1, keepdims=True)
        return (t @ p.T).tolist(), {"method": "embed", "url": embed_url, **emb.identity()}
    vecs = _tfidf([_tokens(x) for x in pool_texts] + [_tokens(x) for x in target_texts])
    pv, tv = vecs[:len(pool_texts)], vecs[len(pool_texts):]
    return [[_cos(t, v) for v in pv] for t in tv], {"method": "tfidf"}


def pick_in_scope(pool: list[dict], registry: dict, method: str,
                  embed_url: str) -> tuple[list[dict], dict]:
    """For each target, the most similar pool API not already taken.

    Texts are "name: description", the form the narrowing ranks (bear.narrowing.tool_corpus),
    with the decoy's eventual name and the real tool's Hermes description.
    """
    desc = {t["name"]: t["description"] for t in registry["tools"]}
    missing = [t for t in IN_SCOPE_TARGETS if t not in desc]
    if missing:
        sys.exit(f"in-scope targets missing from the registry dump: {missing}")
    pool_texts = [f"{_name(p['tool_name'], p['api_name'])}: {p['description']}" for p in pool]
    target_texts = [f"{t}: {desc[t]}" for t in IN_SCOPE_TARGETS]
    sims, how = _similarities(pool_texts, target_texts, method, embed_url)
    taken: set[int] = set()
    picks = []
    for target, row in zip(IN_SCOPE_TARGETS, sims):
        best = min((-s, i) for i, s in enumerate(row) if i not in taken)
        taken.add(best[1])
        picks.append({**pool[best[1]], "near": target, "near_similarity": round(-best[0], 4)})
    return picks, how


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--toolbench", default=DEFAULT_TOOLBENCH)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--near", choices=("embed", "tfidf"), default="embed",
                    help="similarity for choosing in-scope decoys (default: the Nemotron embedder)")
    ap.add_argument("--embed-url", default="http://localhost:8360")
    a = ap.parse_args()
    if not os.path.isfile(a.toolbench):
        sys.exit(f"{a.toolbench} missing. Run evals/toolbench_setup.py --toolbench-only first.")
    raw = open(a.toolbench, "rb").read()
    registry = json.load(open(REGISTRY, encoding="utf-8"))
    real = set(registry["candidates"]) | {"tool_search", "tool_describe", "tool_call"}

    pool = load_pool(a.toolbench)
    in_scope, near_how = pick_in_scope(pool, registry, a.near, a.embed_url)
    picked = {(p["category"], p["tool_name"], p["api_name"]) for p in in_scope}
    rest = [p for p in pool if (p["category"], p["tool_name"], p["api_name"]) not in picked]
    rng = random.Random(a.seed)
    rng.shuffle(rest)
    out_scope = rest[:max(SIZES) - N_IN_SCOPE]

    names: set[str] = set(real)
    decoys = []
    for d, scope_tag in [(p, IN_SCOPE_TAG) for p in in_scope] + \
                        [(p, f"team:{p['category']}") for p in out_scope]:
        base = _name(d["tool_name"], d["api_name"])
        name, k = base, 2
        while name in names:
            name, k = f"{base}_{k}", k + 1
        names.add(name)
        decoys.append({"name": name, "scope_tag": scope_tag, "in_scope": scope_tag == IN_SCOPE_TAG,
                       **d})
    ins = [d for d in decoys if d["in_scope"]]
    outs = [d for d in decoys if not d["in_scope"]]
    sizes = {str(n): [d["name"] for d in ins + outs[:n - N_IN_SCOPE]] for n in SIZES}

    sample = {
        "seed": a.seed,
        "source": {"path": os.path.relpath(a.toolbench, REPO).replace(os.sep, "/"),
                   "sha256": hashlib.sha256(raw).hexdigest()},
        "filters": {"description_chars": [DESC_MIN, DESC_MAX], "max_params": MAX_PARAMS,
                    "param_description_max_chars": PARAM_DESC_MAX,
                    "reject": "control characters or escaped-backslash runs in any text"},
        "pool_size": len(pool),
        "in_scope_targets": list(IN_SCOPE_TARGETS),
        "in_scope_similarity": near_how,
        "registry_commit": registry.get("hermes_commit"),
        "in_scope_tag": IN_SCOPE_TAG,
        "toolset": TOOLSET,
        "error": "Service unavailable (HTTP 503): this API cannot be reached from this environment.",
        "sizes": sizes,
        "category_counts": {n: dict(Counter(d["scope_tag"] for d in decoys if d["name"] in set(v)))
                            for n, v in sizes.items()},
        "decoys": decoys,
    }
    with open(SAMPLE_OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sample, f, indent=1, ensure_ascii=False)
        f.write("\n")

    os.makedirs(CORPUS_OUT, exist_ok=True)
    by_name = {d["name"]: d for d in decoys}
    for n, members in sizes.items():
        rules = [{"id": f"decoy-{m}", "type": "tool", "priority": DECOY_PRIORITY, "content": m,
                  "actions": {"function": m},
                  "scope": {"required_tags": [by_name[m]["scope_tag"]]}} for m in members]
        header = (f"# WP7 decoy rules, size {n}. Generated by hermes/decoys/make_decoys.py "
                  f"(seed {a.seed}).\n"
                  "# One allow rule per decoy. In-scope decoys need team:ops, the rest need\n"
                  "# team:<RapidAPI category>. content is the tool's name only. The ranking reads\n"
                  "# the decoy's own (ToolBench) description, never this file.\n")
        with open(os.path.join(CORPUS_OUT, f"decoys-{n}.yaml"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(header)
            yaml.safe_dump({"instructions": rules}, f, sort_keys=False, allow_unicode=True,
                           width=100)
    print(f"pool {len(pool)}, in scope {len(ins)}, out of scope {len(outs)}")
    for d in ins:
        print(f"  in scope: {d['name']} (near {d['near']}, {d['near_similarity']}): "
              f"{d['description'][:90]}")
    for n, c in sample["category_counts"].items():
        print(f"  size {n}: {len(sizes[n])} decoys, {len(c)} scope tags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
