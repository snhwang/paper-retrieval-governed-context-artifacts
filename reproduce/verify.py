#!/usr/bin/env python3
"""Compare your reproduced outputs with the committed ones, file by file.

    python reproduce/verify.py [--repro DIR] [--committed DIR] [--out DIR] [--only GLOB ...] [--strict]

--repro      the repo-shaped tree of your outputs (default $REPRO_OUT/assembled,
             made by 70_assemble.sh)
--committed  this checkout (default: the repo that holds this script)
--out        verify.md and verify.json go here (default $REPRO_OUT/verify)
--only       compare only paths matching these globs
--strict     a required file you have not produced yet counts as a failure

Every file in --repro is compared with the file of the same path in --committed
(a .gz on either side is read through). Then every file the manuscript needs
(reproduce/lib/paper_map.py, items that need Scott's run) that --repro lacks is
listed as NOT RUN. The table prints one line per file:
  PASS     within the tolerance of its class
  FAIL     outside it (the detail says where)
  INFO     compared, but the class decides nothing (listed for reading)
  NEW      no committed counterpart
  SKIP     not compared (logs, manifests, hand-written reports)
  NOT RUN  required, and not in --repro

The tolerance rules are all in TOLERANCE below, and README.md states them.
Exit code 0 unless a file FAILs (or, with --strict, a required file is NOT RUN).
Needs only the standard library (and numpy for .npz files).
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import gzip
import io
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import paper_map as pm  # noqa: E402

# ---------------------------------------------------------------------------
# TOLERANCE: every rule of the comparison, in one place.
# ---------------------------------------------------------------------------
TOLERANCE = {
    # Deterministic CPU results (BM25, hash, BGE, BGE-M3, Qwen3-0.6B and Qwen3-4B on
    # the CPU, invariants, budget binding, WP5 with BGE): every number equal. Floats
    # compare with a relative and absolute slack of 1e-9, which only absorbs JSON
    # float printing. Strings equal.
    "exact": {"rel": 1e-9, "abs": 1e-9},
    # Hash-backend results inside the exact class (a file or JSON key named for hash).
    # BEAR 0.4.2's _hash_embed sums shingle vectors in float32 in the order of a Python
    # set, which follows PYTHONHASHSEED, so each process rounds the vectors differently in
    # the last bit (about 3e-8 in similarity). Decisions and counts must still be equal:
    # integers compare exactly, and floats agree within 1e-6. That absorbs the rounding,
    # while one changed decision moves a rate or mean over these sets (at most about 10^5
    # items) by 1e-5 or more. Strings compare exactly. Rule from the revision plan,
    # 17 Nov 2026.
    # The evals save hash vectors in the embedding store, so one store keeps the rounding
    # of the process that built it. The committed runs shared one store and your run
    # builds another, so your hash similarities differ from the committed ones (by up to
    # 3e-7 in the kit's first run), and they are the same on every rerun over your store.
    # One exception to "integers compare exactly" (Scott, 19 Nov 2026): the bm25 check
    # (bm25_v042_check_*) counts the hash pairs whose similarity moved by more than 1e-9
    # against an earlier run, hashes the pairs with their similarities into a digest and
    # lists example pairs. All three follow the similarity values, so they read as
    # similarity values: a different count or digest is noted, and each example must show
    # the same decision on both sides and similarities within 1e-6. The presence counts
    # beside them stay exact, and so do the BM25 rows (sim_record, mask_sim).
    "hash": {"abs": 1e-6},
    # Local GPU results (Qwen3-4B bf16 in WP0, Qwen3 fp16 in WP6) and results that
    # embed through the GPU-served Nemotron model: precision, batch size and server
    # batching move values at rounding level. Every point estimate the committed
    # file gives a 95% CI for must lie inside that CI. A float without a CI must
    # agree to 3 decimals (|diff| < 0.0005). Integers and per-query arrays are
    # reported but decide nothing.
    # The kit runs every Qwen3-4B encode at batch 2. The committed rehearsal ran the
    # +Tags and +QueryTags rows (tb_qwen4b, wp4 MetaTool+Tags lists) at batch 8, so
    # those differ at rounding level, which this rule allows.
    "gpu": {"ci_slack": 1e-9, "abs_no_ci": 5e-4},
    # The Ollama executor (Table 10 rerun, the July runs if 55_ reran them): the
    # measured drift of the executor on identical lists is at most 0.0082 in
    # accuracy, so tool and exact accuracy (and governed minus ungated deltas) must
    # agree within 0.01. Retrieval metrics of the lists, which do not depend on the
    # executor, must be exact. Per-query outcomes are reported but decide nothing.
    "ollama": {"abs_acc": 0.01, "acc_keys": ("tool_accuracy", "exact_accuracy", "tool", "exact", "delta")},
    # Sampled LLM runs (Gemma 4 at temperature 1.0 in Supplement Table S1, the Hermes grids):
    # every point estimate with a committed CI must lie inside it. Other numbers
    # decide nothing. The committed Hermes results are agent runs on an older
    # harness, which your runs replace, so expect some FAILs there and read them.
    "llm": {"ci_slack": 1e-9},
    # Tag files written by an LLM (the authorship ablation): a rerun at temperature 0
    # with a fixed seed on the same server should repeat nearly every item, but
    # server batching can move a few. Pass if at least 99% of the committed items
    # are present and at least 90% of the shared items carry the identical tag set.
    "tags": {"min_coverage": 0.99, "min_item_agreement": 0.90},
    # Compared for reading only.
    "info": {},
    # Not compared.
    "skip": {},
}

# Path rules, first match wins. Paths are relative to the repo root.
GPU_STEP = r"(tb_qwen4b|e2e_q4b|wp4_.*q4b|tb_nemotron|e2e_nemotron|wp4_.*nemotron|diag_nemotron)"
CLASS_RULES: list[tuple[str, str, str]] = [
    (r"(^|/)[^/]+\.log$", "skip", "log (timestamps, paths)"),
    (r"(^|/)MANIFEST\.json$", "skip", "manifest of the assembly"),
    (r"(^|/)IDENTICAL_TO_COMMITTED\.txt$", "skip", "list made during the run"),
    (r"(^|/)vram\.jsonl$", "skip", "memory record"),
    (r"^results/v042/report/", "skip", "hand-written report"),
    (r"(^|/)run_provenance\.json$", "skip", "provenance record"),
    (r"\.provenance\.json$", "skip", "provenance record"),
    (r"^figures/", "skip", "PDF (80_figures.sh compares the text)"),
    (r"^results/v042/diag/(probe_q4b|verify_v042|wp4_final|alpha_hash)", "skip", "diagnostic record"),
    (r"^results/authorship/tags/(plugin_tags|query_tags_top5|toolbench_\w+_categories)\.json$", "tags",
     "LLM-written tags (authorship ablation)"),
    (r"^results/authorship/tags/(calls\.jsonl|manifest\.json)$", "info", "call log and run manifest"),
    (r"^results/authorship/", "llm", "authorship ablation (depends on sampled tags)"),
    (r"^results/v042/(v042|v0110)/tb_auth_", "llm", "retrieval with LLM-written tags (authorship ablation)"),
    (r"^results/v042/e2e_rerun/", "ollama", "Ollama executor"),
    (r"^evals/results/toolbench_e2e", "ollama", "Ollama executor (July)"),
    (r"^results/toolbench_react_metrics", "llm", "sampled LLM (July and August)"),
    (r"^hermes/results/", "llm", "Hermes grid (agent runs committed)"),
    (r"^results/v042/compare/", "info", "comparison with the published 0.1.10 values"),
    (r"^results/v042/lists/.*(qwen3[-_]4b|nemotron)", "info", "GPU-made lists (their metrics are checked in the eval files)"),
    (rf"^results/v042/(v042|v0110|v042L|v0110F)/{GPU_STEP}", "gpu", "local GPU or Nemotron"),
    (r"^results/v042/diag/diag_nemotron", "gpu", "Nemotron"),
    (r"^results/v042/wp4/.*(qwen3-4b|nemotron)", "gpu", "GPU-made lists"),
    (r"^results/v042/wp4/(wp4_token_efficiency\.json|summary\.md)$", "gpu", "WP4 over all backends, Qwen3-4B and Nemotron included"),
    (r"^results/v042/mandatory/", "exact", "CPU"),
    (r"^results/[^/]*(qwen3-0\.6b|qwen|nemotron)[^/]*$", "gpu", "Qwen fp16 or Nemotron vectors"),
    (r"^results/(leakage_threat_v042|mandatory_coverage_v042|query_giveaways_v042|tag_noise_overrestriction_v042)",
     "gpu", "mixes Nemotron with CPU backends"),
    (r".*", "exact", "deterministic CPU"),
]

# Keys that hold run facts, not results: never compared.
SKIP_KEY = re.compile(r"^_|(^|_)(provenance|elapsed|seconds|s|latency|ms|time|times|timing|utc|date|wall|duration|"
                      r"host|hostname|user|path|paths|dir|argv|cwd|pid|vram|peak|fills|embedded|written|timestamp|"
                      r"versions|hooks|environment|server|load|request|file)(_|$)", re.I)
MASK_LINE = re.compile(r"(\d{4}-\d\d-\d\d[T ]\d\d:\d\d|elapsed|seconds|\bms\b|took|wall|/home/|/mnt/|"
                       r"[A-Z]:\\\\|provenance|bear_source_sha|python \d|written)", re.I)
# Text lines that state facts of the run, not results: the checkout's commit and status.
RUN_FACT_LINE = re.compile(r"^\s*git (commit|status):", re.I)
# Durations inside result lines ("25/314 tasks, 41s", "[toolbench: 68.1s]", "Ran in 610.9s.").
DURATION = re.compile(r"\b\d+(\.\d+)?\s?(s|min)\b")
# BEAR 0.4.2 under its two names: the candidate sha 9d085b4 that evals/run_wp256.sh puts in
# BEAR_SOURCE_SHA, and the v0.4.2 tag 0d0718a that the kit installs. The code is the same
# (README.md, Known gaps). A string compares with both read as one label.
BEAR_042 = re.compile(r"\b(9d085b4[0-9a-f]{0,33}|0d0718a[0-9a-f]{0,33})\b")
# Hash-backend scope for TOLERANCE["hash"]: a file named for hash, or a JSON path through a
# key named for it (backends/hash, hash:flat_backfill, bear_hash_gov.json).
HASH_NAME = re.compile(r"(^|[/_:\-\[.])hash([/_:\-\].]|$)", re.I)
# The bm25 check's files, whose hash rows count similarity changes (TOLERANCE["hash"]).
SIM_COUNT_FILE = re.compile(r"(^|[/\\])bm25_v\d+_check")
# Their text lines for the hash backend ("  hash: A_on 136/738 (0), ..." and
# "  hash/A_on  present 0.4.0 738/738  default: 136 (0) | ..."), and on those lines the count
# of pairs that differ: the integer before "/738 (0)" or before " (0)". The number in
# parentheses is the count of presence changes, which stays compared.
SIM_COUNT_LINE = re.compile(r"^\s*hash[:/]")
SIM_COUNT = re.compile(r"(?<![/\d.])\b\d+(?=(/\d+)? \(\d+\))")
# A key that is an absolute path to a result file. It compares from the folder that holds
# results/ on, since the committed run and yours ran in different folders.
PATH_KEY = re.compile(r"^(?:[A-Za-z]:)?[/\\].*?([^/\\]+[/\\]results[/\\].+)$")


def classify(rel: str) -> tuple[str, str]:
    for rx, cls, why in CLASS_RULES:
        if re.search(rx, rel):
            return cls, why
    return "exact", "default"


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def open_any(p: Path, mode: str = "rt"):
    if p.suffix == ".gz":
        return gzip.open(p, mode, encoding="utf-8" if "t" in mode else None)
    return open(p, mode, encoding="utf-8", errors="replace") if "t" in mode else open(p, mode)


def strip_gz(rel: str) -> str:
    return rel[:-3] if rel.endswith(".gz") else rel


def find(base: Path, rel: str) -> Path | None:
    for c in (base / rel, base / (rel + ".gz"), base / strip_gz(rel)):
        if c.exists() and c.is_file():
            return c
    return None


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def is_ci_node(o) -> tuple[float, float, float] | None:
    """(point, lo, hi) if o is a value with a 95% CI, in any of the layouts the eval scripts write."""
    if not isinstance(o, dict):
        return None
    for pt, lo, hi in (("point_estimate", "ci_lower", "ci_upper"), ("mean", "ci_lower", "ci_upper"),
                       ("pt", "lo", "hi"), ("value", "lo", "hi"), ("mean", "lo", "hi")):
        if pt in o and lo in o and hi in o and all(is_num(o[k]) for k in (pt, lo, hi)):
            return float(o[pt]), float(o[lo]), float(o[hi])
    for pt in ("mean", "value", "point", "estimate", "delta"):
        if pt in o and is_num(o[pt]):
            for ck in ("ci", "ci95", "ci_95"):
                c = o.get(ck)
                if isinstance(c, (list, tuple)) and len(c) == 2 and all(is_num(x) for x in c):
                    return float(o[pt]), float(c[0]), float(c[1])
    return None


class Diff:
    def __init__(self):
        self.fail: list[str] = []
        self.info: list[str] = []
        self.n = 0
        self.hash_file = False  # the file holds hash-backend results only (TOLERANCE["hash"])
        self.sim_counts = False  # a bm25 check file: hash similarity counts read as similarities

    def bad(self, msg: str):
        if len(self.fail) < 200:
            self.fail.append(msg)

    def note(self, msg: str):
        if len(self.info) < 200:
            self.info.append(msg)


def close(a: float, b: float, rel: float, ab: float) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= max(ab, rel * max(abs(a), abs(b)))


def same_num(c, r, hashy: bool) -> bool:
    """The exact rule, or TOLERANCE["hash"] for a float in hash scope."""
    if hashy and (isinstance(c, float) or isinstance(r, float)):
        return close(float(c), float(r), 0, TOLERANCE["hash"]["abs"])
    t = TOLERANCE["exact"]
    return close(float(c), float(r), t["rel"], t["abs"])


def canon(s: str) -> str:
    """s with BEAR 0.4.2's two shas read as one label."""
    return BEAR_042.sub("<BEAR 0.4.2>", s)


