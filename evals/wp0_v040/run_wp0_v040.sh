#!/usr/bin/env bash
# WP0 rerun of every deterministic retrieval result on BEAR 0.4.0 (bear-dev
# 10730c8 = public v0.4.0 library code), plus the Nemotron backend, the
# end-to-end list comparison against BEAR 0.1.10, and the WP4 ranked lists.
#
# Runs in a clone of the artifacts repo, because many eval scripts write to
# fixed paths under results/ and those files hold the published numbers. After
# each step, files the step created or changed are copied to
# $STAGE/<version>/<step>/ and every JSON there is stamped with provenance.
#
# Resumable: a finished step leaves logs/<step>.done and is skipped next time.
# A failed step leaves logs/<step>.failed, a step the GPU could not take
# leaves logs/<step>.blocked, and the lane continues.
#
# Step kinds
#   gpu     local CUDA. Runs under `flock ~/tist-gpu.lock` (shared with another
#           job) and gpu_gate.sh, which reads free VRAM, caps PyTorch's
#           allocator at min(13 GiB, free - 1 GiB) and refuses to start when
#           that is below the step's need. Qwen3-4B loads in bf16 here (its
#           fp32 weights alone are ~16.1 GB, over the 15 GB budget).
#   remote  the Nemotron embedding service only. Under the same flock, with
#           no local CUDA.
#   cpu     CUDA hidden, 8 threads, the shared embedding cache (sitecustomize
#           WP0_EMB_CACHE), Qwen3-4B in its default fp32.
#
# Lanes run as separate background processes:
#   nohup bash evals/wp0_v040/run_wp0_v040.sh gpu  > ~/tist-evals/wp0-v040/logs/lane_gpu.out  2>&1 &
#   nohup bash evals/wp0_v040/run_wp0_v040.sh cpu1 > ~/tist-evals/wp0-v040/logs/lane_cpu1.out 2>&1 &
#   nohup bash evals/wp0_v040/run_wp0_v040.sh cpu2 > ~/tist-evals/wp0-v040/logs/lane_cpu2.out 2>&1 &
#   bash evals/wp0_v040/run_wp0_v040.sh heavy   # GPU-heavy steps, once VRAM allows
#
# 2026-10-30 (coordinator): every remaining step runs on BEAR 0.4.1 (public tag
# v0.4.1, fa87fc5, installed in the venv), version label v041. Label v040 runs
# 0.4.0 from the export ~/tist-evals/bear-10730c8 on PYTHONPATH, v0110 the
# public v0.1.10 tag. Local model loads are refused (WP0_NO_LOCAL_MODELS) until
# the coordinator clears them, so only BM25, hash and the remote Nemotron
# service run (lanes nomodel, attrlex, tracklex, nemo). Nemotron batches hold
# at most 16 texts. The 0.4.0 run (root ~/tist-evals/wp0-v040) is the 0.4.0
# record. This run's root is ~/tist-evals/wp0-v041.
#
# 2026-10-30, later (coordinator): BEAR 0.4.2 candidate, bear-dev 9d085b4, from
# the export ~/tist-evals/bear-9d085b4 installed in the venv (label v042). The
# comparison is 0.1.10 vs 0.4.2. No GPU: every step hides CUDA. Every step runs
# through ~/bin/tist-capped (a systemd scope in tist.slice) at WP0_STEP_MEM
# (default 8G), and the lanes run as tist-capped services. Local models run on
# CPU only, in one dense lane at a time (WP0_ALLOW_LOCAL_MODELS=1). Root
# ~/tist-evals/wp0-v042.
set -u

ROOT=${WP0_ROOT:-$HOME/tist-evals/wp0-v042}
ART=${WP0_ART:-$ROOT/artifacts}   # lane attr runs in a second clone
STAGE=$ROOT/stage
LOGS=$ROOT/logs
PY=${WP0_PY:-$HOME/.venvs/tist-evals/bin/python}
SITE=$ART/evals/wp0_v040/site
BEAR040_EXPORT=$HOME/tist-evals/bear-10730c8
BEAR040_SHA=$(cat "$BEAR040_EXPORT/EXPORTED_SHA")
BEAR042_SRC=$HOME/tist-evals/bear-9d085b4
BEAR042_SHA=$(cat "$BEAR042_SRC/BEAR_GIT_SHA" 2>/dev/null || echo unknown)
BEAR042_EXPECT=9d085b4
BEAR041_SRC=$HOME/tist-evals/bear-v0.4.1
BEAR041_SHA=$(git -C "$BEAR041_SRC" rev-parse HEAD 2>/dev/null || echo unknown)
BEAR041_TAG_SHA=fa87fc5
BEAR0110_SRC=$HOME/tist-evals/bear-v0110
BEAR0110_SHA=$(git -C "$BEAR0110_SRC" rev-parse HEAD 2>/dev/null || echo unknown)
LOCK=$HOME/tist-gpu.lock
EMBCACHE=$ROOT/embcache
CPU_THREADS=${WP0_CPU_THREADS:-8}
QT5=evals/data/external_benchmarks/metatool/query_tags_top5.json
W=evals/wp0_v040

mkdir -p "$STAGE" "$LOGS" "$ART/results/wp0"
cd "$ART" || exit 1

log() { echo "[$(date '+%F %T')] $*"; }
EXTRA_ENV=()
# Kernel-enforced memory cap for every job (coordinator, 2026-10-30): a
# transient systemd scope in tist.slice, MemoryMax 24G, no swap.
CAP=("$HOME/bin/tist-capped" --mem "${WP0_STEP_MEM:-8G}" --)

