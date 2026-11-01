import asyncio
import copy
import json

import numpy as np
from fastapi.testclient import TestClient
from auth import AUTH

from hallwise.app import create_app
from hallwise.extract import SCHEMA, SYSTEM, Extractor, Turn, build_prompt

SARAH = {
    "key": "sarah-acme",
    "name": "Sarah",
    "company": "Acme",
    "role": "",
    "speakers": ["1:A"],
    "preferred_language": "",
    "introduced_by": "",
    "evidence_turns": [0],
}
COFFEE_THURSDAY = {
    "key": "coffee-with-sarah",
    "owed_by": "owner",
    "owed_to": "sarah-acme",
    "what": "coffee",
    "due": "Thursday",
    "replaces": "",
    "evidence_turns": [2],
}


def state(**overrides):
    base = {
        "owner_speakers": [],
        "turns": [],
        "people": [],
        "mentioned": [],
        "promises": [],
        "suspect_words": [],
        "translations": [],
        "room_topics": [],
    }
    return {**base, **overrides}


class ScriptedLLM:
    def __init__(self, *results):
        self.results = list(results)
        self.prompts: list[str] = []

    async def __call__(self, system, user):
        self.prompts.append(user)
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def test_schema_requires_every_field_it_declares():
    def check(node):
        if node.get("type") == "object":
            assert sorted(node["required"]) == sorted(node["properties"])
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])

    check(SCHEMA)


def test_prompt_lists_owner_vocabulary_and_numbered_turns():
    prompt = build_prompt(
        [Turn(3, "1:B", 65_700, 69_660, "I'm Eric, from Vexi.")], "Eric", "Vexi", ["Vexi", "Raghunathan"]
    )
    assert "Owner: Eric, from Vexi" in prompt
    assert "Vexi, Raghunathan" in prompt
    assert "turn 3 [1:B] 1:05.7-1:09.6: I'm Eric, from Vexi." in prompt
    assert "(owner)" not in prompt and "Owner's voice" not in prompt  # no wearer found: as it always was


def test_prompt_marks_the_wearer_as_the_owner():
    turns = [Turn(0, "1:A", 17_340, 22_220, "Hey, Eric. I'm Ken from Vexy."),
             Turn(1, "1:B", 22_300, 25_000, "I'll send you the deck tonight.")]
    prompt = build_prompt(turns, "Eric", "Hallwise", [], wearer="1:B")
    assert "Owner's voice: speaker 1:B" in prompt
    assert "turn 1 [1:B, Eric (owner)] 0:22.3-0:25.0: I'll send you the deck tonight." in prompt
    assert "turn 0 [1:A] 0:17.3-0:22.2: Hey, Eric." in prompt  # the guest is not marked
    assert "[1:B, the owner (owner)]" in build_prompt(turns, "", "", [], wearer="1:B")


def test_a_wearer_joins_sparks_owner_and_is_not_announced_twice():
    llm = ScriptedLLM(state(owner_speakers=["1:C"]), state(owner_speakers=[]))
    extractor = Extractor(llm, "Eric", "Hallwise")
    assert extractor.set_wearer("1:B") == ["1:B"]
    assert extractor.state["owner_speakers"] == ["1:B"]  # at once, for the fast "met before" path
    extractor.add_turn(Turn(0, "1:B", 0, 1000, "I'll send you the deck."))
    first = asyncio.run(extractor.run())
    assert "turn 0 [1:B, Eric (owner)]" in llm.prompts[-1]
    assert [e for e in first if e[0] == "owner"] == [("owner", 1000, {"speakers": ["1:B", "1:C"]})]
    extractor.add_turn(Turn(1, "1:A", 1000, 2000, "Thanks."))
    second = asyncio.run(extractor.run())  # Spark drops 1:C; the wearer stays
    assert [e for e in second if e[0] == "owner"] == [("owner", 2000, {"speakers": ["1:B"]})]
    assert extractor.set_wearer("") == []  # withdrawn: only what Spark itself listed (nothing, by now) is left
    extractor.add_turn(Turn(2, "1:B", 2000, 3000, "Bye."))
    asyncio.run(extractor.run())
    assert "(owner)" not in llm.prompts[-1]


