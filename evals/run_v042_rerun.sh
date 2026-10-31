#!/usr/bin/env bash
# Rerun on BEAR 0.4.2 (public tag v0.4.2, 0d0718a) every WP2 and WP6 result
# that ran on 0.4.0, from cached vectors only.
#
#   bash evals/run_v042_rerun.sh [step...]    # default: every step, in order
#   steps: tagnoise tagnoise_nemotron gatecheck leakage giveaways mandatory
#   V042_OUT=results/repro bash evals/run_v042_rerun.sh   # write elsewhere
#
# Run by hand from the repo root inside WSL, with the evaluation venv active
# (BEAR 0.4.2 installed). The 2026-10-31 outputs in results/*_v042* came from
# an agent validation run of this script. Outputs are never overwritten, so a
# second run needs V042_OUT set to a new directory (created if missing).
#
# CPU only: CUDA hidden, no model is loaded. Dense backends read the stores in
# ~/.cache/tist-r2-embeddings (TIST_EMB_CACHE) through CachedEmbedder, which
# raises on a missing text, so no step embeds anything or calls the Nemotron
# service. One step at a time, each under ~/bin/tist-capped (16G at most),
# after tist.slice memory other than page cache is at or below 25 GB. A failed
# step stops the run.
#
# Not here: WP5 (evals/run_v042_wp5.sh), which embeds live.
set -uo pipefail
cd "$(dirname "$0")/.."
python -c "import bear,sys; sys.exit(0 if bear.__version__=='0.4.2' else 'BEAR 0.4.2 required')" || exit 1
export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-$(python evals/bear_sha.py)}  # the installed BEAR's commit
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PY=$(command -v python)
TC=${TIST_CAPPED:-$HOME/bin/tist-capped}
[ -x "$TC" ] || { echo "tist-capped not found at $TC (set TIST_CAPPED)"; exit 1; }
CG=/sys/fs/cgroup$(systemctl --user show tist.slice -p ControlGroup --value 2>/dev/null)
[ -r "$CG/memory.stat" ] || { echo "tist.slice not found (start it with tist-capped once)"; exit 1; }
SLICE_MAX=$((25 * 1024 * 1024 * 1024))
W=${WORKERS:-8}
OUT=${V042_OUT:-results}
mkdir -p "$OUT"
# The Qwen3-0.6B sweep, for the gate check's trace comparison: from QWEN_OUT
# when run_qwen_gpu.sh wrote elsewhere, else the committed one (gzipped).
QDIR=${QWEN_OUT:-results}
QWEN_TN=$QDIR/tag_noise_qwen3-0.6b.json
[ -e "$QWEN_TN" ] || QWEN_TN=$QDIR/tag_noise_qwen3-0.6b.json.gz
[ -e "$QWEN_TN" ] || echo "### note: no Qwen3-0.6B sweep in $QDIR, the gate check compares without it"

slice_wait() {  # memory the kernel cannot reclaim, not page cache (as run_qwen_gpu.sh)
  local cur file shmem used
  while :; do
    cur=$(cat "$CG/memory.current")
    file=$(awk '$1 == "file" {print $2}' "$CG/memory.stat")
    shmem=$(awk '$1 == "shmem" {print $2}' "$CG/memory.stat")
    used=$(( cur - file + shmem ))
    echo "### tist.slice without page cache $((used / 1024 / 1024)) MiB $(date -u +%FT%TZ)"
    (( used <= SLICE_MAX )) && return 0
    sleep 60
  done
}

step() {  # name mem script args...
  local name=$1 mem=$2 rc
  shift 2
  slice_wait
  echo "=== $name start $(date -u +%FT%TZ) (cap $mem)"
  "$TC" --mem "$mem" -- "$PY" "$@"
  rc=$?
  echo "=== $name exit $rc $(date -u +%FT%TZ)"
  return "$rc"
}

tagnoise() {
  step tagnoise 16G evals/eval_tag_noise.py --phase run --backends bm25 hash bge --workers "$W" \
    --output "$OUT/tag_noise_v042.json" --log-file "$OUT/tag_noise_v042_output.txt"
}
tagnoise_nemotron() {
  step tagnoise_nemotron 16G evals/eval_tag_noise.py --phase run --backends nemotron --workers "$W" \
    --output "$OUT/tag_noise_nemotron_v042.json" --log-file "$OUT/tag_noise_nemotron_v042_output.txt"
}
gatecheck() {
  step gatecheck 8G evals/eval_tag_noise.py --phase gatecheck \
    --output "$OUT/tag_noise_overrestriction_v042.json" \
    --compare "$OUT/tag_noise_v042.json" "$OUT/tag_noise_nemotron_v042.json" "$QWEN_TN"
}
leakage() {
  step leakage 12G evals/eval_leakage_threat.py --phase run --backends bm25 hash bge nemotron \
    --output "$OUT/leakage_threat_v042.json" --log-file "$OUT/leakage_threat_v042_output.txt"
}
giveaways() {
  step giveaways 8G evals/eval_query_giveaways.py \
    --tag-noise "$OUT/tag_noise_v042.json" "$OUT/tag_noise_nemotron_v042.json" \
    --output "$OUT/query_giveaways_v042.json" --log-file "$OUT/query_giveaways_v042_output.txt"
}
mandatory() {
  step mandatory 8G evals/eval_mandatory_coverage.py --phase run \
    --output "$OUT/mandatory_coverage_v042.json" --log-file "$OUT/mandatory_coverage_v042_output.txt"
}

echo "### run_v042_rerun.sh ${*:-all}, BEAR_SOURCE_SHA ${BEAR_SOURCE_SHA}, outputs in ${OUT}, $(date -u +%FT%TZ)"
steps=("$@")
(( ${#steps[@]} )) || steps=(tagnoise tagnoise_nemotron gatecheck leakage giveaways mandatory)
for s in "${steps[@]}"; do
  declare -F "$s" >/dev/null || { echo "unknown step $s"; exit 2; }
  "$s" || { echo "### stopped at $s"; exit 1; }
done
echo "### run_v042_rerun.sh done $(date -u +%FT%TZ)"
