# Reproducing WP7 (Hermes execution-level experiment) by hand

This document runs WP7 stage 1 and stage 2 from a WSL terminal, with no agent involved. Every step that produces a result is a script in `hermes/scripts/`. Each one prints the commands to follow its progress and writes a run record (section 7).

Runs launched by agents are not reported results. That covers the stage-1 grid in `~/tist-wp7/runs/stage1`, its pilot and smokes, the stage-2 smoke, and the stage-2 block-1 rehearsal (63 cells, stopped 2026-10-31 19:39:49 UTC). The files in `hermes/results/stage1/` and `hermes/results/stage2/` were computed from those agent runs. They are kept for comparison until the runs below replace them.

## 1. Prerequisites

**Machine.**
- Windows 11 with WSL2 Ubuntu 24.04, with systemd enabled and mirrored networking. Under mirrored networking, `127.0.0.1` inside WSL reaches the Windows-side servers.
- WSL must stay up for many hours. A grid runs as a systemd user service, which survives its terminal closing but not WSL shutting down. Here a Windows scheduled task (`wsl-keepalive`) holds a WSL session open. Check that it shows Running before each launch, with `Get-ScheduledTask wsl-keepalive` in PowerShell.
- In WSL you need git, bubblewrap 0.9.0 (`sudo apt install bubblewrap`), uv 0.11 (`uv --version`), the system `python3`, and a docker CLI that can inspect the two server containers. The provenance check reads their image ids.
- Network access to GitHub, for `install_bear.sh` only. Cells have no network, apart from the bridged ports 8355 and 8360.