def test_diff_emits_only_what_is_new_or_changed():
    friday = {**COFFEE_THURSDAY, "due": "Friday", "replaces": "Thursday", "evidence_turns": [2, 3]}
    llm = ScriptedLLM(
        state(
            owner_speakers=["1:B"],
            turns=[{"turn": 0, "kind": "conversation"}, {"turn": 2, "kind": "conversation"}],
            people=[SARAH],
            promises=[COFFEE_THURSDAY],
            suspect_words=[{"heard": "Vexy", "turn": 1, "likely": "Vexi", "reason": "owner's company"}],
        ),
        state(
            owner_speakers=["1:B"],
            turns=[
                {"turn": 0, "kind": "conversation"},
                {"turn": 2, "kind": "conversation"},
                {"turn": 3, "kind": "conversation"},
                {"turn": 4, "kind": "ambient"},
            ],
            people=[SARAH],
            promises=[friday],
            suspect_words=[],  # confirmed since the last run
            room_topics=["restaking yields"],
        ),
    )
    extractor = Extractor(llm, "Eric", "Vexi")
    extractor.add_turn(Turn(0, "1:A", 500, 5400, "Hi, I'm Sarah from Acme."))
    first = asyncio.run(extractor.run())
    assert [e[0] for e in first] == ["owner", "turn_kind", "turn_kind", "person", "promise", "suspect_word"]
    assert first[3][2]["new"] is True

    extractor.add_turn(Turn(3, "1:A", 9_900, 13_700, "Thursday, no, Friday."))
    second = asyncio.run(extractor.run())
    assert [(e[0], e[1]) for e in second] == [
        ("turn_kind", 13_700),
        ("turn_kind", 13_700),
        ("promise", 13_700),
        ("suspect_word_removed", 13_700),
        ("room_topics", 13_700),
    ]
    promise = second[2][2]
    assert (promise["due"], promise["replaces"], promise["new"]) == ("Friday", "Thursday", False)
    assert second[3][2] == {"heard": "Vexy", "turn": 1}
    assert second[4][2] == {"topics": ["restaking yields"]}


def test_recording_reruns_extraction_until_every_turn_is_seen(tmp_path):
    llm = ScriptedLLM(state(people=[SARAH]))

    def make_extractor(hello):
        return Extractor(llm, hello.owner_name, hello.owner_company, hello.keywords or [])

    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=make_extractor), headers=AUTH)
    script = [
        {"start_ms": 100, "end_ms": 600, "speaker": "A", "text": "Hi, I'm Sarah from Acme."},
        {"start_ms": 700, "end_ms": 1200, "speaker": "B", "text": "I'm Eric, from Vexi."},
        {"start_ms": 1300, "end_ms": 1900, "speaker": "A", "text": "Coffee on Friday?"},
    ]
    with client.websocket_connect("/ingest") as ws:
        hello = {
            "sample_rate": 24_000,
            "channels": 1,
            "layout": "mono",
            "owner_name": "Eric",
            "owner_company": "Vexi",
            "fake_script": script,
        }
        ws.send_text(json.dumps(hello))
        recording = ws.receive_json()["recording"]
        ws.send_bytes(np.zeros(48_000, dtype=np.int16).tobytes())
        ws.send_text(json.dumps({"type": "end"}))
        ws.receive_json()

    events = client.get(f"/api/recordings/{recording}/events").json()
    assert [e["key"] for e in events if e["type"] == "person"] == ["sarah-acme"]
    assert "Coffee on Friday?" in llm.prompts[-1]  # the last run saw the last turn
    assert "Owner: Eric, from Vexi" in llm.prompts[0]
    assert events[-1]["type"] == "recording_end"


def test_fold_record_keeps_latest_and_drops_removed():
    from hallwise.events import fold_record

    events = [
        {"type": "turn", "t_ms": 1000, "turn": 1, "speaker": "1:A", "text": "I'm Sarah from Acme"},
        {"type": "owner", "t_ms": 1000, "speakers": ["1:B"]},
        {"type": "person", "t_ms": 1000, "key": "sarah-acme", "name": "Sara", "company": "Acme"},
        {"type": "person", "t_ms": 2000, "key": "sarah-acme", "name": "Sarah", "company": "Acme"},
        {"type": "promise", "t_ms": 2000, "key": "deck-to-sarah-acme", "owed_by": "owner", "owed_to": "sarah-acme", "what": "send the deck"},
        {"type": "promise", "t_ms": 2000, "key": "gone", "owed_by": "owner", "owed_to": "sarah-acme", "what": "x"},
        {"type": "promise_removed", "t_ms": 3000, "key": "gone"},
        {"type": "translation", "t_ms": 3000, "turn": 1, "language": "French", "english": "hello"},
    ]
    r = fold_record(events)
    assert [p["name"] for p in r["people"]] == ["Sarah"]
    assert [q["key"] for q in r["promises"]] == ["deck-to-sarah-acme"]
    assert r["owner_speakers"] == ["1:B"]
    assert r["translations"][1]["english"] == "hello"
    assert len(r["turns"]) == 1


