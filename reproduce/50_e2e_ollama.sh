#!/usr/bin/env bash
# 50_e2e_ollama.sh: the Table 10 (tab:e2e) rows rerun on BEAR 0.4.2's top-5 lists.
#
# Reproduces (full map in reproduce/MANIFEST.md):
#   tab:e2e rows BEAR+BM25 (gov), BM25 (no gov), BEAR+BGE-M3 (gov), whose lists changed
#   under 0.4.2, and the two executor-drift controls BEAR+BGE (gov), BGE (no gov), whose
#   lists did not. 5 x 1,100 calls. Also the governed vs ungated tests of the caption.
#   The other Table 10 rows, tab:e2e-react and tab:e2e-scale keep the previous
#   version's runs (55_e2e_previous_version.sh holds their scripts).
#   With --all-rows: all ten retrieval rows of tab:e2e in one session (BGE, BGE-M3,
#   Qwen3-0.6B, Qwen3-4B and BM25, governed and ungoverned), 10 x 1,100 calls, into a
#   folder of its own. This is part 1 of evals/e2e_rerun/PLAN.md. It also needs the
#   Qwen3-4B lists of 20_gpu_local_embeddings.sh.
# How: evals/wp0_v040/run_wp0_v040.sh's companion evals/wp0_v040/run_e2e_rerun.sh
#   mistral-nemo, which runs e2e_rerun.py with --verify-live (BM25 and hash lists are
#   rebuilt and must match), then evals/wp0_v040/e2e_rerun_report.py.
# Prerequisites: 10_ finished (lists from lanes lex042 and dense042). Ollama on
#   Windows at 127.0.0.1:11434 (WSL mirrored networking) holds the tag
#   mistral-nemo-32k (digest d79a1e80980f, GGUF layer b559938ab7a0, Q4_0, num_ctx
#   32768). Make it once in PowerShell, in this repo: ollama create mistral-nemo-32k -f Modelfile
#   e2e_rerun.py checks the GGUF layer in Ollama's manifest. It finds the models folder
#   through OLLAMA_MODELS, or else the Windows profile (cmd.exe and wslpath).
#   The model-server session agreed to the window, the card shows 67,000 MiB or less,
#   Ollama holds no model, no other GPU job runs, wsl-keepalive is Running.
# Resources: the GPU through Ollama (about 12 GB with the model loaded). Card limits:
#   67,000 MiB before loading, 81,000 MiB before each row. Client memory cap 4G.
#   ~/tist-gpu.lock is held for the whole run. The model is unloaded at the end.
# Time: about 30 to 40 minutes.
# Outputs: $REPRO_OUT/e2e_rerun/mistral-nemo/ (per-row .jsonl and .scores.json,
#   rerun_summary.json, UNLOADED), $REPRO_OUT/e2e_rerun/report.md, the log
#   $REPRO_OUT/wp0/logs/e2e_rerun_mistral-nemo.log.
#
# Usage:
#   bash reproduce/50_e2e_ollama.sh [--all-rows] [--dry-run] [--wait]
# Without --dry-run it starts the user service tist-repro-50 and returns.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"
ALL_ROWS=0
for a in "${ARGS_REST[@]}"; do
  case $a in
    --all-rows) ALL_ROWS=1 ;;
    *) die "unknown option $a (see --help)" ;;
  esac
done

MODEL=mistral-nemo-32k
DIGEST=d79a1e80980f
OUT=$REPRO_OUT/e2e_rerun
ART0=$WP0_DIR/artifacts
LISTS_LEX=$WP0_DIR/artifacts/results/wp0/lists_v042/e2e
LISTS_DENSE=$WP0_DIR/artifacts-dense/results/wp0/lists_v042/e2e
LISTS_GPU=$WP0_DIR/artifacts-gpu/results/wp0/lists_v042/e2e
ROW_SLUGS="bear_bm25_gov bm25_no_gov bear_bge-m3_gov bear_bge_gov bge_no_gov"
STEP_RUN=e2e-rerun STEP_REPORT=e2e-report
ROWS_ENV=()
if [ "$ALL_ROWS" = 1 ]; then
  # Every row again, in one session and one folder, so that no row of the table rests on another run.
  OUT=$REPRO_OUT/e2e_rerun_all
  ROW_SLUGS="bear_bm25_gov bm25_no_gov bear_bge-m3_gov bge-m3_no_gov bear_bge_gov bge_no_gov bear_qwen3-0.6b_gov qwen3-0.6b_no_gov bear_qwen3-4b_gov qwen3-4b_no_gov"
  STEP_RUN=e2e-rerun-all STEP_REPORT=e2e-report-all
  ROWS_ENV=(WP0_E2E_ROWS="BEAR+BM25 (gov);BM25 (no gov);BEAR+BGE-M3 (gov);BGE-M3 (no gov);BEAR+BGE (gov);BGE (no gov);BEAR+Qwen3-0.6B (gov);Qwen3-0.6B (no gov);BEAR+Qwen3-4B (gov);Qwen3-4B (no gov)")
