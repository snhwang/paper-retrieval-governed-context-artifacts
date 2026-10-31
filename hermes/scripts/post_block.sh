#!/bin/bash
# After a stage-2 block ends: status, checks (with verify-audit), and that block's analysis.
#
#   scripts/post_block.sh N
#
# Offline: contacts neither 8355 nor 8360. Reads $WP7_RUNS/stage2-bN and writes
#   $WP7_RUNS/stage2-bN/checks/          checks.json, summary.json, verify_audit.txt
#   $WP7_ANALYSIS/stage2-bN/             the block's tables.md, summary.json, cells.csv, ...
# Block 2 runs only C-cut. Its analysis also reads the C-gate and B baselines from the stage-1
# root ($WP7_RUNS/stage1, operators at 0 and 100 decoys, guests at 100). The combined analysis
# over all three blocks is scripts/analyze_stage2.sh.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
N=${1:?usage: post_block.sh N}
R=$WP7_RUNS/stage2-b$N
OUT=$WP7_ANALYSIS/stage2-b$N
[ -f "$R/logs/plan.json" ] || { echo "no block-$N run at $R"; exit 1; }
systemctl --user is-active --quiet "tist-wp7-stage2-b$N" && { echo "tist-wp7-stage2-b$N is still running"; exit 1; }
mkdir -p "$OUT"
wp7_record_begin "post-block$N" "$R"
cd "$WP7_HERMES_DIR" || exit 20
python3 "$WP7_SCRIPTS/status.py" "$R" > "$OUT/status.json"; head -30 "$OUT/status.json"
wp7_step "checks" 8G "$WP7_PY" checks.py --root "$R" --out-dir "$R/checks" --jobs 8 --expect-sources-removed \
  --registry "$WP7_HERMES_DIR/registry/harness_registry.json" > "$R/checks.console" 2>&1
echo "checks exit $? (exit 1 means some checks failed, see the list below)"
tail -30 "$R/checks.console" | cut -c1-200
BASE=()
if [ "$N" = 2 ]; then
  [ -f "$WP7_RUNS/stage1/logs/plan.json" ] || { echo "block 2's baselines need the stage-1 run at $WP7_RUNS/stage1"; exit 2; }
  BASE=(--baseline "$WP7_RUNS/stage1")
fi
wp7_step "analysis" 8G "$WP7_PY_ANALYSIS" analyze_stage2.py --roots "$R" "${BASE[@]}" --out "$OUT"   --checks-dirs "$R/checks" || exit 2
echo "== done $(date -u +%T). Tables: $OUT/tables.md"
