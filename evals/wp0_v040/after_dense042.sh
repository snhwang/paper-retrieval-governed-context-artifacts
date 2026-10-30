#!/usr/bin/env bash
# after_dense042.sh: start lane manddense042 once lane dense042 has finished
# successfully (coordinator, 2026-10-30). Runs as the capped user service
# wp0-manddense042 (tist-capped --mem 2G --service wp0-manddense042). It only
# waits and reads files; it stops or kills nothing.
#
# "Finished successfully" means all of these:
#   - the service wp0-dense042 is no longer active (tist-capped services are
#     --collect, so the unit disappears when it ends)
#   - lane_dense042.out holds the completion line "WP0 lane=dense042 finished"
#     after the lane's latest start line
#   - no step of that run FAILED or was BLOCKED, apart from decomposed_q4b and
#     decomposed_q4b_v0110, the two cap kills (rc 143) that manddense042 reruns
# Otherwise manddense042 does not start, and the reason goes to
# lane_manddense042.out.
#
# One dense lane at a time, and the memory budget: it also waits while the
# Qwen3-4B GPU lane (wp0-gpuq4b042, 12G host cap) is active. The steps run at
# the same caps as dense042 (20G per step, batch 4, 12 threads).
set -u
R=$HOME/tist-evals/wp0-v042
L=$R/logs
OUT=$L/lane_manddense042.out
DLOG=$L/lane_dense042.out
EXPECTED_FAILS="decomposed_q4b decomposed_q4b_v0110"
log() { echo "[$(date '+%F %T')] $*" >> "$OUT"; }

log "waiter: manddense042 will start when wp0-dense042 finishes successfully"
while systemctl --user is-active -q wp0-dense042; do sleep 60; done
log "waiter: wp0-dense042 is no longer active"

start_line=$(grep -n "WP0 lane=dense042 bear042=" "$DLOG" | tail -1 | cut -d: -f1)
if [[ -z $start_line ]]; then
  log "NOT STARTED: no dense042 start line in $DLOG"; exit 1
fi
segment=$(tail -n +"$start_line" "$DLOG")
if ! grep -q "WP0 lane=dense042 finished" <<<"$segment"; then
  log "NOT STARTED: dense042 ended without its completion line (killed or crashed)"; exit 1
fi
bad=$(grep -E "FAILED|BLOCKED" <<<"$segment" | awk '{print $4}' | sort -u)
unexpected=""
for s in $bad; do
  [[ " $EXPECTED_FAILS " == *" $s "* ]] || unexpected+=" $s"
done
if [[ -n $unexpected ]]; then
  log "NOT STARTED: dense042 steps failed or were blocked:$unexpected"; exit 1
fi
log "waiter: dense042 finished successfully (known cap kills:${bad:+ }$(echo $bad))"

while systemctl --user is-active -q wp0-gpuq4b042; do sleep 60; done
log "waiter: starting manddense042"
cd "$R/artifacts-nemo" || { log "NOT STARTED: no clone artifacts-nemo"; exit 1; }
export WP0_ART=$R/artifacts-nemo WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=20G WP0_ENCODE_BATCH=4 WP0_CPU_THREADS=12
exec bash evals/wp0_v040/run_wp0_v040.sh manddense042 >> "$OUT" 2>&1