def test_next_moves_normalises_keys_and_limits_attachments():
    from hallwise.extract import NEXT_SCHEMA, draft_next_moves

    seen = {}

    async def llm(system, user, schema=None, name=""):
        seen["schema"] = schema
        seen["user"] = user
        return {"moves": [
            {"promise_key": "Deck to Sarah-Acme", "person_key": "Sarah-Acme", "kind": "email", "language": "English",
             "subject": "The deck", "body": "Here it is. Eric", "body_english": "", "when": "", "duration_minutes": 0,
             "attach": "one_pager", "why": "promised"},
            {"promise_key": "not-a-promise", "person_key": "x", "kind": "message", "language": "English", "subject": "",
             "body": "?", "body_english": "", "when": "", "duration_minutes": 30, "attach": "", "why": ""},
        ]}

    record = {
        "people": [{"key": "sarah-acme", "name": "Sarah", "company": "Acme", "preferred_language": ""}],
        "promises": [{"key": "deck-to-sarah-acme", "owed_by": "owner", "owed_to": "sarah-acme", "what": "send the deck", "evidence_turns": [1]}],
        "turns": [{"turn": 1, "speaker": "1:A", "text": "send me the deck"}],
        "turn_kinds": {}, "translations": {},
    }
    moves = asyncio.run(draft_next_moves(
        llm, record, owner_name="Eric", owner_company="Hallwise", now="2026-10-27T14:00:00+08:00", tz="Asia/Taipei",
        busy=[["2026-10-28T10:00:00+08:00", "2026-10-28T11:00:00+08:00"]], links={"deck": "https://x/deck"},
    ))
    assert seen["schema"] is NEXT_SCHEMA
    assert "Owner busy (ISO ranges): 2026-10-28T10:00:00+08:00 to 2026-10-28T11:00:00+08:00" in seen["user"]
    assert "Owner can share: deck" in seen["user"]
    assert [m["promise_key"] for m in moves] == ["deck-to-sarah-acme"]
    assert moves[0]["attach"] == ""  # one_pager is not something the owner has
    assert moves[0]["duration_minutes"] == 30


def _history(key: str, name: str, *events: tuple[str, float]) -> dict:
    return {"type": "person_history", "key": key, "name": name, "company": "",
            "encounters": [{"event": e, "started": t} for e, t in events], "promises": []}


