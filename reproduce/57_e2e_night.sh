#!/usr/bin/env bash
# 57_e2e_night.sh: parts of 56_e2e_long_context.sh, in order, in a night booked with the
# Qwen3.8 server stopped.
#
# Reproduces: nothing by itself. It waits until the booked night is really free, then runs
#   the named parts of 56_e2e_long_context.sh one after the other. That script holds
#   everything about each run.
# Why: Mistral-Nemo and Gemma 4 31B at a 131,072-token window do not fit on the card beside
#   the Qwen3.8 server (port 8355). The model-server session books nights and stops that
#   server just after a window opens. A job that begins with the window would otherwise
#   meet a full card and fail.
#   One queue job per night runs all of the night's parts. Until 21 Nov 2026 each part was
#   its own queue job, chained to the others. One job that failed then made the queue cancel
#   the jobs after it.
# What it does, in order:
#   1. Waits, at most REPRO_NIGHT_WAIT_MIN minutes (default 40), until both hold:
#        GET $REPRO_SGLANG_URL/v1/models gets no answer, and
#        Windows nvidia-smi shows at most REPRO_GPU_START_MIB MiB in use (default 40000).
#   2. For each part, in the order given:
#      - A part that is done already is skipped (its marker in $REPRO_OUT/state).
#      - A run part needs the measured load of its tag to say that the prompt fits
#        ($REPRO_OUT/e2e_long/measure-<model>/measure.json, "fits": true). Without it the
#        part is not run, and the next part is tried.
#      - With less than REPRO_NIGHT_MIN_LEFT_MIN minutes (default 15) of the night left, this
#        part and the ones after it are left for another night.
#      - Runs: bash reproduce/56_e2e_long_context.sh PART, with the card limits of the night
#        (start at or below REPRO_GPU_START_MIB, stop above REPRO_GPU_STOP_MIB, default 94000).
#        At the night's end the part is stopped with SIGTERM. Its guard then unloads the model.
#        A stopped part keeps no result and is made again in a later night.
#      - A part that fails does not stop the parts after it.
#      - After each part it waits until Ollama holds no model and the card is back at or
#        below the start limit. If that does not happen in 5 minutes, it stops.
#   The night's end is the earlier of REPRO_NIGHT_END (a time that date -d reads, for example
#   2026-11-24T06:40:00) and 8 minutes before the end of the queue job this runs in. With
#   neither, there is no end and no part is stopped.
#   It loads nothing itself, and it stops and starts no server.
# Parts: measure-nemo measure-g31 monolithic react g31-scaffold g31-native, and
#   g31-native-s1 to g31-native-s4 for single runs of the native part.
# Prerequisites: those of each part in 56_e2e_long_context.sh, and a booked night.
# Exit code: 0 when every named part is done. 1 when a part failed or the card stayed busy.
#   3 when parts are left for another night and none failed. 75 when the night did not
#   become free.
#
# Usage:
#   bash reproduce/57_e2e_night.sh PART [PART...] [--dry-run]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PARTS="measure-nemo measure-g31 monolithic react g31-scaffold g31-native g31-native-s1 g31-native-s2 g31-native-s3 g31-native-s4"
LIST=()
DRY=0
for a in "$@"; do
  case $a in
    -h|--help) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 0 ;;
    -n|--dry-run) DRY=1 ;;
    *) [[ " $PARTS " == *" $a "* ]] || { echo "unknown part $a. Parts: $PARTS" >&2; exit 2; }
       LIST+=("$a") ;;
  esac
done
[ ${#LIST[@]} -gt 0 ] || { echo "name at least one part: $PARTS" >&2; exit 2; }

REPRO_OUT=${REPRO_OUT:-$HOME/tist-repro}
CHAT=${REPRO_SGLANG_URL:-http://127.0.0.1:8355}
OLLAMA=${REPRO_OLLAMA_ROOT:-http://127.0.0.1:11434}
SMI=${REPRO_SMI:-/mnt/c/Windows/System32/nvidia-smi.exe}
STEP=${REPRO_NIGHT_STEP:-$HERE/56_e2e_long_context.sh}   # the script that runs one part
STATE=$REPRO_OUT/state/$(basename "$STEP" .sh)
export REPRO_GPU_START_MIB=${REPRO_GPU_START_MIB:-40000}
export REPRO_GPU_STOP_MIB=${REPRO_GPU_STOP_MIB:-94000}
WAIT_MIN=${REPRO_NIGHT_WAIT_MIN:-40}
MIN_LEFT=$(( ${REPRO_NIGHT_MIN_LEFT_MIN:-15} * 60 ))
POLL=${REPRO_NIGHT_POLL_S:-20}
say() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
card_mib() { "$SMI" --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' \r'; }
chat_up() { curl -s -m 5 -o /dev/null "$CHAT/v1/models"; }   # exit 0 when the server answers at all
ollama_models() {  # how many models Ollama holds, or nothing when it does not answer
  curl -s -m 5 "$OLLAMA/api/ps" | python3 -c 'import json, sys; print(len(json.load(sys.stdin).get("models", [])))' 2>/dev/null
}
is_done() {  # is_done PART: the part's markers say that nothing is left to do
  local p=$1 d k
  case $p in
    *-native)
      for k in 1 2 3 4; do [ -f "$STATE/$p-s$k.done" ] || return 1; done
      [ -f "$STATE/$p-analysis.done" ] ;;
    *-native-s[1-4])
      [ -f "$STATE/$p.done" ] || return 1
      d=${p%-s*}
      for k in 1 2 3 4; do [ -f "$STATE/$d-s$k.done" ] || return 0; done
      [ -f "$STATE/$d-analysis.done" ] ;;   # the last run of the four also makes the grid
    *-scaffold) [ -f "$STATE/$p.done" ] && [ -f "$STATE/$p-analysis.done" ] ;;
    *) [ -f "$STATE/$p.done" ] ;;
  esac
}
settle() {  # after a part: Ollama holds no model and the card is back at or below the start limit
  local j u
  for j in $(seq 1 30); do
    u=$(card_mib)
    [ "$(ollama_models)" = 0 ] && [[ $u =~ ^[0-9]+$ ]] && (( u <= REPRO_GPU_START_MIB )) && return 0
    sleep 10
  done
  say "after 5 minutes Ollama holds $(ollama_models) model(s) and the card is at $(card_mib) MiB (start limit $REPRO_GPU_START_MIB)"
  return 1
}

