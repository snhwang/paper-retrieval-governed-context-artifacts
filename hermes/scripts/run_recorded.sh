#!/bin/bash
# Run one command under a run record (scripts/run_record.py).
#
#   run_recorded.sh [--record PATH] [--root DIR] [--unit UNIT] NAME -- CMD ARGS...
#
# Writes the start of the record, runs CMD, then writes the end with CMD's exit code. A SIGTERM
# (systemctl --user stop) is passed on to CMD, and the record still gets its end. The launch
# scripts run their grid service through this wrapper. Use it by hand for any other step.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
record="" root="" unit=""
while [ $# -gt 0 ]; do
  case "$1" in
    --record) record=$2; shift 2 ;;
    --root) root=$2; shift 2 ;;
    --unit) unit=$2; shift 2 ;;
    --) shift; break ;;
    *) name=$1; shift ;;
  esac
done
[ $# -gt 0 ] && [ -n "${name:-}" ] || { echo "usage: run_recorded.sh [--record PATH] [--root DIR] [--unit UNIT] NAME -- CMD ..." >&2; exit 2; }
mkdir -p "$WP7_RECORDS"
[ -n "$record" ] || record="$WP7_RECORDS/$(date -u +%Y%m%dT%H%M%SZ)_${name}.json"
python3 "$WP7_SCRIPTS/run_record.py" start "$record" --name "$name" --root "$root" --unit "$unit" \
  --cwd "$PWD" -- "$@"
echo "run record: $record"
"$@" &
child=$!
note=""
trap 'note="stopped by SIGTERM"; kill -TERM "$child" 2>/dev/null' TERM
trap 'note="stopped by SIGINT"; kill -INT "$child" 2>/dev/null' INT
wait "$child"; rc=$?
while kill -0 "$child" 2>/dev/null; do wait "$child"; rc=$?; done
python3 "$WP7_SCRIPTS/run_record.py" end "$record" --exit-code "$rc" --note "$note"
echo "run record: $record (exit $rc${note:+, $note})"
exit "$rc"
