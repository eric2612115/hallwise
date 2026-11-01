import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from hallwise.connector import (
    INTRO_SCHEMA, LOOK_SCHEMA, Connector, build_context, date_on_page, event, kept_events, kept_proposals, notice, quoted,
)
from hallwise.research import CorpusSearch, SearchClient

TAIPEI = timezone(timedelta(hours=8))
TONIGHT = datetime(2026, 10, 28, 20, 0, tzinfo=TAIPEI).timestamp()
CALL = "あ、エリックさんが来た。前に話した名札の人。うん、うちのロボットの現場ログに使えるかもしれない。"
CALL_EN = "Oh, Eric is here. The badge person from before. Yeah, it might be usable for our robots' field logs."
ARM = "Our frame line in Taoyuan is still all by hand. I'm looking for a small robot arm to pilot there."

KENJI, BEN, LENA = "kenji-watanabe-hoshizora-robotics", "ben-walker-stride-mobility", "lena-novak-brightline-grid"
SOFIA, HANA = "sofia-reyes-cobalt-health", "hana-sato-hoshizora-robotics"


def evening(root, rid, event, started, turns, people, promises=(), edges=(), translations=(), kinds=None, now=""):
    """A recording on disk in the shape the server logs it: turns (speaker, text), the people with their speaker keys."""
    d = root / "recordings" / rid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": rid, "event": event, "venue": "Taipei", "started": started, "owner_name": "Eric",
                                             "owner_company": "Hallwise", "tz": "Asia/Taipei", "now": now}))
    lines = [{"type": "owner", "t_ms": 0, "speakers": ["1:B"]}]
    for i, (speaker, text) in enumerate(turns, start=1):
        lines.append({"type": "turn", "t_ms": i * 1000, "turn": i, "speaker": speaker.split(":")[1], "session": 1, "text": text})
        lines.append({"type": "turn_kind", "t_ms": i * 1000, "turn": i, "kind": (kinds or {}).get(i, "conversation")})
    lines += [{"type": "person", "t_ms": 9000, "role": "", "introduced_by": "", "preferred_language": "", **p} for p in people]
    lines += [{"type": "promise", "t_ms": 9000, "due": "", "replaces": "", **q} for q in promises]
    lines += [{"type": "translation", "t_ms": 9000, **t} for t in translations]
    lines += [{"type": "edge", "t_ms": 9000, **e} for e in edges]
    (d / "events.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")


def week(root):
    """Oct 20: Eric promises Lena an introduction to Kenji. Oct 24: Ben wants a small robot arm for his frame line;
    Sofia wants a note-taker. Tonight: Kenji, on the phone in Japanese before greeting Eric, says the badge might work
    for his robots' field logs; Siddharth asks whether Eric knows Kenji; Hana is Kenji's colleague."""
    evening(root, "a-afterparty", "ETH Taipei afterparty", TONIGHT - 8 * 86400,
            [("1:C", "Hi, I'm Lena Novak, Brightline Grid. We do energy storage for data centres."),
             ("1:B", "I'll introduce you to Kenji on Monday."), ("1:D", "Kenji Watanabe, Hoshizora Robotics.")],
            [{"key": LENA, "name": "Lena Novak", "company": "Brightline Grid", "speakers": ["1:C"]},
             {"key": KENJI, "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:D"]}],
            promises=[{"key": "introduce-lena", "owed_by": "owner", "owed_to": LENA, "what": "introduce you to Kenji", "evidence_turns": [2]}])
    evening(root, "b-dinner", "Founder dinner", TONIGHT - 4 * 86400,
            [("1:E", "Ben Walker, Stride Mobility. E-bikes."), ("1:E", ARM), ("1:B", "Good luck with it."),
             ("1:C", "Sofia Reyes, Cobalt Health. We need a note-taker for clinic visits.")],
            [{"key": BEN, "name": "Ben Walker", "company": "Stride Mobility", "speakers": ["1:E"]},
             {"key": SOFIA, "name": "Sofia Reyes", "company": "Cobalt Health", "speakers": ["1:C"]}])
    evening(root, "c-tonight", "Living-room rehearsal", TONIGHT,
            [("1:G", CALL), ("1:H", "Siddharth Raghunathan, Quill Mesh. You know Kenji, no?"),
             ("1:G", "Kenji Watanabe, Hoshizora Robotics. We keep running into each other."),
             ("1:I", "Hana Sato, also Hoshizora. I run perception.")],
            [{"key": KENJI, "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:G"]},
             {"key": "siddharth-raghunathan-quill-mesh", "name": "Siddharth Raghunathan", "company": "Quill Mesh", "speakers": ["1:H"]},
             {"key": HANA, "name": "Hana Sato", "company": "Hoshizora Robotics", "speakers": ["1:I"]}],
            kinds={1: "ambient"},
            translations=[{"turn": 1, "language": "Japanese", "english": CALL_EN, "aside": True}],
            edges=[{"person": KENJI, "turns": [1], "language": "Japanese", "said": CALL, "english": CALL_EN,
                    "text": "Said on the phone, in Japanese, before greeting you: the badge might work for his robots' field logs.",
                    "act": "offer a field-log pilot"}],
            now="2026-10-28T20:30:00+08:00")


