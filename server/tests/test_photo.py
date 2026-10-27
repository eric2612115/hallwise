import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from auth import AUTH
from pictures import picture_b64

from hallwise.photo import FACE_PHRASE, MATCH_SCHEMA, PHOTO_SCHEMA, TAG_PHRASE, build_photo_prompt, match_photo
from hallwise.sam import parse_boxes


def test_photo_prompt_orders_people_left_to_right_by_bearing():
    people = [{"key": "kenji", "name": "Kenji", "bearing": -30}, {"key": "margo", "name": "Margo", "bearing": 40}]
    text = build_photo_prompt(people, "")
    assert "left to right, from the bearings: Margo, Kenji" in text


def test_match_photo_keeps_only_known_keys_and_sane_boxes():
    seen = {}

    async def llm(system, user, schema=None, name="", images=None):
        seen["images"] = images
        seen["schema"] = schema
        return {"faces": [
            {"index": 1, "box": [0.6, 0.1, 0.8, 0.4], "person_key": "Kenji", "confidence": 0.9, "why": "right side"},
            {"index": 0, "box": [0.1, 0.1, 0.3, 0.4], "person_key": "nobody-here", "confidence": 0.5, "why": "?"},
            {"index": 2, "box": [0.9, 0.5, 0.8, 0.4], "person_key": "margo", "confidence": 0.5, "why": "bad box"},
        ], "notes": ""}

    people = [{"key": "kenji", "name": "Kenji", "bearing": -30}, {"key": "margo", "name": "Margo", "bearing": 40}]
    out = asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", people))
    assert seen["images"] == [("image/jpeg", "aGVsbG8=")]
    assert seen["schema"] is PHOTO_SCHEMA
    assert [f["person_key"] for f in out["faces"]] == ["", "kenji"]  # left to right; unknown key dropped; bad box gone
    assert out["faces"][1]["index"] == 1


# --- SAM finds, Spark matches -------------------------------------------------------------------------------

PEOPLE = [
    {"key": "margo-lefebvre-corvane-capital", "name": "Margo Lefebvre", "company": "Corvane Capital", "bearing": 40},
    {"key": "kenji-watanabe-hoshizora-robotics", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "bearing": -30},
]
MARGO, KENJI = PEOPLE[0]["key"], PEOPLE[1]["key"]
RIGHT_FACE = [0.65, 0.37, 0.80, 0.52]
LEFT_FACE = [0.20, 0.37, 0.35, 0.52]
LEFT_TAG = [0.18, 0.54, 0.37, 0.62]


def fake_sam(faces=None, tags=None, fail=None):
    """A SAM that answers by phrase, the way the real one returns them: not left to right."""
    calls = []

    async def sam(image_b64, mime, phrase):
        calls.append((image_b64, mime, phrase))
        if fail and phrase in fail:
            raise httpx.HTTPStatusError("503", request=httpx.Request("POST", "https://x"), response=httpx.Response(503))
        if phrase == FACE_PHRASE:
            return [{"box": b, "score": 0.95} for b in (faces if faces is not None else [RIGHT_FACE, LEFT_FACE])]
        if phrase == TAG_PHRASE:
            return [{"box": b, "score": 0.95} for b in (tags if tags is not None else [LEFT_TAG])]
        return []

    sam.calls = calls
    return sam


def fake_spark(matches, notes=""):
    seen = []

    async def llm(system, user, schema=None, name="", images=None):
        seen.append({"system": system, "user": user, "schema": schema, "images": images})
        if schema is MATCH_SCHEMA:
            return {"matches": matches, "notes": notes}
        return {"faces": [  # Spark-only: Spark's own boxes
            {"index": 0, "box": [0.1, 0.1, 0.3, 0.4], "person_key": MARGO, "confidence": 0.7, "why": "left"},
            {"index": 1, "box": [0.6, 0.1, 0.8, 0.4], "person_key": KENJI, "confidence": 0.7, "why": "right"},
        ], "notes": "spark found them"}

    llm.seen = seen
    return llm