def test_next_prompt_gives_each_person_only_their_own_earlier_meetings():
    from hallwise.extract import NEXT_SYSTEM, build_next_prompt

    oct20, oct22, oct23 = 1792499400.0, 1792668600.0, 1792756800.0
    record = {
        "people": [
            {"key": "siddharth-raghunathan-quill-mesh", "name": "Siddharth Raghunathan", "company": "Quill Mesh"},
            {"key": "kenji-watanabe-hoshizora-robotics", "name": "Kenji Watanabe", "company": "Hoshizora Robotics"},
            {"key": "margaux-lefevre-corvane-capital", "name": "Margaux Lefèvre", "company": "Corvane Capital"},
        ],
        "promises": [{"key": "coffee-to-kenji", "owed_by": "owner", "owed_to": "kenji-watanabe-hoshizora-robotics",
                      "what": "coffee", "due": "Friday", "evidence_turns": [25]}],
        "turns": [
            {"turn": 23, "speaker": "1:F", "text": "Eric! Siddharth Raghunathan, Quill Mesh, we met at Blockchain Week. You know Kenji."},
            {"turn": 24, "speaker": "1:G", "text": "Kenji Watanabe, Hoshizora Robotics. We keep running into each other."},
        ],
        "turn_kinds": {}, "translations": {},
        "history": {
            "siddharth-raghunathan-quill-mesh": _history("siddharth-raghunathan-quill-mesh", "Siddharth Raghunathan",
                                                         ("Blockchain Week side event", oct23), ("ETH Taipei afterparty", oct20)),
            "kenji-watanabe-hoshizora-robotics": _history("kenji-watanabe-hoshizora-robotics", "Kenji Watanabe",
                                                          ("Hardware meetup", oct22), ("ETH Taipei afterparty", oct20)),
        },
    }
    prompt = build_next_prompt(record, owner_name="Eric", owner_company="Hallwise", now="2026-10-27T06:40:36+08:00")
    people = {line.split(" | ")[0][2:]: line for line in prompt.splitlines() if line.startswith("- ") and " | met before: " in line}
    kenji = people["kenji-watanabe-hoshizora-robotics"]
    assert "met before: Hardware meetup" in kenji and "ETH Taipei afterparty" in kenji
    assert "Blockchain" not in kenji  # Siddharth's evening, and Siddharth's words, are not Kenji's
    assert "met before: Blockchain Week side event" in people["siddharth-raghunathan-quill-mesh"]
    assert people["margaux-lefevre-corvane-capital"].endswith("met before: none")
    assert "- kenji-watanabe-hoshizora-robotics (Kenji Watanabe): Hardware meetup" in prompt
    # The rule the drafts follow: that same person's own lines, never someone else's, none when none.
    rule = " ".join(NEXT_SYSTEM.split())
    assert "mention one only when it is listed for that same person" in rule
    assert "Never borrow another person's earlier meetings" in rule
    assert "never take one from what someone else said in the transcript" in rule
    assert '"met before: none" gets no mention of any earlier meeting' in rule


def test_next_prompt_spells_out_the_days_ahead_and_where_next_week_starts():
    from hallwise.extract import NEXT_SYSTEM, build_next_prompt

    record = {"people": [], "promises": [], "turns": [], "turn_kinds": {}, "translations": {}}
    prompt = build_next_prompt(record, owner_name="Eric", owner_company="", now="2026-10-27T06:40:36+08:00", tz="Asia/Taipei")
    (days,) = [line for line in prompt.splitlines() if line.startswith("Days ahead: ")]
    assert days.startswith("Days ahead: Tue 2026-10-27 (today), Wed 2026-10-28,")
    assert "Fri 2026-10-30," in days and "Mon 2026-11-02 (next week starts)" in days and "Wed 2026-11-04" in days
    assert '"next week, Wednesday" is the Wednesday of that week' in " ".join(NEXT_SYSTEM.split())
    assert not [line for line in build_next_prompt(record, owner_name="", owner_company="").splitlines() if line.startswith("Days")]


def test_drafts_never_describe_what_an_attachment_contains():
    """Leo's draft said the deck "includes the face-photo flow"; nobody said so. The rule against it, in the words
    the model reads."""
    from hallwise.extract import NEXT_SYSTEM

    rule = " ".join(NEXT_SYSTEM.split())
    assert "say what is attached or shown, never what it contains" in rule
    assert ("Do not describe the contents of a deck, one-pager, link, demo or product, or what it \"includes\", "
            "\"covers\" or \"shows\", beyond what was said in the transcript") in rule
    assert '"the deck includes the face-photo flow" when nobody said so is an invented fact' in rule


def test_a_provisional_met_before_never_reaches_the_drafts():
    from hallwise.events import fold_record
    from hallwise.extract import build_next_prompt

    sid = {"key": "sid", "name": "Siddharth Raghunathan", "company": "Quill Mesh",
           "encounters": [{"event": "Blockchain Week side event", "started": 1792756800.0}], "promises": []}
    events = [
        {"type": "person", "t_ms": 1, "key": "sid", "name": "Siddharth Raghunathan", "company": "Quill Mesh"},
        {"type": "person_history", "t_ms": 1, **sid, "speaker": "1:F", "provisional": True},
        {"type": "hook", "t_ms": 1, "person_key": "sid", "title": "Tomás's friend · Oct 23", "provisional": True},
    ]
    record = fold_record(events)
    assert "Blockchain Week" not in build_next_prompt(record, owner_name="Eric", owner_company="Hallwise")
    withdrawn = fold_record(events + [
        {"type": "person_history_removed", "t_ms": 2, "key": "sid", "speaker": "1:F", "reason": "not confirmed"},
        {"type": "hook_removed", "t_ms": 2, "person_key": "sid", "title": "Tomás's friend · Oct 23"},
    ])
    assert withdrawn["history"] == {} and withdrawn["hooks"] == {"sid": []}
    confirmed = fold_record(events + [{"type": "person_history", "t_ms": 3, **sid}])
    assert "met before: Blockchain Week side event" in build_next_prompt(confirmed, owner_name="Eric", owner_company="")