def by_spec(x) -> list | None:
    """x sorted by spec, if x is a list of task records that each carry a distinct "spec".
    Such lists are written in the order parallel workers finish (tag_noise per_task), so
    position means nothing."""
    if not (isinstance(x, list) and x and all(isinstance(e, dict) and "spec" in e for e in x)):
        return None
    keys = [json.dumps(e["spec"], sort_keys=True) for e in x]
    if len(set(keys)) != len(keys):
        return None
    return [e for _, e in sorted(zip(keys, x), key=lambda t: t[0])]


def path_keys(o: dict) -> dict:
    """o with absolute-path keys cut to <folder>/results/..., if every key stays distinct."""
    out = {}
    for k, v in o.items():
        m = PATH_KEY.match(k) if isinstance(k, str) else None
        out[m.group(1).replace("\\", "/") if m else k] = v
    return out if len(out) == len(o) else o


def sibling_cis(c: dict, r: dict, path: str, cls: str, d: Diff) -> set:
    """The CI rule for a value x (or x_mean) written beside its CI x_ci, as WP4 does.
    The leakage files write an integer count x beside the CI of its rate. The rate itself
    is not in the file, and integers decide nothing in this class, so that CI is noted
    only and the count goes on to the integer rule. Returns the keys handled here."""
    done: set = set()
    s = TOLERANCE[cls]["ci_slack"]
    for k, ci in c.items():
        if not (isinstance(k, str) and k.endswith("_ci") and isinstance(ci, list) and len(ci) == 2
                and all(is_num(x) for x in ci)):
            continue
        pt = next((p for p in (k[:-3], k[:-3] + "_mean") if is_num(c.get(p))), None)
        if pt is None:
            continue
        done.add(k)
        if isinstance(c[pt], int):
            if r.get(k) != ci:
                d.note(f"{path}/{k}: {ci} -> {r.get(k)} (the CI of a count's rate)")
            continue
        done.add(pt)
        d.n += 1
        if not is_num(r.get(pt)):
            d.bad(f"{path}/{pt}: no value in your file")
            continue
        lo, hi, v = float(ci[0]), float(ci[1]), float(r[pt])
        if not (lo - s <= v <= hi + s):
            d.bad(f"{path}/{pt}: {v:.6g} outside the committed CI [{lo:.6g}, {hi:.6g}] (committed {c[pt]:.6g})")
        elif v != c[pt]:
            d.note(f"{path}/{pt}: {c[pt]:.6g} -> {v:.6g}, inside the CI")
    return done


