"""Offline tests for authorship_regenerate.py (WP6.4).

Nothing here reaches a network. A fake server stands in for the real urlopen
the shim would call, and every socket connect fails the test. The checks:

- the translated request carries the original system and user text byte for
  byte, with the same temperature, max_tokens, enum vocabulary and forced tool
- no Anthropic key and no other credential leaves the process
- a reply with no tool call goes through the original retry path, then
  TaggingError, and the output file keeps the other items
- HTTP 429 is retried by the original code
- generate writes all five targets into a tmp dir, in the original formats,
  and the outputs pass the originals' validation rules
- compare and evaluate run on those outputs
- every committed file under results/ and evals/data/ is byte-identical
  before and after

Run (WSL, repo root):
    CUDA_VISIBLE_DEVICES="" python -m pytest evals/test_authorship_regenerate.py -q
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(EVALS))

import authorship_regenerate as ar  # noqa: E402
import metatool_tagging as mt  # noqa: E402

FAKE_BASE = "http://fake-endpoint.invalid/v1"
FAKE_MODEL = "fake/second-family-model"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real socket connect fails the test."""
    def refuse(self, *a, **k):
        raise AssertionError(f"a real network connection was attempted: {a}")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def _reply(message: dict, finish: str, model: str = FAKE_MODEL) -> ar._Reply:
    body = {"id": "x", "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    return ar._Reply(json.dumps(body).encode("utf-8"))


def _tool_reply(name: str, args: dict) -> ar._Reply:
    return _reply({"role": "assistant", "content": None,
                   "tool_calls": [{"id": "c1", "type": "function",
                                   "function": {"name": name, "arguments": json.dumps(args)}}]},
                  "tool_calls")


def _labels_in(user: str) -> list[str]:
    return re.findall(r"^- (.+)$", user, re.M)


class FakeServer:
    """Plays the OpenAI-compatible endpoint. Records every request it sees."""

    def __init__(self, fail_tool: str | None = None, rate_limit_first: int = 0):
        self.requests: list[tuple[str, dict | None, dict]] = []
        self.fail_tool = fail_tool
        self.rate_limit_left = rate_limit_first

    def __call__(self, req, data=None, timeout=None, **kw):
        url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
        if not url.startswith(FAKE_BASE):
            raise AssertionError(f"request outside the fake endpoint: {url}")
        headers = dict(req.header_items()) if isinstance(req, urllib.request.Request) else {}
        if url.endswith("/models"):
            self.requests.append((url, None, headers))
            return ar._Reply(json.dumps({"data": [{"id": FAKE_MODEL}]}).encode())
        body = json.loads(req.data.decode("utf-8"))
        self.requests.append((url, body, headers))
        if self.rate_limit_left:
            self.rate_limit_left -= 1
            raise urllib.error.HTTPError(url, 429, "rate limited", {"Retry-After": "0"},
                                         io.BytesIO(b"slow down"))
        user = body["messages"][-1]["content"]
        if body.get("tools"):
            name = body["tools"][0]["function"]["name"]
            if self.fail_tool and f"Tool name: {self.fail_tool}\n" in user:
                return _reply({"role": "assistant", "content": "I would rather not."}, "stop")
            if name == "assign_tool_categories":
                return _tool_reply(name, {"tags": ["finance", "travel"]})
            # primary_domain "search" exercises the original's promotion rule
            return _tool_reply(name, {"primary_domain": "search",
                                      "additional_tags": ["food", "search", "weather"]})
        labels = _labels_in(user)
        system = body["messages"][0]["content"]
        if "single RapidAPI category" in system:
            text = labels[3]
        else:
            text = ", ".join(labels[:5])
        # A leading think block must be removed by the shim
        return _reply({"role": "assistant", "content": f"<think>\n\n</think>\n\n{text}"}, "stop")


def _tracked_hashes() -> dict[str, str]:
    out = subprocess.run(["git", "ls-files", "-z", "results", "evals/data"], cwd=REPO,
                         capture_output=True, timeout=120, check=True)
    files = [p for p in out.stdout.decode().split("\0") if p]
    return {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest()
            for p in files if (REPO / p).is_file()}


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def test_tool_request_translation_is_faithful():
    server = FakeServer()
    shim = ar.AnthropicToOpenAIShim(FAKE_BASE, {"chat_template_kwargs": {"enable_thinking": False}},
                                    transport=server)
    with shim:
        shim.target = "tool_tags"
        tags = mt.generate_tool_tags("weather_now", "Live forecasts.", FAKE_MODEL, "sk-secret")
    assert tags == ["finance", "travel"]
    payload, translated = shim.last_payloads["tool_tags"]
    url, sent, headers = server.requests[0]
    assert url == FAKE_BASE + "/chat/completions"
    assert sent == translated
    # system and user text byte for byte
    assert sent["messages"][0] == {"role": "system", "content": payload["system"]}
    assert sent["messages"][1]["content"] == payload["messages"][0]["content"]
    assert mt.taxonomy_text(include_search=False) in sent["messages"][1]["content"]
    assert sent["temperature"] == payload["temperature"] == 0.0
    assert sent["max_tokens"] == payload["max_tokens"] == 300
    fn = sent["tools"][0]["function"]
    assert fn["parameters"] == payload["tools"][0]["input_schema"] == mt._TOOL_TOOL["input_schema"]
    assert fn["parameters"]["properties"]["tags"]["items"]["enum"] == mt.DOMAIN_NAMES
    assert sent["tool_choice"] == {"type": "function",
                                   "function": {"name": "assign_tool_categories"}}
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    # no credential is forwarded
    assert not any(k.lower() in ("x-api-key", "authorization") for k in headers)
    assert "sk-secret" not in json.dumps(sent)


def test_query_tag_validation_is_the_originals():
    server = FakeServer()
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server):
        tags = mt.generate_query_tags("Find me a pizza place", FAKE_MODEL, "k", k=5)
    # the original promotes the first domain tag over a "search" primary
    assert tags == ["food", "search", "weather"]
    sent = server.requests[0][1]
    assert sent["tools"][0]["function"]["parameters"] == mt._QUERY_TOOL["input_schema"]


