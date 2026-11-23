#!/usr/bin/env bash
# 56_e2e_long_context.sh: the long-context end-to-end reruns (parts 2 to 4 of
# evals/e2e_rerun/PLAN.md), with the Ollama tags and the load measurements they need.
#
# Reproduces: with its run parts, the Table 10 monolithic row, the ReAct scaffold on
#   Mistral-Nemo and the Gemma 4 runs of Supplement Table S1, on BEAR 0.4.2. Their prompts
#   hold all 3,225 tools. The tag and measure parts produce no number of the paper.
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
#   monolithic
#       tab:e2e, the monolithic row: evals/eval_toolbench_e2e.py --backends none
#       --monolithic-cap 0 on mistral-nemo-131k. Temperature 0, no seed.
#   monolithic-cap128
#       The monolithic prompt with only the first 128 schemas of the corpus (part 5 of the plan):
#       evals/eval_toolbench_e2e.py --backends none --monolithic-cap 128. Section 4.2 sets it
#       against the full monolithic row. The prompt is short, so this part runs on
#       mistral-nemo-32k (digest d79a1e80980f, window 32,768), the tag of the Table 10 rows
#       (50_e2e_ollama.sh), and fits beside the Qwen3.8 server. Temperature 0, no seed.
#   react
#       The one-step ReAct scaffold on Mistral-Nemo: evals/eval_toolbench_react.py
#       --monolithic-cap 0 on mistral-nemo-131k, run label nemo-v042. Temperature 0, no seed.
#   g12-scaffold, g31-scaffold
#       evals/run_model_scaffold_nothink.sh on the fixed-window Gemma tag, then
#       evals/scaffold_vs_single.py. Labels g4-12b-v042 and g4-31b-v042.
#   g12-native, g31-native, and g12-native-s1 to -s4, g31-native-s1 to -s4
#       evals/run_model_full1100.sh on the same tag: its four runs, one guarded load per run.
#       A name that ends in -sK makes run K only. Run 1 is governed single-turn, run 2 governed
#       with native reasoning, run 3 the monolithic prompt with the reasoning channel off, and
#       run 4 the monolithic prompt with native reasoning. Each run is one pass over the 1,100
#       queries. A run that finished is not made again, so the four runs of the 31B model can
#       spread over several booked nights. When all four are done, evals/grid_from_full1100.py.
#       Runs that an earlier job of the whole part finished before it stopped at a later run
#       are kept, if that job's serving record shows no cut prompt and the result file holds
#       all 1,100 queries (job 350 finished runs 1 and 2 of the 12B model on 20 Nov 2026).
#       The Gemma parts sample (temperature 1.0, top-p 0.95, top-k 64) and send the seed
#       20261120 with every request.
#   A run part goes through evals/e2e_rerun/run_guarded.py. It checks the digests, the card and
#   the loaded window before the script starts. It unloads the tag at the end, searches the
#   Ollama log for a cut prompt, and writes serving.json (how the model was served). The part
#   runs in the clone artifacts-previous with the kit's BEAR 0.4.2, and what it wrote is
#   copied to $REPRO_OUT/e2e_long/<part>/ (for a native run to .../g12-native/ or
#   .../g31-native/, with its serving record in sK/). Tracked files of the clone are then restored.
# Prerequisites: 00_setup.sh. Ollama on Windows at 127.0.0.1:11434 holds the base tag with
#   the digest above. For a measure or run part: the tag part ran, Ollama holds no model, no
#   other GPU job runs, the card is at or below the start limit, wsl-keepalive is Running.
#   The 12B parts fit beside the Qwen3.8 server (gpumem:16, measured 20 Nov 2026: about
#   11,900 MiB on the card, 91,815 prompt tokens by the server's count). The 31B and
#   Mistral-Nemo parts need that server stopped, in a window booked through the model-server
#   session.
# Resources: tag parts, CPU only. Measure and run parts, the GPU through Ollama
#   (model-server's estimates at 131,072: 12B 10 to 13 GiB, 31B 30 to 32 GiB, Mistral-Nemo
#   27.5 GiB). The client hides CUDA, so its BGE embedder runs on the CPU. Client memory cap
#   6G for a measure part and 16G for a run part. ~/tist-gpu.lock is held while the model is
#   loaded.
# Time: a tag part under a minute. A measure part 5 to 20 minutes. In July the monolithic row
#   took about 6 h and the ReAct batch about 8 h. On 20 Nov 2026 the 12B scaffold part took
#   1 h 05, and runs 1 and 2 of the 12B native part took 5 minutes and 5 h 06. In July run 4
#   took 6 h 28 on the 12B model. The 31B model is slower (about 1.5 times in July's scaffold runs).
# Outputs: $REPRO_OUT/e2e_long/<part>/ (measure.json or serving.json, UNLOADED, and for a run
#   part the result files in the repo layout), and notes in the run record. A native part
#   keeps one serving record per run in sK/, the grid in grid.txt, and the files of an
#   attempt that did not finish in unfinished/.
#
# Usage:
#   bash reproduce/56_e2e_long_context.sh PART [--dry-run] [--wait]
#   bash reproduce/56_e2e_long_context.sh --list
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

