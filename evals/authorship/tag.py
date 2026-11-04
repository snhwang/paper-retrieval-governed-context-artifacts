#!/usr/bin/env python3
"""Authorship ablation, step 1: write the three tag sets again with a second model family.

Claude Sonnet 4.6 wrote the MetaTool tool tags (plugin_tags.json), the MetaTool
top-5 query tags (query_tags_top5.json) and the three inferred ToolBench
category sets (top-1, multi, top-5). This writes all five again with the local
Qwen3.8-27B behind SGLang's OpenAI-compatible endpoint (127.0.0.1:8355).

Only the client differs. The prompts, closed vocabularies, tool schemas,
parsing, retries, validation and failure rules are the original scripts' own
code, run unchanged (metatool_tagging.py, metatool_generate_tags.py,
metatool_generate_query_tags_top5.py, eval_toolbench_inferred_categories.py,
eval_toolbench_multitag_categories.py, eval_toolbench_top5_categories.py).
The translation is the wire-level shim of evals/authorship_regenerate.py: the
originals post Anthropic Messages requests with urllib, the shim turns each
into /v1/chat/completions on --base-url and turns the reply back. It follows
the vendor-shim pattern of paper-knowledge-flow's facts/make_questions.py
(_OPENAI, _OpenAIMessages, _OpenAIClient), moved down to the wire, because the
originals call urllib, not an SDK client. The Anthropic API is never called,
and no key leaves the process. This file adds what the ablation needs on top:

- one log line per call (calls.jsonl): target, item, the prompt hashes, the
  translated request's hash, the raw reply (text and tool-call arguments as
  sent), the served model id, finish reason, usage, latency, HTTP status, and
  the shim's parse outcome. validate.py adds the originals' validation outcome.
- the server's identity (get_server_info by allow-list, get_model_info,
  /v1/models) at the start and after every target. A changed model path,
  revision or version stops the run.
- a load check before the first request: SGLang's /get_load (or /metrics).
  A non-empty queue refuses to start, and so do running requests unless
  --share-server. The server's cache is never flushed.
- bounded concurrency: --workers (default 4) for the MetaTool generators,
  never above max_running_requests - 2 or 8. The ToolBench classifiers run one
  request at a time, as written.
- decoding: temperature 0 (the originals' own value, carried in the request),
  a fixed seed (--seed, default 20261104), and Qwen3's thinking off
  (chat_template_kwargs.enable_thinking = false). See evals/authorship/README.md.
- resume: the MetaTool generators keep their own --resume and periodic flush,
  and the ToolBench classifiers their per-query cache. --passes reruns the
  targets with items still missing, with --resume, so items that failed get
  their retries. A failed item stays out of the file, as in the originals.

Usage (WSL, the kit's venv, from a clone's root):
    python evals/authorship/tag.py generate --dry-run
    python evals/authorship/tag.py generate --base-url http://127.0.0.1:8355/v1 --out-dir DIR
    python evals/authorship/tag.py generate ... --only toolbench_top1 --max-items 20   (smoke)
Exit code 0 when every target finished, 1 when one failed or items are missing
after the last pass (the files stay, and validate.py counts them).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
REPO = EVALS.parent
for _p in (str(REPO), str(EVALS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import authorship_regenerate as ar  # noqa: E402

SEED = 20261104
HARD_MAX_CONCURRENCY = 8
# get_server_info is copied by an allow-list (as hermes/provenance.py does),
# so no key or token the server reports ever reaches a log.
SERVER_KEYS = ("version", "model_path", "served_model_name", "revision", "tokenizer_path",
               "quantization", "kv_cache_dtype", "context_length", "random_seed",
               "tool_call_parser", "reasoning_parser", "max_running_requests", "dtype",
               "tp_size", "chat_template", "sampling_defaults", "enable_cache_report")
GUARDED = ("version", "model_path", "revision", "served_model_name", "quantization")
ITEM_RX = (re.compile(r"^Tool name: (.*)$", re.M), re.compile(r"\nQuery: (.*?)\n\n", re.S))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def item_of(user_prompt: str) -> str:
    """The tool name or the query a user prompt is about (each original prompt names one)."""
    for rx in ITEM_RX:
        m = rx.search(user_prompt)
        if m:
            return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------

# The real urlopen, kept before any shim is installed: the server checks go to
# the server's root (/get_server_info, /get_load), which the shim refuses.
_REAL_URLOPEN = urllib.request.urlopen


def _get_json(url: str, timeout: float = 15.0):
    with _REAL_URLOPEN(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def server_info(root: str) -> dict:
    """What the server says it is. Called only in a real run."""
    out: dict = {"checked_utc": now()}
    try:
        info = _get_json(f"{root}/get_server_info")
        out["server_info"] = {k: info.get(k) for k in SERVER_KEYS if isinstance(info, dict) and k in info}
    except Exception as e:  # noqa: BLE001
        out["server_info_error"] = f"{type(e).__name__}: {e}"
    try:
        mi = _get_json(f"{root}/get_model_info")
        out["model_info"] = {k: mi.get(k) for k in ("model_path", "served_model_name", "weight_version",
                                                   "tool_call_parser", "reasoning_parser")
                             if isinstance(mi, dict) and k in mi}
    except Exception as e:  # noqa: BLE001
        out["model_info_error"] = f"{type(e).__name__}: {e}"
    try:
        models = _get_json(f"{root}/v1/models")
        out["v1_models"] = [{k: m.get(k) for k in ("id", "root", "max_model_len")}
                            for m in models.get("data") or []]
    except Exception as e:  # noqa: BLE001
        out["v1_models_error"] = f"{type(e).__name__}: {e}"
    return out


def guarded(info: dict) -> dict:
    s = info.get("server_info") or {}
    return {k: s.get(k) for k in GUARDED}


def parse_load(obj) -> dict | None:
    """Running and waiting requests from SGLang's /get_load, in its list or dict shape."""
    rows = obj if isinstance(obj, list) else [obj] if isinstance(obj, dict) else []
    running = waiting = 0
    seen = False
    for r in rows:
        if not isinstance(r, dict):
            continue
        for k in ("num_reqs", "num_running_reqs", "running"):
            if isinstance(r.get(k), (int, float)):
                running += int(r[k])
                seen = True
                break
        for k in ("num_waiting_reqs", "num_queue_reqs", "waiting"):
            if isinstance(r.get(k), (int, float)):
                waiting += int(r[k])
                seen = True
                break
    return {"running": running, "waiting": waiting} if seen else None


