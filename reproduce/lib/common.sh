# reproduce/lib/common.sh: settings and helpers shared by the numbered scripts.
# Source it, do not run it. Every setting can be overridden from the
# environment before a script starts. Nothing here starts a job by itself.

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

REPRO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ART=$(cd "$REPRO_DIR/.." && pwd)                  # the artifacts checkout that holds this kit

REPRO_OUT=${REPRO_OUT:-$HOME/tist-repro}            # every output of the kit goes below this
REPRO_VENV=${REPRO_VENV:-$HOME/.venvs/tist-repro}   # made by 00_setup.sh
REPRO_PY=$REPRO_VENV/bin/python
REPRO_EMB_CACHE=${REPRO_EMB_CACHE:-$REPRO_OUT/emb-cache}   # WP2/5/6 embedding stores
REPRO_NEMOTRON_URL=${REPRO_NEMOTRON_URL:-http://127.0.0.1:8360}
REPRO_OLLAMA_ROOT=${REPRO_OLLAMA_ROOT:-http://127.0.0.1:11434}
REPRO_SGLANG_URL=${REPRO_SGLANG_URL:-http://127.0.0.1:8355}
REPRO_SLICE_MAX_GB=${REPRO_SLICE_MAX_GB:-25}        # slice memory other than page cache, before a step
# Every Qwen3-4B encode on the GPU (20_ and 65_) uses this fixed batch, under the
# 11.2 GiB allocator cap. The October rehearsal ran +Tags and +QueryTags at 8.
export REPRO_Q4B_BATCH=${REPRO_Q4B_BATCH:-2}

# Fixed paths. The wrapped runners (run_wp0_v040.sh, run_e2e_rerun.sh,
# run_wp256.sh, run_v042_*.sh, run_qwen_gpu.sh) read these and cannot be
# pointed elsewhere, so the kit uses them as they are.
BEAR_SRC=$HOME/tist-evals/bear-v0.4.2
BEAR0110_SRC=$HOME/tist-evals/bear-v0110
TC=$HOME/bin/tist-capped
GPU_LOCK=$HOME/tist-gpu.lock

BEAR_TAG=v0.4.2
BEAR_SHA=0d0718a39a0b0788ef5cca4689352462b830494c
BEAR_VERSION=0.4.2
BEAR0110_TAG=v0.1.10
BEAR0110_SHA=cdba2174d715494ec4f22c098386487002ec492f
BEAR_URL=${REPRO_BEAR_URL:-https://github.com/snhwang/bear.git}

WP0_DIR=$REPRO_OUT/wp0                      # WP0_ROOT of the WP0 lanes (clones, stage, logs)
CLONES=$REPRO_OUT/clones
WP256_CLONE=$CLONES/artifacts-wp256         # WP1, WP2, WP5, WP6 runs
HERMES_CLONE=$CLONES/artifacts-hermes       # WP7
PREV_CLONE=$CLONES/artifacts-previous       # July and August scripts (55)
AUTH_CLONE=$CLONES/artifacts-authorship     # the authorship ablation (65)
ASSEMBLED=$REPRO_OUT/assembled              # repo-shaped tree that verify.py and collect.py read

SMI=/mnt/c/Windows/System32/nvidia-smi.exe
GPU_START_MIB=${REPRO_GPU_START_MIB:-67000}   # start a local GPU model only at or below this
GPU_STOP_MIB=${REPRO_GPU_STOP_MIB:-80000}     # stop it above this
OLLAMA_ROW_MIB=${REPRO_OLLAMA_ROW_MIB:-81000}  # Ollama: card limit before each row, model resident

# The Hugging Face models the local backends load (offline, from the cache).
HF_MODELS_RETRIEVAL="BAAI/bge-base-en-v1.5 BAAI/bge-m3 Qwen/Qwen3-Embedding-0.6B Qwen/Qwen3-Embedding-4B \
ToolBench/ToolBench_IR_bert_based_uncased BAAI/bge-reranker-base sentence-transformers/all-MiniLM-L6-v2"
HF_MODELS_TOKENIZERS="mistralai/Mistral-Nemo-Instruct-2407 google/gemma-4-12B-it"

export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}
# Both service URLs, under the names the eval code reads.
export NEMOTRON_URL=$REPRO_NEMOTRON_URL TIST_NEMOTRON_URL=$REPRO_NEMOTRON_URL
export TIST_EMB_CACHE=$REPRO_EMB_CACHE
export TIKTOKEN_CACHE_DIR=${TIKTOKEN_CACHE_DIR:-$REPRO_OUT/tiktoken-cache}   # filled by 00_setup.sh --download-models
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1

# ---------------------------------------------------------------------------
# Arguments, output and the final line
# ---------------------------------------------------------------------------

DRY_RUN=0
FOREGROUND=0
WAIT=0
ARGS_REST=()
SCRIPT_PATH=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
SCRIPT_NAME=$(basename "$0" .sh)
REPRO_FAIL_REASON=""
REPRO_OK_NOTE=""
REPRO_RECORD=${REPRO_RECORD:-}
REPRO_RUNNING_MARK=""

say()  { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
warn() { say "WARNING: $*"; }
die()  { REPRO_FAIL_REASON="$*"; exit 1; }
hr()   { printf '%s\n' "------------------------------------------------------------------------"; }

# The header comment of the calling script (lines 2 onward that start with #).
repro_help() {
  awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$SCRIPT_PATH"
}

# repro_parse_args "$@": the common flags. Everything else stays in ARGS_REST.
repro_parse_args() {
  while [ $# -gt 0 ]; do
    case $1 in
      -n|--dry-run) DRY_RUN=1 ;;
      --foreground) FOREGROUND=1 ;;
      --wait) WAIT=1 ;;
      -h|--help) repro_help; exit 0 ;;
      *) ARGS_REST+=("$1") ;;
    esac
    shift
  done
  # From here on, any exit prints the final OK or FAILED line.
  trap repro_finish EXIT
}

