#!/usr/bin/env bash
# 90_verify.sh: check your outputs against the committed ones, then build the numbers file.
#
# Runs, on $REPRO_OUT/assembled (made by 70_assemble.sh):
#   1. reproduce/verify.py: every file against the committed file of the same path,
#      under the tolerance of its class (exact for deterministic CPU results, inside
#      the committed CI for local GPU and Nemotron results, within 0.01 accuracy for
#      the Ollama executor). One line per file: PASS, FAIL, INFO, NEW, SKIP or NOT RUN.
#   2. reproduce/collect.py: every manuscript number with its source file, from your
#      outputs, into numbers.json and numbers.md. The final numbers pass reads that file.
# Prerequisites: 70_assemble.sh. The kit's venv (numpy, scipy).
# Resources: CPU only, at most 8G. No server.
# Time: a few minutes.
# Outputs: $REPRO_OUT/verify/verify.{md,json}, $REPRO_OUT/numbers/numbers.{md,json}.
#
# Usage:
#   bash reproduce/90_verify.sh [--dry-run] [--strict]
#   --strict  a required file that is not produced yet fails the check
# The final line is FAILED if a file is outside its tolerance (or, with --strict,
# not produced), or if a number the manuscript needs from your runs is missing.
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"
STRICT=()
for a in "${ARGS_REST[@]}"; do
  case $a in
    --strict) STRICT=(--strict) ;;
    *) die "unknown option $a (see --help)" ;;
  esac
done
repro_begin
[ "$DRY_RUN" = 1 ] || { check_venv; check_tc; }
[ "$DRY_RUN" = 1 ] || [ -d "$ASSEMBLED" ] || die "no $ASSEMBLED. Run 70_assemble.sh first."

rc_v=0 rc_c=0
run_cmd verify -- "$TC" --mem 8G -- "$REPRO_PY" "$REPRO_DIR/verify.py" --repro "$ASSEMBLED" --committed "$ART" \
  --out "$REPRO_OUT/verify" "${STRICT[@]}" || rc_v=$?
hr
run_cmd collect -- "$TC" --mem 8G -- "$REPRO_PY" "$REPRO_DIR/collect.py" --root "$ASSEMBLED" --committed "$ART" \
  --out "$REPRO_OUT/numbers" || rc_c=$?

if [ "$rc_v" -ne 0 ] && [ "$rc_c" -ne 0 ]; then
  die "verify.py found files outside their tolerance, and collect.py found missing numbers (see above)"
elif [ "$rc_v" -ne 0 ]; then
  die "verify.py found files outside their tolerance (see $REPRO_OUT/verify/verify.md)"
elif [ "$rc_c" -ne 0 ]; then
  die "collect.py found numbers the manuscript needs that your runs lack (see $REPRO_OUT/numbers/numbers.md)"
fi
REPRO_OK_NOTE="every file within its tolerance, every needed number present: $REPRO_OUT/numbers/numbers.md"
