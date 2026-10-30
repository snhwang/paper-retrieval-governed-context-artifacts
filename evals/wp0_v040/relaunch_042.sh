#!/usr/bin/env bash
# Start the BEAR 0.4.2 WP0 lanes (coordinator, 2026-10-30). Run in WSL.
#   bash relaunch_042.sh            preflight, clones, then lex042 + attrpet042 + nemo042
#   bash relaunch_042.sh LANE ...   start the named lanes only (clones must exist)
# Lanes run as tist-capped services (survive wsl.exe exiting), and every step
# inside them runs in its own capped scope (runner: WP0_STEP_MEM, default 8G).
set -u
SP=/mnt/c/Users/Scott/AppData/Local/Temp/claude/c--Users-Scott-Documents-Work-paper-retrieval-governed-context/b2a7ec29-e0cc-4cf9-a2d3-67d64780d674/scratchpad
REPO=/mnt/c/Users/Scott/Documents/Work/paper-retrieval-governed-context-artifacts
R=$HOME/tist-evals/wp0-v042
PY=$HOME/.venvs/tist-evals/bin/python
TC=$HOME/bin/tist-capped
mkdir -p $R/logs $R/stage

sync_clone() {  # clone of tist-r2 plus this session's scripts
  local c=$1
  [ -d $R/$c ] || git clone -q --branch tist-r2 $REPO $R/$c
  local D=$R/$c/evals/wp0_v040; mkdir -p $D/site
  for f in $SP/wp0_v040/*.py $SP/wp0_v040/*.sh; do cp $f $D/.t && sed -i 's/\r$//' $D/.t && mv $D/.t $D/$(basename $f); done
  cp $SP/wp0_v040/site/sitecustomize.py $D/site/.t && sed -i 's/\r$//' $D/site/.t && mv $D/site/.t $D/site/sitecustomize.py
  echo "$c: $(git -C $R/$c log --oneline -1), tag fix: $(grep -c 'for tool_id in sorted(expected_ids)' $R/$c/evals/eval_toolbench.py)"
}

start_lane() {  # lane clone [extra env...]
  local lane=$1 clone=$2; shift 2
  ( cd $R/$clone && env WP0_ART=$R/$clone "$@" $TC --mem 2G --service wp0-$lane -- \
      bash -c "bash evals/wp0_v040/run_wp0_v040.sh $lane >> $R/logs/lane_$lane.out 2>&1" )
  echo "started service wp0-$lane"
}

if [ $# -gt 0 ]; then
  for lane in "$@"; do
    case $lane in
      lex042) start_lane lex042 artifacts ;;
      attrpet042) start_lane attrpet042 artifacts-attr ;;
      attrtb042) start_lane attrtb042 artifacts-track ;;
      nemo042) start_lane nemo042 artifacts-nemo ;;
      dense042) sync_clone artifacts-dense
                start_lane dense042 artifacts-dense WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=20G \
                    WP0_ENCODE_BATCH=4 WP0_CPU_THREADS=12 ;;
      gpuq4b042)  # card gates agreed with model-server (2026-10-30): start at 67,000 MiB or
                  # less, stop the step above 80,000. Never beside the Ollama rerun.
                 if systemctl --user is-active -q wp0-e2erun; then echo "e2e rerun active, not started"; exit 75; fi
                 sync_clone artifacts-gpu
                 start_lane gpuq4b042 artifacts-gpu WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=12G \
                     WP0_ENCODE_BATCH=8 WP0_GPU_CAP_FIXED=11.2 WP0_WIN_GPU_MAX_MIB=67000 \
                     WP0_WIN_GPU_STOP_MIB=80000 ;;
      e2erun)  # Table 7 executor rerun on Ollama (mistral-nemo-32k): 67,000 MiB before
               # loading, 81,000 before each later row. Never beside the Qwen3-4B lane.
               if systemctl --user is-active -q wp0-gpuq4b042; then echo "Qwen3-4B lane active, not started"; exit 75; fi
               sync_clone artifacts
               ( cd $R/artifacts && $TC --mem 4G --service wp0-e2erun -- env WP0_WIN_GPU_MAX_MIB=67000 \
                   WP0_WIN_GPU_ROW_MAX_MIB=81000 bash evals/wp0_v040/run_e2e_rerun.sh mistral-nemo )
               echo "started service wp0-e2erun" ;;
      mand042) sync_clone artifacts-nemo
               start_lane mand042 artifacts-nemo WP0_STEP_MEM=4G ;;
      pair042) sync_clone artifacts-nemo
               start_lane pair042 artifacts-nemo WP0_STEP_MEM=4G ;;
      e2eattr042) sync_clone artifacts-nemo
                  start_lane e2eattr042 artifacts-nemo WP0_STEP_MEM=4G ;;
      manddense042) sync_clone artifacts-nemo
                    start_lane manddense042 artifacts-nemo WP0_ALLOW_LOCAL_MODELS=1 WP0_STEP_MEM=20G \
                        WP0_ENCODE_BATCH=4 WP0_CPU_THREADS=12 ;;
      *) echo "unknown lane $lane" ;;
    esac
  done
  exit 0
fi

echo "MemAvailable: $(awk '/MemAvailable/ {printf "%.1f GiB", $2/1048576}' /proc/meminfo)"
systemctl --user show tist.slice -p MemoryMax -p MemoryCurrent 2>/dev/null
curl -s -m 5 http://localhost:8360/health; echo
for c in artifacts artifacts-attr artifacts-track artifacts-nemo; do sync_clone $c; done

cd $R/artifacts
# Preflight inside a capped scope: 0.4.2 installed and equal to the export, the
# 0.4.2 switches present, local models refused unless allowed.
$TC --mem 4G -- env CUDA_VISIBLE_DEVICES= PYTHONPATH=evals/wp0_v040/site $PY evals/wp0_v040/verify_env.py \
    --export $HOME/tist-evals/bear-9d085b4 --expect-sha 9d085b4 --expect-version 0.4.2 \
    --out /tmp/wp0_verify_042.json | tail -1
$TC --mem 4G -- env CUDA_VISIBLE_DEVICES= $PY -c "
from bear import Config
f = sorted(x for x in Config.model_fields if x.startswith('restore_'))
print('switches:', f)
assert {'restore_flat_backfill', 'restore_dropped_rows', 'restore_tie_order'} <= set(f)
"
$TC --mem 4G -- env CUDA_VISIBLE_DEVICES= WP0_NO_LOCAL_MODELS=1 PYTHONPATH=evals/wp0_v040/site $PY -c "
from sentence_transformers import SentenceTransformer
try:
    SentenceTransformer('BAAI/bge-base-en-v1.5'); print('GUARD FAILED')
except RuntimeError as e:
    print('guard ok')
" 2>&1 | tail -1
grep -n "def retrieve_with_trace" -A 60 $HOME/tist-evals/bear-9d085b4/bear/retriever.py | grep -q "self\.retrieve(" \
  && echo "note: retrieve_with_trace calls retrieve (trace hook unsafe)" || echo "trace hook: no recursion"

start_lane lex042 artifacts
start_lane attrpet042 artifacts-attr
start_lane nemo042 artifacts-nemo
sleep 5
systemctl --user list-units 'wp0-*' --no-legend
tail -n 3 $R/logs/lane_*.out
