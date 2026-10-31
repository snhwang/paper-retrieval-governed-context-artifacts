#!/bin/bash
# Stage-2 checks before block 1. Stops at the first failure.
#
#   scripts/pregrid2.sh
#
# Needs BEAR v0.4.2 in the runner venv, and WP7_HARNESS_DIR (default: this checkout's hermes/)
# with the stage-2 materials. Steps:
#   1. test_stage2_tasks.py: derived tokens, cron-only grep, spoof grader (offline)
#   2. plan-only for the three block specs: 874, 828 and 276 cells (offline)
#   3. the cell red team, offline (no bridge, the two ports must be unreachable)
#   4. the cell red team, bridged (contacts 8355 and 8360)
#   5. provenance_check.py against expected/stage2.json (contacts 8355 and 8360)
#   6. a 4-cell re-smoke: A and D, operator and guest, 0 decoys, ambiguous_delete_ask (uses 8355
#      and 8360, flushes the 8355 cache before each cell)
#   7. checks.py on the re-smoke, with --expect-sources-removed (offline)
#   8. resmoke_gate.py --stage 2 (offline)
# Takes about 3 minutes. Its roots are $WP7_RUNS/stage2-redteam-offline, stage2-redteam and
# stage2-resmoke, which must not exist yet. Set WP7_NOT_BEFORE="YYYY-MM-DD HH:MM:SS" (UTC) to
# refuse to start before a booked window.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
if [ -n "${WP7_NOT_BEFORE:-}" ] && [ "$(date -u +%s)" -lt "$(date -u -d "$WP7_NOT_BEFORE" +%s)" ]; then
  echo "too early: it is $(date -u +%T) UTC, the window opens at $WP7_NOT_BEFORE"; exit 9
fi
RO=$WP7_RUNS/stage2-redteam-offline
RT=$WP7_RUNS/stage2-redteam
RS=$WP7_RUNS/stage2-resmoke
for r in "$RO" "$RT" "$RS"; do
  [ -e "$r" ] && { echo "$r exists. Move it away or set WP7_RUNS to a new directory."; exit 21; }
done
mkdir -p "$WP7_RUNS"
wp7_record_begin pregrid2 "$RS"
echo "harness $WP7_HARNESS_DIR at $(git -C "$WP7_HARNESS_DIR" rev-parse --short HEAD), MemAvailable $(wp7_mem_gb) GB"
wp7_require_bear 0.4.2 || exit 10
wp7_no_active_grid || exit 11
cd "$WP7_HARNESS_DIR" || exit 20

wp7_step "1. stage-2 task tests" 4G "$WP7_PY" "$WP7_SCRIPTS/test_stage2_tasks.py" || exit 1
for n in 1 2 3; do
  want=$(case $n in 1) echo 874 ;; 2) echo 828 ;; 3) echo 276 ;; esac)
  got=$("$WP7_PY" run.py matrix --root "$WP7_RUNS/plan-only" --spec "specs/stage2_block$n.json" \
        --plan-only 2>/dev/null | awk '$2 == "cells," {print $1}')
  echo "== 2. block $n plan: ${got:-?} cells (expected $want)"
  [ "${got:-}" = "$want" ] || exit 2
done
wp7_step "3. red team (offline)" 4G "$WP7_PY" run.py redteam --root "$RO" --offline > "$WP7_RUNS/stage2-redteam-offline.txt" 2>&1
rc=$?; grep -E "^FAIL" "$WP7_RUNS/stage2-redteam-offline.txt" | head -20; tail -1 "$WP7_RUNS/stage2-redteam-offline.txt"
[ $rc -eq 0 ] || exit 3
wp7_step "4. red team (bridged)" 8G "$WP7_PY" run.py redteam --root "$RT" > "$WP7_RUNS/stage2-redteam.txt" 2>&1
rc=$?; grep -E "^FAIL" "$WP7_RUNS/stage2-redteam.txt" | head -20; tail -1 "$WP7_RUNS/stage2-redteam.txt"
[ $rc -eq 0 ] || exit 4
wp7_step "5. provenance" 4G "$WP7_PY" "$WP7_SCRIPTS/provenance_check.py" "$WP7_SCRIPTS/expected/stage2.json" || exit 5
wp7_step "6. re-smoke" 8G "$WP7_PY" run.py matrix --root "$RS" --arms A,D --roles operator,guest --decoys 0 \
  --tasks ambiguous_delete_ask > "$WP7_RUNS/stage2-resmoke.console" 2>&1
rc=$?; tail -2 "$WP7_RUNS/stage2-resmoke.console" | cut -c1-300
[ $rc -eq 0 ] || exit 6
cd "$WP7_HERMES_DIR" || exit 20
wp7_step "7. checks" 8G "$WP7_PY" checks.py --root "$RS" --expect-sources-removed \
  --registry "$WP7_HERMES_DIR/registry/harness_registry.json" > "$RS/checks.console" 2>&1
rc=$?; tail -4 "$RS/checks.console"
[ $rc -eq 0 ] || exit 7
wp7_step "8. gates" 4G "$WP7_PY_ANALYSIS" "$WP7_SCRIPTS/resmoke_gate.py" "$RS" --stage 2 || exit 8
grep -h "staged sources removed" "$RS"/logs/*.stderr 2>/dev/null | sort | uniq -c
echo "== all stage-2 pre-grid steps passed $(date -u +%T). Next: scripts/launch_block.sh 1"
