# reproduce/lib/wp0.sh: running the WP0 lanes of evals/wp0_v040/run_wp0_v040.sh.
# Source it after common.sh.
#
# The lane table below (clone and settings per lane) is the one in
# evals/wp0_v040/relaunch_042.sh. That script cannot be called here: it names
# absolute personal paths and copies the scripts from a session folder into the
# clones. The kit runs the committed scripts of each clone instead. They are
# identical to the copies the October runs used.
#
# A lane runs in the foreground of the calling script, which itself runs as a
# user service. Every step of a lane runs in its own tist-capped scope
# (WP0_STEP_MEM), and a finished step leaves $WP0_DIR/logs/<step>.done, so a
# lane that is started again skips what it finished.

lane_clone() {
  case $1 in
    lex042|e2erun) echo artifacts ;;
    attrpet042|fallback0110) echo artifacts-attr ;;
    attrtb042) echo artifacts-track ;;
    nemo042|mand042|pair042|e2eattr042|manddense042) echo artifacts-nemo ;;
    dense042|mandonly042) echo artifacts-dense ;;
    gpuq4b042|gpuq4b042fix|gpuq4b042gov) echo artifacts-gpu ;;
    *) return 1 ;;
  esac
}

lane_env() {
  local gpu="WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=12G WP0_GPU_CAP_FIXED=11.2 WP0_WIN_GPU_MAX_MIB=$GPU_START_MIB"
  gpu+=" WP0_WIN_GPU_STOP_MIB=$GPU_STOP_MIB WP0_GPU_MAXWAIT=${WP0_GPU_MAXWAIT:-7200}"
  case $1 in
    dense042|mandonly042|manddense042)
      echo "WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=20G WP0_ENCODE_BATCH=4 WP0_CPU_THREADS=12" ;;
    gpuq4b042) echo "$gpu WP0_ENCODE_BATCH=8" ;;
    gpuq4b042fix|gpuq4b042gov) echo "$gpu WP0_ENCODE_BATCH=2 WP0_EMPTY_CACHE=1" ;;
    mand042|fallback0110|pair042|e2eattr042) echo "WP0_STEP_MEM=4G" ;;
    *) echo "" ;;
  esac
}

# Steps that fail in a correct run, with the reason. Anything else that fails
# or is blocked stops the script.
lane_expected_failures() {
  case $1 in
    lex042) echo "ablation_lexical" ;;            # eval_ablation.py also loads BGE, refused in this lane. Not in the manuscript.
    dense042) echo "decomposed_q4b decomposed_q4b_v0110" ;;   # killed at the 20G cap (two Qwen3-4B copies); manddense042 reruns them
    gpuq4b042) echo "tb_qwen4b tb_qwen4b_v0110 e2e_q4b_v042 e2e_q4b_v0110 wp4_tb_q4b" ;;  # OOM at batch 8 on long ToolBench texts; gpuq4b042fix reruns them at batch 2
    *) echo "" ;;
  esac
}

# run_lane LANE: run one lane to its end in its clone, then check its result.
run_lane() {
  local lane=$1 clone dir out
  clone=$(lane_clone "$lane") || die "unknown lane $lane"
  dir=$WP0_DIR/$clone
  out=$WP0_DIR/logs/lane_$lane.out
  if step_done "lane_$lane"; then
    say "skip lane $lane (done $(cat "$(state_dir)/lane_$lane.done"))"
    return 0
  fi
  [ "$DRY_RUN" = 1 ] || check_clone "$dir"
  say "lane $lane in $dir (settings: $(lane_env "$lane"))"
  # shellcheck disable=SC2046
  run_cmd "lane-$lane" -C "$dir" -o "$out" -- env WP0_ROOT="$WP0_DIR" WP0_ART="$dir" WP0_PY="$REPRO_PY" \
    $(lane_env "$lane") bash evals/wp0_v040/run_wp0_v040.sh "$lane"
  local rc=$?
  [ "$DRY_RUN" = 1 ] && return 0
  check_lane "$lane" "$rc"
  mark_done "lane_$lane"
}