def parse_metrics(text: str) -> dict | None:
    """Running and waiting requests from Prometheus text (sglang:num_running_reqs, num_queue_reqs)."""
    vals: dict[str, float] = {}
    for ln in text.splitlines():
        m = re.match(r"^sglang:(num_running_reqs|num_queue_reqs)(\{[^}]*\})?\s+([0-9.eE+-]+)", ln)
        if m:
            vals[m.group(1)] = vals.get(m.group(1), 0.0) + float(m.group(3))
    if not vals:
        return None
    return {"running": int(vals.get("num_running_reqs", 0)), "waiting": int(vals.get("num_queue_reqs", 0))}


def server_load(root: str) -> dict:
    try:
        got = parse_load(_get_json(f"{root}/get_load"))
        if got is not None:
            return {**got, "source": "/get_load"}
    except Exception:  # noqa: BLE001
        pass
    try:
        with _REAL_URLOPEN(f"{root}/metrics", timeout=15) as r:
            got = parse_metrics(r.read().decode("utf-8", "replace"))
        if got is not None:
            return {**got, "source": "/metrics"}
    except Exception:  # noqa: BLE001
        pass
    return {"unknown": "neither /get_load nor /metrics gave running and waiting counts"}


def check_load(load: dict, share: bool, unknown_ok: bool) -> None:
    if "unknown" in load:
        if not unknown_ok:
            raise SystemExit(f"cannot read the server's queue ({load['unknown']}). Check it by hand, "
                             "then pass --load-unknown-ok.")
        return
    if load["waiting"] > 0:
        raise SystemExit(f"the server has {load['waiting']} queued request(s). Not starting.")
    if load["running"] > 0 and not share:
        raise SystemExit(f"the server is running {load['running']} request(s) for another client. "
                         "Not starting (pass --share-server to run beside it).")


def concurrency(requested: int, info: dict) -> int:
    mrr = (info.get("server_info") or {}).get("max_running_requests")
    cap = HARD_MAX_CONCURRENCY
    if isinstance(mrr, int) and mrr > 0:
        cap = min(cap, max(1, mrr - 2))   # room for other clients
    if requested > cap:
        raise SystemExit(f"--workers {requested} is above the cap {cap} (max_running_requests "
                         f"{mrr}, minus 2 for other clients, at most {HARD_MAX_CONCURRENCY}).")
    return max(1, requested)