# Margaux spoke English to the owner all evening; to herself, before anyone had a name, she said "avec des chiffres".
MARGAUX = {**SARAH, "key": "margaux-lefevre-corvane-capital", "name": "Margaux Lefèvre", "company": "Corvane Capital",
           "speakers": ["1:D"], "preferred_language": "French", "evidence_turns": [10]}
SOFA = [
    Turn(5, "1:D", 44_000, 50_000, "Honestly, the deck yesterday? I did not understand their model at all."),
    Turn(6, "1:E", 50_000, 55_000, "Same, 20 slides and zero numbers. Zero."),
    Turn(7, "1:D", 55_000, 62_000, "20 slides! Avec des chiffres."),
    Turn(10, "1:D", 74_000, 80_000, "Oh, of course. Margaux Lefèvre, Corvane Capital."),
    Turn(13, "1:D", 93_000, 100_000, "Pre-seed, yes. Send me your one-pager? One page, with numbers. Please."),
]
ASIDE = {"turn": 7, "language": "French", "english": "Twenty slides! With numbers.", "aside": True}
EDGE = {"person": "Margaux Lefevre-Corvane Capital", "turns": [5, 7], "language": "French", "said": "Avec des chiffres",
        "english": "With numbers",
        "text": "Said to herself, in French: 'with numbers'. Yesterday's founder lost her with twenty slides and no numbers.",
        "act": "one page, numbers first"}


def run_sofa(*results):
    """Each result as fresh JSON, as Spark sends it: the run normalises and checks it in place."""
    extractor = Extractor(ScriptedLLM(*copy.deepcopy(results)), "Eric", "Hallwise")
    for t in SOFA:
        extractor.add_turn(t)
    return asyncio.run(extractor.run())


def test_an_aside_never_sets_the_language_and_becomes_an_edge():
    out = run_sofa(state(people=[MARGAUX], translations=[ASIDE], edges=[EDGE]))
    (person,) = [d for kind, _, d in out if kind == "person"]
    assert person["preferred_language"] == ""  # she spoke English with the owner; the aside does not count
    (edge,) = [d for kind, _, d in out if kind == "edge"]
    assert edge["person"] == "margaux-lefevre-corvane-capital" and edge["turns"] == [5, 7] and edge["new"] is True
    assert edge["act"] == "one page, numbers first"
    rules = " ".join(SYSTEM.split())
    assert "An aside never sets it" in rules and "said is their own words copied from one turn exactly as the transcript has them" in rules
    assert SCHEMA["properties"]["translations"]["items"]["properties"]["aside"]["type"] == "boolean"


def test_a_language_spoken_to_the_owner_or_asked_for_stays():
    spoken = {**ASIDE, "turn": 13, "aside": False}  # her follow-up request, in French, to the owner
    out = run_sofa(state(people=[MARGAUX], translations=[ASIDE, spoken]))
    assert [d["preferred_language"] for kind, _, d in out if kind == "person"] == ["French"]

    extractor = Extractor(ScriptedLLM(copy.deepcopy(state(people=[MARGAUX]))), "Eric", "Hallwise")
    extractor.add_turn(Turn(10, "1:D", 0, 1000, "Margaux Lefèvre. Write to me in French, please."))
    assert [d["preferred_language"] for kind, _, d in asyncio.run(extractor.run()) if kind == "person"] == ["French"]

    # never heard from her at all (a guess from an accent, say): English
    out = run_sofa(state(people=[{**MARGAUX, "preferred_language": "Japanese"}], translations=[ASIDE]))
    assert [d["preferred_language"] for kind, _, d in out if kind == "person"] == [""]


