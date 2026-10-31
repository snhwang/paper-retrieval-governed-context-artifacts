#!/usr/bin/env bash
# TIST round 2: WP2, WP5 and WP6 deterministic baselines and stress tests.
#
# Run from the repo root inside WSL with the evaluation venv active. The
# embed and run modes first ran on BEAR 0.4.0 (bear-dev 10730c8), v041 on
# 0.4.1 and the v042 modes on the 0.4.2 candidate 9d085b4 (equal to the public
# v0.4.2 apart from line endings). Each mode records the installed BEAR's
# source commit (evals/bear_sha.py) unless BEAR_SOURCE_SHA is set.
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
# The installed BEAR's source commit (its export's BEAR_GIT_SHA), unless BEAR_SOURCE_SHA is set.
export BEAR_SOURCE_SHA=${BEAR_SOURCE_SHA:-$(command python "$(dirname "$0")/bear_sha.py")}
LOCK=${TIST_GPU_LOCK:-$HOME/tist-gpu.lock}
WORKERS=${WORKERS:-8}
LOCAL="hash bge qwen3-0.6b"
CAP="systemd-run --user --scope --slice=tist.slice -p MemoryMax=24G -p MemorySwapMax=0"
python() { $CAP "$(command -v python)" "$@"; }

command python -c "import bear,sys; sys.exit(0 if bear.__version__ in ('0.4.0','0.4.1','0.4.2') else 'BEAR 0.4.0 to 0.4.2 required, found '+bear.__version__)"

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
    # BEAR 0.4.1 checks (first run on v0.4.1 = fa87fc5). No model is loaded.
    export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1
    python evals/check_bm25_v041.py --workers "$WORKERS"
    python evals/eval_invariants.py --workers "$WORKERS"         --output results/invariants_v041.json         --counterexamples results/invariants_v041_counterexamples.json         --log-file results/invariants_v041_output.txt
    ;;
  v042)
    # BEAR 0.4.2 (first run on the candidate 9d085b4): WP1 invariants, the
    # release acceptance run. No model is loaded.
    export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1
    python evals/eval_invariants.py --workers "$WORKERS" \
        --output results/invariants_v042.json \
        --counterexamples results/invariants_v042_counterexamples.json \
        --log-file results/invariants_v042_output.txt
    command python evals/repro_bm25_admission_gap.py
    # Nesting above the pool size on the stub and BM25, paired against the
    # restore switches that move it.
    python evals/eval_invariants.py --configs main --skip-cross-process --workers "$WORKERS" \
        --sensitivity-configs main main_bm25 legacy_tie_order legacy_dropped_rows legacy_tie_order_bm25 \
        --output results/invariants_v042_pool_sensitivity.json \
        --counterexamples results/invariants_v042_pool_sensitivity_counterexamples.json \
        --log-file results/invariants_v042_pool_sensitivity_output.txt
    # Budget binding on BM25 and hash (bge is a model load, held), with the
    # switches that give the earlier search and backfill, and the paired
    # comparison with the 0.4.0 run.
    python evals/eval_budget_binding.py \
        --backends bm25 bm25:dropped_rows bm25:flat_backfill hash hash:flat_backfill \
        --output results/budget_binding_v042.json \
        --log-file results/budget_binding_v042_output.txt
    python evals/compare_budget_binding.py \
        --old results/budget_binding.json --new results/budget_binding_v042.json \
        --output results/budget_binding_v042_vs_v040.json \
        --log-file results/budget_binding_v042_vs_v040_output.txt
    ;;
  v042-bge)
    # BGE-base budget binding on 0.4.2, CPU only (a local model load, cleared
    # for CPU inside tist.slice). About 20 minutes at 8 threads, 3 GB.
    export CUDA_VISIBLE_DEVICES= \
        OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    CAP="$HOME/bin/tist-capped --mem 8G --"
    python evals/eval_budget_binding.py --backends bge \
        --output results/budget_binding_v042_bge.json \
        --log-file results/budget_binding_v042_bge_output.txt
    python evals/compare_budget_binding.py \
        --old results/budget_binding.json --new results/budget_binding_v042_bge.json \
        --output results/budget_binding_v042_bge_vs_v040.json \
        --log-file results/budget_binding_v042_bge_vs_v040_output.txt
    ;;
  v042-bm25)
    # The committed BM25 results (tag noise, WP2, leakage, giveaways) on 0.4.2,
    # as released and with each restore switch, then the attribution. No model
    # is loaded. About 15 minutes per run at 8 workers, 2 GB.
    export CUDA_VISIBLE_DEVICES= \
        OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
    CAP="$HOME/bin/tist-capped --mem 12G --"
    python evals/check_bm25_v042.py --workers "$WORKERS"
    python evals/check_bm25_v042.py --workers "$WORKERS" --switches flat_backfill
    python evals/check_bm25_v042.py --workers "$WORKERS" --switches dropped_rows
    python evals/check_bm25_v042.py --workers "$WORKERS" --switches tie_order
    python evals/check_bm25_v042.py --workers "$WORKERS" --switches flat_backfill tie_order
    python evals/check_bm25_v042.py --summarize
    ;;
  v042-bgem3)
    # BGE-M3 leakage on the CPU (cleared for CPU in tist.slice), float32. The
    # store fill took 38 minutes at 8 threads (15,700 CPU-s, 3.5 GB), the run
    # about a minute. The Qwen backends run on the GPU: evals/run_qwen_gpu.sh.
    export CUDA_VISIBLE_DEVICES= \
        OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    CAP="$HOME/bin/tist-capped --mem 8G --"
    python evals/eval_leakage_threat.py --phase embed --backends bge-m3
    python evals/eval_leakage_threat.py --phase run --backends bge-m3 \
        --output results/leakage_threat_bge-m3.json \
        --log-file results/leakage_threat_bge-m3_output.txt
    ;;
  *)
    echo "usage: bash evals/run_wp256.sh {embed|run|v041|v042|v042-bge|v042-bm25|v042-bgem3}" >&2
    exit 2
    ;;
esac
