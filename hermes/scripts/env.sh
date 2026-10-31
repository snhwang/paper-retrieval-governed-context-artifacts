# Shared settings for the WP7 scripts. Source it, do not run it.
# Every value can be overridden from the environment before a script starts.

WP7_SCRIPTS=${WP7_SCRIPTS:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
# This checkout's hermes/ directory: checks, analysis and the scripts themselves.
WP7_HERMES_DIR=${WP7_HERMES_DIR:-$(dirname "$WP7_SCRIPTS")}
# The hermes/ directory the runner (run.py) runs from. Stage 1 runs from a worktree at the
# stage-1 harness commit (see REPRODUCE.md). Stage 2 runs from this checkout.
WP7_HARNESS_DIR=${WP7_HARNESS_DIR:-$WP7_HERMES_DIR}
# The Hermes Agent checkout (commit d923a5eb), also read by run.py.
export WP7_HERMES_TREE=${WP7_HERMES_TREE:-$HOME/src/hermes-agent}
# Run roots, analysis output and run records. The default keeps these runs apart from the
# agent-launched ones in ~/tist-wp7/runs, which are not reported results.
WP7_RUNS=${WP7_RUNS:-$HOME/wp7-runs}
WP7_ANALYSIS=${WP7_ANALYSIS:-$WP7_RUNS/analysis}
WP7_RECORDS=${WP7_RECORDS:-$WP7_RUNS/records}
# Where install_bear.sh clones BEAR tags (bear-vX.Y.Z below it).
WP7_BEAR_BASE=${WP7_BEAR_BASE:-$HOME/tist-wp7}
# The venv with Hermes and BEAR (runner, checks, ksweep, annotation cost).
WP7_PY=${WP7_PY:-$HOME/.venvs/tist-spike/bin/python}
# A Python with numpy, scipy and pyyaml (the analysis scripts).
WP7_PY_ANALYSIS=${WP7_PY_ANALYSIS:-$HOME/.venvs/tist-evals/bin/python}
# The memory-cap wrapper (a copy is in this directory as tist-capped).
TIST_CAPPED=${TIST_CAPPED:-$HOME/bin/tist-capped}

export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}
export WP7_SCRIPTS WP7_HERMES_DIR WP7_HARNESS_DIR WP7_RUNS WP7_ANALYSIS WP7_RECORDS WP7_BEAR_BASE \
  WP7_PY WP7_PY_ANALYSIS TIST_CAPPED

wp7_mem_gb() { awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo; }

# wp7_step NAME MEM CMD...: run one step in a capped scope, print its exit code, return it.
wp7_step() {
  local name=$1 mem=$2; shift 2
  echo "== $name $(date -u +%T)"
  "$TIST_CAPPED" --mem "$mem" -- "$@"
  local rc=$?
  echo "== $name exit $rc"
  [ "$rc" -eq 137 ] && echo "   exit 137: the memory cap ($mem) killed this step"
  return "$rc"
}

# wp7_require_bear VERSION: stop unless the runner venv imports that BEAR version.
wp7_require_bear() {
  local want=$1 have
  have=$("$WP7_PY" -c "import importlib.metadata as m; print(m.version('bear'))" 2>/dev/null)
  if [ "$have" != "$want" ]; then
    echo "BEAR $want is needed here, the runner venv has '${have:-none}'. Run scripts/install_bear.sh v$want."
    return 1
  fi
}

# wp7_no_active_grid: stop if any WP7 grid service is active (one grid at a time on 8355).
wp7_no_active_grid() {
  local active
  active=$(systemctl --user list-units --type=service --state=active --no-legend 'tist-wp7-*' 2>/dev/null)
  if [ -n "$active" ]; then
    echo "a WP7 grid service is active, wait for it to end:"; echo "$active"
    return 1
  fi
}

# Run records. wp7_record_begin NAME [ROOT] writes the start of a record for this script and
# makes the EXIT trap write its end (exit code, end time). The record path is printed.
wp7_record_begin() {
  local name=$1 root=${2:-}
  mkdir -p "$WP7_RECORDS"
  WP7_RECORD="$WP7_RECORDS/$(date -u +%Y%m%dT%H%M%SZ)_${name}.json"
  export WP7_RECORD
  python3 "$WP7_SCRIPTS/run_record.py" start "$WP7_RECORD" --name "$name" --root "$root" \
    --cwd "$PWD" -- "$0" "${WP7_SCRIPT_ARGS[@]}"
  trap 'wp7_record_end $?' EXIT
  echo "run record: $WP7_RECORD"
}
wp7_record_end() {
  local rc=$1
  python3 "$WP7_SCRIPTS/run_record.py" end "$WP7_RECORD" --exit-code "$rc"
  echo "run record: $WP7_RECORD (exit $rc)"
}
