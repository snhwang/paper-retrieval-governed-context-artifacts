"""Reproducibility footer helper.

Shared utility used by the new evaluation scripts to print a consistent
metadata block at the end of every committed log file. The block
captures the command line, git commit hash, Python/numpy versions, and
a timestamp so the committed log is self-documenting and a reviewer can
trace it back to exactly the code revision that produced it.

Usage from a script::

    from repro_footer import print_repro_footer
    ...
    print_repro_footer(extra={"backend": "bge", "queries": 60})

If git is unavailable or the working tree is dirty, the helper still
prints what it can.
"""

from __future__ import annotations

import datetime as _dt
import platform as _platform
import shutil as _shutil
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path


def _safe_git(args: list[str], cwd: str | None = None) -> str:
    if not _shutil.which("git"):
        return ""
    try:
        out = _subprocess.run(
            ["git"] + args,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if out.returncode != 0:
            return ""
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _try_version(modname: str) -> str:
    try:
        mod = __import__(modname)
        return getattr(mod, "__version__", "?")
    except Exception:  # noqa: BLE001
        return "(not installed)"


def print_repro_footer(extra: dict | None = None) -> None:
    """Print a self-documenting metadata block.

    The block is bracketed with a clear ``=== Reproducibility ===`` header so it
    is easy to grep for in committed logs.

    Parameters
    ----------
    extra : dict, optional
        Additional key/value pairs to record (e.g. ``{"backend": "bge"}``).
    """
    print("\n=== Reproducibility ===")
    print(f"Timestamp (UTC): {_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"Command line:    {' '.join(_sys.argv)}")
    print(f"Python:          {_sys.version.split()[0]} ({_platform.platform()})")
    print(f"numpy:           {_try_version('numpy')}")
    print(f"scipy:           {_try_version('scipy')}")
    print(f"bear:            {_try_version('bear')}")
    # Try to locate the repo root from the script location
    try:
        repo_root = _Path(__file__).resolve().parents[1]
    except Exception:  # noqa: BLE001
        repo_root = _Path.cwd()
    sha = _safe_git(["rev-parse", "HEAD"], cwd=str(repo_root))
    if sha:
        print(f"git commit:      {sha}")
        dirty = _safe_git(["status", "--porcelain"], cwd=str(repo_root))
        if dirty:
            print(f"git status:      DIRTY ({dirty.count(chr(10))+1} files modified)")
        else:
            print(f"git status:      clean")
        branch = _safe_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo_root))
        if branch:
            print(f"git branch:      {branch}")
    else:
        print("git commit:      (not in a git repository)")
    if extra:
        print("")
        for k, v in extra.items():
            print(f"  {k}: {v}")
    print("===")
