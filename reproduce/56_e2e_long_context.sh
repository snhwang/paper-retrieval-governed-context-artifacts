#!/usr/bin/env bash
# 56_e2e_long_context.sh: the Ollama tags and the load measurements that the long-context
# end-to-end reruns need (parts 2 to 4 of evals/e2e_rerun/PLAN.md).
#
# Reproduces: no number of the paper. It prepares the reruns of the Table 10 monolithic row,
#   the ReAct scaffold and the Gemma 4 runs of Supplement Table S1, whose prompts hold all
#   3,225 tools.
# Why: the Ollama server defaults to a window of 262,144 tokens. With that window the larger
#   models do not fit on the card. A tag that only adds num_ctx bounds the key-value cache.
#   Ollama cuts a prompt that is longer than the window without failing, so the prompt is
#   counted with the model's own tokenizer before any run is booked.
#
# Parts (one per call):
#   tag-g12, tag-g31, tag-nemo
#       Make the fixed-window tag with the Windows Ollama program:
#         gemma4-12b-131k    from gemma4:12b    (digest 4eb23ef187e2), num_ctx 131072
#         gemma4-31b-131k    from gemma4:31b    (digest 6316f0629137), num_ctx 131072
#         mistral-nemo-131k  from mistral-nemo  (digest e7e06d107c6c), num_ctx 131072
#       The Modelfiles are evals/e2e_rerun/Modelfile.<tag>. A tag adds no weights. The base
#       tags are never removed and never pulled again. No GPU.
#   measure-g12, measure-g31, measure-nemo
#       One guarded load of the tag (evals/e2e_rerun/measure_load.py): what Ollama loaded, the
#       card before and after, the server's own count of the monolithic prompt, and any
#       "truncating input prompt" line in the Ollama log. The tag is unloaded at the end.
# Prerequisites: 00_setup.sh. Ollama on Windows at 127.0.0.1:11434 holds the base tag with
#   the digest above. For a measure part: the tag part ran, Ollama holds no model, no other
#   GPU job runs, the card is at or below the start limit, wsl-keepalive is Running.
#   measure-g12 fits beside the Qwen3.8 server (gpumem:16). measure-g31 and measure-nemo need
#   that server stopped, in a window booked through the model-server session.
# Resources: tag parts, CPU only. Measure parts, the GPU through Ollama for a few minutes
#   (model-server's estimates at 131,072: 12B 10 to 13 GiB, 31B 30 to 32 GiB, Mistral-Nemo
#   27.5 GiB). Client memory cap 6G. ~/tist-gpu.lock is held during a measure part.
# Time: a tag part under a minute. A measure part 5 to 20 minutes.
# Outputs: $REPRO_OUT/e2e_long/<part>/ (measure.json, UNLOADED), and notes in the run record.
#
# Usage:
#   bash reproduce/56_e2e_long_context.sh PART [--dry-run] [--wait]
#   bash reproduce/56_e2e_long_context.sh --list
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

PARTS="tag-g12 tag-g31 tag-nemo measure-g12 measure-g31 measure-nemo"
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

CTX=131072
case ${PART#*-} in
  g12)  BASE=gemma4:12b   BASE_DIGEST=4eb23ef187e2 TAG=gemma4-12b-131k ;;
  g31)  BASE=gemma4:31b   BASE_DIGEST=6316f0629137 TAG=gemma4-31b-131k ;;
  nemo) BASE=mistral-nemo BASE_DIGEST=e7e06d107c6c TAG=mistral-nemo-131k ;;
esac
KIND=${PART%%-*}
MODELFILE=evals/e2e_rerun/Modelfile.$TAG
OUT=$REPRO_OUT/e2e_long/$PART
ART0=$WP0_DIR/artifacts

