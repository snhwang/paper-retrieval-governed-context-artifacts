#!/usr/bin/env python3
"""Write a run record: who ran what, where, from which code, and how it ended.

  run_record.py start RECORD --name NAME [--root DIR] [--unit UNIT] [--cwd DIR] -- CMD ...
  run_record.py end RECORD --exit-code N [--note TEXT]

``start`` writes RECORD (JSON) with the user, host, start time, command, the artifacts repo
commit and the state of hermes/, the harness dir the runner uses, the Hermes checkout, the
installed BEAR (version, path, sha) and the endpoints the harness is configured for. It contacts
no server. ``end`` adds the end time, the duration and the exit code, then appends the whole
record as one line to records.jsonl next to RECORD.

Standard library only. Paths come from the WP7_* variables that scripts/env.sh sets.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import platform
import re
import shlex
import socket
import subprocess
import sys


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run(cmd: list[str], timeout: float = 60) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else f"ERROR rc={p.returncode}: {p.stderr.strip()[:200]}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR {type(exc).__name__}: {exc}"


def git_info(path: str, sub: str | None = None) -> dict:
    if not path or not os.path.isdir(path):
        return {"path": path, "error": "missing"}
    top = run(["git", "-C", path, "rev-parse", "--show-toplevel"])
    status = run(["git", "-C", path, "status", "--porcelain"] + (["--", sub] if sub else []))
    return {"path": path, "toplevel": top,
            "branch": run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": run(["git", "-C", path, "rev-parse", "HEAD"]),
            "dirty": status.splitlines() if status and not status.startswith("ERROR") else
            ([] if not status else [status])}


BEAR_SNIPPET = (
    "import json, os, importlib.metadata as md\n"
    "try:\n"
    "    import bear\n"
    "    root = os.path.dirname(os.path.dirname(bear.__file__))\n"
    "    rd = lambda n: open(os.path.join(root, n)).read().strip() if os.path.exists(os.path.join(root, n)) else None\n"
    "    print(json.dumps({'version': md.version('bear'), 'path': root, 'sha': rd('BEAR_GIT_SHA'), 'log': rd('BEAR_GIT_LOG')}))\n"
    "except Exception as e:\n"
    "    print(json.dumps({'error': f'{type(e).__name__}: {e}'}))\n")


def bear_info(python: str) -> dict:
    if not python or not os.path.exists(python):
        return {"error": f"no interpreter at {python}"}
    out = run([python, "-c", BEAR_SNIPPET])
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": out[:300]}


def endpoints(harness_dir: str) -> dict:
    """The model and embedder URLs arms.py configures, read from the file (no server contact)."""
    out = {}
    try:
        text = open(os.path.join(harness_dir, "arms.py"), encoding="utf-8").read()
        for key in ("MODEL", "MODEL_BASE_URL", "EMBED_URL"):
            m = re.search(rf'^{key} = "([^"]*)"', text, re.M)
            out[key.lower()] = m.group(1) if m else None
    except OSError as exc:
        out["error"] = str(exc)
    return out


def start(a, cmd: list[str]) -> None:
    env = os.environ
    hermes_dir = env.get("WP7_HERMES_DIR", "")
    harness_dir = env.get("WP7_HARNESS_DIR", hermes_dir)
    rec = {
        "schema": "wp7.run_record/1",
        "name": a.name,
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "kernel": platform.release(),
        "wsl_distro": env.get("WSL_DISTRO_NAME"),
        "start_utc": now(),
        "end_utc": None,
        "duration_s": None,
        "exit_code": None,
        "command": cmd,
        "command_line": shlex.join(cmd),
        "cwd": a.cwd or os.getcwd(),
        "run_root": a.root or None,
        "systemd_unit": a.unit or None,
        "artifacts": git_info(hermes_dir, "."),
        "harness_dir": harness_dir,
        "harness": git_info(harness_dir, ".") if harness_dir != hermes_dir else "same as artifacts",
        "hermes_tree": git_info(env.get("WP7_HERMES_TREE", "")),
        "bear": bear_info(env.get("WP7_PY", "")),
        "python_runner": env.get("WP7_PY"),
        "python_analysis": env.get("WP7_PY_ANALYSIS"),
        "endpoints": endpoints(harness_dir),
        "tist_capped": env.get("TIST_CAPPED"),
        "mem_available_gb_at_start": None,
    }
    try:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable:"):
                rec["mem_available_gb_at_start"] = round(int(ln.split()[1]) / 1048576, 1)
    except OSError:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(a.record)), exist_ok=True)
    with open(a.record, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")


def end(a) -> None:
    with open(a.record, encoding="utf-8") as f:
        rec = json.load(f)
    rec["end_utc"] = now()
    t0 = dt.datetime.fromisoformat(rec["start_utc"])
    rec["duration_s"] = round((dt.datetime.fromisoformat(rec["end_utc"]) - t0).total_seconds())
    rec["exit_code"] = a.exit_code
    if a.note:
        rec["note"] = a.note
    with open(a.record, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    with open(os.path.join(os.path.dirname(os.path.abspath(a.record)), "records.jsonl"), "a",
              encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    argv = sys.argv[1:]
    cmd: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("start", "end"))
    ap.add_argument("record")
    ap.add_argument("--name", default="run")
    ap.add_argument("--root", default="")
    ap.add_argument("--unit", default="")
    ap.add_argument("--cwd", default="")
    ap.add_argument("--exit-code", type=int, default=None)
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.action == "start":
        start(a, cmd)
    else:
        end(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
