#!/usr/bin/env bash
# 70_assemble.sh: the analyses that combine the runs, then one repo-shaped tree of outputs.
#
# Reproduces (full map in reproduce/MANIFEST.md):
#   tab:tokens-recall and the WP4 text (evals/wp0_v040/merge_wp4_lists.py,
#     wp4_token_efficiency.py, wp4_summary.py over the k=50 lists of 10_, 20_ and 30_)
#   the per-query mandatory tables (evals/wp0_v040/table_mandatory.py)
#   the prompt-size checks behind the Table 10 caption (e2e_prompt_tokens.py with the
#     Mistral-Nemo and Gemma 4 tokenizers) and the BM25 list diff (e2e_list_diff.py)
#   with --with-controls (needs 10_ --with-controls): compare_042.py (every cell against
#     the published 0.1.10 value, the Summary of Differences) and fallback_audit.py
#   the numbers no eval script writes (part derived, reproduce/derive/ and one evals
#     diagnostic), each a JSON with its sources. No model, no server:
#       derive/metatool_split.py       Sec 4.2, 20,614 single-tool and 497 multi-tool queries
#       derive/e2e_name_collisions.py  Table 10 monolithic row, the 14 colliding names
#       derive/composer_tests.py       Sec 3.3, the eight emit_tool_summary tests in BEAR v0.4.2
#       derive/tool_summary_tokens.py  Sec 3.3, tokens the tool summary adds per tool
#       evals/diag_gate_coverage.py    Sec 4.6 and Supplement Sec S2, no gold API gated out
# Then it gathers everything into $REPRO_OUT/assembled/, laid out like this repo, so
# verify.py and collect.py can read it:
#   results/v042/           evals/wp0_v040/assemble_v040.py (WP0 stage, lists, WP4,
#                           e2e reruns, mandatory tables, checks, diag), with MANIFEST.json.
#                           The end-to-end reruns are e2e_rerun_all/ (50_ --all-rows),
#                           e2e_rerun_hash/ (50_ --hash-row) and e2e_long/<part>/ (56_ and 57_)
#   results/*               new result files of 15_ and 40_ (the artifacts-wp256 clone)
#   hermes/results/         $REPRO_OUT/hermes/analysis (60_)
#   (previous version)      $REPRO_OUT/previous/<part>/ (55_)
#   results/derived/        $REPRO_OUT/derived (part derived)
#   results/authorship/     $REPRO_OUT/authorship (65_)
#   figures/                $REPRO_OUT/figures (80_)
# Parts whose runs have not happened yet are skipped with a line saying so.
# Prerequisites: the runs it gathers. 00_setup.sh for the venv and tokenizers.
# Resources: CPU only, CUDA hidden, at most 16G. No server.
# Time: about 20 to 40 minutes (WP4 bootstrap about 15 minutes).
# Outputs: $REPRO_OUT/wp0/{wp4_lists_final,wp4,mandatory,e2e_checks,compare}/ and
#   $REPRO_OUT/assembled/.
#
# Usage:
#   bash reproduce/70_assemble.sh [--dry-run] [--with-controls] [--only "wp4 mandatory e2e-checks derived compare gather"]
set -uo pipefail
source "$(dirname "$0")/lib/common.sh"
repro_parse_args "$@"

PARTS="wp4 mandatory e2e-checks derived gather"
set -- "${ARGS_REST[@]}"
while [ $# -gt 0 ]; do
  case $1 in
    --with-controls) PARTS="wp4 mandatory e2e-checks derived compare gather" ;;
    --only) PARTS=$2; shift ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done

repro_begin
[ "$DRY_RUN" = 1 ] || { check_tc; check_venv; }
export CUDA_VISIBLE_DEVICES=
A0=$WP0_DIR/artifacts
ST=$WP0_DIR/stage
SKIPPED=()

