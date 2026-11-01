"""The edge finder: Muse Spark Open reads the transcript as it grows and finds edges (what someone said not to the
owner that shows what they want); they go through the same check as Muse Spark's own."""

import asyncio
import json

import httpx
import pytest

from hallwise.edge_finder import EDGE_SCHEMA, EDGE_SYSTEM, OPEN, OPEN_MODEL, OPEN_URL, EdgeFinder, OpenClient, clean
from hallwise.extract import EDGE_RULE, SCHEMA

MARGAUX = {"key": "margaux-lefevre-corvane-capital", "name": "Margaux Lefèvre", "company": "Corvane Capital",
           "speakers": ["1:D"], "evidence_turns": [10]}
PICTURE = {"people": [MARGAUX], "promises": []}
EDGE = {"person": "margaux-lefevre-corvane-capital", "turns": [7], "language": "French", "said": "Une page, avec des chiffres",
        "english": "One page, with numbers", "text": "Said to herself, in French: 'one page, with numbers'.",
        "act": "one page, numbers first"}


def test_it_asks_for_edges_only_with_the_rule_spark_uses():
    assert EDGE_SCHEMA["properties"] == {"edges": SCHEMA["properties"]["edges"]}
    assert EDGE_RULE in EDGE_SYSTEM
    assert "speaker keys" in EDGE_SYSTEM


def test_clean_keeps_well_formed_edges_only():
    raw = {"edges": [
        {**EDGE, "turns": [7, "8", None], "act": None},
        {**EDGE, "person": ""},  # nobody
        {**EDGE, "said": "  "},  # no words
        "noise",
    ]}
    assert clean(raw) == [{**EDGE, "turns": [7], "act": ""}]
    assert clean(None) == [] and clean({"edges": None}) == []


def test_the_call_to_baseten():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request, body))
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"people": [], "promises": [], "suspect_words": []}'}}],
                                             "usage": {"prompt_tokens": 1355, "completion_tokens": 1162, "total_tokens": 2517}})
        if len(seen) == 2:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"people": [{"name": "Ken'}, "finish_reason": "stop"}],
                                             "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050}})
        if len(seen) == 3:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"people": []}'}}],
                                             "usage": {"prompt_tokens": 1000, "completion_tokens": 900, "total_tokens": 1900}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "", "reasoning_content": "hmm"}, "finish_reason": "length"}]})

    client = OpenClient("secret", transport=httpx.MockTransport(handler))
    assert asyncio.run(client("sys", "user")) == {"people": [], "promises": [], "suspect_words": []}
    request, body = seen[0]
    assert str(request.url) == OPEN_URL
    assert request.headers["authorization"] == "Api-Key secret"
    assert body["model"] == OPEN_MODEL == "meta-models/muse-spark-open-1026"
    assert body["max_tokens"] >= 2000  # it reasons first: less and the content comes back empty
    assert body["reasoning_effort"] == "low"
    assert body["response_format"] == {"type": "json_schema", "json_schema": {"name": "hallwise_edges", "schema": EDGE_SCHEMA}}
    assert client.last_usage["total_tokens"] == 2517
    # an answer cut off mid-string is asked for once more, and both calls count
    assert asyncio.run(client("sys", "user")) == {"people": []}
    assert client.last_usage["total_tokens"] == 1050 + 1900
    with pytest.raises(ValueError, match="finish_reason length"):
        asyncio.run(client("sys", "user"))
    assert len(seen) == 5  # an empty answer is tried twice too


def test_a_schema_the_server_refuses_falls_back_to_json_in_the_prompt():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(400, json={"error": "response_format json_schema not supported"})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"people": []}'}}]})

    assert asyncio.run(OpenClient("k", transport=httpx.MockTransport(handler))("sys", "user")) == {"people": []}
    assert bodies[1]["response_format"] == {"type": "json_object"}
    assert "Reply with JSON matching this schema" in bodies[1]["messages"][1]["content"]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeOpen:
    def __init__(self, result, fail=False):
        self.result, self.fail, self.calls, self.prompts = result, fail, 0, []
        self.last_usage = {"prompt_tokens": 1200, "completion_tokens": 900, "total_tokens": 2100,
                           "completion_tokens_details": {"reasoning_tokens": 700}}
        self.last_seconds = 4.2

    async def __call__(self, system, user, schema=None, name=""):
        self.calls += 1
        self.prompts.append((system, user, schema, name))
        await asyncio.sleep(0)
        if self.fail:
            raise httpx.ConnectError("no route")
        return self.result


