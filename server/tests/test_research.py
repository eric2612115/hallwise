import asyncio
import json

from hallwise.research import RESEARCH_SCHEMA, Researcher, candidates, ground, parse_response


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def people(n):
    return [{"key": f"p{i}-acme", "record_key": f"p{i}", "name": f"Person {i}", "company": "Acme", "role": ""} for i in range(n)]


def fake_search(clock, calls, tokens=9000, answer=None, results=None):
    async def search(instructions, input, schema=None, name=""):
        assert schema is RESEARCH_SCHEMA
        calls.append((clock(), input))
        clock.t += 1.0  # a request takes a second
        return {"answer": answer or {"status": "no_public_record", "findings": []}, "results": results or [],
                "cited": [], "searches": 1, "usage": {"total_tokens": tokens, "input_tokens": tokens - 500, "output_tokens": 500}}
    return search


def test_research_is_rate_limited_capped_and_cached(tmp_path):
    clock, calls = FakeClock(), []
    r = Researcher(tmp_path, fake_search(clock, calls), clock=clock, sleep=clock.sleep, budget=1_000_000)
    out = asyncio.run(r.run(people(10)))
    assert out["requests"] == len(calls) == 8  # at most eight lookups per run
    starts = [t for t, _ in calls]
    assert all(b - a >= 3.0 for a, b in zip(starts, starts[1:]))  # one at a time, three seconds apart
    assert [s["reason"] for s in out["skipped"]] == ["over 8 lookups this run"] * 2
    assert {p["status"] for p in out["people"]} == {"no_public_record"}
    assert (tmp_path / "research" / "p0-acme.json").exists()

    again = asyncio.run(r.run(people(8)))
    assert again["requests"] == 0 and len(calls) == 8  # a week's cache answers
    assert all(p["cached"] for p in again["people"])

    clock.t += 8 * 86400  # a week later the cache is stale
    later = asyncio.run(r.run(people(1)))
    assert later["requests"] == 1 and len(calls) == 9


def test_research_stops_at_the_token_budget(tmp_path):
    clock, calls = FakeClock(), []
    r = Researcher(tmp_path, fake_search(clock, calls, tokens=10_000), clock=clock, sleep=clock.sleep,
                   budget=30_000, reserve=10_000)
    out = asyncio.run(r.run(people(5)))
    assert len(calls) == 3
    assert out["tokens"] == 30_000
    assert [s["reason"] for s in out["skipped"]] == ["token budget (30000) spent"] * 2


def test_research_off_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HALLWISE_RESEARCH", "off")
    monkeypatch.setenv("MODEL_API_KEY", "x")
    r = Researcher.from_env(tmp_path)
    out = asyncio.run(r.run(people(2)))
    assert out["enabled"] is False and out["people"] == [] and out["requests"] == 0
    assert all("HALLWISE_RESEARCH=off" in s["reason"] for s in out["skipped"])


def test_findings_need_a_source_the_search_returned():
    results = [
        {"url": "https://www.acme.com/about", "title": "About Acme", "snippet": "Acme builds robots for warehouses"},
        {"url": "https://news.example.com/acme-raises", "title": "Acme raises a seed round", "snippet": "seed round"},
    ]
    answer = {"status": "matched", "findings": [
        {"kind": "company", "text": "Acme builds robots for warehouses", "url": "acme.com"},  # a site name: the result on it
        {"kind": "profile", "text": "Jo Park is CTO at Acme", "url": "https://www.acme.com/team/jo-park"},  # made up
        {"kind": "recent", "text": "Acme raised a seed round", "url": "https://news.example.com/acme-raises/"},
    ]}
    status, findings = ground(answer, results, [])
    assert status == "partial"  # the profile had no real source, so nothing ties the person to the company
    assert [(f["kind"], f["source"]) for f in findings] == [
        ("company", "https://www.acme.com/about"), ("recent", "https://news.example.com/acme-raises")]

    status, findings = ground({"status": "matched", "findings": [{"kind": "profile", "text": "x", "url": "https://elsewhere.org/x"}]}, results, [])
    assert (status, findings) == ("no_public_record", [])  # a fictional person: nothing survives


def test_parse_response_takes_the_last_message_and_every_result():
    data = {"output": [
        {"type": "message", "content": [{"type": "output_text", "text": "Searching now."}]},
        {"type": "web_search_call", "status": "completed", "results": [{"url": "https://a.com", "title": "A", "snippet": "s"}]},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"status": "partial", "findings": []}),
                                         "annotations": [{"type": "url_citation", "url": "https://b.com"}]}]},
    ], "usage": {"total_tokens": 7}}
    out = parse_response(data)
    assert out["answer"] == {"status": "partial", "findings": []}
    assert out["results"][0]["url"] == "https://a.com" and out["cited"] == ["https://b.com"]
    assert out["searches"] == 1 and out["usage"]["total_tokens"] == 7


def test_candidates_need_a_name_and_a_company():
    record = {"people": [
        {"key": "kenji", "name": "Kenji Watanabe", "company": "Hoshizora Robotics"},
        {"key": "julian", "name": "Julian", "company": ""},
        {"key": "margot", "name": "Margot Lefèvre", "company": ""},
        {"key": "sid", "name": "Sid", "company": "Quill Mesh"},
        {"key": "x", "name": "", "company": "Acme"},
    ]}
    found, skipped = candidates(record)
    assert [p["name"] for p in found] == ["Kenji Watanabe"]
    assert found[0]["key"] == "kenji-watanabe-hoshizora-robotics" and found[0]["record_key"] == "kenji"
    assert {s["name"]: s["reason"] for s in skipped} == {
        "Julian": "no company to search", "Margot Lefèvre": "no company to search", "Sid": "first name only"}
