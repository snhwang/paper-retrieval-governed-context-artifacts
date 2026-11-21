#!/usr/bin/env python3
"""Run records for the reproduction kit: who ran what, where, from which code, and how it ended.

    run_record.py start RECORD --script NAME [--dry-run 0|1] [--unit UNIT] -- ARGV...
    run_record.py cmd RECORD --label L --rc N --start UTC [--cwd DIR] -- CMD...
    run_record.py endpoint RECORD --name NAME --url URL
    run_record.py note RECORD -- TEXT
    run_record.py end RECORD --exit-code N --status OK|FAILED [--reason R] [--note N]

``start`` writes RECORD (JSON): user, host, kernel, WSL distro, start time, the
script and its arguments, the artifacts checkout (branch, commit, dirty files)
and every clone the kit made, the BEAR install of the kit's venv (version,
source sha, package hash), the BEAR v0.1.10 clone, the Python stack, the
snapshot ids of the cached Hugging Face models, and the kit's settings. It
contacts no server.

``cmd`` appends one executed command with its start and end time and exit code.
``endpoint`` asks one server for its identity and stores the answer (the
Nemotron /health, Ollama's /api/version and /api/tags digests, SGLang's
/get_server_info). The scripts call it only in a real run, never in a dry run.
``end`` adds the end time, the duration, the exit code and the final status,
and appends the whole record as one line to records.jsonl beside it.

Standard library only, so the system python3 can run it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import urllib.request

HOME = os.path.expanduser("~")
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.dirname(KIT)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sh(cmd: list[str], timeout: float = 60) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else f"ERROR rc={p.returncode}: {p.stderr.strip()[:200]}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR {type(exc).__name__}: {exc}"


def git_info(path: str) -> dict:
    if not os.path.isdir(os.path.join(path, ".git")) and not os.path.isfile(os.path.join(path, ".git")):
        return {"path": path, "error": "not a git checkout"}
    status = sh(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"])
    return {"path": path,
            "branch": sh(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": sh(["git", "-C", path, "rev-parse", "HEAD"]),
            "dirty_tracked": status.splitlines() if status and not status.startswith("ERROR") else []}


PY_SNIPPET = r"""
import json, os, sys, importlib.metadata as md
out = {"python": sys.version.split()[0], "executable": sys.executable}
for p in ("bear", "torch", "transformers", "sentence-transformers", "numpy", "scipy",
          "llama-index-core", "instruction-tool-retrieval", "tiktoken"):
    try:
        out[p] = md.version(p)
    except Exception:
        out[p] = None
try:
    du = md.distribution("bear").read_text("direct_url.json")
    url = json.loads(du).get("url") if du else None
    out["bear_direct_url"] = url
    if url and url.startswith("file://"):
        f = os.path.join(url[len("file://"):], "BEAR_GIT_SHA")
        out["bear_git_sha"] = open(f).read().strip() if os.path.exists(f) else None
except Exception as e:
    out["bear_direct_url_error"] = str(e)
