# Reproduction kit

This folder reruns every result of the revised TIST paper, "Retrieval-Governed Context". A person runs each script by hand from a WSL terminal. No agent and no session folder is involved. Each script writes a run record, the evidence for the statement that the author ran every script. `verify.py` then checks your outputs against the committed ones. `collect.py` writes every manuscript number with its source file, so the final numbers pass reads your outputs only.

`MANIFEST.md` maps every table, figure and in-text result of the manuscript to the script and file that produce it. It also gives each item its status:
- **needs Scott's run.** The paper attributes the number to BEAR 0.4.2 or to this revision. That covers every retrieval table, even where the value equals July's, and WP1, WP2, WP4, WP5, WP6, the Table 10 reruns and Hermes.
- **Scott, previous version.** A July or August 2026 run that the revision keeps unchanged, with no claim that it ran on 0.4.2. Examples are the Table 10 rows whose lists did not change and the ReAct and scale tables. Their scripts are here (`55_`), but they need no rerun.

`TEXT_FIXES.md` lists the numbers in the manuscript that no script can produce (stale text, prose estimates, no data), with a proposed change for each.

BEAR is pinned at the public tag v0.4.2 (commit `0d0718a`). The scripts only wrap the evaluation code in `evals/` and `hermes/`. They never write into `results/` or anywhere else in this checkout. Every output goes to `$REPRO_OUT`, by default `~/tist-repro`.

## Prerequisites

- Windows 11 with WSL2 Ubuntu 24.04. systemd on, mirrored networking. Under mirrored networking a Windows service answers on 127.0.0.1 inside WSL. Its LAN address does not.
- In WSL you need git, curl, python3, uv (the venv has no pip), systemd-run, flock and network access for the one-time setup. For the figure you need pdflatex (TeX Live in WSL, or MiKTeX on Windows).
- An NVIDIA GPU shared with the model servers. The scripts read it through Windows `nvidia-smi.exe`.
- The servers, all run by the model-server side:
  - Nemotron embeddings (`nvidia/llama-nemotron-embed-vl-1b-v2`, 2048 dimensions) on port 8360, with a `/health` endpoint
  - SGLang serving Qwen3.8-27B on port 8355 (Hermes only)
  - Ollama on Windows at 127.0.0.1:11434, with the tag `mistral-nemo-32k` for Table 10. Make it once in PowerShell, in this repo, with `ollama create mistral-nemo-32k -f Modelfile`.
- Hermes Agent 0.22.2 and its runner venv, for `60_` only. See `hermes/REPRODUCE.md`, section 1.

### One-time memory setup

Every job runs under `tist-capped` inside the user slice `tist.slice`. The slice is capped at 40G with no swap. A job over its own cap is killed alone, never the VM. Set it up once:

```bash
sudo loginctl enable-linger "$USER"          # user services outlive the terminal
# Delegate the memory controller to the user manager, if `cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.subtree_control`
# does not list "memory":
sudo mkdir -p /etc/systemd/system/user@.service.d
printf '[Service]\nDelegate=cpu cpuset io memory pids\n' | sudo tee /etc/systemd/system/user@.service.d/delegate.conf
sudo systemctl daemon-reload                  # then restart WSL (wsl --shutdown from Windows)
systemctl --user set-property tist.slice MemoryMax=40G MemorySwapMax=0
install -m 755 reproduce/bin/tist-capped ~/bin/tist-capped
```

`00_setup.sh` checks all of this and stops with the missing piece. `--configure-slice` runs the `set-property` line for you. It installs `~/bin/tist-capped` from `reproduce/bin/` when it is missing. It never replaces a copy that differs.

## The scripts

All scripts take `--dry-run`. It prints every command the script would run and checks the prerequisites it can check without starting anything heavy. A dry run sends no request to a server and reads no card. `--help` prints the script's header.

