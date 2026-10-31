"""Shared helpers for the reproduce/derive scripts.

Each derive script computes one small set of manuscript numbers that no eval
script writes, from committed data or code, and saves them as JSON with their
sources: every input file with its sha256, the artifacts commit, and the BEAR
version when the script imports BEAR. None loads a model or calls a server.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]      # the checkout or clone that holds this script
EVALS = REPO / "evals"


def use_evals() -> None:
    """Make the clone's evals/ importable (eval_toolbench and friends)."""
    for p in (str(REPO), str(EVALS)):
        if p not in sys.path:
            sys.path.insert(0, p)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance(script: str, inputs: list[Path]) -> dict:
    try:
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                                text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = None
    out = {"script": script, "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "artifacts_commit": commit,
           "inputs": [{"path": str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p),
                       "sha256": sha256(p)} for p in inputs if p.exists()]}
    try:
        import importlib.metadata as md
        out["bear_version"] = md.version("bear")
    except Exception:  # noqa: BLE001
        pass
    return out


def write(out: Path, data: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "_provenance"}, indent=1, default=str)[:3000])
    print(f"written: {out}")
