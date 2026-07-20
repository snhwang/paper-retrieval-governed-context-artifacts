#!/usr/bin/env bash
# Verify the empty-response guard in eval_toolbench_react.py.
#
# Background: a condition where the model returns NOTHING scores 0 on every such
# query, which is indistinguishable from a wrong answer in the accuracy alone.
# That is how gemma4's "monolithic without reasoning" cell was once measured at
# 0.383 when 43% of its responses were empty -- the number reported silence, not
# selection ability. The guard aborts such a run instead of producing it.
#
# Usage (from repo root):
#     bash evals/verify_empty_guard.sh
#     MODEL=gemma4:31b BASE_URL=http://host:11434/v1 bash evals/verify_empty_guard.sh
#
# Expected outcome:
#   TEST 1 (broken config)  -> FATAL abort at query 25, naming the likely cause
#   TEST 2 (healthy config) -> completes, reports "empty = 0/30 (0.0%)", no abort
set -uo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-gemma4:31b}"
BASE_URL="${BASE_URL:-http://192.168.1.175:11434/v1}"
SAMPLING="--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64"

echo "############ TEST 1: BROKEN config -- expect FATAL abort ############"
echo "(--reasoning-mode with --reasoning-effort none: a thinking model asked to"
echo " reason free-form while its reasoning channel is disabled emits nothing)"
python evals/eval_toolbench_react.py --skip bear-react bear-single \
    --reasoning-mode --reasoning-effort none --max-queries 30 $SAMPLING \
    --run-label GUARDTEST-BROKEN --base-url "$BASE_URL" --model "$MODEL" 2>&1 \
  | grep -aE "FATAL|EMPTY|Common cause|Model=|override" || true

echo
echo "############ TEST 2: HEALTHY config -- expect clean completion ############"
python evals/eval_toolbench_react.py --skip mono-react bear-react \
    --reasoning-effort none --max-queries 30 $SAMPLING \
    --run-label GUARDTEST-GOOD --base-url "$BASE_URL" --model "$MODEL" 2>&1 \
  | grep -aE "FATAL|done; tool-acc|empty =|NOTE:" || true

echo
echo "Cleaning up test artifacts ..."
rm -f results/toolbench_react_metrics_GUARDTEST-*.json \
      results/toolbench_react_output_GUARDTEST-*.txt
echo "Done. TEST 1 should have aborted; TEST 2 should show empty = 0/30 (0.0%)."