# The EXIT trap: close the run record and print the final line.
repro_finish() {
  local rc=$?
  trap - EXIT
  [ -n "${REPRO_RUNNING_MARK:-}" ] && rm -f "$REPRO_RUNNING_MARK"
  local status=OK
  if [ "$rc" -ne 0 ] || [ -n "$REPRO_FAIL_REASON" ]; then
    status=FAILED
    [ "$rc" -eq 0 ] && rc=1
    [ -n "$REPRO_FAIL_REASON" ] || REPRO_FAIL_REASON="exit code $rc"
  fi
  if [ -n "$REPRO_RECORD" ] && [ -f "$REPRO_RECORD" ]; then
    local note=$REPRO_OK_NOTE
    [ "$DRY_RUN" = 1 ] && note=""
    python3 "$REPRO_DIR/lib/run_record.py" end "$REPRO_RECORD" --exit-code "$rc" --status "$status" \
      --reason "$REPRO_FAIL_REASON" --note "$note" >/dev/null 2>&1 \
      || echo "(could not close the run record $REPRO_RECORD)"
    echo "run record: $REPRO_RECORD"
  fi
  hr
  if [ "$status" = OK ] && [ "$DRY_RUN" = 1 ]; then
    echo "OK: $SCRIPT_NAME (dry run. The commands above are what a real run does. Nothing was run)"
  elif [ "$status" = OK ]; then
    echo "OK: $SCRIPT_NAME${REPRO_OK_NOTE:+. $REPRO_OK_NOTE}"
  else
    local dry=""
    [ "$DRY_RUN" = 1 ] && dry=" (dry run)"
    echo "FAILED: $SCRIPT_NAME$dry: $REPRO_FAIL_REASON"
  fi
  exit "$rc"
}

