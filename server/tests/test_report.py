import json
import time
from io import BytesIO

from fastapi.testclient import TestClient
from auth import AUTH
from PIL import Image
from pictures import picture
from week import week

from hallwise.app import create_app
from hallwise.report import Reports, report_day
from hallwise.research import Researcher



def make_app(tmp_path, calls, prompts=None):
    async def llm(system, user, schema=None, name=""):
        calls.append(name)
        if prompts is not None:
            prompts[name] = user
        if name == "hallwise_next_moves":
            return {"moves": [{
                "promise_key": "one-pager-to-margot-lefevre", "person_key": "margot-lefevre", "kind": "email",
                "language": "French", "subject": "Une page", "body": "Bonjour Margot, Chloé m'a dit que vous voudriez voir ça. Eric",
                "body_english": "Chloé told me you'd want to see this.", "when": "", "duration_minutes": 30, "attach": "",
                "why": "", "remind_at": "2000-01-01T10:00:00+08:00", "nudge": "One-pager for Margot"}]}
        chloe = next(line.split(" | ")[0] for line in user.splitlines() if "My colleague Margaux" in line)
        intro = next(line.split(" | ")[0] for line in user.splitlines() if "introduce you two" in line)
        return {"hooks": [
            {"type": "mutual_connection", "people": ["margot-lefevre", "chlo-martin-corvane-capital"], "title": "Chloé's colleague",
             "tag": "Chloé's colleague · Oct 23", "reason": "Chloé said her colleague Margaux would want to see this.",
             "evidence": [chloe], "promise_key": "", "language": "French", "draft": "", "draft_english": ""},
            {"type": "introduction", "people": ["kenji-watanabe-hoshizora-robotics", "lena-novak-brightline-grid"],
             "title": "Introduce Lena to Kenji", "tag": "you owe Lena an intro", "reason": "Promised on Oct 20.",
             "evidence": [intro], "promise_key": "introduce-lena", "language": "English",
             "draft": "Lena, meet Kenji. Eric", "draft_english": ""},
        ]}

    async def search(instructions, input, schema=None, name=""):
        calls.append("search")
        return {"answer": {"status": "no_public_record", "findings": []}, "results": [], "cited": [], "searches": 1,
                "usage": {"total_tokens": 5000, "input_tokens": 4500, "output_tokens": 500}}

    reports = Reports(tmp_path, lambda: llm, Researcher(tmp_path, search, min_gap_s=0))
    return TestClient(create_app(tmp_path, asr="fake", make_extractor=None, reports=reports), headers=AUTH)


def test_report_runs_stores_and_serves(tmp_path):
    week(tmp_path, time.time())
    calls, prompts = [], {}
    client = make_app(tmp_path, calls, prompts)
    assert client.get("/api/report/latest").status_code == 404
    r = client.post("/api/report/run", params={"recording": "c-tonight"})
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["cached"] is False and report["generated_at"] > 0
    # Kenji is looked up (Margot has no company to search); the drafts written without a reason are written again
    assert calls == ["search", "hallwise_hooks", "hallwise_next_moves"]
    assert "margot-lefevre: Chloé's colleague | Chloé said her colleague Margaux" in prompts["hallwise_next_moves"]
    assert report["redrafted"] == ["one-pager-to-margot-lefevre"]
    assert (tmp_path / "reports" / "c-tonight.json").exists()

    rows = {row["person"]["name"]: row for row in report["reach_out"]}
    margot = rows["Margot Lefèvre"]
    assert margot["hook"]["title"] == "Chloé's colleague"
    assert margot["followup"]["source"] == "next_move" and margot["followup"]["move"]["language"] == "French"
    assert margot["followup"]["move"]["body"].startswith("Bonjour Margot, Chloé m'a dit")
    kenji_move = rows["Kenji Watanabe"]["followup"]["move"]
    assert kenji_move["body"] == "Coffee Friday? Eric" and "redrafted" not in kenji_move  # not in the new drafts: kept
    assert margot["check"]["status"] == "unchecked"
    assert rows["Kenji Watanabe"]["hook"]["type"] == "introduction"
    assert rows["Kenji Watanabe"]["check"]["status"] == "no_public_record"
    assert [h["title"] for h in report["introductions"]] == ["Introduce Lena to Kenji"]
    assert report["introductions"][0]["draft"] == "Lena, meet Kenji. Eric"
    assert [c["name"] for c in report["checked"]] == ["Kenji Watanabe"]
    assert {s["name"] for s in report["unchecked"]} == {"Margot Lefèvre"}
    assert [d["promise_key"] for d in report["due_today"]] == ["one-pager-to-margot-lefevre"]
    assert report["due_today"][0]["overdue"] is True
    assert report["summary"]["people"] == 2 and report["summary"]["languages"] == ["French"]

    again = client.post("/api/report/run", params={"recording": "c-tonight"}).json()
    assert again["cached"] is True and len(calls) == 3  # within the hour: the stored one
    forced = client.post("/api/report/run", params={"recording": "c-tonight", "force": 1}).json()
    assert forced["cached"] is False and calls[3:] == ["hallwise_hooks", "hallwise_next_moves"]  # research came from cache

    assert client.get("/api/report/latest").json()["generated_at"] == forced["generated_at"]
    assert client.get("/api/report/c-tonight").json()["recording"] == "c-tonight"
    assert client.get("/api/report/a-afterparty").status_code == 404
    assert client.post("/api/report/run", params={"recording": "nope"}).status_code == 404
    assert client.post("/api/report/run", params={"recording": "../c-tonight"}).status_code == 404


