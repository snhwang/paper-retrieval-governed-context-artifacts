#!/usr/bin/env bash
# gpu_gate.sh NEED_GIB command...
#
# Run under `flock ~/tist-gpu.lock`, so no other lock holder allocates while
# this runs. Exit 75 means "not now" (the runner waits or marks the step
# blocked).
#
# 1. If WP0_WIN_GPU_MAX_MIB is set, Windows' nvidia-smi.exe must report at
#    most that much in use (model-server and the coordinator, 2026-10-30:
#    67,000 MiB for Qwen3-4B). The stop limit (WP0_WIN_GPU_STOP_MIB, 80,000)
#    is enforced while the step runs, by mem_guard.sh.
# 2. The e2e rerun must not be running and its Ollama model (mistral-nemo-32k)
#    must not be loaded, so the two GPU jobs never overlap.
# 3. The PyTorch allocator cap (WP0_GPU_CAP_GIB, enforced by sitecustomize
#    through torch.cuda.set_per_process_memory_fraction) is WP0_GPU_CAP_FIXED
#    when set (Qwen3-4B: about 12 GB), else min(13 GiB, free - 1 GiB). Free
#    VRAM must exceed the cap by 1 GiB for the CUDA context, which sits
#    outside the allocator cap, and the cap must be at least NEED_GIB. Under
#    WSL an allocation past physical VRAM spills to host memory instead of
#    failing, so the cap is what turns an overrun into an error.
need=$1; shift
if [ -n "${WP0_WIN_GPU_MAX_MIB:-}" ]; then
  win_used=$(/mnt/c/Windows/System32/nvidia-smi.exe --query-gpu=memory.used --format=csv,noheader,nounits \
             | head -1 | tr -d ' \r')
  if [ -z "$win_used" ] || (( win_used > WP0_WIN_GPU_MAX_MIB )); then
    echo "### gpu gate: Windows nvidia-smi shows ${win_used:-?} MiB used (start limit ${WP0_WIN_GPU_MAX_MIB}), not started"
    exit 75
  fi
  echo "### gpu gate: Windows nvidia-smi shows ${win_used} MiB used (start limit ${WP0_WIN_GPU_MAX_MIB}, stop limit ${WP0_WIN_GPU_STOP_MIB:-none})"
fi
if systemctl --user is-active -q wp0-e2erun 2>/dev/null; then
  echo "### gpu gate: the e2e rerun (wp0-e2erun) is active, not started"
  exit 75
fi
# 127.0.0.1: WSL uses mirrored networking. A check that cannot reach Ollama refuses.
if ! ollama_ps=$(curl -sf -m 5 "${WP0_OLLAMA_ROOT:-http://127.0.0.1:11434}/api/ps"); then
  echo "### gpu gate: cannot reach Ollama /api/ps, not started"
  exit 75
fi
if grep -q '"name":"mistral-nemo-32k' <<<"$ollama_ps"; then
  echo "### gpu gate: the e2e executor (mistral-nemo-32k) is still loaded in Ollama, not started"
  exit 75
fi
free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')
if [ -n "${WP0_GPU_CAP_FIXED:-}" ]; then
  cap=$WP0_GPU_CAP_FIXED
  if awk -v f="$free_mib" -v c="$cap" 'BEGIN { exit !(f / 1024 < c + 1.0) }'; then
    echo "### gpu gate: free ${free_mib} MiB is under the fixed cap ${cap} GiB + 1 GiB, not started"
    exit 75
  fi
else
  cap=$(awk -v f="$free_mib" 'BEGIN { c = f / 1024 - 1.0; if (c > 13) c = 13; printf "%.2f", c }')
fi
if awk -v c="$cap" -v n="$need" 'BEGIN { exit !(c < n) }'; then
  echo "### gpu gate: free ${free_mib} MiB, cap ${cap} GiB < need ${need} GiB, not started"
  exit 75
fi
echo "### gpu gate: free ${free_mib} MiB, allocator cap ${cap} GiB (need ${need} GiB)"
export WP0_GPU_CAP_GIB=$cap
exec "$@"
