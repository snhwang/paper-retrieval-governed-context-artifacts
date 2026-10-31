#!/bin/bash
# Launch one stage-2 block as its own user service, under a run record.
#
#   scripts/launch_block.sh N [--continue] [--print]
#
#   N           1, 2 or 3 (specs/stage2_blockN.json: 874, 414 and 276 cells)
#   --continue  the root exists from a stopped launch, finish its planned cells (run.py --resume)
#   --print     print the commands and checks, launch nothing
#
# Before launching it checks that no WP7 grid service is active, that BEAR v0.4.2 is installed,
# that hermes/ in the harness dir has no uncommitted change, and (provenance_check.py, which
# contacts 8355 and 8360) that the servers, installs and materials match expected/stage2.json.
# The service runs run.py under scripts/run_recorded.sh, so the record gets the exit code when
# the block ends. It uses 8355 (one cache flush before each cell, so no other client should use
# 8355 meanwhile) and 8360. Run blocks one at a time, in order, after the stage-1 grid and
# scripts/stage2_settings.sh (k is decided before block 2). Block 2 runs only C-cut. Its C-gate
# and B baselines are the stage-1 grid's cells.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
N=${1:?usage: launch_block.sh N [--continue] [--print]}
shift
cont=0 print=0
for x in "$@"; do
  case "$x" in --continue) cont=1 ;; --print) print=1 ;; *) echo "unknown option $x"; exit 2 ;; esac
done
case "$N" in 1|2|3) ;; *) echo "N must be 1, 2 or 3"; exit 2 ;; esac
U=tist-wp7-stage2-b$N
R=$WP7_RUNS/stage2-b$N
SPEC=specs/stage2_block$N.json
REC="$WP7_RECORDS/$(date -u +%Y%m%dT%H%M%SZ)_stage2-block$N.json"
CMD=("$WP7_PY" run.py matrix --root "$R" --spec "$SPEC" --order rep-blocks --seed 20261031 --resume
     --max-error-frac 0.05 --guard-provenance)
FULL=("$TIST_CAPPED" --mem 16G --service "$U" -- /bin/bash "$WP7_SCRIPTS/run_recorded.sh"
      --record "$REC" --root "$R" --unit "$U" "stage2-block$N" -- "${CMD[@]}")

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
When it ends:                  scripts/post_block.sh $N
EOF
}

echo "block $N: $SPEC, root $R, unit $U, harness $WP7_HARNESS_DIR"
if [ $print -eq 1 ]; then
  echo "would run (from $WP7_HARNESS_DIR):"; printf '  %q' "${FULL[@]}"; echo
  status_help
  exit 0
fi
wp7_no_active_grid || exit 1
wp7_require_bear 0.4.2 || exit 1
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
"$TIST_CAPPED" --mem 4G -- "$WP7_PY" "$WP7_SCRIPTS/provenance_check.py" "$WP7_SCRIPTS/expected/stage2.json" \
  > "$WP7_RUNS/provenance-block$N.json" || { cat "$WP7_RUNS/provenance-block$N.json"; echo "provenance check failed"; exit 1; }
echo "launch $U at $(date -u +%FT%TZ), harness $(git rev-parse --short HEAD), MemAvailable $(wp7_mem_gb) GB"
"${FULL[@]}" || { echo "the service did not start"; exit 1; }
sleep 20
systemctl --user is-active "$U"
journalctl --user -u "$U" -n 3 --no-pager | cut -c1-250
status_help
