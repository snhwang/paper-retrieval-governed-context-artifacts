#!/usr/bin/env python3
"""Wait on a WP7 grid (stage 1 or a stage-2 block) and exit with one line when something needs attention.

Exits on: batch_end / batch_stopped / batch_paused, a cell that errored, a provenance warning,
a flush refused for 15+ minutes, no log line for 40 minutes, the service no longer active,
or every PROGRESS_EVERY finished cells. Read-only: it never signals anything.
Usage: watch.py ROOT START_LINE PROGRESS_EVERY UNIT

START_LINE is the line of logs/cells.jsonl to start reading from (0 for all). Offline.
"""
import json
import os
import subprocess
import sys
import time

root, start, every, unit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
log = os.path.join(root, "logs", "cells.jsonl")
seen, last_size, last_change = start, -1, time.time()
done0, first_refusal = None, None
window_errors = []
while True:
    lines = open(log).read().splitlines() if os.path.exists(log) else []
    if len(lines) != last_size:
        last_size, last_change = len(lines), time.time()
    done = sum(1 for ln in lines if '"cell_done"' in ln)
    if done0 is None:
        done0 = done
    for ln in lines[seen:]:
        r = json.loads(ln)
        ev = r.get("event")
        if ev in ("batch_end", "batch_stopped", "batch_paused", "provenance_warning", "cell_not_run"):
            print(f"EVENT {ev}: {json.dumps({k: v for k, v in r.items() if k != 'fingerprint'})[:600]} (line {len(lines)})")
            sys.exit(0)
        if ev == "cell_done":
            first_refusal = None
            bad = r["returncode"] != 0
            if not bad:
                try:
                    bad = bool(json.load(open(r["out"])).get("error"))
                except Exception:
                    bad = True
            if bad:
                window_errors.append(f"{r['cell']} rc={r['returncode']}")
                if len(window_errors) >= 3:
                    print(f"EVENT error burst: {window_errors} (done {done}, line {len(lines)})")
                    sys.exit(0)
        if ev == "flush_cache":
            if r.get("http_status") == 200:
                first_refusal = None
            elif first_refusal is None:
                first_refusal = time.time()
    seen = len(lines)
    if first_refusal and time.time() - first_refusal > 900:
        print(f"EVENT flush refused for 15+ min (done {done}, line {len(lines)})")
        sys.exit(0)
    if time.time() - last_change > 2400:
        print(f"EVENT stall: no log line for 40 min (done {done}, line {len(lines)})")
        sys.exit(0)
    active = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True,
                            text=True).stdout.strip()
    if active not in ("active", "activating"):
        time.sleep(5)
        tail = open(log).read().splitlines()[seen:]
        if not any(json.loads(x).get("event") in ("batch_end", "batch_stopped", "batch_paused") for x in tail):
            print(f"EVENT service {unit} is {active} with no batch end (done {done})")
            sys.exit(0)
    if done - done0 >= every:
        print(f"PROGRESS done {done} (line {len(lines)}), errors this window: {window_errors}")
        sys.exit(0)
    time.sleep(30)
