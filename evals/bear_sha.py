#!/usr/bin/env python3
"""Print the source commit of the installed BEAR, for BEAR_SOURCE_SHA.

Reads it the way tistr2_common.bear_provenance does: the install's
direct_url.json points at a local export, which records its commit in a
BEAR_GIT_SHA (or EXPORTED_SHA) file. A VCS install gives its commit_id
instead. Prints "unknown" when neither is there. Imports nothing heavy, so
the runner scripts can call it before anything else:

    export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-$(python evals/bear_sha.py)}
"""

from __future__ import annotations

import importlib.metadata as md
import json
from pathlib import Path


def installed_bear_sha() -> str:
    try:
        raw = md.distribution("bear").read_text("direct_url.json")
    except md.PackageNotFoundError:
        return "unknown"
    info = json.loads(raw or "{}")
    url = info.get("url", "")
    if url.startswith("file://"):
        src = Path(url[len("file://"):])
        for name in ("BEAR_GIT_SHA", "EXPORTED_SHA"):
            f = src / name
            if f.exists():
                return f.read_text(encoding="utf-8").strip()
    commit = (info.get("vcs_info") or {}).get("commit_id")
    return commit or "unknown"


if __name__ == "__main__":
    print(installed_bear_sha())
