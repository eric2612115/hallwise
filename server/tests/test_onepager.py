"""The deck, rebuilt for the person who'll read it: Muse Spark follows the edge's act, every number on the page is
one the deck has (one more try, then the line goes), and with no deck nothing is sent."""

import asyncio
import json

from hallwise.onepager import (
    ONEPAGER_SCHEMA, ONEPAGER_SYSTEM, Onepagers, build_prompt, clean, cue, event, find_person, numbers, problems, rebuild,
    rebuilt_event, render, said_in, slide_titles, slides,
)

DECK = """# Hallwise

Preface for the owner: 99 things that never reach the page.

## Hallwise

A name badge that remembers the room.

## Why now

- 410 Limitless users voted for a personal CRM.
<!-- Limitless feature board, 2025-12-08. -->
- Muse Spark has a 1M-token context.

## The build, in numbers

- Names heard right: 24 of 25 synthetic voices across 13 accents, with name hints.
<!-- Accent test, 2026-10-29. -->
- 4 Meta models. One person, nine days.
- 0 users.
"""

MARGAUX = {"key": "margaux-lefevre-corvane-capital", "name": "Margaux Lefèvre", "company": "Corvane Capital",
           "role": "Partner", "preferred_language": "", "speakers": ["1:D"]}
EDGE = {"person": MARGAUX["key"], "turns": [5, 7], "language": "French", "said": "Une page, avec des chiffres",
        "english": "One page, with numbers",
        "text": "Said to Julien, in French: yesterday's founder lost her with twenty slides and not one number. "
                "She wants one page, with numbers.",
        "act": "one page, numbers first"}
RECORD = {"people": [MARGAUX], "edges": [EDGE],
          "promises": [{"key": "deck-to-margaux", "owed_by": "owner", "owed_to": MARGAUX["key"], "what": "the deck", "due": "tomorrow"}]}
PROMISE = RECORD["promises"][0]

GOOD = {"applies": True, "shape": "one page, numbers first", "title": "Hallwise", "lede": "A name badge that remembers the room.",
        "figures": [{"value": "24 of 25", "label": "names heard right across 13 accents", "source": "Accent test, 2026-10-29"},
                    {"value": "410", "label": "Limitless users voted for a personal CRM", "source": "Limitless feature board, 2025-12-08"}],
        "sections": [{"heading": "Where it stands", "points": ["0 users.", "One person, nine days."]}],
        "close": "4 Meta models."}