PARTS="tag-g12 tag-g31 tag-nemo measure-g12 measure-g31 measure-nemo monolithic react g12-scaffold g12-native g31-scaffold g31-native"
PARTS+=" g12-native-s1 g12-native-s2 g12-native-s3 g12-native-s4 g31-native-s1 g31-native-s2 g31-native-s3 g31-native-s4"
PARTS+=" monolithic-cap128"
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
TAG_DIGEST=""   # set where the plan names the tag's own digest
# M is the model's short name in the part names. SEED is sent by the sampled (Gemma) parts only.
case $PART in
  monolithic-cap128) M=nemo BASE=mistral-nemo BASE_DIGEST=e7e06d107c6c TAG=mistral-nemo-32k LABEL=nemo-v042 SEED="" CTX=32768 TAG_DIGEST=d79a1e80980f ;;
  *g12*) M=g12  BASE=gemma4:12b   BASE_DIGEST=4eb23ef187e2 TAG=gemma4-12b-131k   LABEL=g4-12b-v042 SEED=20261120 ;;
  *g31*) M=g31  BASE=gemma4:31b   BASE_DIGEST=6316f0629137 TAG=gemma4-31b-131k   LABEL=g4-31b-v042 SEED=20261120 ;;
  *)     M=nemo BASE=mistral-nemo BASE_DIGEST=e7e06d107c6c TAG=mistral-nemo-131k LABEL=nemo-v042   SEED="" ;;
esac
case $PART in tag-*) KIND=tag ;; measure-*) KIND=measure ;; *) KIND=run ;; esac
# A native part is made of four runs. STAGES holds the ones this call makes, and PART_DIR names
# the folder and the markers that the whole part and its single runs share.
case $PART in
  *-native-s[1-4]) STAGES=${PART##*-s} PART_DIR=${PART%-s*} ;;
  *-native)        STAGES="1 2 3 4"    PART_DIR=$PART ;;
  *)               STAGES=""           PART_DIR=$PART ;;
