#!/usr/bin/env python3
"""Query giveaways: queries that name their own answer (WP6).

Governance can do little work on a query that names the tool it needs, since
plain similarity (lexical above all) already finds it. This script finds
those queries without a model and re-reports governed and ungated Recall@5
stratified by them, rather than excluding them. The approach follows the
model-free item-defect checks of paper-knowledge-flow's ``to_check.py``:
precise, anchored matching that flags rather than filters, and rules
chosen to avoid coincidences rather than tuned to a tolerance.

Identifier map
--------------
Every identifier is mapped to the set of tools whose documentation contains
it, and only identifiers that point to exactly one tool are kept. A "tool"
is a RapidAPI tool on ToolBench (several endpoints share one) and a plugin
on MetaTool. Four kinds:

  tool_name   the tool's name (ToolBench tool_name, MetaTool name_for_model
              and name_for_human)
  endpoint    a ToolBench endpoint (api_name)
  parameter   a ToolBench parameter name
  term        a word that occurs in exactly one tool's documentation (names,
              descriptions, parameter names and descriptions)

Text is lower-cased, camelCase and snake_case are split, and everything is
tokenized on [a-z0-9]+. A multi-word identifier matches a contiguous run of
query tokens, a one-word identifier a whole token, so "imdb" never matches
inside "imdbpro". To keep ordinary words from counting as identifiers, every
identifier must contain at least one distinctive token: three or more
characters, not purely numeric, and not a whole word in the 30,522-entry
BERT uncased vocabulary that BGE-base uses (the "common-word lexicon").
"SMTP", "ASIN" and brand names absent from that vocabulary qualify;
"weather" or "pokemon", which the vocabulary contains, do not on their own.
The lenient variant drops that rule for tool names, for a sensitivity row.

A query is a giveaway when it contains an identifier of one of its own
ground-truth tools. Two tiers are reported: names only (tool, endpoint,
parameter) and names or terms. Before the lexicon check a token is also
tried with simple suffixes stripped, so "renting" counts as the common word
"rent". A query that contains only identifiers of other tools
is counted separately ("names another tool").

Results
-------
Recall@5 per stratum for the ungated arm, the gate-only governed arm and
the published governed configuration, read from the per-query arrays of
eval_tag_noise.py (rate 0) so both scripts score the same retrievals. The
governance effect (governed minus ungated) is reported per stratum with a
paired bootstrap CI, and the difference of effects between strata with a
bootstrap over queries.

Usage (after eval_tag_noise.py has written results/tag_noise.json):
    python evals/eval_query_giveaways.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tistr2_common import (  # noqa: E402
    BACKEND_LABEL, REPO_ROOT, Tee, bear_provenance, ci_summary, json_default,
    paired_summary, refuse_overwrite,
)
from repro_footer import print_repro_footer  # noqa: E402

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_TOK = re.compile(r"[a-z0-9]+")
KINDS = ("tool_name", "endpoint", "parameter", "term")


def tokens(text: str) -> list[str]:
    text = _CAMEL.sub(" ", text or "")
    return _TOK.findall(text.replace("_", " ").lower())


def common_lexicon() -> set[str]:
    pat = os.path.expanduser(
        "~/.cache/huggingface/hub/models--BAAI--bge-base-en-v1.5/snapshots/*/vocab.txt")
    hits = glob.glob(pat)
    if not hits:
        raise SystemExit(f"BERT vocabulary not found at {pat}")
    words = Path(hits[0]).read_text(encoding="utf-8").split("\n")
    return {w for w in words if w.isalpha() and not w.startswith("[")}


def _variants(t: str) -> set[str]:
    """The token and simple suffix-stripped forms, so "renting" meets "rent"."""
    v = {t}
    if t.endswith("ies") and len(t) > 4:
        v.add(t[:-3] + "y")
    if t.endswith("es") and len(t) > 3:
        v.add(t[:-2])
    if t.endswith("s") and len(t) > 3:
        v.add(t[:-1])
    for suf in ("ing", "ings", "ed", "er", "ers", "ly", "ment", "ments", "ness",
                "ation", "ations", "ion", "ions", "able", "al"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            base = t[:-len(suf)]
            v.update({base, base + "e"})
            if len(base) > 2 and base[-1] == base[-2]:
                v.add(base[:-1])
    return v


def distinctive(tok: str, lex: set[str]) -> bool:
    """Three or more characters, not a number, and no simple form of it is a common word."""
    return len(tok) >= 3 and not tok.isdigit() and not (_variants(tok) & lex)


# ---------------------------------------------------------------------------
# Tool documentation
# ---------------------------------------------------------------------------

def toolbench_docs():
    """tool -> {"names": [...], "endpoints": [...], "params": [...], "text": str}, query rows."""
    from eval_toolbench import TOOLBENCH_DIR, load_toolbench_corpus_and_queries
    data = json.loads((TOOLBENCH_DIR / "benchmark_data.json").read_text())
    docs: dict[str, dict] = defaultdict(lambda: {"names": set(), "endpoints": set(),
                                                 "params": set(), "text": []})
    for split in data:
        for row in data[split]:
            al = row.get("api_list", "[]")
            al = json.loads(al) if isinstance(al, str) else al
            for api in al:
                if not isinstance(api, dict):
                    continue
                tool = api.get("tool_name", "")
                d = docs[tool]
                d["names"].add(tool)
                d["endpoints"].add(api.get("api_name", ""))
                d["text"].append(tool)
                d["text"].append(api.get("api_name", ""))
                d["text"].append(api.get("api_description", "") or "")
                for p in (api.get("required_parameters") or []) + (api.get("optional_parameters") or []):
                    if isinstance(p, dict):
                        d["params"].add(p.get("name", ""))
                        d["text"].append(p.get("name", ""))
                        d["text"].append(p.get("description", "") or "")
    corpus, queries, _ = load_toolbench_corpus_and_queries()
    tool_of = {i.id: i.metadata.get("tool_name", "") for i in corpus}
    rows = []
    for q in queries:
        gt_tools = {tool_of[e] for e in q[2]}
        rows.append({"query": q[0], "gt_tools": gt_tools})
    return docs, rows


def metatool_docs():
    from eval_toolbench import METATOOL_DIR, load_metatool_queries_tagged
    des = json.loads((METATOOL_DIR / "plugin_des.json").read_text())
    info = {e.get("name_for_model", ""): e
            for e in json.loads((METATOOL_DIR / "plugin_info.json").read_text())}
    docs: dict[str, dict] = {}
    for name, short in des.items():
        i = info.get(name, {})
        names = {name}
        if i.get("name_for_human"):
            names.add(i["name_for_human"])
        docs[name] = {"names": names, "endpoints": set(), "params": set(),
                      "text": [name, i.get("name_for_human", ""), short or "",
                               i.get("description_for_human", "") or "",
                               i.get("description_for_model", "") or ""]}
    rows = [{"query": q, "gt_tools": {t.replace("metatool/", "") for t in e}}
            for q, _t, e in load_metatool_queries_tagged(METATOOL_DIR / "plugin_tags.json")]
    return docs, rows


def build_map(docs: dict, lex: set[str], lenient_names: bool = False) -> dict:
    """identifier (token tuple) -> (tool, kind), for identifiers unique to one tool."""
    owners: dict[tuple, set] = defaultdict(set)
    kinds: dict[tuple, set] = defaultdict(set)
    term_df: Counter = Counter()
    for tool, d in docs.items():
        for kind, field in (("tool_name", "names"), ("endpoint", "endpoints"), ("parameter", "params")):
            for raw in d[field]:
                t = tuple(tokens(raw))
                if t:
                    owners[t].add(tool)
                    kinds[t].add(kind)
        for tok in set(tokens(" ".join(d["text"]))):
            term_df[tok] += 1
            owners[(tok,)].add(tool)
            kinds[(tok,)].add("term")
    out = {}
    for ident, tools in owners.items():
        if len(tools) != 1:
            continue
        ks = kinds[ident]
        if len(ident) == 1 and "term" in ks and term_df[ident[0]] != 1:
            ks = ks - {"term"}
        if not ks:
            continue
        ok = any(distinctive(t, lex) for t in ident)
        if not ok and not (lenient_names and "tool_name" in ks):
            continue
        kind = next(k for k in KINDS if k in ks)
        out[ident] = (next(iter(tools)), kind)
    return out


def find(query: str, imap: dict, max_len: int) -> list[tuple[tuple, str, str]]:
    toks = tokens(query)
    hits = []
    for n in range(1, max_len + 1):
        for i in range(len(toks) - n + 1):
            ident = tuple(toks[i:i + n])
            if ident in imap:
                tool, kind = imap[ident]
                hits.append((ident, tool, kind))
    return hits


def classify(rows: list[dict], imap: dict) -> list[dict]:
    max_len = max((len(k) for k in imap), default=1)
    out = []
    for r in rows:
        hits = find(r["query"], imap, max_len)
        own = [h for h in hits if h[1] in r["gt_tools"]]
        other = [h for h in hits if h[1] not in r["gt_tools"]]
        own_names = [h for h in own if h[2] != "term"]
        out.append({"giveaway": bool(own), "giveaway_names": bool(own_names),
                    "own_kinds": sorted({h[2] for h in own}),
                    "own": [(" ".join(h[0]), h[1], h[2]) for h in own][:5],
                    "names_other_only": bool(other) and not own,
                    "other": [(" ".join(h[0]), h[1], h[2]) for h in other][:5]})
    return out


# ---------------------------------------------------------------------------
# Stratified results
# ---------------------------------------------------------------------------

def diff_of_effects(g1, u1, g0, u0, n_boot=10_000, seed=42) -> dict:
    """Bootstrap the difference of governance effects between two independent strata.

    Each stratum's mean effect is bootstrapped on its own (multinomial over
    distinct per-query differences, as in tistr2_common), then differenced.
    """
    from tistr2_common import multinomial_boot_means
    d1, d0 = np.asarray(g1) - np.asarray(u1), np.asarray(g0) - np.asarray(u0)
    if len(d1) == 0 or len(d0) == 0:
        return {"delta": None, "ci": [None, None], "p_bootstrap": None}
    b1 = multinomial_boot_means(d1, n_boot, seed)
    b0 = multinomial_boot_means(d0, n_boot, seed + 1)
    diff = b1 - b0
    p = 2 * min((diff <= 0).mean(), (diff >= 0).mean())
    return {"delta": float(d1.mean() - d0.mean()),
            "ci": [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))],
            "p_bootstrap": float(max(p, 1 / n_boot))}


def stratify(flags: list[dict], arrays: dict[str, np.ndarray]) -> dict:
    give = np.array([f["giveaway"] for f in flags])
    give_n = np.array([f["giveaway_names"] for f in flags])
    other = np.array([f["names_other_only"] for f in flags])
    strata = {"giveaway": give, "no_giveaway": ~give, "giveaway_names": give_n,
              "no_giveaway_names": ~give_n, "names_other_only": other,
              "all": np.ones_like(give)}
    out = {}
    for name, m in strata.items():
        if not m.any():
            out[name] = {"n": 0}
            continue
        e = {"n": int(m.sum())}
        for arm, a in arrays.items():
            e[arm] = ci_summary(a[m])
        for arm in ("gate_clean", "paper_governed"):
            if arm in arrays:
                e[f"{arm}_minus_ungated"] = paired_summary(arrays[arm][m], arrays["ungated"][m])
        out[name] = e
    for arm in ("gate_clean", "paper_governed"):
        for tag, m in (("", give), ("_names", give_n)):
            if arm in arrays and m.any() and (~m).any():
                out[f"effect_difference{tag}_{arm}"] = diff_of_effects(
                    arrays[arm][m], arrays["ungated"][m],
                    arrays[arm][~m], arrays["ungated"][~m])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag-noise", type=Path, nargs="+",
                    default=[REPO_ROOT / "results" / "tag_noise.json",
                             REPO_ROOT / "results" / "tag_noise_nemotron.json",
                             REPO_ROOT / "results" / "tag_noise_qwen3.json"],
                    help="eval_tag_noise.py outputs; their backends are merged.")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "query_giveaways.json")
    ap.add_argument("--log-file", type=Path,
                    default=REPO_ROOT / "results" / "query_giveaways_output.txt")
    args = ap.parse_args()
    refuse_overwrite(args.output, args.log_file)
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        lex = common_lexicon()
        noise = None
        for path in args.tag_noise:
            if not path.exists():
                print(f"(no {path})")
                continue
            part = json.loads(path.read_text())
            if noise is None:
                noise = part
                continue
            for bn, per_b in part["summary"].items():
                if part["benchmarks"][bn]["query_sha256"] != noise["benchmarks"][bn]["query_sha256"]:
                    raise SystemExit(f"{path}: {bn} query order differs")
                noise["summary"].setdefault(bn, {}).update(per_b)
        print("=== Query giveaways (WP6): identifiers that point to exactly one tool ===")
        print(f"Common-word lexicon: {len(lex)} whole words (BERT uncased vocabulary).")
        out: dict = {"provenance": bear_provenance(), "benchmarks": {}}
        for bn, loader in (("toolbench", toolbench_docs), ("metatool_tags", metatool_docs)):
            docs, rows = loader()
            imap = build_map(docs, lex)
            imap_len = build_map(docs, lex, lenient_names=True)
            flags = classify(rows, imap)
            flags_len = classify(rows, imap_len)
            n = len(rows)
            n_give = sum(f["giveaway"] for f in flags)
            by_kind = Counter(k for f in flags for k in f["own_kinds"])
            id_kinds = Counter(k for _t, k in imap.values())
            print(f"\n{bn}: {len(docs)} tools, {len(imap)} unique identifiers "
                  f"({dict(id_kinds)}), {n} queries")
            n_give_names = sum(f["giveaway_names"] for f in flags)
            print(f"  giveaway queries, names only (tool, endpoint, parameter): {n_give_names} "
                  f"({n_give_names / n:.3f})")
            print(f"  giveaway queries, names or terms: {n_give} ({n_give / n:.3f}); by kind "
                  f"{dict(by_kind)}; lenient tool names {sum(f['giveaway'] for f in flags_len)}")
            print(f"  queries naming only another tool: {sum(f['names_other_only'] for f in flags)}")
            ex = [(r["query"][:90], f["own"][:2]) for r, f in zip(rows, flags) if f["giveaway"]][:6]
            for q, h in ex:
                print(f"    e.g. {q!r} -> {h}")
            entry = {"n_tools": len(docs), "n_queries": n, "n_identifiers": len(imap),
                     "identifiers_by_kind": dict(id_kinds), "n_giveaway": n_give,
                     "giveaway_share": n_give / n, "giveaway_by_kind": dict(by_kind),
                     "n_giveaway_names": n_give_names, "giveaway_names_share": n_give_names / n,
                     "n_giveaway_lenient_names": sum(f["giveaway"] for f in flags_len),
                     "n_names_other_only": sum(f["names_other_only"] for f in flags),
                     "flags": flags, "backends": {}}
            if noise and bn in noise.get("summary", {}):
                from eval_tag_noise import load_bench, query_sha
                bench = load_bench(bn)
                if noise["benchmarks"][bn]["query_sha256"] != query_sha(bench) or len(bench.queries) != n:
                    raise SystemExit(f"{bn}: query order differs from the tag-noise results")
                if [q[0] for q in bench.queries] != [r["query"] for r in rows]:
                    raise SystemExit(f"{bn}: query texts differ between loaders")
                for b, e in noise["summary"][bn].items():
                    arrays = {"ungated": np.asarray(e["ungated"]["per_query_recall"], float),
                              "gate_clean": np.asarray(e["gate_clean"]["per_query_recall"], float),
                              "paper_governed": np.asarray(e["paper_governed"]["per_query_recall"], float)}
                    st = stratify(flags, arrays)
                    entry["backends"][b] = st
                    g, ng = st["giveaway"], st["no_giveaway"]
                    if g["n"] and ng["n"]:
                        print(f"  {BACKEND_LABEL[b]:<18} giveaway (n={g['n']}): ungated "
                              f"{g['ungated']['mean']:.3f} gate {g['gate_clean']['mean']:.3f} "
                              f"published {g['paper_governed']['mean']:.3f} | no giveaway "
                              f"(n={ng['n']}): ungated {ng['ungated']['mean']:.3f} gate "
                              f"{ng['gate_clean']['mean']:.3f} published "
                              f"{ng['paper_governed']['mean']:.3f} | effect diff (gate) "
                              f"{st['effect_difference_gate_clean']['delta']:+.3f} "
                              f"[{st['effect_difference_gate_clean']['ci'][0]:+.3f}, "
                              f"{st['effect_difference_gate_clean']['ci'][1]:+.3f}]")
            out["benchmarks"][bn] = entry
        args.output.write_text(json.dumps(out, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "query_giveaways", **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
