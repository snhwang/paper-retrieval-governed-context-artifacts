"""Reproduce the bridge failure: BEAR's RemoteEmbedder through host+inside bridges on test ports."""
import os
import subprocess
import sys
import time

H = os.environ.get("WP7_HERMES_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
d = os.path.join(RUNS, "scratch", "bridge-test")
os.makedirs(d, exist_ok=True)
sock = os.path.join(d, "8360.sock")
host = subprocess.Popen([sys.executable, f"{H}/sandbox_bridge.py", "host", f"{sock}=127.0.0.1:8360"])
time.sleep(1)
inside = subprocess.Popen([sys.executable, f"{H}/sandbox_bridge.py", "serve-inside", f"18360={sock}"])
time.sleep(1)
from bear.remote_embedder import RemoteEmbedder  # noqa: E402
import yaml  # noqa: E402

texts = [f"tool number {i}: " + "description words " * 30 for i in int(sys.argv[1]) * [0]] if False else \
    [f"tool number {i}: " + "description words " * 30 for i in range(int(sys.argv[1]))]
for url in ("http://localhost:8360", "http://localhost:18360"):
    try:
        e = RemoteEmbedder(url)
        t0 = time.time()
        v = e.embed(texts, is_query=False)
        print(url, "ok", len(v), round(time.time() - t0, 2))
    except Exception as ex:
        print(url, "FAIL", type(ex).__name__, str(ex)[:200])
host.terminate()
inside.terminate()