def test_sam_boxes_come_back_left_to_right_and_spark_only_says_who_is_who():
    sam = fake_sam()
    llm = fake_spark([
        {"face": 1, "person_key": "Kenji Watanabe-Hoshizora Robotics", "confidence": 0.8, "why": "right, voice from the right"},
        {"face": 0, "person_key": MARGO, "confidence": 0.9, "why": "name tag reads Margo", "box": [0, 0, 1, 1]},
    ], notes="")
    out = asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", PEOPLE, "", sam=sam))

    assert out["finder"] == "sam"
    assert [f["box"] for f in out["faces"]] == [LEFT_FACE, RIGHT_FACE]  # SAM's boxes, sorted; Spark's "box" ignored
    assert [f["index"] for f in out["faces"]] == [0, 1]
    assert [f["person_key"] for f in out["faces"]] == [MARGO, KENJI]
    assert out["faces"][0]["why"] == "name tag reads Margo"
    assert set(out["faces"][0]) == {"index", "box", "person_key", "confidence", "why"}  # what the phone reads
    assert sorted(c[2] for c in sam.calls) == sorted([FACE_PHRASE, TAG_PHRASE])
    assert all(c[:2] == ("aGVsbG8=", "image/jpeg") for c in sam.calls)
    (call,) = llm.seen
    assert call["schema"] is MATCH_SCHEMA and "box" not in MATCH_SCHEMA["properties"]["matches"]["items"]["properties"]
    assert call["images"] == [("image/jpeg", "aGVsbG8=")]
    # Spark is told the numbered faces left to right and that the tag sits under face 0.
    assert "face 0: 0.200, 0.370, 0.350, 0.520" in call["user"] and "face 1: 0.650" in call["user"]
    assert "tag at 0.180, 0.540, 0.370, 0.620, under face 0" in call["user"]
    assert "Margo Lefebvre, Kenji Watanabe" in call["user"]  # bearings still in the prompt


def test_sam_path_drops_unknown_keys_bad_face_numbers_and_a_second_claim_on_one_person():
    sam = fake_sam(faces=[RIGHT_FACE, [0.42, 0.40, 0.50, 0.50], LEFT_FACE], tags=[])
    llm = fake_spark([
        {"face": 0, "person_key": "nobody-here", "confidence": 0.9, "why": "tag says Priya"},
        {"face": 1, "person_key": KENJI, "confidence": 0.4, "why": "middle"},
        {"face": 2, "person_key": KENJI, "confidence": 0.8, "why": "right"},
        {"face": 7, "person_key": MARGO, "confidence": 0.9, "why": "no such face"},
    ])
    out = asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", PEOPLE, "", sam=sam))
    assert out["finder"] == "sam"
    assert [f["box"] for f in out["faces"]] == [LEFT_FACE, [0.42, 0.40, 0.50, 0.50], RIGHT_FACE]
    assert [f["person_key"] for f in out["faces"]] == ["", "", KENJI]  # surest claim on Kenji wins; face 7 ignored
    assert out["faces"][0] == {"index": 0, "box": LEFT_FACE, "person_key": "", "confidence": 0.0, "why": "tag says Priya"}
    assert "Name tags found (read them in the photo):\n- none" in llm.seen[0]["user"]


def test_spark_finds_the_faces_when_sam_raises():
    sam = fake_sam(fail={FACE_PHRASE})
    llm = fake_spark([])
    out = asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", PEOPLE, "", sam=sam))
    assert out["finder"] == "spark"
    assert [f["box"] for f in out["faces"]] == [[0.1, 0.1, 0.3, 0.4], [0.6, 0.1, 0.8, 0.4]]  # Spark's own boxes
    assert [f["person_key"] for f in out["faces"]] == [MARGO, KENJI]
    assert out["notes"] == "spark found them"
    assert llm.seen[0]["schema"] is PHOTO_SCHEMA


def test_spark_finds_the_faces_when_sam_finds_none():
    llm = fake_spark([])
    out = asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", PEOPLE, "", sam=fake_sam(faces=[])))
    assert out["finder"] == "spark" and len(out["faces"]) == 2
    assert [c["schema"] for c in llm.seen] == [PHOTO_SCHEMA]


def test_spark_only_without_sam_says_so():
    out = asyncio.run(match_photo(fake_spark([]), "aGVsbG8=", "image/jpeg", PEOPLE))
    assert out["finder"] == "spark"


def test_a_failed_name_tag_search_still_uses_sams_faces():
    sam = fake_sam(fail={TAG_PHRASE})
    llm = fake_spark([{"face": 0, "person_key": MARGO, "confidence": 0.9, "why": "left"}])
    out = asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", PEOPLE, "", sam=sam))
    assert out["finder"] == "sam"
    assert [f["person_key"] for f in out["faces"]] == [MARGO, ""]
    assert "- none" in llm.seen[0]["user"]