def sim_record(c: dict, r: dict, path: str, d: Diff) -> set:
    """A hash record of the bm25 check: pairs_differing, digest and examples follow the
    similarity values (TOLERANCE["hash"]). A different count or digest is noted. Each example
    of your file must show the same decision on both sides and similarities within the hash
    tolerance. Returns the keys handled here. The other keys of the record (pairs, the
    presence counts) go on to the exact rule."""
    tol = TOLERANCE["hash"]["abs"]
    d.n += 1
    for k in ("pairs_differing", "digest"):
        if k in c and k not in r:
            d.bad(f"{path}/{k}: missing in your file")
        elif c.get(k) != r.get(k):
            d.note(f"{path}/{k}: {c.get(k)!r} -> {r.get(k)!r} (follows hash similarities, which may move by {tol:g})")
    ex = r.get("examples") or []
    if not isinstance(ex, list):
        d.bad(f"{path}/examples: not a list")
        ex = []
    for i, e in enumerate(ex):
        new, old = (e.get("new"), e.get("old")) if isinstance(e, dict) else (None, None)
        if not (isinstance(new, dict) and isinstance(old, dict)):
            d.bad(f"{path}/examples[{i}]: not a new and old pair")
            continue
        moved = [k for k in sorted(set(new) | set(old)) if k != "similarity" and new.get(k) != old.get(k)]
        if moved:
            d.bad(f"{path}/examples[{i}]: {', '.join(moved)} changed, not only the similarity")
            continue
        a, b = new.get("similarity"), old.get("similarity")
        if (a is None) != (b is None) or (a is not None and not (is_num(a) and is_num(b)
                                                                 and close(float(a), float(b), 0, tol))):
            d.bad(f"{path}/examples[{i}]/similarity: {b} -> {a} (hash: more than {tol:g} apart)")
    return {"pairs_differing", "digest", "examples"}


