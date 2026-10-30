#!/usr/bin/env bash
# TIST round 2: WP2, WP5 and WP6 deterministic baselines and stress tests.
#
# Run from the repo root inside WSL with the evaluation venv active and BEAR
# 0.4.0 (bear-dev 10730c8) installed:
#
#   source ~/.venvs/tist-evals/bin/activate
#   bash evals/run_wp256.sh embed      # store every vector the runs need
#   bash evals/run_wp256.sh run        # retrieval and statistics, CPU only
#   bash evals/run_wp256.sh v041       # BEAR 0.4.1 checks: BM25 results, WP1 invariants
#
# Every Python step runs in a systemd scope capped at 24 GB with no swap
# (CAP below), with at most 8 workers. A process over the cap is killed on its
# own instead of taking WSL down.
#
# The embed step is the only one that loads an embedding model or calls the
# Nemotron service (port 8360). Local models run on the CPU by default
# (EMBED_ON_GPU=1 puts them on the GPU, under the lock). The Nemotron calls
# always take ~/tist-gpu.lock, since the service shares the card. Everything
# after it reads stored vectors (TIST_EMB_CACHE, default
# ~/.cache/tist-r2-embeddings) with the GPU hidden. Result files are never
# overwritten: each script refuses an existing output.
set -euo pipefail
export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-10730c8ae682f972b731b89789f0f7b97a521523}
LOCK=${TIST_GPU_LOCK:-$HOME/tist-gpu.lock}
WORKERS=${WORKERS:-8}
LOCAL="hash bge qwen3-0.6b"
CAP="systemd-run --user --scope --slice=tist.slice -p MemoryMax=24G -p MemorySwapMax=0"
python() { $CAP "$(command -v python)" "$@"; }

command python -c "import bear,sys; sys.exit(0 if bear.__version__ in ('0.4.0','0.4.1') else 'BEAR 0.4.0 or 0.4.1 required, found '+bear.__version__)"

embed_local() {
  python evals/eval_mandatory_coverage.py --phase embed --backends hash bge bge-m3 qwen3-0.6b qwen3-4b
  python evals/eval_tag_noise.py --phase embed --backends $LOCAL
  python evals/eval_leakage_threat.py --phase embed --backends $LOCAL bge-m3 qwen3-4b
}

case "${1:-}" in
  embed)
    if [ "${EMBED_ON_GPU:-0}" = 1 ]; then
      flock "$LOCK" $CAP bash -c "$(declare -f embed_local); LOCAL='$LOCAL'; embed_local"
    else
      CUDA_VISIBLE_DEVICES= embed_local
    fi
    flock "$LOCK" $CAP env CUDA_VISIBLE_DEVICES= bash -c '
      set -euo pipefail
      python evals/eval_mandatory_coverage.py --phase embed --backends nemotron
      python evals/eval_tag_noise.py --phase embed --backends nemotron
      python evals/eval_leakage_threat.py --phase embed --backends nemotron
    '
    ;;
  run)
    export CUDA_VISIBLE_DEVICES=
    python evals/eval_mandatory_coverage.py --phase run
    python evals/eval_tag_noise.py --phase run --workers "$WORKERS" --backends bm25 hash bge
    python evals/eval_tag_noise.py --phase run --workers "$WORKERS" --backends nemotron \
        --output results/tag_noise_nemotron.json --log-file results/tag_noise_nemotron_output.txt
    python evals/eval_tag_noise.py --phase run --workers "$WORKERS" --backends qwen3-0.6b \
        --output results/tag_noise_qwen3.json --log-file results/tag_noise_qwen3_output.txt
    python evals/eval_leakage_threat.py --phase run
    python evals/eval_query_giveaways.py
    python evals/eval_cpa_maintained.py
    # LlamaIndex arms embed with BGE on the CPU. The Nemotron arms call the
    # service, so they take the lock.
    for c in petsim toolbench; do
      python evals/eval_metadata_filter_baseline.py --corpus $c --encoders bge \
          --output results/metadata_filter_baseline_${c}_bge.json \
          --log-file results/metadata_filter_baseline_${c}_bge_output.txt
      flock "$LOCK" $CAP "$(command -v python)" evals/eval_metadata_filter_baseline.py --corpus $c --encoders nemotron \
          --output results/metadata_filter_baseline_${c}_nemotron.json \
          --log-file results/metadata_filter_baseline_${c}_nemotron_output.txt
    done
    ;;
  v041)
    # BEAR 0.4.1 (v0.4.1 = fa87fc5). No model is loaded.
    export BEAR_SOURCE_SHA=fa87fc554fd394ce52b09ffa8121d36fc3758f28 CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1
    python evals/check_bm25_v041.py --workers "$WORKERS"
    python evals/eval_invariants.py --workers "$WORKERS"         --output results/invariants_v041.json         --counterexamples results/invariants_v041_counterexamples.json         --log-file results/invariants_v041_output.txt
    ;;
  *)
    echo "usage: bash evals/run_wp256.sh {embed|run|v041}" >&2
    exit 2
    ;;
esac