def test_a_tag_worn_off_centre_by_someone_turning_still_finds_its_face():
    # From the photo-real test image: tags sit lower and off to the side of faces turned towards each other.
    faces = [[0.2063, 0.2375, 0.3422, 0.5180], [0.5526, 0.1875, 0.6760, 0.4930], [0.9396, 0.2484, 0.9854, 0.4023]]
    tags = [[0.6422, 0.7180, 0.7188, 0.8148], [0.3208, 0.7094, 0.3964, 0.8039]]
    llm = fake_spark([])
    asyncio.run(match_photo(llm, "aGVsbG8=", "image/jpeg", PEOPLE, "", sam=fake_sam(faces=faces, tags=tags)))
    prompt = llm.seen[0]["user"]
    assert "tag at 0.321, 0.709, 0.396, 0.804, under face 0" in prompt
    assert "tag at 0.642, 0.718, 0.719, 0.815, under face 1" in prompt


def test_parse_boxes_reads_sams_tokens_with_inclusive_corners():
    # Recorded from SAM 3.1 on the stand-in photo (mask payloads shortened).
    text = (
        "<0f>0<|box;x1=1570;y1=585;x2=1908;y2=839;w=2400;h=1600;c=0.9532163739204407|>"
        "<|mask;x=0;y=0;c=0.9532163739204407;data=255,339,!!!!$JGzDVb0|>,"
        "1<|box;x1=491;y1=585;x2=828;y2=838;w=2400;h=1600;c=0.949367105960846|>"
        "<|mask;x=0;y=0;c=0.949367105960846;data=254,338,!!!!$AGAp_#J|>\n"
    )
    found = parse_boxes(text)
    assert [round(v, 4) for v in found[1]["box"]] == [round(491 / 2400, 4), round(585 / 1600, 4), round(829 / 2400, 4), round(839 / 1600, 4)]
    assert found[0]["score"] == pytest.approx(0.9532, abs=1e-4)
    assert parse_boxes("") == [] and parse_boxes("<0f>0<|box;x1=5;y1=5;x2=5;y2=5;w=0;h=0|>") == []


def test_the_photo_endpoint_passes_sam_and_records_the_finder(tmp_path, monkeypatch):
    import hallwise.app as app_module

    class FakeSam:
        def __init__(self, key):
            self.call = fake_sam()

        async def __call__(self, image_b64, mime, phrase):
            return await self.call(image_b64, mime, phrase)

    class FakeSpark:
        def __init__(self, key, model=""):
            self.call = fake_spark([{"face": 1, "person_key": KENJI, "confidence": 0.8, "why": "right"}])

        async def __call__(self, *args, **kwargs):
            return await self.call(*args, **kwargs)

    monkeypatch.setenv("MODEL_API_KEY", "key")
    monkeypatch.setattr(app_module, "SamClient", FakeSam)
    monkeypatch.setattr(app_module, "SparkClient", FakeSpark)
    root = tmp_path / "recordings" / "r1"
    root.mkdir(parents=True)
    (root / "meta.json").write_text(json.dumps({"id": "r1", "started": time.time()}))  # tonight's: it takes photos
    body = {"image_b64": picture_b64(), "mime": "image/jpeg", "people": PEOPLE}

    client = TestClient(app_module.create_app(tmp_path, asr="fake", make_extractor=None), headers=AUTH)
    out = client.post("/api/recordings/r1/photo", json=body).json()
    assert out["finder"] == "sam" and [f["box"] for f in out["faces"]] == [LEFT_FACE, RIGHT_FACE]
    assert [f["person_key"] for f in out["faces"]] == ["", KENJI]
    monkeypatch.setenv("HALLWISE_SAM", "off")
    client = TestClient(app_module.create_app(tmp_path, asr="fake", make_extractor=None), headers=AUTH)
    assert client.post("/api/recordings/r1/photo", json=body).json()["finder"] == "spark"

    photos = [e for e in map(json.loads, (root / "events.jsonl").read_text().splitlines()) if e["type"] == "photo"]
    assert [e["finder"] for e in photos] == ["sam", "spark"]
    assert photos[0]["faces"] == out["faces"]