# repro_begin: start of every script, after repro_parse_args. Opens the run
# record and sets the EXIT trap. A service worker appends to its log file.
repro_begin() {
  if [ -n "${REPRO_LOG:-}" ]; then
    mkdir -p "$(dirname "$REPRO_LOG")"
    exec >>"$REPRO_LOG" 2>&1
  fi
  hr
  say "$SCRIPT_NAME, $(date -u +%FT%TZ), user $(id -un) on $(hostname)"
  say "artifacts checkout: $ART ($(git -C "$ART" rev-parse --short HEAD 2>/dev/null || echo 'no git'))"
  say "outputs: $REPRO_OUT"
  [ "$DRY_RUN" = 1 ] && say "DRY RUN: commands are printed, prerequisites are checked, nothing heavy runs"
  local stamp sub=""
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  [ "$DRY_RUN" = 1 ] && sub=/dryrun
  if [ -z "$REPRO_RECORD" ]; then
    REPRO_RECORD=$REPRO_OUT/runlog$sub/$SCRIPT_NAME-$stamp.json
  fi
  mkdir -p "$(dirname "$REPRO_RECORD")"
  python3 "$REPRO_DIR/lib/run_record.py" start "$REPRO_RECORD" --script "$SCRIPT_NAME" \
    --dry-run "$DRY_RUN" --unit "${REPRO_UNIT:-}" -- "$SCRIPT_PATH" "${ARGS_REST[@]}" \
    || { REPRO_RECORD=""; die "could not write the run record"; }
  export REPRO_RECORD
  # A marker while a real run is in progress. 00_setup.sh --update refuses to
  # move the clones while one exists for a live process.
  if [ "$DRY_RUN" = 0 ]; then
    mkdir -p "$REPRO_OUT/state/running"
    REPRO_RUNNING_MARK=$REPRO_OUT/state/running/$SCRIPT_NAME.$$
    echo "$$ $(date -u +%FT%TZ) ${REPRO_UNIT:-terminal}" > "$REPRO_RUNNING_MARK"
  fi
  say "run record: $REPRO_RECORD"
  [ -n "${SLURM_JOB_ID:-}" ] && record_note "Slurm job $SLURM_JOB_ID (${SLURM_JOB_NAME:-}), submitted by ${SLURM_JOB_USER:-$(id -un)}, $(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | grep -o 'Comment=.*' | head -1)"
  return 0
}

record_note() {  # record_note TEXT: a line in the run record (also printed)
  say "note: $*"
  [ -n "$REPRO_RECORD" ] && python3 "$REPRO_DIR/lib/run_record.py" note "$REPRO_RECORD" -- "$*" >/dev/null 2>&1
  return 0
}

# ---------------------------------------------------------------------------
# Running commands
# ---------------------------------------------------------------------------

# run_cmd LABEL [-C DIR] [-o FILE] -- CMD ARGS...
# Prints the command, runs it (unless dry run), records it with its exit code
# in the run record, and returns that exit code. -C runs it in DIR. -o appends
# its output to FILE instead of the terminal.
run_cmd() {
  local label=$1 dir="" out=""
  shift
  while :; do
    case ${1:-} in
      -C) dir=$2; shift 2 ;;
      -o) out=$2; shift 2 ;;
      --) shift; break ;;
      *) break ;;
    esac
  done
  local shown
  shown=$(printf '%q ' "$@")
  echo "+ ${dir:+(cd $dir) }${shown% }${out:+ >> $out 2>&1}"
  [ "$DRY_RUN" = 1 ] && return 0
  local t0 rc
  t0=$(date -u +%FT%TZ)
  [ -n "$out" ] && { mkdir -p "$(dirname "$out")"; say "$label: output goes to $out"; }
  if [ -n "$out" ]; then
    (cd "${dir:-.}" && "$@") >>"$out" 2>&1
  else
    (cd "${dir:-.}" && "$@")
  fi
  rc=$?
  python3 "$REPRO_DIR/lib/run_record.py" cmd "$REPRO_RECORD" --label "$label" --rc "$rc" \
    --start "$t0" --cwd "${dir:-$PWD}" -- "$@" >/dev/null 2>&1
  say "$label: exit $rc"
  [ "$rc" -eq 137 ] && say "$label: exit 137 means its memory cap killed it"
  return "$rc"
}

# Step markers make a script resumable: a step that finished is skipped next time.
state_dir() { echo "$REPRO_OUT/state/$SCRIPT_NAME"; }
step_done() { [ -f "$(state_dir)/$1.done" ]; }
mark_done() { [ "$DRY_RUN" = 1 ] && return 0; mkdir -p "$(state_dir)"; date -u +%FT%TZ > "$(state_dir)/$1.done"; }

