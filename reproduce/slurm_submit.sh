#!/usr/bin/env bash
# slurm_submit.sh: submit the kit's steps after Hermes to the workstation's Slurm queue, in order.
#
# Scott runs it once. It calls sbatch for each step below and chains them with dependencies,
# so Slurm starts each when its inputs exist, its resources are free and no booked window is in
# the way. It submits only. Nothing runs in this terminal. Draft for model-server's check of
# the caps first (--dry-run prints every sbatch line).
#
# Each job runs `bash reproduce/NN.sh ...` in this checkout. Inside a Slurm job the kit runs in
# the foreground (no user service), each step runs under the job's own cap (tist-capped runs in
# place, see reproduce/bin/tist-capped), and the run record notes the job id. Slurm's own
# output goes to ~/tist-repro/logs/slurm/<name>-<jobid>.out, and the kit's run records to
# ~/tist-repro/runlog/ as always.
#
# Steps, with what they hold (cores are --cpus-per-task, 2 per physical core):
#   rgc-10      CPU retrieval              12 CPUs, 24G, 24 h
#   rgc-15      invariants and baselines   12 CPUs, 16G, 14 h   after rgc-10 ends
#   rgc-15fill  the CPU embedding stores   12 CPUs, 28G, 10 h   after rgc-15 ends (28G: night only)
#   rgc-20      Qwen3-4B on the GPU         4 CPUs, 16G,  6 h   gpumem:14
#   rgc-30      Nemotron                    4 CPUs, 16G,  4 h   embed8360:1
#   rgc-40      robustness from stores      8 CPUs, 16G, 6.5 h  after 15, 15fill, 20 and 30 succeed
#   rgc-50      Table 10 reruns (Ollama)    2 CPUs,  6G, 90 min gpumem:16, after rgc-10 and rgc-20 succeed
#   rgc-50all   all ten Table 10 rows       2 CPUs,  6G, 90 min gpumem:16. Opt-in: only with --only "50all"
#   rgc-56tag-g12, rgc-56meas-g12           a fixed-window tag of gemma4:12b and one measured load of it
#                                           (gpumem:16). Opt-in: only with --only "56tag-g12 56meas-g12"
#   rgc-56g12s  Gemma 4 12B, scaffold runs  4 CPUs, 16G, 12 h   gpumem:16. Opt-in: only with --only "56g12s"
#   rgc-56g12n  Gemma 4 12B, native runs    4 CPUs, 16G, 18 h   gpumem:16, after rgc-56g12s ends.
#                                           Opt-in: only with --only "56g12n", or both names
#               (Supplement Table S1 on BEAR 0.4.2, on the fixed-window tag, beside the Qwen3.8 server.
#               In July each Gemma part took 4 to 9 h.)
#   rgc-65tag   authorship tags             2 CPUs,  8G,  7 h   chat8355:4
#   rgc-65cpu   authorship, CPU part       12 CPUs, 24G, 12 h   after the tags, after rgc-15fill ends
#   rgc-65gpu   authorship, GPU part        4 CPUs, 16G,  6 h   gpumem:14, after the tags and rgc-20
#               (2 h was too short. Job 169 embedded 2.8 queries a second on a busy card and hit
#               the limit 90% through the first of two conditions, 17 Nov. The cache keeps them.)
#   rgc-65nem   authorship, Nemotron part   2 CPUs,  8G, 90 min embed8360:1, after the tags and rgc-30
#   rgc-65an    authorship analysis         2 CPUs,  8G, 45 min after 10, 20, 30 and the three parts
#   rgc-70      assemble                    4 CPUs, 16G, 90 min after everything above ends
#   rgc-80      figure                      1 CPU,   2G, 15 min
#   rgc-90      verify and numbers          2 CPUs,  8G, 30 min after 70 and 80 end
# Every job also takes the license RGC_AFTER_HERMES (default nohermes:1). model-server's Hermes
# hold reserves all of it while a grid can run, because the grid rules allow no kit step in WSL
# beside a grid. 15 is split so its 16G part can run while Scott is at the desk (24G cap in
# all). Only the store fill, whose steps are capped at 24G each, needs 28G.
# Times are the October estimates with room for Zoom freezes, which count against the limit.
# Every job carries --comment="project=RGC; purpose=...; plan=..." (required by the queue). Jobs
# with network timeouts or GPU memory add "; nofreeze" there (throttled, never frozen). The plan
# names the kit commit, and for the authorship parts the approved plan's hash as well.
# Hermes blocks 2 and 3 and analyze are not here. They stay on 60_hermes.sh.
#
# Usage:
#   bash reproduce/slurm_submit.sh --dry-run      # print the sbatch lines, submit nothing
#   bash reproduce/slurm_submit.sh                # submit
#   bash reproduce/slurm_submit.sh --only "20 30" # submit some steps. They wait for the other
#     steps' kit jobs still queued or running, and not for steps that have no job in the queue.
#   bash reproduce/slurm_submit.sh --replace      # resubmit the kit over an earlier submission:
#     cancels this user's pending rgc-<step> kit jobs, and a step whose earlier job is still
#     running gets a new job that starts after it ends (afterany). Finished steps are skipped,
#     so a step that already completed ends at once.
#   bash reproduce/slurm_submit.sh --cancel-all   # cancel every kit job, running ones too, wait
#     until none is left, and submit nothing. Then 00_setup.sh --update can move the clones.
# Only Scott runs this (the paper says no AI agent queued an experiment). sbatch stamps origin=
# (terminal, job page or job <id>) by itself, and inside a Slurm job each kit job also gets
# parent=<id>. There is no via= or requested= here, by design (Scott, 16 Nov).
set -uo pipefail
ART=$(cd "$(dirname "$0")/.." && pwd)
DRY=0 ONLY="" REPLACE=0 CANCEL_ALL=0
while [ $# -gt 0 ]; do
  case $1 in
    -n|--dry-run) DRY=1 ;;
    --only) ONLY=" $2 "; shift ;;
    --replace) REPLACE=1 ;;
    --cancel-all) CANCEL_ALL=1 ;;
    -h|--help) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
