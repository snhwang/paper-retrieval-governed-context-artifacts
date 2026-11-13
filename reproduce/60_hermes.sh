#!/usr/bin/env bash
# 60_hermes.sh: WP7, the execution-level experiment in Hermes Agent (stage 1 and stage 2).
#
# A thin wrapper over hermes/REPRODUCE.md and hermes/scripts/. Read REPRODUCE.md
# first: it gives the prerequisites (Hermes Agent 0.22.2 at ~/src/hermes-agent, the
# runner venv ~/.venvs/tist-spike, bubblewrap, the docker CLI), the settings, the
# checks each launcher makes and how to stop and continue a grid. This wrapper runs
# the same scripts from the clone $REPRO_OUT/clones/artifacts-hermes, keeps the run
# roots under $REPRO_OUT/hermes (WP7_RUNS), and writes a kit run record beside the
# records the Hermes scripts write themselves ($REPRO_OUT/hermes/records/).
#
# Reproduces: sec:eval-hermes (stage 1: arms A, B, C-gate, D x operator and guest x 0,
#   100 and 300 decoys x 23 tasks x 3 reps. Stage 2: blocks 1 to 3, gate with reason,
#   the spoofing probe, C-cut, and the 100-decoy guest block), and the k sweep and
#   annotation cost that choose stage 2's settings.
# Steps, in order, one per call. The grid steps start their own user services.
#   install-bear   scripts/install_bear.sh v0.4.2 (into ~/.venvs/tist-spike)    1 min
#   pregrid        scripts/pregrid.sh (uses 8355 and 8360)                        3 min
#   stage1         scripts/launch_stage1.sh, 1,656 cells (8355 exclusive)         about 27 h
#   post-stage1    scripts/post_stage1.sh                                         15 min
#   settings       scripts/stage2_settings.sh (k sweep, annotation cost)          1 min
#   block1         scripts/launch_block.sh 1, 874 cells                           about 11.5 h
#   post-block1    scripts/post_block.sh 1                                        5 min
#   block2         scripts/launch_block.sh 2, 414 cells                           about 7 h
#   post-block2    scripts/post_block.sh 2                                        5 min
#   block3         scripts/launch_block.sh 3, 276 cells                           about 4.5 h
#   post-block3    scripts/post_block.sh 3                                        5 min
#   analyze        scripts/analyze_stage2.sh                                      a few min
#   status ROOT    python3 scripts/status.py $WP7_RUNS/ROOT (stage1, stage2-b1, ...)
# Grid steps take extra options through: --continue (finish a stopped grid).
# Prerequisites: 00_setup.sh (for the clone), hermes/REPRODUCE.md section 1, SGLang
#   (Qwen3.8-27B) on 8355 for the grid's exclusive use and Nemotron on 8360, both
#   agreed with the model-server session. wsl-keepalive is Running.
# Resources: ports 8355 and 8360. No local model load in WSL while a grid runs. Grid
#   services cap at 16G, other steps at 4G or 8G.
# Time: about 50 hours of grid time in all, plus under an hour of checks and analysis.
# Outputs: $REPRO_OUT/hermes/ (run roots, analysis/, records/). 70_assemble.sh copies
#   analysis/ into $REPRO_OUT/assembled/hermes/results/.
#
# Usage:
#   bash reproduce/60_hermes.sh STEP [--continue] [--dry-run]
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

export WP7_RUNS=${WP7_RUNS:-$REPRO_OUT/hermes}
HS=$HERMES_CLONE/hermes/scripts
STEP="" EXTRA=()
for a in "${ARGS_REST[@]}"; do
  case $a in
    --continue) EXTRA+=(--continue) ;;
    -*) die "unknown option $a (see --help)" ;;
    *) if [ -z "$STEP" ]; then STEP=$a; else EXTRA+=("$a"); fi ;;
  esac
done
[ -n "$STEP" ] || die "name a step (see --help for the order)"

