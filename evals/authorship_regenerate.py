#!/usr/bin/env python3
"""Authorship ablation: write the LLM tags again with a second model family (WP6.4).

Claude Sonnet 4.6 wrote five sets of metadata the paper uses:

    tool_tags         MetaTool tool tags          metatool_generate_tags.py
    query_tags_top5   MetaTool top-5 query tags   metatool_generate_query_tags_top5.py
    toolbench_top1    ToolBench category, top-1   eval_toolbench_inferred_categories.py
    toolbench_multi   ToolBench categories, all   eval_toolbench_multitag_categories.py
    toolbench_top5    ToolBench categories, top-5 eval_toolbench_top5_categories.py

This script writes them again with another model family behind an
OpenAI-compatible endpoint (the local Qwen3.8-27B under SGLang). A reviewer can
then see whether the results depend on the tagger.

Only the client differs. The prompts, closed vocabularies, tool schemas,
parsing, retries and validation are the original scripts' own code, called
unchanged. Those scripts build Anthropic Messages requests and send them with
``urllib.request.urlopen``. In this process only, urlopen is replaced by a shim
(the vendor-shim pattern of paper-knowledge-flow's ``make_questions.py``, moved
down to the wire). A request for the Anthropic Messages endpoint is translated
to ``/chat/completions`` on ``--base-url``. The reply is translated back to the
Anthropic shape, so the original parsing and validation read it. HTTP errors
pass through unchanged, so each original's retry policy applies as written.
The Anthropic key is never sent anywhere. Any other URL is refused, except
requests under ``--base-url`` itself.

Client-only settings, recorded in the manifest:

    chat_template_kwargs.enable_thinking = false   (--thinking turns it on)
        Sonnet ran without extended thinking, so the second model runs
        without it too. A leading <think> block in a reply is removed and
        counted, since an Anthropic text block never carries one.

The MetaTool generators run through their own ``main()``, so their worker
pool, resume, periodic flush and failure handling are reused unchanged. The
ToolBench generators' ``main()`` is not called, because it opens fixed log
files under ``results/`` for writing. Their own ``infer_categories`` runs
instead, with the module's ``CACHE_PATH`` pointed at the new output file.

Subcommands:

    generate   write the tags (``--dry-run`` sends nothing)
    compare    model-free agreement between the Sonnet files and new ones
    evaluate   Recall@5 under both taggers with paired tests (CPU by default)

Outputs go to ``evals/data/authorship/<model-slug>/``. No committed file is
ever written. A file that git tracks, or one of the Sonnet files, is refused
as an output.

Usage (WSL, from the repo root, after the endpoint is up):
    python evals/authorship_regenerate.py generate --dry-run
    python evals/authorship_regenerate.py generate --base-url http://localhost:8355/v1
    python evals/authorship_regenerate.py generate --only toolbench_top1 --max-items 20
    python evals/authorship_regenerate.py compare --regen-dir evals/data/authorship/<slug>
    python evals/authorship_regenerate.py evaluate --regen-dir evals/data/authorship/<slug>
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import importlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_BASE_URL = "http://localhost:8355/v1"
DUMMY_KEY = "unused-by-authorship-shim"

METATOOL_DIR = EVALS_DIR / "data" / "external_benchmarks" / "metatool"
RESULTS_DIR = REPO_ROOT / "results"
DEFAULT_OUT_ROOT = EVALS_DIR / "data" / "authorship"

TARGETS = ("tool_tags", "query_tags_top5", "toolbench_top1", "toolbench_multi", "toolbench_top5")
TB_MODULES = {
    "toolbench_top1": "eval_toolbench_inferred_categories",
    "toolbench_multi": "eval_toolbench_multitag_categories",
    "toolbench_top5": "eval_toolbench_top5_categories",
}
OUT_NAMES = {
    "tool_tags": "plugin_tags.json",
    "query_tags_top5": "query_tags_top5.json",
    "toolbench_top1": "toolbench_inferred_categories.json",
    "toolbench_multi": "toolbench_multitag_categories.json",
    "toolbench_top5": "toolbench_top5_categories.json",
}
SONNET_FILES = {
    "tool_tags": METATOOL_DIR / "plugin_tags.json",
    "query_tags_top5": METATOOL_DIR / "query_tags_top5.json",
    "toolbench_top1": RESULTS_DIR / "toolbench_inferred_categories.json",
    "toolbench_multi": RESULTS_DIR / "toolbench_multitag_categories.json",
    "toolbench_top5": RESULTS_DIR / "toolbench_top5_categories.json",
}
# The generator code whose behavior this script reuses. Each file's SHA-256
# goes in the manifest, so a later reader can check nothing changed.
GENERATOR_SOURCES = (
    "metatool_tagging.py",
    "metatool_generate_tags.py",
    "metatool_generate_query_tags_top5.py",
    "eval_toolbench_inferred_categories.py",
    "eval_toolbench_multitag_categories.py",
    "eval_toolbench_top5_categories.py",
    "eval_toolbench.py",
    "authorship_regenerate.py",
)

# Request keys the shim knows how to carry. Anything else would be dropped in
# translation, so it is an error instead.
_KNOWN_REQUEST_KEYS = {"model", "max_tokens", "temperature", "system", "messages",
                       "tools", "tool_choice"}
_STOP = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use",
         "function_call": "tool_use", "eos": "end_turn"}
_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.S)


def _sha(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Wire-level shim
# ---------------------------------------------------------------------------

class ShimError(RuntimeError):
    """A request the shim cannot carry faithfully."""


class ShimRefused(RuntimeError):
    """A request to a URL the shim does not allow."""


def translate_request(payload: dict, extra: dict | None = None) -> dict:
    """An Anthropic Messages payload as an OpenAI chat/completions payload.

    The system prompt becomes the first message. The user messages pass
    through as they are. A tool's ``input_schema`` becomes the function's
    ``parameters``, and a forced tool becomes a named ``tool_choice``. ``extra``
    holds client-only settings and may not overwrite a translated field.
    """
    unknown = set(payload) - _KNOWN_REQUEST_KEYS
    if unknown:
        raise ShimError(f"request fields the shim cannot carry: {sorted(unknown)}")
    messages: list[dict] = []
    system = payload.get("system")
    if system is not None:
        if not isinstance(system, str):
            raise ShimError("only a string system prompt is supported")
        messages.append({"role": "system", "content": system})
    for m in payload["messages"]:
        if not isinstance(m.get("content"), str):
            raise ShimError("only string message content is supported")
        messages.append({"role": m["role"], "content": m["content"]})
    out: dict = {"model": payload["model"], "messages": messages,
                 "max_tokens": payload["max_tokens"]}
    if "temperature" in payload:
        out["temperature"] = payload["temperature"]
    if payload.get("tools"):
        out["tools"] = [{"type": "function",
                         "function": {"name": t["name"],
                                      "description": t.get("description", ""),
                                      "parameters": t["input_schema"]}}
                        for t in payload["tools"]]
    choice = payload.get("tool_choice")
    if choice:
        kind = choice.get("type")
        if kind == "tool":
            out["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
        elif kind == "any":
            out["tool_choice"] = "required"
        elif kind == "auto":
            out["tool_choice"] = "auto"
        else:
            raise ShimError(f"tool_choice type {kind!r} is not supported")
    for k, v in (extra or {}).items():
        if k in out:
            raise ShimError(f"client extra {k!r} would overwrite a translated field")
        out[k] = v
    return out


def translate_response(data: dict) -> tuple[dict, dict]:
    """An OpenAI chat/completions reply in the Anthropic Messages shape.

    Returns the reply and counts of what the translation had to do. A tool
    call becomes a ``tool_use`` block. Arguments that are not valid JSON are
    dropped and counted, so the original code sees no tool call and retries,
    as it would on an Anthropic reply without one. Text becomes a ``text``
    block, with any leading ``<think>`` block removed and counted.
    """
    notes: Counter = Counter()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content: list[dict] = []
    text = msg.get("content")
    calls = msg.get("tool_calls") or []
    if text is not None or not calls:
        text = text or ""
        stripped = _THINK.sub("", text, count=1)
        if stripped != text:
            notes["think_block_removed"] += 1
        if calls and not stripped.strip():
            pass  # an empty text beside a tool call carries nothing
        else:
            content.append({"type": "text", "text": stripped})
    for call in calls:
        fn = call.get("function") or {}
        args = fn.get("arguments")
        try:
            inp = json.loads(args) if isinstance(args, str) else (args or {})
        except json.JSONDecodeError:
            notes["bad_tool_arguments"] += 1
            continue
        if not isinstance(inp, dict):
            notes["bad_tool_arguments"] += 1
            continue
        content.append({"type": "tool_use", "id": call.get("id", ""),
                        "name": fn.get("name", ""), "input": inp})
    finish = choice.get("finish_reason") or ""
    stop = "tool_use" if any(b["type"] == "tool_use" for b in content) \
        else _STOP.get(finish, finish)
    usage = data.get("usage") or {}
    reply = {"id": data.get("id", ""), "type": "message", "role": "assistant",
             "model": data.get("model", ""), "content": content, "stop_reason": stop,
             "usage": {"input_tokens": usage.get("prompt_tokens", 0),
                       "output_tokens": usage.get("completion_tokens", 0)}}
    return reply, dict(notes)


class _Reply:
    """What urlopen returns, as far as the original code reads it."""

    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)
        self.status = 200
        self.headers: dict = {}

    def read(self, *a):
        return self._buf.read(*a)

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self._buf.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class AnthropicToOpenAIShim:
    """Replaces ``urllib.request.urlopen`` in this process.

    ``transport`` is what actually sends a request. It defaults to the real
    urlopen, captured when the shim is installed. Tests pass a stub.
    ``log_path`` receives one JSON line per translated request, with hashes of
    the system prompt, user prompt and tool schema, so two runs can be checked
    for identical prompts.
    """

    def __init__(self, base_url: str, extra: dict | None = None, transport=None,
                 log_path: Path | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_url = self.base_url + "/chat/completions"
        self.extra = dict(extra or {})
        self._transport = transport
        self._real = None
        self._lock = threading.Lock()
        self._log_path = log_path
        self.target = ""
        self.stats: Counter = Counter()
        self.system_prompts: dict[str, str] = {}
        self.tool_schemas: dict[str, dict] = {}
        self.request_shapes: dict[str, dict] = {}
        self.served_models: Counter = Counter()
        self.last_payloads: dict[str, tuple[dict, dict]] = {}

    # -- installation --------------------------------------------------------
    def install(self) -> "AnthropicToOpenAIShim":
        if self._real is not None:
            return self
        self._real = urllib.request.urlopen
        if self._transport is None:
            self._transport = self._real
        urllib.request.urlopen = self.urlopen
        return self

    def uninstall(self) -> None:
        if self._real is not None:
            urllib.request.urlopen = self._real
            self._real = None

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.uninstall()
        return False

    # -- the replacement -----------------------------------------------------
    def urlopen(self, req, data=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kw):
        url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
        if url == ANTHROPIC_MESSAGES_URL:
            return self._messages(req, timeout)
        if url.startswith(self.base_url + "/"):
            return self._transport(req, data, timeout, **kw)
        with self._lock:
            self.stats["refused"] += 1
        raise ShimRefused(f"refused a request to {url}. Only the Anthropic Messages "
                          f"endpoint (translated) and {self.base_url} are allowed.")

    def _messages(self, req: urllib.request.Request, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        translated = translate_request(payload, self.extra)
        self._record(payload, translated)
        out = urllib.request.Request(
            self.chat_url, data=json.dumps(translated).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self._transport(out, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            with self._lock:
                self.stats[f"http_{e.code}"] += 1
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            with self._lock:
                self.stats["transport_error"] += 1
            raise
        reply, notes = translate_response(data)
        with self._lock:
            self.stats["responses"] += 1
            for k, v in notes.items():
                self.stats[k] += v
            if payload.get("tool_choice") and not any(
                    b["type"] == "tool_use" for b in reply["content"]):
                self.stats["no_tool_call"] += 1
            if data.get("model"):
                self.served_models[data["model"]] += 1
        return _Reply(json.dumps(reply).encode("utf-8"))

    def _record(self, payload: dict, translated: dict) -> None:
        system = payload.get("system") or ""
        user = "\n".join(m["content"] for m in payload["messages"])
        tools = payload.get("tools") or []
        rec = {
            "target": self.target,
            "sha256_system": _sha(system),
            "sha256_user": _sha(user),
            "sha256_tools": _sha(_canon(tools)) if tools else None,
            "sha256_translated": _sha(_canon(translated)),
            "model": payload.get("model"),
            "max_tokens": payload.get("max_tokens"),
            "temperature": payload.get("temperature"),
        }
        shape = {k: rec[k] for k in ("sha256_system", "sha256_tools", "max_tokens",
                                     "temperature")}
        with self._lock:
            self.stats["requests"] += 1
            self.system_prompts[rec["sha256_system"]] = system
            for t in tools:
                self.tool_schemas[_sha(_canon(t))] = t
            self.request_shapes[self.target or "-"] = shape
            self.last_payloads[self.target or "-"] = (payload, translated)
            if self._log_path is not None:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")


def deny_all(req, data=None, timeout=None, **kw):
    """A transport that sends nothing, for modes that must make no calls."""
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    raise ShimRefused(f"no network in this mode: {url}")


def canned_transport(req, data=None, timeout=None, **kw):
    """A transport that answers locally, for --dry-run.

    It picks the first allowed value of every enum, and for a text request the
    first category in the prompt's list. Nothing leaves the process.
    """
    body = json.loads(req.data.decode("utf-8"))
    message: dict = {"role": "assistant", "content": None}
    if body.get("tools"):
        params = body["tools"][0]["function"]["parameters"]
        args = {}
        for name, spec in params.get("properties", {}).items():
            if spec.get("type") == "array":
                args[name] = [spec["items"]["enum"][0]]
            else:
                args[name] = spec.get("enum", [""])[0]
        message["tool_calls"] = [{"id": "dry", "type": "function",
                                  "function": {"name": body["tools"][0]["function"]["name"],
                                               "arguments": json.dumps(args)}}]
        finish = "tool_calls"
    else:
        user = body["messages"][-1]["content"]
        first = re.search(r"^- (.+)$", user, re.M)
        message["content"] = first.group(1) if first else ""
        finish = "stop"
    reply = {"id": "dry", "model": body["model"],
             "choices": [{"index": 0, "message": message, "finish_reason": finish}],
             "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
    return _Reply(json.dumps(reply).encode("utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _argv(argv: list[str]):
    old = sys.argv
    sys.argv = argv
    try:
        yield
    finally:
        sys.argv = old


@contextlib.contextmanager
def _dummy_key():
    """A placeholder Anthropic key while the originals check one is set.

    The shim never sends it. A real key already in the environment is left
    alone, and is not sent either.
    """
    set_here = not os.environ.get("ANTHROPIC_API_KEY")
    if set_here:
        os.environ["ANTHROPIC_API_KEY"] = DUMMY_KEY
    try:
        yield os.environ["ANTHROPIC_API_KEY"]
    finally:
        if set_here:
            os.environ.pop("ANTHROPIC_API_KEY", None)


def model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_") or "model"


def _tracked_files() -> set[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True,
                             timeout=60, check=True)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"cannot list tracked files to protect them ({e}). Refusing to write.")
    return {(REPO_ROOT / p).resolve() for p in out.stdout.decode().split("\0") if p}


def check_outputs(paths: list[Path], resume: bool, tracked: set[Path] | None = None) -> None:
    """Refuse a committed file, a Sonnet file, or (without --resume) any existing file."""
    tracked = _tracked_files() if tracked is None else tracked
    sonnet = {p.resolve() for p in SONNET_FILES.values()}
    for p in paths:
        r = p.resolve()
        if r in tracked or r in sonnet:
            raise SystemExit(f"refusing to write {p}: it is a committed file")
        if r.exists() and not resume:
            raise SystemExit(f"{p} exists. Pass --resume to continue it, or choose "
                             f"another --out-dir.")


def _git_head() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _source_hashes() -> dict[str, str]:
    return {name: _sha((EVALS_DIR / name).read_bytes()) for name in GENERATOR_SOURCES
            if (EVALS_DIR / name).exists()}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_model(base_url: str, model: str) -> tuple[str, dict | None]:
    """The model to request, and what the server says it serves.

    ``auto`` takes the single id ``/models`` lists. Called only by a real
    generate run, never by --dry-run.
    """
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=30) as r:
            listing = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        if model == "auto":
            raise SystemExit(f"--model auto needs {base_url}/models: {e}")
        return model, None
    ids = [row.get("id") for row in listing.get("data") or [] if row.get("id")]
    if model == "auto":
        if len(ids) != 1:
            raise SystemExit(f"--model auto needs exactly one served model, got {ids}")
        return ids[0], listing
    return model, listing


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------

def _load_tb_queries(max_items: int | None):
    from eval_toolbench import load_toolbench_corpus_and_queries
    corpus, queries, category_map = load_toolbench_corpus_and_queries(max_queries=max_items)
    return queries, category_map


def _tb_vocab(mod, queries, category_map):
    labels, tags = mod.gather_categories(queries, category_map)
    return labels, dict(zip(labels, tags))


def _infer_quiet(mod, queries, label_to_tag, cache):
    """The module's own infer_categories over a cache that holds every query.

    Used to parse stored replies with the module's own rules. Every query is
    in the cache, so no request is made, and the caller points CACHE_PATH at
    the null device so the module's save_cache writes nowhere.
    """
    labels = list(label_to_tag)
    res = mod.infer_categories(queries, labels, label_to_tag, "anthropic", "none",
                               DUMMY_KEY, None, cache)
    return res[0], res[1]


def run_metatool(target: str, out_path: Path, model: str, workers: int, resume: bool,
                 max_items: int | None) -> dict:
    """The original MetaTool generator's main(), with its output redirected."""
    if target == "tool_tags":
        import metatool_generate_tags as gen
        argv = ["metatool_generate_tags.py", "--model", model, "--output", str(out_path),
                "--workers", str(workers)]
        orig_load = gen.load_tools
        if max_items:
            gen.load_tools = lambda: orig_load()[:max_items]
        n_items = len(gen.load_tools())
    else:
        import metatool_generate_query_tags_top5 as gen
        argv = ["metatool_generate_query_tags_top5.py", "--model", model, "--output",
                str(out_path), "--workers", str(workers)]
        if max_items:
            argv += ["--max-queries", str(max_items)]
        orig_load = gen.load_queries
        n_all = len(gen.load_queries())
        n_items = min(n_all, max_items) if max_items else n_all
    if resume:
        argv.append("--resume")
    t0 = time.time()
    try:
        with _argv(argv):
            gen.main()
    finally:
        if target == "tool_tags":
            gen.load_tools = orig_load
    written = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    n_written = len(written)
    return {"n_items": n_items, "n_written": n_written, "n_missing": n_items - n_written,
            "elapsed_s": round(time.time() - t0, 1)}


