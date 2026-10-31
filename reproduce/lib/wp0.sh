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