def test_report_without_spark_falls_back_to_threads(tmp_path):
    week(tmp_path, time.time())
    reports = Reports(tmp_path, lambda: None, Researcher(tmp_path, None, off_reason="test"))
    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=None, reports=reports), headers=AUTH)
    report = client.post("/api/report/run", params={"recording": "c-tonight"}).json()
    titles = {row["person"]["name"]: (row["hook"] or {}).get("title", "") for row in report["reach_out"]}
    assert titles["Margot Lefèvre"].startswith("Chloé's colleague")
    assert titles["Kenji Watanabe"].startswith("you owe Lena an intro")
    assert report["checked"] == [] and report["notes"]


def test_faces_are_kept_by_person_and_served(tmp_path):
    week(tmp_path, time.time())
    client = make_app(tmp_path, [])
    r = client.post("/api/people/kenji-watanabe-hoshizora-robotics/face", content=picture("JPEG"), headers={"Content-Type": "image/jpeg"})
    kept = (tmp_path / "faces" / "kenji-watanabe-hoshizora-robotics.jpg").read_bytes()
    assert r.status_code == 200 and r.json()["bytes"] == len(kept)
    assert Image.open(BytesIO(kept)).format == "JPEG"  # kept re-encoded, without whatever metadata came in
    got = client.get("/api/people/kenji-watanabe-hoshizora-robotics/face")
    assert got.status_code == 200 and got.content == kept and got.headers["content-type"] == "image/jpeg"

    # A PNG is kept too, as a JPEG.
    r = client.post("/api/people/lena-novak-brightline-grid/face", content=picture("PNG"), headers={"Content-Type": "image/png"})
    assert r.status_code == 200
    assert Image.open(tmp_path / "faces" / "lena-novak-brightline-grid.jpg").format == "JPEG"
    # A record key from another evening finds the face through the index match (name and company).
    assert client.get("/api/people/kenji-hoshizora/face", params={"name": "Kenji Watanabe", "company": "Hoshizora Robotics"}).content == kept
    assert client.get("/api/people/nobody/face").status_code == 404
    assert client.post("/api/people/x/face", content=b"GIF89a", headers={"Content-Type": "image/gif"}).status_code == 415
    assert client.post("/api/people/..secret/face", content=picture(), headers={"Content-Type": "image/jpeg"}).status_code == 400
    assert client.post("/api/people/Kenji/face", content=picture(), headers={"Content-Type": "image/jpeg"}).status_code == 400
    kenji = next(p for p in client.get("/api/people").json() if p["key"] == "kenji-watanabe-hoshizora-robotics")
    assert kenji["face"] is True


def test_the_report_day_is_the_morning_after():
    tz = "Asia/Taipei"
    assert report_day(1793054436, tz) == "2026-10-27"  # 06:40: the same morning
    assert report_day(1793054436 + 14 * 3600, tz) == "2026-10-28"  # 20:40: tomorrow morning


def test_the_automatic_run_after_a_recording_writes_the_report(tmp_path):
    import asyncio

    week(tmp_path, time.time())
    reports = Reports(tmp_path, lambda: None, Researcher(tmp_path, None, off_reason="test"))
    asyncio.run(reports.later("c-tonight", 0))
    assert reports.get("c-tonight")["recording"] == "c-tonight"
    asyncio.run(reports.later("nope", 0))  # nobody is waiting: a bad id is only logged
    assert reports.get("nope") is None