esac
MODELFILE=evals/e2e_rerun/Modelfile.$TAG
[ "$TAG" = mistral-nemo-32k ] && MODELFILE=Modelfile   # the tag of 50_e2e_ollama.sh, made from the repo's Modelfile
OUT=$REPRO_OUT/e2e_long/$PART_DIR
ART0=$WP0_DIR/artifacts
RUN_CLONE=$PREV_CLONE   # the run parts write here. It holds no change of its own.
BASE_URL=$REPRO_OLLAMA_ROOT/v1

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
  if [ "$KIND" != tag ]; then
    check_slice
    check_keepalive
    if [ -n "$TAG_DIGEST" ]; then
      [ "$(tag_digest "$TAG")" = "$TAG_DIGEST" ] || die "Ollama lists $TAG with digest $(tag_digest "$TAG"), and the plan names $TAG_DIGEST. In PowerShell, in this repo: ollama create $TAG -f $MODELFILE"
    else
      [ -n "$(tag_digest "$TAG")" ] || die "Ollama has no tag $TAG. Run: bash reproduce/56_e2e_long_context.sh tag-$M"
    fi
    check_no_gpu_jobs
    check_card_start
    check_ollama_idle
  fi
  if [ "$KIND" = run ]; then
    check_clone "$RUN_CLONE"
    [ -f "$RUN_CLONE/evals/e2e_rerun/run_guarded.py" ] || die "$RUN_CLONE has no evals/e2e_rerun/run_guarded.py. Run 00_setup.sh --update."
    [ -z "$(git -C "$RUN_CLONE" status --porcelain --untracked-files=no)" ] \
      || die "$RUN_CLONE has changed tracked files. An earlier part did not finish its copy. Look at: git -C $RUN_CLONE status"
    # A native part asks the clone's script for one run at a time. An older copy would make all four.
    [ -z "$STAGES" ] || grep -q '^STAGES=' "$RUN_CLONE/evals/run_model_full1100.sh" \
      || die "$RUN_CLONE/evals/run_model_full1100.sh cannot make single runs yet. Run 00_setup.sh --update."
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
  [ "$KIND" != tag ] && { check_card_start; check_ollama_idle; echo "+ (check: Ollama lists $TAG)"; }
  [ "$KIND" = run ] && echo "+ (check: $RUN_CLONE is a clean clone with evals/e2e_rerun/run_guarded.py)"
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
elif [ "$KIND" = measure ]; then
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
else
  # ---- a run part: one of the reruns of parts 2 to 4, on BEAR 0.4.2
  [ "$DRY_RUN" = 0 ] && mkdir -p "$OUT"
  STAMP=$OUT/.started
  # guard OUTDIR: fills GUARD. The guard loads the tag, runs the script, unloads the tag, checks
  # the Ollama log and writes OUTDIR/serving.json.
  guard() {
    GUARD=(flock "$GPU_LOCK" "$TC" --mem 16G -- env CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
           PYTHONUNBUFFERED=1 BASE_URL="$BASE_URL" ${SEED:+LLM_SEED=$SEED}
           "$REPRO_PY" evals/e2e_rerun/run_guarded.py --model "$TAG" --base "$BASE" --expect-base-digest "$BASE_DIGEST"
           --expect-ctx "$CTX" --base-url "$BASE_URL" --win-gpu-max-mib "$GPU_START_MIB" --win-gpu-stop-mib "$GPU_STOP_MIB"
           ${SEED:+--seed $SEED} --out "$1" --)
  }
  part_note() {
    record_note "run part $PART: $TAG (digest $(tag_digest "$TAG")) from $BASE ($BASE_DIGEST), window $CTX, seed ${SEED:-none}, label $LABEL, BEAR $BEAR_VERSION ($BEAR_SHA), clone $RUN_CLONE at $(git -C "$RUN_CLONE" rev-parse --short HEAD)"
  }
  restore_clone() { (cd "$RUN_CLONE" && git ls-files -m -- results evals/results | xargs -r git checkout -q --); }
