"""Rerun Table 7 (tab:e2e) rows with the executor on BEAR 0.4.2's top-5 lists.

Prepared on 2026-10-30 for the coordinator. Not started: the executor needs the
GPU. run_e2e_rerun.sh is the entry point. It runs one executor at a time and
checks the card first.

What is kept from the published run (evals/eval_toolbench_e2e.py at bcc0343,
results/e2e_v0110_guided.log):
  - the scoring code: evaluate_e2e() itself, unchanged since that commit
  - the corpus and queries: load_toolbench_data(), also unchanged
  - the request: system prompt and tool list built by call_llm_with_tools(),
    OpenAI chat completions, response_format json_schema with an enum of the
    candidate names, temperature 0, max_tokens 100 (HEAD's default is 2048,
    so it is passed explicitly), no seed, no top_p or top_k
  - the model: Ollama mistral-nemo Q4_0, model layer sha256:b559938ab7a0

What changes:
  - the top-5 list per query, read from the 0.4.2 list files
    (dump_toolbench_lists.py --mode e2e), replayed in order. For BM25 and
    hash the script first rebuilds the 0.4.2 retriever and checks that it
    returns the same lists (--verify-live).
  - the Ollama build (0.40.13 now, unknown in July) and, unless the server is
    set to 32768, the context window. Hence the BGE control rows.

Per row it writes, under --out:
  <slug>.jsonl         one line per query: prompt sha256, candidates, the raw
                       reply, the chosen tool, exact and tool scores
  <slug>.scores.json   the arrays in the published toolbench_e2e_scores.json
                       layout, plus the summary with bootstrap CIs
  <slug>.done          written last, so a rerun skips finished rows
At the end, rerun_summary.json compares every row with the published arrays
(queries that changed, McNemar) and gives the governed vs ungated tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import eval_toolbench_e2e as e2e  # noqa: E402
import wp0_common  # noqa: E402

ROWS = {  # condition name -> (backend, governance, list file)
    "BEAR+BM25 (gov)": ("bm25", True, "bear_bm25_gov.json"),
    "BM25 (no gov)": ("bm25", False, "bm25_no_gov.json"),
    "BEAR+BGE-M3 (gov)": ("bge-m3", True, "bear_bge_m3_gov.json"),
    "BEAR+BGE (gov)": ("bge", True, "bear_bge_gov.json"),
    "BGE (no gov)": ("bge", False, "bge_no_gov.json"),
    "BEAR+Hash (gov)": ("hash", True, "bear_hash_gov.json"),
    # The rows the November rerun left to the July run (plan evals/e2e_rerun/PLAN.md, part 1).
    "BGE-M3 (no gov)": ("bge-m3", False, "bge_m3_no_gov.json"),
    "BEAR+Qwen3-0.6B (gov)": ("qwen3-0.6b", True, "bear_qwen3_0_6b_gov.json"),
    "Qwen3-0.6B (no gov)": ("qwen3-0.6b", False, "qwen3_0_6b_no_gov.json"),
    "BEAR+Qwen3-4B (gov)": ("qwen3-4b", True, "bear_qwen3_4b_gov.json"),
    "Qwen3-4B (no gov)": ("qwen3-4b", False, "qwen3_4b_no_gov.json"),
}
NVSMI = "/mnt/c/Windows/System32/nvidia-smi.exe"


def slug(name: str) -> str:
    return name.lower().replace("+", "_").replace(" ", "_").replace("(", "").replace(")", "")


# ---------------------------------------------------------------------------
# Server and card checks
# ---------------------------------------------------------------------------

def win_gpu_used_mib() -> int:
    out = subprocess.run([NVSMI, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    return int(out.splitlines()[0].split(",")[0].strip())


def http(url: str, body: dict | None = None, timeout: int = 30) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ollama_root(base_url: str) -> str:
    return base_url.rstrip("/").removesuffix("/v1")


def server_facts(base_url: str, model: str) -> dict:
    root = ollama_root(base_url)
    tags = http(f"{root}/api/tags")["models"]
    m = next((x for x in tags if same_model(x["name"], model) or same_model(x["model"], model)), None)
    if m is None:
        raise SystemExit(f"{model} is not in {root}/api/tags")
    show = http(f"{root}/api/show", {"model": model})
    return {"ollama_version": http(f"{root}/api/version").get("version"),
            "model": model, "digest": m["digest"], "details": m.get("details"),
            "size": m.get("size"), "modified_at": m.get("modified_at"),
            "parameters": show.get("parameters"), "template_sha256":
                hashlib.sha256((show.get("template") or "").encode()).hexdigest(),
            "model_info_arch": (show.get("model_info") or {}).get("general.architecture")}


def ollama_models_dir() -> Path:
    """The directory holding Ollama's manifests/ and blobs/.

    OLLAMA_MODELS wins when set (as for Ollama itself), as a Windows path
    (C:\\...) or a WSL path. Otherwise the Windows profile's .ollama\\models,
    found through %USERPROFILE% and wslpath, since the Windows Ollama keeps
    its models under the Windows profile, not under WSL's $HOME. Outside WSL
    the default is ~/.ollama/models.
    """
    def to_wsl(p: str) -> str:
        if re.match(r"^[A-Za-z]:[\\/]", p):
            return subprocess.run(["wslpath", "-u", p], capture_output=True, text=True,
                                  check=True).stdout.strip()
        return p
    env = os.environ.get("OLLAMA_MODELS", "").strip()
    if env:
        return Path(to_wsl(env)).expanduser()
    try:
        prof = subprocess.run(["cmd.exe", "/c", "echo %USERPROFILE%"], capture_output=True, text=True,
                              cwd="/mnt/c", timeout=30).stdout.strip().splitlines()[-1].strip()
        if prof and "%" not in prof:
            return Path(to_wsl(prof + "\\.ollama\\models"))
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return Path.home() / ".ollama" / "models"


def same_model(name: str, model: str) -> bool:
    """Ollama lists "mistral-nemo-32k:latest" for a request naming "mistral-nemo-32k"."""
    return name == model or (":" not in model and name == f"{model}:latest")


def loaded(base_url: str) -> list[dict]:
    return http(f"{ollama_root(base_url)}/api/ps").get("models", [])


def gate(limit: int, when: str) -> int:
    """Card limits agreed with model-server (2026-10-30), Windows nvidia-smi
    MiB, "at most": 67,000 before loading with nothing of ours resident, and
    81,000 before each row with our model resident. Over the limit: exit 75
    (main's finally unloads our model first, if it is loaded)."""
    used = win_gpu_used_mib()
    print(f"### card check ({when}): Windows nvidia-smi shows {used} MiB used, limit {limit}", flush=True)
    if used > limit:
        print(f"### card above the limit ({when}), stopping", flush=True)
        sys.exit(75)
    return used


def warm_and_check(args) -> dict:
    """Load the model with a 1-token request, then check what Ollama loaded."""
    try:
        names = [m["name"] for m in loaded(args.base_url)]
    except Exception as exc:  # noqa: BLE001
        print(f"### cannot reach Ollama /api/ps at {ollama_root(args.base_url)} ({exc!r}); not started", flush=True)
        sys.exit(75)
    if any(same_model(n, args.model) for n in names):
        print(f"### {args.model} is already loaded; the start limit assumes nothing of ours is resident",
              flush=True)
        sys.exit(75)
    if names and not args.allow_other_models:
        print(f"### other Ollama models are loaded ({names}); not started", flush=True)
        sys.exit(75)
    t0 = time.time()
    http(f"{args.base_url.rstrip('/')}/chat/completions",
         {"model": args.model, "max_tokens": 1, "temperature": 0,
          "messages": [{"role": "user", "content": "hi"}]}, timeout=600)
    ps = next((m for m in loaded(args.base_url) if same_model(m["name"], args.model)), None)
    info = {"load_seconds": round(time.time() - t0, 1), "ps": ps, "win_used_mib_after_load": win_gpu_used_mib()}
    print(f"### loaded {args.model}: context_length {ps and ps.get('context_length')}, "
          f"size_vram {ps and ps.get('size_vram')}, card now {info['win_used_mib_after_load']} MiB", flush=True)
    if ps is None or (args.expect_ctx and ps.get("context_length") != args.expect_ctx):
        raise SystemExit(f"context window is {ps and ps.get('context_length')}, expected {args.expect_ctx}; "
                         "not run (the model is unloaded on exit)")
    return info


def unload(args) -> None:
    """Unload our model only, then confirm with /api/ps. WP7 stage 2 starts
    after this, so the confirmation goes to the log and to UNLOADED."""
    try:
        http(f"{ollama_root(args.base_url)}/api/generate", {"model": args.model, "keep_alive": 0}, timeout=120)
    except Exception as exc:  # noqa: BLE001
        print(f"### unload request for {args.model} failed: {exc!r}", flush=True)
    for _ in range(60):
        try:
            ps = loaded(args.base_url)
            if not any(same_model(m["name"], args.model) for m in ps):
                used = win_gpu_used_mib()
                utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                msg = (f"{utc} {args.model} unloaded; /api/ps lists {len(ps)} models "
                       f"{[m['name'] for m in ps]}; Windows nvidia-smi {used} MiB")
                print(f"### {msg}", flush=True)
                (Path(args.out) / "UNLOADED").write_text(msg + "\n")
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    print(f"### WARNING: {args.model} still listed by /api/ps two minutes after the unload request", flush=True)


# ---------------------------------------------------------------------------
# Replay of the 0.4.2 lists through the published evaluate_e2e
# ---------------------------------------------------------------------------

class Replay:
    """Stands in for the retriever: returns the saved top-5 list of query i."""

    def __init__(self, corpus, ids: list[list[str]], texts: list[str]):
        self.by_id = {inst.id: inst for inst in corpus}
        self.ids, self.texts, self.i = ids, texts, 0

    def retrieve(self, query, ctx, top_k=5):
        assert query == self.texts[self.i], f"query order differs at {self.i}"
        out = [self.by_id[x] for x in self.ids[self.i][:top_k]]
        self.i += 1
        return out


def verify_live(corpus, queries, backend: str, gov: bool, ids: list[list[str]]) -> int:
    corp = corpus if gov else e2e.strip_governance(corpus)
    r = e2e.build_retriever(corp, backend=backend, governance=gov, mandatory_tags=[])
    bad = 0
    for i, (q, tags, _exp, _api) in enumerate(queries):
        got = [x.id for x in r.retrieve(q, e2e.Context(tags=tags if gov else []), top_k=5)]
        bad += got != list(ids[i])
    return bad


def run_row(args, name: str, corpus, queries, outdir: Path, log) -> dict:
    backend, gov, fname = ROWS[name]
    lst = next((Path(d) / fname for d in args.lists if (Path(d) / fname).exists()), None)
    if lst is None:
        raise SystemExit(f"no list file {fname} in {args.lists}")
    L = json.loads(lst.read_text())
    assert len(L["ids"]) == L["n_queries"] >= len(queries), (len(L["ids"]), len(queries))
    n = len(queries)  # all 1,100 except in a smoke test
    ids = L["ids"][:n]
    if args.verify_live and backend in ("bm25", "hash"):
        bad = verify_live(corpus, queries, backend, gov, ids)
        print(f"### live 0.4.2 retrieval vs {lst}: {bad} queries differ", flush=True)
        if bad:
            raise SystemExit("the saved list does not match live retrieval; not run")
    corp = corpus if gov else e2e.strip_governance(corpus)
    rep = Replay(corp, ids, [q[0] for q in queries])
    jl = open(outdir / f"{slug(name)}.jsonl", "w", encoding="utf-8")
    orig = e2e.call_llm_with_tools
    orig_post = e2e._post_with_retry
    last = {}

    def post(req, *a, **k):  # keeps the server's token counts of the last call
        data = orig_post(req, *a, **k)
        last.clear()
        last.update(data.get("usage") or {})
        last["content"] = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        return data

    def call(query, tool_schemas, model, base_url, **kw):
        # The published request: temperature 0, max_tokens 100.
        names = [s.get("name", "") for s in tool_schemas if s.get("name")]
        tool_list = "\n".join(f"- {s['name']}: {(s.get('description') or '').strip()[:400]}"
                              for s in tool_schemas if s.get("name"))
        if args.dry_run:  # no server: pick the first candidate
            res = {"name": names[0], "arguments": "{}"} if names else None
        else:
            last.clear()
            res = orig(query, tool_schemas, model, base_url, temperature=0.0, max_tokens=100)
            # Ollama cuts a prompt longer than num_ctx without saying so.
            if last.get("prompt_tokens", 0) >= args.expect_ctx:
                raise SystemExit(f"query {rep.i - 1}: prompt_tokens {last['prompt_tokens']} reaches the "
                                 f"{args.expect_ctx} window, so Ollama truncated it")
        jl.write(json.dumps({"i": rep.i - 1, "prompt_sha256": hashlib.sha256(
            (tool_list + "\x00" + query).encode()).hexdigest(), "candidates": names,
            "chosen": res and res["name"], "raw": last.get("content"),
            "prompt_tokens": last.get("prompt_tokens"), "completion_tokens": last.get("completion_tokens")},
            ensure_ascii=False) + "\n")
        return res

    e2e.call_llm_with_tools = call
    e2e._post_with_retry = post
    try:
        t0 = time.time()
        res = e2e.evaluate_e2e(rep, queries, args.model, args.base_url, 5, use_tags=gov, condition_name=name)
        secs = time.time() - t0
    finally:
        e2e.call_llm_with_tools = orig
        e2e._post_with_retry = orig_post
        jl.close()
    for m in ("recall", "precision", "f1", "ndcg"):
        if f"_{m}_scores" in L:
            same = np.allclose(res[f"_{m}_scores"], np.asarray(L[f"_{m}_scores"][:n], float), atol=1e-12)
            assert same, f"{m} arrays differ from the list file: the replay is out of step"
    res["seconds"] = round(secs, 1)
    res["list_file"] = str(lst)
    log(f"{name}: exact {res['exact_accuracy']:.3f}, tool {res['tool_accuracy']:.3f}, "
        f"errors {res['llm_errors']}, {secs / 60:.1f} min")
    return res


def mcnemar(a: np.ndarray, b: np.ndarray) -> dict:
    n01 = int(np.sum((a == 0) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    n = n01 + n10
    if n == 0:
        return {"n01": 0, "n10": 0, "p": 1.0}
    from scipy.stats import binomtest
    return {"n01": n01, "n10": n10, "p": float(binomtest(min(n01, n10), n, 0.5).pvalue)}


def summarize(outdir: Path, pub_path: Path) -> dict:
    from scipy.stats import ttest_rel
    pub = {s["condition"]: s for s in json.loads(pub_path.read_text())["scores"]}
    rows = {}
    for f in sorted(outdir.glob("*.scores.json")):
        d = json.loads(f.read_text())
        rows[d["condition"]] = d
    out = {"rows": {}, "pairs": {}}
    for name, d in rows.items():
        r = {"exact": d["exact_accuracy"], "exact_ci": d["exact_ci"], "tool": d["tool_accuracy"],
             "tool_ci": d["tool_ci"], "llm_errors": d["llm_errors"]}
        p = pub.get(name)
        if p:
            for m in ("exact", "tool"):
                a, b = np.asarray(p[f"_{m}_scores"]), np.asarray(d[f"_{m}_scores"])
                r[f"published_{m}"] = float(a.mean())
                r[f"{m}_queries_changed_vs_published"] = int(np.sum(a != b))
                r[f"{m}_mcnemar_vs_published"] = mcnemar(a, b)
        out["rows"][name] = r
    for g, u in (("BEAR+BM25 (gov)", "BM25 (no gov)"), ("BEAR+BGE (gov)", "BGE (no gov)"),
                 ("BEAR+BGE-M3 (gov)", "BGE-M3 (no gov)"), ("BEAR+Qwen3-0.6B (gov)", "Qwen3-0.6B (no gov)"),
                 ("BEAR+Qwen3-4B (gov)", "Qwen3-4B (no gov)")):
        if g in rows and u in rows:
            pr = {}
            for m in ("tool", "exact"):
                a, b = np.asarray(rows[g][f"_{m}_scores"]), np.asarray(rows[u][f"_{m}_scores"])
                dd = a - b
                sd = dd.std(ddof=1)
                t = ttest_rel(a, b)
                pr[m] = {"delta": float(dd.mean()), "d": float(dd.mean() / sd) if sd else 0.0,
                         "t": float(t.statistic), "p": float(t.pvalue)}
            out["pairs"][f"{g} vs {u}"] = pr
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", nargs="+", required=True, choices=list(ROWS))
    ap.add_argument("--lists", nargs="+", required=True, help="folders holding the 0.4.2 e2e list files")
    ap.add_argument("--model", default="mistral-nemo-32k")
    ap.add_argument("--expect-digest", default="d79a1e80980f",
                    help="Ollama tag digest (12 hex) the run must see; mistral-nemo:latest is e7e06d107c6c")
    ap.add_argument("--expect-model-layer", default="b559938ab7a0",
                    help="sha256 prefix of the GGUF layer, the same for both tags")
    ap.add_argument("--expect-ctx", type=int, default=32768)
    # WSL runs with mirrored networking (2026-10-31): the LAN address does not
    # reach the Windows Ollama from inside WSL, 127.0.0.1 does.
    ap.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--win-gpu-max-mib", type=int, required=True,
                    help="before loading, with nothing of ours resident: start only if Windows "
                         "nvidia-smi shows at most this (agreed: 67000)")
    ap.add_argument("--win-gpu-row-max-mib", type=int, required=True,
                    help="after loading and before each row, with our model resident: go on only "
                         "if the card shows at most this, else unload and stop (agreed: 81000)")
    ap.add_argument("--allow-other-models", action="store_true")
    ap.add_argument("--verify-live", action="store_true")
    ap.add_argument("--keep-loaded", action="store_true", help="do not unload the model at the end")
    ap.add_argument("--published", default="evals/results/toolbench_e2e_scores.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-queries", type=int, default=0, help="smoke test only")
    ap.add_argument("--dry-run", action="store_true",
                    help="no server and no card: checks the replay, the lists and the outputs only")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    logf = open(outdir / "rerun.log", "a", encoding="utf-8")

    def log(msg):
        line = f"[{time.strftime('%F %T')}] {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    todo = [r for r in args.rows if not (outdir / f"{slug(r)}.done").exists()]
    if args.dry_run:
        corpus, queries = e2e.load_toolbench_data()
        queries = queries[:args.max_queries] if args.max_queries else queries
        for name in args.rows:
            run_row(args, name, corpus, queries, outdir, log)
        return
    if not todo:
        log("every requested row is done")
    else:
        gate(args.win_gpu_max_mib, "before loading")
        facts = server_facts(args.base_url, args.model)
        log(f"server: Ollama {facts['ollama_version']}, {args.model} digest {facts['digest'][:12]}, "
            f"{facts['details'] and facts['details'].get('quantization_level')}")
        if not facts["digest"].startswith(args.expect_digest):
            raise SystemExit(f"digest {facts['digest'][:12]} is not the expected {args.expect_digest}")
        # The GGUF must be the July one, so a manifest that cannot be read fails
        # the run (it used to skip the check silently).
        models_dir = ollama_models_dir()
        manifest = models_dir / "manifests/registry.ollama.ai/library" / \
            args.model.split(":")[0] / (args.model.split(":")[1] if ":" in args.model else "latest")
        if not manifest.is_file():
            raise SystemExit(f"Ollama manifest {manifest} not found, so the model layer cannot be checked. "
                             "Set OLLAMA_MODELS to the Ollama models directory (Windows or WSL path).")
        layers = [x["digest"] for x in json.loads(manifest.read_text())["layers"]]
        facts["manifest"] = str(manifest)
        facts["manifest_layers"] = layers
        if not any(x.startswith("sha256:" + args.expect_model_layer) for x in layers):
            raise SystemExit(f"model layer {args.expect_model_layer} not in {manifest}")
        corpus, queries = e2e.load_toolbench_data()
        if args.max_queries:
            queries = queries[:args.max_queries]
        try:
            load = warm_and_check(args)
            gate(args.win_gpu_row_max_mib, "after loading")
            for name in todo:
                gate(args.win_gpu_row_max_mib, f"before {name}")
                res = run_row(args, name, corpus, queries, outdir, log)
                res["_server"] = facts
                res["_load"] = load
                res["_request"] = {"endpoint": "/v1/chat/completions", "temperature": 0.0, "max_tokens": 100,
                                   "response_format": "json_schema strict, enum of candidate names",
                                   "seed": None, "top_p": None, "top_k": None}
                res["_provenance"] = wp0_common.provenance({"script": "evals/wp0_v040/e2e_rerun.py",
                                                            "max_queries": args.max_queries})
                (outdir / f"{slug(name)}.scores.json").write_text(
                    json.dumps(res, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))
                if not args.max_queries:
                    (outdir / f"{slug(name)}.done").write_text(time.strftime("%FT%T") + "\n")
        finally:
            if not args.keep_loaded:
                unload(args)
    if not args.max_queries:
        summ = summarize(outdir, Path(args.published))
        (outdir / "rerun_summary.json").write_text(json.dumps(summ, indent=1))
        log(json.dumps(summ["pairs"]))


if __name__ == "__main__":
    main()
