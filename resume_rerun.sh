#!/usr/bin/env bash
# =============================================================================
# resume_rerun.sh — crash-resilient continuation of run_evals.sh
#
# Runs the steps of the author re-run that had not completed, one at a time,
# recording a marker in results/.rerun_done/ after each success. If WSL (or
# anything else) crashes mid-run, just execute this script again: completed
# steps are skipped and work continues at the step that was interrupted.
#
# The steps already completed by the 2026-08-04 partial run (Pet Sim suite,
# backend comparison, ablations, decomposed, alpha sweep, baseline comparison,
# scalability, tool scaling, composition, parameter sensitivity) are
# pre-seeded as done by seed_completed(). Delete results/.rerun_done to force
# everything to re-run from scratch.
#
# Usage:  ./resume_rerun.sh
# =============================================================================

set -e
cd "$(dirname "$0")"

PY="python3"
[[ -x ".venv/bin/python" ]] && PY=".venv/bin/python"
if ! "$PY" -c "import bear" 2>/dev/null; then
  echo "ERROR: cannot import bear with $PY. Run inside WSL from the repo root." >&2
  exit 1
fi

EVAL_DIR="evals"
RESULTS_DIR="results"
DONE_DIR="$RESULTS_DIR/.rerun_done"
LOG="$RESULTS_DIR/author_rerun_2026-08-01.log"
mkdir -p "$DONE_DIR"

step() {
  local name="$1"; shift
  if [[ -f "$DONE_DIR/$name" ]]; then
    echo "=== SKIP (done): $name ==="
    return 0
  fi
  echo "=== RUN: $name ===" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  touch "$DONE_DIR/$name"
  echo "=== DONE: $name ===" | tee -a "$LOG"
}

seed_completed() {
  # Steps the 2026-08-04 partial run finished before WSL crashed.
  local finished=(petsim_lexical petsim_semantic backends gov_ablation
                  decomposed alpha_sweep baseline scalability tool_scaling
                  composition sensitivity_lex sensitivity_sem)
  for s in "${finished[@]}"; do touch "$DONE_DIR/$s"; done
}
[[ -f "$DONE_DIR/.seeded" ]] || { seed_completed; touch "$DONE_DIR/.seeded"; }

# --- the interrupted block, split so a crash costs one chunk, not hours ---
step toolbench_retrieval  "$PY" "$EVAL_DIR/eval_toolbench.py" --toolbench-only --latex
step metatool_retrieval   "$PY" "$EVAL_DIR/eval_toolbench.py" --metatool-only --latex

# --- remaining tail, one step each ---
step inferred_top1   "$PY" "$EVAL_DIR/eval_toolbench_inferred_categories.py"
step inferred_multi  "$PY" "$EVAL_DIR/eval_toolbench_multitag_categories.py"
step inferred_top5   "$PY" "$EVAL_DIR/eval_toolbench_top5_categories.py"
step safety          "$PY" "$EVAL_DIR/eval_scope_excluded_safety.py"
step diagnosis       "$PY" "$EVAL_DIR/eval_petsim_fix_diagnosis.py"
step transfer_tb     "$PY" "$EVAL_DIR/eval_backend_transfer.py" --corpus toolbench
step transfer_mt     "$PY" "$EVAL_DIR/eval_backend_transfer.py" --corpus metatool
step reranker_petsim "$PY" "$EVAL_DIR/eval_reranker_composition.py" --corpus petsim
step reranker_tb     "$PY" "$EVAL_DIR/eval_reranker_composition.py" --corpus toolbench
step framework_ps    "$PY" "$EVAL_DIR/eval_framework_baseline.py" --corpus petsim
step framework_tb    "$PY" "$EVAL_DIR/eval_framework_baseline.py" --corpus toolbench
step demo            bash -c "\"$PY\" \"$EVAL_DIR/demo_composition.py\" > \"$RESULTS_DIR/composition_demo.txt\" 2>&1"

echo ""
echo "All remaining steps complete. Now verify:"
echo "  $PY evals/verify_rerun.py"
