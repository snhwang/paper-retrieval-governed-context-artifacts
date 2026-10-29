"""WP7 task registry: the core_tool_deferral battery unchanged, plus toolperf_abeval's nine.

``get_task(task_id, workspace)`` returns a task in the harness's shape: ``id``, ``prompt``,
``fixtures(workspace)``, ``grade(ctx) -> (score, notes)``, ``clarify_answers`` and ``timeout``.

Core tasks are the harness's own dicts from ``tasks.TASKS_BY_ID``, returned as they are.

toolperf_abeval tasks are adapted, not rewritten. The prompt text, the sandbox builder
(``make_sandbox``) and the success checks (``SUCCESS``) are imported from
``evals/toolperf_abeval/ab_eval.py`` unchanged. The adapter only does three things:

- fills ``{WORK}`` in the prompt with this run's workspace,
- runs ``make_sandbox(Path(workspace))`` as the fixture (it builds ``<workspace>/proj``),
- grades ``SUCCESS[name](final_answer, Path(workspace))`` as 1.0 or 0.0.

ab_eval passed the last 12 lines of ``hermes chat --quiet`` stdout to the check. Here the check
reads the agent's final answer, which is what that stdout printed.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import tasks as core  # the harness's tasks.py, resolved through HARNESS on sys.path

HERMES_TREE = os.environ.get("WP7_HERMES_TREE") or os.path.expanduser("~/src/hermes-agent")
TOOLPERF_PATH = os.path.join(HERMES_TREE, "evals", "toolperf_abeval", "ab_eval.py")
TOOLPERF_TIMEOUT = 600  # ab_eval's own per-run timeout
TOOLPERF_SOURCE = "toolperf_abeval"

_toolperf_mod = None


def _toolperf():
    """ab_eval.py, imported by path. Importing it only defines constants and functions."""
    global _toolperf_mod
    if _toolperf_mod is None:
        spec = importlib.util.spec_from_file_location("wp7_toolperf_ab_eval", TOOLPERF_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _toolperf_mod = mod
    return _toolperf_mod


def core_ids() -> list[str]:
    return [t["id"] for t in core.TASKS]


def toolperf_ids() -> list[str]:
    return list(_toolperf().TASKS)


def all_ids() -> list[str]:
    return core_ids() + toolperf_ids()


def source_of(task_id: str) -> str:
    if task_id in core.TASKS_BY_ID:
        return "core_tool_deferral"
    if task_id in _toolperf().TASKS:
        return TOOLPERF_SOURCE
    raise KeyError(task_id)


def timeout_of(task_id: str) -> int:
    if task_id in core.TASKS_BY_ID:
        return int(core.TASKS_BY_ID[task_id].get("timeout") or 600)
    return TOOLPERF_TIMEOUT


def get_task(task_id: str, workspace: str) -> dict:
    if task_id in core.TASKS_BY_ID:
        return core.TASKS_BY_ID[task_id]
    tp = _toolperf()
    if task_id not in tp.TASKS:
        raise KeyError(f"unknown task {task_id!r}")
    check = tp.SUCCESS[task_id]

    def fixtures(ws: str) -> None:
        tp.make_sandbox(Path(ws))

    def grade(ctx: dict):
        answer = ctx.get("final_answer") or ""
        try:
            ok = bool(check(answer, Path(ctx["workspace"])))
        except Exception as exc:  # a check that reads a missing file raises
            return 0.0, [f"success check raised {type(exc).__name__}: {exc}"]
        return (1.0, []) if ok else (0.0, ["success check failed"])

    return {
        "id": task_id,
        "prompt": tp.TASKS[task_id].replace("{WORK}", str(workspace)),
        "fixtures": fixtures,
        "grade": grade,
        "clarify_answers": [],
        "timeout": TOOLPERF_TIMEOUT,
        "source": TOOLPERF_SOURCE,
    }
