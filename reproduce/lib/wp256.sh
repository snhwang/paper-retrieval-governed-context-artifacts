# reproduce/lib/wp256.sh: running the WP1, WP2, WP5 and WP6 scripts in their clone.
# Source it after common.sh.
#
# Those scripts write fixed names under results/ and refuse to overwrite a file
# that exists. A fresh clone holds the committed copies, so before a step the
# kit moves the step's committed outputs to <clone>/.repro_aside/ (in the clone
# only, this checkout is never touched). Only files that git tracks and that
# are unmodified are moved. A file a step of yours wrote is untracked, so a
# rerun of a finished step still refuses, and the step markers skip it.

# The runners write to results/ of the clone unless V042_OUT or QWEN_OUT point
# elsewhere. The kit keeps them on results/, so that every later step (the gate
# check reads the Qwen sweep from results/) reads your files.
unset V042_OUT QWEN_OUT
export TIST_CAPPED=$TC

# The outputs of each step, as globs relative to the clone root.
wp256_outputs() {
  case $1 in
    wp256-v042) echo "results/invariants_v042.json results/invariants_v042_counterexamples.json
      results/invariants_v042_output.txt results/invariants_v042_pool_sensitivity*.json
      results/invariants_v042_pool_sensitivity_output.txt results/budget_binding_v042.json
      results/budget_binding_v042_output.txt results/budget_binding_v042_vs_v040.json
      results/budget_binding_v042_vs_v040_output.txt" ;;
    wp256-v042-bge) echo "results/budget_binding_v042_bge.json results/budget_binding_v042_bge_output.txt
      results/budget_binding_v042_bge_vs_v040.json results/budget_binding_v042_bge_vs_v040_output.txt" ;;
    wp256-v042-bm25) echo "results/bm25_v042_check_*" ;;
    wp256-v042-bgem3) echo "results/leakage_threat_bge-m3.json results/leakage_threat_bge-m3_output.txt" ;;
    wp5-bge-cpa) echo "results/metadata_filter_baseline_petsim_bge_v042* results/metadata_filter_baseline_toolbench_bge_v042*
      results/cpa_maintained_v042*" ;;
    wp5-nemotron) echo "results/metadata_filter_baseline_petsim_nemotron_v042* results/metadata_filter_baseline_toolbench_nemotron_v042*" ;;
    # The committed .json.gz copies go too: the gate check and the giveaway strata
    # read a .gz when the .json is missing, and must read yours, never the committed one.
    qwen-run) echo "results/tag_noise_qwen3-0.6b.json* results/tag_noise_qwen3-0.6b_output.txt
      results/leakage_threat_qwen.json* results/leakage_threat_qwen_output.txt" ;;
    v042-rerun) echo "results/tag_noise_v042.json* results/tag_noise_v042_output.txt results/tag_noise_nemotron_v042*
      results/tag_noise_overrestriction_v042* results/leakage_threat_v042* results/query_giveaways_v042*
      results/mandatory_coverage_v042*" ;;
    qwen-giveaways) echo "results/query_giveaways_qwen3-0.6b.json* results/query_giveaways_qwen3-0.6b_output.txt" ;;
    *) echo "" ;;
  esac
}

# aside STEP: move the committed copies of STEP's outputs out of the way.
aside() {
  local step=$1 clone=$WP256_CLONE g f rel n=0
  shopt -s nullglob
  for g in $(wp256_outputs "$step"); do
    for f in "$clone"/$g; do
      rel=${f#"$clone"/}
      git -C "$clone" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1 || continue
      git -C "$clone" diff --quiet -- "$rel" || continue
      if [ "$DRY_RUN" = 1 ]; then
        echo "+ mv $rel .repro_aside/$rel   (committed copy, in the clone)"
      else
        mkdir -p "$clone/.repro_aside/$(dirname "$rel")"
        mv "$f" "$clone/.repro_aside/$rel"
      fi
      n=$((n + 1))
    done
  done
  shopt -u nullglob
  [ "$n" -gt 0 ] && say "$step: moved $n committed output(s) to $clone/.repro_aside/"
  return 0
}

# wp256_step NAME -- CMD...: aside, then a resumable step in the clone.
wp256_step() {
  local name=$1
  shift
  [ "${1:-}" = "--" ] && shift
  if step_done "$name"; then
    say "skip $name (done $(cat "$(state_dir)/$name.done"). Remove $(state_dir)/$name.done to rerun it"
    return 0
  fi
  aside "$name"
  slice_wait
  rstep "$name" -C "$WP256_CLONE" -- "$@"
}
