#!/usr/bin/env bash
# 65_authorship.sh: the authorship ablation (WP6). Do the paper's results depend on the tagger?
#
# Claude Sonnet 4.6 wrote three sets of metadata: the MetaTool tool tags, the MetaTool
# top-5 query tags, and the inferred ToolBench categories (top-1, multi, top-5). This
# writes them again with a second model family, Qwen3.8-27B on SGLang (127.0.0.1:8355),
# through the same code, prompts, closed vocabulary, parsing, retries and validation,
# then reruns the tables that use them and compares the two taggers. Design and
# decisions: evals/authorship/README.md.
#
# Parts, one per run, in this order (each needs one kind of resource):
#   tag       8355. evals/authorship/tag.py generate (the five tag sets, a call log with
#             every raw reply, the server's identity), then evals/authorship/validate.py
#             (the originals' validation on every reply, every failure and fallback
#             counted). Fails if a target loses more than AUTH_MAX_MISSING of its items.
#   cpu       CPU. MetaTool+Tags and MetaTool+QueryTags-top5 with the new tags, governed
#             and ungated, for BM25, hash (no model, 8G) and BGE, BGE-M3, Qwen3-0.6B (as
#             lane dense042: 20G, batch 4, 12 threads), steps tb_auth_<backend> through
#             evals/authorship/eval_tagged.py. Then Table 7 (ToolBench inferred
#             categories, BGE) under both taggers: authorship_regenerate.py evaluate.
#             --backends picks a subset.
#   gpu       local GPU. The same two conditions for Qwen3-4B (bf16, encode batch
#             AUTH_Q4B_BATCH, default 2, allocator cap 11.2 GiB, gates 67,000 and 80,000
#             MiB): tb_auth_q4b with the new tags, and tb_auth_q4b_sonnet with the Sonnet
#             tags at the same batch, so the pair differs only in the tags (the reported
#             tb_qwen4b rows ran at batch 8). --no-sonnet-arm skips the second step.
#   nemotron  8360. The same two conditions for Nemotron (tb_auth_nemotron).
#   analyze   CPU. evals/authorship/analyze.py: tagger agreement (Jaccard, exact sets,
#             Cohen's kappa per tag, category agreement, the gate-pass ceiling) and, per
#             backend, governed Recall@5 and NDCG@5 under each tagger, the paired
#             difference, the governed-minus-ungated effect under each tagger and the
#             difference of the effects, with 95% CIs and tests.
#   test      CPU. The offline tests (canned replies, malformed ones included).
# The Sonnet side of every comparison is the WP0 run of 10_, 20_ and 30_ (steps tb_bge,
# tb_bm25, ...), so run those first.
# Prerequisites: 00_setup.sh (it makes the clone artifacts-authorship). For tag: SGLang
#   on 8355 with nothing queued, no WP7 grid running, and the model-server session's OK.
#   For gpu and nemotron: the same windows as 20_ and 30_. wsl-keepalive is Running.
#   No Anthropic or other paid API is called: the shim refuses every host but --base-url.
# Resources and time (estimates from the item counts and the October timings):
#   tag       8355, at most AUTH_WORKERS (default 4) of the server's 8 slots. 199 tools,
#             21,111 queries, 3 x 1,100 ToolBench queries (sequential, as the originals).
#             About 3 to 5 hours. 8G host memory.
#   cpu       BM25 and hash a few minutes each, BGE about 30 min, BGE-M3 about 1.5 h,
#             Qwen3-0.6B about 2.5 h, Table 7 about 20 min. About 5 hours in all.
#   gpu       about 30 to 40 minutes of card time for both steps.
#   nemotron  about 30 to 45 minutes.
#   analyze   about 15 minutes.
# Outputs: $REPRO_OUT/authorship/ (tags/ with the five files, calls.jsonl, manifest.json
#   and validation.json, evaluate_toolbench_bge.json, analysis/), and the tb_auth_* steps
#   in $REPRO_OUT/wp0/stage/v042/. 70_assemble.sh gathers them.
#
# Usage:
#   bash reproduce/65_authorship.sh --part tag|cpu|gpu|nemotron|analyze|test [--dry-run] [--wait]
#                                   [--backends "bm25 hash bge bge-m3 qwen3-0.6b"] [--no-sonnet-arm]
# Without --dry-run the parts tag, cpu, gpu and nemotron start the user service
# tist-repro-65 and return. analyze and test run in the terminal.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/wp0.sh"
repro_parse_args "$@"