RESEARCH = [{"key": KENJI, "record_key": KENJI, "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "status": "matched",
             "findings": [{"kind": "company", "text": "Hoshizora Robotics builds compact robot arms for small factories.",
                           "source": "https://hoshizora-robotics.example/"},
                          {"kind": "recent", "text": "an unsourced claim", "source": ""}]}]


def line_id(ctx, part):
    return next(x.id for x in ctx.lines.values() if part in x.text)


def side(person, quote, evidence, wants="a need"):
    return {"person": person, "wants": wants, "quote": quote, "evidence": evidence}


def test_the_prompt_has_each_persons_own_words_and_who_is_already_connected(tmp_path):
    week(tmp_path)
    ctx = build_context(tmp_path, "c-tonight", RESEARCH)
    p = ctx.intro_prompt()
    call = line_id(ctx, "現場ログ")
    assert ctx.today == date(2026, 10, 28) and "(Wed 2026-10-28)" in p
    assert f"  {call} | tonight | not to the owner | Japanese: {CALL}  (English: {CALL_EN})" in p
    assert "    edge: Said on the phone, in Japanese, before greeting you" in p
    assert f"| Ben Walker, Stride Mobility | met: Founder dinner (Oct 24)" in p and ARM in p
    assert "I'll introduce you to Kenji" not in p and "Good luck with it." not in p  # the owner's words are nobody's need
    assert "R1 | public: Hoshizora Robotics builds compact robot arms" in p and "unsourced" not in p
    assert ctx.connected[frozenset((LENA, KENJI))].startswith("the owner promised to introduce them (ETH Taipei afterparty")
    assert ctx.connected[frozenset((KENJI, "siddharth-raghunathan-quill-mesh"))] == "Siddharth named Kenji (tonight)"
    assert ctx.connected[frozenset((KENJI, HANA))] == "the same company (Hoshizora Robotics)"
    assert frozenset((KENJI, BEN)) not in ctx.connected


