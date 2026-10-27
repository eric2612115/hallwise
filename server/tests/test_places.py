"""Every recording gets a place: the hello carries the badge's one fix, meta.json keeps it as taken, the API and the
people index hand it on, and the public replay export rounds it to about a kilometre."""

import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from hallwise.app import create_app
from hallwise.people import people_index
from hallwise.places import parse_place, public_place
from hallwise.recording import Hello

SERVER = Path(__file__).resolve().parents[1]
FIX = {"name": "Songshou Rd, Taipei", "lat": 25.035912, "lon": 121.567348}


def hello(**extra):
    return {"sample_rate": 24_000, "channels": 1, "layout": "mono", **extra}


def test_hello_takes_the_place_and_keeps_venue_for_older_readers():
    h = Hello.parse(hello(venue="ATT 4 FUN", place=FIX))
    assert h.place == FIX and h.venue == "ATT 4 FUN"
    # no venue typed: the place's name is the venue too
    assert Hello.parse(hello(place=FIX)).venue == "Songshou Rd, Taipei"
    # a place without a name of its own takes the venue's
    assert Hello.parse(hello(venue="Taipei", place={"lat": 25.04, "lon": 121.51})).place == {"name": "Taipei", "lat": 25.04, "lon": 121.51}
    # an older badge sends no place, and nothing changes
    old = Hello.parse(hello(venue="Taipei"))
    assert old.place is None and old.venue == "Taipei"


def test_a_place_that_is_not_a_fix_is_dropped_not_fatal():
    for junk in ("Taipei", [25.0, 121.5], {"name": "x"}, {"lat": "north", "lon": 1}, {"lat": 95, "lon": 121},
                 {"lat": 25, "lon": 200}, {"lat": math.nan, "lon": 121}, {"lat": 0, "lon": 0}, None):
        assert parse_place(junk) is None, junk
        assert Hello.parse(hello(place=junk)).place is None
    assert parse_place({"lat": "25.5", "lon": "121.25"}) == {"name": "", "lat": 25.5, "lon": 121.25}


def test_ingest_stores_the_precise_place_and_the_recordings_list_exposes_it(tmp_path):
    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=None))
    audio = np.zeros(4800, dtype=np.int16).tobytes()
    ids = []
    for extra in ({"venue": "", "place": FIX}, {"venue": "Taipei"}):
        with client.websocket_connect("/ingest") as ws:
            ws.send_text(json.dumps(hello(fake_script=[], **extra)))
            ids.append(ws.receive_json()["recording"])
            ws.send_bytes(audio)
            ws.send_text(json.dumps({"type": "end"}))
            ws.receive_json()
        time.sleep(1.1)  # recording ids are stamped to the second
    with_place, without = ids
    # a recording from before places: its meta.json has no place at all
    old = tmp_path / "recordings" / "20261020-203000-old0"
    old.mkdir()
    (old / "meta.json").write_text(json.dumps({"id": old.name, "started": 1.0, "venue": "Taipei, Xinyi"}))
    meta = json.loads((tmp_path / "recordings" / with_place / "meta.json").read_text())
    assert meta["place"] == FIX and meta["venue"] == "Songshou Rd, Taipei"
    listed = {m["id"]: m for m in client.get("/api/recordings").json()}
    assert listed[with_place]["place"] == FIX
    assert listed[without]["place"] is None
    assert listed[old.name]["place"] is None


def write_evening(root, rid, event, started, place, people):
    d = root / "recordings" / rid
    d.mkdir(parents=True)
    meta = {"id": rid, "event": event, "venue": "Taipei", "started": started}
    if place is not None:
        meta["place"] = place
    (d / "meta.json").write_text(json.dumps(meta))
    lines = [{"type": "recording_start", "t_ms": 0}]
    for key, name, company in people:
        lines.append({"type": "person", "t_ms": 1000, "key": key, "name": name, "company": company, "role": "",
                      "preferred_language": "", "evidence_turns": [1], "speakers": [], "introduced_by": ""})
    lines.append({"type": "recording_end", "t_ms": 2000})
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def week(root, now):
    write_evening(root, "a-afterparty", "Afterparty", now - 5 * 86400, FIX,
                  [("lena", "Lena Novak", "Brightline"), ("kenji", "Kenji Watanabe", "Hoshizora")])
    write_evening(root, "b-dinner", "Dinner", now - 2 * 86400, {"name": "Da'an, Taipei", "lat": 25.041612, "lon": 121.548637},
                  [("kenji", "Kenji Watanabe", "Hoshizora")])
    write_evening(root, "c-old", "Before places", now - 86400, None, [("ben", "Ben Okafor", "")])


def test_people_index_encounters_carry_their_evening_place(tmp_path):
    week(tmp_path, time.time())
    index = {p["name"]: p for p in people_index(tmp_path)}
    assert [e["place"] for e in index["Kenji Watanabe"]["encounters"]] == [
        {"name": "Da'an, Taipei", "lat": 25.041612, "lon": 121.548637}, FIX]
    assert index["Ben Okafor"]["encounters"][0]["place"] is None


def all_places(obj, out):
    if isinstance(obj, dict):
        if "lat" in obj or "lon" in obj:
            out.append(obj)
        for v in obj.values():
            all_places(v, out)
    elif isinstance(obj, list):
        for v in obj:
            all_places(v, out)
    return out


def test_the_replay_export_rounds_every_place_to_two_decimals(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    week(data, time.time())
    for rid in ("a-afterparty", "b-dinner"):
        subprocess.run([sys.executable, str(SERVER / "scripts" / "export_replay.py"), rid, "--data", str(data), "--out", str(out)],
                       check=True, capture_output=True, cwd=SERVER)
    dinner = json.loads((out / "b-dinner.json").read_text())
    assert dinner["meta"]["place"] == {"name": "Da'an, Taipei", "lat": 25.04, "lon": 121.55}
    kenji = next(p for p in dinner["people_index"]["people"] if p["name"] == "Kenji Watanabe")
    assert [e["place"] for e in kenji["encounters"]] == [
        {"name": "Songshou Rd, Taipei", "lat": 25.04, "lon": 121.57}, {"name": "Da'an, Taipei", "lat": 25.04, "lon": 121.55}]
    index = json.loads((out / "index.json").read_text())
    assert {r["id"]: r["place"] for r in index["recordings"]} == {
        "a-afterparty": public_place(FIX), "b-dinner": {"name": "Da'an, Taipei", "lat": 25.04, "lon": 121.55}}
    # nothing published anywhere in the export carries more than two decimals
    for f in out.glob("*.json"):
        found = all_places(json.loads(f.read_text()), [])
        assert found, f
        for p in found:
            assert p["lat"] == round(p["lat"], 2) and p["lon"] == round(p["lon"], 2), (f.name, p)
        assert "25.0359" not in f.read_text() and "121.5486" not in f.read_text()
    # the server's own copy is untouched
    assert json.loads((data / "recordings" / "a-afterparty" / "meta.json").read_text())["place"] == FIX
