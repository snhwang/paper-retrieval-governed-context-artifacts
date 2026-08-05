#!/usr/bin/env python3
"""Verify that a re-run reproduced the committed result values.

Compares every result JSON in the working tree against the version committed
at HEAD, ignoring volatile fields that legitimately differ between runs
(timings, device names, hostnames). All scientific content (means, CIs,
per-query arrays, contrasts, p-values) must match exactly, which the fixed
bootstrap seeds and deterministic retrieval make possible.

Run after ./run_evals.sh completes:
    python evals/verify_rerun.py
Exit code 0 and "ALL MATCH" mean the re-run reproduced the reported values
bit-for-bit. Any mismatch is listed with its JSON path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VOLATILE = {"elapsed_s", "device", "hostname", "timestamp", "duration_s"}
# key-name patterns that are machine timings, not scientific values
VOLATILE_SUBSTRINGS = ("_ms", "time_s", "latency")


def is_volatile(key: str) -> bool:
    return key in VOLATILE or any(t in key for t in VOLATILE_SUBSTRINGS)


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in sorted(o.items()) if not is_volatile(k)}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


def committed(path: str) -> str | None:
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def find_mismatch(a, b, path=""):
    """Return the first differing path between two stripped JSON values."""
    if type(a) is not type(b):
        return path or "<root>"
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return f"{path}.keys({sorted(set(a) ^ set(b))})"
        for k in a:
            r = find_mismatch(a[k], b[k], f"{path}.{k}")
            if r:
                return r
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}.len({len(a)} vs {len(b)})"
        for i, (x, y) in enumerate(zip(a, b)):
            r = find_mismatch(x, y, f"{path}[{i}]")
            if r:
                return r
        return None
    if isinstance(a, float) and isinstance(b, float):
        # Summation over set-ordered items can differ by one ULP between
        # processes (floating-point addition is not associative). Equality at
        # machine precision is reproduction; anything larger is not.
        import math
        return None if math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15) else path
    return None if a == b else path


def run_marker_time() -> float | None:
    """Start time of the current re-run campaign, written by run_evals.sh /
    resume_rerun.sh. Files older than this were not produced by the re-run."""
    marker = REPO / "results" / ".rerun_started"
    if not marker.exists():
        return None
    try:
        return float(marker.read_text().strip())
    except ValueError:
        return None


def main():
    results = sorted((REPO / "results").glob("*.json"))
    since = run_marker_time()
    if since is None:
        print("NO RUN MARKER: results/.rerun_started not found. Start the")
        print("re-run with ./run_evals.sh or ./resume_rerun.sh (they write")
        print("the marker), then run this verifier.")
        sys.exit(2)
    fresh = [p for p in results if p.stat().st_mtime > since]
    if not fresh:
        print(f"checked {len(results)} result JSONs")
        print("NO RE-RUN DETECTED: no result file is newer than the run marker")
        print("(results/.rerun_started), so there is nothing new to verify.")
        print("Comparing committed files to themselves would trivially pass.")
        print("Run ./run_evals.sh or ./resume_rerun.sh first.")
        sys.exit(2)
    print(f"{len(fresh)} of {len(results)} result JSONs regenerated since the run marker")

    matched, changed, new = [], [], []
    for p in results:
        rel = p.relative_to(REPO).as_posix()
        old = committed(rel)
        if old is None:
            new.append(rel)
            continue
        try:
            a = strip(json.loads(p.read_text(encoding="utf-8")))
            b = strip(json.loads(old))
        except json.JSONDecodeError as e:
            changed.append((rel, f"unparseable: {e}"))
            continue
        where = find_mismatch(a, b)
        if where is None:
            matched.append(rel)
        else:
            changed.append((rel, where))

    stale = [p.relative_to(REPO).as_posix() for p in results
             if p.stat().st_mtime <= since]
    print(f"checked {len(results)} result JSONs")
    if stale:
        print(f"  NOT regenerated this run      : {len(stale)} "
              "(unchanged committed copies, not re-verified evidence)")
    print(f"  identical to committed values : {len(matched)}")
    print(f"  new (no committed counterpart): {len(new)}")
    for n in new:
        print(f"    NEW: {n}")
    if changed:
        print(f"  MISMATCHED: {len(changed)}")
        for rel, where in changed:
            print(f"    {rel}  first difference at {where}")
        sys.exit(1)
    print("ALL MATCH: the re-run reproduced the committed values exactly.")


if __name__ == "__main__":
    main()