def test_a_proposal_stands_only_on_each_persons_own_quoted_lines(tmp_path):
    week(tmp_path)
    ctx = build_context(tmp_path, "c-tonight", RESEARCH)
    call, arm, intro = line_id(ctx, "現場ログ"), line_id(ctx, "small robot arm"), line_id(ctx, "Ben Walker, Stride")
    clinic, lena = line_id(ctx, "note-taker"), line_id(ctx, "energy storage")
    good = {"a": side(KENJI, "うちのロボットの現場ログ", [call, "R1"], "builds compact arms and wants field logs from them"),
            "b": side(BEN, "looking for a small robot arm to pilot", [arm, intro]),
            "collaboration": "a pilot of a Hoshizora arm on Stride's frame line", "why": "w", "ask_first": BEN, "title": "Arm pilot"}
    raw = {"proposals": [
        {**good, "b": side(BEN, "looking for a small robot arm", [arm, "E99"])},  # a line that does not exist
        {**good, "b": side(BEN, "We need a note-taker for clinic visits", [clinic])},  # Sofia's line, cited for Ben
        {**good, "b": side(BEN, "we need a welding robot", [arm])},  # words the line does not have
        {**good, "b": side(BEN, "robot", [arm])},  # one word proves nothing
        {**good, "b": side(BEN, "looking for a small robot arm", [arm, "R1"])},  # Kenji's public finding, cited for Ben
        {**good, "b": side("julien-caron", "looking for a small robot arm", [arm])},  # nobody the owner met
        {**good, "b": side(LENA, "energy storage for data centres", [lena])},  # the introduction the owner already owes
        {**good, "b": side(HANA, "I run perception", [line_id(ctx, "I run perception")])},  # his colleague
        good,
        {**good, "a": side(KENJI, "might be usable for our robots' field logs", [call])},  # the same pair again, by the English
        {**good, "a": side(SOFIA, "We need a note-taker for clinic visits", [clinic]), "ask_first": "nobody"},  # met the same evening
    ]}
    kept, dropped = kept_proposals(raw, ctx)
    assert [d["reason"] for d in dropped] == [
        "E99 is not a line", f"{clinic} is not Ben Walker's own line",
        f"Ben Walker's lines {arm} do not say “we need a welding robot”", f"Ben Walker's lines {arm} do not say “robot”",
        "a public finding cited for Ben Walker is someone else's", "julien-caron is not someone the owner met",
        "already connected: the owner promised to introduce them (ETH Taipei afterparty (Oct 20))",
        "already connected: the same company (Hoshizora Robotics)", "the same pair twice",
    ]
    assert [[s["key"] for s in k["people"]] for k in kept] == [[KENJI, BEN], [SOFIA, BEN]]  # different evenings first
    k, s = kept[0], kept[0]["people"][0]
    assert k["rank"] == 1 and not k["same_evening"] and kept[1]["same_evening"] and kept[1]["ask_first"] == SOFIA
    assert s["evidence"][0]["quote"] == CALL and s["evidence"][0]["english"] == CALL_EN  # from the log, not the model
    assert s["aside"] is True and s["evidence"][0]["edge"]["act"] == "offer a field-log pilot"
    assert s["public"] == [{"id": "R1", "kind": "company", "text": RESEARCH[0]["findings"][0]["text"], "source": "https://hoshizora-robotics.example/"}]
    assert k["people"][1]["aside"] is False and [e["recording"] for e in k["people"][1]["evidence"]] == ["b-dinner", "b-dinner"]

    # Whoever said something tonight comes first, however the model ordered them.
    swapped, _ = kept_proposals({"proposals": [{**good, "a": good["b"], "b": good["a"]}]}, ctx)
    assert [s["key"] for s in swapped[0]["people"]] == [KENJI, BEN] and swapped[0]["ask_first"] == BEN

    # At most three.
    four = [good, {**good, "a": side(SOFIA, "a note-taker for clinic visits", [clinic])},
            {**good, "b": side(SOFIA, "a note-taker for clinic visits", [clinic])},
            {**good, "a": side(LENA, "energy storage for data centres", [lena])}]
    kept, dropped = kept_proposals({"proposals": four}, ctx)
    assert [x["rank"] for x in kept] == [1, 2, 3] and dropped == [{"title": "Arm pilot", "reason": "over three"}]


def test_quotes_are_held_word_for_word():
    assert quoted("robot arm to pilot", [ARM]) and quoted("ROBOT ARM, to pilot!", [ARM])
    assert not quoted("robot arms to pilot", [ARM]) and not quoted("arm", [ARM]) and not quoted("", [ARM])
    assert quoted("現場ログ", [CALL]) and quoted("ロボットの 現場ログ", [CALL])
    assert not quoted("ログ", [CALL]) and not quoted("工場ログ", [CALL])


PAGE = {"url": "https://nangang-hardware.example/meetups/2026-11-05",
        "title": "Nangang Hardware Meetup #19 (Thursday, November 5, 2026)",
        "snippet": "Thursday, November 5, 2026, 19:00, Nangang, Taipei. Ben Walker of Stride Mobility talks about the first robot arm on his line."}
OTHER = {"url": "https://hoshizora-robotics.example/", "title": "Hoshizora Robotics", "snippet": "Compact robot arms."}


def test_an_event_stands_only_on_a_page_the_search_returned(tmp_path):
    week(tmp_path)
    ctx = build_context(tmp_path, "c-tonight")
    arm = line_id(ctx, "small robot arm")
    good = {"title": "Nangang Hardware Meetup #19", "date": "2026-11-05", "time": "19:00", "place": "Nangang", "url": PAGE["url"],
            "who": "Ben Walker", "role": "speaks", "for_people": [BEN], "evidence": [arm], "quote": "a small robot arm to pilot there",
            "bring": [KENJI, BEN], "why": "Ben wants an arm; bring Kenji."}
    answer = {"events": [
        {**good, "url": "https://nangang-hardware.example/meetups/2026-11-05-made-up"},  # not a result
        {**good, "date": "2026-11-20"},  # past the fourteen days
        {**good, "date": "2026-10-20"},  # gone
        {**good, "date": "2026-11-06"},  # in the window, not on the page
        {**good, "who": "Priya Menon"},  # not on the page
        {**good, "quote": "a welding robot"},  # not what Ben said
        {**good, "for_people": [KENJI], "quote": "現場ログ"},  # Kenji's need, cited by Ben's line
        {**good, "bring": [BEN, "nobody-at-all"]},  # only the speaker himself
        good,
    ]}
    kept, dropped = kept_events(answer, [PAGE, OTHER], [], ctx)
    assert [d["reason"] for d in dropped] == [
        "not a page the search returned", "not in the next 14 days", "not in the next 14 days", "the date is not on the page",
        "the person is not named on the page", "no line of theirs says the need it serves",
        "no line of theirs says the need it serves", "nobody to bring along",
    ]
    (e,) = kept
    assert (e["url"], e["site"], e["date"], e["weekday"], e["who_key"]) == (PAGE["url"], "nangang-hardware.example", "2026-11-05", "Thu", BEN)
    assert [b["key"] for b in e["bring"]] == [KENJI] and [f["key"] for f in e["for"]] == [BEN]  # never the speaker himself
    assert e["evidence"][0]["quote"] == ARM
    # A site named alone resolves to the result on that site; a citation off the results never counts.
    site, _ = kept_events({"events": [{**good, "url": "nangang-hardware.example"}]}, [PAGE, OTHER], [], ctx)
    assert site[0]["url"] == PAGE["url"]
    assert kept_events({"events": [good]}, [OTHER], [PAGE["url"]], ctx)[1][0]["reason"] == "the date is not on the page"


