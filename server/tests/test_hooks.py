import asyncio
import time

from week import evening, week

from hallwise.hooks import HOOK_SCHEMA, Threads, build_hook_context, clean_hooks, find_hooks, name_sound

RESEARCH = [{"key": "kenji-watanabe-hoshizora-robotics", "record_key": "kenji-watanabe-hoshizora-robotics",
             "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "status": "partial",
             "findings": [{"kind": "recent", "text": "Hoshizora Robotics opened a Taipei office", "source": "https://hoshizora.example/news"},
                          {"kind": "company", "text": "unsourced claim", "source": ""}]}]


def ids_for(ctx, quote_part):
    return [k for k, e in ctx.evidence.items() if quote_part in e.get("quote", "")]


def test_the_hook_prompt_carries_the_evidence(tmp_path):
    week(tmp_path, time.time())
    ctx = build_hook_context(tmp_path, "c-tonight", RESEARCH, moves=[{"promise_key": "coffee-to-kenji", "person_key": "kenji-watanabe-hoshizora-robotics"}])
    p = ctx.prompt
    chloe = ids_for(ctx, "My colleague Margaux")[0]
    intro = ids_for(ctx, "I'll introduce you two on Monday.")[0]
    assert f"{chloe} | Blockchain Week side event" in p and "My colleague Margaux is in Paris" in p
    assert f"introduce-lena | ETH Taipei afterparty" in p and f"Eric owes Lena Novak [lena-novak-brightline-grid]: introduce you to Kenji | due: Monday | evidence: {intro}" in p
    assert f"Chloé Martin [chlo-martin-corvane-capital] said the name “Margaux” | evidence: {chloe}" in p
    assert "kenji-watanabe-hoshizora-robotics | Kenji Watanabe, Hoshizora Robotics | met: ETH Taipei afterparty" in p
    assert "tonight | draft ready tonight" in p
    assert "R1 | recent: Hoshizora Robotics opened a Taipei office (source: https://hoshizora.example/news)" in p
    assert "unsourced claim" not in p  # research without a source never reaches the model
    assert ctx.tonight["margot-lef-vre"] == "margot-lefevre"


def test_hooks_citing_unknown_people_or_evidence_are_dropped(tmp_path):
    week(tmp_path, time.time())
    ctx = build_hook_context(tmp_path, "c-tonight", RESEARCH)
    chloe = ids_for(ctx, "My colleague Margaux")[0]
    intro = ids_for(ctx, "I'll introduce you two on Monday.")[0]
    good = {"type": "mutual_connection", "people": ["margot-lefevre", "chlo-martin-corvane-capital"], "title": "Chloé's colleague",
            "tag": "Chloé's colleague · Oct 23", "reason": "Chloé said so.", "evidence": [chloe], "promise_key": "",
            "language": "French", "draft": "", "draft_english": ""}
    raw = {"hooks": [
        good,
        {**good, "people": ["margot-lefevre", "julien-caron"]},  # nobody by that key
        {**good, "evidence": [chloe, "E999"]},  # evidence the prompt never had
        {**good, "evidence": []},
        {**good, "type": "timely", "evidence": [chloe]},  # timely without research
        {**good, "type": "timely", "people": ["kenji-watanabe-hoshizora-robotics"], "evidence": ["R1"], "title": "New Taipei office"},
        {**good, "type": "introduction", "people": ["Kenji Watanabe-Hoshizora Robotics", "lena-novak-brightline-grid"],
         "evidence": [intro.lower()], "promise_key": "Introduce Lena", "title": "Introduce " + "Lena to Kenji " * 6},
        {**good, "type": "gossip"},
    ]}
    hooks = clean_hooks(raw, ctx)
    assert [h["type"] for h in hooks] == ["mutual_connection", "timely", "introduction"]
    m, t, i = hooks
    assert m["people"] == ["margot-lef-vre", "chlo-martin-corvane-capital"]  # tonight's key is the index key
    assert m["record_keys"] == {"margot-lef-vre": "margot-lefevre"}
    assert m["evidence"][0]["quote"].startswith("Chloé Martin, Corvane Capital. My colleague Margaux")  # from the log
    assert (m["evidence"][0]["recording"], m["evidence"][0]["turn"]) == ("b-blockchain", 1)
    assert t["evidence"][0]["source"] == "https://hoshizora.example/news"
    assert i["promise_key"] == "introduce-lena" and len(i["title"].split()) == 10


