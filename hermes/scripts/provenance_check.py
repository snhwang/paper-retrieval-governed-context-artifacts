#!/usr/bin/env python3
"""Compare the live setup with the one the reported runs used.

  provenance_check.py expected/stage1_v2.json      (before the stage-1 grid, current harness, BEAR v0.4.2)
  provenance_check.py expected/stage2.json         (before each stage-2 block, BEAR v0.4.2)
  provenance_check.py expected/stage1_9820f8a.json (historical path only: harness 9820f8a, BEAR v0.4.1)

Checks two things and exits 1 on any difference:
- the fingerprint run.py guards during a grid (provenance.fingerprint): SGLang version, model
  path and revision, the guarded SGLang settings, both container image ids, the embedder model
  id and dimension, BEAR version and sha, the Hermes commit and its dirty-file count. Container
  start times may differ and are only printed.
- the sha256 of every material file the runner records (provenance.files): the Hermes harness
  files and, in WP7_HARNESS_DIR, the worker, runner, arms, corpus, decoys and registry.

Contacts 8355 (/get_server_info) and 8360 (/health), and runs ``docker inspect`` for the two
containers. Run it with the runner venv's Python (WP7_PY), from any directory.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.environ.get("WP7_HARNESS_DIR") or os.path.dirname(HERE)
TREE = os.environ.get("WP7_HERMES_TREE") or os.path.expanduser("~/src/hermes-agent")
sys.path.insert(0, HARNESS)
import provenance  # noqa: E402


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "expected", "stage2.json")
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(HERE, path)
    with open(path, encoding="utf-8") as f:
        exp = json.load(f)
    cur = provenance.fingerprint(sys.executable, TREE)
    fp_diff = {k: {"expected": v, "now": cur.get(k)} for k, v in exp["fingerprint"].items() if cur.get(k) != v}
    files_now = provenance.files(HARNESS, TREE)
    file_diff = {k: {"expected": v, "now": files_now.get(k)} for k, v in exp["files_sha256"].items()
                 if files_now.get(k) != v}
    out = {"expected_file": path, "stage": exp.get("stage"), "harness_dir": HARNESS, "hermes_tree": TREE,
           "expected_harness_commit": exp.get("harness_commit"),
           "fingerprint_differences": fp_diff, "file_differences": file_diff,
           "start_times_now": {k: cur.get(k) for k in ("sglang_started_at", "embedder_started_at")},
           "result": "PASS" if not fp_diff and not file_diff else "FAIL"}
    print(json.dumps(out, indent=1, default=str))
    return 0 if out["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
