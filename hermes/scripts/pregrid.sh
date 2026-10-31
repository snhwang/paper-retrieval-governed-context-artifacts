#!/bin/bash
# Checks before the first grid on the current harness (stage 1, then stage 2). Stops at the first
# failure.
#
#   scripts/pregrid.sh
#
# Needs BEAR v0.4.2 in the runner venv, and WP7_HARNESS_DIR (default: this checkout's hermes/).
# Steps:
#   1. test_stage2_tasks.py: derived tokens, cron-only grep, spoof grader (offline)
#   2. plan-only for the four specs: stage 1 1,656 cells, blocks 874, 414 and 276 (offline)
#   3. check_block2_baselines.py: block 2's C-gate and B baselines are stage-1 cells with identical
#      settings (offline)
#   4. the cell red team, offline (no bridge, the two ports must be unreachable)
#   5. the cell red team, bridged (contacts 8355 and 8360)
#   6. provenance_check.py against expected/stage1_v2.json (contacts 8355 and 8360)
#   7. a 4-cell re-smoke: A and D, operator and guest, 0 decoys, ambiguous_delete_ask (uses 8355
#      and 8360, flushes the 8355 cache before each cell)
#   8. checks.py on the re-smoke, with --expect-sources-removed (offline)
#   9. resmoke_gate.py --harness current (offline)
# Takes about 3 minutes. Its roots are $WP7_RUNS/pregrid-redteam-offline, pregrid-redteam and
# pregrid-resmoke, which must not exist yet. Set WP7_NOT_BEFORE="YYYY-MM-DD HH:MM:SS" (UTC) to
# refuse to start before a booked window. The launchers repeat the provenance check before every
# grid, so this script is needed once, unless the harness, BEAR or a server changes.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
if [ -n "${WP7_NOT_BEFORE:-}" ] && [ "$(date -u +%s)" -lt "$(date -u -d "$WP7_NOT_BEFORE" +%s)" ]; then
  echo "too early: it is $(date -u +%T) UTC, the window opens at $WP7_NOT_BEFORE"; exit 29
fi
RO=$WP7_RUNS/pregrid-redteam-offline
RT=$WP7_RUNS/pregrid-redteam
RS=$WP7_RUNS/pregrid-resmoke
for r in "$RO" "$RT" "$RS"; do
  [ -e "$r" ] && { echo "$r exists. Move it away or set WP7_RUNS to a new directory."; exit 21; }
done
mkdir -p "$WP7_RUNS"
wp7_record_begin pregrid "$RS"
echo "harness $WP7_HARNESS_DIR at $(git -C "$WP7_HARNESS_DIR" rev-parse --short HEAD), MemAvailable $(wp7_mem_gb) GB"
wp7_require_bear 0.4.2 || exit 10
wp7_no_active_grid || exit 11
cd "$WP7_HARNESS_DIR" || exit 20

wp7_step "1. stage-2 task tests" 4G "$WP7_PY" "$WP7_SCRIPTS/test_stage2_tasks.py" || exit 1
for pair in stage1_v2:1656 stage2_block1:874 stage2_block2:414 stage2_block3:276; do
  spec=${pair%%:*} want=${pair##*:}
  got=$("$WP7_PY" run.py matrix --root "$WP7_RUNS/plan-only" --spec "specs/$spec.json" \
        --plan-only 2>/dev/null | awk '$2 == "cells," {print $1}')
  echo "== 2. $spec plan: ${got:-?} cells (expected $want)"
  [ "${got:-}" = "$want" ] || exit 2
done
wp7_step "3. block-2 baselines" 4G "$WP7_PY" "$WP7_SCRIPTS/check_block2_baselines.py" || exit 3
wp7_step "4. red team (offline)" 4G "$WP7_PY" run.py redteam --root "$RO" --offline > "$WP7_RUNS/pregrid-redteam-offline.txt" 2>&1
rc=$?; grep -E "^FAIL" "$WP7_RUNS/pregrid-redteam-offline.txt" | head -20; tail -1 "$WP7_RUNS/pregrid-redteam-offline.txt"
[ $rc -eq 0 ] || exit 4
wp7_step "5. red team (bridged)" 8G "$WP7_PY" run.py redteam --root "$RT" > "$WP7_RUNS/pregrid-redteam.txt" 2>&1
rc=$?; grep -E "^FAIL" "$WP7_RUNS/pregrid-redteam.txt" | head -20; tail -1 "$WP7_RUNS/pregrid-redteam.txt"
[ $rc -eq 0 ] || exit 5
wp7_step "6. provenance" 4G "$WP7_PY" "$WP7_SCRIPTS/provenance_check.py" "$WP7_SCRIPTS/expected/stage1_v2.json" || exit 6
wp7_step "7. re-smoke" 8G "$WP7_PY" run.py matrix --root "$RS" --arms A,D --roles operator,guest --decoys 0 \
  --tasks ambiguous_delete_ask > "$WP7_RUNS/pregrid-resmoke.console" 2>&1
rc=$?; tail -2 "$WP7_RUNS/pregrid-resmoke.console" | cut -c1-300
[ $rc -eq 0 ] || exit 7
cd "$WP7_HERMES_DIR" || exit 20
wp7_step "8. checks" 8G "$WP7_PY" checks.py --root "$RS" --expect-sources-removed \
  --registry "$WP7_HERMES_DIR/registry/harness_registry.json" > "$RS/checks.console" 2>&1
rc=$?; tail -4 "$RS/checks.console"
[ $rc -eq 0 ] || exit 8
wp7_step "9. gates" 4G "$WP7_PY_ANALYSIS" "$WP7_SCRIPTS/resmoke_gate.py" "$RS" --harness current || exit 9
grep -h "staged sources removed" "$RS"/logs/*.stderr 2>/dev/null | sort | uniq -c
echo "== all pre-grid steps passed $(date -u +%T). Next: scripts/launch_stage1.sh"
