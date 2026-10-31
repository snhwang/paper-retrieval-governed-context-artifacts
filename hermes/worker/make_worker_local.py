#!/usr/bin/env python3
"""Generate worker_local.py from the Hermes harness's worker.py with fixed, anchored edits.

The harness file is never modified. Each anchor must match exactly once, so a change in the
upstream worker makes this script fail loudly instead of drifting. Task definitions, graders
and scripted replies come unchanged from the harness's tasks.py (HARNESS points at the
original directory). CHANGES.md lists every edit and why.

Usage: make_worker_local.py [--hermes ~/src/hermes-agent] [--out worker_local.py]

Writes worker_local.py and worker_local.diff next to this script.
"""
import argparse
import difflib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# (label, anchor, replacement). Labels match CHANGES.md.
EDITS = [
    (
        "E1 harness path",
        'HARNESS = os.path.dirname(os.path.abspath(__file__))\n',
        'HARNESS = os.environ.get("WP7_HARNESS_DIR") or os.path.expanduser(\n'
        '    "~/src/hermes-agent/evals/core_tool_deferral")  # WP7: the original harness directory\n'
        'sys.path.insert(0, HARNESS)  # WP7: sandbox and tasks resolve to the originals\n',
    ),
    (
        "E2 local endpoint, no OpenRouter key",
        'if not os.environ.get("OPENROUTER_API_KEY"):\n'
        '    print("ABORT: OPENROUTER_API_KEY missing", file=sys.stderr)\n'
        '    sys.exit(3)\n',
        '# WP7: local SGLang only. No OpenRouter key may reach Hermes.\n'
        'os.environ.pop("OPENROUTER_API_KEY", None)\n'
        'WP7_ARM_CONFIG = os.environ.get("WP7_ARM_CONFIG") or ""\n'
        'if not WP7_ARM_CONFIG or not os.path.isfile(WP7_ARM_CONFIG):\n'
        '    print("ABORT: WP7_ARM_CONFIG not set or missing", file=sys.stderr)\n'
        '    sys.exit(3)\n'
        'WP7_BASE_URL = os.environ.get("WP7_BASE_URL", "http://localhost:8355/v1")\n'
        'WP7_DECOYS = int(os.environ.get("WP7_DECOYS") or 0)\n'
        'WP7_DECOY_PLUGIN = os.environ.get("WP7_DECOY_PLUGIN") or ""\n',
    ),
    (
        "E3 per-arm config",
        '    f.write(f"model:\\n  provider: openrouter\\n  model: {MODEL}\\n")\n',
        '    with open(WP7_ARM_CONFIG, encoding="utf-8") as _tpl:  # WP7: per-cell config\n'
        '        f.write(_tpl.read())\n',
    ),
    (
        "E4 decoy plugin",
        'os.environ["HERMES_HOME"] = hermes_home\n',
        '# WP7: the decoy plugin is a directory plugin in this run\'s HERMES_HOME.\n'
        'if WP7_DECOYS > 0:\n'
        '    if not os.path.isfile(os.path.join(WP7_DECOY_PLUGIN, "plugin.yaml")):\n'
        '        print("ABORT: WP7_DECOYS > 0 but WP7_DECOY_PLUGIN has no plugin.yaml", file=sys.stderr)\n'
        '        sys.exit(3)\n'
        '    shutil.copytree(WP7_DECOY_PLUGIN, os.path.join(hermes_home, "plugins", "wp7_decoys"),\n'
        '                    ignore=shutil.ignore_patterns("__pycache__"))\n'
        'os.environ["HERMES_HOME"] = hermes_home\n',
    ),
    (
        "E5 task registry",
        'TASK = taskmod.TASKS_BY_ID[TASK_ID]\n',
        '# WP7: the harness\'s 14 tasks unchanged, plus the 9 toolperf_abeval tasks (wp7_tasks.py).\n'
        'import wp7_tasks\n'
        'TASK = wp7_tasks.get_task(TASK_ID, workspace)\n',
    ),
    (
        "E6 enable cronjob_manage",
        '_stub_entry("image_generate", image_generate_stub)\n',
        '_stub_entry("image_generate", image_generate_stub)\n'
        '\n'
        '# WP7: enable cronjob_manage, every arm alike. Its check_fn needs HERMES_INTERACTIVE,\n'
        '# HERMES_GATEWAY_SESSION, HERMES_EXEC_ASK or a cron session, none of which this hermetic\n'
        '# worker sets. Setting one of those would also change approval presence for every other\n'
        '# tool, so only the check is cleared. The real handler runs and writes HERMES_HOME/cron.\n'
        '_cron_entry = registry.get_entry("cronjob_manage")\n'
        'if _cron_entry is None:\n'
        '    print("ABORT: registry entry missing for cronjob_manage", file=sys.stderr)\n'
        '    sys.exit(3)\n'
        '_cron_entry.check_fn = None\n',
    ),
    (
        "E7 decoy toolset",
        '            "desktop_ui", "project", "code_execution"]\n',
        '            "desktop_ui", "project", "code_execution"]\n'
        'if WP7_DECOYS > 0:  # WP7: the decoy plugin registers its tools in this toolset\n'
        '    TOOLSETS = TOOLSETS + ["wp7_decoys"]\n',
    ),
    (
        "E8 local AIAgent",
        '    base_url="https://openrouter.ai/api/v1",\n'
        '    api_key=os.environ["OPENROUTER_API_KEY"],\n'
        '    provider="openrouter",\n',
        '    base_url=WP7_BASE_URL,  # WP7: local SGLang\n'
        '    api_key="not-needed",\n'
        '    provider="custom",\n',
    ),
    (
        "E13 continuation keeps the conversation",
        '        _reply = _clarify_answers.pop(0)\n'
        '        user_roundtrips += 1\n'
        '        convo = agent.run_conversation(_reply)\n',
        '        _reply = _clarify_answers.pop(0)\n'
        '        user_roundtrips += 1\n'
        '        # WP7 fix: in v0.22.2 run_conversation starts from conversation_history, and from\n'
        '        # nothing when it is None (agent/turn_context.py). Without the history the scripted\n'
        '        # reply reached the model with no task, and the metrics below saw only the last turn.\n'
        '        convo = agent.run_conversation(_reply, conversation_history=_msgs)\n',
    ),
    (
        "E9 surface record and dry mode",
        'PREAMBLE = (',
        '# WP7: record the model-facing tool surface this agent was built with.\n'
        'def _wp7_names(defs):\n'
        '    out = []\n'
        '    for _t in defs or []:\n'
        '        _f = _t.get("function", _t) if isinstance(_t, dict) else {}\n'
        '        out.append(_f.get("name", "?"))\n'
        '    return out\n'
        'WP7_SURFACE = {\n'
        '    "agent_tools": _wp7_names(getattr(agent, "tools", None)),\n'
        '    "toolsets": list(TOOLSETS),\n'
        '    "platform": getattr(agent, "platform", None),\n'
        '    "provider": getattr(agent, "provider", None),\n'
        '    "api_mode": getattr(agent, "api_mode", None),\n'
        '    "base_url": getattr(agent, "base_url", None),\n'
        '    "model": getattr(agent, "model", None),\n'
        '}\n'
        'try:\n'
        '    from hermes_cli.plugins import get_plugin_manager as _gpm\n'
        '    _pm = _gpm()\n'
        '    WP7_SURFACE["middleware"] = {k: len(v) for k, v in getattr(_pm, "_middleware", {}).items()}\n'
        '    WP7_SURFACE["plugins_enabled"] = sorted(k for k, p in getattr(_pm, "_plugins", {}).items()\n'
        '                                            if getattr(p, "enabled", False))\n'
        '    WP7_SURFACE["plugin_errors"] = {k: str(p.error) for k, p in getattr(_pm, "_plugins", {}).items()\n'
        '                                    if getattr(p, "enabled", False) and getattr(p, "error", None)}\n'
        'except Exception as _e:\n'
        '    WP7_SURFACE["plugin_probe_error"] = repr(_e)\n'
        'if os.environ.get("WP7_DRY") == "1":\n'
        '    # No model call. Dump the surface and the registry this worker would expose.\n'
        '    _dry = {"wp7_surface": WP7_SURFACE, "task": TASK_ID, "agent_tool_defs": agent.tools}\n'
        '    try:\n'
        '        _dry["registry_candidates"] = sorted(model_tools._select_tool_names(TOOLSETS, None, True))\n'
        '        _dry["registry_defs"] = model_tools.get_tool_definitions(\n'
        '            enabled_toolsets=TOOLSETS, quiet_mode=True, skip_tool_search_assembly=True)\n'
        '        _dry["registry_toolset_of"] = {n: getattr(registry.get_entry(n), "toolset", None)\n'
        '                                       for n in _dry["registry_candidates"]}\n'
        '    except Exception as _e:\n'
        '        _dry["registry_error"] = repr(_e)\n'
        '    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)\n'
        '    with open(OUT, "w", encoding="utf-8") as _f:\n'
        '        json.dump(_dry, _f, indent=1, default=str)\n'
        '    print(json.dumps({"dry": True, "agent_tools": len(WP7_SURFACE["agent_tools"])}))\n'
        '    shutil.rmtree(tmp_root, ignore_errors=True)\n'
        '    sys.exit(0)\n'
        '\n'
        'PREAMBLE = (',
    ),
    (
        "E10 bridge-call counting",
        '                if name == "tool_call":\n'
        '                    uname = str(fargs.get("name") or "")\n'
        '                    uargs = fargs.get("arguments") or {}\n'
        '                    if isinstance(uargs, str):\n'
        '                        try:\n'
        '                            uargs = json.loads(uargs)\n'
        '                        except Exception:\n'
        '                            uargs = {}\n'
        '                    uname = LEGACY.get(uname, uname)\n'
        '                    if uname:\n'
        '                        tool_counts[uname] = tool_counts.get(uname, 0) + 1\n'
        '                        tool_args.setdefault(uname, []).append(uargs)\n'
        '                continue\n',
        '                if name == "tool_call":\n'
        '                    # WP7 fix: Hermes v0.22.2 sends calls: [{name, arguments}]. The harness read\n'
        '                    # only the older single {name, arguments} form, so a deferred tool reached\n'
        '                    # through the bridge was never counted. Both forms are read.\n'
        '                    _calls = fargs.get("calls")\n'
        '                    if isinstance(_calls, str):\n'
        '                        try:\n'
        '                            _calls = json.loads(_calls)\n'
        '                        except Exception:\n'
        '                            _calls = None\n'
        '                    if not isinstance(_calls, list):\n'
        '                        _calls = [fargs]\n'
        '                    for _c in _calls:\n'
        '                        if not isinstance(_c, dict):\n'
        '                            continue\n'
        '                        uname = str(_c.get("name") or "")\n'
        '                        uargs = _c.get("arguments") or {}\n'
        '                        if isinstance(uargs, str):\n'
        '                            try:\n'
        '                                uargs = json.loads(uargs)\n'
        '                            except Exception:\n'
        '                                uargs = {}\n'
        '                        uname = LEGACY.get(uname, uname)\n'
        '                        if uname:\n'
        '                            tool_counts[uname] = tool_counts.get(uname, 0) + 1\n'
        '                            tool_args.setdefault(uname, []).append(uargs)\n'
        '                            WP7_VIA_BRIDGE.append(uname)\n'
        '                continue\n',
    ),
    (
        "E10 bridge-call counting (list)",
        'bridge_calls = 0\n',
        'bridge_calls = 0\n'
        'WP7_VIA_BRIDGE = []  # WP7: underlying tools reached through tool_call, in order\n',
    ),
    (
        "E11 record fields",
        '    "final_answer": (final_answer or "")[:2000],\n}\n',
        '    "final_answer": (final_answer or "")[:2000],\n'
        '    "wp7": {\n'
        '        "surface": WP7_SURFACE,\n'
        '        "via_bridge": WP7_VIA_BRIDGE,\n'
        '        "task_source": TASK.get("source", "core_tool_deferral"),\n'
        '        "decoys": WP7_DECOYS,\n'
        '        "cell": os.environ.get("WP7_CELL", ""),\n'
        '        "expected_token": (TASK.get("wp7_state") or {}).get("token"),\n'
        '    },\n}\n',
    ),
    (
        "E12 keep HERMES_HOME logs",
        'try:\n    agent.close()\nexcept Exception:\n    pass\nshutil.rmtree(tmp_root, ignore_errors=True)',
        'try:\n    agent.close()\nexcept Exception:\n    pass\n'
        '# WP7: keep the run\'s HERMES_HOME logs, config and cron jobs before cleanup.\n'
        'for _sub in ("logs", "config.yaml", "cron"):\n'
        '    _p = os.path.join(hermes_home, _sub)\n'
        '    try:\n'
        '        if os.path.isdir(_p):\n'
        '            shutil.copytree(_p, OUT + ".home/" + _sub, dirs_exist_ok=True)\n'
        '        elif os.path.isfile(_p):\n'
        '            os.makedirs(OUT + ".home", exist_ok=True)\n'
        '            shutil.copy2(_p, OUT + ".home/" + _sub)\n'
        '    except Exception as _e:\n'
        '        print(f"WP7: could not keep {_sub}: {_e}", file=sys.stderr)\n'
        'shutil.rmtree(tmp_root, ignore_errors=True)',
    ),
    # Stage 2. Applied after the edits above, so their anchors are the edited text.
    (
        "E14 staged sources leave the cell",
        'TASK = wp7_tasks.get_task(TASK_ID, workspace)\n',
        'TASK = wp7_tasks.get_task(TASK_ID, workspace)\n'
        '# WP7 (stage 2): the runner stages this worker, the task registry and the graders (tasks.py,\n'
        '# sandbox.py, ab_eval.py) in a private dir in the cell. They are loaded now, so the dir is\n'
        '# removed before the agent starts and its tools cannot read the planted answers.\n'
        '_wp7_src = os.environ.get("WP7_SRC_DIR") or ""\n'
        'if _wp7_src and os.path.isdir(_wp7_src):\n'
        '    shutil.rmtree(_wp7_src, ignore_errors=True)\n'
        '    print(f"WP7: staged sources removed: {not os.path.exists(_wp7_src)}", file=sys.stderr)\n',
    ),
    (
        "E15 expose manage_connections",
        '_cron_entry.check_fn = None\n',
        '_cron_entry.check_fn = None\n'
        '\n'
        '# WP7 (stage 2): expose manage_connections, which project_mcp_setup grades but the 14\n'
        '# toolsets leave out. Its toolset joins TOOLSETS below, and its check_fn (the connectors\n'
        '# portal gate) is cleared like cronjob_manage\'s. MCP targets go to connection_cb.\n'
        'import tools.connectors.tool  # noqa: F401  registers manage_connections\n'
        '_conn_entry = registry.get_entry("manage_connections")\n'
        'if _conn_entry is None:\n'
        '    print("ABORT: registry entry missing for manage_connections", file=sys.stderr)\n'
        '    sys.exit(3)\n'
        '_conn_entry.check_fn = None\n',
    ),
    (
        "E15 connections toolset",
        'if WP7_DECOYS > 0:  # WP7: the decoy plugin registers its tools in this toolset\n',
        'TOOLSETS = TOOLSETS + ["connections"]  # WP7 (stage 2): manage_connections, every arm\n'
        'if WP7_DECOYS > 0:  # WP7: the decoy plugin registers its tools in this toolset\n',
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes", default=os.path.expanduser("~/src/hermes-agent"))
    ap.add_argument("--out", default=os.path.join(HERE, "worker_local.py"))
    a = ap.parse_args()
    src_path = os.path.join(a.hermes, "evals", "core_tool_deferral", "worker.py")
    src = open(src_path, encoding="utf-8").read()
    out = src
    for label, old, new in EDITS:
        n = out.count(old)
        if n != 1:
            sys.exit(f"{label}: anchor matched {n} times, expected 1:\n{old}")
        out = out.replace(old, new)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    diff = difflib.unified_diff(src.splitlines(keepends=True), out.splitlines(keepends=True),
                                "evals/core_tool_deferral/worker.py", "hermes/worker/worker_local.py")
    diff_path = os.path.join(os.path.dirname(a.out), "worker_local.diff")
    with open(diff_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(diff)
    print(f"wrote {a.out} and {diff_path} from {src_path} with {len(EDITS)} edits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