# step NAME KIND VERSION NEED_GIB MAXWAIT_S -- command...
step() {
  local name=$1 kind=$2 ver=$3 need=$4 maxwait=$5; shift 6
  if [[ -f $LOGS/$name.done ]]; then log "skip $name (done)"; return 0; fi
  rm -f "$LOGS/$name.failed" "$LOGS/$name.blocked"
  local marker=$LOGS/.$name.start
  touch "$marker"; sleep 1
  local pypath sha
  case $ver in
    v042|v042L) pypath=$SITE; sha=$BEAR042_SHA ;;                       # venv site-packages
    v041|v041L) pypath=$SITE:$BEAR041_SRC; sha=$BEAR041_SHA ;;
    v040|v040L) pypath=$SITE:$BEAR040_EXPORT; sha=$BEAR040_SHA ;;
    v0110)      pypath=$SITE:$BEAR0110_SRC; sha=$BEAR0110_SHA ;;
    *) log "unknown version $ver"; return 1 ;;
  esac
  local envs=(
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
    PYTHONUNBUFFERED=1 PYTHONPATH=$pypath BEAR_SOURCE_SHA=$sha
    ANTHROPIC_API_KEY=wp0-dummy-key-no-paid-calls
    WP0_REPORT_VRAM=$LOGS/vram.jsonl WP0_STEP=$name
    "${EXTRA_ENV[@]}"
  )
  [[ ${WP0_ALLOW_LOCAL_MODELS:-0} == 1 ]] || envs+=(WP0_NO_LOCAL_MODELS=1)
  [[ $kind == gpu ]] || envs+=(CUDA_VISIBLE_DEVICES=)   # GPU only for gpu steps (coordinator, 2026-10-30)
  [[ -n ${WP0_ENCODE_BATCH:-} ]] && envs+=(WP0_ENCODE_BATCH=$WP0_ENCODE_BATCH)
  case $kind in
    gpu)    envs+=(WP0_QWEN4B_DTYPE=bfloat16 WP0_SHARE_MODELS=1 WP0_EMB_CACHE=$EMBCACHE) ;;
    remote) envs+=(CUDA_VISIBLE_DEVICES= WP0_NEMO_CACHE=$ROOT/nemocache/nemo.sqlite) ;;
    cpu)    envs+=(CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=$CPU_THREADS MKL_NUM_THREADS=$CPU_THREADS
                   WP0_EMB_CACHE=$EMBCACHE WP0_SHARE_MODELS=1) ;;
  esac
  # Append, never overwrite: a relaunch must not erase the log of an attempt
  # that was killed (the 2026-10-29 relaunch overwrote three such logs).
  {
    echo "### ================ attempt $(date -Is) ================"
    echo "### step:        $name"
    echo "### kind:        $kind (need ${need} GiB)"
    echo "### bear:        $ver ($sha)"
    echo "### started:     $(date -Is)"
    echo "### command:     $*"
    echo "### env:         ${envs[*]}"
    echo "### memory cap:  ${CAP[*]}"
  } >> "$LOGS/$name.log"
  log "start $name ($kind, $ver)"
  local rc waited=0
  while true; do
    # Two memory layers. The kernel cap (CAP, systemd scope in tist.slice with
    # MemoryMax and no swap) kills the step alone if it passes the cap, with
    # exit 137. mem_guard.sh polls as a second layer, and also stops the step
    # when WSL's available memory falls below 16 GiB.
    case $kind in
      gpu)    flock "$LOCK" env -u OPENAI_API_KEY "${envs[@]}" bash "$W/gpu_gate.sh" "$need" \
                "${CAP[@]}" bash "$W/mem_guard.sh" "$@" >> "$LOGS/$name.log" 2>&1; rc=$? ;;
      remote) flock "$LOCK" env -u OPENAI_API_KEY "${envs[@]}" "${CAP[@]}" bash "$W/mem_guard.sh" "$@" \
                >> "$LOGS/$name.log" 2>&1; rc=$? ;;
      cpu)    env -u OPENAI_API_KEY "${envs[@]}" "${CAP[@]}" bash "$W/mem_guard.sh" "$@" \
                >> "$LOGS/$name.log" 2>&1; rc=$? ;;
    esac
    (( rc == 137 )) && echo "### killed (rc 137): the ${WP0_STEP_MEM:-8G} memory cap of the scope" >> "$LOGS/$name.log"
    if [[ $rc -eq 77 ]] && grep -q "not started" <(tail -2 "$LOGS/$name.log"); then
      rc=75   # memory low before start: wait like a VRAM shortfall
    fi
    [[ $rc -ne 75 ]] && break
    if (( waited >= maxwait )); then break; fi
    sleep 300; waited=$((waited + 300))
  done
  echo "### finished:    $(date -Is) rc=$rc" >> "$LOGS/$name.log"
  local dest=$STAGE/$ver/$name; mkdir -p "$dest"
  cp "$LOGS/$name.log" "$dest/"
  while IFS= read -r f; do
    rel=${f#"$ART"/}
    if git -C "$ART" cat-file -e "HEAD:$rel" 2>/dev/null && \
       git -C "$ART" show "HEAD:$rel" | cmp -s - "$f"; then
      # Byte-identical to the committed (published) file. An LLM cache the
      # script rewrote is an input, so leave it out. A result file that
      # reproduced exactly is kept, and listed as such.
      case $rel in results/toolbench_*_categories.json) continue ;; esac
      echo "$rel" >> "$dest/IDENTICAL_TO_COMMITTED.txt"
    fi
    mkdir -p "$dest/$(dirname "$rel")"
    cp "$f" "$dest/$rel"
  done < <(find "$ART/results" "$ART/evals/results" -type f -newer "$marker" \
             ! -path "*/results/wp0/wp4_lists/*" ! -path "*/results/wp0/lists_*" 2>/dev/null)
  env "${envs[@]}" CUDA_VISIBLE_DEVICES= WP0_EMB_CACHE= "${CAP[@]}" "$PY" "$W/stamp_dir.py" "$dest" \
      --step "$name" --command "$*" >> "$LOGS/$name.log" 2>&1
  if [[ $rc -eq 0 ]]; then touch "$LOGS/$name.done"; log "done $name"
  elif [[ $rc -eq 75 ]]; then echo "not enough free VRAM or memory" > "$LOGS/$name.blocked"; log "BLOCKED $name (VRAM or memory)"
  elif [[ $rc -eq 76 || $rc -eq 77 ]]; then echo "$rc memory guard" > "$LOGS/$name.failed"; log "FAILED $name (memory guard rc=$rc)"
  elif [[ $rc -eq 78 ]]; then echo "78 card over the stop limit" > "$LOGS/$name.failed"; touch "$LOGS/.card_stop"
       log "FAILED $name (card over ${WP0_WIN_GPU_STOP_MIB:-?} MiB, rc=78); the lane stops"
  else echo "$rc" > "$LOGS/$name.failed"; log "FAILED $name rc=$rc"; fi
  return 0
}

# tb NAME KIND VERSION NEED SCOPE experiments...   SCOPE: all | toolbench | metatool
tb() {
  local name=$1 kind=$2 ver=$3 need=$4 scope=$5; shift 5
  local extra=()
  [[ $scope == toolbench ]] && extra=(--toolbench-only)
  [[ $scope == metatool ]] && extra=(--metatool-only)
  step "$name" "$kind" "$ver" "$need" 0 -- "$PY" "$W/eval_toolbench_v040.py" --top-k 5 \
      --metatool-query-tags-file "$QT5" "${extra[@]}" \
      --output "results/wp0/toolbench_eval_${name}.json" --backends "$@"
}

