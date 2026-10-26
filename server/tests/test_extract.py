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
            suspect_words=[{"heard": "Vexy", "turn": 1, "likely": "Vexi", "reason": "owner's company"}],
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
        ("room_topic", 13_700),
    ]
    promise = second[2][2]
    assert (promise["due"], promise["replaces"], promise["new"]) == ("Friday", "Thursday", False)


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