# rstep NAME [-C DIR] -- CMD...: a resumable step. Skips if done, fails loudly otherwise.
rstep() {
  local name=$1
  shift
  if step_done "$name"; then
    say "skip $name (done $(cat "$(state_dir)/$name.done"). Remove $(state_dir)/$name.done to rerun it"
    return 0
  fi
  say "step $name"
  run_cmd "$name" "$@" || die "step $name failed (exit $?). See the output above"
  mark_done "$name"
}

# slice_wait: wait until tist.slice holds at most REPRO_SLICE_MAX_GB other
# than page cache (memory.current - file + shmem), as evals/run_qwen_gpu.sh
# does. Raw memory.current never drops while the slice keeps old page cache.
slice_wait() {
  [ "$DRY_RUN" = 1 ] && { echo "+ (wait until tist.slice holds <= ${REPRO_SLICE_MAX_GB} GB other than page cache)"; return 0; }
  # Inside a Slurm job, Slurm's memory limits decide when jobs start, and this job's own cgroup
  # caps it. tist.slice is not used there, so there is nothing to wait for.
  [ -n "${SLURM_JOB_ID:-}" ] && return 0
  local cg cur file shmem used max=$((REPRO_SLICE_MAX_GB * 1024 * 1024 * 1024))
  cg=/sys/fs/cgroup$(systemctl --user show tist.slice -p ControlGroup --value 2>/dev/null)
  [ -r "$cg/memory.current" ] || die "cannot read $cg/memory.current (is tist.slice set up? see 00_setup.sh)"
  while :; do
    cur=$(cat "$cg/memory.current")
    file=$(awk '$1 == "file" {print $2}' "$cg/memory.stat")
    shmem=$(awk '$1 == "shmem" {print $2}' "$cg/memory.stat")
    used=$((cur - file + shmem))
    (( used <= max )) && return 0
    say "tist.slice holds $((used / 1048576)) MiB other than page cache (limit ${REPRO_SLICE_MAX_GB} GB), waiting"
    sleep 60
  done
}

# capped MEM -- CMD...: one command in its own memory-capped scope in tist.slice.
capped() {
  local mem=$1
  shift
  [ "${1:-}" = "--" ] && shift
  "$TC" --mem "$mem" -- "$@"
}

# ---------------------------------------------------------------------------
# Long scripts run as transient user services
# ---------------------------------------------------------------------------

