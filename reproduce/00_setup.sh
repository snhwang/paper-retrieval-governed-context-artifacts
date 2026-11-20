#!/usr/bin/env bash
# 00_setup.sh: one-time setup for the reproduction kit. Run it first.
#
# Reproduces: nothing. It prepares and checks what every later script needs.
#   1. tools: git, curl, python3, uv, systemd-run, flock
#   2. ~/bin/tist-capped (installed from reproduce/bin if missing) and tist.slice
#      (MemoryMax 40G, MemorySwapMax 0, linger, memory controller delegated)
#   3. BEAR v0.4.2 cloned to ~/tist-evals/bear-v0.4.2 with a BEAR_GIT_SHA file,
#      and BEAR v0.1.10 cloned to ~/tist-evals/bear-v0110 (the 0.1.10 control
#      steps of the WP0 lanes and the previous-version scripts use it). The
#      wrapped runners read these two paths, so they are fixed.
#   4. the kit's venv (REPRO_VENV, default ~/.venvs/tist-repro, Python 3.12):
#      requirements.txt without its bear line and its vLLM block, then BEAR
#      installed from the v0.4.2 clone. The venv has no pip: uv installs.
#   5. the Hugging Face models and the tiktoken file, which every run reads
#      offline (--download-models fetches what is missing, with network)
#   6. clones of this repo below REPRO_OUT (the WP0 lane clones, and one each
#      for WP1/2/5/6, Hermes, the previous-version scripts and the authorship ablation). Every run
#      happens in a clone, never in this checkout.
#   7. evals/wp0_v040/verify_env.py: the installed BEAR equals the v0.4.2 source
#      (0d0718a, version 0.4.2), and the Nemotron server names itself
#   8. the model-load guard: with WP0_NO_LOCAL_MODELS set, a model load fails
#
# Prerequisites: WSL Ubuntu 24.04 with systemd, network access (GitHub, and
#   Hugging Face with --download-models), the Nemotron server on 8360 for step 7
#   (one GET of /health. --skip-verify skips step 7).
# Resources: CPU only. No GPU, no model load.
# Time: about 15 minutes with an empty venv, 1 minute after that. Model downloads
#   (--download-models) add about 30 GB and their own time.
# Outputs: $REPRO_OUT/setup/ (verify_env.json, requirements file), the clones in
#   $REPRO_OUT/wp0/ and $REPRO_OUT/clones/, the venv, the run record in
#   $REPRO_OUT/runlog/.
#
# Usage:
#   bash reproduce/00_setup.sh [--dry-run] [--download-models] [--configure-slice] [--skip-verify]
#   bash reproduce/00_setup.sh --update [--dry-run]
#   --configure-slice  run: systemctl --user set-property tist.slice MemoryMax=40G MemorySwapMax=0
#   --update           only bring every existing clone up to tist-r2 of this checkout (a fast-forward
#                      merge), before a later window. It refuses while any kit step, WP0 lane or WP7
#                      grid runs, and for a clone with local changes outside results/. Commit first,
#                      in this checkout, whatever the clones should get. Outputs of earlier runs stay.
#   --update-clone=artifacts-authorship
#                      the same for that one clone, which only 65_authorship.sh uses. It refuses
#                      only while a 65_authorship step runs, so other steps can keep running
#                      (added 17 Nov for the tagger's count fix while rgc-20 ran).
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

DOWNLOAD=0 UPDATE=0 CONFSLICE=0 SKIPVERIFY=0 ONE_CLONE=""
for a in "${ARGS_REST[@]}"; do
  case $a in
    --download-models) DOWNLOAD=1 ;;
    --update|--update-clones) UPDATE=1 ;;
    --update-clone=*) UPDATE=1; ONE_CLONE=${a#*=} ;;
    --configure-slice) CONFSLICE=1 ;;
    --skip-verify) SKIPVERIFY=1 ;;
    *) die "unknown option $a (see --help)" ;;
  esac
done
repro_begin

