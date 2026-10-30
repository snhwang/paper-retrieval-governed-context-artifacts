"""Provenance for WP7 runs: code, model, serving stack and embedder, read from the live system.

``collect()`` is written once per run (provenance.json). ``fingerprint()`` is cheap and is
recorded with every cell, so a server restart or a model swap mid-run shows up in the logs.

Server info is copied by an allow-list of keys, so no API key or token from SGLang's
get_server_info ever reaches a log.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import urllib.request
from typing import Any

SGLANG = "http://localhost:8355"
EMBED = "http://localhost:8360"
SGLANG_KEYS = ("version", "model_path", "served_model_name", "revision", "tokenizer_path",
               "quantization", "kv_cache_dtype", "context_length", "random_seed",
               "enable_cache_report", "tool_call_parser", "reasoning_parser",
               "max_running_requests", "sampling_defaults", "chat_template", "dtype",
               "tp_size", "mem_fraction_static", "attention_backend")
MODEL_INFO_KEYS = ("model_path", "served_model_name", "weight_version", "tool_call_parser",
                   "reasoning_parser", "model_type", "architectures")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _get_json(url: str, timeout: float = 10.0) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _run(cmd: list[str], timeout: float = 15.0) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else f"<rc={p.returncode}> {p.stderr.strip()[:300]}"
    except Exception as exc:
        return f"<error> {type(exc).__name__}: {exc}"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        return f"<missing> {exc}"


def container(port: int) -> dict:
    """The docker container publishing ``port``: image id, image digests and start time."""
    name = _run(["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"])
    if not name or name.startswith("<"):
        return {"error": name or "no container publishes this port"}
    name = name.splitlines()[0]
    raw = _run(["docker", "inspect", name])
    try:
        info = json.loads(raw)[0]
    except Exception:
        return {"name": name, "error": raw[:300]}
    image_id = info.get("Image", "")
    digests = _run(["docker", "image", "inspect", image_id, "--format", "{{json .RepoDigests}}"])
    try:
        digests = json.loads(digests)
    except Exception:
        pass
    return {"name": name, "image": info.get("Config", {}).get("Image"), "image_id": image_id,
            "repo_digests": digests, "created": info.get("Created"),
            "started_at": info.get("State", {}).get("StartedAt")}


def sglang_info() -> dict:
    info = _get_json(f"{SGLANG}/get_server_info")
    out = {k: info.get(k) for k in SGLANG_KEYS if isinstance(info, dict) and k in info}
    if isinstance(info, dict) and "_error" in info:
        out["_error"] = info["_error"]
    mi = _get_json(f"{SGLANG}/get_model_info")
    out["model_info"] = {k: mi.get(k) for k in MODEL_INFO_KEYS if isinstance(mi, dict) and k in mi}
    models = _get_json(f"{SGLANG}/v1/models")
    out["v1_models"] = [{k: m.get(k) for k in ("id", "root", "max_model_len")}
                        for m in (models.get("data") or [])] if isinstance(models, dict) else models
    return out


def embedder_info() -> dict:
    return _get_json(f"{EMBED}/health")


def bear_info() -> dict:
    try:
        import importlib.metadata as md
        import bear
        root = os.path.dirname(os.path.dirname(bear.__file__))
        sha_file = os.path.join(root, "BEAR_GIT_SHA")
        log_file = os.path.join(root, "BEAR_GIT_LOG")
        return {"version": md.version("bear"), "path": root,
                "sha": open(sha_file).read().strip() if os.path.exists(sha_file) else None,
                "log": open(log_file).read().strip() if os.path.exists(log_file) else None}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def hermes_info(tree: str) -> dict:
    status = _run(["git", "-C", tree, "status", "--porcelain"])
    return {"tree": tree, "commit": _run(["git", "-C", tree, "rev-parse", "HEAD"]),
            "describe": _run(["git", "-C", tree, "log", "-1", "--format=%H %cI %s"]),
            "dirty_files": 0 if status == "" else len(status.splitlines())}


def artifacts_info(hermes_dir: str) -> dict:
    """The artifacts repo commit these materials come from, and whether hermes/ is dirty."""
    repo = os.path.dirname(os.path.abspath(hermes_dir))
    status = _run(["git", "-C", repo, "status", "--porcelain", "--", "hermes"], timeout=60)
    return {"repo": repo,
            "branch": _run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"], timeout=60),
            "commit": _run(["git", "-C", repo, "rev-parse", "HEAD"], timeout=60),
            "hermes_dirty": status.splitlines() if status else []}


def files(hermes_dir: str, tree: str) -> dict:
    paths = {
        "harness/worker.py": os.path.join(tree, "evals/core_tool_deferral/worker.py"),
        "harness/tasks.py": os.path.join(tree, "evals/core_tool_deferral/tasks.py"),
        "harness/sandbox.py": os.path.join(tree, "evals/core_tool_deferral/sandbox.py"),
        "toolperf/ab_eval.py": os.path.join(tree, "evals/toolperf_abeval/ab_eval.py"),
    }
    for rel in ("worker/worker_local.py", "worker/wp7_tasks.py", "arms.py", "run.py",
                "provenance.py", "checks.py", "sandbox_bridge.py", "sandbox_redteam.py",
                "corpus/base/tools.yaml", "corpus/decoys/decoys-100.yaml",
                "corpus/decoys/decoys-300.yaml", "decoys/sample.json",
                "decoys/wp7_decoys/__init__.py", "decoys/wp7_decoys/plugin.yaml",
                "registry/harness_registry.json"):
        paths[f"hermes/{rel}"] = os.path.join(hermes_dir, rel)
    return {k: sha256_file(v) for k, v in paths.items()}


def collect(hermes_dir: str, tree: str) -> dict:
    return {
        "recorded_at": now(),
        "host": socket.gethostname(),
        "kernel": platform.release(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "hermes": hermes_info(tree),
        "artifacts": artifacts_info(hermes_dir),
        "bear": bear_info(),
        "sglang": {"endpoint": f"{SGLANG}/v1", **sglang_info(), "container": container(8355)},
        "embedder": {"endpoint": EMBED, "health": embedder_info(), "container": container(8360)},
        "files_sha256": files(hermes_dir, tree),
    }


SGLANG_GUARDED_SETTINGS = ("quantization", "kv_cache_dtype", "context_length", "random_seed",
                           "enable_cache_report", "tool_call_parser", "reasoning_parser",
                           "dtype", "tp_size")
# A change in any of these between cells stops a guarded run (run.py --guard-provenance).
GUARDED = ("sglang_version", "model_path", "model_revision", "sglang_image_id", "sglang_settings",
           "embedder_model_id", "embedder_dim", "embedder_image_id", "bear_version", "bear_sha",
           "hermes_commit", "hermes_dirty")
# A change in these is logged as a warning only (a restart on the same image and model).
WARN_ONLY = ("sglang_started_at", "embedder_started_at")


def bear_info_fresh(python: str) -> dict:
    """bear_info() in a new interpreter, so a reinstall mid-run shows up."""
    here = os.path.dirname(os.path.abspath(__file__))
    code = ("import sys, json; sys.path.insert(0, %r); import provenance; "
            "print(json.dumps(provenance.bear_info()))" % here)
    out = _run([python, "-c", code], timeout=60)
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:
        return {"error": out[:300]}


def fingerprint(python: str | None = None, tree: str | None = None) -> dict:
    """What would reveal a server restart, a swapped model or a changed install between cells."""
    s = _get_json(f"{SGLANG}/get_server_info")
    e = embedder_info()
    cs, ce = container(8355), container(8360)
    fp = {
        "sglang_version": s.get("version") if isinstance(s, dict) else None,
        "model_path": s.get("model_path") if isinstance(s, dict) else None,
        "model_revision": s.get("revision") if isinstance(s, dict) else None,
        "sglang_settings": {k: s.get(k) for k in SGLANG_GUARDED_SETTINGS}
        if isinstance(s, dict) and "_error" not in s else None,
        "sglang_image_id": cs.get("image_id"),
        "sglang_started_at": cs.get("started_at"),
        "embedder_model_id": e.get("model_id") if isinstance(e, dict) else None,
        "embedder_dim": e.get("dim") if isinstance(e, dict) else None,
        "embedder_image_id": ce.get("image_id"),
        "embedder_started_at": ce.get("started_at"),
    }
    if python:
        b = bear_info_fresh(python)
        fp["bear_version"], fp["bear_sha"] = b.get("version"), b.get("sha")
    if tree:
        h = hermes_info(tree)
        fp["hermes_commit"], fp["hermes_dirty"] = h["commit"], h["dirty_files"]
    return fp


def drift(ref: dict, cur: dict) -> tuple[dict, dict]:
    """Guarded and warn-only fields whose value differs from the reference."""
    changed = {k: [ref.get(k), cur.get(k)] for k in GUARDED if k in ref and ref.get(k) != cur.get(k)}
    warned = {k: [ref.get(k), cur.get(k)] for k in WARN_ONLY if ref.get(k) != cur.get(k)}
    return changed, warned


def embedder_revision() -> str:
    """The Nemotron image id, recorded as the plugin's embedding_revision."""
    c = container(8360)
    return c.get("image_id") or ""