def test_an_edge_rests_on_the_persons_own_heard_words():
    out = run_sofa(state(people=[MARGAUX], translations=[ASIDE], edges=[
        EDGE,
        {**EDGE, "turns": [7], "said": "Une page, avec des chiffres"},  # "une page" was never heard
        {**EDGE, "turns": [6], "said": "zero numbers"},  # Julien's words, not hers
        {**EDGE, "person": "julien-caron", "turns": [6], "said": "zero numbers"},  # nobody the owner met
    ]))
    assert [(d["person"], d["said"]) for kind, _, d in out if kind == "edge"] == [
        ("margaux-lefevre-corvane-capital", "Avec des chiffres")]


def test_edges_follow_the_record_and_withdraw():
    from hallwise.events import fold_record

    extractor = Extractor(ScriptedLLM(*copy.deepcopy((state(people=[MARGAUX], edges=[EDGE]), state(people=[MARGAUX])))), "Eric", "Hallwise")
    for t in SOFA:
        extractor.add_turn(t)
    first = asyncio.run(extractor.run())
    second = asyncio.run(extractor.run())
    assert [(k, d) for k, _, d in second if k.startswith("edge")] == [
        ("edge_removed", {"person": "margaux-lefevre-corvane-capital", "turns": [5, 7]})]
    events = [{"type": k, "t_ms": t, **d} for k, t, d in first]
    assert [e["said"] for e in fold_record(events)["edges"]] == ["Avec des chiffres"]
    assert fold_record(events + [{"type": k, "t_ms": t, **d} for k, t, d in second])["edges"] == []
    gone = [e for e in events if e["type"] != "person"]  # an edge of someone no longer listed is not in the record
    assert fold_record(gone)["edges"] == []


def test_drafts_act_on_an_edge_and_never_quote_it():
    from hallwise.extract import NEXT_SYSTEM, build_next_prompt, draft_next_moves, overheard

    record = {
        "people": [{**MARGAUX, "key": "margaux", "preferred_language": ""}],
        "promises": [{"key": "one-pager-to-margaux", "owed_by": "owner", "owed_to": "margaux", "what": "one page with numbers",
                      "due": "tomorrow", "evidence_turns": [13]}],
        "turns": [{"turn": t.turn, "session": 1, "speaker": t.speaker.split(":")[1], "text": t.text} for t in SOFA],
        "turn_kinds": {5: "ambient", 6: "ambient", 7: "ambient"},
        "translations": {7: ASIDE},
        "edges": [{**EDGE, "person": "margaux"}],
    }
    prompt = build_next_prompt(record, owner_name="Eric", owner_company="Hallwise")
    assert ("- margaux: Said to herself, in French: 'with numbers'. Yesterday's founder lost her with twenty slides and "
            "no numbers. | act: one page, numbers first") in prompt
    assert "never quote it or let on it was heard" in prompt
    rule = " ".join(NEXT_SYSTEM.split())
    assert "the message acts on it as if it were simply a good idea" in rule
    assert "Something said to themselves in another language never changes it" in rule

    def move(body):
        return {"promise_key": "one-pager-to-margaux", "person_key": "margaux", "kind": "email", "language": "English",
                "subject": "One page", "body": body, "body_english": "", "when": "", "duration_minutes": 0, "attach": "",
                "why": "", "remind_at": "", "nudge": ""}

    quoting = move("Hi Margaux, as you said, avec des chiffres: here is one page, with numbers. Eric")
    clean = move("Hi Margaux, here is our one-pager, the numbers up front, as promised. Eric")
    assert overheard(quoting, record) == "Avec des chiffres"
    assert overheard(clean, record) == ""
    # the aside's English, word for word, gives it away too; unless she said those words to the owner herself
    told = {**record, "edges": [{**EDGE, "person": "margaux", "said": "Une page, avec des chiffres", "english": "One page, with numbers"}]}
    assert overheard(move("Une page, avec des chiffres, Eric"), told) == "Une page, avec des chiffres"
    assert overheard(move("One page, with numbers, as promised. Eric"), told) == ""
    told["turns"] = told["turns"][:-1]  # without her own "One page, with numbers. Please."
    assert overheard(move("One page, with numbers, as promised. Eric"), told) == "One page, with numbers"

    prompts = []

    async def llm(system, user, schema=None, name=""):
        prompts.append(user)
        return {"moves": [quoting if len(prompts) == 1 else clean]}

    moves = asyncio.run(draft_next_moves(llm, record, owner_name="Eric", owner_company="Hallwise"))
    assert [m["body"] for m in moves] == [clean["body"]]
    assert len(prompts) == 2 and "- one-pager-to-margaux: it lets on what they said not to you (“Avec des chiffres”)" in prompts[1]


