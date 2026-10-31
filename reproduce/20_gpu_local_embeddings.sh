#!/usr/bin/env bash
# 20_gpu_local_embeddings.sh: the results that load a local model on the GPU.
#
# Reproduces (full map in reproduce/MANIFEST.md):
#   the Qwen3-4B rows of tab:toolbench-results, tab:metatool-results and
#     tab:metatool-tags-results, the Qwen3-4B top-5 lists of Table 10 and its WP4
#     lists (tab:tokens-recall). WP0 lanes of evals/wp0_v040/run_wp0_v040.sh, as run
#     in October:
#       gpuq4b042     encode batch 8. The ToolBench rows run out of memory inside the
#                     11.2 GiB allocator cap and are skipped (exit 3), as they were
#                     then. Its +Tags and +QueryTags rows and the MetaTool+Tags WP4
#                     lists are the reported ones (batch 8).
#       gpuq4b042fix  encode batch 2: the skipped rows, the e2e lists and the
#                     ToolBench WP4 lists
#       gpuq4b042gov  encode batch 2: base MetaTool governed, so the base pair
#                     shares one batch size
#   the Qwen3-4B mand-only rows of the four benchmarks (Section 5.4), which no
#     October lane ran: one step, tb_qwen4b_mand, made like a lane step with the
#     settings of gpuq4b042fix (bf16, batch 2, 11.2 GiB cap, same gates)
#   the GPU embedding stores of WP6: Qwen3-0.6B (tag noise, leakage) and Qwen3-4B
#     (leakage), fp16, by evals/run_qwen_gpu.sh embed (at most 8 texts per batch
#     for Qwen3-0.6B, exactly 2 for Qwen3-4B). 40_ runs the CPU part.
# Prerequisites: 00_setup.sh. The model-server session agreed to the window. The
#   card shows 67,000 MiB or less (Windows nvidia-smi), Ollama holds no model, no
#   WP7 grid and no other GPU job of the kit is running, wsl-keepalive is Running.
# Resources: the local GPU, bf16 (WP0) or fp16 (WP6). Allocator caps 11.2 GiB (WP0)
#   and 6 or 12 GiB (WP6). Each step starts only at 67,000 MiB or less and is
#   stopped above 80,000 MiB (gpu_gate.sh and mem_guard.sh, gpu_guard.sh). Host
#   memory 12G per step. One process at a time under ~/tist-gpu.lock.
# Time: about 3 hours of card time (WP0 lanes about 2 h, mand-only rows about
#   30 min, WP6 about 20 min).
# Outputs: $REPRO_OUT/wp0/ (stage/v042/tb_qwen4b*, lists in the artifacts-gpu clone),
#   the stores in $REPRO_EMB_CACHE.
#
# Usage:
#   bash reproduce/20_gpu_local_embeddings.sh [--dry-run] [--wait] [--only "wp0 mandonly wp6"]
# Without --dry-run it starts the user service tist-repro-20 and returns.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/wp0.sh"
source "$(dirname "$0")/lib/wp256.sh"
repro_parse_args "$@"

PARTS="wp0 mandonly wp6"
set -- "${ARGS_REST[@]}"
while [ $# -gt 0 ]; do
  case $1 in
    --only) PARTS=$2; shift ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done

preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_bear0110
  check_hf_models Qwen/Qwen3-Embedding-4B Qwen/Qwen3-Embedding-0.6B
  check_clone "$WP0_DIR/artifacts-gpu"
  check_clone "$WP256_CLONE"
  check_no_gpu_jobs
  check_card_start
  check_ollama_idle
}
maybe_launch tist-repro-20
repro_begin
say "preflight"
if [ "$DRY_RUN" = 0 ]; then
  preflight_launch
  python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name ollama --url "$REPRO_OLLAMA_ROOT" >/dev/null 2>&1
else
  check_card_start
  check_ollama_idle
fi

for part in $PARTS; do
  hr
  case $part in
    wp0)
      run_lane gpuq4b042
      # The batch-8 lane must not have finished a step the reported run took at
      # batch 2. If it did (no out-of-memory this time), clear its marker so
      # gpuq4b042fix redoes it at batch 2, and say so in the run record.
      for s in e2e_q4b_v042 e2e_q4b_v0110 wp4_tb_q4b; do
        if [ "$DRY_RUN" = 0 ] && [ -f "$WP0_DIR/logs/$s.done" ] && ! step_done "lane_gpuq4b042fix"; then
          record_note "step $s finished at encode batch 8 in gpuq4b042. The reported run made it at batch 2, so its marker is removed and gpuq4b042fix reruns it at batch 2."
          rm -f "$WP0_DIR/logs/$s.done"
        fi
      done
      run_lane gpuq4b042fix
      run_lane gpuq4b042gov
      ;;
    mandonly)
      # Section 5.4 says the mand-only condition retrieves nothing on six
      # backends. October ran five. This adds Qwen3-4B on the GPU.
      wp0_gpu_tb_step tb_qwen4b_mand all "BEAR+Qwen3-4B (mand-only)"
      ;;
    wp6)
      # The ToolBench Qwen3-0.6B store is shared by tag noise and leakage.
      rstep qwen-gpu-embed -C "$WP256_CLONE" -- bash evals/run_qwen_gpu.sh embed
      ;;
    *) die "unknown part $part" ;;
  esac
done

if [ "$DRY_RUN" = 0 ]; then
  say "card after the run: $(card_mib) MiB"
fi
REPRO_OK_NOTE="parts finished: $PARTS. Tell the model-server session the GPU is free"
