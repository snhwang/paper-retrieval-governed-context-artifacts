# reproduce/lib/wp0.sh: running the WP0 lanes of evals/wp0_v040/run_wp0_v040.sh.
# Source it after common.sh.
#
# The lane table below (clone and settings per lane) is the one in
# evals/wp0_v040/relaunch_042.sh. The kit does not call that script. It copies
# the checkout's working-tree WP0 scripts into each clone (so uncommitted edits
# would run) and starts lanes side by side as services. The kit runs the
# committed scripts of each clone instead, one lane at a time. They are
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
  local e m
  e=$(lane_env_base "$1")
  if [ -n "${SLURM_JOB_ID:-}" ]; then
    # Inside a Slurm job tist-capped runs each step in place, so WP0_STEP_MEM no longer caps a
    # step on its own, and a step past the job's --mem takes the whole job down (job 85, 16 Nov).
    # mem_guard.sh then stops a step at the same size instead (exit 76). The two dense042 steps
    # that fail at 20G by design (two Qwen3-4B copies) are skipped. manddense042 runs them.
    m=$(sed -n 's/.*WP0_STEP_MEM=\([0-9][0-9]*\)G.*/\1/p' <<<"$e")
    [ -n "$m" ] && e+=" WP0_RSS_MAX_GIB=$m"
    [ "$1" = dense042 ] && e+=" WP0_SKIP_STEPS=decomposed_q4b,decomposed_q4b_v0110"
  fi
  echo "$e"
}

lane_env_base() {
  local gpu="WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=12G WP0_GPU_CAP_FIXED=11.2 WP0_WIN_GPU_MAX_MIB=$GPU_START_MIB"
  gpu+=" WP0_WIN_GPU_STOP_MIB=$GPU_STOP_MIB WP0_GPU_MAXWAIT=${WP0_GPU_MAXWAIT:-7200}"
  case $1 in
    dense042|mandonly042|manddense042)
      echo "WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=20G WP0_ENCODE_BATCH=4 WP0_CPU_THREADS=12" ;;
    gpuq4b042) echo "$gpu WP0_ENCODE_BATCH=$REPRO_Q4B_BATCH WP0_EMPTY_CACHE=1" ;;   # October: 8
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
    # At batch 8 (the October rehearsal) the long ToolBench texts ran out of memory
    # inside the 11.2 GiB cap. At the kit's batch 2 nothing should fail.
    gpuq4b042) [ "$REPRO_Q4B_BATCH" = 8 ] && echo "tb_qwen4b tb_qwen4b_v0110 e2e_q4b_v042 e2e_q4b_v0110 wp4_tb_q4b" ;;
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