def mask_sim(line: str) -> str:
    """A hash line of the bm25 check's text output with its counts of differing pairs masked."""
    return SIM_COUNT.sub("<sim>", line) if SIM_COUNT_LINE.search(line) else line


def walk(c, r, path: str, cls: str, d: Diff) -> None:
    """Compare committed c with reproduced r under class cls."""
    key = path.rsplit("/", 1)[-1]
    if path and SKIP_KEY.search(key):
        return
    hashy = cls == "exact" and (d.hash_file or bool(HASH_NAME.search(path)))
    if cls in ("gpu", "llm"):
        ci = is_ci_node(c)
        if ci is not None:
            d.n += 1
            rc = is_ci_node(r)
            if rc is None:
                d.bad(f"{path}: no value with a CI in your file")
                return
            pt, lo, hi = ci
            s = TOLERANCE[cls]["ci_slack"]
            if not (lo - s <= rc[0] <= hi + s):
                d.bad(f"{path}: {rc[0]:.6g} outside the committed CI [{lo:.6g}, {hi:.6g}] (committed {pt:.6g})")
            elif rc[0] != pt:
                d.note(f"{path}: {pt:.6g} -> {rc[0]:.6g}, inside the CI")
            return
    if isinstance(c, dict) and isinstance(r, dict):
        c, r = path_keys(c), path_keys(r)
        done = sibling_cis(c, r, path, cls, d) if cls in ("gpu", "llm") else set()
        if hashy and d.sim_counts and "pairs_differing" in c and "presence_differing" in c:
            done |= sim_record(c, r, path, d)
        for k in sorted(set(c) | set(r), key=str):
            if k in done or SKIP_KEY.search(str(k)):
                continue
            if k not in r:
                d.bad(f"{path}/{k}: missing in your file") if cls == "exact" else d.note(f"{path}/{k}: missing in yours")
            elif k not in c:
                d.note(f"{path}/{k}: only in your file")
            else:
                walk(c[k], r[k], f"{path}/{k}", cls, d)
        return
    if isinstance(c, list) and isinstance(r, list):
        sc, sr = by_spec(c), by_spec(r)
        if sc is not None and sr is not None:
            c, r = sc, sr
        perq = len(c) > 20
        if len(c) != len(r):
            (d.bad if cls == "exact" else d.note)(f"{path}: length {len(c)} -> {len(r)}")
            return
        if perq and all(is_num(x) for x in c) and all(is_num(x) for x in r):
            changed = [i for i, (x, y) in enumerate(zip(c, r)) if not same_num(x, y, hashy)]
            if changed:
                if cls == "exact":
                    d.bad(f"{path}: {len(changed)} of {len(c)} per-query values differ (first at {changed[0]})")
                else:
                    d.note(f"{path}: {len(changed)} of {len(c)} per-query values differ")
            d.n += 1
            return
        if perq and cls != "exact":
            changed = sum(json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True) for x, y in zip(c, r))
            if changed:
                d.note(f"{path}: {changed} of {len(c)} entries differ")
            d.n += 1
            return
        for i, (x, y) in enumerate(zip(c, r)):
            walk(x, y, f"{path}[{i}]", cls, d)
        return
    d.n += 1
    if is_num(c) and is_num(r):
        if cls == "exact":
            if not same_num(c, r, hashy):
                d.bad(f"{path}: {c} -> {r}"
                      + (" (hash: more than 1e-6 apart)" if hashy and isinstance(c, float) else ""))
        elif cls == "gpu":
            if isinstance(c, int) and isinstance(r, int):
                if c != r:
                    d.note(f"{path}: {c} -> {r}")
            elif not close(float(c), float(r), 0, TOLERANCE["gpu"]["abs_no_ci"]):
                d.bad(f"{path}: {c} -> {r} (more than 0.0005 apart, no CI)")
        elif cls == "ollama":
            t = TOLERANCE["ollama"]
            if key in t["acc_keys"]:
                if not close(float(c), float(r), 0, t["abs_acc"]):
                    d.bad(f"{path}: {c} -> {r} (more than {t['abs_acc']} apart)")
                elif c != r:
                    d.note(f"{path}: {c} -> {r}, within {t['abs_acc']}")
            elif any(s in path for s in ("tool", "exact", "pairs", "mcnemar", "changed", "llm_errors")):
                if c != r:
                    d.note(f"{path}: {c} -> {r}")
            elif not close(float(c), float(r), 1e-9, 1e-9):
                d.bad(f"{path}: {c} -> {r} (a retrieval metric, which must not move)")
        else:
            if c != r:
                d.note(f"{path}: {c} -> {r}")
        return
    if c != r:
        if isinstance(c, str) and isinstance(r, str) and canon(c) == canon(r):
            return
        if cls == "exact" and not (isinstance(c, str) and ("/" in c or "\\" in c)):
            d.bad(f"{path}: {str(c)[:60]!r} -> {str(r)[:60]!r}")
        else:
            d.note(f"{path}: {str(c)[:60]!r} -> {str(r)[:60]!r}")


