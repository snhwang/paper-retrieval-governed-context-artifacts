"""WP7 decoy tools: N ToolBench APIs registered as Hermes plugin tools.

Settings (``plugins.entries.wp7_decoys.settings``):
  sample_path  absolute path to hermes/decoys/sample.json
  size         one of the sizes in sample.json ("100", "300"). 0 registers nothing.

Each decoy's schema is the sampled API's name, description and parameters, verbatim. Every call
returns the same error, so a decoy can cost a turn but never change the workspace. The tools go
in toolset ``wp7_decoys``, which the WP7 worker adds to the agent's toolsets when decoys are on.
Under Hermes's tool search they are plugin tools, so they are deferred behind the bridge.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _handler(error: str):
    payload = json.dumps({"error": error})

    def handler(args=None, **_kw):
        return payload
    return handler


def register(ctx) -> None:
    size = int(ctx.get_config("size", 0) or 0)
    if size <= 0:
        return
    path = ctx.get_config("sample_path", "")
    with open(path, encoding="utf-8") as f:
        sample = json.load(f)
    members = sample["sizes"].get(str(size))
    if members is None:
        raise ValueError(f"wp7_decoys: size {size} not in {sorted(sample['sizes'])}")
    by_name = {d["name"]: d for d in sample["decoys"]}
    handler = _handler(sample["error"])
    toolset = sample.get("toolset", "wp7_decoys")
    for name in members:
        d = by_name[name]
        schema = {"name": name, "description": d["description"], "parameters": d["parameters"]}
        ctx.register_tool(name=name, toolset=toolset, schema=schema, handler=handler,
                          description=d["description"])
    logger.info("wp7_decoys: registered %d decoy tools (size %d)", len(members), size)