def test_every_third_run_at_most_one_in_flight_ten_seconds_apart_and_a_cap():
    clock = Clock()
    llm = FakeOpen({"edges": [EDGE]})
    finder = EdgeFinder(llm, every=3, min_gap_s=10, max_calls=2, clock=clock)
    log, found = [], []

    def sink(type, t_ms, **data):
        log.append((type, data))

    async def run():
        def spark_run():
            return finder.after_spark_run(sink, lambda edges, t: found.append(edges), lambda: "prompt", lambda: PICTURE, 30,
                                          lambda: 5000)

        assert [spark_run(), spark_run()] == [False, False]
        assert spark_run() is True  # the third
        assert finder.busy
        clock.t += 1
        assert [spark_run(), spark_run(), spark_run()] == [False, False, False]  # in flight, then within 10 s
        await finder.task
        clock.t += 5
        assert spark_run() is False  # 6 s after the last call: due, waiting for the gap
        clock.t += 5
        assert spark_run() is True  # the wait is over: the due call goes now
        await finder.task
        clock.t += 60
        for _ in range(6):
            assert spark_run() is False  # the cap: two calls per recording
        assert await finder.finish(sink, lambda edges, t: found.append(edges), lambda: "prompt", lambda: PICTURE, 30,
                                   lambda: 9000) is False  # no call left: the recording falls back on Spark

    asyncio.run(run())
    assert llm.calls == 2 and found == [[EDGE], [EDGE]]
    runs = [d for t, d in log if t == "second_run"]
    assert [r["call"] for r in runs] == [1, 2] and runs[0]["role"] == "edge_finder" and runs[0]["edges"] == 1
    assert runs[0]["usage"] == {"prompt_tokens": 1200, "completion_tokens": 900, "reasoning_tokens": 700, "total_tokens": 2100}
    assert runs[0]["seconds"] == 4.2 and runs[0]["model"] == OPEN
    assert runs[1]["totals"]["calls"] == 2 and runs[1]["totals"]["prompt_tokens"] == 2400
    system, user, schema, name = llm.prompts[0]
    assert (system, schema, name) == (EDGE_SYSTEM, EDGE_SCHEMA, "hallwise_edges")
    assert user.startswith("prompt\n\nPeople the owner has met tonight")
    assert "- margaux-lefevre-corvane-capital | Margaux Lefèvre, Corvane Capital | speaker keys: 1:D" in user
    assert not [t for t, _ in log if t in ("confirmed", "disagreement")]  # no comparison any more


def test_the_end_of_a_recording_always_gets_a_call_after_the_gap():
    clock = Clock()
    finder = EdgeFinder(FakeOpen({"edges": []}), every=3, min_gap_s=0.05, clock=lambda: clock())
    log, found = [], []
    ok = asyncio.run(finder.finish(lambda type, t_ms, **d: log.append(type), lambda e, t: found.append(e), lambda: "p",
                                   lambda: PICTURE, 30, lambda: 1))
    assert ok is True and log == ["second_run"] and found == [[]] and finder.calls == 1


def test_nobody_met_yet_means_no_call():
    llm = FakeOpen({"edges": [EDGE]})
    events, edges = asyncio.run(EdgeFinder(llm, clock=Clock()).listen("p", lambda: {"people": []}, 3, lambda: 1))
    assert (events, edges, llm.calls) == ([], [], 0)


def test_a_failure_is_logged_and_handed_on_as_none():
    finder = EdgeFinder(FakeOpen({}, fail=True), every=1, clock=Clock())
    log, found = [], []

    async def run():
        assert finder.after_spark_run(lambda type, t_ms, **d: log.append((type, d)), lambda e, t: found.append(e), lambda: "p",
                                      lambda: PICTURE, 30, lambda: 7)
        await finder.task

    asyncio.run(run())
    assert [t for t, _ in log] == ["second_error"] and found == [None]
    assert "ConnectError" in log[0][1]["message"]


def test_it_is_off_without_a_key_or_when_turned_off(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    assert EdgeFinder.from_env() is None
    monkeypatch.setenv("BASETEN_API_KEY", "k")
    monkeypatch.setenv("HALLWISE_SECOND", "off")
    assert EdgeFinder.from_env() is None
    monkeypatch.setenv("HALLWISE_SECOND", "on")
    finder = EdgeFinder.from_env()
    assert finder is not None and (finder.every, finder.min_gap_s, finder.max_calls) == (3, 10.0, 30)
    assert finder.llm.effort == "low"