# lists NAME KIND VERSION NEED MODE BACKEND...
lists() {
  local name=$1 kind=$2 ver=$3 need=$4 mode=$5; shift 5
  local out=results/wp0/lists_$ver extra=()
  if [[ $mode != e2e ]]; then
    out=results/wp0/wp4_lists_$ver
    extra=(--share-query-embeddings --nest-check 200 --progress 5000)
  fi
  step "$name" "$kind" "$ver" "$need" 0 -- "$PY" "$W/dump_toolbench_lists.py" --mode "$mode" \
      --backends "$@" --outdir "$out" "${extra[@]}"
}

petsim_suite() {  # version, suffix, kind
  local ver=$1 sfx=$2 kind=$3
  step "retrieval_hash$sfx"     cpu "$ver" 0 0 -- "$PY" evals/eval_retrieval.py
  step "retrieval_semantic$sfx" "$kind" "$ver" 1 0 -- "$PY" evals/eval_retrieval.py --semantic
  step "backends$sfx"           "$kind" "$ver" 3 0 -- "$PY" evals/eval_retrieval_backends.py --all \
      --output results/wp0/backend_comparison.json
  step "gov_ablation$sfx"       "$kind" "$ver" 3 0 -- "$PY" evals/eval_governance_ablation.py \
      --output results/wp0/governance_ablation.json
  step "decomposed$sfx"         "$kind" "$ver" 3 0 -- "$PY" evals/eval_governance_decomposed.py
  step "alpha_sweep$sfx"        "$kind" "$ver" 3 0 -- "$PY" evals/eval_alpha_sweep.py
}

lane_gpu() {
  step verify cpu v040 0 0 -- "$PY" "$W/verify_env.py" --export "$BEAR040_EXPORT" \
      --out results/wp0/run_provenance.json
  tb tb_bge gpu v040 1 all "BEAR+BGE (gov)" "BEAR+BGE (mand-only)" "BGE (no gov)"
  lists e2e_bge_v040  gpu v040  1 e2e bge
  lists e2e_bge_v0110 gpu v0110 1 e2e bge
  step t4_inferred gpu v040 1 0 -- "$PY" evals/eval_toolbench_inferred_categories.py
  step t4_multitag gpu v040 1 0 -- "$PY" evals/eval_toolbench_multitag_categories.py
  step t4_top5     gpu v040 1 0 -- "$PY" evals/eval_toolbench_top5_categories.py
  step transfer_toolbench gpu v040 1 0 -- "$PY" evals/eval_backend_transfer.py --corpus toolbench \
      --output results/wp0/backend_transfer_toolbench_toolbench_ir_bert_based_uncased.json
  step transfer_metatool gpu v040 1 0 -- "$PY" evals/eval_backend_transfer.py --corpus metatool \
      --output results/wp0/backend_transfer_metatool_toolbench_ir_bert_based_uncased.json
  step toolllm_both gpu v040 1 0 -- "$PY" evals/eval_toolbench_toolllm.py \
      --model ToolBench/ToolBench_IR_bert_based_uncased --top-k 5 --mode both \
      --output results/wp0/toolbench_toolllm_fixed.json
  step framework_toolbench gpu v040 1.2 0 -- "$PY" evals/eval_framework_baseline.py --corpus toolbench \
      --output results/wp0/framework_baseline_toolbench.json
  step framework_petsim gpu v040 1.2 0 -- "$PY" evals/eval_framework_baseline.py --corpus petsim \
      --output results/wp0/framework_baseline_petsim.json
  step tool_scaling        gpu v040 1 0 -- "$PY" evals/eval_tool_scaling.py
  step scalability         gpu v040 1 0 -- "$PY" evals/eval_scalability.py
  step baseline_comparison gpu v040 1 0 -- "$PY" evals/eval_baseline_comparison.py
  lists wp4_tb_bge gpu v040 1 toolbench bge
  lists wp4_mt_bge gpu v040 1 metatool-tags bge
  # Nemotron (remote service, no local VRAM)
  tb tb_nemotron remote v040 0 all "BEAR+Nemotron (gov)" "Nemotron (no gov)"
  lists e2e_nemotron_v040 remote v040 0 e2e nemotron
  lists wp4_tb_nemotron remote v040 0 toolbench nemotron
  lists wp4_mt_nemotron remote v040 0 metatool-tags nemotron
  # 0.1.10 controls on the GPU for BGE (cheap)
  tb tb_bge_v0110 gpu v0110 1 all "BEAR+BGE (gov)" "BEAR+BGE (mand-only)" "BGE (no gov)"
  step tool_scaling_v0110        gpu v0110 1 0 -- "$PY" evals/eval_tool_scaling.py
  step baseline_comparison_v0110 gpu v0110 1 0 -- "$PY" evals/eval_baseline_comparison.py
}

# After the model servers were restarted (21:00, not by this run) the embedding
# server no longer held its inflated allocation, so the dense models moved
# back to the GPU: fp32 as published for BGE, BGE-M3 and Qwen3-0.6B, bf16 for
# Qwen3-4B (its fp32 weights alone exceed the 15 GB budget). GPU steps use the
# embedding cache too (keyed by device and dtype), so a 0.1.10 control and the
# WP4 lists reuse the vectors of the main 0.4.0 run.
lane_gpu2() {
  step verify cpu v041 0 0 -- "$PY" "$W/verify_env.py" --export "$BEAR041_SRC" --expect-sha "$BEAR041_TAG_SHA" --expect-version 0.4.1 \
      --out results/wp0/run_provenance.json
  tb tb_bge gpu v041 1 all "BEAR+BGE (gov)" "BEAR+BGE (mand-only)" "BGE (no gov)"
  lists e2e_bge_v040  gpu v041  1 e2e bge
  lists e2e_bge_v0110 gpu v0110 1 e2e bge
  tb tbg_qwen06 gpu v041 3.5 all "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbg_bgem3  gpu v041 3.5 all "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
  lists e2e_dense_gpu_v040  gpu v041  3.5 e2e qwen3-0.6b bge-m3
  lists e2e_dense_gpu_v0110 gpu v0110 3.5 e2e qwen3-0.6b bge-m3
  tb tb_nemotron remote v041 0 all "BEAR+Nemotron (gov)" "Nemotron (no gov)"
  lists e2e_nemotron_v040 remote v041 0 e2e nemotron
  tb tbg_qwen4b gpu v041 11 all "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  lists e2e_q4b_gpu_v040  gpu v041  11 e2e qwen3-4b
  lists e2e_q4b_gpu_v0110 gpu v0110 11 e2e qwen3-4b
  step reranker_toolbench gpu v041 3 0 -- "$PY" evals/eval_reranker_composition.py --corpus toolbench \
      --output results/wp0/reranker_composition_toolbench.json
  step framework_toolbench gpu v041 1.5 0 -- "$PY" evals/eval_framework_baseline.py --corpus toolbench \
      --output results/wp0/framework_baseline_toolbench.json
  step framework_petsim gpu v041 1.5 0 -- "$PY" evals/eval_framework_baseline.py --corpus petsim \
      --output results/wp0/framework_baseline_petsim.json
  # WP4 ranked lists (embeddings come from the cache of the runs above)
  lists wp4_tb_bge gpu v041 1 toolbench bge
  lists wp4_mt_bge gpu v041 1 metatool-tags bge
  lists wp4_tb_dense_gpu gpu v041 3.5 toolbench qwen3-0.6b bge-m3
  lists wp4_mt_dense_gpu gpu v041 3.5 metatool-tags qwen3-0.6b bge-m3
  lists wp4_tb_nemotron remote v041 0 toolbench nemotron
  lists wp4_mt_nemotron remote v041 0 metatool-tags nemotron
  lists wp4_tb_q4b_gpu gpu v041 11 toolbench qwen3-4b
  lists wp4_mt_q4b gpu v041 11 metatool-tags qwen3-4b
  # 0.1.10 controls under the same numerics (cached vectors)
  tb tb_bge_v0110     gpu v0110 1   all "BEAR+BGE (gov)" "BEAR+BGE (mand-only)" "BGE (no gov)"
  tb tbg_qwen06_v0110 gpu v0110 3.5 all "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbg_bgem3_v0110  gpu v0110 3.5 all "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
  tb tbg_qwen4b_v0110 gpu v0110 11  all "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
}