def compare_text(cp: Path, rp: Path, cls: str, d: Diff) -> None:
    def lines(p):
        with open_any(p) as f:
            return [DURATION.sub("<time>", canon(ln.rstrip())) for ln in f
                    if ln.strip() and not MASK_LINE.search(ln) and not RUN_FACT_LINE.search(ln)]
    a, b = lines(cp), lines(rp)
    d.n += max(len(a), len(b))
    if a == b:
        return
    if cls == "exact" and d.sim_counts:
        ma, mb = [mask_sim(x) for x in a], [mask_sim(x) for x in b]
        if ma == mb:
            n = sum(x != y for x, y in zip(a, b))
            d.note(f"{n} line(s) differ only in counts of hash similarities that moved (read as similarity values)")
            return
        a, b = ma, mb
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    msg = f"{len(diff) + abs(len(a) - len(b))} line(s) differ after masking run facts, times and paths"
    if diff:
        i = diff[0]
        msg += f". First: {a[i][:80]!r} -> {b[i][:80]!r}"
    (d.bad if cls == "exact" else d.note)(msg)


def compare_csv(cp: Path, rp: Path, cls: str, d: Diff) -> None:
    def rows(p):
        with open_any(p) as f:
            return list(csv.DictReader(f))
    a, b = rows(cp), rows(rp)
    if len(a) != len(b):
        (d.bad if cls == "exact" else d.note)(f"{len(a)} rows -> {len(b)}")
        return
    timing = re.compile(r"(ms|latency|time|seconds|build)", re.I)
    for i, (x, y) in enumerate(zip(a, b)):
        for k in x:
            if timing.search(k):
                continue
            d.n += 1
            u, v = x.get(k), y.get(k)
            try:
                fu, fv = float(u), float(v)
                ok = close(fu, fv, 1e-9, 1e-9) if cls == "exact" else close(fu, fv, 0, 5e-4)
            except (TypeError, ValueError):
                ok = u == v
            if not ok:
                (d.bad if cls in ("exact", "gpu") else d.note)(f"row {i} column {k}: {u} -> {v}")


