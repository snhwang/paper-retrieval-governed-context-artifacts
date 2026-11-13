#!/usr/bin/env bash
# slurm_submit_hermes.sh: submit the rest of Hermes (WP7 stage 2) to the workstation's Slurm queue.
#
# After the chain (61_hermes_chain.sh) has run stage 1 to block 1, this queues, in order:
#   rgc-h-b2     block 2 (C-cut at k, operators and 100-decoy guests), 414 cells   8355 and 8360 exclusive, 16G, 10 h limit
#   rgc-h-pb2    post-block2 checks (offline)                                    4G, 30 min
#   rgc-h-b3     block 3 (gate with reason at 100 decoys), 276 cells         8355 and 8360 exclusive, 16G,  7 h limit
#   rgc-h-pb3    post-block3 checks (offline)                                    4G, 30 min
#   rgc-h-an     analyze stage 2 (offline)                                       8G, 30 min
# each as `bash reproduce/60_hermes.sh STEP` with its kit run record. A block runs inside its job.
# The blocks hold all of chat8355 and embed8360, are never frozen (nofreeze), and get USR1
# 20 min before their time limit or a booked window, which writes the block's STOP file, so the
# grid ends after its current cell. A block that paused or stopped ends its job FAILED, and the
# jobs after it are cancelled. Continue it with `60_hermes.sh blockN --continue` (or resubmit
# with --continue). Block 1 must be complete first. The script checks its batch_end.
#
# k is Scott's choice from ~/tist-repro/hermes/analysis/stage2-settings/ksweep.md. --k must equal
# the k in hermes/specs/stage2_block2.json (committed), or nothing is submitted. Its value goes
# into the job's purpose.
#
# Usage:
#   bash reproduce/slurm_submit_hermes.sh --k 15 --dry-run
#   bash reproduce/slurm_submit_hermes.sh --k 15
#   bash reproduce/slurm_submit_hermes.sh --k 15 --continue     # block 2 was paused or stopped
set -uo pipefail
ART=$(cd "$(dirname "$0")/.." && pwd)
DRY=0 K="" CONT=""
while [ $# -gt 0 ]; do
  case $1 in
    -n|--dry-run) DRY=1 ;;
    --k) K=$2; shift ;;
    --continue) CONT=" --continue" ;;
    -h|--help) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$K" ] || { echo "give --k (Scott's choice for block 2)" >&2; exit 2; }
SPEC_K=$(python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); ks={k for g in s["grids"] for k in g.get("k", [])}; print(" ".join(map(str, sorted(ks))))' "$ART/hermes/specs/stage2_block2.json") \
  || { echo "cannot read hermes/specs/stage2_block2.json" >&2; exit 1; }
[ "$SPEC_K" = "$K" ] || { echo "specs/stage2_block2.json has k = $SPEC_K, not $K. Edit both k lists, run scripts/check_block2_baselines.py, commit, then submit." >&2; exit 1; }
[ -z "$(git -C "$ART" status --porcelain --untracked-files=no)" ] || { echo "$ART has uncommitted changes. Commit first: the jobs run what is on disk." >&2; exit 1; }
B1=${REPRO_OUT:-$HOME/tist-repro}/hermes/stage2-b1/logs/cells.jsonl
if [ "$DRY" = 0 ]; then
  grep -q '"batch_end"' "$B1" 2>/dev/null || { echo "block 1 has no batch_end in $B1. Let the chain finish block 1 first." >&2; exit 1; }
fi
OUT=${REPRO_OUT:-$HOME/tist-repro}/logs/slurm
[ "$DRY" = 1 ] || mkdir -p "$OUT"
KIT="TIST reproduction kit $(git -C "$ART" rev-parse --short HEAD)"

declare -A ID
sub() {  # sub NAME CPUS MEM TIME LICENSES AFTEROK NOFREEZE PURPOSE CMD
  local name=$1 cpus=$2 mem=$3 time=$4 lic=$5 after=$6 nf=$7 purpose=$8 cmd=$9
  local args=(--parsable --job-name="$name" --cpus-per-task="$cpus" --mem="$mem" --time="$time"
              --chdir="$ART" --output="$OUT/%x-%j.out")
  [ -n "$lic" ] && args+=(--licenses="$lic" --signal=B:USR1@1200)
  [ -n "$after" ] && args+=(--dependency="afterok:${ID[$after]}" --kill-on-invalid-dep=yes)
  args+=(--comment="project=RGC; purpose=$purpose; plan=$KIT, k=$K${nf:+; nofreeze}${RGC_VIA:+; via=$RGC_VIA}${RGC_REQUESTED:+; requested=$RGC_REQUESTED}")
  args+=(--wrap="exec bash $cmd")
  if [ "$DRY" = 1 ]; then
    ID[$name]="<$name>"; printf 'sbatch'; printf " %q" "${args[@]}"; echo; return 0
  fi
  local id
  id=$(sbatch "${args[@]}") || { echo "sbatch failed for $name. Nothing after it was submitted." >&2; exit 1; }
  ID[$name]=${id%%;*}; echo "$name: job ${ID[$name]}"
}

GRID="chat8355:8,embed8360:8"
sub rgc-h-b2  4 16G 10:00:00 "$GRID" ""         nofreeze "TIST Hermes stage 2 block 2: C-cut narrowing at k=$K against stage-1 baselines" "reproduce/60_hermes.sh block2$CONT"
sub rgc-h-pb2 2 4G  00:30:00 ""      rgc-h-b2   ""       "TIST Hermes stage 2: offline checks and tables after block 2" "reproduce/60_hermes.sh post-block2"
sub rgc-h-b3  4 16G 07:00:00 "$GRID" rgc-h-pb2  nofreeze "TIST Hermes stage 2 block 3: gate with reason at 100 decoys, guests" "reproduce/60_hermes.sh block3"
sub rgc-h-pb3 2 4G  00:30:00 ""      rgc-h-b3   ""       "TIST Hermes stage 2: offline checks and tables after block 3" "reproduce/60_hermes.sh post-block3"
sub rgc-h-an  2 8G  00:30:00 ""      rgc-h-pb3  ""       "TIST Hermes stage 2: analysis of blocks 1 to 3 for the paper's Hermes section" "reproduce/60_hermes.sh analyze"
[ "$DRY" = 1 ] && echo "(dry run: nothing submitted)"
[ "$DRY" = 1 ] || echo "submitted. Follow with: squeue -u $(id -un)"
