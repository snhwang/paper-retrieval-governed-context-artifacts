#!/usr/bin/env bash
# Qwen3-0.6B (tag noise and leakage) and Qwen3-4B (leakage) for WP6.
#
#   bash evals/run_qwen_gpu.sh          # embed on the GPU, then run on the CPU
#   bash evals/run_qwen_gpu.sh embed    # the GPU steps only
#   bash evals/run_qwen_gpu.sh run      # the CPU run phases only
#
# Start only on the coordinator's go: after WP0's Qwen3-4B lane, before the
# Ollama rerun. Run from the repo root inside WSL, venv active.
#
# Precision: both models run in float16 on the GPU, as the existing ToolBench
# Qwen3-0.6B store was made (TIST_FP16_BACKENDS=qwen3-0.6b, and Qwen3-4B is
# always float16). A store refuses vectors of other settings, so no precision
# is mixed. Each run output records it (provenance.embedding_stores).
#
# GPU steps (fill the embedding stores): one process at a time, each under
# `flock ~/tist-gpu.lock` and gpu_guard.sh (start at Windows nvidia-smi
# <= 67,000 MiB, stop above 80,000 every 15 s, not while wp0-gpuq4b042 or
# wp0-e2erun runs or Ollama holds a model). PyTorch's allocator is capped at
# 6 GiB for Qwen3-0.6B and 12 GiB for Qwen3-4B, at most 8 texts per batch.
# A step the gate refuses is retried every 2 minutes, at most TIST_GATE_TRIES
# times (90), releasing the lock between tries.
#
# Needed: MetaTool+Tags 42,095 queries and 398 docs (Qwen3-0.6B, new store),
# 4,400 ToolBench leakage queries (Qwen3-0.6B, existing store), and 6,598
# queries and 6,450 docs (Qwen3-4B, new store).
#
# CPU run phases: CUDA hidden, under tist-capped --mem 12G, at most 8 workers,
# each after tist.slice memory.current is at or below 25 GB.
set -uo pipefail
cd "$(dirname "$0")/.."
python -c "import bear,sys; sys.exit(0 if bear.__version__=='0.4.2' else 'BEAR 0.4.2 required')" || exit 1
export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-9d085b49c004cb03e2bede9055fdc3810cf260c0}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TIST_FP16_BACKENDS=qwen3-0.6b TIST_MAX_BATCH=8
PY=$(command -v python)
TC=$HOME/bin/tist-capped
LOCK=$HOME/tist-gpu.lock
CG=/sys/fs/cgroup$(systemctl --user show tist.slice -p ControlGroup --value)
SLICE_MAX=$((25 * 1024 * 1024 * 1024))

slice_wait() {
  local cur
  while :; do
    cur=$(cat "$CG/memory.current")
    echo "### tist.slice memory.current $((cur / 1024 / 1024)) MiB $(date -u +%FT%TZ)"
    (( cur <= SLICE_MAX )) && return 0
    sleep 60
  done
}

gpu_step() {  # name cap_gib script args...
  local name=$1 cap=$2 rc=75 try
  shift 2
  for (( try = 1; try <= ${TIST_GATE_TRIES:-90}; try++ )); do
    slice_wait
    echo "=== $name: try $try $(date -u +%FT%TZ)"
    flock "$LOCK" env -u CUDA_VISIBLE_DEVICES TIST_REQUIRE_CUDA=1 TIST_GPU_CAP_GIB="$cap" OMP_NUM_THREADS=4 \
      bash evals/gpu_guard.sh "$cap" "$TC" --mem 12G -- "$PY" "$@"
    rc=$?
    (( rc == 75 )) || break
    sleep 120
  done
  echo "=== $name exit $rc $(date -u +%FT%TZ)"
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
  gpu_step qwen06_tagnoise 6 evals/eval_tag_noise.py --phase embed --backends qwen3-0.6b || return
  gpu_step qwen06_leakage 6 evals/eval_leakage_threat.py --phase embed --backends qwen3-0.6b || return
  gpu_step qwen4b_leakage 12 evals/eval_leakage_threat.py --phase embed --backends qwen3-4b
}

run() {
  cpu_step tagnoise_qwen06 evals/eval_tag_noise.py --phase run --backends qwen3-0.6b --workers 8 \
    --output results/tag_noise_qwen3-0.6b.json \
    --log-file results/tag_noise_qwen3-0.6b_output.txt || return
  cpu_step leakage_qwen evals/eval_leakage_threat.py --phase run --backends qwen3-0.6b qwen3-4b \
    --output results/leakage_threat_qwen.json \
    --log-file results/leakage_threat_qwen_output.txt
}

case ${1:-all} in
  embed) embed ;;
  run)   run ;;
  all)   embed && run ;;
  *)     echo "usage: bash evals/run_qwen_gpu.sh [embed|run|all]" >&2; exit 2 ;;
esac
