"""Preflight: lint the WP7 corpus at each decoy size and validate every arm's settings against the
installed BEAR's plugin Settings. Offline, no model or embedder call.

Usage: $WP7_PY validate.py   (reads arms.py and the corpus from WP7_HARNESS_DIR, default ../)
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERMES = os.environ.get("WP7_HARNESS_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)
import arms  # noqa: E402
import bear  # noqa: E402
from bear.corpus import Corpus  # noqa: E402
from bear.integrations.hermes.settings import Settings  # noqa: E402

print("bear", bear.__version__, bear.__file__)
root = tempfile.mkdtemp(prefix="wp7-preflight-")
rc_all = 0
for n in (0, 100, 300):
    d = os.path.join(root, f"d{n}")
    os.makedirs(d)
    shutil.copy2(arms.BASE_CORPUS, os.path.join(d, "tools.yaml"))
    if n:
        shutil.copy2(arms.DECOY_CORPUS.format(n=n), os.path.join(d, "decoys.yaml"))
    c = Corpus.from_directory(d)
    p = subprocess.run([sys.executable, "-m", "bear.integrations.hermes", "lint", d],
                       capture_output=True, text=True)
    print(f"== d{n}: {len(c)} instructions, lint rc={p.returncode}")
    print((p.stdout + p.stderr).strip()[-1500:])
    rc_all |= p.returncode
    for arm in ("A", "B", "C-gate", "D"):
        for role in ("operator", "guest"):
            sw = arms.Switches(role=role, decoys=n)
            cfg = arms.hermes_config(arm, sw, corpus_dir=d, audit_path=os.path.join(root, "a.jsonl"),
                                     embedding_revision="sha256:test")
            s = Settings.from_mapping(cfg["plugins"]["entries"]["bear"]["settings"])
            assert s.narrow_top_k is None and s.withheld_names_max is None
            assert s.always_offer == ["clarify"] and s.narrow_scope == "turn"
            assert s.annotate_tools is False
print("settings: all 24 arm x role x decoy configs validate")
shutil.rmtree(root)
sys.exit(rc_all)
