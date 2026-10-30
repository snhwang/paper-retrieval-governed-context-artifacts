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
2. POSTs /flush_cache to SGLang until it answers HTTP 200, logging every attempt with its UTC
   time and status. SGLang refuses a flush while any request runs, and other clients may use
   the server, so a refusal is waited out with backoff (5 s doubling to 60 s, no limit). The
   cell starts only after a 200, and a refusal never fails or skips the cell,
3. runs worker_local.py in its own process with the cell's audit log,
4. appends a cell_done record (timings, return code, paths, provenance fingerprint).

Long batches (matrix options):
  --order rep-blocks --seed N   all cells of rep 0 in a seeded shuffle, then rep 1, and so on,
                                so drift over the hours does not line up with any arm
  --resume                      the cell order is fixed in logs/plan.json on the first start.
                                A restart runs only the planned cells with no cell_done record.
                                A cell interrupted part-way has its partial files moved to
                                aborted/ before it reruns
  --max-error-frac F            stop when more than F of the finished cells errored (worker
                                exit not 0, timeout, no result, or an error in the result),
                                checked once --min-cells-error-check cells are done, and always
                                when the errors exceed F of the whole plan
  --guard-provenance            fingerprint before every cell and stop if a guarded field
                                (provenance.GUARDED: image ids, model path and revision, SGLang
                                settings, embedder id and dim, BEAR version and sha, Hermes
                                commit and dirty count) differs from the plan's reference
  A file named STOP in --root ends the batch after the current cell.

Layout under --root: provenance.json, corpus/d<N>/, configs/, audit/, results/, logs/cells.jsonl,
logs/plan.json, logs/<cell>.stdout and .stderr, aborted/.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
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
HOME_DIR = os.path.expanduser("~")
# Files the worker reads from this directory. Under the sandbox they are copied into the run
# (materials/), checked by sha256, so the sandbox needs no view of /mnt.
MATERIALS = ("worker/worker_local.py", "worker/wp7_tasks.py", "decoys/sample.json",
             "decoys/wp7_decoys/plugin.yaml", "decoys/wp7_decoys/__init__.py",
             "sandbox_bridge.py", "sandbox_redteam.py")
BRIDGED_PORTS = (8355, 8360)  # the model server and the embedder, the only reachable ports
# The sandbox environment is fixed, not copied from the runner, so a cell sees the same
# environment whether the runner was started from a shell, a systemd scope or a user service.
# Everything else is dropped (keys, tokens, WSL interop, display, D-Bus, the user's PATH).
SANDBOX_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _fixed_env() -> dict:
    import pwd
    user = pwd.getpwuid(os.getuid()).pw_name
    return {"LANG": "C.UTF-8", "TERM": "xterm-256color", "USER": user, "LOGNAME": user,
            "PATH": SANDBOX_PATH, "HOME": HOME_DIR, "SHELL": "/bin/bash", "PYTHONUNBUFFERED": "1"}


def _bear_package_dir() -> str:
    import importlib.util
    spec = importlib.util.find_spec("bear")
    return os.path.realpath(list(spec.submodule_search_locations)[0])


BRIDGE_IN = "/run/wp7b"  # where the bridge sockets appear inside (short: unix paths max 107 bytes)
# Host paths no cell may change. The sandbox mounts them read-only or hides them, so a change
# here during a cell means something left the sandbox (bytecode caches aside, which the runner
# itself writes when it imports the harness).
LEAK_WATCH = ("~/.venvs/hermes", "~/.hermes", "~/.ssh", "~/.config/gh", "~/.config/systemd",
              "~/.local/bin", "~/.venvs/tist-spike", "~/.local/share/uv/python")


