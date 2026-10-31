#!/usr/bin/env bash
# 55_e2e_previous_version.sh: the scripts behind the results the revision keeps from
# the July and August 2026 runs (status "Scott, previous version" in MANIFEST.md).
# Scott made these runs then. They need no rerun for the revision. This script is
# here so that each of them can be run again by hand, on BEAR 0.1.10 as then.
#
# Parts (one per run, named on the command line):
#   table10-july        tab:e2e rows kept from July: BEAR+BGE, BEAR+Qwen3-0.6B,
#                       BEAR+Qwen3-4B (gov) and BGE, BGE-M3, Qwen3-0.6B, Qwen3-4B (no gov).
#                       evals/eval_toolbench_e2e.py --all --skip-monolithic.
#                       Runs every retrieval condition. The BM25 and BGE-M3 governed rows
#                       of this run are not the reported ones (50_ reruns them on 0.4.2).
#   table10-monolithic  tab:e2e monolithic row: all 3,225 tools in the prompt.
#                       eval_toolbench_e2e.py --backends none --monolithic-cap 0. Ollama
#                       must serve mistral-nemo with a 131,072-token window
#                       (OLLAMA_CONTEXT_LENGTH=131072, see the repo README, Serving the model).
#   table11-react       tab:e2e-react: eval_toolbench_react.py --monolithic-cap 0, same server.
#   table12-g12-scaffold, table12-g12-native, table12-g31-scaffold, table12-g31-native
#                       tab:e2e-scale, Gemma 4 12B and 31B (Ollama tags gemma4:12b and
#                       gemma4:31b): evals/run_model_scaffold_nothink.sh and
#                       evals/run_model_full1100.sh, temperature 1.0, top_p 0.95, top_k 64.
#                       Then evals/grid_from_full1100.py and evals/scaffold_vs_single.py.
#                       The reported 31B native cells were a pilot plus a complement
#                       (run_gemma_complement.sh, merge_gemma_full1100.py). table12-g31-native
#                       runs all 1,100 queries in one pass, the same query set.
#   tags-api            Appendix A inputs: evals/metatool_generate_tags.py and
#                       metatool_generate_query_tags_top5.py through the Anthropic API
#                       (claude-sonnet-4-6, temperature 0). Paid, and a model answer can
#                       differ from June's. It writes new tag files in the clone only.
# BEAR: v0.1.10 from ~/tist-evals/bear-v0110 on PYTHONPATH, as in July.
# Prerequisites: 00_setup.sh. Ollama at 127.0.0.1:11434 with the model the part needs.
#   The model-server session agreed to the window. wsl-keepalive is Running. tags-api
#   needs ANTHROPIC_API_KEY in the environment.
# Resources: the GPU through Ollama (Mistral-Nemo 12B Q4_0 about 12 GB at 32k, much more
#   at 131k, Gemma 4 31B more again). The client hides CUDA, so its BGE and Qwen
#   embedders run on the CPU and never load onto the card ungated. Client memory cap
#   16G. ~/tist-gpu.lock is held for the whole part.
# Time: table10-july about 4 h, monolithic about 6 h, react about 8 h, each Gemma part
#   4 to 9 h, tags-api under 1 h.
# Outputs: the clone $REPRO_OUT/clones/artifacts-previous, then a copy of every file the
#   part changed in $REPRO_OUT/previous/<part>/ (repo layout).
#
# Usage:
#   bash reproduce/55_e2e_previous_version.sh PART [--dry-run] [--wait]
#   bash reproduce/55_e2e_previous_version.sh --list
# Without --dry-run it starts the user service tist-repro-55 and returns.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

PARTS="table10-july table10-monolithic table11-react table12-g12-scaffold table12-g12-native table12-g31-scaffold table12-g31-native tags-api"
PART=""
for a in "${ARGS_REST[@]}"; do
  case $a in
    --list) trap - EXIT; echo "$PARTS" | tr ' ' '\n'; exit 0 ;;
    -*) die "unknown option $a (see --help)" ;;
    *) [ -z "$PART" ] || die "one part at a time"; PART=$a ;;
  esac
done
[ -n "$PART" ] || die "name a part: $PARTS"
[[ " $PARTS " == *" $PART "* ]] || die "unknown part $PART. Parts: $PARTS"

