"""Who is who, what was promised, which words look misheard — from the transcript, with Muse Spark.

Each run sends the whole transcript so far (it fits easily) and gets back the full current picture as JSON
constrained by SCHEMA. `Extractor` compares it with the previous picture and emits only what is new or changed,
so the dashboard sees people appear and promises change as the conversation goes.

Speaker keys are "<session>:<label>" because Muse Voice Transcribe restarts its labels in every session.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

SPARK_URL = "https://api.meta.ai/v1/chat/completions"

_STR = {"type": "string"}
_INT_LIST = {"type": "array", "items": {"type": "integer"}}
_STR_LIST = {"type": "array", "items": _STR}


def _obj(**props: Any) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props)}


SCHEMA: dict[str, Any] = _obj(
    owner_speakers=_STR_LIST,
    turns={
        "type": "array",
        "items": _obj(
            turn={"type": "integer"},
            kind={"type": "string", "enum": ["conversation", "incidental", "ambient", "stage", "noise"]},
        ),
    },
    people={
        "type": "array",
        "items": _obj(
            key={**_STR, "description": "stable id: lowercase name and company, e.g. 'sarah-acme'"},
            name=_STR,
            company=_STR,
            role=_STR,
            speakers={**_STR_LIST, "description": "speaker keys this person spoke as"},
            preferred_language={**_STR, "description": "language they want follow-ups in; empty if unknown"},
            introduced_by={**_STR, "description": "person key or 'owner' who sent them; empty if none"},
            evidence_turns=_INT_LIST,
        ),
    },
    mentioned={
        "type": "array",
        "items": _obj(name=_STR, by={**_STR, "description": "person key or 'owner'"}, turn={"type": "integer"}),
    },
    promises={
        "type": "array",
        "items": _obj(
            key={**_STR, "description": "stable id, e.g. 'deck-to-sarah-acme'"},
            owed_by={**_STR, "description": "'owner' or a person key"},
            owed_to={**_STR, "description": "'owner' or a person key"},
            what=_STR,
            due={**_STR, "description": "as finally agreed, e.g. 'tonight', 'Friday'; empty if none"},
            replaces={**_STR, "description": "what it said before a correction, e.g. 'Thursday'; empty if none"},
            evidence_turns=_INT_LIST,
        ),
    },
    suspect_words={
        "type": "array",
        "items": _obj(
            heard=_STR,
            turn={"type": "integer"},
            likely={**_STR, "description": "the word it most likely should be"},
            reason=_STR,
        ),
    },
    room_topics={**_STR_LIST, "description": "short topics from ambient speech only; never names or quotes"},
)

SYSTEM = """You read a live transcript from a badge worn at a networking event and keep a precise record for the
person wearing it (the owner).

The transcript has numbered turns with a speaker key ("<session>:<label>"). Labels come from automatic speaker
separation: they are not names, and a label can be wrong at the edges.

Rules:
- Name people only from what is said: self-introductions ("I'm Sarah from Acme"), being addressed by name, a
  spelled-out name. Never guess a name. A person may speak under more than one speaker key.
- The owner introduces himself with the name and company given below. List his speaker keys in owner_speakers
  and never put him in people.
- kind of each turn: conversation = part of an exchange with the owner; incidental = small talk aimed at no one in
  particular or at staff ("thanks", "excuse me", "something to drink?"); ambient = other people's conversations
  the owner is not part of; stage = an announcement or speaker addressing the room; noise = not speech.
- Only conversation turns may create people, promises or mentions. Ambient turns only feed room_topics, as short
  topics with no names and no quotes.
- A promise is a commitment to do something later. When someone corrects it ("Thursday — no, Friday"), keep one
  promise with the final version in due and the earlier one in replaces.
- preferred_language: the language a person asks to be written to in, or clearly prefers; empty if not stated.
- suspect_words: words the transcriber probably got wrong, mainly names, companies and product terms.
  - A word close to one in the vocabulary below is a suspect; likely = the vocabulary word.
  - When the same name appears in two spellings (for example a self-introduction and someone addressing that
    person), list each spelling as a suspect with likely = the other spelling. Do not decide which one is right.
  - A name that looks split or garbled (a surname heard as two short words, an odd spelling of a common name) is a
    suspect even when you cannot tell the right spelling; likely = your best guess.
  - In people, use the spelling from the person's own introduction.
