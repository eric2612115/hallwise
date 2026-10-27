"""The fast "met before": a known person's name in a new turn, bound to that turn's speaker before Muse Spark runs."""

import json
from pathlib import Path

from hallwise.extract import Turn
from hallwise.recall import Matcher, Recall

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "rehearsal_turns.json").read_text())
INDEX = FIXTURE["index"]


def matcher():
    return Matcher(INDEX, "Eric", "Hallwise")


def test_the_rehearsal_introductions_hit_and_nothing_else_does():
    found = {}
    for t in FIXTURE["turns"]:
        hit = matcher().find(t["text"])
        if hit is not None:
            found.setdefault(hit.entry["name"], set()).add(t["text"])
    assert found == {
        "Siddharth Raghunathan": {
            "Eric! Siddharth Raghunathan, Quill Mesh, we met at Blockchain Week. You know Kenji.",
            "I'm Siddharth, Siddharth Ragoo Nathan. I run Quill Mesh, we um schedule warehouse robots.",
        },
        "Kenji Watanabe": {
            "Kenji Watanabe, Hoshizora Robotics. We keep running into each other.",
            "Kenji Watanabe, Hoshizora Robotics. W A T A N A B E.",
            "Kenji Watanabe we keep running into each other.",
        },
    }
    # 66 turns, Eric's own among them ("I'm Eric from Hallwise, this badge."), and the lines that only name
    # someone ("You should meet Siddharth", "Siddharth said you know trading systems", "you know Kenji").
    assert len(FIXTURE["turns"]) == 66
    assert any("I'm Eric from Hallwise" in t["text"] for t in FIXTURE["turns"])


def test_how_a_name_is_heard_does_not_matter_but_who_it_is_about_does():
    m = matcher()
    assert m.find("eric!  SIDDHARTH   raghunathan, quill mesh").why == "full name"
    assert m.find("I'm Siddharth Ragoo Nathan.").why == "full name"  # the surname, heard loosely
    assert m.find("Kenji, Hoshizora.").why == "first name and company"
    assert m.find("Chloe! Corvane Capital.").entry["name"] == "Chloé Martin"  # accents set aside
    assert m.find("Siddharth, from Blockchain Week!").why == "first name and event"
    assert m.find("Tomas Ferreira.").entry["name"] == "Tomás Ferreira"
    for text in [
        "I'm Eric, from Hallwise.",  # the owner
        "Hi, Eric from Hallwise. May I join your conversation?",
        "You should meet Kenji Watanabe.",  # about someone else
        "This is Siddharth Raghunathan, Quill Mesh.",
        "Siddharth Raghunathan said you know trading systems.",
        "Kenji's at Hoshizora Robotics now.",
        "Siddharth Ramachandran.",  # another surname, no company
        "Hana, nice to see you.",  # a first name alone
        "Hoshizora Robotics is hiring.",  # a company alone: Kenji or Hana?
        "The panel ran long, so I missed the first half.",
    ]:
        assert m.find(text) is None, text


def test_an_index_entry_that_is_the_owner_never_matches():
    index = INDEX + [{"key": "eric-hallwise", "name": "Eric", "company": "Hallwise", "encounters": [
        {"recording": "x", "event": "Founder dinner", "venue": "", "started": 1.0, "introduced_by": ""}], "promises": []}]
    assert Matcher(index, "Eric", "Hallwise").find("Eric! Hallwise, this badge.") is None


class FakeThreads:
    def for_person(self, name, company, record_key):
        if name.startswith("Siddharth"):
            return [{"person_key": record_key, "type": "mutual_connection", "title": "Tomás's friend · Oct 23",
                     "tag": "Tomás's friend · Oct 23", "reason": "r", "promise_key": "", "evidence": []}]
        return []


def recall():
    return Recall(INDEX, "Eric", "Hallwise", threads=FakeThreads(), exclude="tonight", before=2e9)


SID = "Eric! Siddharth Raghunathan, Quill Mesh, we met at Blockchain Week. You know Kenji."