fi
if [ "$KIND" = run ] && [ -n "$STAGES" ]; then
  # ---- the native-reasoning runs of one Gemma model, one guarded load per run
  RUN_NAME=([1]=bearsingle-nothink-full [2]=bear-full [3]=mono-nothink-full [4]=mono-think-full)
  RUN_LOG=([1]=bearsingle_full [2]=bear_full [3]=mono_nothink_full [4]=mono_think_full)
  RUN_CONDS=([1]="bear_single" [2]="bear_react bear_single" [3]="mono_react" [4]="mono_react")
  run_files() {  # run_files K: the three files run K writes, relative to the clone. The result file is first.
    echo "results/toolbench_react_metrics_${LABEL}-${RUN_NAME[$1]}_partial.json"
    echo "results/toolbench_react_output_${LABEL}-${RUN_NAME[$1]}_partial.txt"
    echo "results/${LABEL}_${RUN_LOG[$1]}.log"
  }
  collect_run() {  # collect_run K: copy what run K wrote since this part began from the clone to $OUT. Prints the count.
    local rel n=0
    while IFS= read -r rel; do
      [ -f "$RUN_CLONE/$rel" ] && [ "$RUN_CLONE/$rel" -nt "$STAMP" ] || continue
      mkdir -p "$OUT/$(dirname "$rel")"
      cp -p "$RUN_CLONE/$rel" "$OUT/$rel"
      n=$((n + 1))
    done < <(run_files "$1")
    echo "$n"
  }
  set_aside() {  # set_aside K: move what an attempt at run K that did not finish left in $OUT (its copied files and its serving record) to unfinished/, and clear its files from the clone
    local rel dir=$OUT/unfinished/s$1-$(date -u +%Y%m%dT%H%M%SZ) any=0
    while IFS= read -r rel; do
      rm -f "$RUN_CLONE/$rel"
      [ -f "$OUT/$rel" ] || continue
      mkdir -p "$dir"
      mv "$OUT/$rel" "$dir/"
      any=1
    done < <(run_files "$1")
    if [ -d "$OUT/s$1" ]; then
      mkdir -p "$dir"
      mv "$OUT/s$1" "$dir/serving"
      any=1
    fi
    [ "$any" = 1 ] && record_note "run $1: what an attempt that did not finish left was moved to $dir"
    return 0
  }
  run_complete() {  # run_complete K: the copied result file of run K holds all 1,100 queries of each of its conditions, for this tag and seed
    python3 -c '
import json, sys
path, tag, seed, conds = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
try:
    d = json.load(open(path))
except (OSError, ValueError):
    sys.exit(1)
pq = d.get("per_query_correct") or {}
ok = d.get("model") == tag and str(d.get("llm_seed")) == seed and all(len(pq.get(c) or []) == 1100 for c in conds)
sys.exit(0 if ok else 1)
' "$OUT/$(run_files "$1" | head -1)" "$TAG" "${SEED:-None}" ${RUN_CONDS[$1]}
  }
  kept_from_whole_part() {  # kept_from_whole_part K: an earlier job of the whole part wrote run K's result file while its command ran, and its guard saw no cut prompt
    python3 -c '
import calendar, json, os, sys, time
serving, path = sys.argv[1], sys.argv[2]
try:
    s = json.load(open(serving))
    t = os.path.getmtime(path)
    ts = lambda x: calendar.timegm(time.strptime(x, "%Y-%m-%dT%H:%M:%SZ"))
    # A few seconds of slack: the record has whole seconds, and a copy can lose the fraction of a second.
    ok = (s.get("command_ran") is True and s.get("cut_lines_since_start") == 0 and s.get("loaded_after") == []
          and ts(s["utc_command_start"]) - 2 <= t <= ts(s["utc_command_end"]) + 5)
except (OSError, ValueError, KeyError, TypeError):
    ok = False
sys.exit(0 if ok else 1)
' "$OUT/serving.json" "$OUT/$(run_files "$1" | head -1)"
  }
  if [ "$DRY_RUN" = 0 ]; then
    [ -f "$STAMP" ] || date -u +%FT%TZ > "$STAMP"
    part_note
    record_note "runs of $PART_DIR asked for: $STAGES. The part began $(cat "$STAMP")"
  fi
  for k in $STAGES; do
    name=$PART_DIR-s$k
    if step_done "$name"; then
      say "skip $name (done $(cat "$(state_dir)/$name.done")). Remove $(state_dir)/$name.done to rerun it"
      continue
    fi
    guard "$OUT/s$k"
    if [ "$DRY_RUN" = 1 ]; then
      echo "+ (run $k is kept without a new run if an earlier job of the whole part finished it. Otherwise:)"
      run_cmd "$name" -C "$RUN_CLONE" -- "${GUARD[@]}" env MODEL="$TAG" LABEL="$LABEL" STAGES="$k" bash evals/run_model_full1100.sh
      echo "+ (copy the three files of run $k to $OUT, and require 1,100 queries for each of: ${RUN_CONDS[$k]})"
      continue
    fi
    collect_run "$k" >/dev/null
    if run_complete "$k" && kept_from_whole_part "$k"; then
      f=$OUT/$(run_files "$k" | head -1)
      record_note "run $k (${RUN_NAME[$k]}) was finished by an earlier job of the whole part and is kept, not made again. Result file $f, written $(date -u -r "$f" +%FT%TZ), sha256 $(sha256sum "$f" | cut -c1-16). Serving record of that job ($OUT/serving.json): $(cat "$OUT/serving.txt" 2>/dev/null)"
      mark_done "$name"
      continue
    fi
    set_aside "$k"
    say "step $name"
    run_cmd "$name" -C "$RUN_CLONE" -- "${GUARD[@]}" env MODEL="$TAG" LABEL="$LABEL" STAGES="$k" bash evals/run_model_full1100.sh
    rc=$?
    n=$(collect_run "$k")
    restore_clone
    if [ "$rc" -ne 0 ]; then
      set_aside "$k"
      die "step $name failed (exit $rc). See the output above"
    fi
    [ -f "$OUT/s$k/serving.json" ] || die "$OUT/s$k/serving.json is missing, so how the model was served is not on record"
    if ! run_complete "$k"; then
      set_aside "$k"
      die "run $k ended with exit 0, but its result file does not hold 1,100 queries for each of: ${RUN_CONDS[$k]}"
    fi
    mark_done "$name"
    record_note "run $k (${RUN_NAME[$k]}) of $PART_DIR done, $n files copied to $OUT. Serving: $(cat "$OUT/s$k/serving.txt" 2>/dev/null)"
  done
  open=""
  for k in 1 2 3 4; do step_done "$PART_DIR-s$k" || open+=" $k"; done
  if [ -z "$open" ]; then
    if [ "$DRY_RUN" = 0 ]; then  # the grid script reads the clone's results/
      for k in 1 2 3 4; do rel=$(run_files "$k" | head -1); cp -p "$OUT/$rel" "$RUN_CLONE/$rel"; done
    fi
    rstep "$PART_DIR-analysis" -C "$RUN_CLONE" -- "$TC" --mem 4G -- bash -o pipefail -c \
      'python evals/grid_from_full1100.py "$1" | tee "$2"' grid "$LABEL" "$OUT/grid.txt"
  else
    say "runs of $PART_DIR still open:$open. The grid is made when all four are done"
    [ "$DRY_RUN" = 1 ] && echo "+ (when all four runs are done: python evals/grid_from_full1100.py $LABEL, kept as $OUT/grid.txt)"
  fi
  if [ "$DRY_RUN" = 0 ]; then
    say "card after the run: $(card_mib) MiB"
    REPRO_OK_NOTE="part $PART done, model unloaded. Runs of $PART_DIR still open:${open:- none}. Results in $OUT"
  fi