def mem_available_gb() -> float | None:
    """MemAvailable from /proc/meminfo, in GB (None if unreadable)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        return None
    return None


def leak_check(cell: str, marker: str, extra_dirs: list[str]) -> list[str]:
    """Signs that something from ``cell`` left its sandbox. Empty when all is well.

    Checks three things after the cell ends: no process still carries the cell's WP7_CELL,
    no file under the watched host paths is newer than ``marker`` (bytecode caches and .git
    aside), and no worker temp dir (/tmp/ab-*) or user crontab appeared on the host."""
    problems = []
    tag = f"WP7_CELL={cell}".encode()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                env = f.read().split(b"\0")
        except OSError:
            continue
        if tag in env:
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")[:160]
            except OSError:
                cmd = "?"
            problems.append(f"process {pid} outlived the cell: {cmd}")
    roots = [os.path.expanduser(p) for p in LEAK_WATCH] + list(extra_dirs)
    roots = [r for r in roots if os.path.exists(r)]
    p = subprocess.run(["find", *roots, "-newer", marker, "-not", "-path", "*/__pycache__*",
                        "-not", "-name", "*.pyc", "-not", "-path", "*/.git/*"],
                       capture_output=True, text=True)
    changed = [ln for ln in p.stdout.splitlines() if ln.strip()]
    if changed:
        problems.append(f"{len(changed)} host files changed: {changed[:5]}")
    p = subprocess.run(["find", "/tmp", "-maxdepth", "1", "-name", "ab-*", "-newer", marker],
                       capture_output=True, text=True)
    if p.stdout.strip():
        problems.append(f"worker temp dir on the host /tmp: {p.stdout.split()[:3]}")
    c = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if c.returncode == 0 and c.stdout.strip():
        problems.append(f"a user crontab exists: {c.stdout.strip()[:120]}")
    return problems


def bwrap_args(*, ro: list[str], rw: list[str], cwd: str, bridge_dir: str) -> list[str]:
    """The bubblewrap command line every sandboxed cell runs under, in every arm.

    Read-only root. A private tmpfs over /tmp, /var/tmp, /run (WSL interop sockets, the
    Docker socket, the user bus), /mnt (every Windows drive and /mnt/wsl), /media, /Docker
    and the whole home directory. /init (the WSL interop launcher) is replaced by /dev/null.
    Then read-only binds of exactly ``ro`` and writable binds of exactly ``rw``. Private PID,
    IPC and network namespaces (loopback only), a new session, and death with the parent, so
    nothing a cell starts outlives it.
    """
    a = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--tmpfs", "/dev/shm", "--proc", "/proc"]
    for d in ("/tmp", "/var/tmp", "/run", "/mnt", "/media", "/Docker", HOME_DIR):
        if os.path.isdir(d):
            a += ["--tmpfs", d]
    if os.path.exists("/init"):
        a += ["--ro-bind", "/dev/null", "/init"]
    # The venv's base interpreter (uv-managed CPython). The venv reaches it through a
    # versionless symlink (bin/python and pyvenv.cfg's home), which is recreated inside.
    real = os.path.realpath(sys.base_prefix)
    a += ["--ro-bind", real, real]
    links = {sys.base_prefix}
    vpy = os.path.join(sys.prefix, "bin", "python")
    if os.path.islink(vpy):
        links.add(os.path.dirname(os.path.dirname(os.readlink(vpy))))
    try:
        with open(os.path.join(sys.prefix, "pyvenv.cfg"), encoding="utf-8") as f:
            for line in f:
                if line.split("=")[0].strip() == "home":
                    links.add(os.path.dirname(line.split("=", 1)[1].strip()))
    except OSError:
        pass
    for link in sorted(links):
        if link and os.path.isabs(link) and link != real and os.path.realpath(link) == real:
            a += ["--symlink", real, link]
    for p in ro:
        a += ["--ro-bind", p, p]
    for p in rw:
        a += ["--bind", p, p]
    a += ["--bind", bridge_dir, BRIDGE_IN]  # only the two bridge sockets
    a += ["--unshare-pid", "--unshare-ipc", "--unshare-net", "--die-with-parent", "--new-session",
          "--chdir", cwd, "--"]
    return a
FLUSH_URL = "http://localhost:8355/flush_cache"
FLUSH_WAIT_S, FLUSH_WAIT_MAX_S = 5.0, 60.0  # backoff from 5 s, doubling, capped at 60 s
SMOKE_TASK = "ambiguous_delete_ask"


def _tasks_module():
    sys.path.insert(0, HARNESS)
    sys.path.insert(0, os.path.join(HERE, "worker"))
    os.environ.setdefault("WP7_HERMES_TREE", HERMES_TREE)
    import wp7_tasks
    return wp7_tasks


class Bridge:
    """The host side of one cell's port bridge: the process, its socket dir and its log."""

    def __init__(self, proc: subprocess.Popen, sock_dir: str, err) -> None:
        self.proc, self.sock_dir, self.err = proc, sock_dir, err

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.err.close()
        shutil.rmtree(self.sock_dir, ignore_errors=True)