lane_cpu1() {
  tb tb_bm25 cpu v041 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
  tb tb_hash cpu v041 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)" "Hash (no gov)"
  lists e2e_lex_v040  cpu v041  0 e2e bm25 hash
  lists e2e_lex_v0110 cpu v0110 0 e2e bm25 hash
  lists wp4_tb_lex cpu v041 0 toolbench bm25 hash
  lists wp4_mt_lex cpu v041 0 metatool-tags bm25 hash
  petsim_suite v041 "" cpu
  petsim_suite v0110 "_v0110" cpu
  lists e2e_q4b_v040  cpu v041  0 e2e qwen3-4b
  lists e2e_q4b_v0110 cpu v0110 0 e2e qwen3-4b
  step reranker_petsim cpu v041 0 0 -- "$PY" evals/eval_reranker_composition.py --corpus petsim \
      --device cpu --output results/wp0/reranker_composition_petsim.json
  step ablation_lexical  cpu v041 0 0 -- "$PY" evals/eval_ablation.py
  step ablation_semantic cpu v041 0 0 -- "$PY" evals/eval_ablation.py --semantic
  step tool_composition  cpu v041 0 0 -- "$PY" evals/eval_tool_composition.py
  step scalability_cpu   cpu v041 0 0 -- "$PY" evals/eval_scalability.py
  tb tb_bm25_v0110 cpu v0110 0 all "BEAR+BM25 (gov)" "BM25 (no gov)"
  tb tb_hash_v0110 cpu v0110 0 all "BEAR+Hash (gov)" "Hash (no gov)"
}

lane_cpu2() {
  tb tbc_qwen06_tb cpu v040 0 toolbench "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbc_bgem3_tb  cpu v040 0 toolbench "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
  lists e2e_dense_v040  cpu v040  0 e2e qwen3-0.6b bge-m3
  lists e2e_dense_v0110 cpu v0110 0 e2e qwen3-0.6b bge-m3
  lists wp4_tb_dense cpu v040 0 toolbench qwen3-0.6b bge-m3
  tb tbc_qwen4b_tb cpu v040 0 toolbench "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  lists wp4_tb_q4b cpu v040 0 toolbench qwen3-4b
  tb tbc_qwen06_mt cpu v040 0 metatool "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbc_bgem3_mt  cpu v040 0 metatool "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
  lists wp4_mt_dense cpu v040 0 metatool-tags qwen3-0.6b bge-m3
  # 0.1.10 controls under the same CPU numerics (embeddings come from the cache)
  tb tbc_qwen06_tb_v0110 cpu v0110 0 toolbench "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbc_bgem3_tb_v0110  cpu v0110 0 toolbench "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
  tb tbc_qwen4b_tb_v0110 cpu v0110 0 toolbench "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  tb tbc_qwen06_mt_v0110 cpu v0110 0 metatool "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbc_bgem3_mt_v0110  cpu v0110 0 metatool "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
}

lane_heavy() {  # needs VRAM the shared GPU does not have free at the moment
  # Qwen3-4B runs in bf16 here (WP0_QWEN4B_DTYPE), so it fits the 13 GiB cap.
  # The paper's runs used fp32, so a 0.1.10 control in the same precision
  # follows each 0.4.0 run.
  step reranker_toolbench gpu v041 3 0 -- "$PY" evals/eval_reranker_composition.py --corpus toolbench \
      --output results/wp0/reranker_composition_toolbench.json
  tb tbg_qwen4b_tb gpu v041 11 toolbench "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  tb tbg_qwen4b_tb_v0110 gpu v0110 11 toolbench "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  lists wp4_tb_q4b_gpu gpu v041 11 toolbench qwen3-4b
  tb tbg_qwen4b_mt gpu v041 11 metatool "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  tb tbg_qwen4b_mt_v0110 gpu v0110 11 metatool "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
  lists wp4_mt_q4b gpu v041 11 metatool-tags qwen3-4b
  lists e2e_q4b_gpu_v040  gpu v041  11 e2e qwen3-4b
  lists e2e_q4b_gpu_v0110 gpu v0110 11 e2e qwen3-4b
  # Dense MetaTool runs, fp32 as published (moved off the CPU)
  tb tbg_qwen06_mt gpu v041 3.5 metatool "BEAR+Qwen3-0.6B (gov)" "Qwen3-0.6B (no gov)"
  tb tbg_bgem3_mt  gpu v041 3.5 metatool "BEAR+BGE-M3 (gov)" "BGE-M3 (no gov)"
  lists wp4_mt_dense_gpu gpu v041 3.5 metatool-tags qwen3-0.6b bge-m3
}