elif [ "$KIND" = run ]; then
  # COPIED: the part's outputs are in $OUT already. Then a later call copies nothing, because the
  # clone may by now hold newer files that other parts wrote.
  COPIED=0
  [ -f "$OUT/.copied" ] && COPIED=1
  # A scaffold part that finished before the .copied marker existed (job 349) was copied then.
  case $PART in *-scaffold) step_done "$PART" && step_done "$PART-analysis" && COPIED=1 ;; esac
  if [ "$DRY_RUN" = 0 ] && ! step_done "$PART"; then
    date -u +%FT%TZ > "$STAMP"
    part_note
  fi
  guard "$OUT"
  ANALYSIS=()
  case $PART in
    monolithic)
      rstep "$PART" -C "$RUN_CLONE" -- "${GUARD[@]}" python evals/eval_toolbench_e2e.py --backends none \
        --monolithic-cap 0 --base-url "$BASE_URL" --model "$TAG" ;;
    monolithic-cap128)
      rstep "$PART" -C "$RUN_CLONE" -- "${GUARD[@]}" python evals/eval_toolbench_e2e.py --backends none \
        --monolithic-cap 128 --base-url "$BASE_URL" --model "$TAG" ;;
    react)
      rstep "$PART" -C "$RUN_CLONE" -- "${GUARD[@]}" python evals/eval_toolbench_react.py \
        --monolithic-cap 0 --base-url "$BASE_URL" --model "$TAG" --run-label "$LABEL" ;;
    g12-scaffold|g31-scaffold)
      rstep "$PART" -C "$RUN_CLONE" -- "${GUARD[@]}" env MODEL="$TAG" LABEL="$LABEL" bash evals/run_model_scaffold_nothink.sh
      ANALYSIS=(python evals/scaffold_vs_single.py "$LABEL") ;;
  esac
  [ ${#ANALYSIS[@]} -gt 0 ] && rstep "$PART-analysis" -C "$RUN_CLONE" -- "$TC" --mem 4G -- "${ANALYSIS[@]}"
  if [ "$DRY_RUN" = 0 ] && [ "$COPIED" = 1 ]; then
    say "part $PART was done before this call. Nothing is copied again. Results in $OUT"
    REPRO_OK_NOTE="part $PART was done already. Results in $OUT"
  elif [ "$DRY_RUN" = 0 ]; then
    [ -f "$OUT/serving.json" ] || die "$OUT/serving.json is missing, so how the model was served is not on record"
    # Keep a copy of what this part wrote (files newer than its start), then restore the clone's tracked files.
    n=0
    while IFS= read -r rel; do
      [ -f "$RUN_CLONE/$rel" ] && [ "$RUN_CLONE/$rel" -nt "$STAMP" ] || continue
      mkdir -p "$OUT/$(dirname "$rel")"
      cp -p "$RUN_CLONE/$rel" "$OUT/$rel"
      n=$((n + 1))
    done < <(cd "$RUN_CLONE" && { git ls-files -m -- results evals/results; \
             git ls-files --others --exclude-standard -- results evals/results; } | sort -u)
    restore_clone
    date -u +%FT%TZ > "$OUT/.copied"
    say "copied $n file(s) to $OUT"
    record_note "outputs of $PART copied to $OUT ($n files). Serving: $(cat "$OUT/serving.txt" 2>/dev/null)"
    say "card after the run: $(card_mib) MiB"
    REPRO_OK_NOTE="part $PART done, model unloaded. Results in $OUT"
  else
    echo "+ (copy what the part wrote under results/ and evals/results/ to $OUT, then restore the clone's tracked files)"
  fi
fi
