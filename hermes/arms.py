"""WP7 arms and switches, rendered to the HERMES_HOME config.yaml a cell runs with.

Every cell loads the BEAR plugin. Arms differ only in Hermes's tool search and BEAR's
``narrow``, ``narrow_top_k`` and gate ``mode``. All other settings are shared and switchable.

| Arm    | tools.tool_search | narrow  | narrow_top_k | gate mode |
| ------ | ----------------- | ------- | ------------ | --------- |
| A      | off               | observe | null         | observe   |
| B      | on                | observe | null         | observe   |
| C-gate | off               | on      | null         | observe   |
| C-cut  | off               | on      | k            | observe   |
| D      | off               | on      | null         | enforce   |

In A and B, ``narrow: observe`` sends Hermes's own tools and records what C-gate would have
offered (null k), with the whole ranking, so C-cut's k can be swept offline from the records.
Under tool search (B) observe mode ranks the registry built from ``registry_toolsets``.

Switches (``Switches``): role (operator or guest, through the plugin's ``users`` mapping),
decoys (0, 100, 300), backend (nemotron or bm25), annotation (off, none, names, counts, which
sets annotate_tools and withheld_disclosure), narrow_scope (turn or session), narrow_query,
narrow_priority_weight (0 by default, "default" for the retriever's own), always_offer, and k
for C-cut.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_JSON = os.path.join(HERE, "registry", "harness_registry.json")
DECOY_SAMPLE = os.path.join(HERE, "decoys", "sample.json")
DECOY_PLUGIN = os.path.join(HERE, "decoys", "wp7_decoys")
BASE_CORPUS = os.path.join(HERE, "corpus", "base", "tools.yaml")
DECOY_CORPUS = os.path.join(HERE, "corpus", "decoys", "decoys-{n}.yaml")

MODEL = "Qwen3.8-27B"
MODEL_BASE_URL = "http://localhost:8355/v1"
EMBED_URL = "http://localhost:8360"
DECOY_TOOLSET = "wp7_decoys"
TEAM = "team:ops"

ARMS: dict[str, dict[str, Any]] = {
    "A": {"tool_search": "off", "narrow": "observe", "mode": "observe"},
    "B": {"tool_search": "on", "narrow": "observe", "mode": "observe"},
    "C-gate": {"tool_search": "off", "narrow": "on", "mode": "observe"},
    "C-cut": {"tool_search": "off", "narrow": "on", "mode": "observe", "needs_k": True},
    "D": {"tool_search": "off", "narrow": "on", "mode": "enforce"},
}
ROLES = ("operator", "guest")
DECOY_SIZES = (0, 100, 300)
BACKENDS = {"nemotron": f"remote:{EMBED_URL}", "bm25": "bm25"}
ANNOTATIONS = ("off", "none", "names", "counts")  # plus "names<N>": names with withheld_names_max N


def annotation_parts(level: str) -> tuple[bool, str, int | None]:
    """(annotate_tools, withheld_disclosure, withheld_names_max) for an annotation level."""
    if level == "off":
        return False, "counts", None
    if level.startswith("names") and level[5:].isdigit():
        return True, "names", int(level[5:])
    return True, level, None
SCOPES = ("turn", "session")
QUERIES = ("message", "first_plus_message")


@dataclass(frozen=True)
class Switches:
    role: str = "operator"
    decoys: int = 0
    backend: str = "nemotron"
    annotation: str = "off"
    scope: str = "turn"
    query: str = "message"
    priority_weight: str = "0"          # a number, or "default" for the retriever's own
    always_offer: tuple = ("clarify",)
    k: int | None = None                 # C-cut only

    def validate(self, arm: str) -> None:
        if arm not in ARMS:
            raise ValueError(f"arm must be one of {list(ARMS)}, not {arm!r}")
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        if self.decoys not in DECOY_SIZES:
            raise ValueError(f"decoys must be one of {DECOY_SIZES}")
        if self.backend not in BACKENDS:
            raise ValueError(f"backend must be one of {list(BACKENDS)}")
        if self.annotation not in ANNOTATIONS and not (
                self.annotation.startswith("names") and self.annotation[5:].isdigit()):
            raise ValueError(f"annotation must be one of {ANNOTATIONS} or names<N>")
        if self.scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        if self.query not in QUERIES:
            raise ValueError(f"query must be one of {QUERIES}")
        if ARMS[arm].get("needs_k") and (self.k is None or self.k < 0):
            raise ValueError("C-cut needs k >= 0")
        if not ARMS[arm].get("needs_k") and self.k is not None:
            raise ValueError(f"k applies to C-cut only, not {arm}")
        if self.priority_weight != "default":
            w = float(self.priority_weight)
            if not 0.0 <= w <= 1.0:
                raise ValueError("priority_weight must be in [0, 1] or 'default'")


def cell_id(arm: str, task: str, rep: int, sw: Switches) -> str:
    """A file-safe name that changes whenever any setting changes."""
    a = f"{arm}{sw.k}" if arm == "C-cut" else arm
    parts = [a, task, sw.role, f"d{sw.decoys}", sw.backend, f"ann-{sw.annotation}"]
    if sw.scope != "turn":
        parts.append(f"scope-{sw.scope}")
    if sw.query != "message":
        parts.append(f"q-{sw.query}")
    if sw.priority_weight != "0":
        parts.append(f"pw-{sw.priority_weight}")
    if tuple(sw.always_offer) != ("clarify",):
        parts.append("ao-" + ("-".join(sw.always_offer) or "none"))
    parts.append(f"r{rep}")
    return "__".join(parts)


def harness_toolsets() -> list[str]:
    with open(REGISTRY_JSON, encoding="utf-8") as f:
        return list(json.load(f)["toolsets"])


def registry_toolsets(decoys: int) -> list[str]:
    """The toolsets the worker enables, which observe mode under tool search ranks."""
    ts = harness_toolsets()
    return ts + [DECOY_TOOLSET] if decoys > 0 else ts


def bear_settings(arm: str, sw: Switches, *, corpus_dir: str, audit_path: str,
                  embedding_revision: str = "") -> dict[str, Any]:
    spec = ARMS[arm]
    settings: dict[str, Any] = {
        "corpus_dir": corpus_dir,
        "mode": spec["mode"],
        "unlisted": "block",
        "users": {"platform:cli": [f"role:{sw.role}", TEAM]},
        "default_tags": ["role:guest"],
        "embedding": BACKENDS[sw.backend],
        "embedding_revision": embedding_revision if sw.backend == "nemotron" else "",
        "audit_path": audit_path,
        "narrow": spec["narrow"],
        "narrow_top_k": sw.k if spec.get("needs_k") else None,
        "narrow_threshold": 0.0,
        "narrow_scope": sw.scope,
        "narrow_query": sw.query,
        "always_offer": list(sw.always_offer),
        "registry_toolsets": registry_toolsets(sw.decoys),
    }
    annotate, disclosure, names_max = annotation_parts(sw.annotation)
    settings.update({"annotate_tools": annotate, "withheld_disclosure": disclosure})
    if names_max is not None:
        settings["withheld_names_max"] = names_max
    if sw.priority_weight != "default":
        settings["narrow_priority_weight"] = float(sw.priority_weight)
    return settings


def hermes_config(arm: str, sw: Switches, *, corpus_dir: str, audit_path: str,
                  embedding_revision: str = "", decoy_sample: str = DECOY_SAMPLE) -> dict:
    sw.validate(arm)
    enabled = ["bear"] + (["wp7_decoys"] if sw.decoys > 0 else [])
    entries: dict[str, Any] = {"bear": {"settings": bear_settings(
        arm, sw, corpus_dir=corpus_dir, audit_path=audit_path,
        embedding_revision=embedding_revision)}}
    if sw.decoys > 0:
        entries["wp7_decoys"] = {"settings": {"sample_path": decoy_sample, "size": sw.decoys}}
    return {
        "model": {"default": MODEL, "provider": "custom", "base_url": MODEL_BASE_URL,
                  "api_key": "not-needed"},
        "tools": {"tool_search": {"enabled": ARMS[arm]["tool_search"]}},
        "plugins": {"enabled": enabled, "entries": entries},
    }


def render(cfg: dict) -> str:
    return yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False, width=100)


def write_examples(out_dir: str) -> list[str]:
    """One rendered template per arm, with placeholders for the per-cell paths."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for arm in ARMS:
        sw = Switches(k=10 if ARMS[arm].get("needs_k") else None)
        cfg = hermes_config(arm, sw, corpus_dir="<run>/corpus/d<decoys>",
                            audit_path="<run>/audit/<cell>.jsonl",
                            embedding_revision="<nemotron image digest>",
                            decoy_sample="<hermes>/decoys/sample.json")
        head = (f"# WP7 arm {arm}: HERMES_HOME config.yaml template, rendered by hermes/arms.py\n"
                f"# with the default switches ({json.dumps(asdict(sw))}).\n"
                "# The runner fills the <...> paths per cell. Decoys > 0 add wp7_decoys to\n"
                "# plugins.enabled and registry_toolsets, and a plugins.entries.wp7_decoys block.\n")
        path = os.path.join(out_dir, f"{arm}.yaml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(head + render(cfg))
        written.append(path)
    return written


if __name__ == "__main__":
    for p in write_examples(os.path.join(HERE, "configs")):
        print(p)