# Attribution: the same CPU runs on 0.4.0 with BEAR's legacy switches on
# (sitecustomize WP0_BEAR_LEGACY), all at once and one at a time. A switch that
# brings a changed cell back to its 0.1.10 value names the release change that
# moved it. What "all" leaves different comes from the mandatory rules, which
# have no switch. Run in a second clone (WP0_ART), because these scripts write
# fixed paths under results/ that lane cpu1 writes too.
attr_suite() {  # label switches
  local lab=$1 sw=$2
  EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
  step "retrieval_hash_L$lab"     cpu v041L 0 0 -- "$PY" evals/eval_retrieval.py
  step "retrieval_semantic_L$lab" cpu v041L 0 0 -- "$PY" evals/eval_retrieval.py --semantic
  step "backends_L$lab"           cpu v041L 0 0 -- "$PY" evals/eval_retrieval_backends.py --all       --output results/wp0/backend_comparison.json
  step "gov_ablation_L$lab"       cpu v041L 0 0 -- "$PY" evals/eval_governance_ablation.py       --output results/wp0/governance_ablation.json
  step "decomposed_L$lab"         cpu v041L 0 0 -- "$PY" evals/eval_governance_decomposed.py
  step "alpha_sweep_L$lab"        cpu v041L 0 0 -- "$PY" evals/eval_alpha_sweep.py
  step "baseline_comparison_L$lab" cpu v041L 0 0 -- "$PY" evals/eval_baseline_comparison.py
  step "tool_scaling_L$lab"       cpu v041L 0 0 -- "$PY" evals/eval_tool_scaling.py
  EXTRA_ENV=()
}

lane_attr() {
  # CPU baselines for the scripts whose main 0.4.0 runs are on the GPU
  step baseline_comparison_cpu cpu v041 0 0 -- "$PY" evals/eval_baseline_comparison.py
  step tool_scaling_cpu        cpu v041 0 0 -- "$PY" evals/eval_tool_scaling.py
  step baseline_comparison_cpu_v0110 cpu v0110 0 0 -- "$PY" evals/eval_baseline_comparison.py
  step tool_scaling_cpu_v0110        cpu v0110 0 0 -- "$PY" evals/eval_tool_scaling.py
  attr_suite all all
  attr_suite ungated_pool ungated_pool
  attr_suite below_threshold below_threshold
  attr_suite ranked_resolution ranked_resolution
  attr_suite removed_acting removed_acting
}

# Which cells admit anything through the required-tags backfill (trace reason
# "required_tags"), whose score 0.4.1 changes. External cells come from
# track_backfill.py. The committed Pet Sim, customer-support and tool-scaling
# scripts rerun under the sitecustomize trace hook (WP0_TRACE_LOG), which
# checks that the traced output equals retrieve()'s. Runs in a third clone
# (WP0_ART), because the scripts write fixed paths under results/.
lane_track() {
  step track_external_lex cpu v041 0 0 -- "$PY" "$W/track_backfill.py" --backends bm25 hash \
      --out results/wp0/backfill_tracking_external_lex.json
  step track_external_bge cpu v041 0 0 -- "$PY" "$W/track_backfill.py" --backends bge \
      --benchmarks toolbench e2e --out results/wp0/backfill_tracking_external_bge.json
  local s
  for s in retrieval_hash retrieval_semantic backends gov_ablation decomposed alpha_sweep \
           baseline_comparison tool_scaling scalability; do
    EXTRA_ENV=(WP0_TRACE_LOG=$LOGS/trace_$s.jsonl)
    case $s in
      retrieval_hash)      step track_$s cpu v041 0 0 -- "$PY" evals/eval_retrieval.py ;;
      retrieval_semantic)  step track_$s cpu v041 0 0 -- "$PY" evals/eval_retrieval.py --semantic ;;
      backends)            step track_$s cpu v041 0 0 -- "$PY" evals/eval_retrieval_backends.py --all \
                               --output results/wp0/backend_comparison.json ;;
      gov_ablation)        step track_$s cpu v041 0 0 -- "$PY" evals/eval_governance_ablation.py \
                               --output results/wp0/governance_ablation.json ;;
      decomposed)          step track_$s cpu v041 0 0 -- "$PY" evals/eval_governance_decomposed.py ;;
      alpha_sweep)         step track_$s cpu v041 0 0 -- "$PY" evals/eval_alpha_sweep.py ;;
      baseline_comparison) step track_$s cpu v041 0 0 -- "$PY" evals/eval_baseline_comparison.py ;;
      tool_scaling)        step track_$s cpu v041 0 0 -- "$PY" evals/eval_tool_scaling.py ;;
      scalability)         step track_$s cpu v041 0 0 -- "$PY" evals/eval_scalability.py ;;
    esac
  done
  EXTRA_ENV=()
}

# ---------------------------------------------------------------------------
# 0.4.1 lanes that load no local model (2026-10-30)
# ---------------------------------------------------------------------------

verify041() {
  step verify cpu v041 0 0 -- "$PY" "$W/verify_env.py" --export "$BEAR041_SRC" \
      --expect-sha "$BEAR041_TAG_SHA" --expect-version 0.4.1 --out results/wp0/run_provenance.json
}

petsim_lex() {  # version suffix: the Pet Sim scripts on BM25 and hash only
  local ver=$1 sfx=$2
  step "retrieval_hash$sfx"   cpu "$ver" 0 0 -- "$PY" evals/eval_retrieval.py
  step "backends_lex$sfx"     cpu "$ver" 0 0 -- "$PY" evals/eval_retrieval_backends.py --models hash bm25 \
      --output results/wp0/backend_comparison_lex.json
  step "gov_ablation_lex$sfx" cpu "$ver" 0 0 -- "$PY" evals/eval_governance_ablation.py \
      --backends bm25 hash --skip-itr --output results/wp0/governance_ablation_lex.json
  step "decomposed_bm25$sfx"  cpu "$ver" 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends bm25
  step "alpha_sweep_bm25$sfx" cpu "$ver" 0 0 -- "$PY" evals/eval_alpha_sweep.py --backends bm25
}

lane_nomodel() {
  verify041
  tb tb_bm25 cpu v041 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
  tb tb_hash cpu v041 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)" "Hash (no gov)"
  # 0.4.1 with the 0.4.0 backfill (Config.restore_flat_backfill): isolates the fix
  EXTRA_ENV=(WP0_BEAR_LEGACY=flat_backfill)
  tb tb_bm25_Lflat cpu v041L 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)"
  tb tb_hash_Lflat cpu v041L 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)"
  EXTRA_ENV=()
  # 0.1.10 with the sorted MetaTool+Tags tags (artifacts e593950)
  tb tb_bm25_v0110 cpu v0110 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
  tb tb_hash_v0110 cpu v0110 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)" "Hash (no gov)"
  lists e2e_lex_v041  cpu v041  0 e2e bm25 hash
  lists e2e_lex_v0110 cpu v0110 0 e2e bm25 hash
  lists wp4_tb_lex cpu v041 0 toolbench bm25 hash
  lists wp4_mt_lex cpu v041 0 metatool-tags bm25 hash
  petsim_lex v041 ""
  petsim_lex v0110 "_v0110"
  step ablation_lexical cpu v041 0 0 -- "$PY" evals/eval_ablation.py
  step tool_composition cpu v041 0 0 -- "$PY" evals/eval_tool_composition.py
}