- Never infer accent, nationality, ethnicity or personality.
- Every person and promise must cite the turns it comes from. Keep keys stable between runs."""


@dataclass
class Turn:
    turn: int
    speaker: str  # "<session>:<label>"
    start_ms: int
    end_ms: int
    text: str

    def line(self) -> str:
        def mmss(ms: int) -> str:
            return f"{ms // 60000}:{ms // 1000 % 60:02d}.{ms // 100 % 10}"

        return f"turn {self.turn} [{self.speaker}] {mmss(self.start_ms)}-{mmss(self.end_ms)}: {self.text}"


def build_prompt(turns: list[Turn], owner_name: str, owner_company: str, vocabulary: list[str]) -> str:
    lines = [
        f"Owner: {owner_name or 'unknown'}" + (f", from {owner_company}" if owner_company else ""),
        "Vocabulary (names and terms the owner has confirmed before): " + (", ".join(vocabulary) or "none"),
        "",
        "Transcript:",
        *(t.line() for t in turns),
    ]
    return "\n".join(lines)


LLM = Callable[[str, str], Awaitable[dict[str, Any]]]  # (system, user) -> JSON matching SCHEMA


def slug(text: str) -> str:
    """'Kenji Watanabe-Hoshizora Robotics' -> 'kenji-watanabe-hoshizora-robotics'; 'owner' stays 'owner'."""
    return "-".join(re.findall(r"[0-9a-z]+", text.lower()))


def normalize_keys(result: dict[str, Any]) -> dict[str, Any]:
    """Make every key and every reference to a key a plain slug, the same way, so references keep matching."""
    for person in result.get("people", []):
        person["key"] = slug(person["key"])
        person["introduced_by"] = slug(person["introduced_by"])
    for promise in result.get("promises", []):
        for field in ("key", "owed_by", "owed_to"):
            promise[field] = slug(promise[field])
    for mention in result.get("mentioned", []):
        mention["by"] = slug(mention["by"])
    return result


class SparkClient:
    """Muse Spark over the Chat Completions endpoint, with JSON-schema-constrained output."""

    def __init__(self, api_key: str, model: str = "muse-spark-1.3", effort: str = "low", timeout: float = 90):
        self.api_key = api_key
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.last_usage: dict[str, Any] = {}
        self.last_seconds = 0.0

    async def __call__(self, system: str, user: str) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "hallwise_record", "schema": SCHEMA}},
            "reasoning_effort": self.effort,
        }
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(SPARK_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        self.last_seconds = time.monotonic() - started
        response.raise_for_status()
        data = response.json()
        self.last_usage = data.get("usage") or {}
        return json.loads(data["choices"][0]["message"]["content"])


class Extractor:
    """Keeps the latest picture of a recording and turns each new run into events."""

    def __init__(self, llm: LLM, owner_name: str = "", owner_company: str = "", vocabulary: list[str] | None = None):
        self.llm = llm
        self.owner_name = owner_name
        self.owner_company = owner_company
        self.vocabulary = vocabulary or []
        self.turns: list[Turn] = []
        self.state: dict[str, Any] = {}

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    async def run(self) -> list[tuple[str, int, dict[str, Any]]]:
        """Run Muse Spark on the transcript so far; return (type, t_ms, data) for everything new or changed."""
        if not self.turns:
            return []
        turns = list(self.turns)
        result = await self.llm(SYSTEM, build_prompt(turns, self.owner_name, self.owner_company, self.vocabulary))
        return self.diff(normalize_keys(result), t_ms=turns[-1].end_ms)

    def diff(self, new: dict[str, Any], t_ms: int) -> list[tuple[str, int, dict[str, Any]]]:
        old = self.state
        self.state = new
        out: list[tuple[str, int, dict[str, Any]]] = []

        if sorted(new.get("owner_speakers", [])) != sorted(old.get("owner_speakers", [])):
            out.append(("owner", t_ms, {"speakers": sorted(new.get("owner_speakers", []))}))

        old_kinds = {t["turn"]: t["kind"] for t in old.get("turns", [])}
        for t in new.get("turns", []):
            if old_kinds.get(t["turn"]) != t["kind"]:
                out.append(("turn_kind", t_ms, {"turn": t["turn"], "kind": t["kind"]}))

        for section, event, ident in (
            ("people", "person", lambda x: x["key"]),
            ("promises", "promise", lambda x: x["key"]),
            ("mentioned", "mention", lambda x: x["name"].lower()),
            ("suspect_words", "suspect_word", lambda x: (x["heard"].lower(), x["turn"])),
        ):
            before = {ident(x): x for x in old.get(section, [])}
            for item in new.get(section, []):
                previous = before.get(ident(item))
                if previous != item:
                    out.append((event, t_ms, {**item, "new": previous is None}))

        old_topics = set(old.get("room_topics", []))
        for topic in new.get("room_topics", []):
            if topic not in old_topics:
                out.append(("room_topic", t_ms, {"topic": topic}))
        return out
