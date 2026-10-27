"""The replay export carries the morning report when the server has one: whole, cost included, with places and
coordinates rounded like the rest of the export and no local paths; without one, the key is not there."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
FIX = {"name": "Songshou Rd, Taipei", "lat": 25.035912, "lon": 121.567348}


def evening(data, rid, started):
    d = data / "recordings" / rid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": rid, "event": "Founder dinner", "venue": "Taipei", "started": started,
                                             "tz": "Asia/Taipei", "place": FIX}))
    lines = [
        {"type": "recording_start", "t_ms": 0},
        {"type": "turn", "t_ms": 1000, "turn": 1, "speaker": "C", "session": 1, "text": "Kenji Watanabe, Hoshizora.",
         "start_ms": 100, "end_ms": 1000},
        {"type": "person", "t_ms": 1500, "key": "kenji", "name": "Kenji Watanabe", "company": "Hoshizora", "role": "",
         "preferred_language": "", "evidence_turns": [1], "speakers": ["1:C"], "introduced_by": ""},
        {"type": "next_move", "t_ms": 2500, "promise_key": "coffee-to-kenji", "person_key": "kenji", "kind": "email",
         "language": "English", "body": "Coffee Thursday? Eric", "body_english": ""},
        {"type": "recording_end", "t_ms": 3000},
    ]
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def morning(data, rid):
    """A report in the server's shape, with things the public page must not carry: a precise place, a bare
    lat/lon, and a note that names a file on this machine."""
    return {
        "recording": rid, "event": "Founder dinner", "venue": "Taipei", "tz": "Asia/Taipei", "day": "2026-10-28",
        "summary": {"people": 1, "followups": 1, "languages": [], "introductions": 0, "hooks": 1, "unverified": 1},
        "reach_out": [{
            "person": {"key": "kenji", "name": "Kenji Watanabe", "company": "Hoshizora", "tonight": True},
            "hook": None, "more_hooks": [],
            "followup": {"source": "next_move", "promise_key": "coffee-to-kenji",
                         "move": {"promise_key": "coffee-to-kenji", "person_key": "kenji", "kind": "email",
                                  "body": "Coffee Friday, as you asked? Eric", "redrafted": True}},
            "check": {"status": "no_public_record", "sources": [], "note": "no public record found, check before sending"},
        }],
        "redrafted": ["coffee-to-kenji"],
        "hooks": [{"type": "open_thread", "people": ["kenji"], "names": ["Kenji Watanabe"], "record_keys": {"kenji": "kenji"},
                   "title": "Coffee with Kenji", "tag": "Kenji asked for Friday", "reason": "Kenji asked to move coffee.",
                   "evidence": [{"kind": "turn", "recording": rid, "event": "Founder dinner", "day": "Oct 28", "turn": 1,
                                 "speaker": "Kenji Watanabe", "quote": "Kenji Watanabe, Hoshizora.", "id": "E1"}],
                   "promise_key": "coffee-to-kenji", "place": dict(FIX)}],
        "checked": [{"key": "kenji", "name": "Kenji Watanabe", "company": "Hoshizora", "status": "no_public_record",
                     "findings": [], "sources": ["https://example.com/home/team"], "searched": True, "cached": True,
                     "location": {"lat": 25.041612, "lon": 121.548637}}],
        "unchecked": [],
        "due_today": [],
        "notes": [f"research cache at {data / 'research' / 'kenji.json'} was stale",
                  "lookup wrote /var/folders/zz/hallwise/kenji.json"],
        "cost": {"hooks_tokens": 23891, "research_tokens": 0, "research_requests": 0, "searches": 0, "usd": 0.0795},
    }


def export(rid, data, out):
    """As the task runs it: $HALLWISE_DATA picks the data folder."""
    subprocess.run([sys.executable, str(SERVER / "scripts" / "export_replay.py"), rid, "--out", str(out)],
                   check=True, capture_output=True, cwd=SERVER, env={**os.environ, "HALLWISE_DATA": str(data)})
    return (out / f"{rid}.json").read_text()


def test_the_export_carries_the_morning_report_rounded_and_without_local_paths(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    evening(data, "a-dinner", time.time() - 3600)
    (data / "reports").mkdir()
    report = morning(data, "a-dinner")
    (data / "reports" / "a-dinner.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

    text = export("a-dinner", data, out)
    got = json.loads(text)["report"]
    # what the page shows comes through as the server wrote it
    for key in ("summary", "reach_out", "redrafted", "unchecked", "due_today", "cost", "day", "tz"):
        assert got[key] == report[key], key
    assert {k: v for k, v in got["checked"][0].items() if k != "location"} == {
        k: v for k, v in report["checked"][0].items() if k != "location"}
    assert got["cost"] == {"hooks_tokens": 23891, "research_tokens": 0, "research_requests": 0, "searches": 0, "usd": 0.0795}
    assert got["hooks"][0]["evidence"] == report["hooks"][0]["evidence"]
    assert got["checked"][0]["sources"] == ["https://example.com/home/team"]  # a URL is not a local path
    # places and bare coordinates to two decimals, like the rest of the export
    assert got["hooks"][0]["place"] == {"name": "Songshou Rd, Taipei", "lat": 25.04, "lon": 121.57}
    assert got["checked"][0]["location"] == {"lat": 25.04, "lon": 121.55}
    assert "25.0359" not in text and "121.5486" not in text
    # no file on this machine named by its path, in the report or anywhere else in the export
    assert got["notes"] == ["research cache at kenji.json was stale", "lookup wrote kenji.json"]
    assert str(tmp_path) not in text and str(Path.home()) not in text and str(SERVER) not in text
    # the server's own copy is untouched
    assert json.loads((data / "reports" / "a-dinner.json").read_text()) == report


def test_without_a_report_the_export_has_no_report_key(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    evening(data, "b-dinner", time.time() - 3600)
    (data / "reports").mkdir()
    (data / "reports" / "someone-else.json").write_text(json.dumps(morning(data, "someone-else")))

    exported = json.loads(export("b-dinner", data, out))
    assert "report" not in exported
    assert exported["meta"]["place"] == {"name": "Songshou Rd, Taipei", "lat": 25.04, "lon": 121.57}
    assert [m["body"] for m in exported["events"] if m["type"] == "next_move"] == ["Coffee Thursday? Eric"]


def test_a_data_folder_anywhere_is_cut_from_the_report_text():
    spec = importlib.util.spec_from_file_location("export_replay", SERVER / "scripts" / "export_replay.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    got = exporter.public_report({"notes": ["read /data/hallwise/research/kenji.json", "see https://example.com/data/hallwise"]},
                                 [Path("/data/hallwise")])
    assert got == {"notes": ["read kenji.json", "see https://example.com/data/hallwise"]}