class Run:
    def __init__(self, root: str, sandbox: str = "bwrap"):
        self.root = os.path.abspath(os.path.expanduser(root))
        for sub in ("configs", "audit", "results", "logs", "corpus"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        self.log_path = os.path.join(self.root, "logs", "cells.jsonl")
        self._embedding_revision: str | None = None
        if sandbox not in ("bwrap", "none"):
            raise ValueError("sandbox must be bwrap or none")
        self.sandbox = sandbox
        self.materials = os.path.join(self.root, "materials")
        if sandbox == "bwrap":
            if not shutil.which("bwrap"):
                raise SystemExit("ABORT: --sandbox bwrap needs bubblewrap (bwrap) on PATH")
            self.stage_materials()

    def stage_materials(self) -> None:
        """Copy the worker's materials into the run, or check an earlier copy is unchanged."""
        man_path = os.path.join(self.materials, "MANIFEST.json")
        want = {rel: provenance.sha256_file(os.path.join(HERE, rel)) for rel in MATERIALS}
        if os.path.exists(man_path):
            with open(man_path, encoding="utf-8") as f:
                have = json.load(f)
            now = {rel: provenance.sha256_file(os.path.join(self.materials, rel)) for rel in MATERIALS}
            if have != want or now != want:
                raise SystemExit("ABORT: materials/ differs from the source files; a run must "
                                 "keep one set of materials")
            return
        for rel in MATERIALS:
            dst = os.path.join(self.materials, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(HERE, rel), dst)
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(want, f, indent=1)

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

    def flush(self, cell: str) -> dict:
        """POST /flush_cache until HTTP 200, with no limit on attempts.

        SGLang refuses a flush while any request is running or queued, and other clients may
        share the server, so a refusal is waited out (backoff from 5 s, doubling, capped at
        60 s). Every attempt is logged with its UTC time and status. Returns once the flush
        succeeded, with the attempt count and the seconds spent waiting.
        """
        t0, wait, attempt = time.time(), FLUSH_WAIT_S, 0
        while True:
            attempt += 1
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
            rec = {"event": "flush_cache", "cell": cell, "attempt": attempt, "utc": ts,
                   "http_status": status, "body": body.strip()[:200]}
            if status != 200:
                rec["retry_in_s"] = wait
            self.log(rec)
            if status == 200:
                return {"flush_attempts": attempt, "flush_wait_s": round(time.time() - t0, 1)}
            time.sleep(wait)
            wait = min(wait * 2, FLUSH_WAIT_MAX_S)

    def cell_dir(self, cell: str) -> str:
        """The cell's own directory, the only writable path the sandbox shares with the host."""
        return os.path.join(self.root, "cells", cell)

    def prepare(self, arm: str, task: str, rep: int, sw: arms.Switches) -> tuple[str, str, str]:
        sw.validate(arm)
        cell = arms.cell_id(arm, task, rep, sw)
        audit = os.path.join(self.root, "audit", f"{cell}.jsonl")
        if self.sandbox == "bwrap":
            # Inside the sandbox the plugin writes the audit log in the cell's directory and
            # reads the decoy sample from the run's copy of the materials.
            cfg = arms.hermes_config(arm, sw, corpus_dir=self.corpus_dir(sw.decoys),
                                     audit_path=os.path.join(self.cell_dir(cell), "audit.jsonl"),
                                     embedding_revision=self.embedding_revision(),
                                     decoy_sample=os.path.join(self.materials, "decoys", "sample.json"))
        else:
            cfg = arms.hermes_config(arm, sw, corpus_dir=self.corpus_dir(sw.decoys), audit_path=audit,
                                     embedding_revision=self.embedding_revision())
        cfg_path = os.path.join(self.root, "configs", f"{cell}.yaml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(arms.render(cfg))
        return cell, cfg_path, audit

    def sandbox_env(self, cfg_in: str, sw: arms.Switches, cell: str, dry: bool) -> dict:
        """A scrubbed environment: fixed values plus the worker's own WP7 variables."""
        env = _fixed_env()
        env.update({
            "ABDEFER_BASE_TREE": HERMES_TREE,
            "WP7_ARM_CONFIG": cfg_in,
            "WP7_HARNESS_DIR": HARNESS,
            "WP7_HERMES_TREE": HERMES_TREE,
            "WP7_DECOYS": str(sw.decoys),
            "WP7_DECOY_PLUGIN": os.path.join(self.materials, "decoys", "wp7_decoys"),
            "WP7_CELL": cell,
        })
        if dry:
            env["WP7_DRY"] = "1"
        return env

    def sandboxed(self, cell: str, inner: list[str], decoys: int | None) -> tuple[list[str], "Bridge"]:
        """Start the host side of the port bridge and return the bwrap command for ``inner``.

        The sockets live in a short host directory (/tmp/wp7b-XXXX), mounted at /run/wp7b
        inside, because a unix socket path may not exceed 107 bytes."""
        import tempfile
        cdir = self.cell_dir(cell)
        bdir = tempfile.mkdtemp(prefix="wp7b-", dir="/tmp")
        socks = {p: os.path.join(bdir, f"{p}.sock") for p in BRIDGED_PORTS}
        err = open(os.path.join(self.root, "logs", f"{cell}.bridge.stderr"), "w")
        host = subprocess.Popen([PY, os.path.join(HERE, "sandbox_bridge.py"), "host",
                                 *[f"{s}=127.0.0.1:{p}" for p, s in socks.items()]],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=err, start_new_session=True)
        bridge = Bridge(host, bdir, err)
        end = time.time() + 15
        while not all(os.path.exists(s) for s in socks.values()) and time.time() < end:
            if host.poll() is not None:
                break
            time.sleep(0.05)
        if not all(os.path.exists(s) for s in socks.values()):
            bridge.stop()
            raise RuntimeError(f"host bridge did not start for {cell} (see logs/{cell}.bridge.stderr)")
        ro = [HERMES_TREE, sys.prefix, _bear_package_dir(), self.materials]
        if decoys is not None:
            ro.append(self.corpus_dir(decoys))
        cmd = bwrap_args(ro=ro, rw=[cdir], cwd=cdir, bridge_dir=bdir) + [
            PY, os.path.join(self.materials, "sandbox_bridge.py"), "inside",
            *[f"{p}={BRIDGE_IN}/{p}.sock" for p in socks], "--", *inner]
        return cmd, bridge

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

    def set_aside(self, cell: str, out: str, audit: str) -> None:
        """Move a cell's partial files (an interrupted earlier attempt) to aborted/.

        The plugin appends to the audit log, so a rerun on top of a partial log would mix
        two attempts' records."""
        stale = [p for p in (audit, out, out + ".transcript.json", out + ".home",
                             self.cell_dir(cell)) if os.path.exists(p)]
        if not stale:
            return
        dest = os.path.join(self.root, "aborted", provenance.now().replace(":", ""))
        os.makedirs(dest, exist_ok=True)
        for p in stale:
            shutil.move(p, os.path.join(dest, os.path.basename(p)))
        self.log({"event": "cell_set_aside", "cell": cell, "utc": provenance.now(),
                  "moved": [os.path.basename(p) for p in stale], "to": dest})

    def run_cell(self, arm: str, task: str, rep: int, sw: arms.Switches, *, dry: bool = False,
                 timeout_s: int = 900, guard=None) -> int:
        cell, cfg_path, audit = self.prepare(arm, task, rep, sw)
        out = os.path.join(self.root, "results", f"{cell}{'.dry' if dry else ''}.json")
        fp, flush_info = {}, {}
        if not dry:
            self.set_aside(cell, out, audit)
            fp = provenance.fingerprint(PY, HERMES_TREE)
            if guard is not None:
                reason = guard(cell, fp)
                if reason:
                    self.log({"event": "cell_not_run", "cell": cell, "utc": provenance.now(),
                              "reason": reason, "fingerprint": fp})
                    return 5
            flush_info = self.flush(cell)
        elif os.path.exists(self.cell_dir(cell)):
            shutil.rmtree(self.cell_dir(cell), ignore_errors=True)  # a stale dry-build dir
        start, t0 = provenance.now(), time.time()
        suffix = ".dry" if dry else ""
        host_bridge = None
        if self.sandbox == "bwrap":
            cdir = self.cell_dir(cell)
            os.makedirs(cdir, exist_ok=True)
            cfg_in = os.path.join(cdir, "config.yaml")
            shutil.copy2(cfg_path, cfg_in)
            inner_out = os.path.join(cdir, f"result{suffix}.json")
            inner = [PY, os.path.join(self.materials, "worker", "worker_local.py"), "base",
                     arms.MODEL, task, str(rep), inner_out]
            try:
                cmd, host_bridge = self.sandboxed(cell, inner, sw.decoys)
            except RuntimeError as e:  # the bridge did not come up: an error cell, never a hang
                cmd = None
                with open(os.path.join(self.root, "logs", f"{cell}{suffix}.stderr"), "w") as se:
                    se.write(f"WP7 runner: {e}\n")
            env, cwd = self.sandbox_env(cfg_in, sw, cell, dry), cdir
        else:
            cmd = [PY, WORKER, "base", arms.MODEL, task, str(rep), out]
            env, cwd = self.env(cfg_path, sw, cell, dry), self.root
        if cmd is None:
            rc = 6
        else:
            with open(os.path.join(self.root, "logs", f"{cell}{suffix}.stdout"), "w") as so, \
                    open(os.path.join(self.root, "logs", f"{cell}{suffix}.stderr"), "w") as se:
                try:
                    p = subprocess.run(cmd, env=env, stdout=so, stderr=se, cwd=cwd, timeout=timeout_s)
                    rc = p.returncode
                except subprocess.TimeoutExpired:
                    rc = -9
        if self.sandbox == "bwrap":
            if host_bridge is not None:
                host_bridge.stop()
            # Move the cell's outputs to the run's usual places, then drop its directory.
            moves = [(inner_out, out), (inner_out + ".transcript.json", out + ".transcript.json"),
                     (inner_out + ".home", out + ".home")]
            if not dry:
                moves.append((os.path.join(cdir, "audit.jsonl"), audit))
            for src, dst in moves:
                if os.path.exists(src):
                    shutil.move(src, dst)
            shutil.rmtree(cdir, ignore_errors=True)
        self.log({"event": "cell_dry" if dry else "cell_done", "cell": cell, "arm": arm,
                  "task": task, "rep": rep, "switches": sw.__dict__, "start_utc": start,
                  "end_utc": provenance.now(), "wall_s": round(time.time() - t0, 1),
                  "returncode": rc, "audit": audit, "out": out, "config": cfg_path,
                  "sandbox": self.sandbox, **flush_info, "fingerprint": fp})
        return rc

    def redteam(self) -> int:
        """Run sandbox_redteam.py in a cell sandbox (no model), then check from the host that
        nothing it started outlived the cell. Writes redteam.json."""
        cell = "redteam__" + provenance.now().replace(":", "").replace(".", "")
        cdir = self.cell_dir(cell)
        os.makedirs(cdir, exist_ok=True)
        out = os.path.join(cdir, "redteam.jsonl")
        inner = [PY, os.path.join(self.materials, "sandbox_redteam.py"), out]
        cmd, host_bridge = self.sandboxed(cell, inner, 0)
        env = self.sandbox_env(os.path.join(cdir, "none.yaml"), arms.Switches(), cell, False)
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=cdir, timeout=300)
        host_bridge.stop()
        time.sleep(2)
        rows = []
        if os.path.exists(out):
            with open(out, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        # Host-side checks: the markers the script left running must be gone.
        for marker in ("wp7-redteam-tmux", "wp7-redteam-nohup"):
            alive = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
            rows.append({"test": f"host: process {marker} gone after the cell", "expect": "absent",
                         "ok": alive.returncode != 0, "detail": alive.stdout.strip()[:200]})
        tm = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
        rows.append({"test": "host: no tmux session wp7redteam", "expect": "absent",
                     "ok": "wp7redteam" not in tm.stdout, "detail": (tm.stdout + tm.stderr).strip()[:200]})
        for probe in (os.path.expanduser("~/.venvs/hermes/wp7_redteam_probe"),
                      os.path.join(HERMES_TREE, "wp7_redteam_probe"),
                      os.path.join(self.root, "wp7_redteam_probe")):
            rows.append({"test": f"host: {probe} not created", "expect": "absent",
                         "ok": not os.path.exists(probe), "detail": ""})
        res = {"utc": provenance.now(), "returncode": p.returncode, "stderr_tail": p.stderr[-1500:],
               "bwrap": cmd[:cmd.index("--") + 1], "tests": rows,
               "passed": sum(r["ok"] for r in rows), "failed": sum(not r["ok"] for r in rows)}
        with open(os.path.join(self.root, "redteam.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        shutil.rmtree(cdir, ignore_errors=True)
        for r in rows:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['test']}  ({r['expect']})  {str(r.get('detail'))[:120]}")
        print(f"passed {res['passed']}, failed {res['failed']}, sandbox rc {p.returncode}")
        return 0 if res["failed"] == 0 and p.returncode == 0 else 1


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def task_ids(spec: str) -> list[str]:
    """A comma list of task ids, or "all" for the 14 core and 9 toolperf tasks."""
    if spec.strip() == "all":
        return _tasks_module().all_ids()
    return _csv(spec)


def grid(a) -> list[tuple]:
    out = []
    for task, arm, role, decoys, backend, ann, rep in itertools.product(
            task_ids(a.tasks), _csv(a.arms), _csv(a.roles), [int(x) for x in _csv(a.decoys)],
            _csv(a.backends), _csv(a.annotations), range(a.reps)):
        ks = [int(k) for k in _csv(a.k)] if arm == "C-cut" else [None]
        for k in ks:
            sw = arms.Switches(role=role, decoys=decoys, backend=backend, annotation=ann,
                               scope=a.scope, query=a.query, priority_weight=a.priority_weight,
                               always_offer=tuple(_csv(a.always_offer)), k=k)
            sw.validate(arm)
            out.append((arm, task, rep, sw))
    if getattr(a, "order", "product") == "rep-blocks":
        # Rep blocks in order, each one shuffled with its own seeded generator.
        blocks = []
        for rep in sorted({c[2] for c in out}):
            block = sorted((c for c in out if c[2] == rep), key=lambda c: arms.cell_id(*c[:3], c[3]))
            random.Random(int(a.seed) * 1000 + rep).shuffle(block)
            blocks.extend(block)
        out = blocks
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
    p.add_argument("--order", default="product", choices=("product", "rep-blocks"))
    p.add_argument("--seed", default="20261030", help="seed for --order rep-blocks")
    p.add_argument("--resume", action="store_true",
                   help="keep logs/plan.json's order and run only cells with no cell_done")
    p.add_argument("--max-error-frac", type=float, default=None)
    p.add_argument("--min-cells-error-check", type=int, default=40)
    p.add_argument("--guard-provenance", action="store_true")
    p.add_argument("--sandbox", default="bwrap", choices=("bwrap", "none"),
                   help="bwrap (default): every worker in the cell sandbox; none: the old way")
    p.add_argument("--min-avail-gb", type=float, default=16.0,
                   help="stop before a cell when the host's MemAvailable is below this (0 = off)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("matrix", "dry"):
        add_grid_args(sub.add_parser(name))
    rp = sub.add_parser("redteam", help="escape attempts inside a cell sandbox, no model")
    rp.add_argument("--root", required=True)
    sp = sub.add_parser("smoke")
    sp.add_argument("--root", required=True)
    sp.add_argument("--sandbox", default="bwrap", choices=("bwrap", "none"))
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
        print(json.dumps(Run(a.root, sandbox="none").write_provenance(), indent=1, default=str))
        return 0
    if a.cmd == "registry":
        return registry()
    if a.cmd == "redteam":
        return Run(a.root, sandbox="bwrap").redteam()

    if a.cmd == "smoke":
        a = argparse.Namespace(cmd="smoke", root=a.root, arms="A,B,C-gate,D", tasks=a.task,
                               roles="operator,guest", decoys="0,100", backends="nemotron",
                               annotations="off", reps=1, k="10", scope="turn", query="message",
                               priority_weight="0", always_offer="clarify", order="product",
                               seed="0", resume=False, max_error_frac=None,
                               min_cells_error_check=40, guard_provenance=False,
                               sandbox=a.sandbox, min_avail_gb=16.0)
    cells = grid(a)
    t = _tasks_module()
    run = Run(a.root, sandbox=a.sandbox)
    dry = a.cmd == "dry"
    cid = lambda c: arms.cell_id(c[0], c[1], c[2], c[3])  # noqa: E731
    planned = [{"cell": cid(c), "arm": c[0], "task": c[1], "rep": c[2], "switches": c[3].__dict__}
               for c in cells]
    plan_ids = {p["cell"] for p in planned}
    plan_path = os.path.join(run.root, "logs", "plan.json")
    ref_fp: dict = {}
    resuming = not dry and a.resume and os.path.exists(plan_path)
    if resuming:
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        if {p["cell"] for p in plan["cells"]} != plan_ids:
            print("ABORT: --resume with a grid that differs from logs/plan.json", file=sys.stderr)
            return 2
        pos = {p["cell"]: i for i, p in enumerate(plan["cells"])}
        cells.sort(key=lambda c: pos[cid(c)])
        ref_fp = plan.get("reference_fingerprint") or {}
        with open(os.path.join(run.root, f"provenance.resume-{provenance.now().replace(':', '')}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(provenance.collect(HERE, HERMES_TREE), f, indent=1, default=str)
    elif not dry:
        run.write_provenance()
        if a.resume or a.guard_provenance:
            ref_fp = provenance.fingerprint(PY, HERMES_TREE)
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump({"created_utc": provenance.now(), "argv": sys.argv[1:], "order": a.order,
                           "seed": a.seed, "sandbox": a.sandbox,
                           "artifacts": provenance.artifacts_info(HERE), "cells": planned,
                           "reference_fingerprint": ref_fp}, f, indent=1, default=str)

    def is_error(rc: int, out: str) -> bool:
        if rc != 0 or not os.path.exists(out):
            return True
        try:
            with open(out, encoding="utf-8") as f:
                return bool(json.load(f).get("error"))
        except Exception:
            return True

    done: dict[str, dict] = {}
    if a.resume and os.path.exists(run.log_path):
        with open(run.log_path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("event") == "cell_done" and r.get("cell") in plan_ids:
                    done[r["cell"]] = r
    todo = [c for c in cells if cid(c) not in done]
    ndone = len(done)
    errors = sum(is_error(r["returncode"], r["out"]) for r in done.values())

    last_warned: dict = {}

    def guard(cell: str, fp: dict) -> str | None:
        nonlocal last_warned
        changed, warned = provenance.drift(ref_fp, fp)
        if changed:  # rule out a transient read failure before stopping
            time.sleep(15)
            changed, warned = provenance.drift(ref_fp, provenance.fingerprint(PY, HERMES_TREE))
        if warned and warned != last_warned:
            run.log({"event": "provenance_warning", "cell": cell, "utc": provenance.now(),
                     "changed": warned})
        last_warned = warned
        return f"guarded provenance changed: {json.dumps(changed, default=str)}" if changed else None

    leak_on = run.sandbox == "bwrap" and not dry
    marker = os.path.join(run.root, "logs", f"leakcheck.{provenance.now().replace(':', '')}.marker")
    if leak_on:
        with open(marker, "w") as f:
            f.write("host files newer than this were changed during the batch\n")
    run.log({"event": "batch_start", "utc": provenance.now(), "cmd": a.cmd, "cells": len(cells),
             "to_run": len(todo), "already_done": ndone, "errors_so_far": errors,
             "resumed": resuming, "sandbox": run.sandbox, "leak_check": leak_on,
             "artifacts": provenance.artifacts_info(HERE), "argv": sys.argv[1:]})
    failures = 0
    for c in todo:
        arm, task, rep, sw = c
        avail = mem_available_gb()
        if not dry and a.min_avail_gb and avail is not None and avail < a.min_avail_gb:
            run.log({"event": "batch_stopped", "utc": provenance.now(), "reason": "low_memory",
                     "mem_available_gb": round(avail, 1), "floor_gb": a.min_avail_gb,
                     "next_cell": cid(c), "done": ndone, "errors": errors})
            return 2
        rc = run.run_cell(arm, task, rep, sw, dry=dry, timeout_s=t.timeout_of(task) + 120,
                          guard=guard if (a.guard_provenance and not dry) else None)
        if rc == 5:
            run.log({"event": "batch_stopped", "utc": provenance.now(), "reason": "provenance",
                     "cell": cid(c), "done": ndone, "errors": errors})
            return 2
        failures += rc != 0
        if dry:
            continue
        if leak_on and rc != 5:
            problems = leak_check(cid(c), marker,
                                  [os.path.dirname(_bear_package_dir()), HERMES_TREE])
            if problems:
                run.log({"event": "batch_stopped", "utc": provenance.now(), "reason": "sandbox_leak",
                         "cell": cid(c), "problems": problems, "done": ndone + 1})
                return 2
        ndone += 1
        errors += is_error(rc, os.path.join(run.root, "results", f"{cid(c)}.json"))
        frac = a.max_error_frac
        if frac is not None and ((ndone >= a.min_cells_error_check and errors > frac * ndone)
                                 or errors > frac * len(planned)):
            run.log({"event": "batch_stopped", "utc": provenance.now(), "reason": "error_rate",
                     "done": ndone, "errors": errors, "planned": len(planned)})
            return 2
        if os.path.exists(os.path.join(run.root, "STOP")):
            run.log({"event": "batch_paused", "utc": provenance.now(), "reason": "STOP file",
                     "done": ndone, "errors": errors})
            return 3
    run.log({"event": "batch_end", "utc": provenance.now(), "cells": len(cells),
             "done": ndone, "errors": errors, "nonzero_this_session": failures})
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
