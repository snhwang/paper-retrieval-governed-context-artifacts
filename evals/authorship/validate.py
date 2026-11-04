#!/usr/bin/env python3
"""Authorship ablation, step 2: validate every call and count every failure and fallback.

    python evals/authorship/validate.py --tags-dir DIR [--out DIR/validation.json] [--max-missing-frac 0.01]

Reads the call log (calls.jsonl) and the five output files that tag.py wrote,
and applies the originals' own validation to every recorded reply:
- MetaTool tool and query tags: the reply's tool-call arguments go through the
  original generate_tool_tags / generate_query_tags post-processing
  (metatool_tagging.py), with the API call replaced by the recorded arguments.
  The outcome is the tag list, or the original's TaggingError (no valid tag,
  no domain tag). A reply without a tool call is the original's retry case.
- ToolBench categories: the reply text goes through the module's own
  normalization (infer_categories for top-1, _parse_multitag_response for the
  multi and top-5 sets), which maps an out-of-vocabulary answer to no tag.
Per item it counts the calls (retries), the final outcome, and how the item
ended in the output:
- MetaTool: a failed item is absent from the file (the originals' rule). An
  absent tool carries no required tags at evaluation, and an absent query is
  left out of the MetaTool+QueryTags-top5 set.
- ToolBench: an out-of-vocabulary answer becomes the empty tag (top-1) or is
  dropped from the set (multi, top-5). An empty set leaves the query ungated.
Nothing becomes an empty tag set without being counted here. The same
normalization runs over the Sonnet files, so both taggers are counted alike.

Exit code 1 when a target's absent or empty items exceed --max-missing-frac.
No network: the shim of authorship_regenerate.py refuses every request.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
REPO = EVALS.parent
for _p in (str(REPO), str(EVALS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import authorship_regenerate as ar  # noqa: E402


def read_calls(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def tool_args(rec: dict) -> dict | None:
    """The first tool call's arguments as a dict, or None when there is none or it is not JSON."""
    for c in rec.get("raw_tool_calls") or []:
        a = c.get("arguments")
        try:
            d = json.loads(a) if isinstance(a, str) else a
        except (TypeError, json.JSONDecodeError):
            return None
        return d if isinstance(d, dict) else None
    return None


def metatool_outcome(target: str, rec: dict, mt) -> tuple[str, list[str] | None, str]:
    """(outcome, tags, detail) of one recorded call, through the original post-processing."""
    if rec.get("shim_outcome") in ("http_error", "transport_error"):
        return "call_error", None, rec.get("error", "")
    args = tool_args(rec)
    if args is None:
        return "no_tool_call", None, "the original retries this call"
    orig = mt._anthropic_tool_call
    mt._anthropic_tool_call = lambda **kw: args
    try:
        if target == "tool_tags":
            tags = mt.generate_tool_tags(rec.get("item", ""), "", "replay", "replay")
        else:
            tags = mt.generate_query_tags(rec.get("item", ""), "replay", "replay", k=5)
        return "valid", tags, ""
    except mt.TaggingError as e:
        return "invalid", None, str(e)
    finally:
        mt._anthropic_tool_call = orig


class ToolBenchNormalizer:
    """The module's own normalization of a category reply, with its vocabulary."""

    def __init__(self, target: str) -> None:
        import importlib
        self.target = target
        self.mod = importlib.import_module(ar.TB_MODULES[target])
        queries, category_map = ar._load_tb_queries(None)
        self.queries = queries
        self.labels, self.label_to_tag = ar._tb_vocab(self.mod, queries, category_map)

    def __call__(self, raw: str) -> tuple[str, list[str], int]:
        raw = ar._THINK.sub("", raw or "", count=1)
        if self.target == "toolbench_top1":
            old = self.mod.CACHE_PATH
            self.mod.CACHE_PATH = Path(os.devnull)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    tags, _ = self.mod.infer_categories([("q", [], set())], self.labels, self.label_to_tag,
                                                        "anthropic", "none", "replay", None, {"q": raw})
            except IndexError:
                return "empty_reply", [], 1
            finally:
                self.mod.CACHE_PATH = old
            return ("valid", [tags[0]], 0) if tags[0] else ("out_of_vocabulary", [], 1)
        tags, n_oov = self.mod._parse_multitag_response(raw, self.label_to_tag)
        if not tags:
            return "empty_set", [], n_oov
        return ("partly_out_of_vocabulary" if n_oov else "valid"), tags, n_oov


def summarize_calls(target: str, calls: list[dict], outcome_of) -> tuple[dict, dict]:
    per_item: dict[str, list[tuple[str, str]]] = defaultdict(list)
    call_outcomes: Counter = Counter()
    shim: Counter = Counter()
    served: Counter = Counter()
    for rec in calls:
        if rec.get("target") != target:
            continue
        o = outcome_of(rec)
        call_outcomes[o] += 1
        shim[rec.get("shim_outcome", "?")] += 1
        if rec.get("served_model"):
            served[rec["served_model"]] += 1
        for k, v in (rec.get("translation_notes") or {}).items():
            shim[f"note:{k}"] += v
        per_item[rec.get("item", "")].append((rec.get("utc", ""), o))
    final = Counter(sorted(v)[-1][1] for v in per_item.values())
    retried = sum(1 for v in per_item.values() if len(v) > 1)
    return ({"calls": sum(call_outcomes.values()), "items_called": len(per_item), "items_retried": retried,
             "call_outcomes": dict(call_outcomes), "final_call_outcome_per_item": dict(final),
             "shim_outcomes": dict(shim), "served_models": dict(served)}, per_item)


