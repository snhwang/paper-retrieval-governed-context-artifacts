#!/usr/bin/env bash
# mem_guard.sh command...
#
# Runs the command in its own session and stops it if the session's resident
# memory exceeds WP0_RSS_MAX_GIB (default 24), or if WSL's MemAvailable falls
# below WP0_MEMAVAIL_MIN_GIB (default 16). Refuses to start below that
# minimum. Exit 76 means the RSS limit was hit, 77 that memory ran low. The
# peak resident memory of the session is printed at the end.
max_kib=$(( ${WP0_RSS_MAX_GIB:-24} * 1024 * 1024 ))
min_kib=$(( ${WP0_MEMAVAIL_MIN_GIB:-16} * 1024 * 1024 ))
avail() { awk '/MemAvailable/ {print $2}' /proc/meminfo; }
if (( $(avail) < min_kib )); then
  echo "### mem guard: MemAvailable $(avail) kB below the minimum, not started"
  exit 77
fi
setsid "$@" &
pid=$!
peak=0
stop() {
  echo "### mem guard: $1, stopping the step"
  kill -TERM -- "-$pid" 2>/dev/null; sleep 10; kill -KILL -- "-$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  echo "### mem guard: peak session RSS $(( peak / 1024 )) MiB"
  exit "$2"
}
while kill -0 "$pid" 2>/dev/null; do
  rss=$(ps -o rss= --sid "$pid" 2>/dev/null | awk '{s += $1} END {print s + 0}')
  (( rss > peak )) && peak=$rss
  (( rss > max_kib )) && stop "session RSS ${rss} kB over the ${WP0_RSS_MAX_GIB:-24} GiB limit" 76
  a=$(avail)
  (( a < min_kib )) && stop "MemAvailable ${a} kB below the ${WP0_MEMAVAIL_MIN_GIB:-16} GiB minimum" 77
  sleep 5
done
wait "$pid"; rc=$?
echo "### mem guard: peak session RSS $(( peak / 1024 )) MiB"
exit $rc