def test_dates_on_a_page():
    d = date(2026, 11, 5)
    for text in ("Thursday, November 5, 2026", "on 5 November", "Nov 5, 19:00", "2026-11-05", "11/5/2026", "11月5日（木）"):
        assert date_on_page(d, text), text
    assert not date_on_page(d, "November 15, 2026") and not date_on_page(d, "2026-11-50") and not date_on_page(d, "Nov 6")


def test_off_unless_switched_on(tmp_path, monkeypatch):
    week(tmp_path)
    monkeypatch.setenv("MODEL_API_KEY", "x")
    monkeypatch.delenv("HALLWISE_CONNECTOR", raising=False)
    off = Connector.from_env(tmp_path)
    assert not off.enabled and off.off_reason == "HALLWISE_CONNECTOR is not on"
    out = asyncio.run(off.run("c-tonight"))
    assert out["status"] == "off" and out["introductions"] == [] and not (tmp_path / "connector").exists()
    for value in ("1", "true", "off"):
        monkeypatch.setenv("HALLWISE_CONNECTOR", value)
        assert not Connector.from_env(tmp_path).enabled

    monkeypatch.setenv("HALLWISE_CONNECTOR", "on")
    monkeypatch.delenv("MODEL_API_KEY")
    assert Connector.from_env(tmp_path).off_reason == "MODEL_API_KEY is not set"
    monkeypatch.setenv("MODEL_API_KEY", "x")
    on = Connector.from_env(tmp_path)
    assert on.enabled and type(on.search) is SearchClient  # the web by default
    corpus = tmp_path / "web.json"
    corpus.write_text(json.dumps({"pages": [{"url": PAGE["url"], "title": PAGE["title"], "text": PAGE["snippet"]}]}))
    monkeypatch.setenv("HALLWISE_RESEARCH_CORPUS", str(corpus))
    assert isinstance(Connector.from_env(tmp_path).search, CorpusSearch)
    monkeypatch.setenv("HALLWISE_RESEARCH_CORPUS", str(tmp_path / "missing.json"))
    bad = Connector.from_env(tmp_path)
    assert bad.enabled and bad.search is None and "HALLWISE_RESEARCH_CORPUS unreadable" in bad.notes[0]  # never the web instead
    monkeypatch.setenv("HALLWISE_CONNECTOR_LOOKAHEAD", "off")
    assert Connector.from_env(tmp_path).search is None