# ---------------------------------------------------------------------------
# The shim, with one log line per call
# ---------------------------------------------------------------------------

class RecordingShim(ar.AnthropicToOpenAIShim):
    """authorship_regenerate's shim, plus a calls.jsonl line per call with the raw reply."""

    def __init__(self, base_url: str, extra: dict, call_log: Path | None, transport=None) -> None:
        super().__init__(base_url, extra, transport=transport, log_path=None)
        self.call_log = call_log
        self._n = 0

    def _write(self, rec: dict) -> None:
        if self.call_log is None:
            return
        with self._lock:
            with open(self.call_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _messages(self, req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        translated = ar.translate_request(payload, self.extra)
        self._record(payload, translated)   # stats and the prompt registry of the parent
        user = "\n".join(m["content"] for m in payload["messages"])
        tools = payload.get("tools") or []
        with self._lock:
            self._n += 1
            call = self._n
        rec = {"call": call, "target": self.target, "item": item_of(user), "utc": now(),
               "sha256_system": ar._sha(payload.get("system") or ""), "sha256_user": ar._sha(user),
               "sha256_tools": ar._sha(ar._canon(tools)) if tools else None,
               "sha256_request": ar._sha(ar._canon(translated)),
               "forced_tool": (payload.get("tool_choice") or {}).get("name"),
               "max_tokens": payload.get("max_tokens"), "temperature": payload.get("temperature")}
        out = urllib.request.Request(self.chat_url, data=json.dumps(translated).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.time()
        try:
            with self._transport(out, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            with self._lock:
                self.stats[f"http_{e.code}"] += 1
            rec.update(http_status=e.code, error=f"HTTP {e.code}", latency_s=round(time.time() - t0, 3),
                       shim_outcome="http_error")
            self._write(rec)
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            with self._lock:
                self.stats["transport_error"] += 1
            rec.update(error=f"{type(e).__name__}: {e}", latency_s=round(time.time() - t0, 3),
                       shim_outcome="transport_error")
            self._write(rec)
            raise
        reply, notes = ar.translate_response(data)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        has_tool = any(b["type"] == "tool_use" for b in reply["content"])
        if payload.get("tool_choice"):
            outcome = "tool_call" if has_tool else ("bad_tool_arguments" if notes.get("bad_tool_arguments")
                                                    else "no_tool_call")
        else:
            text = next((b["text"] for b in reply["content"] if b["type"] == "text"), "")
            outcome = "text" if text.strip() else "empty_text"
        rec.update(http_status=200, latency_s=round(time.time() - t0, 3), served_model=data.get("model"),
                   finish_reason=choice.get("finish_reason"), raw_content=msg.get("content"),
                   raw_tool_calls=[{"name": (c.get("function") or {}).get("name"),
                                    "arguments": (c.get("function") or {}).get("arguments")}
                                   for c in msg.get("tool_calls") or []],
                   reasoning_chars=len(msg.get("reasoning_content") or ""),
                   usage=data.get("usage"), translation_notes=notes, shim_outcome=outcome)
        with self._lock:
            self.stats["responses"] += 1
            for k, v in notes.items():
                self.stats[k] += v
            if payload.get("tool_choice") and not has_tool:
                self.stats["no_tool_call"] += 1
            if data.get("model"):
                self.served_models[data["model"]] += 1
        self._write(rec)
        return ar._Reply(json.dumps(reply).encode("utf-8"))


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

def client_extras(thinking: bool, seed: int) -> dict:
    extra: dict = {"seed": seed}
    if not thinking:
        extra["chat_template_kwargs"] = {"enable_thinking": False}
    return extra


def generate(args) -> int:
    extra = client_extras(args.thinking, args.seed)
    targets = args.only or list(ar.TARGETS)
    if args.dry_run:
        ar.dry_run(targets, "<model id from /v1/models>", extra, args.max_items)
        print(f"\nDry run. Workers {args.workers}, passes {args.passes}, seed {args.seed}, "
              f"thinking {'on' if args.thinking else 'off'}. Nothing was sent.")
        return 0
    if not args.out_dir:
        raise SystemExit("--out-dir is required for a real run")
    root = args.base_url.rstrip("/")
    root = root[:-3] if root.endswith("/v1") else root
    info0 = server_info(root)
    load0 = server_load(root)
    print(f"server: {json.dumps(guarded(info0))}, load {load0}")
    check_load(load0, args.share_server, args.load_unknown_ok)
    workers = concurrency(args.workers, info0)
    model, served = ar.resolve_model(args.base_url, args.model)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = {t: out_dir / ar.OUT_NAMES[t] for t in targets}
    ar.check_outputs(list(outs.values()), args.resume)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"runs": []}
    run = {"started_utc": now(), "model": model, "base_url": args.base_url, "client_extras": extra,
           "decoding": {"temperature": "0.0, from the originals' requests", "seed": args.seed,
                        "thinking": bool(args.thinking), "top_k": "not sent (SGLang rejects 0)"},
           "workers": workers, "passes": args.passes, "served_models_listing": served,
           "server_at_start": info0, "load_at_start": load0, "targets": targets,
           "max_items": args.max_items, "resume": args.resume, "artifacts_git_head": ar._git_head(),
           "generator_source_sha256": ar._source_hashes(), "results": {}, "server_after": {}}
    shim = RecordingShim(args.base_url, extra, out_dir / "calls.jsonl")
    failed = False
    try:
        with shim, ar._dummy_key() as key:
            todo = list(targets)
            for p in range(1, args.passes + 1):
                resume = args.resume or p > 1
                again = []
                for target in todo:
                    shim.target = target
                    before = Counter(shim.stats)
                    print(f"\n=== pass {p}: {target} -> {outs[target]} ===")
                    try:
                        if target in ar.TB_MODULES:
                            res = ar.run_toolbench(target, outs[target], model, resume, args.max_items, key)
                        else:
                            res = ar.run_metatool(target, outs[target], model, workers, resume, args.max_items)
                    except Exception as e:  # noqa: BLE001  recorded, the other targets still run
                        res = {"error": f"{type(e).__name__}: {e}"}
                        print(f"  {target} FAILED: {res['error']}")
                    res["shim_counts"] = dict(Counter(shim.stats) - before)
                    if outs[target].exists():
                        res["sha256_output"] = ar._sha(outs[target].read_bytes())
                    run["results"].setdefault(target, []).append({"pass": p, **res})
                    after = server_info(root)
                    run["server_after"][f"{target}/pass{p}"] = after
                    if guarded(after) != guarded(info0):
                        raise SystemExit(f"the server changed during {target}: {guarded(info0)} -> "
                                         f"{guarded(after)}. Stopping. The files so far stay for --resume.")
                    if res.get("error") or res.get("n_missing", 0) > 0:
                        again.append(target)
                todo = again
                if not todo:
                    break
            for target in todo:
                last = run["results"][target][-1]
                print(f"  {target}: still {last.get('n_missing', '?')} missing or failed after "
                      f"{args.passes} pass(es): {last.get('error', '')}")
                failed = True
    finally:
        run["finished_utc"] = now()
        run["shim_totals"] = dict(shim.stats)
        run["served_models_in_replies"] = dict(shim.served_models)
        run["system_prompts"] = dict(shim.system_prompts)
        run["tool_schemas"] = shim.tool_schemas
        run["request_shapes"] = shim.request_shapes
        manifest["runs"].append(run)
        manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_dir}. Calls: {shim.stats.get('requests', 0)}, served by {dict(shim.served_models)}")
    return 1 if failed else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--base-url", default="http://127.0.0.1:8355/v1")
    g.add_argument("--model", default="auto", help="model id. 'auto' takes the one id /v1/models lists")
    g.add_argument("--only", nargs="+", choices=ar.TARGETS, default=None)
    g.add_argument("--out-dir", default=None)
    g.add_argument("--workers", type=int, default=4, help="concurrent requests (MetaTool generators)")
    g.add_argument("--passes", type=int, default=3, help="passes over targets with missing items")
    g.add_argument("--seed", type=int, default=SEED)
    g.add_argument("--thinking", action="store_true", help="leave Qwen3's thinking on (default off)")
    g.add_argument("--max-items", type=int, default=None, help="smoke runs only")
    g.add_argument("--resume", action="store_true")
    g.add_argument("--share-server", action="store_true", help="start although other requests are running")
    g.add_argument("--load-unknown-ok", action="store_true", help="start although the queue cannot be read")
    g.add_argument("--dry-run", action="store_true", help="print one translated request per target, send nothing")
    a = p.parse_args(argv)
    return generate(a)


if __name__ == "__main__":
    sys.exit(main())