lane_attrlex() {  # single-switch attribution on hash and BM25 (second clone)
  local sw
  for sw in all ungated_pool below_threshold ranked_resolution removed_acting pool_by_k \
            unchecked_requires flat_backfill; do
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    step "retrieval_hash_L$sw"   cpu v041L 0 0 -- "$PY" evals/eval_retrieval.py
    step "backends_lex_L$sw"     cpu v041L 0 0 -- "$PY" evals/eval_retrieval_backends.py --models hash bm25 \
        --output results/wp0/backend_comparison_lex.json
    step "gov_ablation_lex_L$sw" cpu v041L 0 0 -- "$PY" evals/eval_governance_ablation.py \
        --backends bm25 hash --skip-itr --output results/wp0/governance_ablation_lex.json
    step "decomposed_bm25_L$sw"  cpu v041L 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends bm25
    step "alpha_sweep_bm25_L$sw" cpu v041L 0 0 -- "$PY" evals/eval_alpha_sweep.py --backends bm25
  done
  EXTRA_ENV=()
}

lane_tracklex() {  # required_tags admissions on 0.4.0 and 0.4.1 (third clone)
  local v
  for v in v040 v041; do
    step "track_external_lex_$v" cpu $v 0 0 -- "$PY" "$W/track_backfill.py" --backends bm25 hash \
        --out results/wp0/backfill_tracking_external_lex_$v.json
    EXTRA_ENV=(WP0_TRACE_LOG=$LOGS/trace_petsim_lex_$v.jsonl)
    step "track_retrieval_hash_$v"    cpu $v 0 0 -- "$PY" evals/eval_retrieval.py
    step "track_backends_lex_$v"      cpu $v 0 0 -- "$PY" evals/eval_retrieval_backends.py --models hash bm25 \
        --output results/wp0/backend_comparison_lex.json
    step "track_gov_ablation_lex_$v"  cpu $v 0 0 -- "$PY" evals/eval_governance_ablation.py \
        --backends bm25 hash --skip-itr --output results/wp0/governance_ablation_lex.json
    step "track_decomposed_bm25_$v"   cpu $v 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends bm25
    step "track_alpha_sweep_bm25_$v"  cpu $v 0 0 -- "$PY" evals/eval_alpha_sweep.py --backends bm25
    EXTRA_ENV=()
  done
}

lane_nemo() {  # Nemotron through 8360, batches of at most 16 texts
  tb tb_nemotron remote v041 0 all "BEAR+Nemotron (gov)" "Nemotron (no gov)"
  lists e2e_nemotron_v041 remote v041 0 e2e nemotron
  lists wp4_tb_nemotron remote v041 0 toolbench nemotron
  lists wp4_mt_nemotron remote v041 0 metatool-tags nemotron
}

# ---------------------------------------------------------------------------
# BEAR 0.4.2 lanes (coordinator, 2026-10-30). No GPU. Lexical and Nemotron
# steps run at WP0_STEP_MEM=8G. Dense lanes run on CPU, one at a time, with
# WP0_ALLOW_LOCAL_MODELS=1, WP0_STEP_MEM <= 20G, WP0_ENCODE_BATCH small and
# WP0_CPU_THREADS <= 12 (set when the lane is launched).
# ---------------------------------------------------------------------------

SWITCHES_042="all ungated_pool below_threshold ranked_resolution removed_acting pool_by_k unchecked_requires flat_backfill dropped_rows tie_order"

verify042() {
  step verify cpu v042 0 0 -- "$PY" "$W/verify_env.py" --export "$BEAR042_SRC" \
      --expect-sha "$BEAR042_EXPECT" --expect-version 0.4.2 --out results/wp0/run_provenance.json
}

lane_lex042() {  # step 1: BM25 and hash across all tables, and 0.1.10 controls
  verify042
  tb tb_bm25 cpu v042 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
  tb tb_hash cpu v042 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)" "Hash (no gov)"
  tb tb_bm25_v0110 cpu v0110 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
  tb tb_hash_v0110 cpu v0110 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)" "Hash (no gov)"
  lists e2e_lex_v042  cpu v042  0 e2e bm25 hash
  lists e2e_lex_v0110 cpu v0110 0 e2e bm25 hash
  petsim_lex v042 ""
  petsim_lex v0110 "_v0110"
  step ablation_lexical cpu v042 0 0 -- "$PY" evals/eval_ablation.py
  step tool_composition cpu v042 0 0 -- "$PY" evals/eval_tool_composition.py
  lists wp4_tb_lex cpu v042 0 toolbench bm25 hash
  lists wp4_mt_lex cpu v042 0 metatool-tags bm25 hash
}

lane_attrpet042() {  # Pet Sim single-switch attribution on hash and BM25 (second clone)
  local sw
  for sw in $SWITCHES_042; do
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    step "retrieval_hash_L$sw"   cpu v042L 0 0 -- "$PY" evals/eval_retrieval.py
    step "backends_lex_L$sw"     cpu v042L 0 0 -- "$PY" evals/eval_retrieval_backends.py --models hash bm25 \
        --output results/wp0/backend_comparison_lex.json
    step "gov_ablation_lex_L$sw" cpu v042L 0 0 -- "$PY" evals/eval_governance_ablation.py \
        --backends bm25 hash --skip-itr --output results/wp0/governance_ablation_lex.json
    step "decomposed_bm25_L$sw"  cpu v042L 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends bm25
    step "alpha_sweep_bm25_L$sw" cpu v042L 0 0 -- "$PY" evals/eval_alpha_sweep.py --backends bm25
  done
  EXTRA_ENV=()
}

lane_attrtb042() {  # external-table single-switch attribution on BM25 and hash (third clone)
  local sw
  for sw in ${WP0_SWITCHES:-$SWITCHES_042}; do
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    tb "tb_bm25_L$sw" cpu v042L 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
    tb "tb_hash_L$sw" cpu v042L 0 all "BEAR+Hash (gov)" "BEAR+Hash (mand-only)" "Hash (no gov)"
  done
  EXTRA_ENV=()
}

lane_nemo042() {  # step 2: Nemotron through 8360, batches of at most 16 texts
  tb tb_nemotron remote v042 0 all "BEAR+Nemotron (gov)" "Nemotron (no gov)"
  lists e2e_nemotron_v042 remote v042 0 e2e nemotron
  lists wp4_tb_nemotron remote v042 0 toolbench nemotron
  lists wp4_mt_nemotron remote v042 0 metatool-tags nemotron
}

