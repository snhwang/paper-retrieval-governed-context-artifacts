"""Run one long-context end-to-end part on a fixed-window Ollama tag, under guards, and record how
the model was served (evals/e2e_rerun/PLAN.md, "What each run records").

    python evals/e2e_rerun/run_guarded.py --model TAG --base BASE --expect-base-digest HEX
        --win-gpu-max-mib N --win-gpu-stop-mib N --out DIR [--seed N] -- COMMAND...

Before the command:
  - the base tag has the digest the plan names, and Ollama lists the fixed-window tag
  - the card is at or below the start limit and Ollama holds no model
  - one request of one token loads the tag, and Ollama reports the expected window
  - the card after the load is at or below the stop limit
Then COMMAND runs with this process's environment and working directory. Its output passes through.
After the command, whatever its exit code:
  - the tag is unloaded if Ollama still lists it, and the unload is confirmed
  - the part of the Ollama server log written since the start is searched for
    "truncating input prompt". Ollama cuts a prompt that is longer than the window without failing.
serving.json in DIR holds all of it: the Ollama version, both digests, the tag's parameters and
quantization, what Ollama loaded, the card readings, whether the server on port 8355 answered at the
start and at the end, the seed, the command, its exit code and the count of cut prompts.

Exit code: the command's own when it failed. Otherwise 3 if a prompt was cut or the tag is still
loaded, 75 if a guard stopped the run before the command, 2 if the window is not the expected one,
and 0 when all is well.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "wp0_v040"))
sys.path.insert(0, str(HERE.parent))

CUT_LINE = "truncating input prompt"


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ollama_log() -> Path | None:
    hits = sorted(Path("/mnt/c/Users").glob("*/AppData/Local/Ollama/server.log"))
    return hits[0] if hits else None


def chat_server(url: str) -> dict:
    """Whether the Qwen3.8 server answers, and which model it names. Never raises."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/models", timeout=5) as r:
            data = json.loads(r.read())
        return {"up": True, "models": [m.get("id") for m in data.get("data", [])]}
    except Exception as exc:  # noqa: BLE001
        return {"up": False, "error": type(exc).__name__}


def main() -> int:
    import e2e_rerun as rr
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="the fixed-window tag the command will call")
    ap.add_argument("--base", required=True, help="the tag it was made from")
    ap.add_argument("--expect-base-digest", required=True, help="digest (12 hex) the plan names for the base tag")
    ap.add_argument("--expect-ctx", type=int, default=131072)
    ap.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--chat-url", default="http://127.0.0.1:8355/v1", help="the Qwen3.8 server, recorded as up or down")
    ap.add_argument("--win-gpu-max-mib", type=int, required=True, help="start only at or below this")
    ap.add_argument("--win-gpu-stop-mib", type=int, required=True, help="do not run above this after the load")
    ap.add_argument("--seed", type=int, default=None, help="recorded only. The command sends it")
    ap.add_argument("--out", required=True)
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- COMMAND...")
    args = ap.parse_args()
    cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not cmd:
        ap.error("no command after --")
    args.allow_other_models = False  # warm_and_check of e2e_rerun.py reads it
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    res = {"utc_start": utc(), "model": args.model, "base": args.base, "expect_ctx": args.expect_ctx,
           "seed": args.seed, "command": cmd, "chat_server_at_start": chat_server(args.chat_url)}
    base = rr.server_facts(args.base_url, args.base)
    if not base["digest"].startswith(args.expect_base_digest):
        raise SystemExit(f"{args.base} has digest {base['digest'][:12]}, the plan names {args.expect_base_digest}. Not run.")
    tag = rr.server_facts(args.base_url, args.model)
    res.update(ollama_version=tag["ollama_version"], base_digest=base["digest"], tag_digest=tag["digest"],
               tag_parameters=tag["parameters"], details=tag["details"], template_sha256=tag["template_sha256"])
    print(f"### Ollama {tag['ollama_version']}, {args.base} {base['digest'][:12]}, {args.model} {tag['digest'][:12]}, "
          f"parameters {tag['parameters']!r}, the server on 8355 is {'up' if res['chat_server_at_start']['up'] else 'down'}",
          flush=True)

    log = ollama_log()
    log_start = log.stat().st_size if log else None
    card = {"before": rr.gate(args.win_gpu_max_mib, "before loading")}
    code, ran = 0, False

    def on_term(signum, _frame):  # the queue's time limit, or a cancel: still unload and write the record
        print(f"### signal {signum}: stopping the command and unloading", flush=True)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, on_term)
    try:
        info = rr.warm_and_check(args)  # exits 75 if anything is loaded, raises if the window is not expect_ctx
        res["load"] = info
        card["after_load"] = info["win_used_mib_after_load"]
        if card["after_load"] > args.win_gpu_stop_mib:
            print(f"### card at {card['after_load']} MiB, above the stop limit {args.win_gpu_stop_mib}. Not run.", flush=True)
            code = 75
        else:
            print(f"### running: {' '.join(cmd)}", flush=True)
            res["utc_command_start"] = utc()
            ran = True
            code = subprocess.run(cmd).returncode
            res["utc_command_end"] = utc()
            card["after_command"] = rr.win_gpu_used_mib()
            print(f"### the command ended with exit code {code}, card now {card['after_command']} MiB", flush=True)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if not isinstance(exc.code, int):
            print(f"### {exc.code}", flush=True)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # a second signal must not interrupt the unload
        # Unload our tag only, and only if Ollama lists it. A request for a tag that is not loaded could load it.
        try:
            ours = any(rr.same_model(m["name"], args.model) for m in rr.loaded(args.base_url))
        except Exception:  # noqa: BLE001
            ours = True
        if ours:
            rr.unload(args)
        try:
            left = [m["name"] for m in rr.loaded(args.base_url)]
        except Exception:  # noqa: BLE001
            left = ["unknown"]
        card["after_unload"] = rr.win_gpu_used_mib()
    still = left == ["unknown"] or any(rr.same_model(n, args.model) for n in left)
    res.update(card_mib=card, loaded_after=left, chat_server_at_end=chat_server(args.chat_url), command_ran=ran,
               command_exit_code=code if ran else None)

    cut = None
    if log and log_start is not None:
        try:
            with open(log, "rb") as f:
                f.seek(min(log_start, log.stat().st_size))
                cut = sum(1 for line in f.read().decode("utf-8", errors="replace").splitlines() if CUT_LINE in line)
        except OSError as exc:
            print(f"### cannot read {log}: {exc!r}", flush=True)
    res["ollama_log"] = str(log) if log else None
    res["cut_lines_since_start"] = cut
    if code == 0 and (cut or still):
        code = 3
    res["exit_code"] = code
    res["utc_end"] = utc()
    (out / "serving.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    line = (f"Ollama {res['ollama_version']}, {args.model} {tag['digest'][:12]} from {args.base} {base['digest'][:12]}, "
            f"window {args.expect_ctx}, seed {args.seed}, card {card.get('before')} to {card.get('after_load')} MiB, "
            f"8355 {'up' if res['chat_server_at_start']['up'] else 'down'} at the start and "
            f"{'up' if res['chat_server_at_end']['up'] else 'down'} at the end, cut prompts {cut}, "
            f"unloaded {not still}, exit {code}")
    (out / "serving.txt").write_text(line + "\n", encoding="utf-8")
    print("### " + line, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
