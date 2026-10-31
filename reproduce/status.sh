#!/usr/bin/env bash
# status.sh: what the kit is doing now, and how each script last ended.
#
# Shows the kit's user services (tist-repro-*), the WP0 lane and WP7 grid services,
# the last lines of each script's log, the latest run record of each script with
# its status, and the card reading. Reads only: it starts and stops nothing, and
# sends no request to any server.
#
# Usage: bash reproduce/status.sh [LINES]   (LINES of each log, default 3)
set -u
REPRO_OUT=${REPRO_OUT:-$HOME/tist-repro}
N=${1:-3}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
echo "== services"
systemctl --user list-units --type=service --all --no-legend 'tist-repro-*' 'wp0-*' 'tist-wp7-*' 2>/dev/null \
  | awk '{printf "  %-28s %s %s\n", $1, $3, $4}'
echo "== logs ($REPRO_OUT/logs)"
for f in "$REPRO_OUT"/logs/*.log; do
  [ -f "$f" ] || continue
  echo "  $(basename "$f"):"
  tail -n "$N" "$f" | sed 's/^/    /'
done
echo "== latest run record per script ($REPRO_OUT/runlog)"
for s in $(ls "$REPRO_OUT"/runlog/*.json 2>/dev/null | sed -E 's#.*/##; s#-[0-9]{8}T[0-9]{6}Z\.json$##' | sort -u); do
  f=$(ls -t "$REPRO_OUT"/runlog/"$s"-*.json | head -1)
  python3 - "$f" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print(f"  {r['script']:32} {r.get('status'):8} start {r.get('start_utc')} end {r.get('end_utc') or '-'}"
      f" exit {r.get('exit_code')} {('(' + r['failure_reason'] + ')') if r.get('failure_reason') else ''}")
PY
done
smi=/mnt/c/Windows/System32/nvidia-smi.exe
[ -x "$smi" ] && echo "== card: $("$smi" --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1 | tr -d '\r')"
echo "== slice: $(systemctl --user show tist.slice -p MemoryCurrent --value 2>/dev/null | awk '{printf "%.1f GiB in use (page cache included)", $1/1073741824}')"