AUTH=$REPRO_OUT/authorship
TAGS=$AUTH/tags
AUTH_CLONE=$CLONES/artifacts-authorship
AUTH_WORKERS=${AUTH_WORKERS:-4}
AUTH_SEED=${AUTH_SEED:-20261104}            # -1 sends no seed, if the server rejects the field
AUTH_MAX_MISSING=${AUTH_MAX_MISSING:-0.01}
export KIT_Q4B_BATCH=${AUTH_Q4B_BATCH:-2}
PART="" CPU_BACKENDS="bm25 hash bge bge-m3 qwen3-0.6b" SONNET_ARM=1
set -- "${ARGS_REST[@]}"
while [ $# -gt 0 ]; do
  case $1 in
    --part) PART=$2; shift ;;
    --backends) CPU_BACKENDS=$2; shift ;;
    --no-sonnet-arm) SONNET_ARM=0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done
case $PART in
  tag|cpu|gpu|nemotron|analyze|test) ;;
  "") die "name a part with --part: tag, cpu, gpu, nemotron, analyze or test" ;;
  *) die "unknown part $PART" ;;
esac

# backend -> label in the eval's experiment names, step suffix, kind of step
backend_row() {
  case $1 in
    bm25) echo "BM25 bm25 lex" ;;
    hash) echo "Hash hash lex" ;;
    bge) echo "BGE bge dense" ;;
    bge-m3) echo "BGE-M3 bgem3 dense" ;;
    qwen3-0.6b) echo "Qwen3-0.6B qwen06 dense" ;;
    *) return 1 ;;
  esac
}

tagged_step() {  # tagged_step KIND STEP LABEL TOOL_TAGS QUERY_TAGS
  local kind=$1 step=$2 label=$3 tt=$4 qt=$5
  kit_tb_step "$kind" "$step" "$AUTH_CLONE" -- "$REPRO_PY" evals/authorship/eval_tagged.py \
    --tool-tags "$tt" --query-tags "$qt" --backends "BEAR+$label (gov)" "$label (no gov)" \
    --output "results/wp0/toolbench_eval_$step.json"
}

need_tags() {
  [ "$DRY_RUN" = 1 ] && return 0
  local f
  for f in plugin_tags.json query_tags_top5.json; do
    [ -s "$TAGS/$f" ] || die "no $TAGS/$f. Run --part tag first."
  done
  [ -s "$TAGS/validation.json" ] || die "no $TAGS/validation.json. The tag part did not finish."
}

preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_clone "$AUTH_CLONE"
  [ -f "$AUTH_CLONE/evals/authorship/tag.py" ] || die "$AUTH_CLONE has no evals/authorship (run 00_setup.sh --update)"
  case $PART in
    tag|gpu|nemotron) check_no_gpu_jobs ;;
  esac
  case $PART in
    cpu|gpu|nemotron) need_tags ;;
  esac
  case $PART in
    cpu) check_hf_models BAAI/bge-base-en-v1.5 BAAI/bge-m3 Qwen/Qwen3-Embedding-0.6B ;;
    gpu) check_hf_models Qwen/Qwen3-Embedding-4B; check_card_start; check_ollama_idle ;;
  esac
}

case $PART in
  tag|cpu|gpu|nemotron) maybe_launch tist-repro-65 ;;
esac
repro_begin
say "authorship ablation, part $PART, outputs in $AUTH"
[ "$DRY_RUN" = 1 ] || preflight_launch
export CUDA_VISIBLE_DEVICES=

