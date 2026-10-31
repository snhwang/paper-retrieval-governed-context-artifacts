#!/bin/bash
# The stage-2 analysis over all three blocks (run post_block.sh for each block first).
#
#   scripts/analyze_stage2.sh
#
# Offline. Reads $WP7_RUNS/stage2-b1, -b2 and -b3 with their checks, and writes
# $WP7_ANALYSIS/stage2/ (tables.md, summary.json, cells.csv, groups.csv, paired.csv,
# digest_match.json, spoof.json, asks.json). 10,000 bootstrap resamples, seed 20261031.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
roots=() checks=()
for n in 1 2 3; do
  R=$WP7_RUNS/stage2-b$n
  [ -f "$R/logs/plan.json" ] || { echo "no block-$n run at $R"; exit 1; }
  [ -f "$R/checks/checks.json" ] || { echo "block $n has no checks yet: scripts/post_block.sh $n"; exit 1; }
  roots+=("$R"); checks+=("$R/checks")
done
OUT=$WP7_ANALYSIS/stage2
mkdir -p "$OUT"
wp7_record_begin analyze-stage2 "$WP7_RUNS"
cd "$WP7_HERMES_DIR" || exit 20
wp7_step "analysis" 8G "$WP7_PY_ANALYSIS" analyze_stage2.py --roots "${roots[@]}" --out "$OUT" \
  --boot 10000 --seed 20261031 --checks-dirs "${checks[@]}" || exit 1
echo "== done $(date -u +%T). Tables: $OUT/tables.md"
