"""One photo, everyone gets a face.

The owner takes a photo of the people they are talking to. SAM 3.1 finds the faces and the name tags in it; Muse
Spark looks at the photo with those numbered boxes, who is around the badge right now and where each voice came
from, and says which face is which. The boxes the phone draws and crops are SAM's. When SAM is not there, fails
or finds no face, Spark finds the faces itself as well (`finder` says which ran). The phone crops the faces onto
the cards; the owner confirms with a tap.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Any

from .extract import LLM, _STR, _obj, slug
from .sam import Finder

log = logging.getLogger(__name__)

# SAM noun phrases, picked on test photos: "head" keeps the hair but also finds slivers of heads at the edges;
# "badge" found no name tag.
FACE_PHRASE = "face"
TAG_PHRASE = "name tag"

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

MATCH_SCHEMA: dict[str, Any] = _obj(
    matches={
        "type": "array",
        "items": _obj(
            face={"type": "integer", "description": "the face's number from the list of faces found"},
            person_key={**_STR, "description": "the person this face most likely is, from the list; empty when nobody fits"},
            confidence={"type": "number"},
            why={**_STR, "description": "one short reason: a name tag, position, the hint"},
        ),
    },
    notes={**_STR, "description": "anything the owner should know, e.g. a face that matches nobody; else empty"},
)

MATCH_SYSTEM = """You match the people in a photo to the people the badge wearer has been talking to.

You get the photo, taken with the phone's back camera from where the wearer stands; the faces in it, already
found and numbered left to right, each with its box as fractions of the image width and height; the name tags
found in it, with the face each one sits under; the list of people around the wearer right now, each with where
their voice came from (bearing in degrees: 0 is straight ahead, positive is to the wearer's left, which is the
left side of the photo, negative is to the right); and sometimes a hint from the wearer.

Rules:
- Say which numbered face is which person, one entry per face. Use only the face numbers given; do not look for
  other faces and do not give boxes.
- A name tag you can read under a face beats position, and so does the hint. Otherwise match by order and
  position: a voice from the left is a face on the left.
- Use a person_key only from the list, never invented; leave it empty when nobody fits. One person, one face.
- confidence is how sure you are of the match, 0 to 1.
- why is one short reason. Say nothing about appearance."""


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


def tag_owner(tag: list[float], faces: list[dict[str, Any]]) -> int | None:
    """The face a name tag sits under, or None. A tag is worn on the chest, so its top is below the middle of the
    face and within three face heights of the chin; people turn, so its middle may be up to a face width off the
    face's middle. Of the faces that fit, the nearest."""
    cx = (tag[0] + tag[2]) / 2
    best, best_cost = None, 0.0
    for i, f in enumerate(faces):
        x0, y0, x1, y1 = f["box"]
        fw, fh = x1 - x0, y1 - y0
        dx, gap = abs(cx - (x0 + x1) / 2), tag[1] - y1
        if dx > fw or tag[1] < (y0 + y1) / 2 or gap > 3 * fh:
            continue
        cost = dx / fw + max(0.0, gap) / fh
        if best is None or cost < best_cost:
            best, best_cost = i, cost
    return best


def build_match_prompt(
    faces: list[dict[str, Any]], tags: list[dict[str, Any]], people: list[dict[str, Any]], hint: str
) -> str:
    def box(b: list[float]) -> str:
        return ", ".join(f"{v:.3f}" for v in b)

    lines = [
        "Faces found, numbered left to right (x0, y0, x1, y1):",
        *(f"- face {i}: {box(f['box'])}" for i, f in enumerate(faces)),
        "",
        "Name tags found (read them in the photo):",
        *(
            f"- tag at {box(t['box'])}" + (f", under face {t['under']}" if t["under"] is not None else ", under no face")
            for t in tags
        ),
        *(["- none"] if not tags else []),
        "",
        build_photo_prompt(people, hint),
    ]
    return "\n".join(lines)


async def find_faces(sam: Finder, image_b64: str, mime: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """SAM's faces, left to right, and name tags, each tagged with the face it sits under. No faces when SAM fails;
    no tags when only the tag search fails."""
    faces, tags = await asyncio.gather(
        sam(image_b64, mime, FACE_PHRASE), sam(image_b64, mime, TAG_PHRASE), return_exceptions=True
    )
    if isinstance(faces, BaseException):
        log.warning("SAM face search failed, Spark finds the faces: %r", faces)
        return [], []
    if isinstance(tags, BaseException):
        log.warning("SAM name tag search failed: %r", tags)
        tags = []
    if not faces:
        log.info("SAM found no face, Spark finds the faces")
    faces = sorted(faces, key=lambda f: (f["box"][0] + f["box"][2]) / 2)
    tags = sorted(tags, key=lambda t: (t["box"][0] + t["box"][2]) / 2)
    return faces, [{**t, "under": tag_owner(t["box"], faces)} for t in tags]


def _unit(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


async def match_photo(
    llm: LLM, image_b64: str, mime: str, people: list[dict[str, Any]], hint: str = "", sam: Finder | None = None
) -> dict[str, Any]:
    if sam is not None:
        faces, tags = await find_faces(sam, image_b64, mime)
        if faces:
            return await match_found(llm, image_b64, mime, people, hint, faces, tags)
    return await match_by_spark(llm, image_b64, mime, people, hint)


async def match_found(
    llm: LLM, image_b64: str, mime: str, people: list[dict[str, Any]], hint: str,
    faces: list[dict[str, Any]], tags: list[dict[str, Any]],
) -> dict[str, Any]:
    """Spark says which of SAM's numbered faces is which person; the boxes stay SAM's."""
    result = await llm(
        MATCH_SYSTEM, build_match_prompt(faces, tags, people, hint),
        schema=MATCH_SCHEMA, name="hallwise_photo_match", images=[(mime, image_b64)],
    )
    known = {p["key"] for p in people}
    matched: dict[int, dict[str, Any]] = {}
    said: dict[int, str] = {}
    taken: set[str] = set()
    for m in sorted(result.get("matches", []), key=lambda m: -_unit(m.get("confidence"))):  # surest claim wins
        try:
            i = int(m.get("face", -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(faces):
            continue
        said.setdefault(i, m.get("why", ""))
        key = slug(m.get("person_key", ""))
        if i in matched or key not in known or key in taken:
            continue
        matched[i] = {"person_key": key, "confidence": _unit(m.get("confidence")), "why": m.get("why", "")}
        taken.add(key)
    out = [
        {"index": i, "box": [round(v, 4) for v in f["box"]],
         **matched.get(i, {"person_key": "", "confidence": 0.0, "why": said.get(i, "")})}
        for i, f in enumerate(faces)
    ]
    return {"faces": out, "notes": result.get("notes", ""), "finder": "sam"}


async def match_by_spark(llm: LLM, image_b64: str, mime: str, people: list[dict[str, Any]], hint: str) -> dict[str, Any]:
    """Spark alone: it finds the faces, estimates their boxes and matches them."""
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
    return {"faces": faces, "notes": result.get("notes", ""), "finder": "spark"}


def save_photo(root: Path, image_b64: str, mime: str) -> str:
    """Keep the original under the recording; returns the file name."""
    ext = {"image/png": "png", "image/heic": "heic"}.get(mime, "jpg")
    (root / "photos").mkdir(parents=True, exist_ok=True)
    name = time.strftime("%H%M%S") + "." + ext
    (root / "photos" / name).write_bytes(base64.b64decode(image_b64))
    return name
