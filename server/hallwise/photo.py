"""One photo, everyone gets a face.

The owner takes a photo of the people they are talking to. Muse Spark looks at it together with who is around
the badge right now and where each voice came from, and says which face is which. The phone crops the faces
onto the cards; the owner confirms with a tap.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

from .extract import LLM, _STR, _obj, slug

PHOTO_SCHEMA: dict[str, Any] = _obj(
    faces={
        "type": "array",
        "items": _obj(
            index={"type": "integer", "description": "0 for the leftmost face, then rightwards"},
            box={"type": "array", "items": {"type": "number"}, "description": "x0, y0, x1, y1 around the head, as fractions of the image width and height"},
            person_key={**_STR, "description": "the person this most likely is, from the list; empty when nobody fits"},
            confidence={"type": "number"},
            why={**_STR, "description": "one short reason: position, a name tag, the hint"},
        ),
    },
    notes={**_STR, "description": "anything the owner should know, e.g. a face that matches nobody; else empty"},
)

PHOTO_SYSTEM = """You match the people in a photo to the people the badge wearer has been talking to.

You get the photo, taken with the phone's back camera from where the wearer stands; the list of people around
the wearer right now, each with where their voice came from (bearing in degrees: 0 is straight ahead, positive
is to the wearer's left, which is the left side of the photo, negative is to the right); and sometimes a hint
from the wearer.

Rules:
- One entry per visible face, left to right, with a tight box around the head as fractions of the image.
- Match by order and position first: a voice from the left is a face on the left. A visible name tag or the
  hint beats position.
- Use a person_key only from the list, never invented; leave it empty when nobody fits. One person, one face.
- confidence is how sure you are of the match, 0 to 1.
- Say nothing about appearance beyond what the box needs."""


def build_photo_prompt(people: list[dict[str, Any]], hint: str) -> str:
    ordered = sorted(people, key=lambda p: -float(p.get("bearing", 0)))  # leftmost first
    lines = [
        "People around the wearer, with the bearing of their voice:",
        *(
            f"- {p['key']} | {p.get('name', '')}" + (f", {p['company']}" if p.get("company") else "")
            + f" | bearing {float(p.get('bearing', 0)):.0f}°"
            for p in people
        ),
        "",
        "Expected order in the photo, left to right, from the bearings: " + ", ".join(p.get("name", p["key"]) for p in ordered),
        "Hint from the wearer: " + (hint or "none"),
    ]
    return "\n".join(lines)


async def match_photo(
    llm: LLM, image_b64: str, mime: str, people: list[dict[str, Any]], hint: str = ""
) -> dict[str, Any]:
    result = await llm(PHOTO_SYSTEM, build_photo_prompt(people, hint), schema=PHOTO_SCHEMA, name="hallwise_photo", images=[(mime, image_b64)])
    known = {p["key"] for p in people}
    faces = []
    for f in sorted(result.get("faces", []), key=lambda f: f.get("index", 0)):
        box = [max(0.0, min(1.0, float(v))) for v in (f.get("box") or [0, 0, 0, 0])[:4]]
        if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
            continue
        key = slug(f.get("person_key", ""))
        faces.append({
            "index": len(faces), "box": box, "person_key": key if key in known else "",
            "confidence": max(0.0, min(1.0, float(f.get("confidence", 0)))), "why": f.get("why", ""),
        })
    return {"faces": faces, "notes": result.get("notes", "")}


def save_photo(root: Path, image_b64: str, mime: str) -> str:
    """Keep the original under the recording; returns the file name."""
    ext = {"image/png": "png", "image/heic": "heic"}.get(mime, "jpg")
    (root / "photos").mkdir(parents=True, exist_ok=True)
    name = time.strftime("%H%M%S") + "." + ext
    (root / "photos" / name).write_bytes(base64.b64decode(image_b64))
    return name
