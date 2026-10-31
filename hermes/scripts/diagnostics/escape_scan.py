"""List tool calls in WP7 transcripts that reach outside the cell. Masks token-like strings.

Usage: escape_scan.py OUT_TXT
"""
import glob
import json
import os
import re
import sys
from collections import Counter

RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
HOME = re.escape(os.path.expanduser("~"))
files = sorted(glob.glob(os.path.join(RUNS, "*", "results", "*.transcript.json"))
               + glob.glob(os.path.expanduser("~/tist-spike/**/*.transcript.json"), recursive=True))
PAT = {
    "home-path": HOME + r"(?!/(tist-|wp7-))",
    "tist-path": HOME + r"/(tist-|wp7-)",
    "dotdirs": r"(~|\$HOME)/\.(config|ssh|venvs|hermes|cache|local|netrc|gitconfig|claude|aws|docker|npm)",
    "mnt": r"/mnt/",
    "docker": r"\bdocker\b|docker\.sock",
    "windows-exe": r"cmd\.exe|powershell|pwsh|wsl\.exe|\.exe\b",
    "pkg-install": r"pip3? install|-m pip|\buv (pip|add|sync|tool|run)|\bapt(-get)? |npm (i|install)|\bnpx\b|sync_venv",
    "tmux/daemon": r"\btmux\b|\bnohup\b|\bsetsid\b|\bdisown\b|\bsystemctl\b|\bcrontab\b",
    "kill": r"\b(kill|pkill|killall)\b",
    "sudo": r"\bsudo\b",
    "gh-cli": r"(^|[;&|\s(\"])gh\s",
    "hermes-cli": r"(^|[;&|\s(\"])hermes\s",
    "net-egress": r"(curl|wget|urllib|requests\.|httpx|http\.client|urlopen)[^\n]*https?://(?!(localhost|127\.0\.0\.1))",
    "url": r"https?://(?!(localhost|127\.0\.0\.1))[A-Za-z0-9.-]+",
}
tok = re.compile(r"(gh[opsur]_|github_pat_)[A-Za-z0-9_]{4,}")
rows = []
for f in files:
    run = os.path.relpath(f, RUNS).split(os.sep)[0] if f.startswith(RUNS) else "tist-spike"
    cell = os.path.basename(f).replace(".json.transcript.json", "").replace(".transcript.json", "")
    msgs = (json.load(open(f)) or {}).get("messages") or []
    for i, m in enumerate(msgs):
        for tc in m.get("tool_calls") or []:
            name = tc["function"]["name"]
            a = tc["function"].get("arguments") or ""
            if name in ("web_search", "web_extract"):
                rows.append((run, cell, i, name, ["internet-tool"], a))
                continue
            hit = [k for k, p in PAT.items() if re.search(p, a)]
            if hit:
                rows.append((run, cell, i, name, hit, a))
with open(sys.argv[1], "w") as fh:
    for run, cell, i, name, hit, a in rows:
        body = tok.sub("<tok>", a)[:700].replace("\n", " | ")
        fh.write(f"{run} :: {cell} | msg {i} | {name} | {','.join(hit)}\n    {body}\n")
print(len(files), "transcripts,", len(rows), "flagged calls")
print("by run:", Counter(r[0] for r in rows).most_common())
print("by cell:")
for (run, cell), n in Counter((r[0], r[1]) for r in rows).most_common():
    kinds = Counter(k for r in rows if (r[0], r[1]) == (run, cell) for k in r[4])
    print(f"  {run} :: {cell[:60]}  {n} calls  {dict(kinds)}")
