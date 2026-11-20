#!/usr/bin/env bash
# 57_e2e_night.sh: one part of 56_e2e_long_context.sh, in a night booked with the Qwen3.8
# server stopped.
#
# Reproduces: nothing by itself. It waits until the booked night is really free, then runs
#   the named part of 56_e2e_long_context.sh, which holds everything about the run.
# Why: Mistral-Nemo and Gemma 4 31B at a 131,072-token window do not fit on the card beside
#   the Qwen3.8 server (port 8355). The model-server session books nights and stops that
#   server just after a window opens. A job that begins with the window would otherwise
#   meet a full card and fail.
# What it does, in order:
#   1. Waits, at most REPRO_NIGHT_WAIT_MIN minutes (default 40), until both hold:
#        GET $REPRO_SGLANG_URL/v1/models gets no answer, and
#        Windows nvidia-smi shows at most REPRO_GPU_START_MIB MiB in use (default 40000).
#   2. For a run part, requires the measured load of the part's tag to say that the prompt
#      fits ($REPRO_OUT/e2e_long/measure-<model>/measure.json, "fits": true).
#   3. Runs: bash reproduce/56_e2e_long_context.sh PART, with the card limits of the night
#      (start at or below REPRO_GPU_START_MIB, stop above REPRO_GPU_STOP_MIB, default 94000).
#   It loads nothing itself, and it stops and starts no server.
# Parts: measure-g31 measure-nemo monolithic react g31-scaffold g31-native
# Prerequisites: those of the part in 56_e2e_long_context.sh, and a booked night.
# Exit code: the part's own. 75 when the night did not become free, or no measurement says
#   that the prompt fits.
#
# Usage:
#   bash reproduce/57_e2e_night.sh PART [--dry-run]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
case ${1:-} in -h|--help) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 0 ;; esac
PART=${1:-}
DRY=0
[ "${2:-}" = --dry-run ] && DRY=1
PARTS="measure-g31 measure-nemo monolithic react g31-scaffold g31-native"
[[ -n "$PART" && " $PARTS " == *" $PART "* ]] || { echo "name a part: $PARTS" >&2; exit 2; }

REPRO_OUT=${REPRO_OUT:-$HOME/tist-repro}
CHAT=${REPRO_SGLANG_URL:-http://127.0.0.1:8355}
SMI=/mnt/c/Windows/System32/nvidia-smi.exe
export REPRO_GPU_START_MIB=${REPRO_GPU_START_MIB:-40000}
export REPRO_GPU_STOP_MIB=${REPRO_GPU_STOP_MIB:-94000}
WAIT_MIN=${REPRO_NIGHT_WAIT_MIN:-40}
say() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
card_mib() { "$SMI" --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' \r'; }
chat_up() { curl -s -m 5 -o /dev/null "$CHAT/v1/models"; }   # exit 0 when the server answers at all

case $PART in *g31*) M=g31 ;; *) M=nemo ;; esac
if [ "$DRY" = 1 ]; then
  echo "+ (wait at most $WAIT_MIN min until $CHAT/v1/models gets no answer and the card is at or below $REPRO_GPU_START_MIB MiB)"
  case $PART in measure-*) ;; *) echo "+ (check: $REPRO_OUT/e2e_long/measure-$M/measure.json says the prompt fits)" ;; esac
  exec bash "$HERE/56_e2e_long_context.sh" "$PART" --dry-run
fi

say "night part $PART: waiting for the Qwen3.8 server at $CHAT to be down and the card at or below $REPRO_GPU_START_MIB MiB"
free=0
for i in $(seq 0 $((WAIT_MIN * 3))); do
  u=$(card_mib)
  if chat_up; then
    why="the server at $CHAT still answers"
  elif ! [[ $u =~ ^[0-9]+$ ]]; then
    why="no reading from $SMI"
  elif (( u > REPRO_GPU_START_MIB )); then
    why="the card is at $u MiB"
  else
    free=1
    break
  fi
  (( i % 9 == 0 )) && say "not free yet: $why"
  sleep 20
done
if [ "$free" != 1 ]; then
  say "the night did not become free in $WAIT_MIN minutes: $why. Nothing was loaded. Ask the model-server session."
  exit 75
fi
say "the night is free: no answer from $CHAT, card at $u MiB"

case $PART in
  measure-*) ;;
  *)
    mj=$REPRO_OUT/e2e_long/measure-$M/measure.json
    python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("fits") is True else 1)' "$mj" 2>/dev/null \
      || { say "no measurement says that the prompt fits ($mj). Run measure-$M first. Nothing was loaded."; exit 75; } ;;
esac
exec bash "$HERE/56_e2e_long_context.sh" "$PART"