print(json.dumps(out))
"""


def venv_info() -> dict:
    py = os.path.join(os.environ.get("REPRO_VENV", os.path.join(HOME, ".venvs", "tist-repro")), "bin", "python")
    if not os.path.exists(py):
        return {"error": f"no interpreter at {py}"}
    out = sh([py, "-c", PY_SNIPPET], timeout=120)
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": out[:300]}


def tree_hash(pkg: str) -> str | None:
    """sha256 over bear/*.py, line endings normalized (as evals/wp0_v040/verify_env.py)."""
    if not os.path.isdir(pkg):
        return None
    h = hashlib.sha256()
    files = []
    for root, dirs, names in os.walk(pkg):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        files += [os.path.join(root, n) for n in names if n.endswith(".py")]
    for p in sorted(files, key=lambda x: os.path.relpath(x, pkg).replace(os.sep, "/")):
        h.update(os.path.relpath(p, pkg).replace(os.sep, "/").encode())
        h.update(b"\0")
        with open(p, "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def bear_sources() -> dict:
    src = os.path.join(HOME, "tist-evals", "bear-v0.4.2")
    old = os.path.join(HOME, "tist-evals", "bear-v0110")
    sha_file = os.path.join(src, "BEAR_GIT_SHA")
    return {"v0.4.2": {"path": src, "BEAR_GIT_SHA": open(sha_file).read().strip() if os.path.exists(sha_file) else None,
                       "git_head": sh(["git", "-C", src, "rev-parse", "HEAD"]),
                       "bear_tree_sha256": tree_hash(os.path.join(src, "bear"))},
            "v0.1.10": {"path": old, "git_head": sh(["git", "-C", old, "rev-parse", "HEAD"])}}


def hf_snapshots() -> dict:
    hub = os.path.join(os.environ.get("HF_HOME", os.path.join(HOME, ".cache", "huggingface")), "hub")
    out = {}
    if not os.path.isdir(hub):
        return {"error": f"no cache at {hub}"}
    for d in sorted(os.listdir(hub)):
        if not d.startswith("models--"):
            continue
        ref = os.path.join(hub, d, "refs", "main")
        name = d[len("models--"):].replace("--", "/")
        out[name] = open(ref).read().strip() if os.path.exists(ref) else sorted(
            os.listdir(os.path.join(hub, d, "snapshots"))) if os.path.isdir(os.path.join(hub, d, "snapshots")) else None
    return out


def clones() -> dict:
    out = {}
    root = os.environ.get("REPRO_OUT", os.path.join(HOME, "tist-repro"))
    for base in (os.path.join(root, "clones"), os.path.join(root, "wp0")):
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                p = os.path.join(base, d)
                if os.path.isdir(os.path.join(p, ".git")):
                    info = git_info(p)
                    out[os.path.relpath(p, root)] = {k: info.get(k) for k in ("commit", "branch", "dirty_tracked")}
    return out


def settings() -> dict:
    keep = ("REPRO_", "WP0_", "TIST_", "WP7_", "NEMOTRON", "CUDA_VISIBLE_DEVICES", "OMP_NUM_THREADS",
            "MKL_NUM_THREADS", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "BEAR_SOURCE_SHA", "PYTHONHASHSEED")
    return {k: v for k, v in sorted(os.environ.items()) if k.startswith(keep)}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path: str, rec: dict) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"  # one per process, so that two writers never share it
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def start(a, argv: list[str]) -> None:
    rec = {
        "schema": "tist-repro.run_record/1",
        "script": a.script,
        "dry_run": a.dry_run == "1",
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "kernel": platform.release(),
        "wsl_distro": os.environ.get("WSL_DISTRO_NAME"),
        "systemd_unit": a.unit or None,
        "start_utc": now(),
        "end_utc": None,
        "duration_s": None,
        "exit_code": None,
        "status": "running",
        "argv": argv,
        "command_line": shlex.join(["bash"] + argv),
        "cwd": os.getcwd(),
        "artifacts": git_info(ART),
        "clones": clones(),
        "venv": venv_info(),
        "bear_sources": bear_sources(),
        "hf_model_snapshots": hf_snapshots(),
        "settings": settings(),
        "endpoints": {},
        "commands": [],
        "notes": [],
    }
    try:
        with open("/proc/meminfo") as f:
            for ln in f:
                if ln.startswith(("MemTotal:", "MemAvailable:")):
                    k, v = ln.split(":")
                    rec[f"{k.lower()}_gb_at_start"] = round(int(v.split()[0]) / 1048576, 1)
        rec["cpus"] = os.cpu_count()
    except OSError:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(a.record)), exist_ok=True)
    save(a.record, rec)


def get_json(url: str, data: bytes | None = None, timeout: float = 15) -> object:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except ValueError:
        return body[:2000]


def endpoint(a) -> None:
    rec = load(a.record)
    entry: dict = {"url": a.url, "checked_utc": now()}
    try:
        if a.name == "ollama":
            root = a.url.rstrip("/")
            entry["version"] = get_json(root + "/api/version")
            tags = get_json(root + "/api/tags")
            entry["models"] = [{k: m.get(k) for k in ("name", "digest", "size", "modified_at", "details")}
                               for m in (tags.get("models", []) if isinstance(tags, dict) else [])]
        elif a.name == "sglang":
            info = get_json(a.url.rstrip("/") + "/get_server_info")
            keep = ("model_path", "served_model_name", "revision", "version", "kv_cache_dtype", "random_seed",
                    "dtype", "tp_size", "enable_cache_report", "tool_call_parser", "reasoning_parser")
            entry["server_info"] = {k: info.get(k) for k in keep} if isinstance(info, dict) else info
        else:
            entry["response"] = get_json(a.url)
    except Exception as exc:  # noqa: BLE001
        entry["error"] = f"{type(exc).__name__}: {exc}"
    rec.setdefault("endpoints", {})[a.name] = entry
    save(a.record, rec)


def cmd(a, argv: list[str]) -> None:
    rec = load(a.record)
    rec.setdefault("commands", []).append({"label": a.label, "start_utc": a.start, "end_utc": now(),
                                           "exit_code": a.rc, "cwd": a.cwd, "argv": argv,
                                           "command_line": shlex.join(argv)})
    save(a.record, rec)


def note(a, argv: list[str]) -> None:
    rec = load(a.record)
    rec.setdefault("notes", []).append({"utc": now(), "text": " ".join(argv)})
    save(a.record, rec)


def end(a) -> None:
    rec = load(a.record)
    rec["end_utc"] = now()
    t0 = dt.datetime.fromisoformat(rec["start_utc"])
    rec["duration_s"] = round((dt.datetime.fromisoformat(rec["end_utc"]) - t0).total_seconds())
    rec["exit_code"] = a.exit_code
    rec["status"] = a.status
    if a.reason:
        rec["failure_reason"] = a.reason
    if a.note:
        rec.setdefault("notes", []).append({"utc": now(), "text": a.note})
    save(a.record, rec)
    with open(os.path.join(os.path.dirname(os.path.abspath(a.record)), "records.jsonl"), "a",
              encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    argv = sys.argv[1:]
    rest: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, rest = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("start", "cmd", "endpoint", "note", "end"))
    ap.add_argument("record")
    ap.add_argument("--script", default="")
    ap.add_argument("--dry-run", default="0")
    ap.add_argument("--unit", default="")
    ap.add_argument("--label", default="")
    ap.add_argument("--rc", type=int, default=None)
    ap.add_argument("--start", default="")
    ap.add_argument("--cwd", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--exit-code", type=int, default=None)
    ap.add_argument("--status", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.action == "start":
        start(a, rest)
    elif a.action == "cmd":
        cmd(a, rest)
    elif a.action == "endpoint":
        endpoint(a)
    elif a.action == "note":
        note(a, rest)
    else:
        end(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
