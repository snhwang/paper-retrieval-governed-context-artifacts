#!/usr/bin/env bash
# Start the BEAR 0.4.1 work that loads no local model (coordinator, 2026-10-30).
# Lanes: nomodel (BM25, hash), attrlex (single-switch attribution on hash and
# BM25), tracklex (required_tags admissions on 0.4.0 and 0.4.1), nemo
# (Nemotron through 8360, batches of 16). Run once, in WSL.
set -u
SP=/mnt/c/Users/Scott/AppData/Local/Temp/claude/c--Users-Scott-Documents-Work-paper-retrieval-governed-context/b2a7ec29-e0cc-4cf9-a2d3-67d64780d674/scratchpad
REPO=/mnt/c/Users/Scott/Documents/Work/paper-retrieval-governed-context-artifacts
R=$HOME/tist-evals/wp0-v041
PY=$HOME/.venvs/tist-evals/bin/python
mkdir -p $R/logs $R/stage

echo "MemAvailable: $(awk '/MemAvailable/ {printf "%.1f GiB", $2/1048576}' /proc/meminfo)"
curl -s -m 5 http://localhost:8360/health; echo
$PY -c "import bear; print('bear', bear.__version__, bear.__file__)"
echo "bear-v0.4.1 clone: $(git -C $HOME/tist-evals/bear-v0.4.1 rev-parse HEAD)"

# Fresh clones of the artifacts branch tist-r2 (has the tag-order fix e593950).
for c in artifacts artifacts-attr artifacts-track; do
  [ -d $R/$c ] || git clone -q --branch tist-r2 $REPO $R/$c
  git -C $R/$c log --oneline -1
  D=$R/$c/evals/wp0_v040; mkdir -p $D/site
  for f in $SP/wp0_v040/*.py $SP/wp0_v040/*.sh; do cp $f $D/.t && sed -i 's/\r$//' $D/.t && mv $D/.t $D/$(basename $f); done
  cp $SP/wp0_v040/site/sitecustomize.py $D/site/.t && sed -i 's/\r$//' $D/site/.t && mv $D/site/.t $D/site/sitecustomize.py
  grep -q "for tool_id in sorted(expected_ids)" $R/$c/evals/eval_toolbench.py && echo "  tag fix present"
done

# The trace hook must not recurse.
grep -n "def retrieve_with_trace" -A 60 $HOME/tist-evals/bear-v0.4.1/bear/retriever.py | grep -q "self\.retrieve(" \
  && echo "WARNING: retrieve_with_trace calls retrieve; do not start tracklex" || echo "trace hook: no recursion"

# The guard must refuse a local model before anything touches the GPU.
cd $R/artifacts
CUDA_VISIBLE_DEVICES= WP0_NO_LOCAL_MODELS=1 PYTHONPATH=evals/wp0_v040/site $PY -c "
from sentence_transformers import SentenceTransformer
try:
    SentenceTransformer('BAAI/bge-base-en-v1.5'); print('GUARD FAILED')
except RuntimeError as e:
    print('guard ok:', str(e)[:60])
" 2>&1 | tail -1

for lane in nomodel nemo; do
  nohup setsid bash evals/wp0_v040/run_wp0_v040.sh $lane >> $R/logs/lane_$lane.out 2>&1 < /dev/null &
done
cd $R/artifacts-attr;  WP0_ART=$R/artifacts-attr  nohup setsid bash evals/wp0_v040/run_wp0_v040.sh attrlex  >> $R/logs/lane_attrlex.out  2>&1 < /dev/null &
cd $R/artifacts-track; WP0_ART=$R/artifacts-track nohup setsid bash evals/wp0_v040/run_wp0_v040.sh tracklex >> $R/logs/lane_tracklex.out 2>&1 < /dev/null &
sleep 5
ps -eo pid,args | grep "[r]un_wp0_v040"
tail -n 2 $R/logs/lane_*.out
