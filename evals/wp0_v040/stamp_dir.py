"""Stamp provenance into every JSON a run step produced (run_wp0_v040.sh).

A JSON object gains a ``_provenance`` key unless it already has one. Any other
JSON (a top-level list) gets a ``<name>.provenance.json`` sidecar. Lanes run
side by side, so a step's window can also catch a file another lane wrote.
The final assembly keeps each file only under the step that produces it. Logs carry
the same facts in their header, written by the runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wp0_common  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dest")
    ap.add_argument("--step", required=True)
    ap.add_argument("--command", default="")
    args = ap.parse_args()
    n_stamped = n_side = n_kept = 0
    for p in sorted(Path(args.dest).rglob("*.json")):
        if p.name.endswith(".provenance.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"stamp: cannot parse {p}: {exc}")
            continue
        extra = {"step": args.step, "command": args.command,
                 "file": p.relative_to(args.dest).as_posix()}
        if isinstance(data, dict):
            if "_provenance" in data:
                # Written by the producing script itself. Leave it alone: with
                # lanes running side by side, the step collecting a file is
                # not always the step that wrote it.
                n_kept += 1
                continue
            else:
                data["_provenance"] = wp0_common.provenance(extra)
                n_stamped += 1
            p.write_text(json.dumps(data, indent=1, default=float), encoding="utf-8")
        else:
            side = p.with_name(p.name + ".provenance.json")
            side.write_text(json.dumps(wp0_common.provenance(extra), indent=2), encoding="utf-8")
            n_side += 1
    print(f"stamp: {n_stamped} stamped, {n_kept} already stamped, {n_side} sidecars in {args.dest}")


if __name__ == "__main__":
    main()