def run_toolbench(target: str, out_path: Path, model: str, resume: bool,
                  max_items: int | None, api_key: str) -> dict:
    """The original ToolBench classifier's infer_categories, cache redirected."""
    mod = importlib.import_module(TB_MODULES[target])
    queries, category_map = _load_tb_queries(max_items)
    labels, label_to_tag = _tb_vocab(mod, queries, category_map)
    cache = json.loads(out_path.read_text(encoding="utf-8")) if (resume and out_path.exists()) else {}
    old = mod.CACHE_PATH
    mod.CACHE_PATH = out_path
    t0 = time.time()
    try:
        res = mod.infer_categories(queries, labels, label_to_tag, "anthropic", model,
                                   api_key, None, cache)
    finally:
        mod.CACHE_PATH = old
    inferred = res[0]
    rows = []
    for q, inf in zip(queries, inferred):
        raw = cache[q[0]]
        if target == "toolbench_top1":
            tags, n_oov = ([inf] if inf else []), (0 if inf else 1)
        else:
            tags, n_oov = mod._parse_multitag_response(raw, label_to_tag)
        rows.append({"query": q[0], "split": q[3] if len(q) > 3 else None,
                     "gold_tags": list(q[1]), "inferred_tags": tags, "n_oov": n_oov, "raw": raw})
    parsed_path = out_path.with_name(out_path.stem + "_parsed.json")
    parsed_path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    if target == "toolbench_top1":
        acc = mod.classifier_accuracy(queries, inferred)
        summary = {"top1_accuracy_vs_gold": acc}
    else:
        contains, size = mod.classifier_setlevel_accuracy(queries, inferred)
        summary = {"contains_gold_primary": contains, "mean_set_size": size}
    print(f"  {target}: {summary}")
    return {"n_items": len(queries), "n_written": len(cache), "n_new_calls": res[1],
            "n_oov_items": sum(1 for r in rows if r["n_oov"]),
            "vocabulary_size": len(labels), "parsed_file": parsed_path.name,
            "elapsed_s": round(time.time() - t0, 1), **summary}


