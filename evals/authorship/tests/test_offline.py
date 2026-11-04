"""Offline tests for evals/authorship (tag.py, validate.py, analyze.py, eval_tagged.py).

No network: every socket connection fails the test. Replies are canned,
malformed ones included. Run from the repo root with the kit's venv:

    python -m unittest discover -s evals/authorship/tests -v

The ToolBench normalization tests import eval_toolbench (BEAR). They are
skipped when BEAR is not installed.
"""
from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH = HERE.parent
EVALS = AUTH.parent
for p in (str(EVALS.parent), str(EVALS), str(AUTH)):
    if p not in sys.path:
        sys.path.insert(0, p)

import authorship_regenerate as ar  # noqa: E402
import metatool_tagging as mt  # noqa: E402
import analyze  # noqa: E402
import tag  # noqa: E402
import validate  # noqa: E402


def _no_network(*a, **kw):
    raise AssertionError("a test tried to open a network connection")


socket.create_connection = _no_network
_orig_socket_connect = socket.socket.connect
socket.socket.connect = lambda self, *a, **kw: _no_network()


class _Resp:
    def __init__(self, body: dict) -> None:
        self._b = io.BytesIO(json.dumps(body).encode())

    def read(self, *a):
        return self._b.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


def tool_reply(name: str, args) -> dict:
    a = args if isinstance(args, str) else json.dumps(args)
    return {"id": "x", "model": "qwen-test", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": a}}]}}]}


def text_reply(text: str) -> dict:
    return {"id": "x", "model": "qwen-test", "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


class Stub:
    """A transport that answers from a list of canned replies (or exceptions), in order."""

    def __init__(self, replies) -> None:
        self.replies = list(replies)
        self.requests = []

    def __call__(self, req, data=None, timeout=None, **kw):
        self.requests.append(json.loads(req.data.decode()))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)


class ShimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "calls.jsonl"
        self._sleep = mt.time.sleep
        mt.time.sleep = lambda s: None

    def tearDown(self):
        mt.time.sleep = self._sleep

    def records(self):
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf-8").splitlines()]

    def run_tool_tags(self, replies):
        stub = Stub(replies)
        shim = tag.RecordingShim("http://127.0.0.1:8355/v1", tag.client_extras(False, 7), self.log, transport=stub)
        shim.target = "tool_tags"
        with shim:
            try:
                return mt.generate_tool_tags("weatherapp", "forecasts", "m", "k"), stub
            except mt.TaggingError as e:
                return e, stub

    def test_valid_tool_call_is_logged_with_raw_reply(self):
        out, stub = self.run_tool_tags([tool_reply("assign_tool_categories", {"tags": ["weather", "location"]})])
        self.assertEqual(out, ["weather", "location"])
        r = self.records()[0]
        self.assertEqual(r["shim_outcome"], "tool_call")
        self.assertEqual(r["served_model"], "qwen-test")
        self.assertEqual(r["item"], "weatherapp")
        self.assertIn('"weather"', r["raw_tool_calls"][0]["arguments"])
        self.assertEqual(stub.requests[0]["seed"], 7)
        self.assertEqual(stub.requests[0]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(stub.requests[0]["temperature"], 0.0)
        self.assertNotIn("top_k", stub.requests[0])

    def test_malformed_arguments_then_valid_go_through_the_original_retry(self):
        out, stub = self.run_tool_tags([tool_reply("assign_tool_categories", "{not json"),
                                        tool_reply("assign_tool_categories", {"tags": ["finance"]})])
        self.assertEqual(out, ["finance"])
        recs = self.records()
        self.assertEqual([r["shim_outcome"] for r in recs], ["bad_tool_arguments", "tool_call"])

    def test_no_tool_call_six_times_raises_tagging_error(self):
        out, _ = self.run_tool_tags([text_reply("I think it is weather")] * 6)
        self.assertIsInstance(out, mt.TaggingError)
        self.assertEqual([r["shim_outcome"] for r in self.records()], ["no_tool_call"] * 6)

    def test_only_out_of_vocabulary_tags_is_a_tagging_error(self):
        out, _ = self.run_tool_tags([tool_reply("assign_tool_categories", {"tags": ["search", "weathers"]})])
        self.assertIsInstance(out, mt.TaggingError)

    def test_http_429_is_logged_and_retried(self):
        err = urllib.error.HTTPError("u", 429, "busy", {}, io.BytesIO(b"busy"))
        out, _ = self.run_tool_tags([err, tool_reply("assign_tool_categories", {"tags": ["news"]})])
        self.assertEqual(out, ["news"])
        self.assertEqual([r["shim_outcome"] for r in self.records()], ["http_error", "tool_call"])

    def test_think_block_is_removed_from_text(self):
        reply, notes = ar.translate_response(text_reply("<think>hmm</think>Travel & Local"))
        self.assertEqual(reply["content"][0]["text"], "Travel & Local")
        self.assertEqual(notes.get("think_block_removed"), 1)

    def test_anthropic_url_is_never_reached_and_others_refused(self):
        shim = tag.RecordingShim("http://127.0.0.1:8355/v1", {}, None, transport=Stub([]))
        with shim:
            with self.assertRaises(ar.ShimRefused):
                urllib.request.urlopen("https://example.com/x")

    def test_item_of(self):
        self.assertEqual(tag.item_of("x\nTool name: foo_bar\nDescription: d"), "foo_bar")
        self.assertEqual(tag.item_of("Categories:\n- A\n\nQuery: where is it?\n\nCategory:"), "where is it?")


class ServerTests(unittest.TestCase):
    def test_parse_load_shapes(self):
        self.assertEqual(tag.parse_load([{"dp_rank": 0, "num_reqs": 2, "num_waiting_reqs": 1}]),
                         {"running": 2, "waiting": 1})
        self.assertEqual(tag.parse_load({"num_running_reqs": 0, "num_queue_reqs": 0}), {"running": 0, "waiting": 0})
        self.assertIsNone(tag.parse_load({"something": "else"}))

    def test_parse_metrics(self):
        txt = 'sglang:num_running_reqs{model_name="q"} 3.0\nsglang:num_queue_reqs{model_name="q"} 0.0\n'
        self.assertEqual(tag.parse_metrics(txt), {"running": 3, "waiting": 0})
        self.assertIsNone(tag.parse_metrics("# nothing"))

    def test_check_load(self):
        tag.check_load({"running": 0, "waiting": 0}, False, False)
        with self.assertRaises(SystemExit):
            tag.check_load({"running": 0, "waiting": 2}, True, False)
        with self.assertRaises(SystemExit):
            tag.check_load({"running": 1, "waiting": 0}, False, False)
        tag.check_load({"running": 1, "waiting": 0}, True, False)
        with self.assertRaises(SystemExit):
            tag.check_load({"unknown": "x"}, False, False)

    def test_concurrency_cap(self):
        info = {"server_info": {"max_running_requests": 8}}
        self.assertEqual(tag.concurrency(4, info), 4)
        with self.assertRaises(SystemExit):
            tag.concurrency(7, info)          # 8 - 2 room for other clients
        with self.assertRaises(SystemExit):
            tag.concurrency(9, {"server_info": {}})


class ValidateTests(unittest.TestCase):
    def rec(self, args, outcome="tool_call", item="foo"):
        return {"target": "tool_tags", "item": item, "shim_outcome": outcome,
                "raw_tool_calls": [] if args is None else [{"name": "t", "arguments": args}]}

    def test_metatool_outcomes(self):
        o = validate.metatool_outcome("tool_tags", self.rec(json.dumps({"tags": ["weather"]})), mt)
        self.assertEqual(o[:2], ("valid", ["weather"]))
        o = validate.metatool_outcome("tool_tags", self.rec(json.dumps({"tags": ["search"]})), mt)
        self.assertEqual(o[0], "invalid")
        o = validate.metatool_outcome("tool_tags", self.rec("{oops"), mt)
        self.assertEqual(o[0], "no_tool_call")
        o = validate.metatool_outcome("tool_tags", self.rec(None, outcome="no_tool_call"), mt)
        self.assertEqual(o[0], "no_tool_call")
        o = validate.metatool_outcome("tool_tags", {"shim_outcome": "http_error", "error": "HTTP 500"}, mt)
        self.assertEqual(o[0], "call_error")

    def test_query_outcomes(self):
        good = {"target": "query_tags_top5", "item": "q", "shim_outcome": "tool_call",
                "raw_tool_calls": [{"name": "t", "arguments": json.dumps(
                    {"primary_domain": "search", "additional_tags": ["weather", "search"]})}]}
        o = validate.metatool_outcome("query_tags_top5", good, mt)
        self.assertEqual(o[:2], ("valid", ["weather", "search"]))   # the original promotes a domain tag
        bad = dict(good, raw_tool_calls=[{"name": "t", "arguments": json.dumps(
            {"primary_domain": "search", "additional_tags": []})}])
        self.assertEqual(validate.metatool_outcome("query_tags_top5", bad, mt)[0], "invalid")

    def test_summarize_counts_retries(self):
        calls = [dict(self.rec("{x", "bad_tool_arguments"), utc="1"),
                 dict(self.rec(json.dumps({"tags": ["news"]})), utc="2"),
                 dict(self.rec(json.dumps({"tags": ["food"]}), item="bar"), utc="3")]
        s, per = validate.summarize_calls("tool_tags", calls, lambda r: validate.metatool_outcome(
            "tool_tags", r, mt)[0])
        self.assertEqual(s["calls"], 3)
        self.assertEqual(s["items_called"], 2)
        self.assertEqual(s["items_retried"], 1)
        self.assertEqual(s["final_call_outcome_per_item"], {"valid": 2})


@unittest.skipUnless(__import__("importlib").util.find_spec("bear"), "BEAR not installed")
class ToolBenchNormalizerTests(unittest.TestCase):
    def test_top1_and_multi(self):
        n1 = validate.ToolBenchNormalizer("toolbench_top1")
        lab = n1.labels[0]
        self.assertEqual(n1(lab)[0], "valid")
        self.assertEqual(n1(lab.upper())[0], "valid")
        self.assertEqual(n1("Not A Category")[0], "out_of_vocabulary")
        self.assertEqual(n1("")[0], "empty_reply")
        self.assertEqual(n1(f"<think>x</think>{lab}")[0], "valid")
        nm = validate.ToolBenchNormalizer("toolbench_multi")
        o, tags, n_oov = nm(f"{nm.labels[0]}, Nonsense")
        self.assertEqual((o, n_oov), ("partly_out_of_vocabulary", 1))
        self.assertEqual(nm("Nonsense")[0], "empty_set")


class AnalyzeTests(unittest.TestCase):
    def test_kappa(self):
        self.assertAlmostEqual(analyze.kappa_binary([True, False, True, False], [True, False, True, False]), 1.0)
        self.assertLess(analyze.kappa_binary([True, False, True, False], [False, True, False, True]), 0)

    def test_qt_keys_and_align(self):
        tmp = Path(tempfile.mkdtemp())
        a = tmp / "a.json"
        b = tmp / "b.json"
        a.write_text(json.dumps([{"query": "q1", "tools": ["T"], "context_tags": []},
                                 {"query": "q1", "tools": ["T"], "context_tags": []},
                                 {"query": "q2", "tools": ["U"], "context_tags": []},
                                 {"query": "", "tools": ["U"], "context_tags": []}]))
        b.write_text(json.dumps([{"query": "q2", "tools": ["U"], "context_tags": []},
                                 {"query": "q1", "tools": ["T"], "context_tags": []}]))
        ka, kb = analyze.qt_keys(a), analyze.qt_keys(b)
        self.assertEqual(len(ka), 3)
        ia, ib = analyze.align(ka, kb)
        self.assertEqual((ia, ib), ([0, 2], [1, 0]))

    def test_paired(self):
        r = analyze.paired([1, 1, 1, 0, 1, 1, 0, 1], [0, 1, 0, 0, 0, 1, 0, 0])
        self.assertAlmostEqual(r["delta"], 0.5)
        self.assertGreater(r["ci"][0], 0)


class EvalTaggedTests(unittest.TestCase):
    def test_query_tag_file_name_is_checked(self):
        import eval_tagged
        tmp = Path(tempfile.mkdtemp())
        (tmp / "plugin_tags.json").write_text("{}")
        (tmp / "qt.json").write_text("[]")
        with self.assertRaises(SystemExit):
            eval_tagged.main(["--tool-tags", str(tmp / "plugin_tags.json"), "--query-tags", str(tmp / "qt.json"),
                              "--backends", "BM25 (no gov)", "--output", str(tmp / "o.json")])


if __name__ == "__main__":
    unittest.main()
