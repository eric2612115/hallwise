"""The second listener: Muse Spark Open re-hears the transcript; the two Meta models' readings are compared."""

import asyncio
import json

import httpx
import pytest

from hallwise.second import (
    MAIN, OPEN, OPEN_MODEL, OPEN_URL, SECOND_SCHEMA, OpenClient, SecondListener, compare, validate, what_similarity,
)


def person(key, name, company, speakers, turn=3):
    return {"key": key, "name": name, "company": company, "speakers": speakers, "evidence_turns": [turn]}


def promise(key, owed_by, owed_to, what, due="", turn=5):
    return {"key": key, "owed_by": owed_by, "owed_to": owed_to, "what": what, "due": due, "evidence_turns": [turn]}


SPARK = {
    "people": [
        person("leo-wong-bright-path", "Leo Wong", "Bright Path", ["1:A"]),
        person("margot-lefevre-corvane", "Margot Lefèvre", "Corvane Capital", ["1:C"], turn=16),
        person("kenji-watanabe-hoshizora-robotics", "Kenji Watanabe", "Hoshizora Robotics", ["1:G"], turn=24),
    ],
    "promises": [
        promise("deck-to-leo", "owner", "leo-wong-bright-path", "our deck", "tonight"),
        promise("one-pager-to-margot", "owner", "margot-lefevre-corvane", "one-pager", "tomorrow", turn=18),
        promise("coffee-kenji", "owner", "kenji-watanabe-hoshizora-robotics", "coffee", "Friday", turn=26),
    ],
}


def test_agreement_is_found_whatever_the_keys_and_the_wording():
    other = {
        "people": [
            {"name": "leo wong", "company": "Bright Path", "speakers": ["1:A"]},  # case set aside
            {"name": "Margot Lefevre", "company": "Corvane Capital", "speakers": ["1:C"]},  # accents set aside
            {"name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:G", "1:H"]},
        ],
        "promises": [
            {"owed_by": "owner", "owed_to": "Leo Wong", "what": "send the deck", "due": "tonight", "turn": 5},
            {"owed_by": "owner", "owed_to": "Margot Lefevre", "what": "one page with numbers", "due": "by tomorrow", "turn": 18},
            {"owed_by": "owner", "owed_to": "Kenji", "what": "coffee", "due": "Friday", "turn": 26},
        ],
        "suspect_words": [],
    }
    cmp = compare(SPARK, other, upto_turn=30)
    assert sorted(cmp.confirmed) == sorted([
        "person:leo-wong-bright-path", "person:margot-lefevre-corvane", "person:kenji-watanabe-hoshizora-robotics",
        "promise:deck-to-leo", "promise:one-pager-to-margot", "promise:coffee-kenji",
    ])
    assert cmp.confirmed["promise:deck-to-leo"] == {"kind": "promise", "key": "deck-to-leo", "by": [MAIN, OPEN]}
    assert cmp.disagreements == {}


def test_a_name_heard_two_ways_and_a_promise_only_one_model_heard_are_disagreements():
    other = {
        "people": [
            {"name": "Leo Wong", "company": "Bright Path", "speakers": ["1:A"]},
            {"name": "Margaux Lefèvre", "company": "Corvane Capital", "speakers": ["1:C"]},
            {"name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:G"]},
        ],
        "promises": [
            {"owed_by": "owner", "owed_to": "Margaux Lefèvre", "what": "one-pager", "due": "tomorrow", "turn": 18},
            {"owed_by": "owner", "owed_to": "Kenji Watanabe", "what": "coffee", "due": "Thursday", "turn": 26},
            {"owed_by": "Leo Wong", "owed_to": "owner", "what": "intro to his CTO", "due": "", "turn": 9},
        ],
        "suspect_words": [],
    }
    cmp = compare(SPARK, other, upto_turn=30)
    name = cmp.disagreements["person:margot-lefevre-corvane:name"]
    assert name["speaker"] == "1:C" and name["turn"] == 16
    assert name["a"] == {"by": MAIN, "text": "Margot Lefèvre"} and name["b"] == {"by": OPEN, "text": "Margaux Lefèvre"}
    # the one-pager is still matched to Margot through her voice, so it is confirmed
    assert "promise:one-pager-to-margot" in cmp.confirmed
    assert "person:margot-lefevre-corvane" not in cmp.confirmed
    deck = cmp.disagreements["promise:deck-to-leo:exists"]
    assert deck["a"]["text"] == "our deck · tonight · to Leo Wong" and deck["b"]["text"] == ""
    assert cmp.disagreements["promise:coffee-kenji:due"]["a"]["text"] == "Friday"
    assert cmp.disagreements["promise:coffee-kenji:due"]["b"]["text"] == "Thursday"
    (only_open,) = [d for d in cmp.disagreements.values() if d["field"] == "exists" and not d["key"]]
    assert only_open["owed_by"] == "leo-wong-bright-path" and only_open["owed_to"] == "owner"
    assert only_open["a"]["text"] == "" and only_open["b"]["text"] == "intro to his CTO · from Leo Wong"