def test_a_known_name_rings_at_once_bound_to_the_speaker_with_its_hooks():
    r = recall()
    out = r.on_turn(Turn(23, "1:F", 120_000, 125_000, SID), {"owner_speakers": ["1:B"], "people": []}, set(), 125_400)
    assert [k for k, _, _ in out] == ["person_history", "hook"]
    kind, t_ms, history = out[0]
    assert t_ms == 125_400
    assert history["key"] == "siddharth-raghunathan-quill-mesh" and history["speaker"] == "1:F"
    assert history["provisional"] is True and history["turn"] == 23 and history["matched"] == "full name"
    assert [e["event"] for e in history["encounters"]] == ["Blockchain Week side event", "ETH Taipei afterparty"]
    assert out[1][2]["provisional"] is True and out[1][2]["kind"] == "mutual_connection"
    # once per person, never for the owner's voice or an unlabelled one
    assert r.on_turn(Turn(24, "1:F", 0, 0, SID), {"people": []}, set(), 0) == []
    kenji = "Kenji Watanabe, Hoshizora Robotics."
    assert recall().on_turn(Turn(5, "1:B", 0, 0, kenji), {"owner_speakers": ["1:B"]}, set(), 0) == []
    assert recall().on_turn(Turn(5, "1:?", 0, 0, kenji), {}, set(), 0) == []


def test_spark_already_naming_that_voice_decides_the_key_or_stops_it():
    named = {"people": [{"key": "siddharth", "name": "Siddharth", "company": "", "speakers": ["1:F"]}]}
    out = recall().on_turn(Turn(23, "1:F", 0, 0, SID), named, set(), 0)
    assert out[0][2]["key"] == "siddharth"  # the ring goes on the person already in the room
    other = {"people": [{"key": "leo-wong", "name": "Leo Wong", "company": "", "speakers": ["1:F"]}]}
    assert recall().on_turn(Turn(23, "1:F", 0, 0, SID), other, set(), 0) == []
    ringed = {"people": [{"key": "sid-qm", "name": "Siddharth Raghunathan", "company": "Quill Mesh", "speakers": ["1:A"]}]}
    assert recall().on_turn(Turn(23, "1:F", 0, 0, SID), ringed, {"sid-qm"}, 0) == []


def spark_person(key, name, company, speaker):
    return {"key": key, "name": name, "company": company, "speakers": [speaker], "evidence_turns": [23]}


def test_the_next_spark_run_confirms_it_under_the_same_key():
    r = recall()
    r.on_turn(Turn(23, "1:F", 0, 0, SID), {"people": []}, set(), 0)
    sent = {"siddharth-raghunathan-quill-mesh"}  # Spark's own match already sent the confirmed history
    state = {"people": [spark_person("siddharth-raghunathan-quill-mesh", "Siddharth Raghunathan", "Quill Mesh", "1:F")]}
    assert r.after_run(state, seen_turn=22, sent=sent, t_ms=1) == []  # this run never heard the turn
    assert r.after_run(state, seen_turn=23, sent=sent, t_ms=1) == []
    assert r.pending == {} and r.close(9) == []


def test_spark_confirming_under_its_own_key_moves_the_ring_there():
    r = recall()
    r.on_turn(Turn(23, "1:F", 0, 0, SID), {"people": []}, set(), 0)
    sent: set[str] = set()
    state = {"people": [spark_person("siddharth-ragoo-nathan", "Siddharth Ragoo Nathan", "", "1:F")]}
    out = r.after_run(state, seen_turn=23, sent=sent, t_ms=7)
    assert [k for k, _, _ in out] == ["person_history", "person_history_removed", "hook_removed"]
    assert out[0][2]["key"] == "siddharth-ragoo-nathan" and "provisional" not in out[0][2]
    assert out[1][2] == {"key": "siddharth-raghunathan-quill-mesh", "speaker": "1:F",
                         "reason": "confirmed as siddharth-ragoo-nathan", "replaced_by": "siddharth-ragoo-nathan"}
    assert sent == {"siddharth-ragoo-nathan"}


def test_spark_naming_someone_else_for_that_voice_withdraws_it():
    r = recall()
    r.on_turn(Turn(23, "1:F", 0, 0, SID), {"people": []}, set(), 0)
    nobody = {"people": []}
    assert r.after_run(nobody, seen_turn=30, sent=set(), t_ms=1) == []  # not named yet: still provisional
    state = {"people": [spark_person("tomas-ferreira", "Tomás Ferreira", "Marlin Ventures", "1:F")]}
    out = r.after_run(state, seen_turn=30, sent=set(), t_ms=8)
    assert [k for k, _, _ in out] == ["person_history_removed", "hook_removed"]
    assert out[0][2]["reason"] == "Muse Spark heard Tomás Ferreira for this voice"


def test_whatever_spark_never_confirmed_is_withdrawn_at_the_end():
    r = recall()
    r.on_turn(Turn(23, "1:F", 0, 0, SID), {"people": []}, set(), 0)
    out = r.close(99_000)
    assert [(k, d["key"], d["reason"]) for k, _, d in out if k == "person_history_removed"] == [
        ("person_history_removed", "siddharth-raghunathan-quill-mesh", "not confirmed by Muse Spark")]
