import asyncio
import json
from pathlib import Path

import httpx

from hallwise.research import (
    CORPUS_NOTE, RESEARCH_SCHEMA, RESEARCH_SYSTEM, CorpusSearch, Researcher, SearchClient, candidates, ground, parse_response,
)


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


PAGES = [
    {"url": "https://acme.example/", "title": "Acme", "text": "Acme builds robots for warehouses."},
    {"url": "https://acme.example/team", "title": "Team | Acme", "text": "Jo Park, CTO, leads hardware at Acme."},
]


def corpus_reply(findings, status="matched", annotations=()):
    """A Responses API answer with no web_search_call in it: the model only read the pages it was given."""
    text = json.dumps({"status": status, "findings": findings})
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text, "annotations": list(annotations)}]}],
            "usage": {"total_tokens": 3000, "input_tokens": 2600, "output_tokens": 400}}


def corpus_client(sent, reply, pages=PAGES):
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=reply)
    return CorpusSearch("k", pages, transport=httpx.MockTransport(handler))


def test_corpus_search_sends_the_pages_instead_of_a_search_tool():
    sent = []
    client = corpus_client(sent, corpus_reply([], status="no_public_record",
                                              annotations=[{"type": "url_citation", "url": "https://elsewhere.org/x"}]))
    out = asyncio.run(client(RESEARCH_SYSTEM, "Person: Jo Park\nCompany: Acme"))
    body = sent[0]
    assert "tools" not in body and "include" not in body  # nothing searched
    assert body["model"] == SearchClient("k").model and body["text"]["format"]["schema"] is not None
    assert body["instructions"] == RESEARCH_SYSTEM + CORPUS_NOTE
    assert body["input"].startswith("Person: Jo Park\nCompany: Acme")
    assert all(p["url"] in body["input"] and p["text"] in body["input"] for p in PAGES)
    assert out["results"] == [{"url": p["url"], "title": p["title"], "snippet": p["text"]} for p in PAGES]
    assert out["cited"] == [] and out["searches"] == 1  # a citation off the pages is no source


def test_corpus_findings_must_cite_a_page(tmp_path):
    clock, sent = FakeClock(), []
    client = corpus_client(sent, corpus_reply([
        {"kind": "company", "text": "Acme builds robots for warehouses.", "url": "https://acme.example/"},
        {"kind": "profile", "text": "Jo Park is CTO at Acme.", "url": "https://acme.example/team"},
        {"kind": "recent", "text": "Acme raised a seed round.", "url": "https://news.example/acme-raises"},  # not a page
    ]))
    r = Researcher(tmp_path, client, clock=clock, sleep=clock.sleep)
    person = {"key": "jo-park-acme", "record_key": "jo", "name": "Jo Park", "company": "Acme", "role": ""}
    out = asyncio.run(r.run([person]))
    got = out["people"][0]
    assert got["status"] == "matched" and got["corpus"] is True
    assert [(f["kind"], f["source"]) for f in got["findings"]] == [
        ("company", "https://acme.example/"), ("profile", "https://acme.example/team")]
    assert out["searches"] == 1 and out["requests"] == 1

    assert (tmp_path / "research" / "corpus" / "jo-park-acme.json").exists()  # cached apart from the web's
    assert not (tmp_path / "research" / "jo-park-acme.json").exists()
    web = Researcher(tmp_path, fake_search(clock, []), clock=clock, sleep=clock.sleep)
    assert web.cached("jo-park-acme") is None  # the web never sees a corpus result
    assert asyncio.run(r.run([person]))["people"][0]["cached"] is True and len(sent) == 1


def test_from_env_reads_the_corpus_when_it_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "x")
    monkeypatch.delenv("HALLWISE_RESEARCH", raising=False)
    assert type(Researcher.from_env(tmp_path).search) is SearchClient  # the web by default

    corpus = tmp_path / "web.json"
    corpus.write_text(json.dumps({"pages": PAGES}))
    monkeypatch.setenv("HALLWISE_RESEARCH_CORPUS", str(corpus))
    r = Researcher.from_env(tmp_path)
    assert isinstance(r.search, CorpusSearch) and r.search.pages == PAGES
    assert r.dir == tmp_path / "research" / "corpus"

    monkeypatch.setenv("HALLWISE_RESEARCH_CORPUS", str(tmp_path / "missing.json"))
    off = Researcher.from_env(tmp_path)
    assert off.search is None and "HALLWISE_RESEARCH_CORPUS" in off.off_reason  # never the web instead


def test_the_demo_corpus_points_at_no_real_site():
    pages = CorpusSearch.load("k", Path(__file__).parents[2] / "demo" / "rig" / "fictional-web.json").pages
    assert 12 <= len(pages) <= 18
    assert all(httpx.URL(p["url"]).host.endswith(".example") for p in pages)  # RFC 2606
    corvane = " ".join(p["text"] for p in pages if httpx.URL(p["url"]).host == "corvane.example")
    assert "Margaux Lefèvre" in corvane and "Chloé Martin" in corvane and "Julien" not in corvane
