#!/usr/bin/env bash
# 61_hermes_chain.sh: run the Hermes steps of 60_hermes.sh in order, unattended, from a go file.
#
# A stopgap until a shared job queue exists. Scott types it once. It starts the user service
# tist-repro-61, which waits for the go file, then runs, one after another:
#   stage1, post-stage1, settings, block1, post-block1
# each as `bash reproduce/60_hermes.sh STEP`, with its own kit run record. It stops before
# block2, because block 2's k is Scott's choice (see the ksweep that settings writes). Block 1
# uses no k, so it runs in the chain. Block 2, block 3 and analyze stay manual.
#
# The go file. Nothing starts, and no paused grid continues, while $REPRO_OUT/hermes-chain/GO is
# missing. model-server touches it to give the go, and removes it to hold the chain. To make a
# running grid yield (a Hearthwick measured run), remove GO and touch the grid's STOP file. The
# chain continues the grid once GO is back.
#
# Windows. $REPRO_OUT/hermes-chain/windows.txt lists blocked windows, one per line, as
# "START END" in UTC (2026-11-16T13:10Z 2026-11-16T17:00Z). It is read on every pass, so a line
# can be added while the chain runs. When a window opens while a grid runs, the chain writes the
# grid's STOP file. The grid ends after its current cell (at most about 17 min). No grid starts
# or continues inside a window, or less than 30 min before one. After the window the chain removes
# the STOP file (kept as logs/STOP.<time>) and continues the grid with --continue. The defaults
# are the A3 windows: Mon 16 and Tue 17 Nov, 13:10 to 17:00 UTC, and Wed 18 Nov, 13:10 to
# 15:00 UTC. One transient timer per window also writes the STOP file, in case this service dies.
#
# How a grid ended decides what comes next (from the last batch event in logs/cells.jsonl):
#   batch_end       all planned cells ran: the next step
#   batch_paused    a STOP file: wait for the window to close and for GO, then --continue
#   batch_stopped   the runner stopped itself (errors, provenance, memory, sandbox leak):
#                   the chain stops with FAILED and the reason. Read it before continuing.
#   no batch event  the service was killed: the chain stops with FAILED
# Any other step that fails stops the chain. Rerunning this script resumes: finished steps
# are skipped, and a paused or stopped grid is continued.
#
# Records. This script's run record names the user who submitted it and when. Each step it
# runs writes its own 60_hermes.sh run record (runlog/60_hermes-<UTC>.json) with a note that
# this chain started it, and its full terminal output to
# logs/hermes-chain/60_hermes-<step>[-continue]-<UTC>.log. The chain's own output is
# logs/61_hermes_chain.log. A grid's own output is in its root (logs/cells.jsonl) and journal.
#
# Resources: the chain itself is a 2G service in tist.slice and only waits. The grids are
# 60_hermes.sh's (8355 and 8360, 16G services tist-wp7-*).
#
# Usage:
#   bash reproduce/61_hermes_chain.sh --dry-run     # the plan, the windows and the timers
#   bash reproduce/61_hermes_chain.sh               # start the service and the timers
#   bash reproduce/61_hermes_chain.sh --stop-now    # write the STOP file of any running grid
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

STOP_NOW=0
for a in "${ARGS_REST[@]}"; do
  case $a in
    --stop-now) STOP_NOW=1 ;;
    *) die "unknown option $a (see --help)" ;;
  esac
done

export WP7_RUNS=${WP7_RUNS:-$REPRO_OUT/hermes}
CHAIN_DIR=$REPRO_OUT/hermes-chain
GO=$CHAIN_DIR/GO
WINDOWS=$CHAIN_DIR/windows.txt
STEPS="stage1 post-stage1 settings block1 post-block1"
LEAD_S=1800      # no grid starts or continues less than this before a window
POLL_S=30
DEFAULT_WINDOWS="2026-11-16T13:10Z 2026-11-16T17:00Z
2026-11-17T13:10Z 2026-11-17T17:00Z
2026-11-18T13:10Z 2026-11-18T15:00Z"

grid_root() {  # grid_root STEP: the run root of a grid step
  case $1 in
    stage1) echo "$WP7_RUNS/stage1" ;;
    block[123]) echo "$WP7_RUNS/stage2-b${1#block}" ;;
  esac
}
grid_unit() {
  case $1 in
    stage1) echo tist-wp7-stage1 ;;
    block[123]) echo "tist-wp7-stage2-b${1#block}" ;;
  esac
}
is_grid() { case $1 in stage1|block[123]) return 0 ;; esac; return 1; }

