#!/usr/bin/env bash
# Start the BEAR 0.4.1 work that loads no local model (coordinator, 2026-10-30).
# Lanes: nomodel (BM25, hash), attrlex (single-switch attribution on hash and
# BM25), tracklex (required_tags admissions on 0.4.0 and 0.4.1), nemo
# (Nemotron through 8360, batches of 16). Run once, in WSL.
set -u
# The artifacts repo is two levels above this script. Clones are made from it,
# and the WP0 scripts are synced from its evals/wp0_v040/ (working tree).
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SRC=$REPO/evals/wp0_v040
R=${WP0_ROOT:-$HOME/tist-evals/wp0-v041}
export WP0_ROOT=$R   # the runner's default root is the 0.4.2 one
PY=${WP0_PY:-$HOME/.venvs/tist-evals/bin/python}
mkdir -p $R/logs $R/stage
CAP=(systemd-run --user --scope --quiet --slice=tist.slice -p MemoryMax=24G -p MemorySwapMax=0)

# Every job runs under the kernel memory cap. Refuse to start without it.
if ! "${CAP[@]}" true; then
  echo "systemd-run scope in tist.slice is not available; not starting (ask the coordinator)"
  exit 1
fi
echo "memory cap: ok ($("${CAP[@]}" bash -c 'cat /proc/self/cgroup' | tail -1))"

echo "MemAvailable: $(awk '/MemAvailable/ {printf "%.1f GiB", $2/1048576}' /proc/meminfo)"
curl -s -m 5 http://localhost:8360/health; echo
$PY -c "import bear; print('bear', bear.__version__, bear.__file__)"
echo "bear-v0.4.1 clone: $(git -C $HOME/tist-evals/bear-v0.4.1 rev-parse HEAD)"

# Fresh clones of the artifacts branch tist-r2 (has the tag-order fix e593950).
for c in artifacts artifacts-attr artifacts-track; do
  [ -d $R/$c ] || git clone -q --branch tist-r2 $REPO $R/$c
  git -C $R/$c log --oneline -1
  D=$R/$c/evals/wp0_v040; mkdir -p $D/site
  for f in $SRC/*.py $SRC/*.sh; do cp $f $D/.t && sed -i 's/\r$//' $D/.t && mv $D/.t $D/$(basename $f); done
  cp $SRC/site/sitecustomize.py $D/site/.t && sed -i 's/\r$//' $D/site/.t && mv $D/site/.t $D/site/sitecustomize.py
  grep -q "for tool_id in sorted(expected_ids)" $R/$c/evals/eval_toolbench.py && echo "  tag fix present"
done

# The trace hook must not recurse.
grep -n "def retrieve_with_trace" -A 60 $HOME/tist-evals/bear-v0.4.1/bear/retriever.py | grep -q "self\.retrieve(" \
  && echo "WARNING: retrieve_with_trace calls retrieve; do not start tracklex" || echo "trace hook: no recursion"

# The guard must refuse a local model before anything touches the GPU.
cd $R/artifacts
CUDA_VISIBLE_DEVICES= WP0_NO_LOCAL_MODELS=1 PYTHONPATH=evals/wp0_v040/site "${CAP[@]}" $PY -c "
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
