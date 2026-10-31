#!/usr/bin/env bash
# Qwen3-0.6B (tag noise and leakage) and Qwen3-4B (leakage) for WP6.
#
#   bash evals/run_qwen_gpu.sh          # embed on the GPU, then run on the CPU
#   bash evals/run_qwen_gpu.sh embed    # the GPU steps only
#   bash evals/run_qwen_gpu.sh run      # the CPU run phases only
#
# Run by hand from the repo root inside WSL with the evaluation venv active,
# when the GPU is free of other jobs (the gate below checks). BEAR is the
# public 0.4.2 (tag v0.4.2, 0d0718a). The 2026-10-31 outputs (results/
# tag_noise_qwen3-0.6b*, leakage_threat_qwen*, qwen_gpu_v042_job.log) came
# from an agent validation run of this script. The stores it filled stay in
# ~/.cache/tist-r2-embeddings, so a second run only re-embeds what is
# missing. Outputs are never overwritten, so a second run needs QWEN_OUT set
# to a new directory (created if missing).
#
# Precision: both models run in float16 on the GPU, as the existing ToolBench
# Qwen3-0.6B store was made (TIST_FP16_BACKENDS=qwen3-0.6b, and Qwen3-4B is
# always float16). A store refuses vectors of other settings, so no precision
# is mixed.
#
# Batches. Qwen3-0.6B: at most 8 texts and 16,000 characters per batch, under
# a 6 GiB allocator cap. Qwen3-4B: exactly 2 texts per batch, the last one
# padded (TIST_FIXED_BATCH=1), under a 12 GiB cap. Nothing is truncated. The
# longest batch goes first and its memory is logged as the probe. Each fill is
# recorded in its store (batch, precision, device, probe), and every run output
# carries those records (provenance.embedding_stores). A fill stops on a wrong
# row count, a bad vector, a model that is not the one asked for (BEAR falls
# back to hash embeddings on a failed load), or a text left missing.
#
# GPU steps (fill the stores): one process at a time, each under
# `flock ~/tist-gpu.lock` and gpu_guard.sh (start at Windows nvidia-smi
# <= 67,000 MiB, stop above 80,000 every 15 s, not while wp0-gpuq4b042 or
# wp0-e2erun runs or Ollama holds a model). A step the gate refuses waits
# 2 minutes and tries again, at most TIST_GATE_TRIES times (360, 12 hours),
# releasing the lock between tries. No step talks to the Nemotron service.
#
# Needed: MetaTool+Tags 42,095 queries and 398 docs (Qwen3-0.6B, new store),
# 4,400 ToolBench leakage queries (Qwen3-0.6B, existing store), and 6,598
# queries and 6,450 docs (Qwen3-4B, new store).
#
# CPU run phases: CUDA hidden, under tist-capped --mem 12G, at most 8 workers,
# each after tist.slice holds at most 25 GB other than page cache (the
# kernel reclaims cache inside the slice's cap first). Any failed step
# stops the job with a non-zero exit.
set -uo pipefail
cd "$(dirname "$0")/.."
python -c "import bear,sys; sys.exit(0 if bear.__version__=='0.4.2' else 'BEAR 0.4.2 required')" || exit 1
export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-0d0718a39a0b0788ef5cca4689352462b830494c}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TIST_FP16_BACKENDS=qwen3-0.6b
unset TIST_MAX_BATCH TIST_FIXED_BATCH TIST_CHAR_BUDGET
PY=$(command -v python)
TC=${TIST_CAPPED:-$HOME/bin/tist-capped}
[ -x "$TC" ] || { echo "tist-capped not found at $TC (set TIST_CAPPED)"; exit 1; }
LOCK=$HOME/tist-gpu.lock
CG=/sys/fs/cgroup$(systemctl --user show tist.slice -p ControlGroup --value 2>/dev/null)
[ -r "$CG/memory.stat" ] || { echo "tist.slice not found (start it with tist-capped once)"; exit 1; }
OUT=${QWEN_OUT:-results}
mkdir -p "$OUT"
SLICE_MAX=$((25 * 1024 * 1024 * 1024))
SMI=/mnt/c/Windows/System32/nvidia-smi.exe

