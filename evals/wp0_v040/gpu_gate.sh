#!/usr/bin/env bash
# gpu_gate.sh NEED_GIB command...
#
# Run under `flock ~/tist-gpu.lock`, so no other lock holder allocates while
# this runs. Reads free VRAM, caps PyTorch's CUDA allocator at
# min(13 GiB, free - 1 GiB) through WP0_GPU_CAP_GIB (sitecustomize), and
# starts the command only if that cap is at least NEED_GIB. The 1 GiB margin
# covers the CUDA context, which sits outside the allocator cap. Under WSL an
# allocation past physical VRAM spills to host memory instead of failing, so
# the cap is what turns an overrun into an error. Exit 75 means "not enough
# free VRAM now".
need=$1; shift
free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' ')
cap=$(awk -v f="$free_mib" 'BEGIN { c = f / 1024 - 1.0; if (c > 13) c = 13; printf "%.2f", c }')
if awk -v c="$cap" -v n="$need" 'BEGIN { exit !(c < n) }'; then
  echo "### gpu gate: free ${free_mib} MiB, cap ${cap} GiB < need ${need} GiB, not started"
  exit 75
fi
echo "### gpu gate: free ${free_mib} MiB, allocator cap ${cap} GiB (need ${need} GiB)"
export WP0_GPU_CAP_GIB=$cap
exec "$@"
