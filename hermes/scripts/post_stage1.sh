#!/bin/bash
# After the stage-1 grid: checks (with verify-audit), the stage-1 analysis and its extras.
#
#   scripts/post_stage1.sh [--harness current|9820f8a]
#
# Offline: contacts neither 8355 nor 8360. With the default (current harness) it reads
# $WP7_RUNS/stage1 and writes
#   $WP7_RUNS/stage1/checks/              checks.json, summary.json, verify_audit.txt
#   $WP7_ANALYSIS/stage1/                 tables.md, summary.json, cells.csv, per_task.csv, ...
#                                         plus checks_summary.json, run_info.json, sandbox_redteam.json
# The current harness uses the stage-2 registry (28 tools, manage_connections exposed) and expects
# the staged sources to be removed in every cell. --harness 9820f8a reads $WP7_RUNS/stage1-9820f8a
# with the stage-1 registry and writes $WP7_ANALYSIS/stage1-9820f8a/. The analysis uses 10,000
# bootstrap resamples with seed 20261030.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
harness=current
[ "${1:-}" = "--harness" ] && harness=${2:-}
case "$harness" in
  current) R=$WP7_RUNS/stage1; OUT=$WP7_ANALYSIS/stage1; U=tist-wp7-stage1
           REG=$WP7_HERMES_DIR/registry/harness_registry.json; EXTRA=(--expect-sources-removed)
           RT=$WP7_RUNS/pregrid-redteam ;;
  9820f8a) R=$WP7_RUNS/stage1-9820f8a; OUT=$WP7_ANALYSIS/stage1-9820f8a; U=tist-wp7-stage1-9820f8a
           REG=$WP7_HERMES_DIR/registry/harness_registry.stage1.json; EXTRA=()
           RT=$WP7_RUNS/9820f8a-redteam ;;
  *) echo "--harness must be current or 9820f8a"; exit 2 ;;
esac
[ -f "$R/logs/plan.json" ] || { echo "no stage-1 run at $R"; exit 1; }
systemctl --user is-active --quiet "$U" && { echo "$U is still running"; exit 1; }
mkdir -p "$OUT"
wp7_record_begin "post-stage1-$harness" "$R"
cd "$WP7_HERMES_DIR" || exit 20
python3 "$WP7_SCRIPTS/status.py" "$R" > "$OUT/status.json"; head -20 "$OUT/status.json"
wp7_step "checks" 8G "$WP7_PY" checks.py --root "$R" --out-dir "$R/checks" --jobs 8 "${EXTRA[@]}" \
  --registry "$REG" > "$R/checks.console" 2>&1
echo "checks exit $? (exit 1 means some checks failed, see the list below and CHANGES.md)"
tail -30 "$R/checks.console" | cut -c1-200
wp7_step "analysis" 8G "$WP7_PY_ANALYSIS" analyze_stage1.py --root "$R" --out "$OUT" --boot 10000 --seed 20261030 \
  --checks-dir "$R/checks" --registry "$REG" || exit 2
wp7_step "extras" 4G python3 "$WP7_SCRIPTS/results_extras.py" "$R" "$OUT" || exit 3
[ -f "$RT/redteam.json" ] && cp "$RT/redteam.json" "$OUT/sandbox_redteam.json"
echo "== done $(date -u +%T). Tables: $OUT/tables.md"
echo "   The agent-run stage 1 (old harness, BEAR v0.4.1) is in $WP7_HERMES_DIR/results/stage1 for comparison."