AFTER_HERMES=${RGC_AFTER_HERMES:-nohermes:1}
OUT=${REPRO_OUT:-$HOME/tist-repro}/logs/slurm
[ "$DRY" = 1 ] || mkdir -p "$OUT"
command -v sbatch >/dev/null || [ "$DRY" = 1 ] || { echo "sbatch not found" >&2; exit 1; }
[ -z "$(git -C "$ART" status --porcelain --untracked-files=no)" ] || echo "WARNING: $ART has uncommitted changes. The jobs run what is on disk when they start."

declare -A ID PREV
want() { [ -z "$ONLY" ] || [[ $ONLY == *" $1 "* ]]; }
dep() {  # dep KIND:STEP... -> --dependency=... from the ids submitted so far
  local parts=() k s ids
  for k in "$@"; do
    ids=""
    for s in ${k#*:}; do [ -n "${ID[$s]:-}" ] && ids+=":${ID[$s]}"; done
    [ -n "$ids" ] && parts+=("${k%%:*}$ids")
  done
  [ ${#parts[@]} -gt 0 ] && (IFS=,; echo "--dependency=${parts[*]}")
}
sub() {  # sub STEP CPUS MEM TIME "LICENSES" "DEPENDENCY" "nofreeze|" CMD...  (purpose and plan from PURPOSE, PLAN)
  local step=$1 cpus=$2 mem=$3 time=$4 lic=$5 dp=$6 freeze=$7
  shift 7
  want "$step" || return 0
  local args=(--parsable --job-name="rgc-$step" --cpus-per-task="$cpus" --mem="$mem" --time="$time"
              --chdir="$ART" --output="$OUT/%x-%j.out")
  args+=(--licenses="$AFTER_HERMES${lic:+,$lic}")
  if [ -n "${PREV[$step]:-}" ]; then
    if [ -n "$dp" ]; then dp+=",afterany:${PREV[$step]}"; else dp="--dependency=afterany:${PREV[$step]}"; fi
  fi
  [ -n "$dp" ] && args+=("$dp" --kill-on-invalid-dep=yes)
  [ -n "${PURPOSE[$step]:-}" ] || { echo "no purpose for rgc-$step" >&2; exit 1; }
  args+=(--comment="project=RGC; purpose=${PURPOSE[$step]}; plan=${PLAN[$step]:-$KIT_PLAN}${freeze:+; nofreeze}${SLURM_JOB_ID:+; parent=$SLURM_JOB_ID}")
  args+=(--wrap="$*")
  if [ "$DRY" = 1 ]; then
    ID[$step]="<rgc-$step>"
    printf 'sbatch'; printf " %q" "${args[@]}"; echo
    return 0
  fi
  local id
  id=$(sbatch "${args[@]}") || { echo "sbatch failed for rgc-$step. Nothing after it was submitted." >&2; exit 1; }
  ID[$step]=${id%%;*}
  echo "rgc-$step: job ${ID[$step]}"
}

KIT_STEPS="10 15 15fill 20 30 40 50 65tag 65cpu 65gpu 65nem 65an 70 80 90"
kit_jobs() {  # job ids of this user's queued or running rgc-<step> kit jobs
  squeue -h -u "$(id -un)" -o "%i %j" 2>/dev/null | while read -r jid jname; do
    [[ " $KIT_STEPS " == *" ${jname#rgc-} "* ]] && [ "$jid" != "${SLURM_JOB_ID:-}" ] && echo "$jid"
  done
}
if [ "$CANCEL_ALL" = 1 ]; then
  ids=$(kit_jobs | tr "
" " ")
  [ -z "${ids// /}" ] && { echo "cancel-all: no kit job queued or running"; exit 0; }
  echo "cancel-all: $ids"
  [ "$DRY" = 1 ] && exit 0
  scancel $ids
  for i in $(seq 1 60); do [ -z "$(kit_jobs)" ] && { echo "cancel-all: done"; exit 0; }; sleep 10; done
  echo "cancel-all: kit jobs still listed after 10 min: $(kit_jobs | tr "
" " ")" >&2; exit 1
fi
if [ "$REPLACE" = 1 ]; then
  while read -r jid jname jstate; do
    s=${jname#rgc-}
    [[ " $KIT_STEPS " == *" $s "* ]] || continue
    want "$s" || continue
    case $jstate in
      PENDING) echo "replace: cancel pending $jname (job $jid)"; [ "$DRY" = 1 ] || scancel "$jid" ;;
      *) PREV[$s]=$jid; echo "replace: $jname (job $jid) is $jstate, the new $jname starts after it" ;;
    esac
  done < <(squeue -h -u "$(id -un)" -o "%i %j %T" 2>/dev/null)
fi
# With --only, a step submitted now still waits for the kit jobs of the other steps that are
# already queued or running (pending or running rgc-<step> jobs). Without this, --only dropped
# them, and a resubmitted rgc-70 could assemble before rgc-40 and rgc-50 ran (17 Nov).
# Steps with no job in the queue are finished or were never submitted, and no dependency is added.
if [ -n "$ONLY" ]; then
  while read -r jid jname jstate; do
    s=${jname#rgc-}
    [[ " $KIT_STEPS " == *" $s "* ]] || continue
    want "$s" && continue
    [ "$jid" = "${SLURM_JOB_ID:-}" ] && continue
    ID[$s]=$jid
    echo "only: rgc-$s is job $jid ($jstate). Steps submitted now that need it wait for it."
  done < <(squeue -h -u "$(id -un)" -o "%i %j %T" 2>/dev/null)
fi

NOFREEZE=nofreeze
KIT_PLAN="TIST reproduction kit $(git -C "$ART" rev-parse --short HEAD)"
AUTH_PLAN="authorship PLAN.md v2 sha256 834b15fb, $KIT_PLAN"
declare -A PURPOSE PLAN
PURPOSE=(
  [10]="TIST paper revision: CPU retrieval rows of Tables 6 to 9, 11 and 18 and Supplement Tables S2 to S4 on BEAR 0.4.2"
  [15]="TIST paper revision: invariant tests, budget binding, BM25 and BGE-M3 checks, WP5 BGE and CPA rows"
  [15fill]="TIST paper revision: CPU embedding stores for the tag-noise, leakage and mandatory-coverage tests"
  [20]="TIST paper revision: Qwen3-4B rows of Tables 6, 8 and 9 and the Qwen stores, on the local GPU"
  [30]="TIST paper revision: Nemotron rows of Tables 6, 8 and 9, threshold diagnosis, Nemotron stores"
  [40]="TIST paper revision: tag noise, over-restriction, leakage and coverage tests from the stores"
  [50]="TIST paper revision: Table 10 end-to-end reruns on BEAR 0.4.2 with Mistral-Nemo in Ollama"
  [50all]="TIST paper revision: all ten retrieval rows of Table 10 rerun in one session on BEAR 0.4.2 with Mistral-Nemo in Ollama"
  [56tag-g12]="TIST paper revision: make the Ollama tag gemma4-12b-131k, which only adds a 131072-token window to gemma4:12b"
  [56meas-g12]="TIST paper revision: one guarded load of gemma4-12b-131k to measure its card use and count the monolithic prompt, then unload"
  [56g12s]="TIST paper revision: Supplement Table S1 rerun on BEAR 0.4.2, Gemma 4 12B under the one-step scaffold with native reasoning off, three conditions on 1100 queries, Ollama tag gemma4-12b-131k, seed 20261120"
  [56g12n]="TIST paper revision: Supplement Table S1 rerun on BEAR 0.4.2, Gemma 4 12B with native reasoning off and on, four runs on 1100 queries, Ollama tag gemma4-12b-131k, seed 20261120"
  [65tag]="TIST authorship ablation: rewrite all tool and query tags with Qwen3.8-27B on 8355"
  [65cpu]="TIST authorship ablation: retrieval reruns with the new tags, CPU backends"
  [65gpu]="TIST authorship ablation: retrieval reruns with the new tags, Qwen3-4B on the local GPU"
  [65nem]="TIST authorship ablation: retrieval reruns with the new tags, Nemotron on 8360"
  [65an]="TIST authorship ablation: compare the two taggers by the approved plan's rules"
  [70]="TIST paper revision: assemble all kit outputs and derived numbers in the repo layout"
  [80]="TIST paper revision: draw Figure 2, the pipeline diagram"
  [90]="TIST paper revision: check outputs against the committed results and write the numbers file"
)
for s in 65tag 65cpu 65gpu 65nem 65an; do PLAN[$s]=$AUTH_PLAN; done
for s in 50all 56tag-g12 56meas-g12 56g12s 56g12n; do PLAN[$s]="end-to-end rerun PLAN.md v3 sha256 114cf0d7, $KIT_PLAN"; done
# Card gates for GPU steps under Slurm (model-server, 16 Nov). The card has 97,887 MiB. Windows' desktop
# takes about 6 GB beside the containers' 67.5 GB, so the 30 Oct start limit (67,000) cannot be met with
# Scott's windows open. Start at 97,887 - gpumem*1024 - 2,048 or less, and stop above 94,000. The Ollama
# row limit (model resident) is the same stop limit.
gate() { echo "env REPRO_GPU_START_MIB=$((97887 - $1 * 1024 - 2048)) REPRO_GPU_STOP_MIB=94000${2:+ REPRO_OLLAMA_ROW_MIB=94000}"; }
sub 10     12 24G 1-00:00:00 ""            ""                                         ""          bash reproduce/10_cpu_retrieval.sh
sub 15     12 16G 14:00:00   ""            "$(dep afterany:10)"                        ""          bash reproduce/15_cpu_invariants_baselines.sh --only "'wp256-v042 wp256-v042-bge wp256-v042-bm25 wp256-v042-bgem3 wp5-bge-cpa'"
sub 15fill 12 28G 10:00:00   ""            "$(dep afterany:15)"                        ""          bash reproduce/15_cpu_invariants_baselines.sh --only fill-cpu-stores
sub 20      4 16G 06:00:00   "gpumem:14"   ""                                         "$NOFREEZE" $(gate 14) bash reproduce/20_gpu_local_embeddings.sh
sub 30      4 16G 04:00:00   "embed8360:1" ""                                         "$NOFREEZE" bash reproduce/30_nemotron.sh
sub 40      8 16G 06:30:00   ""            "$(dep 'afterok:15 15fill 20 30')"          ""          bash reproduce/40_robustness_from_stores.sh
sub 50      2 6G  01:30:00   "gpumem:16"   "$(dep 'afterok:10 20')"                   "$NOFREEZE" $(gate 16 row) bash reproduce/50_e2e_ollama.sh
# Opt-in steps. They are submitted only when --only names them, so a plain run of the kit stays as it was.
[[ $ONLY == *" 50all "* ]] && sub 50all 2 6G 01:30:00 "gpumem:16" "" "$NOFREEZE" $(gate 16 row) bash reproduce/50_e2e_ollama.sh --all-rows
[[ $ONLY == *" 56tag-g12 "* ]] && sub 56tag-g12 1 2G 00:20:00 "" "" "" bash reproduce/56_e2e_long_context.sh tag-g12
[[ $ONLY == *" 56meas-g12 "* ]] && sub 56meas-g12 2 8G 01:00:00 "gpumem:16" "$(dep afterok:56tag-g12)" "$NOFREEZE" $(gate 16) bash reproduce/56_e2e_long_context.sh measure-g12
[[ $ONLY == *" 56g12s "* ]] && sub 56g12s 4 16G 12:00:00 "gpumem:16" "" "$NOFREEZE" $(gate 16) bash reproduce/56_e2e_long_context.sh g12-scaffold
[[ $ONLY == *" 56g12n "* ]] && sub 56g12n 4 16G 18:00:00 "gpumem:16" "$(dep afterany:56g12s)" "$NOFREEZE" $(gate 16) bash reproduce/56_e2e_long_context.sh g12-native
sub 65tag   2 8G  07:00:00   "chat8355:4"  ""                                         "$NOFREEZE" bash reproduce/65_authorship.sh --part tag
sub 65cpu  12 24G 12:00:00   ""            "$(dep afterok:65tag afterany:15fill)"      ""          bash reproduce/65_authorship.sh --part cpu
sub 65gpu   4 16G 06:00:00   "gpumem:14"   "$(dep 'afterok:65tag 20')"                 "$NOFREEZE" $(gate 14) bash reproduce/65_authorship.sh --part gpu
sub 65nem   2 8G  01:30:00   "embed8360:1" "$(dep 'afterok:65tag 30')"                 "$NOFREEZE" bash reproduce/65_authorship.sh --part nemotron
sub 65an    2 8G  00:45:00   ""            "$(dep 'afterok:10 20 30 65cpu 65gpu 65nem')" ""        bash reproduce/65_authorship.sh --part analyze
sub 70      4 16G 01:30:00   ""            "$(dep 'afterany:10 15 15fill 20 30 40 50 65an')" ""    bash reproduce/70_assemble.sh
sub 80      1 2G  00:15:00   ""            ""                                         ""          bash reproduce/80_figures.sh
sub 90      2 8G  00:30:00   ""            "$(dep 'afterany:70 80')"                   ""          bash reproduce/90_verify.sh
[ "$DRY" = 1 ] && echo "(dry run: nothing submitted. <rgc-NN> stands for that step's job id)"
[ "$DRY" = 1 ] || echo "submitted. Follow with: squeue -u $(id -un)   and   sacct -X -u $(id -un) -S today"