def compare_npz(cp: Path, rp: Path, cls: str, d: Diff) -> None:
    import numpy as np
    with np.load(cp) as a, np.load(rp) as b:
        for k in sorted(set(a.files) | set(b.files)):
            d.n += 1
            if k not in a.files or k not in b.files:
                d.bad(f"array {k} only on one side")
                continue
            x, y = a[k], b[k]
            if x.shape != y.shape:
                d.bad(f"array {k}: shape {x.shape} -> {y.shape}")
            elif not np.array_equal(x, y, equal_nan=x.dtype.kind == "f"):
                if x.dtype.kind != "f":
                    n = int(np.sum(x != y))
                elif cls == "exact" and d.hash_file:
                    n = int(np.sum(~np.isclose(x, y, rtol=0, atol=TOLERANCE["hash"]["abs"], equal_nan=True)))
                    if n == 0:
                        continue
                else:
                    n = int(np.sum(~np.isclose(x, y, rtol=1e-9, atol=1e-9)))
                (d.bad if cls == "exact" else d.note)(f"array {k}: {n} entries differ"
                                                       + (" (hash: more than 1e-6 apart)" if d.hash_file and x.dtype.kind == "f" else ""))


def compare_tags(cp: Path, rp: Path, d: Diff) -> None:
    """Per-item agreement of two tag files (a dict per tool or query, or a list of query entries)."""
    def items(x) -> dict:
        if isinstance(x, dict):
            return {k: frozenset(v) if isinstance(v, list) else str(v).strip() for k, v in x.items()}
        out, seen = {}, {}
        for e in x:
            k = (str(e.get("query", "")).strip(), tuple(sorted(e.get("tools", []))))
            n = seen.get(k, 0)
            seen[k] = n + 1
            out[k + (n,)] = frozenset(e.get("context_tags", []))
        return out
    with open_any(cp) as f:
        a = items(json.load(f))
    with open_any(rp) as f:
        b = items(json.load(f))
    common = a.keys() & b.keys()
    t = TOLERANCE["tags"]
    d.n += len(common)
    cov = len(common) / max(len(a), 1)
    agree = sum(a[k] == b[k] for k in common) / max(len(common), 1)
    if cov < t["min_coverage"]:
        d.bad(f"only {cov:.3f} of the committed items are in your file")
    if agree < t["min_item_agreement"]:
        d.bad(f"{agree:.3f} of the shared items carry the same tags (need {t['min_item_agreement']})")
    elif agree < 1:
        d.note(f"{agree:.3f} of the shared items carry the same tags")