# maybe_launch UNIT: unless --foreground or --dry-run, start this same script
# as the user service UNIT (memory cap 2G for the orchestrator, while every heavy
# step inside runs in its own capped scope) and exit. With --wait, follow the
# log until the service ends and exit with its result.
maybe_launch() {
  local unit=$1
  # A Slurm job is already the long-running unit: run here, after the quick checks.
  if [ -n "${SLURM_JOB_ID:-}" ] && [ "$DRY_RUN" = 0 ]; then
    FOREGROUND=1
    if declare -F preflight_launch >/dev/null; then
      say "quick checks (Slurm job $SLURM_JOB_ID)"
      preflight_launch
    fi
    return 0
  fi
  [ "$FOREGROUND" = 1 ] || [ "$DRY_RUN" = 1 ] && return 0
  [ -x "$TC" ] || die "$TC is missing (run 00_setup.sh)"
  if systemctl --user is-active -q "$unit" 2>/dev/null; then
    die "the service $unit is already running. Follow it with: bash $REPRO_DIR/status.sh"
  fi
  # Quick checks in the terminal before the service starts, if the script has them.
  if declare -F preflight_launch >/dev/null; then
    say "quick checks before launching"
    preflight_launch
  fi
  local stamp log rec
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  log=$REPRO_OUT/logs/$SCRIPT_NAME.log
  rec=$REPRO_OUT/runlog/$SCRIPT_NAME-$stamp.json
  mkdir -p "$REPRO_OUT/logs" "$REPRO_OUT/runlog"
  : >> "$log"
  local start_line
  start_line=$(($(wc -l < "$log") + 1))
  # A service does not inherit this shell. Hand it every override the scripts read.
  local passthru=() v
  while IFS= read -r v; do passthru+=("$v=${!v}"); done < <(compgen -e | grep -E '^(REPRO|AUTH|KIT|WP0)_' || true)
  (cd "$ART" && "$TC" --mem 2G --service "$unit" -- env \
      REPRO_OUT="$REPRO_OUT" REPRO_VENV="$REPRO_VENV" REPRO_EMB_CACHE="$REPRO_EMB_CACHE" \
      REPRO_NEMOTRON_URL="$REPRO_NEMOTRON_URL" REPRO_OLLAMA_ROOT="$REPRO_OLLAMA_ROOT" \
      REPRO_SGLANG_URL="$REPRO_SGLANG_URL" REPRO_SLICE_MAX_GB="$REPRO_SLICE_MAX_GB" \
      REPRO_GPU_START_MIB="$GPU_START_MIB" REPRO_GPU_STOP_MIB="$GPU_STOP_MIB" \
      REPRO_OLLAMA_ROW_MIB="$OLLAMA_ROW_MIB" REPRO_SKIP_KEEPALIVE_CHECK="${REPRO_SKIP_KEEPALIVE_CHECK:-0}" \
      ${OLLAMA_MODELS:+OLLAMA_MODELS="$OLLAMA_MODELS"} "${passthru[@]}"       REPRO_LOG="$log" REPRO_RECORD="$rec" REPRO_UNIT="$unit" \
      bash "$SCRIPT_PATH" --foreground "${ARGS_REST[@]}") \
    || die "could not start the service $unit"
  sleep 2
  cat <<EOF
Started the user service $unit. It runs this script with --foreground.
  status:    systemctl --user status $unit --no-pager
  progress:  tail -f $log
  overview:  bash $REPRO_DIR/status.sh
  stop:      systemctl --user stop $unit   (rerun the script later to continue: finished steps are skipped)
  run record: $rec
The log ends with a line "OK: $SCRIPT_NAME" or "FAILED: $SCRIPT_NAME: <reason>".
EOF
  if [ "$WAIT" = 1 ]; then
    echo "Waiting for $unit to end (Ctrl-C stops the waiting, not the service)."
    tail -n +"$start_line" -f "$log" &
    local tailpid=$!
    while systemctl --user is-active -q "$unit" 2>/dev/null; do sleep 20; done
    sleep 2
    kill "$tailpid" 2>/dev/null
    wait "$tailpid" 2>/dev/null
    local last
    last=$(tail -n +"$start_line" "$log" | grep -E "^(OK|FAILED): $SCRIPT_NAME" | tail -1)
    trap - EXIT
    echo "${last:-FAILED: $SCRIPT_NAME: the service ended without a final line (killed? see $log)}"
    [[ $last == OK:* ]] && exit 0
    exit 1
  fi
  trap - EXIT
  echo "OK: $SCRIPT_NAME launched as $unit (the result is the final line of $log)"
  exit 0
}

