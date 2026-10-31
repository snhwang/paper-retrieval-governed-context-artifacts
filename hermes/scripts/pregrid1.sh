#!/bin/bash
# Stage-1 checks before the grid. Stops at the first failure.
#
#   WP7_HARNESS_DIR=$WP7_RUNS/artifacts-stage1/hermes scripts/pregrid1.sh
#
# Needs BEAR v0.4.1 in the runner venv and WP7_HARNESS_DIR at the stage-1 harness commit
# 9820f8a (REPRODUCE.md, step S1.1). Steps:
#   1. validate.py: lint the corpus at 0, 100 and 300 decoys, validate the 24 arm configs (offline)
#   2. the cell red team, bridged (contacts 8355 and 8360)
#   3. provenance_check.py against expected/stage1.json (contacts 8355 and 8360)
#   4. a 4-cell re-smoke: A and D, operator and guest, 0 decoys, ambiguous_delete_ask (uses 8355
#      and 8360, flushes the 8355 cache before each cell)
#   5. checks.py on the re-smoke (offline)
#   6. resmoke_gate.py --stage 1 (offline)
# Takes about 3 minutes. Its roots are $WP7_RUNS/stage1-redteam and $WP7_RUNS/stage1-resmoke,
# which must not exist yet.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
RT=$WP7_RUNS/stage1-redteam
RS=$WP7_RUNS/stage1-resmoke
for r in "$RT" "$RS"; do
  [ -e "$r" ] && { echo "$r exists. Move it away or set WP7_RUNS to a new directory."; exit 21; }
done
mkdir -p "$WP7_RUNS"
wp7_record_begin pregrid1 "$RS"
echo "harness $WP7_HARNESS_DIR at $(git -C "$WP7_HARNESS_DIR" rev-parse --short HEAD), MemAvailable $(wp7_mem_gb) GB"
wp7_require_bear 0.4.1 || exit 10
wp7_no_active_grid || exit 11
cd "$WP7_HARNESS_DIR" || exit 20

WP7_HARNESS_DIR=$WP7_HARNESS_DIR wp7_step "1. validate" 8G "$WP7_PY" "$WP7_SCRIPTS/validate.py" || exit 1
wp7_step "2. red team (bridged)" 8G "$WP7_PY" run.py redteam --root "$RT" > "$WP7_RUNS/stage1-redteam.txt" 2>&1
rc=$?; grep -E "^FAIL" "$WP7_RUNS/stage1-redteam.txt" | head -20; tail -1 "$WP7_RUNS/stage1-redteam.txt"
[ $rc -eq 0 ] || exit 2
wp7_step "3. provenance" 4G "$WP7_PY" "$WP7_SCRIPTS/provenance_check.py" "$WP7_SCRIPTS/expected/stage1.json" || exit 3
wp7_step "4. re-smoke" 8G "$WP7_PY" run.py matrix --root "$RS" --arms A,D --roles operator,guest --decoys 0 \
  --tasks ambiguous_delete_ask > "$WP7_RUNS/stage1-resmoke.console" 2>&1
rc=$?; tail -2 "$WP7_RUNS/stage1-resmoke.console" | cut -c1-300
[ $rc -eq 0 ] || exit 4
cd "$WP7_HERMES_DIR" || exit 20
wp7_step "5. checks" 8G "$WP7_PY" checks.py --root "$RS" \
  --registry "$WP7_HERMES_DIR/registry/harness_registry.stage1.json" > "$RS/checks.console" 2>&1
rc=$?; tail -4 "$RS/checks.console"
[ $rc -eq 0 ] || exit 5
wp7_step "6. gates" 4G "$WP7_PY_ANALYSIS" "$WP7_SCRIPTS/resmoke_gate.py" "$RS" --stage 1 || exit 6
echo "== all stage-1 pre-grid steps passed $(date -u +%T). Next: scripts/launch_stage1.sh"