class FakeSpark:
    """Muse Spark as the tests see it: the answers in order, every call kept, usage as the real client keeps it."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []
        self.last_usage = {}

    async def __call__(self, system, user, schema=None, name=""):
        self.calls.append({"system": system, "user": user, "schema": schema, "name": name})
        self.last_usage = {"prompt_tokens": 2000, "completion_tokens": 600, "total_tokens": 2600,
                           "completion_tokens_details": {"reasoning_tokens": 200}}
        return self.answers.pop(0)


def run(llm, record=RECORD, source=DECK, **kw):
    return asyncio.run(rebuild(llm, record, MARGAUX["key"], PROMISE, source, owner_name="Eric", owner_company="Hallwise",
                               day="October 30, 2026", **kw))


def with_figure(value, label):
    return {**GOOD, "figures": GOOD["figures"] + [{"value": value, "label": label, "source": ""}]}


# --- the number check -----------------------------------------------------------------------------------------

def test_numbers_are_read_one_way_however_they_are_written():
    assert numbers("24 of 25 names, 1,000 hints, 3.10 s, 2025-12-05, 20+ speakers, a 1M-token context") == {
        "24", "25", "1000", "3.1", "2025", "12", "5", "20", "1"}
    assert numbers("Twenty slides and not one number; nine days, a dozen") == {"20", "1", "9", "12"}
    assert numbers("Thursday, no, Friday") == set()
    assert numbers("") == set()


def test_a_number_the_deck_does_not_have_is_found_on_its_line():
    allowed, cited = numbers(said_in(DECK)), numbers(slides(DECK))
    assert "99" not in cited  # the preface is the owner's, not the page's
    page = clean({**GOOD, "sections": [{"heading": "Traction", "points": ["0 users.", "3 pilots signed.", "Twelve accents."]}]})
    found = problems(page, allowed, [], cited)
    # 12 is in the deck only as a date in a comment ("2025-12-08"): it backs a source, never a claim
    assert [(p["where"], p["numbers"]) for p in found] == [("sections[0].points[1]", ["3"]), ("sections[0].points[2]", ["12"])]
    assert problems(clean(GOOD), allowed, [], cited) == []
    sourced = clean(with_figure("410", "votes"))
    sourced["figures"][-1]["source"] = "Limitless feature board, 2025-12-31"  # a date the deck never gave
    assert [(p["where"], p["numbers"]) for p in problems(sourced, allowed, [], cited)] == [("figures[2]", ["31"])]


def test_a_page_with_an_unbacked_number_is_written_again_once_and_the_fix_kept():
    llm = FakeSpark(with_figure("96%", "names right"), GOOD)
    out = run(llm)
    assert out["status"] == "ok" and out["retried"] is True and out["dropped"] == []
    assert len(llm.calls) == 2
    again = llm.calls[1]["user"]
    assert again.startswith(llm.calls[0]["user"])
    assert "96% names right (not in the deck: 96)" in again
    assert out["page"]["figures"] == clean(GOOD)["figures"]
    assert out["usage"] == {"prompt_tokens": 4000, "completion_tokens": 1200, "total_tokens": 5200, "reasoning_tokens": 400, "calls": 2}


def test_a_line_still_unbacked_after_the_second_try_is_dropped_and_the_rest_kept():
    bad = {**with_figure("3", "pilots signed"),
           "sections": [{"heading": "Where it stands", "points": ["0 users.", "Raised 2 rounds."]},
                        {"heading": "Revenue", "points": ["$50 a month."]}]}
    llm = FakeSpark(bad, bad)
    out = run(llm)
    assert len(llm.calls) == 2 and out["status"] == "ok" and out["retried"] is True
    assert [(d["where"], d["numbers"]) for d in out["dropped"]] == [
        ("figures[2]", ["3"]), ("sections[0].points[1]", ["2"]), ("sections[1].points[0]", ["50"])]
    page = out["page"]
    assert [f["value"] for f in page["figures"]] == ["24 of 25", "410"]
    assert page["sections"] == [{"heading": "Where it stands", "points": ["0 users."]}]  # Revenue had nothing left
    assert "pilots" not in out["html"] and "$50" not in out["html"] and "Revenue" not in out["html"]


def test_the_readers_own_words_never_come_back_to_them():
    leaky = {**GOOD, "lede": "Hallwise: one page, with numbers.", "close": "Une page, avec des chiffres."}
    llm = FakeSpark(leaky, leaky)
    out = run(llm)
    assert {d["where"] for d in out["dropped"]} == {"lede", "close"} and all(d["quoted"] for d in out["dropped"])
    assert "too close to the reader's own words" in llm.calls[1]["user"]
    assert "chiffres" not in out["html"] and "with numbers" not in out["html"]


# --- the prompt -------------------------------------------------------------------------------------------------

def test_the_prompt_has_the_act_the_reader_the_promise_and_the_deck_never_what_was_said():
    prompt = build_prompt(DECK, MARGAUX, ["one page, numbers first"], PROMISE, owner_name="Eric", owner_company="Hallwise")
    assert prompt.splitlines()[:5] == [
        "Owner: Eric, from Hallwise",
        "Reader: Margaux Lefèvre, Corvane Capital, Partner",
        "Promised: the deck (due: tomorrow)",
        "Act (how the page should be shaped for this reader):",
        "- one page, numbers first",
    ]
    assert prompt.endswith(slides(DECK)) and "## Why now" in prompt and "<!-- Limitless feature board, 2025-12-08. -->" in prompt
    assert "Preface for the owner" not in prompt
    for heard in ("chiffres", "twenty slides", "Julien", "French", "One page, with numbers"):
        assert heard not in prompt


def test_the_call_follows_every_act_in_the_readers_language():
    record = {**RECORD, "people": [{**MARGAUX, "preferred_language": "French"}],
              "edges": [EDGE, {**EDGE, "turns": [9], "act": "one page, numbers first"}, {**EDGE, "turns": [11], "act": "no jargon"}]}
    llm = FakeSpark(GOOD, GOOD)
    run(llm, record=record)
    run(llm)  # she spoke English with the owner
    french, english = llm.calls
    assert french["name"] == "hallwise_onepager" and french["schema"] is ONEPAGER_SCHEMA
    assert french["system"] == ONEPAGER_SYSTEM.replace("{language}", "French")
    assert "- one page, numbers first\n- no jargon\n" in french["user"]  # each act once
    assert "Write in the deck's language." in english["system"]


def test_no_edge_no_person_or_no_deck_asks_nothing():
    llm = FakeSpark()
    assert run(llm, record={**RECORD, "edges": []})["status"] == "no_edge"
    assert run(llm, record={**RECORD, "edges": [{**EDGE, "act": " "}]})["status"] == "no_edge"
    assert run(llm, record={**RECORD, "people": []})["status"] == "no_person"
    assert run(llm, source="")["status"] == "no_source"
    assert run(llm, source=" \n")["status"] == "no_source"
    assert llm.calls == []


def test_an_act_about_something_else_makes_no_page():
    llm = FakeSpark({"applies": False, "title": "", "lede": "", "figures": [], "sections": [], "close": ""})
    out = run(llm, record={**RECORD, "edges": [{**EDGE, "act": "propose Wednesday, not Thursday"}]})
    assert out["status"] == "not_applicable" and "html" not in out and len(llm.calls) == 1


# --- the page ---------------------------------------------------------------------------------------------------

def test_the_page_is_plain_escaped_html_with_the_numbers_first():
    page = clean({**GOOD, "lede": "A badge <script>alert(1)</script> & more", "close": ""})
    out = render(page, brand="Hallwise", reader="Margaux Lefèvre, Corvane Capital", owner="Eric", day="October 30, 2026")
    assert "<script>" not in out and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in out
    assert "<img" not in out and "http" not in out and "<link" not in out
    assert "<h1>Hallwise</h1>" in out and "<footer><b>Hallwise</b> · Eric</footer>" in out
    assert "For Margaux Lefèvre, Corvane Capital" in out and "background: #fff" in out
    assert "@media print {\n  :root { --ink: #000; --soft: #000; --rule: #000; --accent: #000; }" in out  # black on white on paper
    assert out.index('class="figures"') < out.index("<section>")
    assert '<div class="value">24 of 25</div>' in out
    assert "Accent test, 2026\u201110\u201129" in out  # a date never breaks at its hyphens


def test_clean_keeps_the_page_to_one_page():
    raw = {"title": " Hallwise \n", "figures": [{"value": str(i), "label": "x", "source": None} for i in range(9)] + [{"value": ""}],
           "sections": [{"heading": f"S{i}", "points": ["a", "", 7, "b", "c", "d", "e"]} for i in range(8)] + [{"heading": "empty", "points": []}]}
    page = clean(raw)
    assert page["applies"] is True and page["title"] == "Hallwise"
    assert len(page["figures"]) == 6 and page["figures"][0] == {"value": "0", "label": "x", "source": ""}
    assert len(page["sections"]) == 5 and page["sections"][0]["points"] == ["a", "b", "c", "d"]
    assert clean(None) == {"applies": True, "shape": "", "title": "", "lede": "", "figures": [], "sections": [], "close": ""}


# --- on disk, and the off switch --------------------------------------------------------------------------------

def test_off_without_a_deck_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("HALLWISE_DECK", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "x")
    pages = Onepagers.from_env(tmp_path)
    assert pages.enabled is False and pages.llm is None
    out = asyncio.run(pages.rebuild("rec-1", RECORD, MARGAUX["key"], PROMISE))
    assert out["status"] == "off" and out["reason"] == "HALLWISE_DECK is not set"
    moves = [{"promise_key": "deck-to-margaux", "person_key": MARGAUX["key"], "kind": "email", "attach": "deck"}]
    assert asyncio.run(pages.for_moves("rec-1", RECORD, moves)) == {}
    assert not (tmp_path / "onepagers").exists()

    monkeypatch.setenv("HALLWISE_DECK", str(tmp_path / "deck.md"))
    monkeypatch.delenv("MODEL_API_KEY")
    assert Onepagers.from_env(tmp_path).off_reason == "MODEL_API_KEY is not set"


def test_an_unreadable_deck_is_off_too(tmp_path, monkeypatch):
    monkeypatch.setenv("HALLWISE_DECK", str(tmp_path / "missing.md"))
    monkeypatch.setenv("MODEL_API_KEY", "x")
    pages = Onepagers.from_env(tmp_path)
    assert pages.enabled and pages.model == "muse-spark-1.3"
    out = asyncio.run(pages.rebuild("rec-1", RECORD, MARGAUX["key"], PROMISE))
    assert out["status"] == "off" and out["reason"] == "HALLWISE_DECK unreadable (FileNotFoundError)"


def test_a_page_is_kept_per_recording_and_person_and_not_asked_for_twice(tmp_path):
    deck = tmp_path / "deck.md"
    deck.write_text(DECK)
    llm = FakeSpark(GOOD, GOOD)
    pages = Onepagers(tmp_path, llm, deck, model="muse-spark-1.3")
    out = asyncio.run(pages.rebuild("rec-1", RECORD, MARGAUX["key"], PROMISE, owner_name="Eric", owner_company="Hallwise"))
    assert out["status"] == "ok" and out["cached"] is False and "html" not in out
    assert out["file"] == f"onepagers/rec-1/{MARGAUX['key']}.html"
    assert "<h1>Hallwise</h1>" in pages.html("rec-1", MARGAUX["key"])
    kept = json.loads((tmp_path / "onepagers" / "rec-1" / f"{MARGAUX['key']}.json").read_text())
    assert kept["acts"] == ["one page, numbers first"] and kept["usage"]["calls"] == 1 and "html" not in kept

    again = asyncio.run(pages.rebuild("rec-1", RECORD, MARGAUX["key"], PROMISE, owner_name="Eric", owner_company="Hallwise"))
    assert again["cached"] is True and len(llm.calls) == 1
    deck.write_text(DECK.replace("0 users.", "0 users. One page."))  # a changed deck is a new page
    asyncio.run(pages.rebuild("rec-1", RECORD, MARGAUX["key"], PROMISE, owner_name="Eric", owner_company="Hallwise"))
    assert len(llm.calls) == 2

    assert set(event(out)) == {"person_key", "promise_key", "acts", "slides", "status", "file", "dropped", "retried",
                               "usage", "seconds", "model", "cached"}
    assert out["slides"] == ["Hallwise", "Why now", "The build, in numbers"]
    assert pages.html("../etc", "passwd") is None and pages.html("rec-1", "../x") is None
    bad = asyncio.run(pages.rebuild("rec/1", RECORD, MARGAUX["key"], PROMISE))
    assert bad["status"] == "error" and len(llm.calls) == 2


def test_a_failed_call_is_an_error_not_an_exception_and_is_not_kept(tmp_path):
    deck = tmp_path / "deck.md"
    deck.write_text(DECK)

    async def broken(system, user, schema=None, name=""):
        raise TimeoutError("slow")

    pages = Onepagers(tmp_path, broken, deck)
    out = asyncio.run(pages.rebuild("rec-1", RECORD, MARGAUX["key"], PROMISE))
    assert out["status"] == "error" and out["reason"] == "TimeoutError: slow"
    assert pages.get("rec-1", MARGAUX["key"]) is None


def test_one_page_per_person_with_an_edge_for_the_move_that_attaches_the_deck(tmp_path):
    deck = tmp_path / "deck.md"
    deck.write_text(DECK)
    julien = {"key": "julien-caron-corvane-capital", "name": "Julien Caron", "company": "Corvane Capital"}
    record = {**RECORD, "people": [MARGAUX, julien], "promises": RECORD["promises"] + [
        {"key": "coffee-margaux", "what": "coffee", "due": "Friday"}, {"key": "intro-julien", "what": "an introduction"}]}
    moves = [
        {"promise_key": "coffee-margaux", "person_key": MARGAUX["key"], "kind": "calendar", "attach": ""},
        {"promise_key": "deck-to-margaux", "person_key": MARGAUX["key"], "kind": "email", "attach": "deck"},
        {"promise_key": "intro-julien", "person_key": julien["key"], "kind": "email", "attach": ""},  # no edge
        {"promise_key": "numbers-to-owner", "person_key": MARGAUX["key"], "kind": "nudge", "attach": ""},
    ]
    llm = FakeSpark(GOOD)
    out = asyncio.run(Onepagers(tmp_path, llm, deck).for_moves("rec-1", record, moves, owner_name="Eric", owner_company="Hallwise"))
    assert list(out) == [MARGAUX["key"]] and out[MARGAUX["key"]]["promise_key"] == "deck-to-margaux"
    assert "Promised: the deck (due: tomorrow)" in llm.calls[0]["user"]


# --- ready: the event, the demo's cue, the routes -------------------------------------------------------------

MARGOT = {"key": "margot-lefebvre-corvane-capital", "name": "Margot Lefebvre", "company": "Corvane Capital"}
LIVE = {"people": [MARGOT, {"key": "julien-caron-corvane-capital", "name": "Julien Caron"}], "edges": [], "promises": []}


def test_the_rebuilt_event_says_who_what_and_where():
    assert rebuilt_event("rec-1", MARGAUX["key"], "Margaux Lefèvre", shape="one page, numbers first",
                         acts=["one page, numbers first"], slides=["Hallwise", "Why now"], title="Hallwise") == {
        "person_key": MARGAUX["key"], "name": "Margaux Lefèvre", "status": "ok", "title": "Hallwise",
        "shape": "one page, numbers first", "acts": ["one page, numbers first"], "slides": ["Hallwise", "Why now"],
        "format": "html", "url": f"/api/recordings/rec-1/onepager/{MARGAUX['key']}"}


def test_a_first_name_finds_the_person_as_the_transcriber_spelled_them():
    julien = LIVE["people"][1]
    assert find_person(LIVE, "Margaux") == MARGOT
    assert find_person(LIVE, "Julian") == julien
    assert find_person({"people": [julien]}, "Margaux") is None
    assert find_person({"people": [MARGOT, {**MARGOT, "key": "margot-b"}]}, "Margaux") is None  # two of them: ask
    assert find_person(LIVE, "") is None


def test_on_cue_a_page_made_beforehand_goes_in_for_that_person_and_stays(tmp_path):
    made = tmp_path / "made" / "one-pager.pdf"
    made.parent.mkdir()
    made.write_bytes(b"%PDF-1.7 the owner's own page")
    out = cue(tmp_path, "rec-1", LIVE, made, "Margaux", shape="one page, numbers first", slides=["", "", ""])
    assert out == {"person_key": MARGOT["key"], "name": "Margot Lefebvre", "status": "ok", "title": "",
                   "shape": "one page, numbers first", "acts": [], "slides": ["", "", ""], "format": "pdf",
                   "url": f"/api/recordings/rec-1/onepager/{MARGOT['key']}", "cued": True}
    kept = tmp_path / "onepagers" / "rec-1"
    assert (kept / f"{MARGOT['key']}.pdf").read_bytes() == made.read_bytes()
    # the morning's pass keeps the page she was shown: no call, nothing replaced
    deck = tmp_path / "deck.md"
    deck.write_text(DECK)
    llm = FakeSpark()
    record = {**LIVE, "edges": [{**EDGE, "person": MARGOT["key"]}]}
    again = asyncio.run(Onepagers(tmp_path, llm, deck).rebuild("rec-1", record, MARGOT["key"], {"key": "x", "what": "deck"}))
    assert again["cached"] is True and again["cued"] is True and llm.calls == []
    # cued again as HTML, the PDF goes: one page per person
    html_page = made.with_suffix(".html")
    html_page.write_text("<!doctype html><h1>Hallwise</h1>")
    assert cue(tmp_path, "rec-1", LIVE, html_page, "Margot")["format"] == "html"
    assert not (kept / f"{MARGOT['key']}.pdf").exists() and (kept / f"{MARGOT['key']}.html").exists()

    for bad, error in ((made.with_suffix(".txt"), ValueError), (made, LookupError)):
        bad.write_text("x")
        try:
            cue(tmp_path, "rec-1", {"people": []} if error is LookupError else LIVE, bad, "Margaux")
        except error:
            pass
        else:
            raise AssertionError(f"cued {bad.name}")


def routes(tmp_path, logged):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from hallwise.onepager import router

    def record_of(rid):
        if rid != "rec-1":
            raise HTTPException(404, "no such recording")
        return LIVE, [], {}

    def append(rid, type, **data):
        logged.append((rid, type, data))
        return {"type": type, "t_ms": 61_000, **data}

    app = FastAPI()
    app.include_router(router(tmp_path, record_of, append))
    return TestClient(app)


def test_the_cue_route_logs_rebuilt_and_the_page_route_serves_it(tmp_path, monkeypatch):
    logged = []
    client = routes(tmp_path, logged)
    monkeypatch.delenv("HALLWISE_ONEPAGER_CUE", raising=False)
    monkeypatch.delenv("HALLWISE_ONEPAGER_SLIDES", raising=False)
    assert client.post("/api/recordings/rec-1/onepager/cue", params={"name": "Margaux"}).status_code == 503

    made = tmp_path / "one-pager.html"
    made.write_text("<!doctype html><h1>Hallwise</h1>")
    deck = tmp_path / "deck.md"
    deck.write_text(DECK)
    monkeypatch.setenv("HALLWISE_ONEPAGER_CUE", str(made))
    monkeypatch.setenv("HALLWISE_DECK", str(deck))
    r = client.post("/api/recordings/rec-1/onepager/cue", params={"name": "Margaux"})
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "rebuilt" and r.json()["shape"] == "one page, numbers first"
    (rid, kind, data), = logged
    assert (rid, kind, data["person_key"], data["slides"]) == ("rec-1", "rebuilt", MARGOT["key"], slide_titles(DECK))

    page = client.get(data["url"])
    assert page.status_code == 200 and page.text == made.read_text()
    assert page.headers["content-type"].startswith("text/html")
    assert page.headers["content-security-policy"].startswith("default-src 'none'")

    monkeypatch.delenv("HALLWISE_DECK")
    monkeypatch.setenv("HALLWISE_ONEPAGER_SLIDES", "7")
    made_pdf = tmp_path / "one-pager.pdf"
    made_pdf.write_bytes(b"%PDF-1.7")
    monkeypatch.setenv("HALLWISE_ONEPAGER_CUE", str(made_pdf))
    assert client.post("/api/recordings/rec-1/onepager/cue", params={"name": "Margaux", "shape": "one page"}).json()[
        "slides"] == [""] * 7
    pdf = client.get(data["url"])
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content == b"%PDF-1.7"

    assert client.post("/api/recordings/rec-1/onepager/cue", params={"name": "Kenji"}).status_code == 404
    assert client.post("/api/recordings/rec-2/onepager/cue", params={"name": "Margaux"}).status_code == 404
    assert client.get("/api/recordings/rec-1/onepager/kenji").status_code == 404
    assert client.get("/api/recordings/rec-1/onepager/..%2f..%2fetc").status_code == 404