@pytest.mark.parametrize("modname,max_tokens", [
    ("eval_toolbench_inferred_categories", 64),
    ("eval_toolbench_multitag_categories", 256),
    ("eval_toolbench_top5_categories", 256),
])
def test_text_request_translation_is_faithful(modname, max_tokens):
    mod = importlib.import_module(modname)
    server = FakeServer()
    labels = ["Data", "Finance", "Sports", "Travel", "Weather", "Music"]
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server):
        raw = mod.classify_query("  Will it rain in Oslo?  ", labels, "anthropic",
                                 FAKE_MODEL, "k", None)
    sent = server.requests[0][1]
    assert sent["messages"][0]["content"] == mod.SYSTEM_PROMPT
    assert sent["messages"][1]["content"] == mod.build_user_prompt("  Will it rain in Oslo?  ", labels)
    assert sent["max_tokens"] == max_tokens and sent["temperature"] == 0.0
    assert "tools" not in sent and "tool_choice" not in sent
    assert "<think>" not in raw
    expected = "Travel" if modname.endswith("inferred_categories") else ", ".join(labels[:5])
    assert raw == expected


def test_unknown_request_field_is_refused():
    with pytest.raises(ar.ShimError):
        ar.translate_request({"model": "m", "max_tokens": 1, "messages": [], "top_p": 0.9})
    with pytest.raises(ar.ShimError):
        ar.translate_request({"model": "m", "max_tokens": 1, "messages": []},
                             extra={"max_tokens": 5})


def test_shim_refuses_other_hosts():
    server = FakeServer()
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server):
        for url in ("https://api.openai.com/v1/chat/completions",
                    "http://localhost:8355/v1/chat/completions"):
            with pytest.raises(ar.ShimRefused):
                urllib.request.urlopen(url, timeout=1)
    assert server.requests == []