def dry_run(targets: list[str], model: str, extra: dict, max_items: int | None) -> None:
    """Count the items and show one translated request per target. Sends nothing."""
    shim = AnthropicToOpenAIShim(DEFAULT_BASE_URL, extra, transport=canned_transport)
    with shim, _dummy_key() as key:
        for target in targets:
            shim.target = target
            if target == "tool_tags":
                import metatool_generate_tags as gen
                import metatool_tagging as mt
                items = gen.load_tools()
                mt.generate_tool_tags(items[0]["name"], items[0]["description"], model, key)
            elif target == "query_tags_top5":
                import metatool_generate_query_tags_top5 as gen
                import metatool_tagging as mt
                items = gen.load_queries()
                mt.generate_query_tags(items[0]["query"], model, key, k=5)
            else:
                mod = importlib.import_module(TB_MODULES[target])
                items, category_map = _load_tb_queries(None)
                labels, _ = _tb_vocab(mod, items, category_map)
                mod.classify_query(items[0][0], labels, "anthropic", model, key, None)
            n = min(len(items), max_items) if max_items else len(items)
            _, translated = shim.last_payloads[target]
            print(f"\n=== {target}: {n} items, one request each ===")
            print(json.dumps(translated, indent=1, ensure_ascii=False)[:6000])
    print(f"\nNothing was sent. Client extras: {extra}")


