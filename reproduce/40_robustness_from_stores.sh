#!/usr/bin/env bash
# 40_robustness_from_stores.sh: WP2 and WP6 analyses on BEAR 0.4.2, from stored vectors.
#
# Reproduces (full map in reproduce/MANIFEST.md):
#   tab:robustness: the tag-noise sweep with its crossovers (BM25, hash, BGE,
#     Nemotron, Qwen3-0.6B), over-restriction vs leakage (gatecheck), the leakage
#     and injection panel (BM25, hash, BGE, Nemotron, Qwen3-0.6B, Qwen3-4B. BGE-M3 is
#     15_), and the query-giveaway strata
#   the mandatory-coverage test: tab:decomposed-ablation bottom rows and its text
# How, in this order, in the clone artifacts-wp256:
#   1. evals/run_qwen_gpu.sh run: tag_noise_qwen3-0.6b.json, leakage_threat_qwen.json
#   2. evals/run_v042_rerun.sh: tagnoise, tagnoise_nemotron, gatecheck, leakage,
#      giveaways, mandatory (the *_v042.json files). gatecheck reads step 1's file.
#   3. eval_query_giveaways.py on the Qwen3-0.6B tag-noise file
# Every step reads the embedding stores and nothing else: CachedEmbedder raises on
# a missing text, so no step embeds anything or calls a server.
# Prerequisites: 15_ (CPU stores), 20_ (Qwen stores, part wp6) and 30_ (Nemotron
#   stores, part stores) finished. wsl-keepalive is Running.
# Resources: CPU only, CUDA hidden, 8G to 16G per step, at most 8 workers, each
#   step after tist.slice holds 25 GB or less other than page cache.
# Time: about 1 hour.
# Outputs: new files in $REPRO_OUT/clones/artifacts-wp256/results/. The two raw
#   tag-noise JSONs are large (about 350 MB and 115 MB).
#
# Usage:
#   bash reproduce/40_robustness_from_stores.sh [--dry-run] [--wait] [--only "qwen-run v042-rerun qwen-giveaways"]
# Without --dry-run it starts the user service tist-repro-40 and returns.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/wp256.sh"
repro_parse_args "$@"

STEPS="qwen-run v042-rerun qwen-giveaways"
set -- "${ARGS_REST[@]}"
while [ $# -gt 0 ]; do
  case $1 in
    --only) STEPS=$2; shift ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done

# The stores each step reads (names as tistr2_common.EmbeddingStore writes them).
STORES="petsim__hash petsim__bge petsim__bge-m3 petsim__qwen3-0.6b petsim__qwen3-4b petsim__nemotron
toolbench__hash toolbench__bge toolbench__nemotron toolbench__qwen3-0.6b toolbench__qwen3-4b
metatool_tags__hash metatool_tags__bge metatool_tags__nemotron metatool_tags__qwen3-0.6b"

preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_clone "$WP256_CLONE"
  local s missing=""
  for s in $STORES; do [ -s "$REPRO_EMB_CACHE/$s.npz" ] || missing+=" $s"; done
  [ -z "$missing" ] || die "stores missing in $REPRO_EMB_CACHE:$missing. Run 15_, 20_ (wp6) and 30_ (stores) first."
}
maybe_launch tist-repro-40
repro_begin
say "preflight"
[ "$DRY_RUN" = 1 ] || preflight_launch
export CUDA_VISIBLE_DEVICES=
say "embedding stores: $TIST_EMB_CACHE"

for s in $STEPS; do
  hr
  case $s in
    qwen-run) wp256_step "$s" -- bash evals/run_qwen_gpu.sh run ;;
    v042-rerun) wp256_step "$s" -- bash evals/run_v042_rerun.sh ;;
    qwen-giveaways)
      wp256_step "$s" -- capped 8G -- python evals/eval_query_giveaways.py \
        --tag-noise results/tag_noise_qwen3-0.6b.json \
        --output results/query_giveaways_qwen3-0.6b.json \
        --log-file results/query_giveaways_qwen3-0.6b_output.txt ;;
    *) die "unknown step $s" ;;
  esac
done

REPRO_OK_NOTE="steps finished: $STEPS"