def compare_file(cp: Path, rp: Path, cls: str) -> Diff:
    d = Diff()
    name = strip_gz(cp.name)
    d.hash_file = bool(HASH_NAME.search(name))
    d.sim_counts = bool(SIM_COUNT_FILE.search(name))
    if cls == "tags":
        compare_tags(cp, rp, d)
    elif name.endswith(".json"):
        with open_any(cp) as f:
            c = json.load(f)
        with open_any(rp) as f:
            r = json.load(f)
        walk(c, r, "", cls, d)
    elif name.endswith(".jsonl"):
        with open_any(cp) as f:
            a = f.read().splitlines()
        with open_any(rp) as f:
            b = f.read().splitlines()
        changed = sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
        d.n += max(len(a), len(b))
        if changed:
            (d.bad if cls == "exact" else d.note)(f"{changed} of {len(a)} lines differ")
    elif name.endswith(".csv"):
        compare_csv(cp, rp, cls, d)
    elif name.endswith(".npz"):
        compare_npz(cp, rp, cls, d)
    elif name.endswith((".txt", ".md")):
        compare_text(cp, rp, cls, d)
    else:
        with open_any(cp, "rb") as f:
            a = f.read()
        with open_any(rp, "rb") as f:
            b = f.read()
        d.n += 1
        if a != b:
            (d.bad if cls == "exact" else d.note)("bytes differ")
    return d


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    rep = Path(os.environ.get("REPRO_OUT", Path.home() / "tist-repro"))
    ap.add_argument("--repro", type=Path, default=rep / "assembled")
    ap.add_argument("--committed", type=Path, default=HERE.parent)
    ap.add_argument("--out", type=Path, default=rep / "verify")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    if not a.repro.is_dir():
        print(f"FAILED: verify: no folder {a.repro} (run 70_assemble.sh first, or pass --repro)")
        return 1
    repro, committed = a.repro.resolve(), a.committed.resolve()
    rows = []
    seen = set()
    files = []
    for dirpath, dirnames, filenames in os.walk(repro):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".git", ".repro_aside", "__pycache__")))
        files += [Path(dirpath) / f for f in sorted(filenames)]
    for rp in files:
        rel = rp.relative_to(repro).as_posix()
        key = strip_gz(rel)
        if a.only and not any(fnmatch.fnmatch(key, g) for g in a.only):
            continue
        seen.add(key)
        cls, why = classify(key)
        cp = find(committed, key)
        if cls == "skip":
            rows.append({"path": key, "class": cls, "verdict": "SKIP", "detail": why})
            continue
        if cp is None:
            rows.append({"path": key, "class": cls, "verdict": "NEW", "detail": "no committed counterpart"})
            continue
        try:
            d = compare_file(cp, rp, cls)
        except Exception as exc:  # noqa: BLE001
            rows.append({"path": key, "class": cls, "verdict": "FAIL", "detail": f"could not compare: {type(exc).__name__}: {exc}"})
            continue
        if cls == "info":
            verdict = "INFO"
        else:
            verdict = "FAIL" if d.fail else "PASS"
        detail = " | ".join(d.fail[:3]) if d.fail else (f"{len(d.info)} rounding-level or noted difference(s)" if d.info else "")
        rows.append({"path": key, "class": cls, "verdict": verdict, "detail": detail, "compared": d.n,
                     "failures": d.fail, "notes": d.info[:50]})
    for rel in pm.required_files("b"):
        key = strip_gz(rel)
        if key in seen or (a.only and not any(fnmatch.fnmatch(key, g) for g in a.only)):
            continue
        if find(repro, key) is None:
            rows.append({"path": key, "class": classify(key)[0], "verdict": "NOT RUN",
                         "detail": "the manuscript needs it (paper_map.py). Produce it first"})
    order = {"FAIL": 0, "NOT RUN": 1, "PASS": 2, "INFO": 3, "NEW": 4, "SKIP": 5}
    rows.sort(key=lambda r: (order[r["verdict"]], r["path"]))
    counts = {k: sum(r["verdict"] == k for r in rows) for k in order}
    w = max([len(r["path"]) for r in rows] + [10])
    print(f"{'verdict':8}  {'class':6}  {'file':{w}}  detail")
    for r in rows:
        if r["verdict"] in ("SKIP",):
            continue
        print(f"{r['verdict']:8}  {r['class']:6}  {r['path']:{w}}  {r['detail'][:160]}")
    print("totals: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "verify.json").write_text(json.dumps({"repro": str(repro), "committed": str(committed),
                                                   "tolerance": TOLERANCE, "counts": counts, "files": rows},
                                                  indent=1, default=str), encoding="utf-8")
    md = ["# verify.py", "", f"Your outputs `{repro}` against the committed files `{committed}`.", "",
          "Totals: " + ", ".join(f"{k} {v}" for k, v in counts.items()), "",
          "| Verdict | Class | File | Detail |", "|---|---|---|---|"]
    md += [f"| {r['verdict']} | {r['class']} | `{r['path']}` | {r['detail'][:300].replace('|', '/')} |" for r in rows]
    (a.out / "verify.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"written: {a.out / 'verify.md'} and verify.json")
    failed = counts["FAIL"] > 0 or (a.strict and counts["NOT RUN"] > 0)
    if failed:
        why = f"{counts['FAIL']} file(s) FAIL" + (f", {counts['NOT RUN']} required file(s) NOT RUN" if a.strict else "")
        print(f"FAILED: verify: {why}")
        return 1
    tail = f" ({counts['NOT RUN']} required file(s) not run yet)" if counts["NOT RUN"] else ""
    print(f"OK: verify: no file outside its tolerance{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