# check_lane LANE RC: read the lane's latest run in lane_LANE.out. Dies unless
# it reached its last line and every failed or blocked step is an expected one.
check_lane() {
  local lane=$1 rc=$2 out=$WP0_DIR/logs/lane_$lane.out start seg bad s unexpected=""
  [ "$rc" -eq 0 ] || die "lane $lane exited with $rc (see $out)"
  start=$(grep -n "WP0 lane=$lane bear042=" "$out" | tail -1 | cut -d: -f1)
  [ -n "$start" ] || die "lane $lane: no start line in $out"
  seg=$(tail -n +"$start" "$out")
  grep -q "WP0 lane=$lane finished" <<<"$seg" || die "lane $lane ended without its last line (killed?), see $out"
  if grep -qE "stopped|needs WP0_|expects WP0_|unknown lane" <<<"$seg"; then
    die "lane $lane stopped early: $(grep -E "stopped|needs WP0_|expects WP0_|unknown lane" <<<"$seg" | tail -1)"
  fi
  bad=$(grep -E "\] (FAILED|BLOCKED) " <<<"$seg" | awk '{print $4}' | sort -u)
  local expected
  expected=$(lane_expected_failures "$lane")
  for s in $bad; do
    if [[ " $expected " == *" $s "* ]]; then
      record_note "lane $lane: step $s failed as expected ($(head -1 "$WP0_DIR/logs/$s.failed" 2>/dev/null))"
    else
      unexpected+=" $s"
    fi
  done
  [ -z "$unexpected" ] || die "lane $lane: steps failed or were blocked:$unexpected (logs in $WP0_DIR/logs/<step>.log)"
  if grep -q "^cat: .*EXPORTED_SHA" <<<"$seg"; then
    say "lane $lane: the 'cat: ...EXPORTED_SHA' line is harmless (the runner reads a 0.4.0 export it does not use here)"
  fi
  say "lane $lane: finished, no unexpected failure ($(grep -c "\] done " <<<"$seg") steps done in this pass)"
}

