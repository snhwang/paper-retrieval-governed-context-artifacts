"""Check the run environment before the WP0 reruns, and record it.

* The imported bear package hashes the same as the source tree's bear/
  directory, and the source tree is at the expected commit. The source tree
  is either an export with an EXPORTED_SHA file (0.4.0: bear-dev 10730c8) or
  a git clone (0.4.1: public tag v0.4.1, fa87fc5).
* bear reports the expected version.
* The embedding service at NEMOTRON_URL identifies itself through /health.

Exits non-zero if any check fails.

Usage:
    python evals/wp0_v040/verify_env.py --export ~/tist-evals/bear-v0.4.1 \
        --expect-sha fa87fc5 --expect-version 0.4.1 --out results/wp0/run_provenance.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wp0_common  # noqa: E402


def tree_hash(pkg: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(pkg.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(pkg).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
    return h.hexdigest()


def source_sha(src: Path) -> str:
    f = src / "EXPORTED_SHA"
    if f.exists():
        return f.read_text().strip()
    out = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True, help="BEAR source tree (export or git clone)")
    ap.add_argument("--expect-sha", default="10730c8ae682f972b731b89789f0f7b97a521523")
    ap.add_argument("--expect-version", default="0.4.0")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = Path(args.export).expanduser()
    ident = wp0_common.bear_identity()
    sha = source_sha(src)
    src_hash = tree_hash(src / "bear")
    from bear.remote_embedder import RemoteEmbedder
    nemo = RemoteEmbedder(wp0_common.NEMOTRON_URL).identity()
    rec = {
        **wp0_common.provenance(),
        "source_dir": str(src),
        "source_sha": sha,
        "source_pkg_sha256": src_hash,
        "installed_matches_source": ident["bear_pkg_sha256"] == src_hash,
        "source_sha_is_expected": sha.startswith(args.expect_sha),
        "version_is_expected": ident["bear_version"] == args.expect_version,
        "nemotron_identity": nemo,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(json.dumps(rec, indent=2))
    ok = (rec["installed_matches_source"] and rec["source_sha_is_expected"]
          and rec["version_is_expected"] and nemo.get("model_id"))
    if not ok:
        print("VERIFY FAILED", file=sys.stderr)
        sys.exit(1)
    print("VERIFY OK")


if __name__ == "__main__":
    main()