def test_find_hooks_sends_the_prompt_with_the_schema(tmp_path):
    week(tmp_path, time.time())
    seen = {}

    async def llm(system, user, schema=None, name=""):
        seen.update(system=system, user=user, schema=schema)
        return {"hooks": []}

    hooks, ctx = asyncio.run(find_hooks(llm, tmp_path, "c-tonight", []))
    assert hooks == [] and seen["schema"] is HOOK_SCHEMA and seen["user"] == ctx.prompt
    assert "A mention links two people only when the text says so" in seen["system"]


def test_threads_find_the_open_intro_and_the_colleague(tmp_path):
    now = time.time()
    week(tmp_path, now)
    threads = Threads.load(tmp_path, exclude="c-tonight", before=now - 3600)
    margot = threads.for_person("Margot Lefèvre", "", "margot-lefevre")
    assert [h["title"].split(" · ")[0] for h in margot] == ["Chloé's colleague"]
    assert margot[0]["evidence"][0]["recording"] == "b-blockchain"
    kenji = threads.for_person("Kenji Watanabe", "Hoshizora Robotics", "kenji")
    assert kenji[0]["title"].startswith("you owe Lena an intro · ") and kenji[0]["promise_key"] == "introduce-lena"
    lena = threads.for_person("Lena Novak", "Brightline Grid", "lena")
    assert lena[0]["title"].startswith("you owe Lena an intro to Kenji")
    assert threads.for_person("Julian", "", "julian") == []


def test_a_thank_you_closes_an_introduction(tmp_path):
    now = time.time()
    week(tmp_path, now)
    evening(tmp_path, "b2-later", "Coffee", now - 2 * 86400, [("1:G", "Kenji here. Thanks for the intro to Lena!")],
            people=[{"key": "kenji-watanabe-hoshizora-robotics", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:G"]}])
    threads = Threads.load(tmp_path, exclude="c-tonight", before=now - 3600)
    assert threads.intros == []


def test_names_sound_alike_across_spellings():
    assert name_sound("Margaux") == name_sound("Margot")
    assert name_sound("Lefèvre") == name_sound("Lefevre")


def test_a_person_turning_up_gets_their_hooks_and_the_drafts_use_them(tmp_path):
    import json

    import numpy as np
    from fastapi.testclient import TestClient

    from hallwise.app import create_app
    from hallwise.extract import Extractor

    week(tmp_path, time.time() - 600)
    prompts = {}
    margot = {"key": "margot-lefevre", "name": "Margot Lefèvre", "company": "", "role": "", "speakers": ["1:A"],
              "preferred_language": "French", "introduced_by": "", "evidence_turns": [0]}
    promise = {"key": "one-pager-to-margot-lefevre", "owed_by": "owner", "owed_to": "margot-lefevre",
               "what": "one page with numbers", "due": "tomorrow", "replaces": "", "evidence_turns": [0]}

    async def llm(system, user, schema=None, name=""):
        prompts[name or "record"] = user
        if name == "hallwise_next_moves":
            return {"moves": []}
        return {"owner_speakers": ["1:B"], "turns": [], "people": [margot], "mentioned": [], "promises": [promise],
                "suspect_words": [], "translations": [], "room_topics": []}

    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=lambda hello: Extractor(llm, "Eric", "Hallwise")))
    with client.websocket_connect("/ingest") as ws:
        ws.send_text(json.dumps({"sample_rate": 24_000, "channels": 1, "layout": "mono", "owner_name": "Eric",
                                 "fake_script": [{"start_ms": 100, "end_ms": 600, "speaker": "A", "text": "Margot Lefèvre."}]}))
        rid = ws.receive_json()["recording"]
        ws.send_bytes(np.zeros(24_000, dtype=np.int16).tobytes())
        ws.send_text(json.dumps({"type": "end"}))
        ws.receive_json()

    events = client.get(f"/api/recordings/{rid}/events").json()
    hooks = [e for e in events if e["type"] == "hook"]
    assert [(h["person_key"], h["title"].split(" · ")[0]) for h in hooks] == [("margot-lefevre", "Chloé's colleague")]
    assert hooks[0]["kind"] == "mutual_connection"
    assert hooks[0]["evidence"][0]["quote"].startswith("Chloé Martin, Corvane Capital. My colleague Margaux")
    assert "Reasons to write" in prompts["hallwise_next_moves"]
    assert "- margot-lefevre: Chloé's colleague" in prompts["hallwise_next_moves"]
