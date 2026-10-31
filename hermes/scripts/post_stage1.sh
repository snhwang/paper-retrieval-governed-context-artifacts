#!/bin/bash
# After the stage-1 grid: checks (with verify-audit), the stage-1 analysis and its extras.
#
#   scripts/post_stage1.sh
#
# Offline: contacts neither 8355 nor 8360. Reads $WP7_RUNS/stage1 and writes
#   $WP7_RUNS/stage1/checks/              checks.json, summary.json, verify_audit.txt
#   $WP7_ANALYSIS/stage1/                 tables.md, summary.json, cells.csv, per_task.csv, ...
#                                         plus checks_summary.json, run_info.json, sandbox_redteam.json
# The analysis uses 10,000 bootstrap resamples with seed 20261030, as reported. Compare with the
# committed hermes/results/stage1/ (the agent-run grid) using the diff command printed at the end.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
R=$WP7_RUNS/stage1
OUT=$WP7_ANALYSIS/stage1
[ -f "$R/logs/plan.json" ] || { echo "no stage-1 run at $R"; exit 1; }
systemctl --user is-active --quiet tist-wp7-stage1 && { echo "tist-wp7-stage1 is still running"; exit 1; }
mkdir -p "$OUT"
wp7_record_begin post-stage1 "$R"
cd "$WP7_HERMES_DIR" || exit 20
python3 "$WP7_SCRIPTS/status.py" "$R" > "$OUT/status.json"; head -20 "$OUT/status.json"
wp7_step "checks" 8G "$WP7_PY" checks.py --root "$R" --out-dir "$R/checks" --jobs 8 \
  --registry "$WP7_HERMES_DIR/registry/harness_registry.stage1.json" > "$R/checks.console" 2>&1
echo "checks exit $? (exit 1 means some checks failed; the stage-1 grid had 119 failures, all explained in CHANGES.md)"
tail -30 "$R/checks.console" | cut -c1-200
wp7_step "analysis" 8G "$WP7_PY_ANALYSIS" analyze_stage1.py --root "$R" --out "$OUT" --boot 10000 --seed 20261030 \
  --checks-dir "$R/checks" || exit 2
wp7_step "extras" 4G python3 "$WP7_SCRIPTS/results_extras.py" "$R" "$OUT" || exit 3
[ -f "$WP7_RUNS/stage1-redteam/redteam.json" ] && cp "$WP7_RUNS/stage1-redteam/redteam.json" "$OUT/sandbox_redteam.json"
echo "== done $(date -u +%T). Compare with the agent-run results:"
echo "   diff -r $WP7_HERMES_DIR/results/stage1 $OUT | head"
