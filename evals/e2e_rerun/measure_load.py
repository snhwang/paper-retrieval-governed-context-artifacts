"""One guarded load of a fixed-window Ollama tag, before the long-context reruns are booked.

Part of evals/e2e_rerun/PLAN.md. No number of the paper comes from this script. It answers three
questions that the booking of the card depends on:
  1. How much of the card does the tag take once it is loaded with its window?
  2. How many tokens is the monolithic prompt for this model's own tokenizer?
  3. Does the server cut the prompt? (Ollama does that without failing. Only its log says so.)

What it does, in order:
  - checks that the base tag has the digest the plan names, and reads the fixed-window tag's digest
  - stops unless Ollama holds no model and the card is at or below the start limit
  - loads the tag with a one-token request and reads what Ollama loaded (context_length, size_vram)
  - stops, after unloading, if the window is not the expected one or the card is above the stop limit
  - sends the monolithic prompt of eval_toolbench_react.py with the longest query and one output token,
    and reads the server's own count (usage.prompt_tokens)
  - looks for "truncating input prompt" in the part of the Ollama log written since the start
  - unloads the tag, confirms it, and writes measure.json

Exit codes: 0 the prompt fits with the reserve and nothing was cut, 3 it does not fit or was cut,
75 a guard stopped the run before or after the load, 2 the window is not the expected one.

Usage (from the repo root, as reproduce/56_e2e_long_context.sh calls it):
    python evals/e2e_rerun/measure_load.py --model gemma4-12b-131k --base gemma4:12b \
        --expect-base-digest 4eb23ef187e2 --expect-ctx 131072 \
        --win-gpu-max-mib 79455 --win-gpu-stop-mib 94000 --out OUTDIR
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "wp0_v040"))

import e2e_rerun as rr  # noqa: E402  (card and server helpers)
import eval_toolbench_react as react  # noqa: E402

CUT_LINE = "truncating input prompt"


def ollama_log() -> Path | None:
    """The Windows Ollama's server.log, as a WSL path."""
    try:
        base = subprocess.run(["cmd.exe", "/c", "echo %LOCALAPPDATA%"], capture_output=True, text=True,
                              cwd="/mnt/c", timeout=30).stdout.strip().splitlines()[-1].strip()
        if base and "%" not in base:
            p = Path(subprocess.run(["wslpath", "-u", base + "\\Ollama\\server.log"], capture_output=True,
                                    text=True, check=True).stdout.strip())
            if p.exists():
                return p
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    for p in Path("/mnt/c/Users").glob("*/AppData/Local/Ollama/server.log"):
        return p
    return None