BASE_URL=$REPRO_OLLAMA_ROOT/v1
case $PART in
  table10-july)       NEED_MODEL=${PREV_E2E_MODEL:-mistral-nemo-32k} ;;
  table10-monolithic|table11-react) NEED_MODEL=${PREV_MONO_MODEL:-mistral-nemo} ;;
  table12-g12-*)      NEED_MODEL=gemma4:12b ;;
  table12-g31-*)      NEED_MODEL=gemma4:31b ;;
  tags-api)           NEED_MODEL="" ;;
esac

preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_bear0110
  check_clone "$PREV_CLONE"
  if [ "$PART" = tags-api ]; then
    [ -n "${ANTHROPIC_API_KEY:-}" ] || die "tags-api needs ANTHROPIC_API_KEY"
  else
    check_no_gpu_jobs
    check_card_start
    check_ollama_idle
  fi
}
maybe_launch tist-repro-55
repro_begin
say "part $PART, BEAR 0.1.10 from $BEAR0110_SRC, model ${NEED_MODEL:-none}"
if [ "$DRY_RUN" = 0 ]; then
  preflight_launch
  [ -n "$NEED_MODEL" ] && python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name ollama \
    --url "$REPRO_OLLAMA_ROOT" >/dev/null 2>&1
fi

# BEAR 0.1.10 first on the path, the kit's venv for everything else (as the
# 0.1.10 control steps of the WP0 lanes run it).
P010=(env CUDA_VISIBLE_DEVICES= PYTHONPATH="$BEAR0110_SRC" BEAR_SOURCE_SHA="$BEAR0110_SHA" BASE_URL="$BASE_URL")
LOCKED=(flock "$GPU_LOCK" "$TC" --mem 16G --)
case $PART in
  table10-july)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" python evals/eval_toolbench_e2e.py --all \
      --skip-monolithic --base-url "$BASE_URL" --model "$NEED_MODEL" ;;
  table10-monolithic)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" python evals/eval_toolbench_e2e.py --backends none \
      --monolithic-cap 0 --base-url "$BASE_URL" --model "$NEED_MODEL" ;;
  table11-react)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" python evals/eval_toolbench_react.py \
      --monolithic-cap 0 --base-url "$BASE_URL" --model "$NEED_MODEL" ;;
  table12-g12-scaffold)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" MODEL=gemma4:12b LABEL=g4-12b bash evals/run_model_scaffold_nothink.sh
    rstep "$PART-analysis" -C "$PREV_CLONE" -- "${P010[@]}" python evals/scaffold_vs_single.py g4-12b ;;
  table12-g12-native)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" MODEL=gemma4:12b LABEL=g4-12b bash evals/run_model_full1100.sh
    rstep "$PART-analysis" -C "$PREV_CLONE" -- "${P010[@]}" python evals/grid_from_full1100.py g4-12b ;;
  table12-g31-scaffold)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_scaffold_nothink.sh
    rstep "$PART-analysis" -C "$PREV_CLONE" -- "${P010[@]}" python evals/scaffold_vs_single.py g4-31b ;;
  table12-g31-native)
    rstep "$PART" -C "$PREV_CLONE" -- "${LOCKED[@]}" "${P010[@]}" MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_full1100.sh
    rstep "$PART-analysis" -C "$PREV_CLONE" -- "${P010[@]}" python evals/grid_from_full1100.py g4-31b ;;
  tags-api)
    rstep "$PART-tools" -C "$PREV_CLONE" -- "$TC" --mem 4G -- "${P010[@]}" python evals/metatool_generate_tags.py
    rstep "$PART-queries" -C "$PREV_CLONE" -- "$TC" --mem 4G -- "${P010[@]}" python evals/metatool_generate_query_tags_top5.py ;;
esac

# Keep a copy of what this part changed, so a later part cannot overwrite it.
if [ "$DRY_RUN" = 0 ]; then
  dest=$REPRO_OUT/previous/$PART
  mkdir -p "$dest"
  n=0
  while IFS= read -r rel; do
    [ -f "$PREV_CLONE/$rel" ] || continue
    mkdir -p "$dest/$(dirname "$rel")"
    cp -p "$PREV_CLONE/$rel" "$dest/$rel"
    n=$((n + 1))
  done < <(cd "$PREV_CLONE" && { git ls-files -m -- results evals/results evals/data; \
           git ls-files --others --exclude-standard -- results evals/results evals/data; } | sort -u)
  say "copied $n changed file(s) to $dest"
  record_note "outputs of $PART copied to $dest ($n files)"
else
  echo "+ (copy every file the part changed under results/, evals/results/, evals/data/ to $REPRO_OUT/previous/$PART/)"
fi
REPRO_OK_NOTE="part $PART done"