# The night's end, in seconds since 1970. Empty means no end.
END=""
if [ -n "${REPRO_NIGHT_END:-}" ]; then
  END=$(date -d "$REPRO_NIGHT_END" +%s 2>/dev/null) || { echo "REPRO_NIGHT_END is not a time that date -d reads: $REPRO_NIGHT_END" >&2; exit 2; }
fi
if [ -n "${SLURM_JOB_ID:-}" ] && [ "$DRY" = 0 ]; then
  je=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | grep -o 'EndTime=[^ ]*' | head -1 | cut -d= -f2)
  if [[ $je =~ ^[0-9]{4}- ]]; then
    js=$(( $(date -d "$je" +%s) - 480 ))
    if [ -z "$END" ] || (( js < END )); then END=$js; fi
  fi
fi
left() { if [ -z "$END" ]; then echo 999999999; else echo $(( END - $(date +%s) )); fi; }

if [ "$DRY" = 1 ]; then
  echo "+ (wait at most $WAIT_MIN min until $CHAT/v1/models gets no answer and the card is at or below $REPRO_GPU_START_MIB MiB)"
  echo "+ (the night ends at ${REPRO_NIGHT_END:-no set time}, or 8 minutes before the queue job's end if that is earlier)"
  for p in "${LIST[@]}"; do
    case $p in *g31*) M=g31 ;; *) M=nemo ;; esac
    echo "== $p"
    echo "+ (skipped if its markers in $STATE say it is done)"
    case $p in measure-*) ;; *) echo "+ (check: $REPRO_OUT/e2e_long/measure-$M/measure.json says the prompt fits)" ;; esac
    bash "$STEP" "$p" --dry-run
  done
  exit 0
fi

say "night parts: ${LIST[*]}"
[ -n "$END" ] && say "the night ends at $(date -d "@$END" '+%F %T %Z'), $(( $(left) / 60 )) minutes from now"
say "waiting for the Qwen3.8 server at $CHAT to be down and the card at or below $REPRO_GPU_START_MIB MiB"
free=0
why=""
for i in $(seq 0 $(( WAIT_MIN * 60 / POLL ))); do
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
  sleep "$POLL"
done
if [ "$free" != 1 ]; then
  say "the night did not become free in $WAIT_MIN minutes: $why. Nothing was loaded. Ask the model-server session."
  exit 75
fi
say "the night is free: no answer from $CHAT, card at $u MiB"

DONE=() FAILED=() LEFT=()
busy=0
for i in "${!LIST[@]}"; do
  p=${LIST[$i]}
  if is_done "$p"; then
    say "$p: done already, skipped"
    DONE+=("$p")
    continue
  fi
  case $p in *g31*) M=g31 ;; *) M=nemo ;; esac
  case $p in
    measure-*) ;;
    *)
      mj=$REPRO_OUT/e2e_long/measure-$M/measure.json
      if ! python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("fits") is True else 1)' "$mj" 2>/dev/null; then
        say "$p: not run. No measurement says that the prompt fits ($mj). Nothing was loaded."
        FAILED+=("$p (no measurement)")
        continue
      fi ;;
  esac
  t=$(left)
  if (( t < MIN_LEFT )); then
    say "$(( t / 60 )) minutes of the night are left. Left for another night: ${LIST[*]:$i}"
    LEFT=("${LIST[@]:$i}")
    break
  fi
  if [ -n "$END" ]; then
    say "$p: start, $(( t / 60 )) minutes of the night left"
    timeout --signal=TERM --kill-after=240 "$t" bash "$STEP" "$p"
  else
    say "$p: start"
    bash "$STEP" "$p"
  fi
  rc=$?
  if [ "$rc" -eq 0 ]; then
    say "$p: done"
    DONE+=("$p")
  elif [ -n "$END" ] && { [ "$rc" -eq 124 ] || (( $(left) <= 60 )); }; then
    say "$p: stopped at the night's end (exit $rc). It keeps no result and is made again in a later night"
    LEFT=("${LIST[@]:$i}")
    settle || busy=1
    break
  else
    say "$p: failed (exit $rc). The parts after it are still tried"
    FAILED+=("$p (exit $rc)")
  fi
  if ! settle; then
    say "the card is not free, so no further part is started: ${LIST[*]:$((i + 1))}"
    LEFT=("${LIST[@]:$((i + 1))}")
    busy=1
    break
  fi
done

say "night summary. Done: ${DONE[*]:-none}. Failed: ${FAILED[*]:-none}. Left for another night: ${LEFT[*]:-none}."
say "Ollama holds $(ollama_models) model(s), card at $(card_mib) MiB"
[ "$busy" = 1 ] && { say "the card or Ollama stayed busy. Tell the model-server session before its server starts again."; exit 1; }
[ ${#FAILED[@]} -gt 0 ] && exit 1
[ ${#LEFT[@]} -gt 0 ] && exit 3
exit 0