# kit_tb_step KIND NAME CLONE -- CMD...: one step that writes
# results/wp0/toolbench_eval_NAME.json in CLONE, made the way run_wp0_v040.sh
# makes a step of that kind, for rows no lane holds (the Qwen3-4B mand-only
# rows, the authorship ablation). It uses the lanes' stage folder, embedding
# cache, log header and .done/.failed markers, so 70_assemble.sh picks it up
# (steps named tb_*).
#   KIND lex    CPU, no model (WP0_NO_LOCAL_MODELS), 8G
#   KIND dense  CPU, local models as lane dense042: 20G, batch 4, 12 threads
#   KIND gpu    local GPU as lane gpuq4b042fix: flock ~/tist-gpu.lock, gpu_gate.sh
#               (start at GPU_START_MIB or less, allocator cap 11.2 GiB),
#               tist-capped --mem 12G, mem_guard.sh (stop above GPU_STOP_MIB),
#               bf16, encode batch KIT_Q4B_BATCH (default REPRO_Q4B_BATCH, 2), empty cache
#   KIND remote the Nemotron service as lane nemo042: flock, 8G, CUDA hidden,
#               the lanes' response cache
# Exit 75 from a gate (card or memory busy) is retried every 5 minutes for
# WP0_GPU_MAXWAIT seconds. Any other failure stops the script.
kit_tb_step() {
  local kind=$1 name=$2 art=$3
  shift 3
  [ "${1:-}" = "--" ] && shift
  local logs=$WP0_DIR/logs W=evals/wp0_v040 out=results/wp0/toolbench_eval_$name.json
  if [ -f "$logs/$name.done" ]; then
    say "skip $name (done, $logs/$name.done)"
    return 0
  fi
  local envs=(HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1
              PYTHONPATH="$art/$W/site" BEAR_SOURCE_SHA="$BEAR_SHA" ANTHROPIC_API_KEY=wp0-dummy-key-no-paid-calls
              WP0_REPORT_VRAM="$logs/vram.jsonl" WP0_STEP="$name" WP0_ART="$art")
  local mem chain=()
  case $kind in
    lex)    mem=8G
            envs+=(CUDA_VISIBLE_DEVICES= WP0_NO_LOCAL_MODELS=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8) ;;
    dense)  mem=20G
            envs+=(CUDA_VISIBLE_DEVICES= WP0_ALLOW_LOCAL_MODELS=1 WP0_ENCODE_BATCH=4 OMP_NUM_THREADS=12
                   MKL_NUM_THREADS=12 WP0_EMB_CACHE="$WP0_DIR/embcache" WP0_SHARE_MODELS=1) ;;
    gpu)    mem=12G
            envs+=(WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=12G WP0_ENCODE_BATCH="${KIT_Q4B_BATCH:-$REPRO_Q4B_BATCH}" WP0_EMPTY_CACHE=1
                   WP0_GPU_CAP_FIXED=11.2 WP0_WIN_GPU_MAX_MIB="$GPU_START_MIB" WP0_WIN_GPU_STOP_MIB="$GPU_STOP_MIB"
                   WP0_QWEN4B_DTYPE=bfloat16 WP0_SHARE_MODELS=1 WP0_EMB_CACHE="$WP0_DIR/embcache") ;;
    remote) mem=8G
            envs+=(CUDA_VISIBLE_DEVICES= WP0_NO_LOCAL_MODELS=1 WP0_NEMO_CACHE="$WP0_DIR/nemocache/nemo.sqlite") ;;
    *) die "kit_tb_step: unknown kind $kind" ;;
  esac
  case $kind in
    gpu)    chain=(flock "$GPU_LOCK" env -u OPENAI_API_KEY "${envs[@]}" bash "$W/gpu_gate.sh" 11
                   "$TC" --mem "$mem" -- bash "$W/mem_guard.sh") ;;
    remote) chain=(flock "$GPU_LOCK" env -u OPENAI_API_KEY "${envs[@]}" "$TC" --mem "$mem" -- bash "$W/mem_guard.sh") ;;
    *)      chain=(env -u OPENAI_API_KEY "${envs[@]}" "$TC" --mem "$mem" -- bash "$W/mem_guard.sh") ;;
  esac
  local detail="$kind, memory cap $mem"
  [ "$kind" = gpu ] && detail+=", bf16, encode batch ${KIT_Q4B_BATCH:-$REPRO_Q4B_BATCH}, allocator cap 11.2 GiB, gates $GPU_START_MIB and $GPU_STOP_MIB MiB"
  say "step $name ($detail)"
  if [ "$DRY_RUN" = 1 ]; then
    echo "+ (cd $art) $(printf '%q ' "${chain[@]}" "$@")"
    echo "+ (copy $out to $WP0_DIR/stage/v042/$name/, stamp it with $W/stamp_dir.py, write $logs/$name.done)"
    return 0
  fi
  mkdir -p "$logs" "$art/results/wp0" "$WP0_DIR/nemocache"
  {
    echo "### ================ attempt $(date -Is) ================"
    echo "### step:        $name"
    echo "### kind:        $kind"
    echo "### bear:        v042 ($BEAR_SHA)"
    echo "### started:     $(date -Is)"
    echo "### command:     $*"
    echo "### env:         ${envs[*]}"
    echo "### memory cap:  $TC --mem $mem --"
    echo "### made by:     reproduce/lib/wp0.sh kit_tb_step (no lane holds this step)"
  } >> "$logs/$name.log"
  rm -f "$logs/$name.failed" "$logs/$name.blocked"
  local rc waited=0 maxwait=${WP0_GPU_MAXWAIT:-7200} t0
  t0=$(date -u +%FT%TZ)
  while :; do
    (cd "$art" && "${chain[@]}" "$@") >> "$logs/$name.log" 2>&1
    rc=$?
    [ "$rc" -ne 75 ] && break
    (( waited >= maxwait )) && break
    say "$name: the gate says not now (card or memory), retry in 5 minutes"
    sleep 300; waited=$((waited + 300))
  done
  echo "### finished:    $(date -Is) rc=$rc" >> "$logs/$name.log"
  python3 "$REPRO_DIR/lib/run_record.py" cmd "$REPRO_RECORD" --label "$name" --rc "$rc" --start "$t0"     --cwd "$art" -- "$@" >/dev/null 2>&1
  if [ "$rc" -ne 0 ]; then
    echo "$rc" > "$logs/$name.failed"
    die "step $name failed (exit $rc. 75 means the card or memory stayed busy, 78 that the card passed the stop limit, 3 that a row is missing). See $logs/$name.log"
  fi
  local dest=$WP0_DIR/stage/v042/$name
  mkdir -p "$dest/results/wp0"
  cp "$logs/$name.log" "$dest/"
  cp "$art/$out" "$dest/$out" || die "step $name wrote no $out"
  (cd "$art" && env "${envs[@]}" CUDA_VISIBLE_DEVICES= WP0_EMB_CACHE= "$TC" --mem 4G -- "$REPRO_PY" "$W/stamp_dir.py" "$dest"       --step "$name" --command "$*") >> "$logs/$name.log" 2>&1 || die "stamp_dir.py failed for $name"
  touch "$logs/$name.done"
  say "$name: done, staged in $dest"
}

# wp0_gpu_tb_step NAME SCOPE ROW...: one GPU step of eval_toolbench_v040.py,
# settings of lane gpuq4b042fix (used for the Qwen3-4B mand-only rows).
wp0_gpu_tb_step() {
  local name=$1 scope=$2
  shift 2
  local extra=()
  case $scope in
    toolbench) extra=(--toolbench-only) ;;
    metatool) extra=(--metatool-only) ;;
    metatool-base) extra=(--metatool-only --metatool-base-only) ;;
  esac
  KIT_Q4B_BATCH=$REPRO_Q4B_BATCH kit_tb_step gpu "$name" "$WP0_DIR/artifacts-gpu" -- "$REPRO_PY" evals/wp0_v040/eval_toolbench_v040.py     --top-k 5 --metatool-query-tags-file evals/data/external_benchmarks/metatool/query_tags_top5.json     "${extra[@]}" --output "results/wp0/toolbench_eval_$name.json" --backends "$@"
}
