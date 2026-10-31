#!/usr/bin/env bash
# 15_cpu_invariants_baselines.sh: WP1, the CPU part of WP5, the BM25 and BGE-M3
# parts of WP6, and the CPU embedding stores that 40_ reads. BEAR 0.4.2.
#
# Reproduces (full map in reproduce/MANIFEST.md):
#   tab:invariants and the nesting rate (evals/run_wp256.sh v042: eval_invariants.py
#     on 2,000 random corpora, the pool-sensitivity run, repro_bm25_admission_gap.py)
#   the budget-binding paragraph (run_wp256.sh v042 for BM25 and hash, v042-bge for BGE)
#   the BM25 cells of tab:robustness and the mandatory-coverage test (run_wp256.sh
#     v042-bm25: check_bm25_v042.py as released and under each restore switch)
#   the BGE-M3 row of the leakage panel of tab:robustness (run_wp256.sh v042-bgem3)
#   tab:baselines BGE rows and the maintained-CPA paragraph (evals/run_v042_wp5.sh
#     bge_petsim bge_toolbench cpa)
#   the CPU-filled embedding stores for WP2 and WP6 (hash, BGE, BGE-M3, and Qwen3
#     for the mandatory-coverage corpus), the same commands as run_wp256.sh embed
#     without its Qwen3-0.6B tag-noise and leakage part, which 20_ fills in fp16 on
#     the GPU as the reported rows were made, and without its Nemotron part (30_).
# Prerequisites: 00_setup.sh. The wsl-keepalive task is Running. No server is used.
# Resources: CPU only, CUDA hidden. Steps at 8G to 24G inside tist.slice, one at a time.
# Time: about 4 to 6 hours.
# Outputs: the clone $REPRO_OUT/clones/artifacts-wp256/results/ (new files only, the
#   committed copies are moved to its .repro_aside/), the stores in $REPRO_EMB_CACHE.
#   70_assemble.sh copies the new result files to $REPRO_OUT/assembled/results/.
#
# Usage:
#   bash reproduce/15_cpu_invariants_baselines.sh [--dry-run] [--wait] [--only "STEP ..."]
#   steps: wp256-v042 wp256-v042-bge wp256-v042-bm25 wp256-v042-bgem3 fill-cpu-stores wp5-bge-cpa
# Without --dry-run it starts the user service tist-repro-15 and returns.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/wp256.sh"
repro_parse_args "$@"

STEPS="wp256-v042 wp256-v042-bge wp256-v042-bm25 wp256-v042-bgem3 fill-cpu-stores wp5-bge-cpa"
set -- "${ARGS_REST[@]}"
while [ $# -gt 0 ]; do
  case $1 in
    --only) STEPS=$2; shift ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done

preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_clone "$WP256_CLONE"
  check_hf_models BAAI/bge-base-en-v1.5 BAAI/bge-m3 Qwen/Qwen3-Embedding-0.6B Qwen/Qwen3-Embedding-4B
}
maybe_launch tist-repro-15
repro_begin
say "preflight"
[ "$DRY_RUN" = 1 ] || preflight_launch
export CUDA_VISIBLE_DEVICES=
say "embedding stores: $TIST_EMB_CACHE"
say "steps, in order: $STEPS"

R="bash evals/run_wp256.sh"
for s in $STEPS; do
  hr
  case $s in
    wp256-v042)       wp256_step "$s" -- $R v042 ;;
    wp256-v042-bge)   wp256_step "$s" -- $R v042-bge ;;
    wp256-v042-bm25)  wp256_step "$s" -- $R v042-bm25 ;;
    wp256-v042-bgem3) wp256_step "$s" -- $R v042-bgem3 ;;
    fill-cpu-stores)
      # run_wp256.sh embed, CPU part: same scripts and backends, minus Qwen3-0.6B
      # for tag noise and leakage (20_ fills those stores in fp16 on the GPU).
      slice_wait
      rstep fill-mandatory-coverage -C "$WP256_CLONE" -- capped 24G -- python evals/eval_mandatory_coverage.py \
        --phase embed --backends hash bge bge-m3 qwen3-0.6b qwen3-4b
      rstep fill-tag-noise -C "$WP256_CLONE" -- capped 24G -- python evals/eval_tag_noise.py \
        --phase embed --backends hash bge
      rstep fill-leakage -C "$WP256_CLONE" -- capped 24G -- python evals/eval_leakage_threat.py \
        --phase embed --backends hash bge
      ;;
    wp5-bge-cpa) wp256_step "$s" -- bash evals/run_v042_wp5.sh bge_petsim bge_toolbench cpa ;;
    *) die "unknown step $s" ;;
  esac
done

REPRO_OK_NOTE="steps finished: $STEPS"