# ---------------------------------------------------------------------------
# Retries and failures
# ---------------------------------------------------------------------------

def test_no_tool_call_retries_then_tagging_error():
    server = FakeServer(fail_tool="stubborn")
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server) as shim:
        with pytest.raises(mt.TaggingError):
            mt.generate_tool_tags("stubborn", "x", FAKE_MODEL, "k")
    # the original's max_retries is 6
    assert len(server.requests) == 6
    assert shim.stats["no_tool_call"] == 6


def test_http_429_is_retried_by_the_original():
    server = FakeServer(rate_limit_first=2)
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server) as shim:
        assert mt.generate_tool_tags("weather_now", "x", FAKE_MODEL, "k") == ["finance", "travel"]
    assert len(server.requests) == 3
    assert shim.stats["http_429"] == 2


def test_failed_tool_is_left_out_not_emptied(tmp_path, monkeypatch):
    import metatool_generate_tags as gen
    tools = gen.load_tools()[:4]
    monkeypatch.setattr(gen, "load_tools", lambda: tools)
    server = FakeServer(fail_tool=tools[1]["name"])
    out = tmp_path / "plugin_tags.json"
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server), ar._dummy_key():
        res = ar.run_metatool("tool_tags", out, FAKE_MODEL, workers=2, resume=False,
                              max_items=None)
    written = json.loads(out.read_text())
    assert tools[1]["name"] not in written
    assert set(written) == {t["name"] for t in tools} - {tools[1]["name"]}
    assert all(v for v in written.values())
    assert res["n_missing"] == 1


def test_repeated_query_counts_once(tmp_path, monkeypatch):
    # MetaTool repeats some query texts. The generator keys by text, so a repeat
    # is tagged once and is not missing (job 155 reported 70 missing for this).
    import metatool_generate_query_tags_top5 as gen
    qs = gen.load_queries()[:3]
    rows = qs + [dict(qs[0])]
    monkeypatch.setattr(gen, "load_queries", lambda: [dict(q) for q in rows])
    server = FakeServer()
    out = tmp_path / "query_tags_top5.json"
    with ar.AnthropicToOpenAIShim(FAKE_BASE, transport=server), ar._dummy_key():
        res = ar.run_metatool("query_tags_top5", out, FAKE_MODEL, workers=2, resume=False,
                              max_items=None)
    assert res["n_input_rows"] == 4
    assert res["n_items"] == res["n_written"] == 3
    assert res["n_missing"] == 0