case $STEP in
  install-bear) CMD=(bash "$HS/install_bear.sh" v0.4.2) ;;
  pregrid)      CMD=(bash "$HS/pregrid.sh") ;;
  stage1)       CMD=(bash "$HS/launch_stage1.sh" "${EXTRA[@]}") ;;
  post-stage1)  CMD=(bash "$HS/post_stage1.sh") ;;
  settings)     CMD=(bash "$HS/stage2_settings.sh") ;;
  block[123])   CMD=(bash "$HS/launch_block.sh" "${STEP#block}" "${EXTRA[@]}") ;;
  post-block[123]) CMD=(bash "$HS/post_block.sh" "${STEP#post-block}") ;;
  analyze)      CMD=(bash "$HS/analyze_stage2.sh") ;;
  status)       CMD=(python3 "$HS/status.py" "$WP7_RUNS/${EXTRA[0]:-stage1}") ;;
  *) die "unknown step $STEP (see --help)" ;;
esac

repro_begin
[ -n "${REPRO_CHAIN:-}" ] && record_note "$REPRO_CHAIN"
say "Hermes step $STEP from $HERMES_CLONE, WP7_RUNS=$WP7_RUNS"
[ -d "$HERMES_CLONE/.git" ] || [ "$DRY_RUN" = 1 ] || die "missing clone $HERMES_CLONE (run 00_setup.sh)"
[ "$DRY_RUN" = 1 ] || check_clone "$HERMES_CLONE"
[ -f "$HS/env.sh" ] || [ "$DRY_RUN" = 1 ] || die "$HS/env.sh is missing. The clone predates hermes/scripts (run 00_setup.sh --update)"
case $STEP in
  stage1|block[123]|pregrid)
    [ "$DRY_RUN" = 1 ] || { check_tc; check_slice; check_keepalive; check_no_gpu_jobs; } ;;
esac

if [ "$DRY_RUN" = 1 ]; then
  case $STEP in
    stage1|block[123])
      # --print makes the launcher show its commands and checks, and launch nothing.
      echo "+ (the launcher's own --print output follows)"
      if [ -f "$HS/env.sh" ]; then "${CMD[@]}" --print; else echo "+ ${CMD[*]} --print   (clone not made yet)"; fi ;;
    *) echo "+ $(printf '%q ' "${CMD[@]}")" ;;
  esac
  REPRO_OK_NOTE="step $STEP (dry run)"
  exit 0
fi

case $STEP in
  stage1|block[123]|pregrid)
    python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name sglang --url "$REPRO_SGLANG_URL" >/dev/null 2>&1
    python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name nemotron --url "$REPRO_NEMOTRON_URL/health" >/dev/null 2>&1 ;;
esac
if [ -n "${SLURM_JOB_ID:-}" ] && [[ $STEP == block[123] ]]; then
  # A block runs inside this Slurm job. sbatch --signal=B:USR1@<s> (with --wrap "exec bash ...")
  # reaches this shell before the time limit or a booked window, and we write the block's STOP
  # file: the grid ends after its current cell. Rerun the step with --continue later.
  ROOT=$WP7_RUNS/stage2-b${STEP#block}
  trap 'touch "$ROOT/STOP"; record_note "USR1 from Slurm at $(date -u +%FT%TZ): STOP written for $ROOT"' USR1
  run_cmd "hermes-$STEP" -C "$HERMES_CLONE/hermes" -- "${CMD[@]}" &
  pid=$!
  while :; do wait "$pid"; rc=$?; kill -0 "$pid" 2>/dev/null || break; done
  case $rc in
    0|1) REPRO_OK_NOTE="block ${STEP#block} finished in Slurm job $SLURM_JOB_ID (run.py exit $rc). Next: post-$STEP"; exit 0 ;;
    3) die "block ${STEP#block} paused by its STOP file. Continue with: 60_hermes.sh $STEP --continue" ;;
    *) die "block ${STEP#block} ended with exit $rc (2 means the runner stopped itself: read $ROOT/logs/cells.jsonl)" ;;
  esac
fi
run_cmd "hermes-$STEP" -C "$HERMES_CLONE/hermes" -- "${CMD[@]}" || die "hermes step $STEP failed (see its output above)"
case $STEP in
  stage1|block[123]) REPRO_OK_NOTE="the grid service is started (its status commands are printed above). When it ends, run the next step: post-${STEP/stage1/stage1}" ;;
  *) REPRO_OK_NOTE="step $STEP done" ;;
esac