# kit_activity: print every kit run in progress (live markers and services),
# one per line. Prints nothing when the kit is idle.
kit_activity() {
  local m pid
  for m in "$REPRO_OUT"/state/running/*; do
    [ -f "$m" ] || continue
    pid=${m##*.}
    [ "$pid" = "$$" ] && continue
    if kill -0 "$pid" 2>/dev/null; then echo "running: $(basename "$m") ($(cat "$m"))"; else rm -f "$m"; fi
  done
  systemctl --user list-units --type=service --state=active,activating --no-legend 'tist-repro-*' 'wp0-*' 'tist-wp7-*'     2>/dev/null | awk '{print "service: " $1}'
}

# ---------------------------------------------------------------------------
# Prerequisite checks. Each one dies with a reason. None sends a request in a dry run.
# ---------------------------------------------------------------------------

need_cmd() { local c; for c in "$@"; do command -v "$c" >/dev/null 2>&1 || die "command not found: $c"; done; }
need_file() { local f; for f in "$@"; do [ -e "$f" ] || die "missing: $f"; done; }

check_tc() {
  [ -x "$TC" ] || die "$TC is missing. Install it with: install -m 755 $REPRO_DIR/bin/tist-capped $TC"
  cmp -s "$TC" "$REPRO_DIR/bin/tist-capped" || warn "$TC differs from $REPRO_DIR/bin/tist-capped"
}

check_slice() {
  local max swap
  if [ -n "${SLURM_JOB_ID:-}" ]; then
    # Inside a Slurm job the job's own cgroup is the cap (sbatch --mem), and tist.slice is not
    # used (model-server keeps it small once Slurm holds the share). Check that cap instead.
    local cg
    cg=$(awk -F: '$1 == "0" { print $3 }' /proc/self/cgroup 2>/dev/null)
    max=$(cat "/sys/fs/cgroup$cg/memory.max" 2>/dev/null)
    while [ "$max" = max ] && [ "$cg" != / ] && [ -n "$cg" ]; do
      cg=$(dirname "$cg"); max=$(cat "/sys/fs/cgroup$cg/memory.max" 2>/dev/null)
    done
    [[ $max =~ ^[0-9]+$ ]] || die "Slurm job $SLURM_JOB_ID has no finite memory cap in its cgroup ('${max:-unreadable}')"
    say "memory cap from Slurm job $SLURM_JOB_ID's cgroup: $(( max / 1024 ** 2 )) MiB"
    return 0
  fi
  max=$(systemctl --user show tist.slice -p MemoryMax --value 2>/dev/null)
  swap=$(systemctl --user show tist.slice -p MemorySwapMax --value 2>/dev/null)
  # model-server sets the cap (40G, or 24G while Scott is at the desk). Any finite cap from
  # 20G (a 16G grid plus a 4G check) to 40G is fine. Each job keeps its own cap inside it.
  [[ $max =~ ^[0-9]+$ ]] && (( max >= 20 * 1024 ** 3 && max <= 40 * 1024 ** 3 )) \
    || die "tist.slice MemoryMax is '${max:-unset}', not a cap from 20G to 40G. Run: systemctl --user set-property tist.slice MemoryMax=40G MemorySwapMax=0"
  [ "$swap" = 0 ] || die "tist.slice MemorySwapMax is '${swap:-unset}', not 0. Run: systemctl --user set-property tist.slice MemorySwapMax=0"
  local ctl=/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.subtree_control
  grep -qw memory "$ctl" 2>/dev/null || die "the memory controller is not delegated to the user manager ($ctl). See README, one-time setup."
}

check_keepalive() {
  [ "${REPRO_SKIP_KEEPALIVE_CHECK:-0}" = 1 ] && { warn "keepalive check skipped (REPRO_SKIP_KEEPALIVE_CHECK=1)"; return 0; }
  local ps=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe state
  [ -x "$ps" ] || die "cannot run powershell.exe from WSL to check the wsl-keepalive task (set REPRO_SKIP_KEEPALIVE_CHECK=1 if you checked it by hand)"
  state=$("$ps" -NoProfile -Command "(Get-ScheduledTask -TaskName wsl-keepalive -ErrorAction SilentlyContinue).State" 2>/dev/null | tr -d '\r ')
  [ "$state" = Running ] || die "the Windows task wsl-keepalive is '${state:-missing}', not Running. A long service dies with WSL. Start the task, or set REPRO_SKIP_KEEPALIVE_CHECK=1 if you know WSL stays up."
}

check_venv() {
  [ -x "$REPRO_PY" ] || die "no Python at $REPRO_PY. Run 00_setup.sh first."
  local v
  v=$("$REPRO_PY" -c "import importlib.metadata as m; print(m.version('bear'))" 2>/dev/null)
  [ "$v" = "$BEAR_VERSION" ] || die "BEAR in $REPRO_VENV is '${v:-not installed}', not $BEAR_VERSION. Run 00_setup.sh."
  [ -f "$BEAR_SRC/BEAR_GIT_SHA" ] || die "$BEAR_SRC/BEAR_GIT_SHA is missing. Run 00_setup.sh."
  [ "$(cat "$BEAR_SRC/BEAR_GIT_SHA")" = "$BEAR_SHA" ] || die "$BEAR_SRC/BEAR_GIT_SHA is not $BEAR_SHA"
  export BEAR_SOURCE_SHA=$BEAR_SHA
  export PATH=$REPRO_VENV/bin:$PATH VIRTUAL_ENV=$REPRO_VENV
}

check_bear0110() {
  [ "$(git -C "$BEAR0110_SRC" rev-parse HEAD 2>/dev/null)" = "$BEAR0110_SHA" ] \
    || die "$BEAR0110_SRC is not a clone at $BEAR0110_TAG ($BEAR0110_SHA). Run 00_setup.sh."
}

hf_cached() {  # hf_cached ORG/NAME: is the model in the local Hugging Face cache?
  local d=${HF_HOME:-$HOME/.cache/huggingface}/hub/models--${1//\//--}
  [ -d "$d/snapshots" ] && [ -n "$(ls -A "$d/snapshots" 2>/dev/null)" ]
}
check_hf_models() {
  local m missing=""
  for m in "$@"; do hf_cached "$m" || missing+=" $m"; done
  [ -z "$missing" ] || die "models not in the Hugging Face cache:$missing. Run 00_setup.sh --download-models (needs network)."
}

check_clone() {  # check_clone DIR: a clone of this repo exists; warn if it is behind
  local d=$1
  [ -d "$d/.git" ] || die "missing clone $d. Run 00_setup.sh."
  local h a
  h=$(git -C "$d" rev-parse HEAD)
  a=$(git -C "$ART" rev-parse HEAD)
  [ "$h" = "$a" ] || warn "$d is at ${h:0:7}, the checkout at ${a:0:7}. The clone's code runs. 00_setup.sh --update moves it."
}

# Card reading from Windows nvidia-smi.exe (MiB used). Not called in a dry run.
card_mib() { "$SMI" --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' \r'; }

check_card_start() {
  [ "$DRY_RUN" = 1 ] && { echo "+ (check: Windows nvidia-smi shows <= $GPU_START_MIB MiB in use)"; return 0; }
  local u
  u=$(card_mib)
  [[ $u =~ ^[0-9]+$ ]] || die "no reading from $SMI"
  (( u <= GPU_START_MIB )) || die "the card is at $u MiB, above the start limit $GPU_START_MIB. Ask the model-server session, then retry."
  say "card at $u MiB (start limit $GPU_START_MIB, stop limit $GPU_STOP_MIB)"
}

# Only one GPU or server job of the kit (and no WP7 grid) at a time.
check_no_gpu_jobs() {
  local mine=${REPRO_UNIT:-} u active=""
  for u in tist-repro-20 tist-repro-30 tist-repro-50 tist-repro-55 tist-repro-60 tist-repro-65 wp0-gpuq4b042 wp0-gpuq4b042fix \
           wp0-gpuq4b042gov wp0-e2erun tist-qwen-gpu; do
    [ "$u" = "$mine" ] && continue
    systemctl --user is-active -q "$u" 2>/dev/null && active+=" $u"
  done
  active+=$(systemctl --user list-units --type=service --state=active --no-legend 'tist-wp7-*' 2>/dev/null \
            | awk '{printf " %s", $1}')
  [ -z "$active" ] || die "another GPU or server job is active:$active. One at a time."
}

# GET a URL with a short timeout. Never called in a dry run.
http_get() { curl -sf -m "${2:-10}" "$1"; }

check_nemotron() {
  [ "$DRY_RUN" = 1 ] && { echo "+ (check: GET $REPRO_NEMOTRON_URL/health names nvidia/llama-nemotron-embed-vl-1b-v2)"; return 0; }
  local h
  h=$(http_get "$REPRO_NEMOTRON_URL/health") || die "no answer from $REPRO_NEMOTRON_URL/health (the Nemotron embedding server)"
  grep -q "llama-nemotron-embed-vl-1b-v2" <<<"$h" || die "$REPRO_NEMOTRON_URL/health does not name nvidia/llama-nemotron-embed-vl-1b-v2: $h"
  python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name nemotron --url "$REPRO_NEMOTRON_URL/health" >/dev/null 2>&1
  say "Nemotron at $REPRO_NEMOTRON_URL answers"
}

check_ollama_idle() {  # Ollama answers and holds no model
  [ "$DRY_RUN" = 1 ] && { echo "+ (check: GET $REPRO_OLLAMA_ROOT/api/ps lists no loaded model)"; return 0; }
  local ps
  ps=$(http_get "$REPRO_OLLAMA_ROOT/api/ps") || die "no answer from Ollama at $REPRO_OLLAMA_ROOT (a loaded model cannot be ruled out)"
  python3 -c 'import json,sys; sys.exit(1 if json.load(sys.stdin).get("models") else 0)' <<<"$ps" \
    || die "Ollama has a model loaded: $ps"
}