tag_digest() {  # tag_digest NAME: the 12-hex digest Ollama lists for NAME, or nothing
  http_get "$REPRO_OLLAMA_ROOT/api/tags" | python3 -c '
import json, sys
want = sys.argv[1]
for m in json.load(sys.stdin).get("models", []):
    if m.get("name") in (want, want + ":latest"):
        print(m.get("digest", "")[:12])
        break
' "$1"
}
check_base() {  # the base tag is the build the plan names
  local d
  d=$(tag_digest "$BASE") || die "no answer from Ollama at $REPRO_OLLAMA_ROOT"
  [ "$d" = "$BASE_DIGEST" ] || die "Ollama lists $BASE with digest ${d:-none}, and the plan names $BASE_DIGEST. Do not pull $BASE again. Ask before going on."
}
find_ollama_exe() {
  command -v ollama.exe 2>/dev/null && return 0
  ls /mnt/c/Users/*/AppData/Local/Programs/Ollama/ollama.exe 2>/dev/null | head -1
}

preflight_launch() {
  check_tc
  check_venv
  check_clone "$ART0"
  [ -f "$ART/$MODELFILE" ] || die "missing $ART/$MODELFILE"
  check_base
  if [ "$KIND" = measure ]; then
    check_slice
    check_keepalive
    [ -n "$(tag_digest "$TAG")" ] || die "Ollama has no tag $TAG. Run: bash reproduce/56_e2e_long_context.sh tag-${PART#*-}"
    check_no_gpu_jobs
    check_card_start
    check_ollama_idle
  fi
}
maybe_launch tist-repro-56
repro_begin
say "part $PART: $TAG from $BASE ($BASE_DIGEST), window $CTX"
if [ "$DRY_RUN" = 0 ]; then
  preflight_launch
  python3 "$REPRO_DIR/lib/run_record.py" endpoint "$REPRO_RECORD" --name ollama --url "$REPRO_OLLAMA_ROOT" >/dev/null 2>&1
else
  echo "+ (check: Ollama lists $BASE with digest $BASE_DIGEST)"
  [ "$KIND" = measure ] && { check_card_start; check_ollama_idle; echo "+ (check: Ollama lists $TAG)"; }
fi

hr
if [ "$KIND" = tag ]; then
  # The Windows program reads the Modelfile, so it runs from the checkout on the Windows drive.
  OLLAMA_EXE=$(find_ollama_exe)
  [ -n "$OLLAMA_EXE" ] || [ "$DRY_RUN" = 1 ] || die "ollama.exe not found from WSL. In PowerShell, in this repo: ollama create $TAG -f $MODELFILE"
  rstep "$PART" -C "$ART" -- "${OLLAMA_EXE:-ollama.exe}" create "$TAG" -f "$MODELFILE"
  if [ "$DRY_RUN" = 0 ]; then
    d=$(tag_digest "$TAG")
    [ -n "$d" ] || die "Ollama does not list $TAG after the create"
    record_note "tag $TAG made from $BASE ($BASE_DIGEST) with $MODELFILE ($(tr '\n' ' ' < "$ART/$MODELFILE")). Its digest is $d"
    REPRO_OK_NOTE="tag $TAG, digest $d"
  fi
else
  mkdir -p "$OUT" 2>/dev/null || true
  rstep "$PART" -C "$ART0" -- flock "$GPU_LOCK" "$TC" --mem 6G -- env CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 WP0_NO_LOCAL_MODELS=1 PYTHONUNBUFFERED=1 PYTHONPATH=evals/wp0_v040/site \
    "$REPRO_PY" evals/e2e_rerun/measure_load.py --model "$TAG" --base "$BASE" --expect-base-digest "$BASE_DIGEST" \
    --expect-ctx "$CTX" --base-url "$REPRO_OLLAMA_ROOT/v1" --win-gpu-max-mib "$GPU_START_MIB" \
    --win-gpu-stop-mib "$GPU_STOP_MIB" --out "$OUT"
  if [ "$DRY_RUN" = 0 ]; then
    [ -f "$OUT/UNLOADED" ] || die "the tag was not confirmed unloaded ($OUT/UNLOADED missing). Check Ollama with: curl -s $REPRO_OLLAMA_ROOT/api/ps"
    record_note "measure $TAG: $(python3 -c '
import json, sys
r = json.load(open(sys.argv[1]))
c, p = r.get("card_mib", {}), r.get("prompt", {})
print("card before %s, after load %s, after prompt %s, after unload %s MiB. Prompt %s tokens by the server (%s cl100k). Cut lines %s" % (
    c.get("before"), c.get("after_load"), c.get("after_prompt"), c.get("after_unload"), p.get("prompt_tokens"), p.get("cl100k"), r.get("cut_lines_since_start")))
' "$OUT/measure.json")"
    say "card after the run: $(card_mib) MiB"
    REPRO_OK_NOTE="measured $TAG, model unloaded. Send $OUT/measure.json to the model-server session"
  fi
fi