for part in $PARTS; do
  hr
  case $part in
    wp4)
      srcs=()
      for d in "$WP0_DIR"/artifacts*/results/wp0/wp4_lists_v042; do [ -d "$d" ] && srcs+=("$d"); done
      mains=()
      for s in tb_bm25 tb_hash tb_nemotron tb_bge tb_bgem3 tb_qwen06 tb_qwen4b tb_qwen4b_tb_fix; do
        mains+=("$ST/v042/$s/results/wp0/toolbench_eval_$s.json")
      done
      missing=""
      for f in "${mains[@]}"; do [ -s "$f" ] || missing+=" $(basename "$f")"; done
      if [ "$DRY_RUN" = 0 ] && { [ ${#srcs[@]} -lt 4 ] || [ -n "$missing" ]; }; then
        warn "WP4 skipped: it needs the lists and runs of 10_, 20_ and 30_ (have ${#srcs[@]} list folders of 4, missing:${missing:- none})"
        SKIPPED+=(wp4); continue
      fi
      [ "$DRY_RUN" = 1 ] && srcs=("$WP0_DIR/artifacts/results/wp0/wp4_lists_v042" "...")
      rstep wp4-merge -C "$A0" -- capped 8G -- "$REPRO_PY" evals/wp0_v040/merge_wp4_lists.py \
        --out "$WP0_DIR/wp4_lists_final" "${srcs[@]}"
      rstep wp4-analysis -C "$A0" -- capped 16G -- "$REPRO_PY" evals/wp0_v040/wp4_token_efficiency.py \
        --lists "$WP0_DIR/wp4_lists_final" --main-runs "${mains[@]}" --outdir "$WP0_DIR/wp4"
      step_done wp4-summary || { [ "$DRY_RUN" = 1 ] || rm -f "$WP0_DIR/wp4/summary.md"; }
      rstep wp4-summary -C "$A0" -o "$WP0_DIR/wp4/summary.md" -- "$REPRO_PY" evals/wp0_v040/wp4_summary.py \
        "$WP0_DIR/wp4/wp4_token_efficiency.json"
      ;;
    mandatory)
      for b in lex dense q4b; do
        runs=(--run "v0110=$ST/v0110/diag_mand_${b}_v0110/results/wp0/diag_mandatory_${b}_v0110.json"
              --run "v042=$ST/v042/diag_mand_${b}_v042/results/wp0/diag_mandatory_${b}_v042.json")
        for sw in all ungated_pool below_threshold ranked_resolution removed_acting pool_by_k unchecked_requires \
                  flat_backfill dropped_rows tie_order; do
          f=$ST/v042L/diag_mand_${b}_L$sw/results/wp0/diag_mandatory_${b}_v042_L$sw.json
          { [ -s "$f" ] || [ "$DRY_RUN" = 1 ]; } && runs+=(--run "L_$sw=$f")
        done
        if [ "$DRY_RUN" = 0 ] && [ ! -s "${runs[1]#v0110=}" ]; then
          warn "mandatory table $b skipped: no diag_mand_${b} runs yet (10_)"; SKIPPED+=("mandatory-$b"); continue
        fi
        [ "$DRY_RUN" = 1 ] || mkdir -p "$WP0_DIR/mandatory"
        rstep "mandatory-$b" -C "$A0" -- capped 4G -- "$REPRO_PY" evals/wp0_v040/table_mandatory.py "${runs[@]}" \
          --out "$WP0_DIR/mandatory/mandatory_table_$b"
      done
      ;;
    e2e-checks)
      lists=()
      for d in artifacts/results/wp0/lists_v0110/e2e artifacts/results/wp0/lists_v042/e2e \
               artifacts-dense/results/wp0/lists_v0110/e2e artifacts-dense/results/wp0/lists_v042/e2e \
               artifacts-nemo/results/wp0/lists_v042/e2e; do
        { [ -d "$WP0_DIR/$d" ] || [ "$DRY_RUN" = 1 ]; } && lists+=("$WP0_DIR/$d")
      done
      if [ ${#lists[@]} -lt 5 ]; then
        warn "e2e checks skipped: they need the e2e lists of 10_ and 30_"; SKIPPED+=(e2e-checks); continue
      fi
      [ "$DRY_RUN" = 1 ] || mkdir -p "$WP0_DIR/e2e_checks"
      rstep e2e-prompt-tokens -C "$A0" -- capped 8G -- "$REPRO_PY" evals/wp0_v040/e2e_prompt_tokens.py \
        --lists "${lists[@]}" --gemma-tokenizer google/gemma-4-12B-it --out "$WP0_DIR/e2e_checks/e2e_prompt_tokens.json"
      rstep e2e-list-diff-lex -C "$A0" -- capped 4G -- "$REPRO_PY" evals/wp0_v040/e2e_list_diff.py \
        --a "$WP0_DIR/artifacts/results/wp0/lists_v0110/e2e" --b "$WP0_DIR/artifacts/results/wp0/lists_v042/e2e" \
        --out "$WP0_DIR/e2e_checks/e2e_list_diff_lex_v0110_v042.json"
      ;;
    derived)
      DV=$REPRO_OUT/derived
      [ "$DRY_RUN" = 1 ] || [ -d "$A0/reproduce/derive" ] || die "$A0 has no reproduce/derive (run 00_setup.sh --update)"
      [ "$DRY_RUN" = 1 ] || mkdir -p "$DV"
      rstep derive-metatool-split -C "$A0" -- capped 4G -- "$REPRO_PY" reproduce/derive/metatool_split.py         --out "$DV/metatool_split.json"
      rstep derive-e2e-name-collisions -C "$A0" -- capped 4G -- "$REPRO_PY" reproduce/derive/e2e_name_collisions.py         --out "$DV/e2e_name_collisions.json"
      rstep derive-composer-tests -C "$A0" -- capped 2G -- "$REPRO_PY" reproduce/derive/composer_tests.py         --bear "$BEAR_SRC" --out "$DV/composer_tests.json"
      rstep derive-tool-summary-tokens -C "$A0" -- capped 4G -- "$REPRO_PY" reproduce/derive/tool_summary_tokens.py         --out "$DV/tool_summary_tokens.json"
      rstep derive-gate-coverage -C "$A0" -- capped 4G -- "$REPRO_PY" evals/diag_gate_coverage.py         --out "$DV/gate_coverage.json"
      ;;
    compare)
      if [ "$DRY_RUN" = 0 ] && [ ! -d "$ST/v042L" ]; then
        warn "compare skipped: it needs the control lanes (10_ --with-controls)"; SKIPPED+=(compare); continue
      fi
      wlists=()
      for d in "$WP0_DIR"/artifacts*/results/wp0; do wlists+=("$d"); done
      # --pub is this checkout's results/: the published files, read only. The
      # clones' copies may have been rewritten by the runs.
      rstep compare-042 -C "$A0" -- capped 8G -- "$REPRO_PY" evals/wp0_v040/compare_042.py --pub "$ART/results" \
        --pub-e2e "$ART/evals/results/toolbench_e2e_scores.json" --stage "$ST" --lists "${wlists[@]}" \
        --out "$WP0_DIR/compare"
      if [ -d "$ST/v0110F" ] || [ "$DRY_RUN" = 1 ]; then
        rstep fallback-audit -C "$A0" -- capped 8G -- "$REPRO_PY" evals/wp0_v040/fallback_audit.py --pub "$ART" \
          --stage "$ST" --lists "${wlists[@]}" --published "$ART/evals/results/toolbench_e2e_scores.json" \
          --out "$WP0_DIR/compare/fallback_audit"
        rstep fallback-audit-md -C "$A0" -- "$REPRO_PY" evals/wp0_v040/audit_md.py \
          "$WP0_DIR/compare/fallback_audit/fallback_audit.json" "$WP0_DIR/compare/fallback_audit/fallback_audit.md"
      fi
      ;;
    gather)
      # Always redone from scratch: the assembled tree is a copy, never a source.
      if [ "$DRY_RUN" = 0 ]; then rm -rf "$ASSEMBLED"; mkdir -p "$ASSEMBLED"; fi
      echo "+ rm -rf $ASSEMBLED"
      if [ -d "$ST/v042" ] || [ "$DRY_RUN" = 1 ]; then
        extra=()
        # e2e_rerun is the five-row rerun of early November, which the paper no longer cites.
        # e2e_rerun_all, e2e_rerun_hash and e2e_long are parts 1 to 5 of evals/e2e_rerun/PLAN.md.
        for kv in "e2e_rerun=$REPRO_OUT/e2e_rerun" "e2e_rerun_all=$REPRO_OUT/e2e_rerun_all" \
                  "e2e_rerun_hash=$REPRO_OUT/e2e_rerun_hash" "e2e_long=$REPRO_OUT/e2e_long" \
                  "mandatory=$WP0_DIR/mandatory" "e2e_checks=$WP0_DIR/e2e_checks" "diag=$WP0_DIR/diag"; do
          { [ -d "${kv#*=}" ] || [ "$DRY_RUN" = 1 ]; } && extra+=("$kv")
        done
        run_cmd assemble-wp0 -C "$A0" -- capped 8G -- "$REPRO_PY" evals/wp0_v040/assemble_v040.py --root "$WP0_DIR" \
          --repo "$ASSEMBLED" --ver v042 --extra "${extra[@]}" || die "assemble_v040.py failed"
      else
        warn "no WP0 runs yet ($ST/v042)"; SKIPPED+=(wp0)
      fi
      # Result files your runs wrote in the WP1/2/5/6 clone: new files, and files
      # at a committed path whose committed copy was moved aside (git sees them as modified).
      if [ -d "$WP256_CLONE/.git" ]; then
        n=0
        while IFS= read -r rel; do
          [ -f "$WP256_CLONE/$rel" ] || continue
          if [ "$DRY_RUN" = 0 ]; then mkdir -p "$ASSEMBLED/$(dirname "$rel")"; cp -p "$WP256_CLONE/$rel" "$ASSEMBLED/$rel"; fi
          n=$((n + 1))
        done < <({ git -C "$WP256_CLONE" ls-files --others --exclude-standard -- results
                   git -C "$WP256_CLONE" ls-files -m -- results; } | sort -u)
        # A file of yours that equals the committed copy is neither new nor modified for git. That is
        # the case once your output has become the committed copy and the clone was updated. Such
        # files are listed with their git blob hash, by 00_setup.sh --update in the clone and for the
        # update of 20 Nov 2026 in lib/outputs_equal_committed.txt. A listed file is copied while the
        # clone's file still has that hash. A modified file was copied by the loop above.
        neq=0
        while read -r blob rel; do
          case $blob in ''|'#'*) continue ;; esac
          [ -n "$rel" ] && [ -f "$WP256_CLONE/$rel" ] || continue
          git -C "$WP256_CLONE" diff --quiet -- "$rel" || continue
          [ "$(git -C "$WP256_CLONE" hash-object "$WP256_CLONE/$rel")" = "$blob" ] || continue
          if [ "$DRY_RUN" = 0 ]; then mkdir -p "$ASSEMBLED/$(dirname "$rel")"; cp -p "$WP256_CLONE/$rel" "$ASSEMBLED/$rel"; fi
          neq=$((neq + 1))
        done < <(cat "$WP256_CLONE/.repro_aside/outputs_equal_committed.txt" "$REPRO_DIR/lib/outputs_equal_committed.txt" 2>/dev/null \
                   | tr -d '\r' | sort -u)
        say "copied $n new result file(s) of $WP256_CLONE, and $neq of yours that equal the committed copy"
      else
        warn "no clone $WP256_CLONE"; SKIPPED+=(wp256)
      fi
      # Hermes analysis (60_): stage 1, stage 2 and the stage-2 settings.
      H=${WP7_RUNS:-$REPRO_OUT/hermes}/analysis
      for pair in "stage1:stage1" "stage2:stage2" "stage2-settings:stage2"; do
        src=$H/${pair%%:*}
        if [ -d "$src" ]; then
          [ "$DRY_RUN" = 1 ] || { mkdir -p "$ASSEMBLED/hermes/results/${pair#*:}"; cp -rp "$src"/. "$ASSEMBLED/hermes/results/${pair#*:}/"; }
          say "copied $src"
        else
          SKIPPED+=("hermes-${pair%%:*}")
        fi
      done
      # Previous-version parts (55_), merged in repo layout.
      if [ -d "$REPRO_OUT/previous" ]; then
        for p in "$REPRO_OUT"/previous/*/; do
          [ "$DRY_RUN" = 1 ] || cp -rp "$p". "$ASSEMBLED/"
          say "copied $p"
        done
      fi
      # The authorship ablation (65_): tags, call log, validation, analysis.
      if [ -d "$REPRO_OUT/authorship" ]; then
        if [ "$DRY_RUN" = 0 ]; then
          mkdir -p "$ASSEMBLED/results/authorship"
          (cd "$REPRO_OUT/authorship" && find . -path ./toolbench_only -prune -o -type f -print) | while IFS= read -r f; do
            mkdir -p "$ASSEMBLED/results/authorship/$(dirname "$f")"
            cp -p "$REPRO_OUT/authorship/$f" "$ASSEMBLED/results/authorship/$f"
          done
        fi
        say "copied $REPRO_OUT/authorship"
      else
        SKIPPED+=(authorship)
      fi
      if [ -d "$REPRO_OUT/derived" ]; then
        [ "$DRY_RUN" = 1 ] || { mkdir -p "$ASSEMBLED/results/derived"; cp -p "$REPRO_OUT"/derived/*.json "$ASSEMBLED/results/derived/" 2>/dev/null; }
        say "copied $REPRO_OUT/derived"
      else
        SKIPPED+=(derived)
      fi
      if [ -d "$REPRO_OUT/figures" ]; then
        [ "$DRY_RUN" = 1 ] || { mkdir -p "$ASSEMBLED/figures"; cp -p "$REPRO_OUT"/figures/*.pdf "$ASSEMBLED/figures/" 2>/dev/null; }
        say "copied $REPRO_OUT/figures"
      fi
      ;;
    *) die "unknown part $part" ;;
  esac
done

if [ ${#SKIPPED[@]} -gt 0 ]; then
  REPRO_OK_NOTE="assembled what exists. Not yet run, so skipped: ${SKIPPED[*]}. verify.py lists them as NOT RUN"
else
  REPRO_OK_NOTE="assembled into $ASSEMBLED. Next: 90_verify.sh"
fi