# The clones every later script uses. WP0 clone names are the ones
# run_wp0_v040.sh and run_e2e_rerun.sh expect below WP0_ROOT.
WP0_CLONES="artifacts artifacts-dense artifacts-nemo artifacts-gpu artifacts-attr artifacts-track"
OTHER_CLONES="$WP256_CLONE $HERMES_CLONE $PREV_CLONE $AUTH_CLONE"
# Files a clone must hold. Some were written late in the revision. A clone
# made before they were committed lacks them.
REQUIRED_IN_CLONE="evals/wp0_v040/run_wp0_v040.sh evals/wp0_v040/run_e2e_rerun.sh evals/wp0_v040/e2e_rerun.py
evals/wp0_v040/verify_env.py evals/wp0_v040/assemble_v040.py evals/run_wp256.sh evals/run_v042_rerun.sh
evals/run_v042_wp5.sh evals/run_qwen_gpu.sh evals/gpu_guard.sh evals/tistr2_common.py
evals/rerun_filter_baseline_bear_cached.py hermes/REPRODUCE.md hermes/scripts/env.sh reproduce/lib/common.sh
evals/authorship_regenerate.py evals/authorship/tag.py"
BR=${REPRO_BRANCH:-tist-r2}

# ---------------------------------------------------------------------------
# --update: fast-forward the clones, nothing else.
update_clone() {
  local d=$1 old new local_changes f missing=""
  if [ ! -d "$d/.git" ]; then
    say "no clone $d yet. A full run of 00_setup.sh makes it (and skips what exists)"
    return 0
  fi
  local_changes=$(git -C "$d" status --porcelain --untracked-files=no | awk '{print $2}'                   | grep -vE '^(results|evals/results)/' || true)
  [ -z "$local_changes" ] || die "$d has local changes outside results/, so it is not updated:
$local_changes"
  old=$(git -C "$d" rev-parse --short HEAD)
  run_cmd "fetch-$(basename "$d")" -C "$d" -- git fetch -q "$ART" "$BR" || die "could not fetch $BR from $ART into $d"
  # A result file that a run of yours changed, and that the new commits change too, stops the
  # fast-forward. When your copy already equals the new committed one, or the kit moved the committed
  # copy aside, the committed copy is restored first. The merge then brings in the same content.
  if [ "$DRY_RUN" = 0 ]; then
    local both g
    both=$(comm -12 <(git -C "$d" status --porcelain --untracked-files=no | awk '{print $2}' | sort) \
                    <(git -C "$d" diff --name-only HEAD FETCH_HEAD | sort))
    for g in $both; do
      if [ ! -e "$d/$g" ] || [ "$(git -C "$d" hash-object "$d/$g")" = "$(git -C "$d" rev-parse "FETCH_HEAD:$g" 2>/dev/null)" ]; then
        git -C "$d" checkout -q -- "$g" || die "could not restore $g in $d"
        say "$d: $g restored before the update (your copy equals the new committed one, or was moved aside)"
      else
        die "$d: your $g differs from the new committed copy, so $d is not updated"
      fi
    done
  fi
  run_cmd "merge-$(basename "$d")" -C "$d" -- git merge -q --ff-only FETCH_HEAD     || die "could not fast-forward $d. A new commit may touch a result file a run of yours changed (see git -C $d status)."
  [ "$DRY_RUN" = 1 ] && return 0
  new=$(git -C "$d" rev-parse --short HEAD)
  for f in $REQUIRED_IN_CLONE; do [ -e "$d/$f" ] || missing+=" $f"; done
  [ -z "$missing" ] || die "$d still lacks:$missing (commit them in $ART first)"
  say "$d: $old -> $new"
  record_note "clone $d updated from $old to $new"
}
if [ "$UPDATE" = 1 ]; then
  dirty=$(git -C "$ART" status --porcelain --untracked-files=no -- evals hermes reproduce requirements.txt)
  [ -z "$dirty" ] || warn "this checkout has uncommitted changes under evals/, hermes/ or reproduce/. The clones get the committed state only:
$dirty"
  if [ -n "$ONE_CLONE" ]; then
    case $ONE_CLONE in
      artifacts-authorship) d=$AUTH_CLONE users='65_authorship|tist-repro-65' ;;
      *) die "--update-clone takes artifacts-authorship only. Use --update for every clone." ;;
    esac
    say "update: $d only, to $BR of $ART ($(git -C "$ART" rev-parse --short "$BR"))"
    activity=$(kit_activity | grep -E "$users" || true)
    [ -z "$activity" ] || die "a step that uses $d is running, so it stays as it is. Wait for it to end:
$activity"
    update_clone "$d"
    REPRO_OK_NOTE="clone $d updated to $BR $(git -C "$ART" rev-parse --short "$BR")"
    exit 0
  fi
  say "update: every clone below $REPRO_OUT to $BR of $ART ($(git -C "$ART" rev-parse --short "$BR"))"
  activity=$(kit_activity)
  [ -z "$activity" ] || die "a step is running, so the clones stay as they are. Wait for it to end:
$activity"
  for c in artifacts artifacts-dense artifacts-nemo artifacts-gpu artifacts-attr artifacts-track; do
    update_clone "$WP0_DIR/$c"
  done
  for d in "$WP256_CLONE" "$HERMES_CLONE" "$PREV_CLONE" "$AUTH_CLONE"; do update_clone "$d"; done
  REPRO_OK_NOTE="clones updated to $BR $(git -C "$ART" rev-parse --short "$BR")"
  exit 0
fi

# ---------------------------------------------------------------------------
say "1. tools"
need_cmd git curl python3 systemd-run systemctl flock awk sed
UV=$(command -v uv || echo "$HOME/.local/bin/uv")
[ -x "$UV" ] || die "uv not found (PATH or ~/.local/bin/uv). Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
say "uv: $UV ($("$UV" --version 2>/dev/null))"
[ -n "${WSL_DISTRO_NAME:-}" ] || warn "WSL_DISTRO_NAME is unset: this does not look like WSL"
[ -e "$SMI" ] || warn "$SMI not found: the GPU scripts read the card through it"

# ---------------------------------------------------------------------------
say "2. memory cap wrapper and tist.slice"
if [ ! -x "$TC" ]; then
  run_cmd install-tist-capped -- install -D -m 755 "$REPRO_DIR/bin/tist-capped" "$TC" || die "could not install $TC"
elif ! cmp -s "$TC" "$REPRO_DIR/bin/tist-capped"; then
  warn "$TC differs from $REPRO_DIR/bin/tist-capped. Left as it is. Compare them with: diff $TC $REPRO_DIR/bin/tist-capped"
else
  say "$TC is the kit's copy"
fi
if [ "$CONFSLICE" = 1 ]; then
  run_cmd configure-slice -- systemctl --user set-property tist.slice MemoryMax=40G MemorySwapMax=0 \
    || die "could not set the tist.slice properties"
