import asyncio
import json

import numpy as np
from fastapi.testclient import TestClient

from hallwise.app import create_app
from hallwise.extract import SCHEMA, Extractor, Turn, build_prompt

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

    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=make_extractor))
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