fi
N_ROWS=$(echo $ROW_SLUGS | wc -w)

check_tag() {  # the executor tag exists with the expected digest
  local tags
  tags=$(http_get "$REPRO_OLLAMA_ROOT/api/tags") || die "no answer from Ollama at $REPRO_OLLAMA_ROOT"
  python3 -c '
import json, sys
model, digest = sys.argv[1], sys.argv[2]
tags = json.load(sys.stdin).get("models", [])
ok = [m for m in tags if m.get("name", "").split(":")[0] == model and m.get("digest", "").startswith(digest)]
sys.exit(0 if ok else 1)
' "$MODEL" "$DIGEST" <<<"$tags"     || die "Ollama has no tag $MODEL with digest $DIGEST. In PowerShell, in this repo: ollama create $MODEL -f Modelfile"
}

preflight_launch() {
  check_tc
  check_slice
  check_keepalive
  check_venv
  check_clone "$ART0"
  local f
  for f in "$LISTS_LEX/bear_bm25_gov.json" "$LISTS_LEX/bm25_no_gov.json" "$LISTS_DENSE/bear_bge_m3_gov.json" \
           "$LISTS_DENSE/bear_bge_gov.json" "$LISTS_DENSE/bge_no_gov.json"; do
    [ -s "$f" ] || die "missing list $f. Run 10_cpu_retrieval.sh (lanes lex042 and dense042) first."
  done
  if [ "$ALL_ROWS" = 1 ]; then
    for f in "$LISTS_DENSE/bge_m3_no_gov.json" "$LISTS_DENSE/bear_qwen3_0_6b_gov.json" "$LISTS_DENSE/qwen3_0_6b_no_gov.json" \
             "$LISTS_GPU/bear_qwen3_4b_gov.json" "$LISTS_GPU/qwen3_4b_no_gov.json"; do
      [ -s "$f" ] || die "missing list $f. Run 10_cpu_retrieval.sh and 20_gpu_local_embeddings.sh first."
    done
  fi
  check_no_gpu_jobs
  check_card_start
  check_ollama_idle
  check_tag
}
maybe_launch tist-repro-50
repro_begin
say "preflight"
if [ "$DRY_RUN" = 0 ]; then
  preflight_launch
  python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name ollama --url "$REPRO_OLLAMA_ROOT" >/dev/null 2>&1
else
  check_card_start
  check_ollama_idle
  echo "+ (check: Ollama lists $MODEL with digest $DIGEST)"
fi
[ -d "$OUT/mistral-nemo" ] && [ -n "$(ls "$OUT"/mistral-nemo/*.done 2>/dev/null)" ] \
  && say "rows already done in $OUT/mistral-nemo are skipped: $(cd "$OUT/mistral-nemo" && ls ./*.done | tr '\n' ' ')"

hr
# run_e2e_rerun.sh writes to WP0_E2E_OUT. Its default is the clone's
# results/v042/e2e_rerun, which holds the committed rows and their .done files,
# so it would skip every row. The kit always points it at a fresh folder.
rstep "$STEP_RUN" -C "$ART0" -- env WP0_ROOT="$WP0_DIR" WP0_ART="$ART0" WP0_PY="$REPRO_PY" WP0_E2E_OUT="$OUT" "${ROWS_ENV[@]}" \
  WP0_WIN_GPU_MAX_MIB="$GPU_START_MIB" WP0_WIN_GPU_ROW_MAX_MIB="$OLLAMA_ROW_MIB" \
  WP0_OLLAMA_URL="$REPRO_OLLAMA_ROOT/v1" WP0_E2E_MODEL="$MODEL" WP0_E2E_DIGEST="$DIGEST" \
  bash evals/wp0_v040/run_e2e_rerun.sh mistral-nemo

if [ "$DRY_RUN" = 0 ]; then
  [ -f "$OUT/mistral-nemo/UNLOADED" ] || die "the executor did not confirm the unload ($OUT/mistral-nemo/UNLOADED missing). Check Ollama with: curl -s $REPRO_OLLAMA_ROOT/api/ps"
  for r in $ROW_SLUGS; do
    [ -f "$OUT/mistral-nemo/$r.done" ] || die "row $r has no .done file"
  done
  say "card after the run: $(card_mib) MiB"
fi
step_done "$STEP_REPORT" || { [ "$DRY_RUN" = 1 ] || rm -f "$OUT/report.md"; }
rstep "$STEP_REPORT" -C "$ART0" -o "$OUT/report.md" -- "$REPRO_PY" evals/wp0_v040/e2e_rerun_report.py \
  "$OUT/mistral-nemo" evals/results/toolbench_e2e_scores.json evals/results/toolbench_e2e_results.json
[ "$DRY_RUN" = 1 ] || cat "$OUT/report.md"

REPRO_OK_NOTE="$N_ROWS rows done, model unloaded. Tell the model-server session the GPU is free"