fi
if [ "$DRY_RUN" = 0 ]; then
  check_slice
  [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" = yes ] \
    || die "linger is off: user services stop when the last session ends. Run once: sudo loginctl enable-linger $(id -un)"
  say "tist.slice: MemoryMax 40G, no swap, linger on, memory controller delegated"
else
  echo "+ (check: tist.slice MemoryMax=40G MemorySwapMax=0, linger on, memory controller delegated)"
fi

# ---------------------------------------------------------------------------
say "3. BEAR sources"
clone_tag() {  # clone_tag DIR TAG SHA
  local dir=$1 tag=$2 sha=$3
  if [ ! -d "$dir/.git" ]; then
    run_cmd "clone-bear-$tag" -- git clone -q --branch "$tag" "$BEAR_URL" "$dir" || die "could not clone BEAR $tag"
  fi
  [ "$DRY_RUN" = 1 ] && return 0
  [ "$(git -C "$dir" rev-parse HEAD)" = "$sha" ] || die "$dir is at $(git -C "$dir" rev-parse HEAD), not $tag ($sha)"
  [ -z "$(git -C "$dir" status --porcelain --untracked-files=no)" ] || die "$dir has local changes"
  say "$dir is $tag ($sha), clean"
}
clone_tag "$BEAR_SRC" "$BEAR_TAG" "$BEAR_SHA"
if [ "$DRY_RUN" = 0 ]; then
  if [ -f "$BEAR_SRC/BEAR_GIT_SHA" ]; then
    [ "$(cat "$BEAR_SRC/BEAR_GIT_SHA")" = "$BEAR_SHA" ] || die "$BEAR_SRC/BEAR_GIT_SHA does not hold $BEAR_SHA"
  else
    git -C "$BEAR_SRC" rev-parse HEAD > "$BEAR_SRC/BEAR_GIT_SHA"
    record_note "wrote $BEAR_SRC/BEAR_GIT_SHA from git rev-parse HEAD"
  fi
else
  echo "+ git -C $BEAR_SRC rev-parse HEAD > $BEAR_SRC/BEAR_GIT_SHA   (if missing)"
fi
clone_tag "$BEAR0110_SRC" "$BEAR0110_TAG" "$BEAR0110_SHA"

# ---------------------------------------------------------------------------
say "4. the kit's venv ($REPRO_VENV)"
REQ=$REPRO_OUT/setup/requirements-nobear-novllm.txt
if [ ! -x "$REPRO_PY" ]; then
  run_cmd make-venv -- "$UV" venv --python 3.12 "$REPRO_VENV" || die "uv venv failed"
  if [ "$DRY_RUN" = 0 ]; then
    mkdir -p "$(dirname "$REQ")"
    # requirements.txt without the bear line (installed from the clone below)
    # and without the vLLM block (no reported result uses vLLM).
    grep -vE '^(bear|vllm|flashinfer)' "$ART/requirements.txt" > "$REQ"
  else
    echo "+ grep -vE '^(bear|vllm|flashinfer)' $ART/requirements.txt > $REQ"
  fi
  run_cmd install-requirements -- "$UV" pip install --python "$REPRO_PY" -r "$REQ" || die "installing the requirements failed"
  run_cmd install-bear -- "$UV" pip install --python "$REPRO_PY" "$BEAR_SRC[embeddings,hermes]" || die "installing BEAR failed"
else
  have=$("$REPRO_PY" -c "import importlib.metadata as m; print(m.version('bear'))" 2>/dev/null)
  if [ "$have" = "$BEAR_VERSION" ]; then
    say "venv exists with BEAR $have"
  else
    say "venv exists with BEAR '${have:-none}', installing $BEAR_VERSION from $BEAR_SRC"
    run_cmd install-bear -- "$UV" pip install --python "$REPRO_PY" --reinstall-package bear "$BEAR_SRC[embeddings,hermes]"       || die "installing BEAR failed"
  fi
fi
if [ "$DRY_RUN" = 0 ]; then
  check_venv
  say "BEAR $("$REPRO_PY" -c 'import importlib.metadata as m; print(m.version("bear"))') in $REPRO_VENV"
  "$REPRO_PY" -c "import importlib.metadata as m, json; print(json.dumps({p: m.version(p) for p in ['torch','transformers','sentence-transformers','numpy','scipy','llama-index-core','instruction-tool-retrieval','tiktoken']}))" \
    || die "the venv lacks a pinned package"
fi

# ---------------------------------------------------------------------------
say "5. models and tokenizer files (read offline by every run)"
if [ "$DOWNLOAD" = 1 ]; then
  for m in $HF_MODELS_RETRIEVAL $HF_MODELS_TOKENIZERS; do
    hf_cached "$m" && continue
    run_cmd "download-$m" -- env HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 "$REPRO_PY" -c \
      "import sys; from huggingface_hub import snapshot_download; print(snapshot_download(sys.argv[1]))" "$m" \
      || die "could not download $m (a gated model needs: huggingface-cli login)"
  done
  run_cmd tiktoken-cl100k -- env TIKTOKEN_CACHE_DIR="$TIKTOKEN_CACHE_DIR" "$REPRO_PY" -c \
    "import tiktoken; tiktoken.get_encoding('cl100k_base'); print('cl100k_base cached')" || die "could not fetch cl100k_base"
fi
if [ "$DRY_RUN" = 0 ]; then
  check_hf_models $HF_MODELS_RETRIEVAL $HF_MODELS_TOKENIZERS
  [ -n "$(ls -A "$TIKTOKEN_CACHE_DIR" 2>/dev/null)" ] || die "no tiktoken files in $TIKTOKEN_CACHE_DIR. Run with --download-models."
  say "all models and the tiktoken file are cached"
else
  echo "+ (check: $HF_MODELS_RETRIEVAL $HF_MODELS_TOKENIZERS in the HF cache, cl100k_base in $TIKTOKEN_CACHE_DIR)"
fi

# ---------------------------------------------------------------------------
say "6. clones of this repo (branch $BR, commit $(git -C "$ART" rev-parse --short "$BR"))"
dirty=$(git -C "$ART" status --porcelain --untracked-files=no -- evals hermes reproduce requirements.txt)
[ -z "$dirty" ] || warn "this checkout has uncommitted changes under evals/, hermes/ or reproduce/. Clones get the committed state only:
$dirty"
make_clone() {
  local d=$1
  if [ ! -d "$d/.git" ]; then
    run_cmd "clone-$(basename "$d")" -- git clone -q --branch "$BR" "$ART" "$d" || die "could not clone into $d"
  fi
  [ "$DRY_RUN" = 1 ] && return 0
  local f missing=""
  for f in $REQUIRED_IN_CLONE; do [ -e "$d/$f" ] || missing+=" $f"; done
  [ -z "$missing" ] || die "$d lacks:$missing. Commit them in $ART, then run 00_setup.sh --update."
  check_clone "$d"
}
for c in $WP0_CLONES; do make_clone "$WP0_DIR/$c"; done
for d in $OTHER_CLONES; do make_clone "$d"; done
[ "$DRY_RUN" = 0 ] && mkdir -p "$WP0_DIR/logs" "$WP0_DIR/stage" "$REPRO_OUT/logs" "$REPRO_EMB_CACHE"

# ---------------------------------------------------------------------------
say "7. verify_env.py: installed BEAR equals the v0.4.2 source, and Nemotron names itself"
if [ "$SKIPVERIFY" = 1 ]; then
  warn "verify_env.py skipped (--skip-verify). Every later script checks the BEAR version again."
else
  check_nemotron
  check_tc
  run_cmd verify-env -C "$WP0_DIR/artifacts" -- "$TC" --mem 4G -- env CUDA_VISIBLE_DEVICES= \
    PYTHONPATH=evals/wp0_v040/site BEAR_SOURCE_SHA="$BEAR_SHA" "$REPRO_PY" evals/wp0_v040/verify_env.py \
    --export "$BEAR_SRC" --expect-sha 0d0718a --expect-version "$BEAR_VERSION" --out "$REPRO_OUT/setup/verify_env.json" \
    || die "verify_env.py failed (see its output above)"
fi

# ---------------------------------------------------------------------------
say "8. the model-load guard and BEAR's restore switches"
run_cmd guard-check -C "$WP0_DIR/artifacts" -- "$TC" --mem 4G -- env CUDA_VISIBLE_DEVICES= WP0_NO_LOCAL_MODELS=1 \
  PYTHONPATH=evals/wp0_v040/site "$REPRO_PY" -c "
from bear import Config
f = sorted(x for x in Config.model_fields if x.startswith('restore_'))
assert {'restore_flat_backfill', 'restore_dropped_rows', 'restore_tie_order'} <= set(f), f
from sentence_transformers import SentenceTransformer
try:
    SentenceTransformer('BAAI/bge-base-en-v1.5')
except RuntimeError:
    print('guard ok: a refused model load raises; restore switches present:', len(f))
else:
    raise SystemExit('GUARD FAILED: the model loaded although WP0_NO_LOCAL_MODELS is set')
" || die "the model-load guard check failed"

REPRO_OK_NOTE="next: 10_cpu_retrieval.sh and 15_cpu_invariants_baselines.sh (see README, run order)"