# --stop-now: the timers' action. Writes STOP for every active grid unit and nothing else.
if [ "$STOP_NOW" = 1 ]; then
  trap - EXIT
  for s in stage1 block1 block2 block3; do
    if systemctl --user is-active -q "$(grid_unit "$s")" 2>/dev/null; then
      touch "$(grid_root "$s")/STOP"
      echo "$(date -u +%FT%TZ) STOP written for $(grid_unit "$s") by --stop-now" | tee -a "$CHAIN_DIR/stop-now.log"
    fi
  done
  exit 0
fi

# The windows as "start_epoch end_epoch" lines.
windows() {
  local src=$DEFAULT_WINDOWS
  [ -s "$WINDOWS" ] && src=$(grep -v '^\s*#' "$WINDOWS")
  local s e
  while read -r s e; do
    [ -n "$s" ] && [ -n "$e" ] || continue
    echo "$(date -u -d "${s/Z/ UTC}" +%s 2>/dev/null) $(date -u -d "${e/Z/ UTC}" +%s 2>/dev/null)"
  done <<<"$src"
}
in_window() {  # in_window [LEAD]: true inside a window, or within LEAD seconds before one
  local lead=${1:-0} now s e
  now=$(date -u +%s)
  while read -r s e; do
    [ -n "$s" ] && [ -n "$e" ] || continue
    (( now >= s - lead && now < e )) && return 0
  done < <(windows)
  return 1
}

last_batch_event() {  # last_batch_event ROOT: the last batch_* event name and its reason
  python3 - "$1/logs/cells.jsonl" <<'PY'
import json, sys
last = None
try:
    for line in open(sys.argv[1]):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("event", "")).startswith("batch_") and r["event"] != "batch_start":
            last = r
except OSError:
    pass
print(f'{last["event"]} {last.get("reason", "")}' if last else "none")
PY
}

hermes_step() {  # hermes_step STEP [--continue]: one 60_hermes.sh call under its own record
  local out
  out=$REPRO_OUT/logs/hermes-chain/60_hermes-$1$([ "${2:-}" = --continue ] && echo -continue)-$(date -u +%Y%m%dT%H%M%SZ).log
  run_cmd "hermes-$*" -C "$ART" -o "$out" -- env -u REPRO_RECORD -u REPRO_LOG -u REPRO_UNIT \
    REPRO_CHAIN="started by 61_hermes_chain.sh (run record $(basename "${REPRO_RECORD:-none}"), submitted ${REPRO_SUBMITTED:-unknown})" \
    bash "$REPRO_DIR/60_hermes.sh" "$@"
}

wait_go() {  # wait_go: until GO exists and no window is near
  local said=""
  while [ ! -e "$GO" ] || in_window "$LEAD_S"; do
    local why="waiting for the go file $GO"
    [ -e "$GO" ] && why="waiting: a blocked window is open or less than $((LEAD_S / 60)) min away"
    [ "$why" = "$said" ] || { say "$why"; said=$why; }
    sleep "$POLL_S"
  done
  [ -n "$said" ] && say "go: $GO is present and no window is near"
  return 0
}

watch_grid() {  # watch_grid STEP: while the grid runs, write STOP when a window opens
  local unit root
  unit=$(grid_unit "$1"); root=$(grid_root "$1")
  while systemctl --user is-active -q "$unit" 2>/dev/null; do
    if in_window 0 && [ ! -e "$root/STOP" ]; then
      touch "$root/STOP"
      record_note "STOP written for $unit at $(date -u +%FT%TZ): a blocked window opened"
    fi
    sleep "$POLL_S"
  done
}