def generate(args) -> None:
    extra = {} if args.thinking else {"chat_template_kwargs": {"enable_thinking": False}}
    targets = args.only or list(TARGETS)
    if args.dry_run:
        dry_run(targets, args.model if args.model != "auto" else "<auto>", extra,
                args.max_items)
        return
    model, served = resolve_model(args.base_url, args.model)
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_ROOT / model_slug(model)
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = {t: out_dir / OUT_NAMES[t] for t in targets}
    extra_files = [out_dir / (OUT_NAMES[t].replace(".json", "_parsed.json"))
                   for t in targets if t in TB_MODULES]
    check_outputs(list(outs.values()), args.resume)
    check_outputs(extra_files + [out_dir / "manifest.json", out_dir / "requests.jsonl"],
                  resume=True)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) \
        if manifest_path.exists() else {"runs": []}
    run = {"started_utc": _now(), "model": model, "base_url": args.base_url,
           "client_extras": extra, "served_models_listing": served,
           "targets": targets, "max_items": args.max_items, "workers": args.workers,
           "resume": args.resume, "artifacts_git_head": _git_head(),
           "generator_source_sha256": _source_hashes(), "results": {}}
    shim = AnthropicToOpenAIShim(args.base_url, extra, log_path=out_dir / "requests.jsonl")
    try:
        with shim, _dummy_key() as key:
            for target in targets:
                shim.target = target
                before = Counter(shim.stats)
                print(f"\n=== {target} -> {outs[target]} ===")
                # One target failing (for example the top-1 parser's IndexError on
                # an empty reply) is recorded, and the others still run. Its
                # partial output stays on disk for --resume.
                try:
                    if target in TB_MODULES:
                        res = run_toolbench(target, outs[target], model, args.resume,
                                            args.max_items, key)
                    else:
                        res = run_metatool(target, outs[target], model, args.workers,
                                           args.resume, args.max_items)
                except Exception as e:  # noqa: BLE001
                    res = {"error": f"{type(e).__name__}: {e}"}
                    print(f"  {target} FAILED: {res['error']}")
                res["shim_counts"] = dict(Counter(shim.stats) - before)
                if outs[target].exists():
                    res["sha256_output"] = _sha(outs[target].read_bytes())
                run["results"][target] = res
    finally:
        run["finished_utc"] = _now()
        run["shim_totals"] = dict(shim.stats)
        run["served_models_in_replies"] = dict(shim.served_models)
        run["system_prompts"] = {h: t for h, t in shim.system_prompts.items()}
        run["tool_schemas"] = shim.tool_schemas
        run["request_shapes"] = shim.request_shapes
        manifest["runs"].append(run)
        manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                                 encoding="utf-8")
    print(f"\nWrote {out_dir}")