| Script | Reproduces (MANIFEST ids) | Needs | Memory cap | GPU | Time | Outputs |
|---|---|---|---|---|---|---|
| `00_setup.sh` | nothing. Venv, BEAR clones, models, repo clones, `verify_env.py`. `--update` brings existing clones up to `tist-r2` | CPU, network once, 8360 `/health` | 4G | none | 15 min (models extra), `--update` 1 min | `setup/`, `wp0/`, `clones/` |
| `10_cpu_retrieval.sh` | Tables 6, 8, 9 (BGE, BGE-M3, Qwen3-0.6B, BM25, hash), Tables 7, 13 to 17, 23 to 28, mand-only rows, Table 10 lists, WP4 lists, mandatory tables (T06 to T09, T13 to T17, T23 to T28, X53, X54) | CPU only (8360 `/health` once) | 8G lexical, 20G dense, per step | none | 13 to 15 h (`--with-controls` adds 3 h) | `wp0/` |
| `15_cpu_invariants_baselines.sh` | invariants, budget binding, BM25 checks, BGE-M3 leakage, WP5 BGE rows and CPA, the CPU embedding stores (T18, XBB, T19, T20) | CPU only | 8G to 24G per step | none | 4 to 6 h | `clones/artifacts-wp256/results/`, `emb-cache/` |
| `20_gpu_local_embeddings.sh` | Qwen3-4B rows of Tables 6, 8, 9, its mand-only rows, its Table 10 and WP4 lists, the Qwen WP6 stores (T06, T08, T09, X54, T20) | local GPU | 12G host | start at 67,000 MiB or less, stop above 80,000. Allocator 11.2 GiB (WP0), 6 or 12 GiB (WP6) | 3 h | `wp0/`, `emb-cache/` |
| `30_nemotron.sh` | Nemotron rows of Tables 6, 8, 9, its lists, the threshold diagnosis, the Nemotron WP2/WP6 stores, the Nemotron rows of Table 19 (T06, T08, T09, X42, T19, T20) | port 8360 | 4G to 16G per step | none locally | 2 to 3 h | `wp0/`, `emb-cache/`, `clones/artifacts-wp256/results/` |
| `40_robustness_from_stores.sh` | tag noise, over-restriction, leakage, giveaways, mandatory coverage (T17b, T20) | CPU only, after 15, 20 and 30 | 8G to 16G per step | none | 1 h | `clones/artifacts-wp256/results/` |
| `50_e2e_ollama.sh` | Table 10 rows rerun on 0.4.2 and the drift controls (T10a) | Ollama on 11434 | 4G client | start at 67,000 MiB or less, 81,000 before each row | 30 to 40 min | `e2e_rerun/` |
| `55_e2e_previous_version.sh PART` | the previous-version runs: Table 10 July rows, monolithic row, Tables 11 and 12, Appendix A tags (T10b, T10c, T11, T12, AA). Optional | Ollama (Anthropic API for `tags-api`) | 16G client | as the Ollama model needs | 4 to 9 h per part | `previous/PART/` |
| `65_authorship.sh --part P` | the authorship ablation: the tags again with Qwen3.8-27B, then MetaTool+Tags, MetaTool+QueryTags-top5 (seven backends) and Table 7 under both taggers (XAUTH). Parts tag, cpu, gpu, nemotron, analyze, test | tag 8355, cpu CPU, gpu local GPU, nemotron 8360 | 8G (tag), 8G or 20G (cpu), 12G (gpu), 8G (nemotron) | gpu part as 20_ | tag 3 to 5 h, cpu about 5 h, gpu 40 min, nemotron 45 min, analyze 15 min | `authorship/`, `wp0/stage/v042/tb_auth_*` |
| `60_hermes.sh STEP` | Hermes stage 1 and stage 2 (XH) | ports 8355 and 8360 | 16G grid, 4G to 8G otherwise | none locally | about 50 h of grids | `hermes/` |
| `70_assemble.sh` | WP4 analysis, mandatory tables, prompt-size checks, the derived numbers no eval script writes (`reproduce/derive/`, `evals/diag_gate_coverage.py`), then gathers everything (T21, XE2Eb, X33, X42s, XE2Ea, X53) | CPU only | 16G | none | 20 to 40 min | `derived/`, `assembled/` |
| `80_figures.sh` | Figure 2 (fig:pipeline), drawn in TikZ (F2) | CPU, pdflatex, the paper repo | none | none | 1 min | `figures/` |
| `90_verify.sh` | runs `verify.py` and `collect.py` | CPU only | 8G | none | a few minutes | `verify/`, `numbers/` |
| `status.sh` | shows services, logs, the last run records and the card | nothing | none | reads the card | instant | none |

Times are wall-clock estimates from the October runs on this machine (28 cores, RTX PRO 6000). Memory caps are per step. The slice holds 40G for everything at once.

## Run order

Run the windows in this order. Inside a window, run the scripts one after another. Two CPU scripts at once can pass the 40G slice cap.