**Code.**
- Hermes Agent, checked out at `~/src/hermes-agent`, commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` (release 0.22.2), with no local change. Set `WP7_HERMES_TREE` if it lives elsewhere.
- The runner venv, `~/.venvs/tist-spike`.
  - Python 3.14.5, with Hermes installed editable from the checkout (`uv pip install --python ~/.venvs/tist-spike/bin/python -e ~/src/hermes-agent`).
  - BEAR is installed by `scripts/install_bear.sh` (v0.4.1 for stage 1, v0.4.2 for stage 2).
  - The full package list is in `scripts/expected/tist-spike-packages.txt`. The venv has no pip, so use uv.
- An analysis Python with numpy 2.2.6, scipy 1.17.1 and pyyaml 6.0.1. The agent runs used Python 3.12.13 in `~/.venvs/tist-evals`. Set `WP7_PY_ANALYSIS` to another one if you prefer.
- This artifacts repo, branch `tist-r2`, with LF line endings. Clone or check it out from WSL git, or set `core.autocrlf=false`. A CRLF copy of the materials breaks cells, and `provenance_check.py` rejects it because the file hashes differ.

**Servers.** Both run in Docker on the Windows side. `scripts/expected/stage1.json` and `stage2.json` hold the exact values, and `provenance_check.py` compares them with the live servers.
- Port 8355 runs SGLang 0.5.21, serving `unsloth/Qwen3.8-27B-NVFP4` at revision `f0b7c9e722f5565102fff8481c99e4d86ae099c7`. The image is `sha256:b1259f3e...`. Settings are `kv_cache_dtype fp8_e4m3`, `random_seed 1`, `enable_cache_report true`, `tool_call_parser qwen3_coder`, `reasoning_parser qwen3`, `dtype auto` and `tp_size 1`. The runner posts `/flush_cache` before every cell and waits for HTTP 200, so no other client should use 8355 during a grid.
- Port 8360 runs the embedder `nvidia/llama-nemotron-embed-vl-1b-v2` (dimension 2048), image `sha256:6eec0ff4...`. Another client may share it, and slow calls are normal.

**Memory.**
- Cap the user slice once with `systemctl --user set-property tist.slice MemoryMax=40G`.
- Install the wrapper with `install -m 755 hermes/scripts/tist-capped ~/bin/tist-capped`.
- Grids run as a 16G transient service. Other steps run in 4G or 8G scopes. Exit code 137 means the cap killed that job.
- The runner also stops a grid when MemAvailable falls below 16 GB (`--min-avail-gb 16`).
- Load no local model in WSL while a grid runs.

## 2. Settings

`scripts/env.sh` sets these, and you can override any of them in your shell first:

| Variable | Default | Meaning |
| --- | --- | --- |
| `WP7_RUNS` | `~/wp7-runs` | run roots, kept apart from the agent runs in `~/tist-wp7/runs` |
| `WP7_ANALYSIS` | `$WP7_RUNS/analysis` | checks summaries, tables and analysis output |
| `WP7_RECORDS` | `$WP7_RUNS/records` | run records |
| `WP7_HARNESS_DIR` | this checkout's `hermes/` | where `run.py` and the cell materials come from (stage 1 uses a clone, step S1.1) |
| `WP7_HERMES_TREE` | `~/src/hermes-agent` | the Hermes checkout |
| `WP7_PY` | `~/.venvs/tist-spike/bin/python` | runner venv (Hermes and BEAR) |
| `WP7_PY_ANALYSIS` | `~/.venvs/tist-evals/bin/python` | analysis Python (numpy, scipy, pyyaml) |
| `WP7_BEAR_BASE` | `~/tist-wp7` | where `install_bear.sh` keeps the BEAR clones |
| `TIST_CAPPED` | `~/bin/tist-capped` | the memory-cap wrapper |

Checks and analysis always come from this checkout. Only `run.py` and the materials it mounts into cells come from `WP7_HARNESS_DIR`.

Two files hold the home directory `/home/snhwang`. They are `sandbox_redteam.py`, whose probes check host paths, and `analyze_stage1.py`, whose patterns count out-of-cell attempts. On this machine nothing needs changing. Under another account, edit those two lines first. The provenance check will then report the changed `sandbox_redteam.py`, which is expected.

## 3. Which steps use the servers

| Step | 8355 (model) | 8360 (embedder) |
| --- | --- | --- |
| `install_bear.sh`, `validate.py`, `test_stage2_tasks.py`, plan-only, red team `--offline` | no | no |
| red team (bridged), part of `pregrid1.sh` and `pregrid2.sh` | probes only | probes only |
| `provenance_check.py`, also run by both launchers | `/get_server_info` | `/health` |
| re-smoke (4 cells), part of both pre-grid scripts | yes, with cache flushes | yes |
| stage-1 grid and stage-2 blocks | yes, with cache flushes (exclusive use) | yes |
| `checks.py` (includes BEAR verify-audit), `post_stage1.sh`, `post_block.sh` | no | no |
| `analyze_stage1.py`, `analyze_stage2.py`, `stage2_settings.sh` (k sweep, annotation cost) | no | no |
| `status.py`, `watch.py` | no | no |

## 4. Stage 1 (BEAR v0.4.1, harness commit 9820f8a)

Stage 1 ran its cells from artifacts commit `9820f8a8baa2a4522688e0dd09bb805bcd1bf94d`. Later commits changed the worker and tasks for stage 2. To repeat stage 1 exactly, run its cells from a clone at that commit.

Start every session like this (adjust `REPO` to where WSL sees this repo):

```bash
export REPO=/mnt/c/Users/Scott/Documents/Work/paper-retrieval-governed-context-artifacts
cd "$REPO/hermes"
```

**S1.1 The stage-1 harness.**

```bash
git clone "$REPO" "$HOME/wp7-runs/artifacts-stage1"
git -C "$HOME/wp7-runs/artifacts-stage1" checkout --detach 9820f8a8baa2a4522688e0dd09bb805bcd1bf94d
export WP7_HARNESS_DIR=$HOME/wp7-runs/artifacts-stage1/hermes
```

Keep `WP7_HARNESS_DIR` set for steps S1.3 and S1.4.

**S1.2 BEAR v0.4.1.** No server is needed.

```bash
bash scripts/install_bear.sh v0.4.1
```

It clones the tag, checks the commit (`fa87fc5`), writes `BEAR_GIT_SHA` and `BEAR_GIT_LOG` into the clone, and installs it editable into the runner venv with `uv pip install --no-deps --reinstall -e`.

**S1.3 Pre-grid checks.** These take about 2 minutes and need both servers.

```bash
bash scripts/pregrid1.sh
```

It runs these steps in order and stops at the first failure:
1. `validate.py` (offline lint of the corpus at 0, 100 and 300 decoys, and the 24 arm configs)
2. the bridged cell red team
3. `provenance_check.py expected/stage1.json`
4. a 4-cell re-smoke (A and D, operator and guest, 0 decoys, `ambiguous_delete_ask`)
5. `checks.py` on the re-smoke
6. `resmoke_gate.py --stage 1`

The gates cover these points:
- exit 0, sandboxed, Nemotron everywhere, no exact ties
- restore flags false
- no `required_tags` admissions
- the D guest never sent `terminal`
- every check passes, and verify-audit reports no differs

The D guest's score is printed but is not a gate. An agent that asks in plain text instead of calling `clarify` scores 0.0 there (CHANGES.md, "A grader limitation").

**S1.4 The grid.** It has 1,656 cells and needs both servers, with 8355 to itself. The agent run took 27.2 hours (59 s per cell).

```bash
bash scripts/launch_stage1.sh
```

The grid is arms A, B, C-gate and D × operator and guest × 0, 100 and 300 decoys × 23 tasks × 3 reps, on Nemotron with annotations off. Cells run in seeded rep blocks (seed 20261030), with `--resume --max-error-frac 0.05 --guard-provenance`. Before launching, the script refuses to start if:
- another WP7 grid is active
- BEAR is not v0.4.1
- the harness has uncommitted changes
- the provenance check fails

It prints the status commands and the run record path, for example:

```bash
systemctl --user status tist-wp7-stage1 --no-pager
journalctl --user -u tist-wp7-stage1 -n 20 --no-pager
python3 scripts/status.py ~/wp7-runs/stage1
python3 scripts/watch.py ~/wp7-runs/stage1 $(wc -l < ~/wp7-runs/stage1/logs/cells.jsonl) 100 tist-wp7-stage1
```

`watch.py` returns after 100 more cells, or on an error burst, a stop, a 40-minute stall, a flush refused for 15 minutes, or the service ending. Section 8 covers stopping and continuing.

**S1.5 Checks and analysis.** These are offline and take about 15 minutes. The agent run's checks took about 5 minutes with 16 jobs, and this script uses 8.

```bash
unset WP7_HARNESS_DIR
bash scripts/post_stage1.sh
```

This runs `checks.py`, with verify-audit and the stage-1 registry, into `~/wp7-runs/stage1/checks/`. It then runs `analyze_stage1.py` with 10,000 bootstrap resamples and seed 20261030 into `~/wp7-runs/analysis/stage1/`. It adds `checks_summary.json`, `run_info.json` and `sandbox_redteam.json`. At the end it prints a `diff` against the committed agent-run results in `hermes/results/stage1/`.

**Optional stage-1 extras.** The agent also ran two more checks before the grid. The results do not need them.
- The 16-cell smoke. Run `$WP7_PY run.py smoke --root ~/wp7-runs/stage1-smoke` from `$WP7_HARNESS_DIR`. It needs both servers.
- Dry builds. Run `run.py dry` with the matrix options. They build each agent without a model call, but still reach 8360.

## 5. Settings for stage 2 from the stage-1 run (BEAR v0.4.2)

**S2.0 BEAR v0.4.2.** No server is needed.

```bash
unset WP7_HARNESS_DIR
bash scripts/install_bear.sh v0.4.2
```

The commit is `0d0718a`.

**S2.1 k sweep and annotation cost.** Both are offline and take about a minute.

```bash
bash scripts/stage2_settings.sh
```

This writes `ksweep.{json,md}` and `annotation_cost.{json,md}` to `~/wp7-runs/analysis/stage2-settings/`. The block-2 spec uses k=15, chosen from the agent-run sweep (`hermes/results/stage2/ksweep.md`). That was the smallest k that kept at least 95% of needed tool groups on both backends. If your sweep points to a different k, decide before block 2 and change `specs/stage2_block2.json` in a commit. The spec is not among the hashed materials, so the provenance check does not flag that edit. The launcher does refuse to start while it is uncommitted.

## 6. Stage 2 (BEAR v0.4.2, this checkout)

Stage 2 runs from this checkout (`WP7_HARNESS_DIR` unset). The stage-2 materials are unchanged since commit `1f38aca`. `expected/stage2.json` holds their hashes.

**S2.2 Pre-grid checks.** These take about 2 minutes and need both servers.

```bash
bash scripts/pregrid2.sh
```

It runs these steps in order and stops at the first failure:
1. `test_stage2_tasks.py` (offline)
2. plan-only for the three specs (874, 828 and 276 cells, offline)
3. the red team offline, then bridged
4. `provenance_check.py expected/stage2.json`
5. the 4-cell re-smoke
6. `checks.py --expect-sources-removed`
7. `resmoke_gate.py --stage 2`

If 8355 is booked, set `WP7_NOT_BEFORE="YYYY-MM-DD HH:MM:SS"` (UTC), and the script refuses to start earlier.

**S2.3 to S2.5 The three blocks.** Run them one at a time, in order. Each block is its own service and root. After each block, run its checks and analysis before launching the next.

```bash
bash scripts/launch_block.sh 1      # 874 cells. 2b at 0 decoys plus the 2c spoof probe
bash scripts/post_block.sh 1        # offline: checks, verify-audit, block analysis
bash scripts/launch_block.sh 2      # 828 cells. 2a: C-cut k=15 on Nemotron and BM25, C-gate, B
bash scripts/post_block.sh 2
bash scripts/launch_block.sh 3      # 276 cells. 2b at 100 decoys, guests
bash scripts/post_block.sh 3
```

| Block | Spec | Cells | Expected time | Service, root |
| --- | --- | --- | --- | --- |
| 1 | `specs/stage2_block1.json` | 874 | about 11.5 h (47 s per cell in the stopped rehearsal) | `tist-wp7-stage2-b1`, `~/wp7-runs/stage2-b1` |
| 2 | `specs/stage2_block2.json` | 828 | about 13.5 h (turn scope like stage 1, 59 s per cell) | `tist-wp7-stage2-b2`, `~/wp7-runs/stage2-b2` |
| 3 | `specs/stage2_block3.json` | 276 | about 4 to 4.5 h | `tist-wp7-stage2-b3`, `~/wp7-runs/stage2-b3` |

Each launch first checks the following, and refuses to start if any check fails:
- no other WP7 grid is active
- BEAR is v0.4.2
- `hermes/` has no uncommitted change
- `provenance_check.py expected/stage2.json` passes

All cells use seed 20261031, rep-block order, `--resume --max-error-frac 0.05 --guard-provenance`. `post_block.sh N` writes `~/wp7-runs/stage2-bN/checks/` and `~/wp7-runs/analysis/stage2-bN/`. Add `--print` to a launcher to see its exact commands without launching.

**S2.6 Combined analysis.** This is offline.

```bash
bash scripts/analyze_stage2.sh
```

It reads the three blocks and their checks, and writes `~/wp7-runs/analysis/stage2/` with 10,000 resamples and seed 20261031. The files are `tables.md`, `summary.json`, `cells.csv`, `groups.csv`, `paired.csv`, `digest_match.json`, `spoof.json` and `asks.json`.

## 7. Run records

Every script in section 4 to 6 writes a JSON record to `~/wp7-runs/records/<UTC start>_<name>.json` when it starts. It completes the record when it ends, and appends the finished record to `records.jsonl` there. A grid's record is written by `scripts/run_recorded.sh` inside the service, so it gets the grid's own exit code, even when the service is stopped. A record holds these fields:
- user, host, kernel and WSL distro
- start and end UTC, duration and exit code (plus a note when SIGTERM or SIGINT stopped it)
- the command and working directory, the run root and the systemd unit
- the artifacts repo branch and commit, and any uncommitted file under `hermes/`
- the harness clone's commit when it differs
- the Hermes commit and its dirty files
- the installed BEAR version, path and sha
- the model and embedder endpoints configured in `arms.py` (read from the file, no server contact)
- MemAvailable at start

To run any other step under a record, use `bash scripts/run_recorded.sh NAME -- COMMAND ...`. To list records, use `python3 -c "import json; [print(r['name'], r['start_utc'], r['exit_code']) for r in map(json.loads, open('$HOME/wp7-runs/records/records.jsonl'))]"`.

## 8. Stopping, continuing and failures

- **Stop after the current cell.** Run `touch ~/wp7-runs/<root>/STOP`. The runner ends the batch cleanly (`batch_end` in `logs/cells.jsonl`).
- **Stop now.** Run `systemctl --user stop <unit>`. The in-flight cell is lost. On continue, its partial files move to `aborted/` and the cell reruns. The run record notes the SIGTERM.
- **Continue.** Run the same launcher with `--continue`. `run.py --resume` runs only the planned cells that have no `cell_done` record. The order was fixed in `logs/plan.json` at the first start.
- **The runner stops itself** (a `batch_stopped` line, with a reason) in these cases:
  - more than 5% of cells errored
  - a guarded provenance field changed (a server restart on another image or model, a BEAR or Hermes change)
  - a sandbox leak was found after a cell
  - MemAvailable fell below 16 GB
  Read the reason before continuing. A changed container start time alone is only a warning.
- **Exit 137** means the memory cap killed the job. Do not raise a grid's cap above 24G.
- **WSL failure.** If WSL goes down mid-grid, do not retry in a loop. Bring WSL back, check the servers, rerun `provenance_check.py`, then continue with `--continue`.
- **Cell timeouts** show as exit -9 (each task has its own timeout plus 120 s). `status.py` counts them.

## 9. Script index

All scripts live in `hermes/scripts/`. Run shell scripts with `bash` and Python scripts with the interpreter shown.

| Script | What it does | Servers |
| --- | --- | --- |
| `env.sh` | shared settings and helpers (sourced by the others) | no |
| `install_bear.sh TAG` | clone a BEAR release, check its sha, install it editable | no |
| `validate.py` (`$WP7_PY`) | lint the corpus, validate the arm configs | no |
| `test_stage2_tasks.py` (`$WP7_PY`) | offline test of the stage-2 task changes | no |
| `provenance_check.py EXPECTED` (`$WP7_PY`) | compare servers, installs and material hashes with `expected/` | yes |
| `pregrid1.sh`, `pregrid2.sh` | pre-grid checks for each stage | yes |
| `resmoke_gate.py ROOT --stage N` (`$WP7_PY_ANALYSIS`) | re-smoke gates | no |
| `launch_stage1.sh`, `launch_block.sh N` | launch a grid service under a run record | yes |
| `run_recorded.sh`, `run_record.py` | run records | no |
| `status.py ROOT`, `watch.py ROOT LINE N UNIT` (`python3`) | progress, errors, timeouts, version checks | no |
| `post_stage1.sh`, `post_block.sh N`, `analyze_stage2.sh` | checks and analysis | no |
| `stage2_settings.sh` | k sweep and annotation cost from stage 1 | no |
| `results_extras.py ROOT OUT` (`python3`) | `checks_summary.json` and `run_info.json` for stage 1 | no |
| `tist-capped` | copy of the memory-cap wrapper | no |
| `expected/` | expected fingerprints and material hashes per stage, the runner venv's package list | no |
| `diagnostics/` | one-off look-ups and tests from the agent runs (escape scan, anomaly look-ups, bridge tests, the original provenance re-checks, the script that wrote `expected/`) | some |

The runner itself is `hermes/run.py` (`run.py --help`). The checks are in `hermes/checks.py`, and the analyses in `hermes/analyze_stage1.py` and `hermes/analyze_stage2.py`. `hermes/CHANGES.md` explains every harness change and why.