def test_with_the_edge_finder_on_spark_finds_no_edges_and_the_finder_s_stand_in_every_picture():
    from hallwise.extract import SCHEMA_NO_EDGES, SYSTEM_NO_EDGES

    asked = []
    renamed = {**MARGAUX, "key": "margaux-lefevre-corvane-capital-partners", "preferred_language": ""}

    async def llm(system, user, **kw):
        asked.append((system, kw.get("schema")))
        return copy.deepcopy(state(people=[renamed if len(asked) > 1 else {**MARGAUX, "preferred_language": ""}],
                                   edges=[{**EDGE, "said": "something Spark found"}]))

    extractor = Extractor(llm, "Eric", "Hallwise")
    extractor.edge_finder = True
    for t in SOFA:
        extractor.add_turn(t)
    asyncio.run(extractor.run())
    assert asked == [(SYSTEM_NO_EDGES, SCHEMA_NO_EDGES)] and extractor.state["edges"] == []  # Spark's own are ignored
    # the finder's answer: checked as Spark's are (only the words heard, in her own turn), into the picture at once
    out = extractor.take_edges([EDGE, {**EDGE, "said": "Une page, avec des chiffres"}, {**EDGE, "person": "nobody"}], 70_000)
    assert [(k, d["person"], d["said"]) for k, _, d in out] == [("edge", "margaux-lefevre-corvane-capital", "Avec des chiffres")]
    # Spark lists her under another key: the edge follows her voice, withdrawn under the old key, kept under the new
    second = asyncio.run(extractor.run())
    assert [(k, d["person"]) for k, _, d in second if k.startswith("edge")] == [
        ("edge", "margaux-lefevre-corvane-capital-partners"), ("edge_removed", "margaux-lefevre-corvane-capital")]
    assert extractor.take_edges([], 80_000) == [("edge_removed", 80_000, {"person": "margaux-lefevre-corvane-capital-partners",
                                                                          "turns": [5, 7]})]


# Kenji, on the phone in Japanese before he greeted the owner: the badge might do for his robots' field logs.
KENJI = {"key": "kenji", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "role": "", "speakers": ["1:G"],
         "preferred_language": "", "introduced_by": "", "evidence_turns": [22]}
CALL = {"person": "kenji", "turns": [19], "language": "Japanese",
        "said": "あ、エリックさんが来た。前に話した名札の人。うん、うちのロボットの現場ログに使えるかもしれない。",
        "english": "Ah, Eric's here. The badge person from before. Yes, could be usable for our robot's field logs.",
        "text": "Said on a call, in Japanese: the badge could log what's said around his robots.", "act": "offer a demo for his robots"}
TABLE = {
    "people": [KENJI], "owner_speakers": ["1:A"],
    "promises": [{"key": "coffee-kenji", "owed_by": "owner", "owed_to": "kenji", "what": "a coffee", "due": "Friday",
                  "evidence_turns": [24]}],
    "turns": [
        {"turn": 19, "session": 1, "speaker": "G", "text": CALL["said"]},
        {"turn": 20, "session": 1, "speaker": "A", "text": "Hey! It's, uh... sorry, it's been a long week."},
        {"turn": 22, "session": 1, "speaker": "G", "text": "Kenji, Kenji Watanabe, Hoshizora Robotics, the hardware meetup?"},
        {"turn": 23, "session": 1, "speaker": "A", "text": "Kenji! Of course. I make this badge. We still owe each other a coffee. Thursday?"},
        {"turn": 24, "session": 1, "speaker": "G", "text": "Thursday is... no, Friday. Friday is better."},
    ],
    "turn_kinds": {19: "ambient"}, "translations": {}, "edges": [CALL],
}


def kenji_move(body):
    return {"promise_key": "coffee-kenji", "person_key": "kenji", "kind": "calendar", "language": "English", "subject": "",
            "body": body, "body_english": "", "when": "", "duration_minutes": 30, "attach": "", "why": ""}


def test_a_close_paraphrase_of_what_they_said_on_the_phone_is_overheard_too():
    from hallwise.extract import overheard

    who = {"owner_name": "Eric", "owner_company": "Hallwise"}
    assert overheard(kenji_move("Coffee Friday? I'd love to show how the badge could capture Hoshizora field logs. Eric"), TABLE, who) == "field logs"
    assert overheard(kenji_move("Coffee Friday? Happy to bring a demo for your robots, and the intro to Lena. Eric"), TABLE, who) == ""
    assert overheard(kenji_move("Coffee Friday? Your logging in the field could use it. Eric"), TABLE, who) == "logging field"