# ---------------------------------------------------------------------------
# compare: model-free agreement
# ---------------------------------------------------------------------------

def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def _ci(values) -> dict:
    from stat_utils import bootstrap_ci
    ci = bootstrap_ci(values)
    return {"mean": ci["point_estimate"], "ci": [ci["ci_lower"], ci["ci_upper"]], "n": ci["n"]}


def _kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if not n:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _first_by_query(entries: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in entries:
        out.setdefault(e["query"], e)
    return out


def compare_tool_tags(s: dict, r: dict) -> dict:
    names = sorted(set(s) & set(r))
    exact = [float(set(s[n]) == set(r[n])) for n in names]
    jac = [_jaccard(s[n], r[n]) for n in names]
    first = [float(s[n][0] == r[n][0]) for n in names if s[n] and r[n]]
    return {"n_both": len(names), "n_sonnet": len(s), "n_regen": len(r),
            "exact_set_agreement": _ci(exact), "jaccard": _ci(jac),
            "first_tag_agreement": _ci(first),
            "first_tag_kappa": _kappa([s[n][0] for n in names], [r[n][0] for n in names]),
            "mean_tags": {"sonnet": sum(len(s[n]) for n in names) / max(len(names), 1),
                          "regen": sum(len(r[n]) for n in names) / max(len(names), 1)},
            "per_item": {"names": names, "exact": exact, "jaccard": jac}}


def compare_query_tags(s_entries: list, r_entries: list, tool_s: dict, tool_r: dict | None) -> dict:
    from stat_utils import mcnemar, paired_bootstrap
    s, r = _first_by_query(s_entries), _first_by_query(r_entries)
    qs = [q for q in s if q in r]
    first = [float(s[q]["context_tags"][:1] == r[q]["context_tags"][:1]) for q in qs]
    jac = [_jaccard(s[q]["context_tags"], r[q]["context_tags"]) for q in qs]
    out = {"n_both": len(qs), "n_sonnet": len(s), "n_regen": len(r),
           "first_tag_agreement": _ci(first), "jaccard": _ci(jac),
           "mean_tags": {"sonnet": sum(len(s[q]["context_tags"]) for q in qs) / max(len(qs), 1),
                         "regen": sum(len(r[q]["context_tags"]) for q in qs) / max(len(qs), 1)}}

    # Gate-pass ceiling: the fraction of a query's tools whose required tags
    # (all of the tool's tags) are inside the query's tags. Recall cannot
    # exceed it under the gate. Model-free, one value per query.
    def ceiling(tool_tags: dict, entry: dict) -> float:
        ctx = set(entry["context_tags"])
        tools = entry["tools"]
        ok = [t for t in tools if t in tool_tags and set(tool_tags[t]) <= ctx]
        return len(ok) / len(tools) if tools else 0.0

    combos = {"sonnet_tools_sonnet_queries": (tool_s, s)}
    combos["sonnet_tools_regen_queries"] = (tool_s, r)
    if tool_r:
        combos["regen_tools_sonnet_queries"] = (tool_r, s)
        combos["regen_tools_regen_queries"] = (tool_r, r)
    per = {k: [ceiling(tt, src[q]) for q in qs] for k, (tt, src) in combos.items()}
    out["gate_pass_ceiling"] = {k: _ci(v) for k, v in per.items()}
    ref = per["sonnet_tools_sonnet_queries"]
    for k, v in per.items():
        if k == "sonnet_tools_sonnet_queries":
            continue
        pb = paired_bootstrap(v, ref)
        mc = mcnemar([int(x == 1.0) for x in v], [int(x == 1.0) for x in ref])
        out["gate_pass_ceiling"][k]["vs_sonnet_sonnet"] = {
            "delta": pb["delta"], "ci": [pb["ci_lower"], pb["ci_upper"]],
            "p_bootstrap": pb["p_value"], "mcnemar_all_pass": mc}
    out["per_item"] = {"queries": qs, "first": first, "jaccard": jac, "ceiling": per}
    return out


def compare_toolbench(target: str, sonnet_cache: dict, regen_cache: dict) -> dict:
    from stat_utils import mcnemar
    mod = importlib.import_module(TB_MODULES[target])
    queries, category_map = _load_tb_queries(None)
    labels, label_to_tag = _tb_vocab(mod, queries, category_map)
    both = [q for q in queries if q[0] in sonnet_cache and q[0] in regen_cache]
    parsed = {}
    old = mod.CACHE_PATH
    mod.CACHE_PATH = Path(os.devnull)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for who, cache in (("sonnet", sonnet_cache), ("regen", regen_cache)):
                parsed[who] = _infer_quiet(mod, both, label_to_tag,
                                           {q[0]: cache[q[0]] for q in both})[0]
    finally:
        mod.CACHE_PATH = old
    gold = [q[1][0] if q[1] else "" for q in both]
    out = {"n_both": len(both), "vocabulary_size": len(labels)}
    if target == "toolbench_top1":
        hit = {w: [int(t == g) for t, g in zip(parsed[w], gold)] for w in parsed}
        for w in parsed:
            assert abs(sum(hit[w]) / max(len(both), 1)
                       - mod.classifier_accuracy(both, parsed[w])) < 1e-12
            out[f"accuracy_vs_gold_{w}"] = _ci(hit[w])
            out[f"oov_{w}"] = sum(1 for t in parsed[w] if not t)
        out["tagger_agreement"] = _ci([float(a == b) for a, b in zip(parsed["sonnet"], parsed["regen"])])
        out["mcnemar_regen_vs_sonnet"] = mcnemar(hit["regen"], hit["sonnet"])
    else:
        hit = {w: [int(g in t) for t, g in zip(parsed[w], gold)] for w in parsed}
        for w in parsed:
            contains, size = mod.classifier_setlevel_accuracy(both, parsed[w])
            assert abs(sum(hit[w]) / max(len(both), 1) - contains) < 1e-12
            out[f"contains_gold_primary_{w}"] = _ci(hit[w])
            out[f"mean_set_size_{w}"] = size
        out["jaccard_between_taggers"] = _ci([_jaccard(a, b) for a, b in
                                              zip(parsed["sonnet"], parsed["regen"])])
        out["mcnemar_regen_vs_sonnet"] = mcnemar(hit["regen"], hit["sonnet"])
    out["per_item"] = {"queries": [q[0] for q in both], "gold": gold,
                       "sonnet": parsed["sonnet"], "regen": parsed["regen"]}
    return out


def compare(args) -> None:
    regen = Path(args.regen_dir)
    report: dict = {"regen_dir": str(regen), "created_utc": _now(), "targets": {}}
    # compare reads files only. The deny-all shim makes sure of it.
    with AnthropicToOpenAIShim(DEFAULT_BASE_URL, transport=deny_all):
        tool_s = json.loads(SONNET_FILES["tool_tags"].read_text(encoding="utf-8"))
        tool_r = None
        if (regen / OUT_NAMES["tool_tags"]).exists():
            tool_r = json.loads((regen / OUT_NAMES["tool_tags"]).read_text(encoding="utf-8"))
            report["targets"]["tool_tags"] = compare_tool_tags(tool_s, tool_r)
        if (regen / OUT_NAMES["query_tags_top5"]).exists():
            report["targets"]["query_tags_top5"] = compare_query_tags(
                json.loads(SONNET_FILES["query_tags_top5"].read_text(encoding="utf-8")),
                json.loads((regen / OUT_NAMES["query_tags_top5"]).read_text(encoding="utf-8")),
                tool_s, tool_r)
        for target in TB_MODULES:
            path = regen / OUT_NAMES[target]
            if path.exists():
                report["targets"][target] = compare_toolbench(
                    target, json.loads(SONNET_FILES[target].read_text(encoding="utf-8")),
                    json.loads(path.read_text(encoding="utf-8")))
    out = Path(args.output) if args.output else regen / "compare.json"
    check_outputs([out], resume=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for t, res in report["targets"].items():
        brief = {}
        for k, v in res.items():
            if k == "per_item":
                continue
            if isinstance(v, dict) and "mean" in v:
                brief[k] = f"{v['mean']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]"
            elif not isinstance(v, dict):
                brief[k] = v
        print(f"{t}: {json.dumps(brief, default=str)}")
    print(f"Wrote {out}")


# ---------------------------------------------------------------------------
# evaluate: Recall@5 under both taggers
# ---------------------------------------------------------------------------

def _paired(a, b) -> dict:
    import numpy as np
    from scipy.stats import wilcoxon
    from stat_utils import paired_bootstrap
    a, b = np.asarray(a, float), np.asarray(b, float)
    pb = paired_bootstrap(a, b)
    diff = a - b
    sd = diff.std(ddof=1) if len(diff) > 1 else 0.0
    nz = diff[diff != 0]
    w = float(wilcoxon(nz).pvalue) if len(nz) >= 5 else None
    return {"delta": pb["delta"], "ci": [pb["ci_lower"], pb["ci_upper"]],
            "p_bootstrap": pb["p_value"], "p_wilcoxon": w,
            "cohens_d_paired": float(diff.mean() / sd) if sd > 0 else 0.0, "n": pb["n"]}


def evaluate(args) -> None:
    """Recall@5 and NDCG@5 under the Sonnet tags and the regenerated tags.

    Uses eval_toolbench's loaders, retriever and metric loop. Pairs are
    aligned by query text. CPU only unless --allow-gpu.
    """
    if not args.allow_gpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import numpy as np  # noqa: F401
    import eval_toolbench as et
    regen = Path(args.regen_dir)
    report: dict = {"regen_dir": str(regen), "backend": args.backend, "k": args.top_k,
                    "created_utc": _now(), "conditions": {}}

    def run(retriever, queries, use_tags=True):
        m = et.evaluate_retriever(retriever, queries, top_k=args.top_k, use_tags=use_tags)
        return {k: v.tolist() for k, v in m.items() if k in ("recall", "ndcg")}

    def summarise(name, arms: dict, pairs: list[tuple[str, str]], queries: list[str]):
        entry = {"n": len(queries), "arms": {}, "contrasts": {}, "queries": queries}
        for a, m in arms.items():
            entry["arms"][a] = {k: _ci(v) for k, v in m.items()}
            entry["arms"][a]["per_query"] = m
        for a, b in pairs:
            entry["contrasts"][f"{a}_vs_{b}"] = {k: _paired(arms[a][k], arms[b][k])
                                                 for k in ("recall", "ndcg")}
        report["conditions"][name] = entry
        r = {a: round(entry["arms"][a]["recall"]["mean"], 4) for a in arms}
        print(f"  {name}: Recall@{args.top_k} {r}")

    with AnthropicToOpenAIShim(DEFAULT_BASE_URL, transport=deny_all):
        # ToolBench, the three inferred-category conditions.
        tb_targets = [t for t in TB_MODULES if (regen / OUT_NAMES[t]).exists()]
        if tb_targets:
            # Every query is loaded, so the vocabulary matches generation. The
            # pairs are the queries both caches hold, capped by --max-queries.
            corpus, queries, category_map = et.load_toolbench_corpus_and_queries()
            r_gov = et.build_retriever(corpus, backend=args.backend, governance=True)
            r_nog = et.build_retriever(et.strip_governance(corpus), backend=args.backend,
                                       governance=False)
            for target in tb_targets:
                mod = importlib.import_module(TB_MODULES[target])
                s_cache = json.loads(SONNET_FILES[target].read_text(encoding="utf-8"))
                r_cache = json.loads((regen / OUT_NAMES[target]).read_text(encoding="utf-8"))
                both = [q for q in queries if q[0] in s_cache and q[0] in r_cache]
                if args.max_queries:
                    both = both[:args.max_queries]
                if len(both) < 2:
                    print(f"  ToolBench {target}: {len(both)} paired queries, skipped")
                    continue
                labels, label_to_tag = _tb_vocab(mod, queries, category_map)
                tags = {}
                old = mod.CACHE_PATH
                mod.CACHE_PATH = Path(os.devnull)
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        for who, cache in (("sonnet", s_cache), ("regen", r_cache)):
                            got = _infer_quiet(mod, both, label_to_tag,
                                               {q[0]: cache[q[0]] for q in both})[0]
                            tags[who] = [([t] if t else []) if isinstance(t, str) else t
                                         for t in got]
                finally:
                    mod.CACHE_PATH = old
                arms = {"oracle": run(r_gov, both)}
                for who in ("sonnet", "regen"):
                    arms[who] = run(r_gov, [(q[0], tg, q[2]) for q, tg in zip(both, tags[who])])
                arms["no_gov"] = run(r_nog, both, use_tags=False)
                summarise(f"ToolBench {target}", arms,
                          [("regen", "sonnet"), ("sonnet", "no_gov"), ("regen", "no_gov")],
                          [q[0] for q in both])

        # MetaTool+Tags: tool tags from one tagger, query tags from its target tools.
        r_tool = regen / OUT_NAMES["tool_tags"]
        if r_tool.exists():
            arms, qtexts = {}, None
            for who, path in (("sonnet", SONNET_FILES["tool_tags"]), ("regen", r_tool)):
                corpus_t, _ = et.load_metatool_corpus_tagged(path)
                qs = et.load_metatool_queries_tagged(path, max_queries=args.max_queries)
                arms[who] = run(et.build_retriever(corpus_t, backend=args.backend,
                                                   governance=True), qs)
                qtexts = [q[0] for q in qs]
            summarise("MetaTool+Tags", arms, [("regen", "sonnet")], qtexts)

        # MetaTool+QueryTags-top5: tool and query tags from one tagger, aligned by query.
        r_q = regen / OUT_NAMES["query_tags_top5"]
        common: list[str] = []
        if r_q.exists():
            sq = et.load_metatool_queries_from_query_tags(SONNET_FILES["query_tags_top5"])
            rq = et.load_metatool_queries_from_query_tags(r_q)
            s_by, r_by = {}, {}
            for q in sq:
                s_by.setdefault(q[0], q)
            for q in rq:
                r_by.setdefault(q[0], q)
            common = [t for t in s_by if t in r_by]
            if args.max_queries and len(common) > args.max_queries:
                common = common[:args.max_queries]
        if r_q.exists() and len(common) >= 2:
            arms = {}
            tool_paths = {"sonnet": SONNET_FILES["tool_tags"],
                          "regen": r_tool if r_tool.exists() else SONNET_FILES["tool_tags"]}
            for who, by in (("sonnet", s_by), ("regen", r_by)):
                corpus_t, _ = et.load_metatool_corpus_tagged(tool_paths[who])
                arms[who] = run(et.build_retriever(corpus_t, backend=args.backend,
                                                   governance=True), [by[t] for t in common])
            report["conditions_note"] = (
                "MetaTool+QueryTags-top5 uses regenerated tool tags for the regen arm "
                "only if plugin_tags.json was regenerated, else the Sonnet tool tags.")
            summarise("MetaTool+QueryTags-top5", arms, [("regen", "sonnet")], common)

    out = Path(args.output) if args.output else regen / f"evaluate_{args.backend}.json"
    check_outputs([out], resume=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"Wrote {out}")
    try:
        from repro_footer import print_repro_footer
        print_repro_footer(extra={"eval": "authorship_evaluate", "backend": args.backend})
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write the tags with the second model")
    g.add_argument("--base-url", default=DEFAULT_BASE_URL)
    g.add_argument("--model", default="auto",
                   help="Model id to request. 'auto' takes the one id /models lists.")
    g.add_argument("--only", nargs="+", choices=TARGETS, default=None)
    g.add_argument("--out-dir", default=None,
                   help="Default evals/data/authorship/<model-slug>/.")
    g.add_argument("--workers", type=int, default=8,
                   help="Concurrent requests for the MetaTool generators (their default).")
    g.add_argument("--max-items", type=int, default=None,
                   help="Smoke runs. First N tools, N sampled MetaTool queries "
                        "(the generator's own seeded shuffle), N sampled ToolBench queries.")
    g.add_argument("--resume", action="store_true")
    g.add_argument("--thinking", action="store_true",
                   help="Leave the model's thinking on (default off, as Sonnet ran).")
    g.add_argument("--dry-run", action="store_true",
                   help="Count items and print one translated request each. Sends nothing.")

    c = sub.add_parser("compare", help="model-free agreement with the Sonnet files")
    c.add_argument("--regen-dir", required=True)
    c.add_argument("--output", default=None)

    e = sub.add_parser("evaluate", help="Recall@5 under both taggers")
    e.add_argument("--regen-dir", required=True)
    e.add_argument("--backend", default="bge", choices=["bge", "bm25", "hash"])
    e.add_argument("--top-k", type=int, default=5)
    e.add_argument("--max-queries", type=int, default=None)
    e.add_argument("--allow-gpu", action="store_true")
    e.add_argument("--output", default=None)
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    {"generate": generate, "compare": compare, "evaluate": evaluate}[args.cmd](args)


if __name__ == "__main__":
    main()