class FakeSpark:
    """Muse Spark as SparkClient answers: the JSON, and the usage of the last call."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.last_usage = {}

    async def __call__(self, system, user, schema=None, name=""):
        self.calls.append((system, user, schema, name))
        self.last_usage = {"prompt_tokens": 4000, "completion_tokens": 900, "completion_tokens_details": {"reasoning_tokens": 700}}
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def corpus_search(sent, answer):
    """research.py's corpus client over a mock transport: the look-ahead's call, as the Responses API answers it."""
    reply = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}],
             "usage": {"input_tokens": 5000, "output_tokens": 1200, "total_tokens": 6200}}

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=reply)
    pages = [{"url": PAGE["url"], "title": PAGE["title"], "text": PAGE["snippet"]},
             {"url": OTHER["url"], "title": OTHER["title"], "text": OTHER["snippet"]}]
    return CorpusSearch("k", pages, transport=httpx.MockTransport(handler))


def test_a_run_logs_its_tokens_keeps_its_result_and_says_it_when_the_owner_sits_down(tmp_path):
    week(tmp_path)
    ctx = build_context(tmp_path, "c-tonight", RESEARCH)
    call, arm = line_id(ctx, "現場ログ"), line_id(ctx, "small robot arm")
    llm = FakeSpark({"proposals": [{
        "a": side(KENJI, "うちのロボットの現場ログ", [call, "R1"], "builds compact arms and wants field logs from them"),
        "b": side(BEN, "looking for a small robot arm to pilot", [arm]),
        "collaboration": "a pilot of a Hoshizora arm on Stride's frame line", "why": "w", "ask_first": BEN, "title": "Arm pilot"}]})
    sent = []
    search = corpus_search(sent, {"events": [{
        "title": "Nangang Hardware Meetup #19", "date": "2026-11-05", "time": "19:00", "place": "Nangang", "url": PAGE["url"],
        "who": "Ben Walker", "role": "speaks", "for_people": [BEN], "evidence": [arm], "quote": "small robot arm to pilot",
        "bring": [KENJI], "why": "Ben wants an arm; bring Kenji."}]})
    connector = Connector(tmp_path, llm, search, model="muse-spark-1.3", clock=lambda: 1_800_000_000.0)
    out = asyncio.run(connector.run("c-tonight", research=RESEARCH))

    system, user, schema, name = llm.calls[0]
    assert schema is INTRO_SCHEMA and name == "hallwise_connector" and user == ctx.intro_prompt()
    body = sent[0]
    assert "tools" not in body and body["text"]["format"]["schema"] == LOOK_SCHEMA  # the pages, not the web
    assert "Window: Wed 2026-10-28 to Wed 2026-11-11 (the next 14 days), in or near Taipei" in body["input"]
    assert f"1. {KENJI} (Kenji Watanabe, Hoshizora Robotics): builds compact arms" in body["input"]
    assert [[p["name"] for p in x["people"]] for x in out["introductions"]] == [["Kenji Watanabe", "Ben Walker"]]
    assert [e["who"] for e in out["lookahead"]["events"]] == ["Ben Walker"] and out["lookahead"]["corpus"] is True
    assert out["usage"]["introductions"] == {"calls": 1, "prompt_tokens": 4000, "completion_tokens": 900, "reasoning_tokens": 700,
                                             "seconds": out["usage"]["introductions"]["seconds"]}
    assert out["usage"]["lookahead"]["input_tokens"] == 5000 and out["usage"]["lookahead"]["searches"] == 0  # nothing searched
    assert out["usage"]["tokens"] == 4000 + 900 + 5000 + 1200 and out["usage"]["usd"] == round(9000 * 1.25e-6 + 2100 * 4.25e-6, 4)
    assert out["cached"] is False and json.loads((tmp_path / "connector" / "c-tonight.json").read_text())["model"] == "muse-spark-1.3"

    logged = event(out)
    assert (logged["introductions"], logged["events"], logged["corpus"]) == (1, 1, True)
    assert "現場" not in json.dumps(logged, ensure_ascii=False) and "robot arm" not in json.dumps(logged)  # no one's words in the log
    assert notice(out) == {"title": "Kenji and Ben should meet",
                           "body": "a pilot of a Hoshizora arm on Stride's frame line · Thu 11-05: Ben Walker at Nangang Hardware Meetup #19"}

    again = asyncio.run(connector.run("c-tonight"))
    assert again["cached"] is True and len(llm.calls) == 1 and len(sent) == 1  # kept: asked once
    asyncio.run(connector.run("c-tonight", force=True))
    assert len(llm.calls) == 2 and len(sent) == 2


def test_a_failed_call_leaves_the_other_part(tmp_path):
    week(tmp_path)
    sent = []
    out = asyncio.run(Connector(tmp_path, FakeSpark(RuntimeError("down")), corpus_search(sent, {"events": []})).run("c-tonight"))
    assert out["introductions"] == [] and out["notes"] == ["introductions failed (RuntimeError)"] and len(sent) == 1
    assert "Introductions proposed tonight (their needs first):\n- none" in sent[0]["input"]


def test_the_demo_corpus_has_one_upcoming_event_and_it_is_invented():
    pages = CorpusSearch.load("k", Path(__file__).parents[2] / "demo" / "rig" / "fictional-web.json").pages
    window = [date(2026, 10, 28) + timedelta(days=i) for i in range(15)]
    upcoming = [p for p in pages if any(date_on_page(d, p["title"] + " " + p["text"]) for d in window)]
    assert len(upcoming) == 1
    (page,) = upcoming
    assert httpx.URL(page["url"]).host.endswith(".example") and "Ben Walker" in page["text"]
    assert not any(name in page["title"] + page["text"] for name in ("Corvane", "Margaux", "Julien"))