run_grid() {  # run_grid STEP: launch or continue until the grid's plan is done
  local step=$1 root unit ev reason cont=()
  root=$(grid_root "$step"); unit=$(grid_unit "$step")
  [ -e "$root" ] && cont=(--continue)
  while :; do
    wait_go
    if [ -e "$root/STOP" ]; then
      mv "$root/STOP" "$root/logs/STOP.$(date -u +%Y%m%dT%H%M%SZ)"
      record_note "STOP file of $step moved to logs/ before continuing"
    fi
    hermes_step "$step" "${cont[@]}" || die "60_hermes.sh $step ${cont[*]} failed to launch (see above)"
    sleep 30
    watch_grid "$step"
    read -r ev reason <<<"$(last_batch_event "$root")"
    record_note "$unit ended at $(date -u +%FT%TZ): $ev${reason:+ ($reason)}"
    case $ev in
      batch_end) return 0 ;;
      batch_paused) cont=(--continue) ;;
      batch_stopped) die "$step: the runner stopped itself ($reason). Read $root/logs/cells.jsonl, then rerun this script to continue" ;;
      *) die "$step: $unit ended with no batch event (killed?). Check journalctl --user -u $unit, then rerun this script" ;;
    esac
  done
}

arm_timers() {  # one transient timer per window that has not ended, each runs --stop-now
  local s e now n=0
  now=$(date -u +%s)
  while read -r s e; do
    [ -n "$s" ] && (( e > now )) || continue
    local unit="tist-repro-61-stop-$(date -u -d "@$s" +%Y%m%dT%H%M)"
    local when
    when=$(date -u -d "@$s" '+%Y-%m-%d %H:%M:%S UTC')
    if [ "$DRY_RUN" = 1 ]; then
      echo "+ systemd-run --user --unit $unit --on-calendar '$when' -- bash $REPRO_DIR/61_hermes_chain.sh --stop-now"
      continue
    fi
    systemctl --user is-active -q "$unit.timer" 2>/dev/null && { say "timer $unit already armed"; continue; }
    systemd-run --user --quiet --unit "$unit" --on-calendar "$when" --timer-property=AccuracySec=1s \
      -- bash "$REPRO_DIR/61_hermes_chain.sh" --stop-now \
      && { record_note "armed timer $unit for $when"; n=$((n + 1)); } \
      || warn "could not arm the timer $unit"
  done < <(windows)
  return 0
}

if [ "$FOREGROUND" = 0 ] && [ "$DRY_RUN" = 0 ]; then
  export REPRO_SUBMITTED="by $(id -un) at $(date -u +%FT%TZ) from ${SSH_TTY:-$(tty 2>/dev/null || echo 'no tty')}"
fi
preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_clone "$HERMES_CLONE"
  mkdir -p "$CHAIN_DIR"
  [ -s "$WINDOWS" ] || printf '# START END, UTC. Read on every pass.\n%s\n' "$DEFAULT_WINDOWS" > "$WINDOWS"
}
maybe_launch tist-repro-61
repro_begin
[ -n "${REPRO_SUBMITTED:-}" ] && record_note "submitted $REPRO_SUBMITTED"
say "chain: $STEPS (stops before block2: k is Scott's choice)"
say "go file: $GO ($([ -e "$GO" ] && echo present || echo 'not present yet'))"
say "windows (UTC), from ${WINDOWS}$([ -s "$WINDOWS" ] || echo ', defaults'):"
while read -r s e; do [ -n "$s" ] && say "  $(date -u -d "@$s" +%FT%H:%MZ) to $(date -u -d "@$e" +%FT%H:%MZ)"; done < <(windows)
arm_timers

if [ "$DRY_RUN" = 1 ]; then
  for s in $STEPS; do
    if step_done "chain-$s"; then echo "+ skip $s (done)"; continue; fi
    is_grid "$s" && echo "+ (wait for $GO and no window within $((LEAD_S / 60)) min)"
    echo "+ bash $REPRO_DIR/60_hermes.sh $s$([ -e "$(grid_root "$s" 2>/dev/null)" ] && is_grid "$s" && echo ' --continue')"
    is_grid "$s" && echo "+ (watch $(grid_unit "$s"): STOP when a window opens, --continue after it, stop on batch_stopped)"
  done
  REPRO_OK_NOTE="chain plan shown"
  exit 0
fi

mkdir -p "$CHAIN_DIR"
for s in $STEPS; do
  hr
  if step_done "chain-$s"; then say "skip $s (done $(cat "$(state_dir)/chain-$s.done"))"; continue; fi
  if is_grid "$s"; then
    run_grid "$s"
  else
    hermes_step "$s" || die "60_hermes.sh $s failed. Read its output above, then rerun this script"
  fi
  mark_done "chain-$s"
done
REPRO_OK_NOTE="the chain ran $STEPS. Next: choose k from the settings ksweep, then bash reproduce/60_hermes.sh block2"
