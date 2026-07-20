#!/usr/bin/env bash
# Unattended driver: same-format native-reasoning ablation on both Gemma models.
#
# Pairs the constrained {thought, action} scaffold with native thinking ON against
# the existing native-OFF runs. Because the output format is identical in both,
# the difference isolates native reasoning -- which the cross-format comparison
# (scaffold-off 0.660 vs reasoning-mode-on 0.620) cannot do.
#
# Usage (from repo root), safe to leave running:
#     nohup bash evals/run_scaffold_thinking_ablation.sh > scaffold_ablation.out 2>&1 &
#
# Design for unattended operation:
#   * PREFLIGHT: each model is first run on 30 queries. The scaffold has never
#     been run with thinking ON, so if the JSON grammar and the thinking channel
#     interact badly the empty-response guard aborts in ~1 min and we skip that
#     model's long run instead of burning ~9 h on it.
#   * Order: 31B first (the headline model), so an interruption still leaves the
#     result that matters most.
#   * Each stage tees to its own log; failures do not stop the remaining stages.
#
# Runtime: ~8-9 h for 31B, ~4-5 h for 12B (monolithic + native thinking is the
# slowest configuration we run). Total ~13 h.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://192.168.1.175:11434/v1}"
SAMPLING="--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64"

run_model () {
  local MODEL="$1" LABEL="$2"
  echo
  echo "=================================================================="
  echo "[$(date)] $MODEL ($LABEL)"
  echo "=================================================================="

  echo "[$(date)] PREFLIGHT: 30 queries -- checking the scaffold tolerates thinking"
  if ! python evals/eval_toolbench_react.py --skip bear-single --max-queries 30 \
        $SAMPLING --base-url "$BASE_URL" --model "$MODEL" \
        --run-label ${LABEL}-scaffold-thinking-PREFLIGHT \
        > results/${LABEL}_scaffold_thinking_preflight.log 2>&1; then
    echo "[$(date)] PREFLIGHT FAILED for $MODEL -- skipping its full run."
    grep -aE "FATAL|EMPTY|Common cause" results/${LABEL}_scaffold_thinking_preflight.log | head -5
    rm -f results/toolbench_react_*_${LABEL}-scaffold-thinking-PREFLIGHT_partial.*
    return 1
  fi
  grep -aE "done; tool-acc|empty =" results/${LABEL}_scaffold_thinking_preflight.log | tail -2
  rm -f results/toolbench_react_*_${LABEL}-scaffold-thinking-PREFLIGHT_partial.*
  echo "[$(date)] preflight clean -- starting full 1,100 run"

  MODEL="$MODEL" LABEL="$LABEL" BASE_URL="$BASE_URL" \
    bash evals/run_model_scaffold_thinking.sh \
    || { echo "[$(date)] full run FAILED for $MODEL"; return 1; }
}

run_model gemma4:31b g4-31b
run_model gemma4:12b g4-12b

echo
echo "[$(date)] ================= RESULTS ================="
for L in g4-31b g4-12b; do
  echo
  python evals/scaffold_thinking_ablation.py "$L" 2>&1 || echo "  ($L incomplete)"
done
echo
echo "[$(date)] ALL DONE"
