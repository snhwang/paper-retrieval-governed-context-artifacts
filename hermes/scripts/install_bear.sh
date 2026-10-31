#!/bin/bash
# Install a public BEAR release, editable, into the runner venv.
#
#   install_bear.sh v0.4.1    (stage 1)
#   install_bear.sh v0.4.2    (stage 2, and ksweep and annotation cost)
#
# Clones the tag into $WP7_BEAR_BASE/bear-<tag> (once), checks the commit against the expected
# sha, writes BEAR_GIT_SHA and BEAR_GIT_LOG into the clone (provenance reads them), installs it
# with uv (the venv has no pip, and --no-deps keeps every other package as it is), then prints
# the version, path and sha the venv now imports. Needs network access to GitHub. No model or
# embedder server is contacted.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
WP7_SCRIPT_ARGS=("$@")
tag=${1:?usage: install_bear.sh v0.4.1|v0.4.2}
case "$tag" in
  v0.4.1) expect=fa87fc554fd394ce52b09ffa8121d36fc3758f28 ;;
  v0.4.2) expect=0d0718a39a0b0788ef5cca4689352462b830494c ;;
  *) echo "unknown tag $tag (stage 1 used v0.4.1, stage 2 v0.4.2)"; exit 2 ;;
esac
wp7_record_begin "install-bear-$tag"
dir="$WP7_BEAR_BASE/bear-$tag"
if [ ! -d "$dir/.git" ]; then
  git clone --depth 1 --branch "$tag" https://github.com/snhwang/bear.git "$dir" || exit 1
fi
sha=$(git -C "$dir" rev-parse HEAD)
if [ "$sha" != "$expect" ]; then
  echo "FAIL: $dir is at $sha, expected $expect"
  exit 1
fi
git -C "$dir" rev-parse HEAD > "$dir/BEAR_GIT_SHA"
git -C "$dir" log -1 --format="%H %cI %s" > "$dir/BEAR_GIT_LOG"
uv pip install --python "$WP7_PY" --no-deps --reinstall -e "$dir" || exit 1
"$WP7_PY" - "$expect" <<'EOF'
import importlib.metadata as md, os, sys
import bear
root = os.path.dirname(os.path.dirname(bear.__file__))
sha = open(os.path.join(root, "BEAR_GIT_SHA")).read().strip()
print(f"bear {md.version('bear')} at {root}, sha {sha}")
sys.exit(0 if sha == sys.argv[1] else 1)
EOF