lane_dense042() {  # step 3: local models on CPU, one dense lane at a time (fourth clone)
  # Launched with WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=20G WP0_ENCODE_BATCH=4
  # WP0_CPU_THREADS=12. Qwen3-4B on ToolBench and MetaTool is not here: on the
  # CPU it needs far more than 12 hours, so it waits for a GPU window.
  [[ ${WP0_ALLOW_LOCAL_MODELS:-0} == 1 ]] || { log "dense042 needs WP0_ALLOW_LOCAL_MODELS=1"; return 1; }
  # BGE: Tables 3, 5, 6, the end-to-end lists, Table 4, WP4
  tb tb_bge cpu v042 0 all "BEAR+BGE (gov)" "BEAR+BGE (mand-only)" "BGE (no gov)"
  tb tb_bge_v0110 cpu v0110 0 all "BEAR+BGE (gov)" "BEAR+BGE (mand-only)" "BGE (no gov)"
  lists e2e_bge_v042  cpu v042  0 e2e bge
  lists e2e_bge_v0110 cpu v0110 0 e2e bge
  step t4_inferred cpu v042 0 0 -- "$PY" evals/eval_toolbench_inferred_categories.py
  step t4_multitag cpu v042 0 0 -- "$PY" evals/eval_toolbench_multitag_categories.py
  step t4_top5     cpu v042 0 0 -- "$PY" evals/eval_toolbench_top5_categories.py
  lists wp4_tb_bge cpu v042 0 toolbench bge
  lists wp4_mt_bge cpu v042 0 metatool-tags bge
  # Pet Sim, all backends. Qwen3-4B (16.1 GB in fp32) runs in its own process,
  # so no other model is resident beside it under the 20G cap.
  local v sfx
  for v in v042 v0110; do
    sfx=""; [[ $v == v0110 ]] && sfx=_v0110
    step "retrieval_semantic$sfx" cpu $v 0 0 -- "$PY" evals/eval_retrieval.py --semantic
    step "backends_dense$sfx" cpu $v 0 0 -- "$PY" evals/eval_retrieval_backends.py         --models bge bge-m3 qwen3 itr --output results/wp0/backend_comparison_dense.json
    step "backends_q4b$sfx" cpu $v 0 0 -- "$PY" evals/eval_retrieval_backends.py         --models qwen3-4b --output results/wp0/backend_comparison_q4b.json
    step "gov_ablation_dense$sfx" cpu $v 0 0 -- "$PY" evals/eval_governance_ablation.py         --backends bge bge-m3 qwen3 --output results/wp0/governance_ablation_dense.json
    step "gov_ablation_q4b$sfx" cpu $v 0 0 -- "$PY" evals/eval_governance_ablation.py         --backends qwen3-4b --skip-itr --output results/wp0/governance_ablation_q4b.json
    step "decomposed_dense$sfx" cpu $v 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends bge bge-m3 qwen3
    step "decomposed_q4b$sfx"   cpu $v 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends qwen3-4b
    step "alpha_sweep_dense$sfx" cpu $v 0 0 -- "$PY" evals/eval_alpha_sweep.py --backends bge bge-m3 qwen3
    step "alpha_sweep_q4b$sfx"   cpu $v 0 0 -- "$PY" evals/eval_alpha_sweep.py --backends qwen3-4b
  done
  local sw
  for sw in $SWITCHES_042; do   # dense attribution, BGE
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    step "retrieval_semantic_L$sw" cpu v042L 0 0 -- "$PY" evals/eval_retrieval.py --semantic
    step "backends_bge_L$sw" cpu v042L 0 0 -- "$PY" evals/eval_retrieval_backends.py --models bge \
        --output results/wp0/backend_comparison_bge.json
    EXTRA_ENV=()
  done
  # Customer support and tool scaling (BGE)
  step baseline_comparison cpu v042 0 0 -- "$PY" evals/eval_baseline_comparison.py
  step tool_scaling        cpu v042 0 0 -- "$PY" evals/eval_tool_scaling.py
  step scalability         cpu v042 0 0 -- "$PY" evals/eval_scalability.py
  step baseline_comparison_v0110 cpu v0110 0 0 -- "$PY" evals/eval_baseline_comparison.py
  step tool_scaling_v0110        cpu v0110 0 0 -- "$PY" evals/eval_tool_scaling.py
  # ToolBench-IR, LlamaIndex, reranker
  step transfer_toolbench cpu v042 0 0 -- "$PY" evals/eval_backend_transfer.py --corpus toolbench \
      --output results/wp0/backend_transfer_toolbench_toolbench_ir_bert_based_uncased.json
  step transfer_metatool cpu v042 0 0 -- "$PY" evals/eval_backend_transfer.py --corpus metatool \
      --output results/wp0/backend_transfer_metatool_toolbench_ir_bert_based_uncased.json
  step toolllm_both cpu v042 0 0 -- "$PY" evals/eval_toolbench_toolllm.py \
      --model ToolBench/ToolBench_IR_bert_based_uncased --top-k 5 --mode both \
      --output results/wp0/toolbench_toolllm_fixed.json
  step framework_petsim cpu v042 0 0 -- "$PY" evals/eval_framework_baseline.py --corpus petsim \
      --output results/wp0/framework_baseline_petsim.json
  step framework_toolbench cpu v042 0 0 -- "$PY" evals/eval_framework_baseline.py --corpus toolbench \
      --output results/wp0/framework_baseline_toolbench.json
  step reranker_petsim cpu v042 0 0 -- "$PY" evals/eval_reranker_composition.py --corpus petsim \
      --device cpu --output results/wp0/reranker_composition_petsim.json
  step reranker_toolbench cpu v042 0 0 -- "$PY" evals/eval_reranker_composition.py --corpus toolbench \
      --device cpu --batch-size 4 --output results/wp0/reranker_composition_toolbench.json
  # BGE-M3 and Qwen3-0.6B on the external tables
  local m lab
  for m in bgem3 qwen06; do
    case $m in bgem3) lab=BGE-M3; b=bge-m3 ;; qwen06) lab=Qwen3-0.6B; b=qwen3-0.6b ;; esac
    tb tb_$m cpu v042 0 all "BEAR+$lab (gov)" "$lab (no gov)"
    tb tb_${m}_v0110 cpu v0110 0 all "BEAR+$lab (gov)" "$lab (no gov)"
    lists e2e_${m}_v042  cpu v042  0 e2e $b
    lists e2e_${m}_v0110 cpu v0110 0 e2e $b
    lists wp4_tb_$m cpu v042 0 toolbench $b
    lists wp4_mt_$m cpu v042 0 metatool-tags $b
  done
}