| Window | Step | Script | Time |
|---|---|---|---|
| 1. CPU only | setup | `00_setup.sh --download-models` (once) | 15 min |
| | WP0 retrieval | `10_cpu_retrieval.sh` | 13 to 15 h |
| | WP1, WP5 CPU, BM25, BGE-M3, CPU stores | `15_cpu_invariants_baselines.sh` | 4 to 6 h |
| 2. local GPU | Qwen3-4B lanes, its mand-only rows, Qwen stores | `20_gpu_local_embeddings.sh` | 3 h |
| 3. Nemotron (8360) | Nemotron rows, stores, WP5 | `30_nemotron.sh` | 2 to 3 h |
| 4. CPU only | WP2, WP6 from the stores | `40_robustness_from_stores.sh` | 1 h |
| 5. Ollama (11434) | Table 10 reruns | `50_e2e_ollama.sh` | 40 min |
| 6. Hermes (8355, 8360) | stage 1, settings, blocks 1 to 3, analysis | `60_hermes.sh STEP`, one step at a time (see its `--help`) | about 51 h |
| 6b. authorship (8355, then CPU, GPU, 8360) | the tags again, the reruns, the analysis | `65_authorship.sh --part tag`, then `--part cpu`, `--part gpu` (in a GPU window), `--part nemotron` (in a Nemotron window), `--part analyze` | about 11 h |
| 7. CPU only | analysis and assembly | `70_assemble.sh` | 30 min |
| | figure | `80_figures.sh` | 1 min |
| | check and numbers | `90_verify.sh` | 5 min |

The total is about 90 hours of running, about 37 hours without Hermes. The authorship ablation adds about 11 hours, and its parts can share the windows of 20_, 30_ and 60_. Windows 2, 3, 5 and 6 need the GPU or a server and wait for the model-server session's OK. `40_` needs the stores of 15, 20 and 30, so it comes after them although it uses only the CPU. `70_` and `90_` can run at any time. They assemble and check what exists so far, and list the rest as NOT RUN.

`55_` is optional. Its parts rerun the previous-version results, which the revision keeps.

### Before a later window: update the clones

Every run happens in clones of this repo below `$REPRO_OUT`, made by `00_setup.sh`. When `tist-r2` gains commits between windows (a fix to the kit or to `evals/`), bring the clones up to date before the next window:

```bash
git -C /path/to/this/checkout log --oneline -3     # the commits the clones will get
bash reproduce/00_setup.sh --update --dry-run      # what it would do
bash reproduce/00_setup.sh --update
```

`--update` fast-forwards every existing clone to `tist-r2` of this checkout and does nothing else. Outputs of earlier runs stay where they are. It refuses while any kit script, WP0 lane or WP7 grid is running, and for a clone with local changes outside `results/`. It also refuses when a new commit touches a result file that a run of yours changed in that clone. The run record lists each clone's old and new commit.

## Before you run

- [ ] The Windows task `wsl-keepalive` shows Running (`Get-ScheduledTask wsl-keepalive` in PowerShell). Long scripts run as user services, which die with WSL. The scripts check this through `powershell.exe` and stop if it is not Running.
- [ ] Nothing else is booked on the GPU or on ports 8355, 8360 and 11434 for your window. The model-server session coordinates that. Ask it before windows 2, 3, 5 and 6, and tell it when each ends.
- [ ] No other GPU job runs. The GPU scripts check for the kit's services, the WP0 lane services and any `tist-wp7-*` grid, and refuse to start beside one.
- [ ] Your checkout is committed. The clones get the committed state only, and the run record names the commit.
- [ ] A dry run of the script passes (`bash reproduce/NN_name.sh --dry-run`).

## How a script runs

- **Long scripts run as user services.** `10_` to `55_`, and the parts tag, cpu, gpu and nemotron of `65_`, start the service `tist-repro-NN`, which runs the same script with `--foreground`, and return at once. They print the commands to follow it:

  ```bash
  systemctl --user status tist-repro-10 --no-pager
  tail -f ~/tist-repro/logs/10_cpu_retrieval.log
  bash reproduce/status.sh
  ```

  Add `--wait` to follow the log in the terminal until the service ends. `--foreground` runs the script in the terminal instead of a service. `60_hermes.sh` runs in the terminal, and its grid steps start their own services (`tist-wp7-*`).