# wp0_gpu_tb_step NAME SCOPE ROW...: one GPU step of eval_toolbench_v040.py on
# BEAR 0.4.2, made the way run_wp0_v040.sh makes a "tb" step of kind gpu, for a
# row no lane holds. Used for the Qwen3-4B mand-only rows (Section 5.4).
# - the same clone (artifacts-gpu), stage folder, embedding cache, log header
#   and .done/.failed markers as the lanes, so 70_assemble.sh picks it up
# - the same chain: flock ~/tist-gpu.lock, gpu_gate.sh (start at GPU_START_MIB
#   or less, allocator cap 11.2 GiB), tist-capped --mem 12G, mem_guard.sh (stop
#   above GPU_STOP_MIB)
# - the settings of lane gpuq4b042fix: bf16, encode batch 2, empty cache
# Exit 75 from the gate (card busy) is retried every 5 minutes for WP0_GPU_MAXWAIT seconds.
wp0_gpu_tb_step() {
  local name=$1 scope=$2
  shift 2
  local art=$WP0_DIR/artifacts-gpu logs=$WP0_DIR/logs W=evals/wp0_v040
  local out=results/wp0/toolbench_eval_$name.json extra=()
  case $scope in
    toolbench) extra=(--toolbench-only) ;;
    metatool) extra=(--metatool-only) ;;
    metatool-base) extra=(--metatool-only --metatool-base-only) ;;
  esac
  if [ -f "$logs/$name.done" ]; then
    say "skip $name (done, $logs/$name.done)"
    return 0
  fi
  local envs=(HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1
              PYTHONPATH="$art/$W/site" BEAR_SOURCE_SHA="$BEAR_SHA" ANTHROPIC_API_KEY=wp0-dummy-key-no-paid-calls
              WP0_REPORT_VRAM="$logs/vram.jsonl" WP0_STEP="$name" WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=12G
              WP0_ENCODE_BATCH=2 WP0_EMPTY_CACHE=1 WP0_GPU_CAP_FIXED=11.2 WP0_WIN_GPU_MAX_MIB="$GPU_START_MIB"
              WP0_WIN_GPU_STOP_MIB="$GPU_STOP_MIB" WP0_QWEN4B_DTYPE=bfloat16 WP0_SHARE_MODELS=1
              WP0_EMB_CACHE="$WP0_DIR/embcache" WP0_ART="$art")
  local cmd=("$REPRO_PY" "$W/eval_toolbench_v040.py" --top-k 5
             --metatool-query-tags-file evals/data/external_benchmarks/metatool/query_tags_top5.json
             "${extra[@]}" --output "$out" --backends "$@")
  say "step $name (GPU, Qwen3-4B bf16, batch 2, cap 11.2 GiB, gates $GPU_START_MIB and $GPU_STOP_MIB MiB)"
  if [ "$DRY_RUN" = 1 ]; then
    echo "+ (cd $art) flock $GPU_LOCK env -u OPENAI_API_KEY ${envs[*]} bash $W/gpu_gate.sh 11 $TC --mem 12G -- bash $W/mem_guard.sh $(printf '%q ' "${cmd[@]}")"
    echo "+ (copy $out to $WP0_DIR/stage/v042/$name/, stamp it with $W/stamp_dir.py, write $logs/$name.done)"
    return 0
  fi
  mkdir -p "$logs" "$art/results/wp0"
  {
    echo "### ================ attempt $(date -Is) ================"
    echo "### step:        $name"
    echo "### kind:        gpu (need 11 GiB)"
    echo "### bear:        v042 ($BEAR_SHA)"
    echo "### started:     $(date -Is)"
    echo "### command:     ${cmd[*]}"
    echo "### env:         ${envs[*]}"
    echo "### memory cap:  $TC --mem 12G --"
    echo "### made by:     reproduce/lib/wp0.sh wp0_gpu_tb_step (no lane holds this row)"
  } >> "$logs/$name.log"
  rm -f "$logs/$name.failed" "$logs/$name.blocked"
  local rc waited=0 maxwait=${WP0_GPU_MAXWAIT:-7200} t0
  t0=$(date -u +%FT%TZ)
  while :; do
    (cd "$art" && flock "$GPU_LOCK" env -u OPENAI_API_KEY "${envs[@]}" bash "$W/gpu_gate.sh" 11 \
        "$TC" --mem 12G -- bash "$W/mem_guard.sh" "${cmd[@]}") >> "$logs/$name.log" 2>&1
    rc=$?
    [ "$rc" -ne 75 ] && break
    (( waited >= maxwait )) && break
    say "$name: the gate says not now (card or memory), retry in 5 minutes"
    sleep 300; waited=$((waited + 300))
  done
  echo "### finished:    $(date -Is) rc=$rc" >> "$logs/$name.log"
  python3 "$REPRO_DIR/lib/run_record.py" cmd "$REPRO_RECORD" --label "$name" --rc "$rc" --start "$t0" \
    --cwd "$art" -- "${cmd[@]}" >/dev/null 2>&1
  if [ "$rc" -ne 0 ]; then
    echo "$rc" > "$logs/$name.failed"
    die "step $name failed (exit $rc, 75 means the card stayed busy, 78 that it passed the stop limit). See $logs/$name.log"
  fi
  local dest=$WP0_DIR/stage/v042/$name
  mkdir -p "$dest/results/wp0"
  cp "$logs/$name.log" "$dest/"
  cp "$art/$out" "$dest/$out" || die "step $name wrote no $out"
  (cd "$art" && env "${envs[@]}" CUDA_VISIBLE_DEVICES= WP0_EMB_CACHE= "$TC" --mem 4G -- "$REPRO_PY" "$W/stamp_dir.py" "$dest" \
      --step "$name" --command "${cmd[*]}") >> "$logs/$name.log" 2>&1 || die "stamp_dir.py failed for $name"
  touch "$logs/$name.done"
  say "$name: done, staged in $dest"
}