def prompt_messages(fmt: str) -> tuple[list[dict], dict]:
    """The monolithic prompt of eval_toolbench_react.py, character for character, with the longest query."""
    import tiktoken
    corpus, queries = react.load_toolbench_data()
    name_map: dict = {}
    react.build_id_to_function(corpus, name_map)
    schemas = react.build_monolithic_schemas(corpus, 0, name_map)
    tool_list = "\n".join(f"- {s['name']}: {(s.get('description') or '').strip()[:400]}"
                          for s in schemas if s.get("name"))
    system = (react.REACT_REASONING_SYSTEM_PROMPT if fmt == "native" else react.REACT_SYSTEM_PROMPT) \
        + "\nAvailable tools:\n" + tool_list
    longest = max((q[0] for q in queries), key=len)
    enc = tiktoken.get_encoding("cl100k_base")
    size = {"format": fmt, "n_tools": len([s for s in schemas if s.get("name")]),
            "chars": len(system) + len(longest), "cl100k": len(enc.encode(system)) + len(enc.encode(longest))}
    return [{"role": "system", "content": system}, {"role": "user", "content": longest}], size


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="the fixed-window tag to load")
    ap.add_argument("--base", required=True, help="the tag it was made from")
    ap.add_argument("--expect-base-digest", required=True, help="digest (12 hex) the plan names for the base tag")
    ap.add_argument("--expect-ctx", type=int, default=131072)
    ap.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--win-gpu-max-mib", type=int, required=True, help="start only at or below this")
    ap.add_argument("--win-gpu-stop-mib", type=int, required=True, help="unload and stop above this")
    ap.add_argument("--prompt", choices=["scaffold", "native"], default="native")
    ap.add_argument("--reserve-output", type=int, default=8192 + 512,
                    help="tokens the window must still hold after the prompt (the reasoning budget and a margin)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true", help="no server and no card: builds the prompt only")
    args = ap.parse_args()
    args.allow_other_models = False  # warm_and_check of e2e_rerun.py reads it
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    messages, size = prompt_messages(args.prompt)
    print(f"### prompt ({args.prompt}): {size['n_tools']} tools, {size['chars']} characters, {size['cl100k']} cl100k tokens",
          flush=True)
    if args.dry_run:
        print("### dry run: no server and no card", flush=True)
        return 0

    res = {"utc_start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model": args.model, "base": args.base,
           "expect_ctx": args.expect_ctx, "prompt": size}
    base = rr.server_facts(args.base_url, args.base)
    if not base["digest"].startswith(args.expect_base_digest):
        raise SystemExit(f"{args.base} has digest {base['digest'][:12]}, the plan names {args.expect_base_digest}. Not run.")
    tag = rr.server_facts(args.base_url, args.model)
    res.update(ollama_version=tag["ollama_version"], base_digest=base["digest"], tag_digest=tag["digest"],
               tag_parameters=tag["parameters"], details=tag["details"])
    print(f"### Ollama {tag['ollama_version']}, {args.base} {base['digest'][:12]}, {args.model} {tag['digest'][:12]}, "
          f"parameters {tag['parameters']!r}", flush=True)

    log = ollama_log()
    log_start = log.stat().st_size if log else None
    card = {"before": rr.gate(args.win_gpu_max_mib, "before loading")}
    code = 0
    try:
        info = rr.warm_and_check(args)  # exits 75 if anything is loaded, raises if the window is not expect_ctx
        res["load"] = info
        card["after_load"] = info["win_used_mib_after_load"]
        if card["after_load"] > args.win_gpu_stop_mib:
            print(f"### card at {card['after_load']} MiB, above the stop limit {args.win_gpu_stop_mib}", flush=True)
            code = 75
        else:
            t0 = time.time()
            data = rr.http(f"{args.base_url.rstrip('/')}/chat/completions",
                           {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 1},
                           timeout=3600)
            usage = data.get("usage") or {}
            res["prompt"]["prompt_tokens"] = usage.get("prompt_tokens")
            res["prompt"]["seconds"] = round(time.time() - t0, 1)
            card["after_prompt"] = rr.win_gpu_used_mib()
            print(f"### the server counts {usage.get('prompt_tokens')} prompt tokens "
                  f"({res['prompt']['seconds']} s), card now {card['after_prompt']} MiB", flush=True)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if not isinstance(exc.code, int):
            print(f"### {exc.code}", flush=True)
    finally:
        # Unload our tag only, and only if Ollama lists it. A request for a tag that is not loaded could load it.
        try:
            ours = any(rr.same_model(m["name"], args.model) for m in rr.loaded(args.base_url))
        except Exception:  # noqa: BLE001
            ours = True
        if ours:
            rr.unload(args)
        card["after_unload"] = rr.win_gpu_used_mib()
    res["card_mib"] = card

    cut = None
    if log and log_start is not None:
        try:
            with open(log, "rb") as f:
                f.seek(log_start)
                new = f.read().decode("utf-8", errors="replace")
            cut = sum(1 for line in new.splitlines() if CUT_LINE in line)
        except OSError as exc:
            print(f"### cannot read {log}: {exc!r}", flush=True)
    res["ollama_log"] = str(log) if log else None
    res["cut_lines_since_start"] = cut
    n = res["prompt"].get("prompt_tokens")
    if code == 0:
        res["window_left_after_prompt"] = None if n is None else args.expect_ctx - n
        fits = n is not None and args.expect_ctx - n >= args.reserve_output and not cut
        res["fits"] = bool(fits)
        code = 0 if fits else 3
    res["exit_code"] = code
    (out / "measure.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("model", "tag_digest", "card_mib", "prompt", "cut_lines_since_start",
                                          "exit_code") if k in res}, indent=1), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
