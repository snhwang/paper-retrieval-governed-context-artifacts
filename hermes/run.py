#!/usr/bin/env python3
"""WP7 runner: Hermes harness cells under the BEAR arms, one at a time, with full provenance.

Run with the Python that has Hermes and BEAR installed (WSL ~/.venvs/tist-spike).

  run.py matrix --root DIR --arms A,B,C-gate,D --tasks T1,T2 --roles operator,guest \\
                --decoys 0,100 --backends nemotron --annotations off --reps 1 [--k 10] \\
                [--scope turn] [--query message] [--priority-weight 0] [--always-offer clarify]
  run.py smoke --root DIR [--task ambiguous_delete_ask]   the 16-cell smoke grid
  run.py dry --root DIR --arms ... (as matrix)            build each agent, no model call
  run.py registry                                         rewrite registry/harness_registry.json
  run.py provenance --root DIR                            write DIR/provenance.json
  run.py tasks                                            list task ids and sources

Each live cell:
1. writes the HERMES_HOME config for the cell (configs/<cell>.yaml) from arms.py,
2. POSTs /flush_cache to SGLang until it answers HTTP 200 (30 tries, 5 s apart), logging every
   attempt with its UTC time and status. A cell whose flush never succeeds is skipped,
3. runs worker_local.py in its own process with the cell's audit log,
4. appends a cell_done record (timings, return code, paths, provenance fingerprint).

Layout under --root: provenance.json, corpus/d<N>/, configs/, audit/, results/, logs/cells.jsonl,
logs/<cell>.stdout and .stderr.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import arms  # noqa: E402
import provenance  # noqa: E402

HERMES_TREE = os.environ.get("WP7_HERMES_TREE") or os.path.expanduser("~/src/hermes-agent")
HARNESS = os.path.join(HERMES_TREE, "evals", "core_tool_deferral")
WORKER = os.path.join(HERE, "worker", "worker_local.py")
PY = sys.executable
FLUSH_URL = "http://localhost:8355/flush_cache"
FLUSH_TRIES, FLUSH_WAIT_S = 30, 5.0
SMOKE_TASK = "ambiguous_delete_ask"


def _tasks_module():
    sys.path.insert(0, HARNESS)
    sys.path.insert(0, os.path.join(HERE, "worker"))
    os.environ.setdefault("WP7_HERMES_TREE", HERMES_TREE)
    import wp7_tasks
    return wp7_tasks


class Run:
    def __init__(self, root: str):
        self.root = os.path.abspath(os.path.expanduser(root))
        for sub in ("configs", "audit", "results", "logs", "corpus"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        self.log_path = os.path.join(self.root, "logs", "cells.jsonl")
        self._embedding_revision: str | None = None

    def log(self, rec: dict) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps(rec, default=str)[:400], flush=True)

    def embedding_revision(self) -> str:
        if self._embedding_revision is None:
            self._embedding_revision = provenance.embedder_revision()
        return self._embedding_revision

    def corpus_dir(self, decoys: int) -> str:
        """base/tools.yaml plus decoys-<N>.yaml, so the corpus names exactly the tools present."""
        d = os.path.join(self.root, "corpus", f"d{decoys}")
        if not os.path.isdir(d):
            os.makedirs(d)
            shutil.copy2(arms.BASE_CORPUS, os.path.join(d, "tools.yaml"))
            if decoys > 0:
                shutil.copy2(arms.DECOY_CORPUS.format(n=decoys), os.path.join(d, "decoys.yaml"))
        return d

    def write_provenance(self) -> dict:
        p = provenance.collect(HERE, HERMES_TREE)
        with open(os.path.join(self.root, "provenance.json"), "w", encoding="utf-8") as f:
            json.dump(p, f, indent=1, default=str)
        return p

    def flush(self, cell: str) -> bool:
        for attempt in range(1, FLUSH_TRIES + 1):
            ts = provenance.now()
            status, body = None, ""
            try:
                req = urllib.request.Request(FLUSH_URL, data=b"", method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    status, body = r.status, r.read(500).decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read(500).decode("utf-8", "replace")
            except Exception as e:
                body = f"{type(e).__name__}: {e}"
            self.log({"event": "flush_cache", "cell": cell, "attempt": attempt, "utc": ts,
                      "http_status": status, "body": body.strip()[:200]})
            if status == 200:
                return True
            time.sleep(FLUSH_WAIT_S)
        return False

    def prepare(self, arm: str, task: str, rep: int, sw: arms.Switches) -> tuple[str, str, str]:
        sw.validate(arm)
        cell = arms.cell_id(arm, task, rep, sw)
        audit = os.path.join(self.root, "audit", f"{cell}.jsonl")
        cfg = arms.hermes_config(arm, sw, corpus_dir=self.corpus_dir(sw.decoys), audit_path=audit,
                                 embedding_revision=self.embedding_revision())
        cfg_path = os.path.join(self.root, "configs", f"{cell}.yaml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(arms.render(cfg))
        return cell, cfg_path, audit

    def env(self, cfg_path: str, sw: arms.Switches, cell: str, dry: bool) -> dict:
        env = dict(os.environ)
        env.pop("OPENROUTER_API_KEY", None)
        env.update({
            "ABDEFER_BASE_TREE": HERMES_TREE,
            "WP7_ARM_CONFIG": cfg_path,
            "WP7_HARNESS_DIR": HARNESS,
            "WP7_HERMES_TREE": HERMES_TREE,
            "WP7_DECOYS": str(sw.decoys),
            "WP7_DECOY_PLUGIN": arms.DECOY_PLUGIN,
            "WP7_CELL": cell,
            "PYTHONUNBUFFERED": "1",
        })
        if dry:
            env["WP7_DRY"] = "1"
        else:
            env.pop("WP7_DRY", None)
        return env

    def run_cell(self, arm: str, task: str, rep: int, sw: arms.Switches, *, dry: bool = False,
                 timeout_s: int = 900) -> int:
        cell, cfg_path, audit = self.prepare(arm, task, rep, sw)
        out = os.path.join(self.root, "results", f"{cell}{'.dry' if dry else ''}.json")
        if not dry and not self.flush(cell):
            self.log({"event": "cell_skipped", "cell": cell, "utc": provenance.now(),
                      "reason": "flush_cache never returned 200"})
            return 4
        fp = provenance.fingerprint() if not dry else {}
        start, t0 = provenance.now(), time.time()
        cmd = [PY, WORKER, "base", arms.MODEL, task, str(rep), out]
        suffix = ".dry" if dry else ""
        with open(os.path.join(self.root, "logs", f"{cell}{suffix}.stdout"), "w") as so, \
                open(os.path.join(self.root, "logs", f"{cell}{suffix}.stderr"), "w") as se:
            try:
                p = subprocess.run(cmd, env=self.env(cfg_path, sw, cell, dry), stdout=so,
                                   stderr=se, cwd=self.root, timeout=timeout_s)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = -9
        self.log({"event": "cell_dry" if dry else "cell_done", "cell": cell, "arm": arm,
                  "task": task, "rep": rep, "switches": sw.__dict__, "start_utc": start,
                  "end_utc": provenance.now(), "wall_s": round(time.time() - t0, 1),
                  "returncode": rc, "audit": audit, "out": out, "config": cfg_path,
                  "fingerprint": fp})
        return rc


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def grid(a) -> list[tuple]:
    out = []
    for task, arm, role, decoys, backend, ann, rep in itertools.product(
            _csv(a.tasks), _csv(a.arms), _csv(a.roles), [int(x) for x in _csv(a.decoys)],
            _csv(a.backends), _csv(a.annotations), range(a.reps)):
        ks = [int(k) for k in _csv(a.k)] if arm == "C-cut" else [None]
        for k in ks:
            sw = arms.Switches(role=role, decoys=decoys, backend=backend, annotation=ann,
                               scope=a.scope, query=a.query, priority_weight=a.priority_weight,
                               always_offer=tuple(_csv(a.always_offer)), k=k)
            sw.validate(arm)
            out.append((arm, task, rep, sw))
    return out


def add_grid_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", required=True)
    p.add_argument("--arms", default="A,B,C-gate,D")
    p.add_argument("--tasks", default=SMOKE_TASK)
    p.add_argument("--roles", default="operator,guest")
    p.add_argument("--decoys", default="0")
    p.add_argument("--backends", default="nemotron")
    p.add_argument("--annotations", default="off")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--k", default="10", help="C-cut k values, comma-separated")
    p.add_argument("--scope", default="turn", choices=arms.SCOPES)
    p.add_argument("--query", default="message", choices=arms.QUERIES)
    p.add_argument("--priority-weight", default="0")
    p.add_argument("--always-offer", default="clarify", help="comma-separated, '' for none")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("matrix", "dry"):
        add_grid_args(sub.add_parser(name))
    sp = sub.add_parser("smoke")
    sp.add_argument("--root", required=True)
    sp.add_argument("--task", default=SMOKE_TASK)
    pp = sub.add_parser("provenance")
    pp.add_argument("--root", required=True)
    sub.add_parser("registry")
    sub.add_parser("tasks")
    a = ap.parse_args()

    if a.cmd == "tasks":
        t = _tasks_module()
        for tid in t.all_ids():
            print(f"{tid:28s} {t.source_of(tid):20s} timeout {t.timeout_of(tid)}s")
        return 0
    if a.cmd == "provenance":
        print(json.dumps(Run(a.root).write_provenance(), indent=1, default=str))
        return 0
    if a.cmd == "registry":
        return registry()

    if a.cmd == "smoke":
        a = argparse.Namespace(cmd="smoke", root=a.root, arms="A,B,C-gate,D", tasks=a.task,
                               roles="operator,guest", decoys="0,100", backends="nemotron",
                               annotations="off", reps=1, k="10", scope="turn", query="message",
                               priority_weight="0", always_offer="clarify")
    cells = grid(a)
    t = _tasks_module()
    run = Run(a.root)
    dry = a.cmd == "dry"
    if not dry:
        run.write_provenance()
    run.log({"event": "batch_start", "utc": provenance.now(), "cmd": a.cmd, "cells": len(cells),
             "argv": sys.argv[1:]})
    failures = 0
    for arm, task, rep, sw in cells:
        rc = run.run_cell(arm, task, rep, sw, dry=dry, timeout_s=t.timeout_of(task) + 120)
        failures += rc != 0
    run.log({"event": "batch_end", "utc": provenance.now(), "cells": len(cells),
             "nonzero": failures})
    return 1 if failures else 0


def registry() -> int:
    """Dry-build one agent with no decoys and no plugin, and save the registry it exposes."""
    import tempfile
    root = tempfile.mkdtemp(prefix="wp7-registry-")
    cfg = os.path.join(root, "config.yaml")
    with open(cfg, "w") as f:
        f.write(arms.render({"model": {"default": arms.MODEL, "provider": "custom",
                                       "base_url": arms.MODEL_BASE_URL, "api_key": "not-needed"},
                             "tools": {"tool_search": {"enabled": "off"}}}))
    out = os.path.join(root, "dry.json")
    env = dict(os.environ, ABDEFER_BASE_TREE=HERMES_TREE, WP7_ARM_CONFIG=cfg, WP7_DRY="1",
               WP7_HARNESS_DIR=HARNESS, WP7_HERMES_TREE=HERMES_TREE, WP7_DECOYS="0")
    env.pop("OPENROUTER_API_KEY", None)
    p = subprocess.run([PY, WORKER, "base", arms.MODEL, "config_grep_distractor", "0", out],
                       env=env, cwd=root, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        print(p.stderr[-3000:], file=sys.stderr)
        return p.returncode
    d = json.load(open(out))
    reg = {
        "hermes_commit": provenance.hermes_info(HERMES_TREE)["commit"],
        "made_by": "hermes/run.py registry: worker_local.py in WP7_DRY mode, "
                   "cronjob_manage enabled, no decoys, no plugin",
        "toolsets": d["wp7_surface"]["toolsets"],
        "candidates": d["registry_candidates"],
        "toolset_of": d["registry_toolset_of"],
        "agent_tools": d["wp7_surface"]["agent_tools"],
        "tools": [{"name": t["function"]["name"],
                   "toolset": d["registry_toolset_of"].get(t["function"]["name"]),
                   "description": t["function"].get("description", "")}
                  for t in d["registry_defs"]],
    }
    with open(arms.REGISTRY_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(reg, f, indent=1, ensure_ascii=False)
        f.write("\n")
    shutil.rmtree(root, ignore_errors=True)
    print(f"wrote {arms.REGISTRY_JSON}: {len(reg['tools'])} tools, "
          f"{len(reg['candidates'])} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
