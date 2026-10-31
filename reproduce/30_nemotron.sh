#!/usr/bin/env bash
# 30_nemotron.sh: every result that embeds through the Nemotron server on port 8360.
#
# Reproduces (full map in reproduce/MANIFEST.md):
#   the Nemotron rows of tab:toolbench-results, tab:metatool-results and
#     tab:metatool-tags-results, its Table 10 lists and WP4 lists (WP0 lane nemo042),
#   the threshold diagnosis in the MetaTool text (evals/wp0_v040/diag_nemotron_threshold.py,
#     from the response cache of nemo042, so it sends no new request)
#   the Nemotron embedding stores of WP2 and WP6 (eval_mandatory_coverage.py,
#     eval_tag_noise.py and eval_leakage_threat.py --phase embed --backends nemotron,
#     the Nemotron part of run_wp256.sh embed). 40_ runs the analysis from them.
#   the Nemotron rows of tab:baselines (WP5a): eval_metadata_filter_baseline.py
#     --encoders nemotron, live, for both corpora, on BEAR 0.4.2. The stores hold no
#     vectors for these texts, so the cached route of run_v042_wp5.sh cannot run them.
# Prerequisites: 00_setup.sh. The Nemotron server (nvidia/llama-nemotron-embed-vl-1b-v2)
#   answers on 8360 and the model-server session agreed to the window. No WP7 grid
#   and no other GPU job of the kit runs. wsl-keepalive is Running.
# Resources: port 8360 (batches of at most 16 texts in WP0, 64 in WP2/5/6). No local
#   CUDA. Host memory 8G to 16G per step. Every step holds ~/tist-gpu.lock.
# Time: about 2 to 3 hours (nemo042 about 1 h, stores and WP5 about 1 to 2 h).
# Outputs: $REPRO_OUT/wp0/ (stage/v042/tb_nemotron, diag/, nemocache/), the stores
#   in $REPRO_EMB_CACHE, new files in the clone artifacts-wp256/results/.
#
# Usage:
#   bash reproduce/30_nemotron.sh [--dry-run] [--wait] [--only "wp0 diag stores wp5"]
# Without --dry-run it starts the user service tist-repro-30 and returns.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/wp0.sh"
source "$(dirname "$0")/lib/wp256.sh"
repro_parse_args "$@"

PARTS="wp0 diag stores wp5"
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
  check_clone "$WP0_DIR/artifacts-nemo"
  check_clone "$WP256_CLONE"
  check_no_gpu_jobs
}
maybe_launch tist-repro-30
repro_begin
say "preflight"
[ "$DRY_RUN" = 1 ] || preflight_launch
check_nemotron
export CUDA_VISIBLE_DEVICES=

for part in $PARTS; do
  hr
  case $part in
    wp0) run_lane nemo042 ;;
    diag)
      need_cache=$WP0_DIR/nemocache/nemo.sqlite
      [ "$DRY_RUN" = 1 ] || [ -s "$need_cache" ] || die "no Nemotron response cache at $need_cache (run the wp0 part first)"
      [ "$DRY_RUN" = 1 ] || mkdir -p "$WP0_DIR/diag"
      rstep diag-nemotron-threshold -C "$WP0_DIR/artifacts-nemo" -- capped 4G -- env WP0_NEMO_CACHE="$need_cache" \
        PYTHONPATH=evals/wp0_v040/site "$REPRO_PY" evals/wp0_v040/diag_nemotron_threshold.py \
        --out "$WP0_DIR/diag/diag_nemotron_threshold.json"
      ;;
    stores)
      # The Nemotron block of run_wp256.sh embed, under the GPU lock as there.
      slice_wait
      for s in eval_mandatory_coverage eval_tag_noise eval_leakage_threat; do
        rstep "fill-$s" -C "$WP256_CLONE" -- flock "$GPU_LOCK" "$TC" --mem 16G -- python "evals/$s.py" \
          --phase embed --backends nemotron
      done
      ;;
    wp5)
      for c in petsim toolbench; do
        aside wp5-nemotron
        slice_wait
        rstep "wp5-nemotron-$c" -C "$WP256_CLONE" -- flock "$GPU_LOCK" "$TC" --mem 8G -- \
          python evals/eval_metadata_filter_baseline.py --corpus "$c" --encoders nemotron \
          --output "results/metadata_filter_baseline_${c}_nemotron_v042.json" \
          --log-file "results/metadata_filter_baseline_${c}_nemotron_v042_output.txt"
      done
      ;;
    *) die "unknown part $part" ;;
  esac
done

REPRO_OK_NOTE="parts finished: $PARTS"