def validate(tags_dir: Path) -> dict:
    import metatool_generate_query_tags_top5 as gq
    import metatool_generate_tags as gt
    import metatool_tagging as mt
    calls = read_calls(tags_dir / "calls.jsonl")
    report: dict = {"tags_dir": str(tags_dir), "n_call_records": len(calls), "targets": {}}

    # MetaTool tool tags
    tools = gt.load_tools()
    out = tags_dir / ar.OUT_NAMES["tool_tags"]
    got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    sonnet = json.loads(ar.SONNET_FILES["tool_tags"].read_text(encoding="utf-8"))
    s, _ = summarize_calls("tool_tags", calls, lambda r: metatool_outcome("tool_tags", r, mt)[0])
    names = [t["name"] for t in tools]
    s.update(items_expected=len(names), items_in_output=sum(1 for n in names if n in got),
             items_absent=[n for n in names if n not in got],
             items_with_no_tag=[n for n in names if n in got and not got[n]],
             out_of_vocabulary_tags=sum(1 for n in got for t in got[n] if t not in mt.DOMAIN_NAMES),
             sonnet={"items": len(sonnet), "absent": sum(1 for n in names if n not in sonnet),
                     "out_of_vocabulary_tags": sum(1 for n in sonnet for t in sonnet[n] if t not in mt.DOMAIN_NAMES)})
    s["fallback"] = "an absent tool carries no required tags at evaluation (eval_toolbench.load_metatool_corpus_tagged)"
    report["targets"]["tool_tags"] = s

    # MetaTool top-5 query tags
    queries = gq.load_queries()
    out = tags_dir / ar.OUT_NAMES["query_tags_top5"]
    got_q = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    sonnet_q = json.loads(ar.SONNET_FILES["query_tags_top5"].read_text(encoding="utf-8"))
    s, _ = summarize_calls("query_tags_top5", calls, lambda r: metatool_outcome("query_tags_top5", r, mt)[0])

    def key(e):
        return (e["query"].strip(), tuple(sorted(e.get("tools", []))))
    want = Counter(key(q) for q in queries)
    have = Counter(key(e) for e in got_q)
    absent = sum(max(0, n - have.get(k, 0)) for k, n in want.items())
    s.update(items_expected=sum(want.values()), items_in_output=len(got_q), items_absent=absent,
             items_with_no_domain_tag=sum(1 for e in got_q if not any(t in mt.DOMAIN_NAMES for t in e["context_tags"])),
             out_of_vocabulary_tags=sum(1 for e in got_q for t in e["context_tags"] if t not in mt.QUERY_VOCAB),
             sonnet={"items": len(sonnet_q),
                     "absent": sum(max(0, n - Counter(key(e) for e in sonnet_q).get(k, 0)) for k, n in want.items())})
    s["fallback"] = "an absent query is left out of the MetaTool+QueryTags-top5 set (load_metatool_queries_from_query_tags)"
    report["targets"]["query_tags_top5"] = s

    # ToolBench categories
    for target in ar.TB_MODULES:
        norm = ToolBenchNormalizer(target)
        out = tags_dir / ar.OUT_NAMES[target]
        cache = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        sonnet_c = json.loads(ar.SONNET_FILES[target].read_text(encoding="utf-8"))
        s, _ = summarize_calls(target, calls, lambda r: (norm(r.get("raw_content") or "")[0]
                                                         if r.get("shim_outcome") not in ("http_error", "transport_error")
                                                         else "call_error"))
        texts = list(dict.fromkeys(q[0] for q in norm.queries))

        def final(c):
            res = Counter()
            for t in texts:
                if t not in c:
                    res["absent"] += 1
                    continue
                o, tags, n_oov = norm(c[t])
                res[o] += 1
                res["oov_labels"] += n_oov
            return dict(res)
        fin = final(cache)
        s.update(items_expected=len(texts), items_in_output=sum(1 for t in texts if t in cache),
                 final_normalized=fin, sonnet_final_normalized=final(sonnet_c),
                 fallback=("out of vocabulary becomes the empty tag, so the query is not gated"
                           if target == "toolbench_top1" else
                           "out-of-vocabulary labels are dropped from the set, an empty set leaves the query ungated"))
        report["targets"][target] = s
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--max-missing-frac", type=float, default=0.01)
    a = ap.parse_args(argv)
    with ar.AnthropicToOpenAIShim(ar.DEFAULT_BASE_URL, transport=ar.deny_all):
        rep = validate(a.tags_dir)
    bad = []
    for t, s in rep["targets"].items():
        n = s["items_expected"] or 1
        if t in ("tool_tags", "query_tags_top5"):
            lost = (len(s["items_absent"]) if isinstance(s["items_absent"], list) else s["items_absent"])
            lost += len(s.get("items_with_no_tag", [])) + s.get("items_with_no_domain_tag", 0)
        else:
            f = s["final_normalized"]
            lost = f.get("absent", 0) + f.get("empty_reply", 0)
        s["lost_fraction"] = lost / n
        print(f"{t}: expected {s['items_expected']}, in output {s['items_in_output']}, calls {s['calls']}, "
              f"retried items {s['items_retried']}, lost {lost} ({lost / n:.2%})")
        if lost / n > a.max_missing_frac:
            bad.append(t)
    rep["max_missing_frac"] = a.max_missing_frac
    rep["over_the_limit"] = bad
    out = a.out or (a.tags_dir / "validation.json")
    out.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"written: {out}")
    if bad:
        print(f"FAILED: validate: lost items above {a.max_missing_frac:.0%} in {' '.join(bad)}")
        return 1
    print("OK: validate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