- **The final line.** Every script ends with one line, `OK: <script>` or `FAILED: <script>: <reason>`. For a service, that line ends its log.
- **Run records.** Each run writes `$REPRO_OUT/runlog/<script>-<UTC time>.json` and appends it to `runlog/records.jsonl`. A record holds:
  - the user, host, kernel and WSL distro
  - start and end times, the exit code, the status and the failure reason
  - the artifacts commit, its branch and any uncommitted tracked file, and the commit of every clone
  - the installed BEAR version, its source sha (`BEAR_GIT_SHA`) and the hash of its `bear/` tree, and the v0.1.10 clone
  - the Python stack (torch, transformers, sentence-transformers, numpy, scipy and others)
  - the snapshot id of every cached Hugging Face model
  - the endpoints the script used, with Nemotron's `/health`, Ollama's version and tag digests, or SGLang's server info
  - every command line it ran, with its start and end times and exit code
  - notes, such as an expected step failure

  Dry runs write their records to `runlog/dryrun/`.
- **Resuming.** Every script can be run again after a stop or a failure. Finished steps are skipped. The kit marks them in `$REPRO_OUT/state/`, and the WP0 lanes mark theirs in `wp0/logs/<step>.done`. To redo a step, remove its marker.
- **Stopping.** `systemctl --user stop tist-repro-NN` stops a service. Each step runs in its own scope or service, with its own process group. Never use pattern kills (`pkill -f`, `killall`).
- **Failing loudly.** A failed step stops the script with its reason. Three steps fail in a correct run, as they did in October, and the script notes them in the run record:
  - `ablation_lexical` in lane lex042. `eval_ablation.py` also loads BGE, which that lane refuses. The manuscript does not use it.
  - `decomposed_q4b` in lane dense042. Two Qwen3-4B copies pass the 20G cap. Lane manddense042 reruns it with two models kept.
  - the ToolBench rows of `tb_qwen4b` and the batch-8 Qwen3-4B lists in lane gpuq4b042. They run out of memory inside the 11.2 GiB cap. Lane gpuq4b042fix reruns them at batch 2, as reported.

  Anything else that fails stops the script. No step falls back to hash embeddings. BEAR 0.4.2 raises when a model fails to load, the WP0 runner's `assert_not_hash` and `tistr2_common.check_real_model` stop any run whose embedder is in hash mode, and ITR's own fallback is caught by `fallback_audit.py` (`70_ --with-controls`).

## Outputs

```
$REPRO_OUT/                     default ~/tist-repro
  runlog/                       run records (the evidence)
  logs/                         one log per script
  state/                        step markers
  setup/                        verify_env.json, the requirements file used
  wp0/                          WP0_ROOT: lane clones, stage/<version>/<step>/, logs/, wp4/, diag/, ...
  clones/                       artifacts-wp256, artifacts-hermes, artifacts-previous
  emb-cache/                    WP2/WP6 embedding stores
  e2e_rerun/                    Table 10 reruns
  hermes/                       WP7 run roots, analysis/, records/
  previous/                     55_ outputs per part
  figures/                      Figure1-pipeline.pdf
  assembled/                    everything above in this repo's layout (70_)
  verify/                       verify.md, verify.json
  numbers/                      numbers.md, numbers.json
```

## Checking against the committed results

`verify.py` compares every file of `assembled/` with the committed file of the same path. A `.gz` on either side is read through. Each file gets a class from its path, and each class has one rule. All rules sit in `TOLERANCE` and `CLASS_RULES` at the top of `verify.py`.

| Class | Which files | Rule |
|---|---|---|
| exact | deterministic CPU results: BM25, hash, BGE, BGE-M3, Qwen3-0.6B and Qwen3-4B on the CPU, invariants, budget binding, WP5 with BGE, mandatory tables | every number equal, with a slack of 1e-9 for float printing. Strings equal |
| gpu | Qwen3-4B in bf16 (WP0), the Qwen fp16 stores (WP6), anything embedded by the GPU-served Nemotron, WP4 | every point estimate that the committed file gives a 95% CI for lies inside that CI. A float without a CI agrees to 3 decimals. Precision and batch size move values at rounding level |
| ollama | Table 10 reruns and July runs | tool and exact accuracy, and governed minus ungated deltas, within 0.01. The measured executor drift on identical lists is at most 0.0082. Retrieval metrics of the lists must be exact |
| llm | Gemma 4 at temperature 1.0 (Table 12), Hermes grids, the authorship ablation's runs | every point estimate with a committed CI lies inside it. The committed Hermes results are agent runs on an older harness, so read their FAILs rather than count them |
| tags | the tag files the authorship ablation writes | at least 99% of the committed items present, and at least 90% of the shared items with the identical tags. The retrieval runs with those tags (`tb_auth_*`) and the analysis use the llm rule |
| info | GPU-made top-k lists, the 0.1.10 comparison | compared, for reading only |
| skip | logs, manifests, provenance records, the hand-written report, PDFs | not compared |