def test_people_without_a_label_pair_by_first_name_and_spark_items_open_never_heard_are_left_out():
    spark = {"people": [person("julian", "Julian", "", []), *SPARK["people"]], "promises": SPARK["promises"]}
    other = {"people": [{"name": "Julien Caron", "company": "", "speakers": ["1:D"]}], "promises": [], "suspect_words": []}
    cmp = compare(spark, other, upto_turn=10)  # Margot (16), Kenji (24) and their promises come later
    assert cmp.disagreements["person:julian:name"]["b"]["text"] == "Julien Caron"
    assert list(cmp.disagreements) == ["person:julian:name", "promise:deck-to-leo:exists"]


def test_a_promise_to_someone_spark_never_listed_still_matches_by_key():
    """Live run, Oct 27: the transcriber put Kenji's introduction inside Siddharth's turn, so Muse Spark listed no
    Kenji but kept the coffee owed to kenji-watanabe-hoshizora-robotics; Spark Open owed it to "Kenji Watanabe"."""
    spark = {"people": [person("siddharth-raghunathan-quill-mesh", "Siddharth Raghunathan", "Quill Mesh", ["1:F"], turn=23)],
             "promises": [promise("coffee-to-kenji-watanabe-hoshizora-robotics", "owner", "kenji-watanabe-hoshizora-robotics",
                                  "coffee", "Friday", turn=24)]}
    for owed_to in ("Kenji Watanabe", "Kenji"):
        other = {"people": [{"name": "Siddharth Raghunathan", "company": "Quill Mesh", "speakers": ["1:F"]}],
                 "promises": [{"owed_by": "owner", "owed_to": owed_to, "what": "coffee", "due": "Friday", "turn": 24}],
                 "suspect_words": []}
        cmp = compare(spark, other, upto_turn=26)
        assert "promise:coffee-to-kenji-watanabe-hoshizora-robotics" in cmp.confirmed, owed_to
        assert cmp.disagreements == {}, owed_to
    # and when Open does not have it, the row still names who it is owed to
    alone = compare(spark, {"people": [], "promises": [], "suspect_words": []}, upto_turn=26)
    assert alone.disagreements["promise:coffee-to-kenji-watanabe-hoshizora-robotics:exists"]["a"]["text"] == (
        "coffee · Friday · to Kenji Watanabe Hoshizora Robotics")


def test_wording_similarity():
    assert what_similarity("send our deck", "the deck") == 1
    assert what_similarity("one-pager", "one page with numbers") >= 0.5
    assert what_similarity("demo at their office", "show them a demo") >= 0.5
    assert what_similarity("coffee", "introduction to Lena") < 0.5


def test_validate_drops_what_does_not_fit():
    raw = {"people": [{"name": "Kenji", "company": None, "speakers": "1:G"}, {"name": ""}, "x"],
           "promises": [{"what": "coffee", "turn": "26"}, {"what": ""}], "suspect_words": [{"heard": "Margox", "turn": None}]}
    assert validate(raw) == {
        "people": [{"name": "Kenji", "company": "", "speakers": []}],
        "promises": [{"owed_by": "", "owed_to": "", "what": "coffee", "due": "", "turn": 26}],
        "suspect_words": [{"heard": "Margox", "turn": -1, "likely": ""}],
    }
    assert validate(None) == {"people": [], "promises": [], "suspect_words": []}


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
    assert body["response_format"] == {"type": "json_schema", "json_schema": {"name": "hallwise_second", "schema": SECOND_SCHEMA}}
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
        self.result, self.fail, self.calls = result, fail, 0
        self.last_usage = {"prompt_tokens": 1200, "completion_tokens": 900, "total_tokens": 2100,
                           "completion_tokens_details": {"reasoning_tokens": 700}}
        self.last_seconds = 4.2

    async def __call__(self, system, user, schema=None, name=""):
        self.calls += 1
        await asyncio.sleep(0)
        if self.fail:
            raise httpx.ConnectError("no route")
        return self.result


AGREE = {"people": [{"name": "Leo Wong", "company": "Bright Path", "speakers": ["1:A"]}],
         "promises": [{"owed_by": "owner", "owed_to": "Leo Wong", "what": "deck", "due": "tonight", "turn": 5}],
         "suspect_words": []}
SPARK_LEO = {"people": [SPARK["people"][0]], "promises": [SPARK["promises"][0]]}


