#!/usr/bin/env bash
# gpu_guard.sh CAP_GIB command...
#
# Start gate and card watchdog for one GPU step of run_qwen_gpu.sh. Run it
# under `flock ~/tist-gpu.lock`, so no other lock holder allocates meanwhile.
#
# Gate (exit 75, "not now", when any check fails):
#   1. Windows nvidia-smi shows at most TIST_WIN_GPU_MAX_MIB in use (67,000).
#   2. WP0's Qwen3-4B lane (service wp0-gpuq4b042) and its e2e rerun
#      (service wp0-e2erun) are not active.
#   3. Ollama (TIST_OLLAMA_ROOT, WP0's default) has no model loaded. An
#      Ollama that does not answer counts as a failure, since a loaded model
#      cannot be ruled out.
#   4. Free VRAM (WSL nvidia-smi) exceeds CAP_GIB by 1 GiB, for the CUDA
#      context outside the allocator cap. The step itself caps PyTorch's
#      allocator at CAP_GIB (TIST_GPU_CAP_GIB, tistr2_common.cap_cuda_memory).
# Watchdog: every 15 s, Windows nvidia-smi above TIST_WIN_GPU_STOP_MIB
# (80,000) stops the step's process group, exit 78. Only the recorded PID's
# group is signalled.
set -u
cap=$1; shift
start_max=${TIST_WIN_GPU_MAX_MIB:-67000}
stop_max=${TIST_WIN_GPU_STOP_MIB:-80000}
ollama=${TIST_OLLAMA_ROOT:-http://192.168.1.175:11434}
smi=/mnt/c/Windows/System32/nvidia-smi.exe
win_used() { "$smi" --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' \r'; }

used=$(win_used)
if ! [[ $used =~ ^[0-9]+$ ]]; then
  echo "### gpu guard: Windows nvidia-smi gave no reading, not started"; exit 75
fi
if (( used > start_max )); then
  echo "### gpu guard: card at ${used} MiB (start limit ${start_max}), not started"; exit 75
fi
for unit in wp0-gpuq4b042 wp0-e2erun; do
  if systemctl --user is-active -q "$unit" 2>/dev/null; then
    echo "### gpu guard: ${unit} is active, not started"; exit 75
  fi
done
if ! ps_json=$(curl -s -m 5 "$ollama/api/ps"); then
  echo "### gpu guard: Ollama at ${ollama} did not answer, not started"; exit 75
fi
if ! python3 -c 'import json, sys; sys.exit(1 if json.load(sys.stdin).get("models") else 0)' \
     <<<"$ps_json" 2>/dev/null; then
  echo "### gpu guard: Ollama has a model loaded (or answered oddly), not started"; exit 75
fi
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')
if ! [[ $free =~ ^[0-9]+$ ]] || awk -v f="$free" -v c="$cap" 'BEGIN { exit !(f / 1024 < c + 1.0) }'; then
  echo "### gpu guard: free ${free:-?} MiB is under the ${cap} GiB cap + 1 GiB, not started"; exit 75
fi
echo "### gpu guard: card ${used} MiB (start ${start_max}, stop ${stop_max}), free ${free} MiB, cap ${cap} GiB, $(date -u +%FT%TZ)"

setsid "$@" &
pid=$!
peak=$used
tick=0
while kill -0 "$pid" 2>/dev/null; do
  sleep 5
  tick=$((tick + 1))
  (( tick % 3 == 0 )) || continue
  used=$(win_used)
  [[ $used =~ ^[0-9]+$ ]] || continue
  (( used > peak )) && peak=$used
  if (( used > stop_max )); then
    echo "### gpu guard: card at ${used} MiB, over the ${stop_max} MiB stop limit, stopping the step"
    kill -TERM -- "-$pid" 2>/dev/null; sleep 10; kill -KILL -- "-$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    echo "### gpu guard: card peak ${peak} MiB"
    exit 78
  fi
done
wait "$pid"; rc=$?
echo "### gpu guard: card peak ${peak} MiB (stop limit ${stop_max}), exit ${rc}"
exit $rc