Keys that hold run facts are never compared: provenance, times, latencies, paths, hosts and users.

The table prints one line per file: PASS, FAIL, INFO, NEW (no committed file of that name), SKIP, or NOT RUN (the manuscript needs the file and you have not produced it yet). `--strict` counts NOT RUN as a failure. Use it for the final check.

Some committed files are older than your runs. Several WP2, WP5 and WP6 rows were committed from BEAR 0.4.0, and the committed Hermes tables come from agent runs. Your 0.4.2 runs replace them, so a FAIL there can be a real 0.4.0 to 0.4.2 change. The detail column names the value.

## The numbers file

`collect.py` reads `assembled/` and writes `numbers/numbers.md` and `numbers.json`. For each MANIFEST item it lists the source files with their sha256, every number with its 95% CI, source file and JSON path, and the output tables the numbers are printed in. It also computes what the October numbers pass computed by hand:
- governed minus ungated per backend for Tables 6, 8 and 9, with paired t, p, Wilcoxon p and d = mean(diff) / sd(diff)
- the cross-backend d against BEAR+BGE in the Section 4.2 text
- for Table 10, the BEAR+BGE-M3 rerun against the July ungated row, and the drift of the BGE controls
- for Table 14, McNemar exact p, Cohen's h and the Clopper-Pearson bound for CPA

Items that need your run are read from `assembled/` only. Items from the previous version are read from `assembled/` when `55_` reran them, else from the committed file of that run. `collect.py` exits 1 while an item that needs your run is incomplete.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `REPRO_OUT` | `~/tist-repro` | every output |
| `REPRO_VENV` | `~/.venvs/tist-repro` | the kit's venv (Python 3.12) |
| `REPRO_EMB_CACHE` | `$REPRO_OUT/emb-cache` | WP2/WP6 embedding stores (`TIST_EMB_CACHE`) |
| `REPRO_NEMOTRON_URL` | `http://127.0.0.1:8360` | Nemotron server |
| `REPRO_OLLAMA_ROOT` | `http://127.0.0.1:11434` | Ollama |
| `REPRO_SGLANG_URL` | `http://127.0.0.1:8355` | SGLang (Hermes) |
| `REPRO_GPU_START_MIB`, `REPRO_GPU_STOP_MIB`, `REPRO_OLLAMA_ROW_MIB` | 67000, 80000, 81000 | card limits |
| `REPRO_SLICE_MAX_GB` | 25 | slice memory other than page cache before a step starts |
| `REPRO_SKIP_KEEPALIVE_CHECK` | 0 | 1 skips the wsl-keepalive check |
| `WP0_GPU_MAXWAIT` | 7200 | seconds a WP0 GPU step waits for the card |
| `WP7_RUNS` | `$REPRO_OUT/hermes` | Hermes run roots |
| `PAPER_REPO` | `../paper-retrieval-governed-context` | the paper repo, for `80_` |

Some paths are fixed, because the wrapped runners read them:
- `~/tist-evals/bear-v0.4.2` (BEAR v0.4.2 with `BEAR_GIT_SHA`) and `~/tist-evals/bear-v0110` (v0.1.10)
- `~/bin/tist-capped` and `~/tist-gpu.lock`

`00_setup.sh` makes the two clones if they are missing and checks them if they exist.

## Known gaps

`MANIFEST.md` lists every gap: results with no script, numbers worked out by hand, logs without JSON, and scripts that hold personal paths or LAN addresses. In short:
- A few numbers in the text have no possible script (stale text, prose estimates, no data). `TEXT_FIXES.md` lists them with a proposed change. Every other number is computed, by an eval script, by `reproduce/derive/`, or by `collect.py` from the per-query arrays.
- The kit does not call `evals/wp0_v040/relaunch_042.sh`, which copies the checkout's working-tree WP0 scripts into the clones and starts lanes side by side. It runs the committed WP0 scripts, one lane at a time, with the same lane settings.
- `evals/run_wp256.sh` labels its v042 modes with the candidate sha `9d085b4` in `BEAR_SOURCE_SHA`. The code is the same as v0.4.2. The result files also record `bear_export_sha` from `BEAR_GIT_SHA`, and the run record holds the real sha.

## Style

The kit's docs and messages follow the author's style: short sentences, no semicolons, no em dashes, and colons only to introduce a list.