def test_a_draft_never_claims_what_the_owner_s_sources_do_not_say():
    from hallwise.extract import unsupported_claims

    context = {"owner_name": "Eric", "owner_company": "Hallwise"}
    margaux = {**TABLE, "people": [{**MARGAUX, "key": "margaux"}], "edges": [],
               "promises": [{"key": "one-pager-to-margaux", "owed_by": "owner", "owed_to": "margaux", "what": "one page with numbers",
                             "due": "tomorrow"}]}
    invented = {**kenji_move("Great to meet you, Margot. Chloé told me you'd want to see this. "
                             "Hallwise makes money by selling our badge to event organizers. Eric"), "person_key": "margaux"}
    assert unsupported_claims(invented, margaux, context) == ["Hallwise makes money by selling our badge to event organizers."]
    plain = {**invented, "body": "Here is the Hallwise one-pager, one page with numbers, as promised. Eric"}
    assert unsupported_claims(plain, margaux, context) == []  # the promise, not a claim
    # the deck is a source: what it says may be said
    deck = "## Business model\nEvent organizers buy the badge for their attendees; the owner keeps the money."
    assert unsupported_claims(invented, margaux, {**context, "deck": deck}) == []
    # so are the owner's own lines tonight ("I make this badge")
    assert unsupported_claims(kenji_move("We make this badge. Coffee Friday? Eric"), TABLE, context) == []


def test_a_draft_that_still_claims_or_lets_on_after_one_rewrite_loses_that_sentence():
    from hallwise.extract import NEXT_SYSTEM, build_next_prompt, draft_next_moves

    first = kenji_move("Coffee on Friday works. Hallwise is used by 40 event organizers. I'd love to show the field logs idea. Eric")
    second = kenji_move("Coffee on Friday works. Hallwise is used by 40 event organizers. Happy to bring a demo for your robots. Eric")
    prompts = []

    async def llm(system, user, schema=None, name=""):
        prompts.append(user)
        return {"moves": [first if len(prompts) == 1 else second]}

    (move,) = asyncio.run(draft_next_moves(llm, TABLE, owner_name="Eric", owner_company="Hallwise"))
    assert len(prompts) == 2
    assert "- coffee-kenji: it lets on what they said not to you (“field logs”)" in prompts[1]
    assert "- coffee-kenji: “Hallwise is used by 40 event organizers.” states something about the owner's product" in prompts[1]
    assert move["body"] == "Coffee on Friday works. Happy to bring a demo for your robots. Eric"
    assert move["trimmed"] == ["Hallwise is used by 40 event organizers."]
    # the rules the drafts read, and the sources they are told about
    rule = " ".join(NEXT_SYSTEM.split())
    assert "say only what \"Owner's sources\" give" in rule and "never the specific thing they said (\"your field logs\")" in rule
    prompt = build_next_prompt(TABLE, owner_name="Eric", owner_company="Hallwise", deck="## Hallwise\nA badge.")
    assert "Owner's sources (the only facts about his product and company a draft may state)" in prompt and "## Hallwise\nA badge." in prompt
    assert "turn 23 [A, owner]: Kenji! Of course." in prompt and "turn 22 [G]: Kenji" in prompt


def test_an_act_says_what_to_do_never_what_to_claim():
    rule = " ".join(SYSTEM.split())
    assert "its form, length, order or what to bring" in rule
    assert "never a fact or claim to state and never the specific thing they said" in rule


def test_a_proposal_the_owner_says_he_will_set_up_is_his_promise():
    """Margaux: "Then let's do a call next week, the three of us. With Chloé." Eric: "Perfect. I'll send an invite."
    It came out owed by Margaux, so the morning had a nudge to her instead of an invite from him."""
    rule = " ".join(SYSTEM.split())
    assert 'answers that he will arrange it ("I\'ll send an invite", "I\'ll set it up", "I\'ll book it")' in rule
    assert 'the promise is owed_by "owner" and owed_to the person who proposed it' in rule
    assert "names everyone the proposal named" in rule and "due as agreed" in rule
