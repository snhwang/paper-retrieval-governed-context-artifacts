#!/usr/bin/env python3
"""Section 3.3: "Eight unit tests in the BEAR repository (tests/test_composer.py)".

    python reproduce/derive/composer_tests.py --bear ~/tist-evals/bear-v0.4.2 --out DIR/composer_tests.json

Counts the test functions of the class that covers emit_tool_summary
(TestEmitToolSummary) in the pinned BEAR release, by reading the file's syntax
tree. It runs nothing. It also lists every test class with its count, so a
renamed class still shows up.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

from _common import provenance, write


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bear", type=Path, default=Path.home() / "tist-evals" / "bear-v0.4.2")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    f = a.bear / "tests" / "test_composer.py"
    tree = ast.parse(f.read_text(encoding="utf-8"))
    classes = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = [n.name for n in node.body
                                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]
    module_tests = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
    sha_file = a.bear / "BEAR_GIT_SHA"
    write(a.out, {
        "file": "tests/test_composer.py",
        "bear_git_sha": sha_file.read_text().strip() if sha_file.exists() else None,
        "emit_tool_summary_tests": len(classes.get("TestEmitToolSummary", [])),
        "emit_tool_summary_test_names": classes.get("TestEmitToolSummary", []),
        "tests_per_class": {k: len(v) for k, v in classes.items()},
        "module_level_tests": len(module_tests),
        "_provenance": provenance("reproduce/derive/composer_tests.py", [f]),
    })


if __name__ == "__main__":
    main()
