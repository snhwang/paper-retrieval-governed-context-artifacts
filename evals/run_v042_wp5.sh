#!/usr/bin/env bash
# WP5 on BEAR 0.4.2 (public tag v0.4.2, 0d0718a).
#
#   bash evals/run_v042_wp5.sh [step...]   # default: every step, in order
#   steps: nemotron_toolbench nemotron_petsim bge_petsim bge_toolbench cpa
#   V042_OUT=results/repro bash evals/run_v042_wp5.sh   # write elsewhere
#
# Run by hand from the repo root inside WSL, with the evaluation venv active
# (BEAR 0.4.2 installed) and the BGE-base model in the Hugging Face cache. The
# 2026-10-31 outputs in results/*_v042* came from an agent validation run of
# this script. Outputs are never overwritten, so a second run needs V042_OUT
# set to a new directory (created if missing).
#
# Nemotron: only the two BEAR rows, from cached vectors, with no request to the
# Nemotron service (rerun_filter_baseline_bear_cached.py). The LlamaIndex rows
# are reused from the 0.4.0 files, since they do not use BEAR's retrieval. In
# the 2026-10-31 run the stores lacked the governed-corpus document texts
# (3,225 on ToolBench, 44 on the Pet Simulation), so both steps stopped before
# retrieving and wrote *_missing.json. They need those texts embedded through
# the Nemotron service first. A stopped Nemotron step does not stop the others.
#
# BGE (WP5a both corpora, WP5b CPA): live on the CPU, as at 0.4.0. BEAR's
# Embedder batching is identical in 0.4.0 and 0.4.2, and LlamaIndex keeps its
# default embed_batch_size. Both are recorded in the outputs.
#
# CUDA hidden. One step at a time under ~/bin/tist-capped --mem 8G, each after
# tist.slice memory other than page cache is at or below 25 GB, and only while
# no tist-v042-rerun service (run_v042_rerun.sh) is active.
set -uo pipefail
cd "$(dirname "$0")/.."
python -c "import bear,sys; sys.exit(0 if bear.__version__=='0.4.2' else 'BEAR 0.4.2 required')" || exit 1
export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-$(python evals/bear_sha.py)}  # the installed BEAR's commit
export CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
PY=$(command -v python)
TC=${TIST_CAPPED:-$HOME/bin/tist-capped}
[ -x "$TC" ] || { echo "tist-capped not found at $TC (set TIST_CAPPED)"; exit 1; }
CG=/sys/fs/cgroup$(systemctl --user show tist.slice -p ControlGroup --value 2>/dev/null)
[ -r "$CG/memory.stat" ] || { echo "tist.slice not found (start it with tist-capped once)"; exit 1; }
SLICE_MAX=$((25 * 1024 * 1024 * 1024))
OUT=${V042_OUT:-results}
mkdir -p "$OUT"

slice_wait() {
  local cur file shmem used
  while systemctl --user is-active -q tist-v042-rerun 2>/dev/null; do
    echo "### waiting for tist-v042-rerun to finish $(date -u +%FT%TZ)"
    sleep 120
  done
  while :; do
    cur=$(cat "$CG/memory.current")
    file=$(awk '$1 == "file" {print $2}' "$CG/memory.stat")
    shmem=$(awk '$1 == "shmem" {print $2}' "$CG/memory.stat")
    used=$(( cur - file + shmem ))
    echo "### tist.slice without page cache $((used / 1024 / 1024)) MiB $(date -u +%FT%TZ)"
    (( used <= SLICE_MAX )) && return 0
    sleep 60
  done
}

step() {  # name threads script args...
  local name=$1 threads=$2 rc
  shift 2
  slice_wait
  echo "=== $name start $(date -u +%FT%TZ)"
  env OMP_NUM_THREADS="$threads" MKL_NUM_THREADS="$threads" "$TC" --mem 8G -- "$PY" "$@"
  rc=$?
  echo "=== $name exit $rc $(date -u +%FT%TZ)"
  return "$rc"
}

nemotron_toolbench() {
  step nemotron_toolbench 1 evals/rerun_filter_baseline_bear_cached.py --corpus toolbench \
    --old results/metadata_filter_baseline_toolbench_nemotron.json \
    --output "$OUT/metadata_filter_baseline_toolbench_nemotron_v042.json" \
    --log-file "$OUT/metadata_filter_baseline_toolbench_nemotron_v042_output.txt"
}
nemotron_petsim() {
  step nemotron_petsim 1 evals/rerun_filter_baseline_bear_cached.py --corpus petsim \
    --old results/metadata_filter_baseline_petsim_nemotron.json \
    --output "$OUT/metadata_filter_baseline_petsim_nemotron_v042.json" \
    --log-file "$OUT/metadata_filter_baseline_petsim_nemotron_v042_output.txt"
}
bge_petsim() {
  step bge_petsim 8 evals/eval_metadata_filter_baseline.py --corpus petsim --encoders bge \
    --output "$OUT/metadata_filter_baseline_petsim_bge_v042.json" \
    --log-file "$OUT/metadata_filter_baseline_petsim_bge_v042_output.txt"
}
bge_toolbench() {
  step bge_toolbench 8 evals/eval_metadata_filter_baseline.py --corpus toolbench --encoders bge \
    --output "$OUT/metadata_filter_baseline_toolbench_bge_v042.json" \
    --log-file "$OUT/metadata_filter_baseline_toolbench_bge_v042_output.txt"
}
cpa() {
  step cpa 8 evals/eval_cpa_maintained.py \
    --output "$OUT/cpa_maintained_v042.json" --log-file "$OUT/cpa_maintained_v042_output.txt"
}

echo "### run_v042_wp5.sh ${*:-all}, BEAR_SOURCE_SHA ${BEAR_SOURCE_SHA}, outputs in ${OUT}, $(date -u +%FT%TZ)"
steps=("$@")
(( ${#steps[@]} )) || steps=(nemotron_toolbench nemotron_petsim bge_petsim bge_toolbench cpa)
failed=0
for s in "${steps[@]}"; do
  declare -F "$s" >/dev/null || { echo "unknown step $s"; exit 2; }
  if ! "$s"; then
    # A Nemotron step that stops on missing cached texts is reported, not fatal.
    [[ $s == nemotron_* ]] || { echo "### stopped at $s"; exit 1; }
    echo "### $s failed, continuing (see its log)"
    failed=1
  fi
done
(( failed )) && { echo "### run_v042_wp5.sh done with a failed Nemotron step $(date -u +%FT%TZ)"; exit 1; }
echo "### run_v042_wp5.sh done $(date -u +%FT%TZ)"
