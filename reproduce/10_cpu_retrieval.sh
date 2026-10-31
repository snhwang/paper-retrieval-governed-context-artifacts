#!/usr/bin/env bash
# 10_cpu_retrieval.sh: every retrieval result of WP0 on BEAR 0.4.2 that runs on the CPU.
#
# Reproduces (manuscript labels, full map in reproduce/MANIFEST.md):
#   tab:toolbench-results, tab:metatool-results, tab:metatool-tags-results
#     (BGE, BGE-M3, Qwen3-0.6B, BM25, hash. Qwen3-4B is in 20_, Nemotron in 30_)
#   tab:toolbench-inferred, tab:token-efficiency, tab:semantic-advantage,
#   tab:token-compare, tab:governance-ablation, tab:decomposed-ablation (with its
#   ITR row), tab:alpha-sweep, tab:retrieval, tab:tool-scaling, tab:token-savings,
#   tab:transfer, tab:reranker (and the LlamaIndex rows), the mand-only rows,
#   the Table 10 top-5 lists of BM25, hash, BGE, BGE-M3 and Qwen3-0.6B, the WP4
#   k=50 lists of the same backends, and the per-query mandatory tables.
# How: the lanes of evals/wp0_v040/run_wp0_v040.sh, in this order, each to its end:
#   lex042 (BM25 and hash, every table), dense042 (local models on the CPU),
#   manddense042 (Qwen3-4B decomposed, mandatory diagnostics), mandonly042
#   (mand-only rows), mand042 (lexical mandatory diagnostics).
#   --with-controls adds the BEAR 0.1.10 attribution lanes behind the Summary of
#   Differences: attrpet042, attrtb042, pair042, e2eattr042, fallback0110.
#   The lanes run 0.1.10 control steps too (they need ~/tist-evals/bear-v0110).
# Prerequisites: 00_setup.sh. The Nemotron server answers /health (the first
#   step, verify, asks it to name itself. No embedding request is sent here).
#   The wsl-keepalive task is Running.
# Resources: CPU only, CUDA hidden. Lexical steps at 8G, dense steps at 20G
#   (batch 4, 12 threads), one step at a time, all inside tist.slice.
# Time: about 14 hours (lex042 0.5 h, dense042 10 to 11 h, the rest 2 h).
#   --with-controls adds about 3 hours.
# Outputs: $REPRO_OUT/wp0/ (stage/v042/<step>/, logs/, the clones' results/wp0/).
#   70_assemble.sh gathers them into $REPRO_OUT/assembled/results/v042/.
#
# Usage:
#   bash reproduce/10_cpu_retrieval.sh [--dry-run] [--wait] [--with-controls] [--lanes "lex042 dense042 ..."]
# Without --dry-run it starts the user service tist-repro-10 and returns. The
# service runs this script with --foreground. Run it again to continue after a
# stop: finished lanes and steps are skipped.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/wp0.sh"
repro_parse_args "$@"

LANES="lex042 dense042 manddense042 mandonly042 mand042"
CONTROLS="attrpet042 attrtb042 pair042 e2eattr042 fallback0110"
set -- "${ARGS_REST[@]}"
while [ $# -gt 0 ]; do
  case $1 in
    --with-controls) LANES="$LANES $CONTROLS" ;;
    --lanes) LANES=$2; shift ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done

preflight_launch() {  # quick checks, in the terminal and again in the service
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_bear0110
  check_hf_models $HF_MODELS_RETRIEVAL
}
maybe_launch tist-repro-10
repro_begin

say "preflight"
[ "$DRY_RUN" = 1 ] || preflight_launch
check_nemotron
for lane in $LANES; do
  lane_clone "$lane" >/dev/null || die "unknown lane $lane"
  [ "$DRY_RUN" = 1 ] || check_clone "$WP0_DIR/$(lane_clone "$lane")"
done
say "lanes, in order: $LANES"

for lane in $LANES; do
  hr
  run_lane "$lane"
done

REPRO_OK_NOTE="lanes finished: $LANES. Next: 15_cpu_invariants_baselines.sh (CPU) or the GPU and server scripts"