lane_mand042() {  # mandatory finding, per query (coordinator, 2026-10-30): lexical backends, no model
  local sw
  step diag_mand_lex_v0110 cpu v0110 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
      --out results/wp0/diag_mandatory_lex_v0110.json
  step diag_mand_lex_v042 cpu v042 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
      --out results/wp0/diag_mandatory_lex_v042.json
  for sw in $SWITCHES_042; do
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    step "diag_mand_lex_L$sw" cpu v042L 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
        --out "results/wp0/diag_mandatory_lex_v042_L$sw.json"
  done
  EXTRA_ENV=()
}
lane_e2eattr042() {  # which switch brings back the 0.1.10 BM25 end-to-end lists (Table 7)
  local sw
  for sw in $SWITCHES_042; do
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    step "e2e_bm25_L$sw" cpu v042L 0 0 -- "$PY" "$W/dump_toolbench_lists.py" --mode e2e \
        --backends bm25 --outdir "results/wp0/lists_v042L_$sw"
  done
  EXTRA_ENV=()
}
lane_pair042() {  # BM25 needs two switches at once: tie_order alone restores the governed
  # e2e lists but not the ungated ones (2026-10-30). Rows kept beside every
  # term-sharing row (dropped_rows) change numpy's tie order too.
  EXTRA_ENV=(WP0_BEAR_LEGACY=tie_order,dropped_rows)
  step e2e_bm25_Ltie_dropped cpu v042L 0 0 -- "$PY" "$W/dump_toolbench_lists.py" --mode e2e       --backends bm25 --outdir results/wp0/lists_v042L_tie_dropped
  tb tb_bm25_Ltie_dropped cpu v042L 0 all "BEAR+BM25 (gov)" "BEAR+BM25 (mand-only)" "BM25 (no gov)"
  EXTRA_ENV=()
}
lane_manddense042() {  # after dense042 (one dense lane at a time): redo the cap kills, then the
  # dense mandatory diagnostic. Launched like dense042 (20G, batch 4, 12 threads).
  [[ ${WP0_ALLOW_LOCAL_MODELS:-0} == 1 ]] || { log "manddense042 needs WP0_ALLOW_LOCAL_MODELS=1"; return 1; }
  local sw ver sfx
  # decomposed_q4b was killed at the 20G cap (rc 143, oom-kill, 2026-10-30
  # 09:15): ITR's encoder evicted Qwen3-4B from the one-model share, so the
  # adversarial-safety part loaded a second 16 GB copy. Keep two models.
  for ver in v042 v0110; do
    sfx=""; [[ $ver == v0110 ]] && sfx=_v0110
    EXTRA_ENV=(WP0_SHARE_KEEP=2)
    step "decomposed_q4b$sfx" cpu $ver 0 0 -- "$PY" evals/eval_governance_decomposed.py --backends qwen3-4b
    EXTRA_ENV=()
  done
  for ver in v0110 v042; do
    step "diag_mand_dense_$ver" cpu $ver 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
        --backends bge bge-m3 qwen3 --out "results/wp0/diag_mandatory_dense_$ver.json"
    step "diag_mand_q4b_$ver" cpu $ver 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
        --backends qwen3-4b --out "results/wp0/diag_mandatory_q4b_$ver.json"
  done
  for sw in $SWITCHES_042; do
    EXTRA_ENV=(WP0_BEAR_LEGACY=$sw)
    step "diag_mand_dense_L$sw" cpu v042L 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
        --backends bge bge-m3 qwen3 --out "results/wp0/diag_mandatory_dense_v042_L$sw.json"
    step "diag_mand_q4b_L$sw" cpu v042L 0 0 -- "$PY" $W/diag_mandatory_petsim.py \
        --backends qwen3-4b --out "results/wp0/diag_mandatory_q4b_v042_L$sw.json"
  done
  EXTRA_ENV=()
}
lane_gpuq4b042() {  # Qwen3-4B on the GPU, bf16, once the coordinator gives the go
  # Launched (relaunch_042.sh gpuq4b042) with WP0_ALLOW_LOCAL_MODELS=1
  # WP0_STEP_MEM=12G WP0_ENCODE_BATCH=8 WP0_GPU_CAP_FIXED=11.2 (about 12 GB),
  # and the card gates agreed with model-server (2026-10-30):
  #   WP0_WIN_GPU_MAX_MIB=67000   gpu_gate.sh starts a step only if Windows
  #                               nvidia-smi shows 67,000 MiB or less
  #   WP0_WIN_GPU_STOP_MIB=80000  mem_guard.sh stops a step above 80,000 (rc 78),
  #                               and the lane then stops
  # gpu_gate.sh also refuses while the Ollama e2e rerun runs or its model is
  # loaded, so the two GPU jobs never overlap.
  [[ ${WP0_ALLOW_LOCAL_MODELS:-0} == 1 ]] || { log "gpuq4b042 needs WP0_ALLOW_LOCAL_MODELS=1"; return 1; }
  rm -f "$LOGS/.card_stop"
  local s
  for s in "tb tb_qwen4b gpu v042 11 all" "tb tb_qwen4b_v0110 gpu v0110 11 all" \
           "lists e2e_q4b_v042 gpu v042 11 e2e qwen3-4b" "lists e2e_q4b_v0110 gpu v0110 11 e2e qwen3-4b" \
           "lists wp4_tb_q4b gpu v042 11 toolbench qwen3-4b" "lists wp4_mt_q4b gpu v042 11 metatool-tags qwen3-4b"; do
    if [[ -f $LOGS/.card_stop ]]; then log "gpuq4b042 stopped: the card passed the stop limit"; return 1; fi
    if [[ $s == tb* ]]; then
      # shellcheck disable=SC2086
      $s "BEAR+Qwen3-4B (gov)" "Qwen3-4B (no gov)"
    else
      # shellcheck disable=SC2086
      $s
    fi
  done
}

lane=${1:-}
log "WP0 lane=$lane bear042=$BEAR042_SHA bear041=$BEAR041_SHA bear040=$BEAR040_SHA bear0110=$BEAR0110_SHA"
case $lane in
  gpu) lane_gpu ;;
  gpu2) lane_gpu2 ;;
  cpu1) lane_cpu1 ;;
  cpu2) lane_cpu2 ;;
  heavy) lane_heavy ;;
  attr) lane_attr ;;
  track) lane_track ;;
  nomodel) lane_nomodel ;;
  lex042) lane_lex042 ;;
  attrpet042) lane_attrpet042 ;;
  attrtb042) lane_attrtb042 ;;
  nemo042) lane_nemo042 ;;
  dense042) lane_dense042 ;;
  gpuq4b042) lane_gpuq4b042 ;;
  mand042) lane_mand042 ;;
  e2eattr042) lane_e2eattr042 ;;
  pair042) lane_pair042 ;;
  manddense042) lane_manddense042 ;;
  attrlex) lane_attrlex ;;
  tracklex) lane_tracklex ;;
  nemo) lane_nemo ;;
  *) echo "usage: $0 lex042|attrpet042|attrtb042|nemo042 (0.4.2), or the older lanes"; exit 2 ;;
esac
log "WP0 lane=$lane finished"