def test_every_third_run_at_most_one_in_flight_ten_seconds_apart_and_a_cap():
    clock = Clock()
    llm = FakeOpen(AGREE)
    second = SecondListener(llm, every=3, min_gap_s=10, max_calls=2, clock=clock)
    log = []

    def sink(type, t_ms, **data):
        log.append((type, data))

    async def run():
        def spark_run():
            return second.after_spark_run(sink, lambda: "prompt", lambda: SPARK_LEO, 30, lambda: 5000)

        assert [spark_run(), spark_run()] == [False, False]
        assert spark_run() is True  # the third
        assert second.busy
        clock.t += 1
        assert [spark_run(), spark_run(), spark_run()] == [False, False, False]  # in flight, then within 10 s
        await second.task
        clock.t += 5
        assert spark_run() is False  # 6 s after the last call: due, waiting for the gap
        clock.t += 5
        assert spark_run() is True  # the wait is over: the due call goes now
        await second.task
        clock.t += 60
        for _ in range(6):
            assert spark_run() is False  # the cap: two calls per recording
        await second.finish(sink, lambda: "prompt", lambda: SPARK_LEO, 30, lambda: 9000)

    asyncio.run(run())
    assert llm.calls == 2
    runs = [d for t, d in log if t == "second_run"]
    assert [r["call"] for r in runs] == [1, 2]
    assert runs[0]["usage"] == {"prompt_tokens": 1200, "completion_tokens": 900, "reasoning_tokens": 700, "total_tokens": 2100}
    assert runs[0]["seconds"] == 4.2 and runs[0]["model"] == OPEN
    assert runs[1]["totals"]["calls"] == 2 and runs[1]["totals"]["prompt_tokens"] == 2400
    # confirmed once, not again on the second call
    assert [d["key"] for t, d in log if t == "confirmed"] == ["leo-wong-bright-path", "deck-to-leo"]


def test_the_end_of_a_recording_always_gets_a_call_after_the_gap():
    clock = Clock()
    second = SecondListener(FakeOpen(AGREE), every=3, min_gap_s=0.05, clock=lambda: clock())
    log = []
    asyncio.run(second.finish(lambda type, t_ms, **d: log.append(type), lambda: "p", lambda: SPARK_LEO, 30, lambda: 1))
    assert log[0] == "second_run" and second.calls == 1


def test_a_failure_is_logged_and_goes_no_further():
    second = SecondListener(FakeOpen(AGREE, fail=True), every=1, clock=Clock())
    log = []

    async def run():
        assert second.after_spark_run(lambda type, t_ms, **d: log.append((type, d)), lambda: "p", lambda: SPARK_LEO, 30, lambda: 7)
        await second.task

    asyncio.run(run())
    assert [t for t, _ in log] == ["second_error"]
    assert "ConnectError" in log[0][1]["message"]


def test_a_disagreement_is_raised_once_and_withdrawn_when_the_models_agree():
    spark = {"people": [person("margot", "Margot Lefèvre", "", ["1:C"])], "promises": []}
    heard_margaux = {"people": [{"name": "Margaux Lefèvre", "company": "", "speakers": ["1:C"]}], "promises": [], "suspect_words": []}
    heard_margot = {"people": [{"name": "Margot Lefèvre", "company": "", "speakers": ["1:C"]}], "promises": [], "suspect_words": []}
    llm = FakeOpen(heard_margaux)
    second = SecondListener(llm, clock=Clock())

    async def run():
        out1 = await second.listen("p", lambda: spark, 10, lambda: 1)
        out2 = await second.listen("p", lambda: spark, 12, lambda: 2)
        llm.result = heard_margot
        out3 = await second.listen("p", lambda: spark, 14, lambda: 3)
        return out1, out2, out3

    out1, out2, out3 = asyncio.run(run())
    assert [(t, d.get("id")) for t, _, d in out1[1:]] == [("disagreement", "person:margot:name")]
    assert out2[1:] == []
    assert [(t, d.get("id", d.get("key"))) for t, _, d in out3[1:]] == [("confirmed", "margot"), ("disagreement_removed", "person:margot:name")]


def test_a_promise_only_open_heard_is_raised_once_in_any_wording_and_withdrawn_when_spark_has_it():
    extra = lambda what: {"people": [{"name": "Leo Wong", "company": "Bright Path", "speakers": ["1:A"]}],  # noqa: E731
                          "promises": [{"owed_by": "owner", "owed_to": "Leo Wong", "what": what, "due": "", "turn": 9}],
                          "suspect_words": []}
    llm = FakeOpen(extra("intro to Kenji"))
    second = SecondListener(llm, clock=Clock())
    nothing = {"people": [SPARK["people"][0]], "promises": []}
    with_it = {"people": [SPARK["people"][0]], "promises": [promise("intro-kenji", "owner", "leo-wong-bright-path", "introduce Kenji", turn=9)]}

    async def run():
        a = await second.listen("p", lambda: nothing, 10, lambda: 1)
        llm.result = extra("an introduction to Kenji")
        b = await second.listen("p", lambda: nothing, 11, lambda: 2)
        c = await second.listen("p", lambda: with_it, 12, lambda: 3)
        return a, b, c

    a, b, c = asyncio.run(run())
    assert [t for t, _, _ in a[1:]] == ["confirmed", "disagreement"]
    assert b[1:] == []  # reworded, not raised again
    assert [t for t, _, _ in c[1:]] == ["confirmed", "disagreement_removed"]


def test_it_is_off_without_a_key_or_when_turned_off(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    assert SecondListener.from_env() is None
    monkeypatch.setenv("BASETEN_API_KEY", "k")
    monkeypatch.setenv("HALLWISE_SECOND", "off")
    assert SecondListener.from_env() is None
    monkeypatch.setenv("HALLWISE_SECOND", "on")
    second = SecondListener.from_env()
    assert second is not None and (second.every, second.min_gap_s, second.max_calls) == (3, 10.0, 30)