card() { "$SMI" --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1 | tr -d '\r'; }

slice_wait() {  # waits on memory the kernel cannot reclaim, not on page cache
  local cur file shmem used
  while :; do
    cur=$(cat "$CG/memory.current")
    file=$(awk '$1 == "file" {print $2}' "$CG/memory.stat")
    shmem=$(awk '$1 == "shmem" {print $2}' "$CG/memory.stat")
    used=$(( cur - file + shmem ))
    echo "### tist.slice memory.current $((cur / 1024 / 1024)) MiB, without page cache $((used / 1024 / 1024)) MiB $(date -u +%FT%TZ)"
    (( used <= SLICE_MAX )) && return 0
    sleep 60
  done
}

gpu_step() {  # name cap_gib max_batch fixed(0|1) script args...
  local name=$1 cap=$2 batch=$3 fixed=$4 rc=75 try
  shift 4
  for (( try = 1; try <= ${TIST_GATE_TRIES:-360}; try++ )); do
    slice_wait
    echo "=== $name: try $try, cap ${cap} GiB, batch ${batch} (fixed ${fixed}) $(date -u +%FT%TZ)"
    flock "$LOCK" env -u CUDA_VISIBLE_DEVICES TIST_REQUIRE_CUDA=1 TIST_GPU_CAP_GIB="$cap" \
      TIST_MAX_BATCH="$batch" TIST_FIXED_BATCH="$fixed" OMP_NUM_THREADS=4 \
      bash evals/gpu_guard.sh "$cap" "$TC" --mem 12G -- "$PY" "$@"
    rc=$?
    (( rc == 75 )) || break
    sleep 120
  done
  echo "=== $name exit $rc $(date -u +%FT%TZ), card $(card)"
  return "$rc"
}

cpu_step() {  # name script args...
  local name=$1 rc
  shift
  slice_wait
  echo "=== $name start $(date -u +%FT%TZ)"
  env CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$TC" --mem 12G -- "$PY" "$@"
  rc=$?
  echo "=== $name exit $rc $(date -u +%FT%TZ)"
  return "$rc"
}

embed() {
  gpu_step qwen06_tagnoise 6 8 0 evals/eval_tag_noise.py --phase embed --backends qwen3-0.6b || return
  gpu_step qwen06_leakage 6 8 0 evals/eval_leakage_threat.py --phase embed --backends qwen3-0.6b || return
  gpu_step qwen4b_leakage 12 2 1 evals/eval_leakage_threat.py --phase embed --backends qwen3-4b
}

run() {
  cpu_step tagnoise_qwen06 evals/eval_tag_noise.py --phase run --backends qwen3-0.6b --workers 8 \
    --output "$OUT/tag_noise_qwen3-0.6b.json" \
    --log-file "$OUT/tag_noise_qwen3-0.6b_output.txt" || return
  cpu_step leakage_qwen evals/eval_leakage_threat.py --phase run --backends qwen3-0.6b qwen3-4b \
    --output "$OUT/leakage_threat_qwen.json" \
    --log-file "$OUT/leakage_threat_qwen_output.txt"
}

echo "### run_qwen_gpu.sh ${1:-all}, BEAR_SOURCE_SHA ${BEAR_SOURCE_SHA}, start $(date -u +%FT%TZ), card $(card)"
case ${1:-all} in
  embed) embed ;;
  run)   run ;;
  all)   embed && run ;;
  *)     echo "usage: bash evals/run_qwen_gpu.sh [embed|run|all]" >&2; exit 2 ;;
esac
rc=$?
echo "### run_qwen_gpu.sh exit ${rc} $(date -u +%FT%TZ), card $(card)"
exit "$rc"
