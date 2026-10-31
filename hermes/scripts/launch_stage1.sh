#!/bin/bash
# Launch the stage-1 grid (1,656 cells) as a user service, under a run record.
#
#   scripts/launch_stage1.sh [--harness current|9820f8a] [--continue] [--print]
#
#   --harness current   (default) the reported stage 1: specs/stage1_v2.json on this checkout's
#                       harness (the stage-2 harness, giveaways hidden) with BEAR v0.4.2.
#                       Root $WP7_RUNS/stage1, unit tist-wp7-stage1, expected/stage1_v2.json
#   --harness 9820f8a   historical only: the agent-run stage 1 exactly, from a clone at commit
#                       9820f8a with BEAR v0.4.1 (set WP7_HARNESS_DIR to the clone's hermes/).
#                       Root $WP7_RUNS/stage1-9820f8a, unit tist-wp7-stage1-9820f8a,
#                       expected/stage1_9820f8a.json
#   --continue          the root exists from a stopped launch, finish its planned cells
#   --print             print the commands and checks, launch nothing
#
# Grid: arms A, B, C-gate and D, roles operator and guest, 0, 100 and 300 decoys, 23 tasks,
# 3 reps, Nemotron, annotations off, turn scope, message query, cells in seeded rep blocks
# (seed 20261030). Its B and C-gate cells at 0 and 100 decoys are block 2's baselines.
# Before launching it checks that no WP7 grid service is active, the BEAR version, that the
# harness dir has no uncommitted change, and (provenance_check.py, which contacts 8355 and 8360)
# that the servers, installs and materials match expected/. The grid uses 8355 (one cache flush
# before each cell, so no other client should use 8355 meanwhile) and 8360. Run
# scripts/pregrid.sh first (scripts/pregrid_9820f8a.sh for the historical path).
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cont=0 print=0 harness=current
while [ $# -gt 0 ]; do
  case "$1" in
    --continue) cont=1; shift ;;
    --print) print=1; shift ;;
    --harness) harness=${2:-}; shift 2 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done
case "$harness" in
  current)
    U=tist-wp7-stage1; R=$WP7_RUNS/stage1; BEAR=0.4.2; EXPECT=stage1_v2.json
    GRID=(--spec specs/stage1_v2.json) ;;
  9820f8a)
    U=tist-wp7-stage1-9820f8a; R=$WP7_RUNS/stage1-9820f8a; BEAR=0.4.1; EXPECT=stage1_9820f8a.json
    # run.py at 9820f8a has no --spec, so the same grid is given as options.
    GRID=(--arms A,B,C-gate,D --roles operator,guest --decoys 0,100,300 --tasks all --reps 3) ;;
  *) echo "--harness must be current or 9820f8a"; exit 2 ;;
esac
REC="$WP7_RECORDS/$(date -u +%Y%m%dT%H%M%SZ)_stage1-$harness.json"
CMD=("$WP7_PY" run.py matrix --root "$R" "${GRID[@]}" --order rep-blocks --seed 20261030 --resume
     --max-error-frac 0.05 --guard-provenance)
FULL=("$TIST_CAPPED" --mem 16G --service "$U" -- /bin/bash "$WP7_SCRIPTS/run_recorded.sh"
      --record "$REC" --root "$R" --unit "$U" "stage1-$harness" -- "${CMD[@]}")

status_help() {
  cat <<EOF
Status:
  systemctl --user status $U --no-pager
  journalctl --user -u $U -n 20 --no-pager
  python3 $WP7_SCRIPTS/status.py $R
  python3 $WP7_SCRIPTS/watch.py $R \$(wc -l < $R/logs/cells.jsonl) 100 $U
      (returns after 100 more cells, or on an error burst, a stop, a stall or the service ending)
Stop after the current cell:   touch $R/STOP
Run record:                    $REC
When it ends:                  scripts/post_stage1.sh --harness $harness
EOF
}

echo "stage 1 ($harness harness): root $R, unit $U, BEAR $BEAR, harness dir $WP7_HARNESS_DIR"
if [ $print -eq 1 ]; then
  echo "would run (from $WP7_HARNESS_DIR):"; printf '  %q' "${FULL[@]}"; echo
  status_help
  exit 0
fi
if [ "$harness" = 9820f8a ] && [ "$(git -C "$WP7_HARNESS_DIR" rev-parse HEAD 2>/dev/null)" != 9820f8a8baa2a4522688e0dd09bb805bcd1bf94d ]; then
  echo "WP7_HARNESS_DIR ($WP7_HARNESS_DIR) is not a checkout at 9820f8a (REPRODUCE.md, appendix A)"; exit 1
fi
wp7_no_active_grid || exit 1
wp7_require_bear "$BEAR" || exit 1
if [ -e "$R" ] && [ $cont -eq 0 ]; then
  echo "$R exists. Use --continue to finish its plan, or move it away to start over."; exit 1
fi
if [ ! -e "$R" ] && [ $cont -eq 1 ]; then
  echo "$R does not exist, nothing to continue."; exit 1
fi
mkdir -p "$WP7_RUNS" "$WP7_RECORDS"
cd "$WP7_HARNESS_DIR" || exit 20
if [ -n "$(git status --porcelain -- .)" ]; then
  echo "hermes/ has uncommitted changes in $WP7_HARNESS_DIR:"; git status --short -- .; exit 1
fi
"$TIST_CAPPED" --mem 4G -- "$WP7_PY" "$WP7_SCRIPTS/provenance_check.py" "$WP7_SCRIPTS/expected/$EXPECT" \
  > "$WP7_RUNS/provenance-stage1-$harness.json" || { cat "$WP7_RUNS/provenance-stage1-$harness.json"; echo "provenance check failed"; exit 1; }
echo "launch $U at $(date -u +%FT%TZ), harness $(git rev-parse --short HEAD), MemAvailable $(wp7_mem_gb) GB"
"${FULL[@]}" || { echo "the service did not start"; exit 1; }
sleep 20
systemctl --user is-active "$U"
journalctl --user -u "$U" -n 3 --no-pager | cut -c1-250
status_help
