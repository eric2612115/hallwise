import json
import time

from hallwise.people import history_event, match, people_index


def write_recording(root, rid, event, started, people, promises=()):
    d = root / "recordings" / rid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": rid, "event": event, "venue": "Taipei", "started": started}))
    lines = [{"type": "recording_start", "t_ms": 0}]
    for p in people:
        lines.append({"type": "person", "t_ms": 1000, "evidence_turns": [1], "speakers": [], "introduced_by": "", **p})
    for q in promises:
        lines.append({"type": "promise", "t_ms": 2000, "evidence_turns": [1], "replaces": "", **q})
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def test_people_index_merges_the_same_person_across_recordings(tmp_path):
    now = time.time()
    write_recording(tmp_path, "a", "Afterparty", now - 7 * 86400,
                    [{"key": "kenji-watanabe-hoshizora-robotics", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "role": "", "preferred_language": "Japanese"},
                     {"key": "lena-novak-brightline", "name": "Lena Novak", "company": "Brightline", "role": "energy", "preferred_language": ""}],
                    [{"key": "intro", "owed_by": "owner", "owed_to": "lena-novak-brightline", "what": "introduce Kenji", "due": ""}])
    write_recording(tmp_path, "b", "Rehearsal", now,
                    [{"key": "kenji-watanabe-hoshizora", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "role": "", "preferred_language": ""}])
    index = people_index(tmp_path)
    kenji = next(e for e in index if e["name"] == "Kenji Watanabe")
    assert [e["event"] for e in kenji["encounters"]] == ["Rehearsal", "Afterparty"]
    assert kenji["language"] == "Japanese"
    assert index[0]["name"] == "Kenji Watanabe"

    known = people_index(tmp_path, exclude="b")
    assert [e["event"] for e in next(e for e in known if e["name"] == "Kenji Watanabe")["encounters"]] == ["Afterparty"]
    assert match(known, "Lena Novak", "") is not None
    assert match(known, "Lena Novak", "Other Corp") is None
    h = history_event(match(known, "Lena Novak", ""), "lena-novak", exclude="b")
    assert h["key"] == "lena-novak" and h["encounters"][0]["event"] == "Afterparty"
    assert h["promises"][0]["direction"] == "owner_owes"


def test_history_counts_only_earlier_evenings(tmp_path):
    now = time.time()
    write_recording(tmp_path, "early", "Dinner", now - 3 * 86400,
                    [{"key": "k", "name": "Kenji Watanabe", "company": "Hoshizora", "role": "", "preferred_language": ""}])
    write_recording(tmp_path, "late", "Rehearsal", now,
                    [{"key": "k", "name": "Kenji Watanabe", "company": "Hoshizora", "role": "", "preferred_language": ""}])
    write_recording(tmp_path, "mid", "Meetup", now - 86400,
                    [{"key": "k", "name": "Kenji Watanabe", "company": "Hoshizora", "role": "", "preferred_language": ""}])
    entry = match(people_index(tmp_path, exclude="mid"), "Kenji Watanabe", "Hoshizora")
    h = history_event(entry, "k", exclude="mid", before=now - 86400)
    assert [e["event"] for e in h["encounters"]] == ["Dinner"]


def test_match_forgives_a_misheard_surname_when_the_company_matches(tmp_path):
    now = time.time()
    write_recording(tmp_path, "a", "Afterparty", now - 86400,
                    [{"key": "sid", "name": "Siddharth Raghunathan", "company": "Quill Mesh", "role": "", "preferred_language": ""}])
    known = people_index(tmp_path)
    assert match(known, "Siddharth Ragoo Nathan", "Quill Mesh")["name"] == "Siddharth Raghunathan"
    assert match(known, "Siddharth Ragoo Nathan", "Other Co") is None
