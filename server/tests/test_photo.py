import asyncio

from hallwise.photo import PHOTO_SCHEMA, build_photo_prompt, match_photo


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