case $PART in
  tag)
    if [ "$DRY_RUN" = 0 ]; then
      http_get "$REPRO_SGLANG_URL/get_server_info" >/dev/null || die "no answer from SGLang at $REPRO_SGLANG_URL"
      python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name sglang --url "$REPRO_SGLANG_URL" >/dev/null 2>&1
      mkdir -p "$TAGS"
    else
      echo "+ (check: GET $REPRO_SGLANG_URL/get_server_info answers. tag.py then reads the queue and refuses if it is not empty)"
    fi
    resume=()
    [ -n "$(ls "$TAGS"/*.json 2>/dev/null)" ] && resume=(--resume)
    if [ "$DRY_RUN" = 1 ] && [ -f "$AUTH_CLONE/evals/authorship/tag.py" ] && [ -x "$REPRO_PY" ]; then
      # tag.py's own dry run: one translated request per target, answered by a
      # canned reply inside the process. Nothing leaves the machine.
      say "tag.py --dry-run (canned replies, sends nothing):"
      (cd "$AUTH_CLONE" && "$REPRO_PY" evals/authorship/tag.py generate --dry-run --workers "$AUTH_WORKERS" \
         --seed "$AUTH_SEED" 2>&1 | tail -n 25) || die "tag.py --dry-run failed"
    fi
    rstep auth-tag -C "$AUTH_CLONE" -- capped 8G -- "$REPRO_PY" evals/authorship/tag.py generate \
      --base-url "$REPRO_SGLANG_URL/v1" --out-dir "$TAGS" --workers "$AUTH_WORKERS" --passes 3 \
      --seed "$AUTH_SEED" "${resume[@]}"
    rstep auth-validate -C "$AUTH_CLONE" -- capped 8G -- "$REPRO_PY" evals/authorship/validate.py \
      --tags-dir "$TAGS" --max-missing-frac "$AUTH_MAX_MISSING"
    REPRO_OK_NOTE="tags written and validated in $TAGS. Tell the model-server session 8355 is free"
    ;;
  cpu)
    for b in $CPU_BACKENDS; do
      row=$(backend_row "$b") || die "unknown backend $b (bm25 hash bge bge-m3 qwen3-0.6b)"
      read -r label slug kind <<<"$row"
      hr
      tagged_step "$kind" "tb_auth_$slug" "$label" "$TAGS/plugin_tags.json" "$TAGS/query_tags_top5.json"
    done
    hr
    # Table 7 reports BGE only. The three ToolBench caches in a folder of their own,
    # so evaluate runs the ToolBench conditions and nothing else.
    if [ "$DRY_RUN" = 0 ]; then
      mkdir -p "$AUTH/toolbench_only"
      cp -p "$TAGS"/toolbench_*_categories.json "$AUTH/toolbench_only/" || die "no ToolBench category files in $TAGS"
    else
      echo "+ cp $TAGS/toolbench_*_categories.json $AUTH/toolbench_only/"
    fi
    rstep auth-toolbench-bge -C "$AUTH_CLONE" -- capped 20G -- env OMP_NUM_THREADS=12 MKL_NUM_THREADS=12 \
      "$REPRO_PY" evals/authorship_regenerate.py evaluate --regen-dir "$AUTH/toolbench_only" --backend bge \
      --output "$AUTH/evaluate_toolbench_bge.json"
    REPRO_OK_NOTE="CPU backends done: $CPU_BACKENDS, and Table 7 under both taggers"
    ;;
  gpu)
    tagged_step gpu tb_auth_q4b Qwen3-4B "$TAGS/plugin_tags.json" "$TAGS/query_tags_top5.json"
    if [ "$SONNET_ARM" = 1 ]; then
      hr
      tagged_step gpu tb_auth_q4b_sonnet Qwen3-4B "$AUTH_CLONE/evals/data/external_benchmarks/metatool/plugin_tags.json" \
        "$AUTH_CLONE/evals/data/external_benchmarks/metatool/query_tags_top5.json"
    fi
    [ "$DRY_RUN" = 1 ] || say "card after the run: $(card_mib) MiB"
    REPRO_OK_NOTE="Qwen3-4B done at encode batch $KIT_Q4B_BATCH. Tell the model-server session the GPU is free"
    ;;
  nemotron)
    check_nemotron
    tagged_step remote tb_auth_nemotron Nemotron "$TAGS/plugin_tags.json" "$TAGS/query_tags_top5.json"
    REPRO_OK_NOTE="Nemotron done"
    ;;
  analyze)
    run_cmd auth-analyze -C "$AUTH_CLONE" -- capped 8G -- "$REPRO_PY" evals/authorship/analyze.py \
      --qwen-tags "$TAGS" --runs-root "$WP0_DIR/stage/v042" --out "$AUTH/analysis" \
      --toolbench-eval "$AUTH/evaluate_toolbench_bge.json" || die "analyze.py failed"
    [ "$DRY_RUN" = 1 ] || cat "$AUTH/analysis/authorship.md"
    REPRO_OK_NOTE="analysis in $AUTH/analysis/authorship.md"
    ;;
  test)
    run_cmd auth-tests -C "$AUTH_CLONE" -- capped 4G -- "$REPRO_PY" -m unittest discover -s evals/authorship/tests -v \
      || die "the offline tests failed"
    REPRO_OK_NOTE="offline tests passed"
    ;;
esac