# ---------------------------------------------------------------------------
# End to end: generate, compare, evaluate
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Run generate on 3 items per target into a tmp dir, with the fake server."""
    before = _tracked_hashes()
    out_dir = tmp_path_factory.mktemp("regen")
    server = FakeServer()
    real = urllib.request.urlopen
    mp = pytest.MonkeyPatch()
    mp.setattr(urllib.request, "urlopen", server)
    mp.setattr(socket.socket, "connect",
               lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    import time
    mp.setattr(time, "sleep", lambda s: None)
    try:
        ar.main(["generate", "--base-url", FAKE_BASE, "--out-dir", str(out_dir),
                 "--max-items", "3", "--workers", "2"])
    finally:
        mp.undo()
    assert urllib.request.urlopen is real
    return {"dir": out_dir, "server": server, "before": before}


def test_generate_writes_valid_outputs(generated):
    d = generated["dir"]
    tool = json.loads((d / "plugin_tags.json").read_text())
    assert len(tool) == 3
    for tags in tool.values():
        assert 1 <= len(tags) <= 3 and all(t in mt.DOMAIN_NAMES for t in tags)
    qt = json.loads((d / "query_tags_top5.json").read_text())
    assert len(qt) == 3
    for e in qt:
        assert e["context_tags"][0] in mt.DOMAIN_NAMES
        assert len(e["context_tags"]) <= 5
        assert all(t in mt.QUERY_VOCAB for t in e["context_tags"])
        assert set(e) == {"query", "context_tags", "tools", "type"}
    for target in ("toolbench_top1", "toolbench_multi", "toolbench_top5"):
        name = ar.OUT_NAMES[target]
        cache = json.loads((d / name).read_text())
        assert len(cache) == 3 and all("<think>" not in v for v in cache.values())
        parsed = json.loads((d / name.replace(".json", "_parsed.json")).read_text())
        assert len(parsed) == 3
        for row in parsed:
            assert row["inferred_tags"], row
            limit = 1 if target == "toolbench_top1" else 5
            assert len(row["inferred_tags"]) <= limit


def test_manifest_and_request_log(generated):
    d = generated["dir"]
    man = json.loads((d / "manifest.json").read_text())
    run = man["runs"][-1]
    assert run["model"] == FAKE_MODEL and run["base_url"] == FAKE_BASE
    assert run["client_extras"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert set(run["results"]) == set(ar.TARGETS)
    assert all("error" not in r for r in run["results"].values())
    assert "metatool_tagging.py" in run["generator_source_sha256"]
    assert run["served_models_in_replies"] == {FAKE_MODEL: 15}
    assert len(run["system_prompts"]) == 5
    assert {s["name"] for s in run["tool_schemas"].values()} == {
        "assign_tool_categories", "assign_query_categories"}
    assert run["shim_totals"]["think_block_removed"] == 9
    lines = (d / "requests.jsonl").read_text().splitlines()
    assert len(lines) == run["shim_totals"]["requests"] == 15
    # every chat request the fake server saw was one the shim logged
    chats = [r for r in generated["server"].requests if r[1] is not None]
    assert len(chats) == 15
    for _, body, headers in chats:
        assert not any(k.lower() in ("x-api-key", "authorization") for k in headers)
        assert body["model"] == FAKE_MODEL


def test_refuses_committed_and_existing_outputs(generated, tmp_path):
    with pytest.raises(SystemExit):
        ar.check_outputs([ar.SONNET_FILES["tool_tags"]], resume=True)
    with pytest.raises(SystemExit):
        ar.check_outputs([REPO / "results" / "budget_binding.json"], resume=True)
    with pytest.raises(SystemExit):
        ar.check_outputs([generated["dir"] / "plugin_tags.json"], resume=False)
    ar.check_outputs([generated["dir"] / "plugin_tags.json"], resume=True)
    ar.check_outputs([tmp_path / "new.json"], resume=False)


def test_compare_on_generated(generated, tmp_path):
    out = tmp_path / "compare.json"
    ar.main(["compare", "--regen-dir", str(generated["dir"]), "--output", str(out)])
    rep = json.loads(out.read_text())["targets"]
    assert set(rep) == set(ar.TARGETS)
    assert rep["tool_tags"]["n_both"] == 3
    assert rep["query_tags_top5"]["n_both"] == 3
    assert "regen_tools_regen_queries" in rep["query_tags_top5"]["gate_pass_ceiling"]
    assert rep["toolbench_top1"]["n_both"] == 3
    assert "accuracy_vs_gold_sonnet" in rep["toolbench_top1"]
    assert "contains_gold_primary_regen" in rep["toolbench_top5"]


def test_evaluate_hash_tiny(generated, tmp_path):
    out = tmp_path / "evaluate.json"
    ar.main(["evaluate", "--regen-dir", str(generated["dir"]), "--backend", "hash",
             "--max-queries", "20", "--output", str(out)])
    rep = json.loads(out.read_text())
    names = set(rep["conditions"])
    assert "ToolBench toolbench_top5" in names and "MetaTool+Tags" in names
    c = rep["conditions"]["MetaTool+Tags"]
    assert c["n"] == 20 and "regen_vs_sonnet" in c["contrasts"]
    assert len(c["arms"]["regen"]["per_query"]["recall"]) == 20


def test_committed_files_unchanged(generated):
    # runs last in this module: generate, compare and evaluate have all run
    assert _tracked_hashes() == generated["before"]
