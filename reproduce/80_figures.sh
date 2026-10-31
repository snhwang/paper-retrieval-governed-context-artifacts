#!/usr/bin/env bash
# 80_figures.sh: the manuscript's figures.
#
# Reproduces:
#   fig:pipeline (Figure 2): Figure1.tex, a standalone TikZ drawing in the paper repo,
#     built with pdflatex into Figure1.pdf, which the manuscript includes as
#     Figure1-pipeline.pdf. It draws no data.
#   fig:instructions (Figure 1) is a verbatim block inside sample-manuscript.tex.
#     Nothing to build.
#   No other figure or plot in the manuscript comes from data (no pgfplots, no
#   matplotlib, no CSV input).
# Prerequisites: the paper repo (PAPER_REPO, default: the folder
#   paper-retrieval-governed-context beside this repo) and a pdflatex with the
#   standalone class and TikZ: TeX Live in WSL (pdflatex), or MiKTeX on Windows
#   (pdflatex.exe through WSL interop).
# Resources: CPU only. No server.
# Time: under a minute.
# Outputs: $REPRO_OUT/figures/Figure1-pipeline.pdf, and a text comparison with the
#   paper repo's Figure1-pipeline.pdf when pdftotext is available.
#
# Usage:
#   bash reproduce/80_figures.sh [--dry-run]
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"
[ ${#ARGS_REST[@]} -eq 0 ] || die "unknown option ${ARGS_REST[0]} (see --help)"

PAPER_REPO=${PAPER_REPO:-$(cd "$ART/.." && pwd)/paper-retrieval-governed-context}
OUT=$REPRO_OUT/figures
repro_begin
[ -f "$PAPER_REPO/Figure1.tex" ] || die "no $PAPER_REPO/Figure1.tex (set PAPER_REPO to the paper repo)"

# Build in a scratch copy, so nothing is written into the paper repo.
WORK=$REPRO_OUT/figures/build
if command -v pdflatex >/dev/null 2>&1; then
  TEX=(pdflatex)
  WORK_TEX=$WORK
elif command -v pdflatex.exe >/dev/null 2>&1; then
  # MiKTeX runs on Windows and needs a Windows path. Use a folder under the
  # Windows temp directory, then copy the result back.
  wt=$(cmd.exe /c "echo %TEMP%" 2>/dev/null | tr -d '\r')
  [ -n "$wt" ] || die "cannot read the Windows TEMP folder for pdflatex.exe"
  WORK_TEX=$(wslpath -u "$wt")/tist-repro-figures
  TEX=(pdflatex.exe)
else
  die "no pdflatex (TeX Live in WSL) and no pdflatex.exe (MiKTeX) on PATH"
fi
say "pdflatex: ${TEX[*]}, build folder $WORK_TEX"

run_cmd copy-source -- mkdir -p "$WORK_TEX" "$OUT" || die "cannot make $WORK_TEX"
run_cmd copy-source -- cp "$PAPER_REPO/Figure1.tex" "$WORK_TEX/Figure1.tex" || die "cannot copy Figure1.tex"
run_cmd pdflatex -C "$WORK_TEX" -- "${TEX[@]}" -interaction=nonstopmode -halt-on-error Figure1.tex \
  || die "pdflatex failed (see $WORK_TEX/Figure1.log)"
run_cmd copy-result -- cp "$WORK_TEX/Figure1.pdf" "$OUT/Figure1-pipeline.pdf" || die "no Figure1.pdf was built"

if [ "$DRY_RUN" = 0 ] && command -v pdftotext >/dev/null 2>&1 && [ -f "$PAPER_REPO/Figure1-pipeline.pdf" ]; then
  if diff -q <(pdftotext "$OUT/Figure1-pipeline.pdf" -) <(pdftotext "$PAPER_REPO/Figure1-pipeline.pdf" -) >/dev/null; then
    say "the text of the built figure equals the manuscript's Figure1-pipeline.pdf"
  else
    die "the text of the built figure differs from $PAPER_REPO/Figure1-pipeline.pdf"
  fi
else
  say "no text comparison (pdftotext missing or no committed PDF). Compare the two PDFs by eye."
fi
REPRO_OK_NOTE="built $OUT/Figure1-pipeline.pdf"
