#!/bin/bash
# Stage-2 settings from the stage-1 run: the offline k sweep for C-cut and the annotation cost.
#
#   scripts/stage2_settings.sh
#
# Needs BEAR v0.4.2 in the runner venv (both scripts use its BM25 and annotate code). Offline:
# the k sweep replays BM25 with BEAR's own code and reads Nemotron rankings from the stage-1
# records, so neither 8355 nor 8360 is contacted. Writes $WP7_ANALYSIS/stage2-settings/
# ksweep.{json,md} and annotation_cost.{json,md}. The block-2 spec uses k=15, the choice from the
# agent-run stage 1 (hermes/results/stage2/ksweep.md). If this run's ksweep.md gives another k,
# decide before block 2 and edit specs/stage2_block2.json in a commit.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
R=$WP7_RUNS/stage1
OUT=$WP7_ANALYSIS/stage2-settings
[ -f "$R/logs/plan.json" ] || { echo "no stage-1 run at $R"; exit 1; }
wp7_require_bear 0.4.2 || exit 1
mkdir -p "$OUT"
wp7_record_begin stage2-settings "$R"
cd "$WP7_HERMES_DIR" || exit 20
wp7_step "k sweep" 8G "$WP7_PY" ksweep_stage2.py --root "$R" --out "$OUT" \
  --registry "$WP7_HERMES_DIR/registry/harness_registry.stage1.json" > "$OUT/ksweep.console" 2>&1 || exit 1
wp7_step "annotation cost" 8G "$WP7_PY" annotation_cost_stage2.py --root "$R" --out "$OUT" \
  > "$OUT/annotation_cost.console" 2>&1 || exit 2
python3 - "$OUT/ksweep.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for k, v in d.get("choice", {}).items():
    print(k, v)
EOF
echo "== done. Compare: diff $WP7_HERMES_DIR/results/stage2/ksweep.md $OUT/ksweep.md"
