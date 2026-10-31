"""Run a RemoteEmbedder call inside a cell sandbox, through the runner's own sandbox code."""
import os
import subprocess
import sys

H = os.environ.get("WP7_HERMES_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
sys.path.insert(0, H)
import run  # noqa: E402
import arms  # noqa: E402

r = run.Run(os.path.join(RUNS, "stage1-sandbox-test"), sandbox="bwrap")
code = ("import time, urllib.request, json\n"
        "from bear.remote_embedder import RemoteEmbedder\n"
        "print(urllib.request.urlopen('http://localhost:8360/health', timeout=5).read()[:60])\n"
        "for n in (1, 5, 64, 327):\n"
        "    t = [f'tool {i}: ' + 'words ' * 30 for i in range(n)]\n"
        "    for url in ('http://localhost:8360', 'http://127.0.0.1:8360'):\n"
        "        try:\n"
        "            t0 = time.time(); v = RemoteEmbedder(url).embed(t, is_query=False)\n"
        "            print(n, url, 'ok', len(v), round(time.time() - t0, 2))\n"
        "        except Exception as e:\n"
        "            print(n, url, 'FAIL', type(e).__name__, str(e)[:160])\n")
cell = "embedtest"
cmd, host = r.sandboxed(cell, [sys.executable, "-c", code], 0)
env = r.sandbox_env("/dev/null", arms.Switches(), cell, False)
p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=r.cell_dir(cell), timeout=300)
host.terminate()
print(p.returncode)
print(p.stdout[-3000:])
print(p.stderr[-2000:])
