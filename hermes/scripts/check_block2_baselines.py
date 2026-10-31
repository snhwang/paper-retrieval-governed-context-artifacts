#!/usr/bin/env python3
"""Check that the stage-1 grid supplies block 2's C-gate and B baselines with identical settings.

Block 2 first planned its own C-gate and B cells beside C-cut (the two baseline sub-grids
below, as committed in specs/stage2_block2.json up to 324bf10). Stage 1 now runs on the same
harness and BEAR (specs/stage1_v2.json), so those cells already exist there. This script builds
the cell lists with run.py's own grid code and checks, offline:
- every original baseline cell has a cell with the same id in the stage-1 grid (a cell id
  changes whenever any setting changes),
- the two have equal switches and an identical rendered Hermes config (arms.hermes_config),
- the new block 2 plus those baselines is exactly the original block 2.
Prints the cell counts and PASS or FAIL. No server, no model, no file written.

Usage: $WP7_PY scripts/check_block2_baselines.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
H = os.environ.get("WP7_HARNESS_DIR") or os.path.dirname(HERE)
sys.path.insert(0, H)
import arms  # noqa: E402
import run  # noqa: E402

ORIGINAL_BASELINES = [
    {"label": "C-gate and B, operators", "arms": ["C-gate", "B"], "backends": ["nemotron"], "roles": ["operator"],
     "decoys": [0, 100], "annotations": ["off"], "scope": "turn", "query": "message", "tasks": "all", "reps": 3},
    {"label": "C-gate and B, guests at 100 decoys", "arms": ["C-gate", "B"], "backends": ["nemotron"],
     "roles": ["guest"], "decoys": [100], "annotations": ["off"], "scope": "turn", "query": "message",
     "tasks": "all", "reps": 3},
]


def cells(spec: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        path = f.name
    try:
        p = argparse.ArgumentParser()
        run.add_grid_args(p)
        a = p.parse_args(["--root", "/nonexistent", "--spec", path])
        return {arms.cell_id(arm, task, rep, sw): (arm, sw) for arm, task, rep, sw in run.grid(a)}
    finally:
        os.unlink(path)


def config(arm: str, sw) -> dict:
    return arms.hermes_config(arm, sw, corpus_dir="/corpus", audit_path="/audit.jsonl",
                              embedding_revision="sha256:fixed")


def main() -> int:
    with open(os.path.join(H, "specs", "stage1_v2.json"), encoding="utf-8") as f:
        stage1 = cells(json.load(f))
    with open(os.path.join(H, "specs", "stage2_block2.json"), encoding="utf-8") as f:
        block2 = json.load(f)
    new_b2 = cells(block2)
    base = cells({"grids": ORIGINAL_BASELINES})
    original_b2 = cells({"grids": block2["grids"] + ORIGINAL_BASELINES})
    missing = sorted(c for c in base if c not in stage1)
    differ = sorted(c for c in base if c in stage1 and (stage1[c][0] != base[c][0] or stage1[c][1] != base[c][1]
                                                         or config(*stage1[c]) != config(*base[c])))
    union_ok = set(new_b2) | set(base) == set(original_b2) and not (set(new_b2) & set(base))
    print(json.dumps({"stage1_v2_cells": len(stage1), "block2_new_cells": len(new_b2),
                      "baseline_cells": len(base), "block2_original_cells": len(original_b2),
                      "baselines_missing_from_stage1": len(missing), "baselines_with_other_settings": len(differ),
                      "new_block2_plus_baselines_equals_original": union_ok,
                      "examples": {"missing": missing[:3], "differ": differ[:3]}}, indent=1))
    ok = not missing and not differ and union_ok
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
