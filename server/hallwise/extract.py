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
from datetime import datetime, timedelta
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
    translations={
        "type": "array",
        "items": _obj(
            turn={"type": "integer"},
            language={**_STR, "description": "the non-English language in this turn, e.g. 'Japanese'"},
            english={**_STR, "description": "the whole turn in English"},
        ),
    },
    room_topics={**_STR_LIST, "description": "short topics from ambient speech only; never names or quotes"},
)

NEXT_SCHEMA: dict[str, Any] = _obj(
    moves={
        "type": "array",
        "items": _obj(
            promise_key=_STR,
            person_key={**_STR, "description": "who the move goes to"},
            kind={"type": "string", "enum": ["message", "email", "calendar", "nudge"]},
            language={**_STR, "description": "language of body, e.g. 'Japanese' or 'English'"},
            subject={**_STR, "description": "email subject; empty for other kinds"},
            body={**_STR, "description": "the message, ready to send, in `language`"},
            body_english={**_STR, "description": "the same message in English; empty when body is English"},
            when={**_STR, "description": "calendar kinds: proposed start, ISO 8601 with the owner's offset; else empty"},
            duration_minutes={"type": "integer"},
            attach={**_STR, "description": "'deck', 'one_pager', 'blurb' or '' — only ones the owner has"},
            why={**_STR, "description": "one line: why this move, and for calendar what the time avoids"},
            remind_at={**_STR, "description": "ISO 8601 with the owner's offset: when to remind the owner if this is still not sent; empty if no due"},
            nudge={**_STR, "description": "the reminder line, under 10 words, e.g. 'Deck for Kevin is due tonight'"},
        ),
    },
)

NEXT_SYSTEM = """You are the assistant of the person who wore the badge (the owner). The event is over; write the
follow-ups. You get the record of the conversations: people, promises, the transcript, the owner's busy windows for
the coming week, and which links the owner can share.

Write exactly one move per promise:
- A promise the owner owes becomes a message to that person, ready to send: 2-4 sentences, warm and specific.
  Name the thing promised and one concrete detail from what was said. No padding ("I hope this finds you well").
  When a due date was agreed ("by Friday"), say so. Never invent facts, prices, names or dates.
- Attachments and products: say what is attached or shown, never what it contains. Do not describe the contents of
  a deck, one-pager, link, demo or product, or what it "includes", "covers" or "shows", beyond what was said in the
  transcript: "the deck includes the face-photo flow" when nobody said so is an invented fact.
- Earlier meetings: mention one only when it is listed for that same person, under their own key in "Met before"
  (their People line repeats it), and name it as listed. Never borrow another person's earlier meetings, and never
  take one from what someone else said in the transcript: when one guest says "we met at Blockchain Week", that is
  where the owner met that guest, not the person standing next to him. A person whose line says "met before: none"
  gets no mention of any earlier meeting.
- Reasons to write: when a person has one listed (someone who mentioned them at an earlier evening, an
  introduction the owner still owes, a question left open), the message may use it in one natural clause, in the
  message's language ("Chloé told me you'd want to see this"; "and the introduction to Lena I still owe you").
  Use only what the reason and its quote say; never add a relation, a reaction or a fact it does not give.
- A promise owed to the owner becomes kind "nudge": a short, friendly reminder the owner can send a few days later.
- body is in the person's preferred_language when one is set, else English. body_english is the same message in
  English, empty when body is already English. language names the language of body.
- kind "calendar" when the promise is to meet, call, visit or demo. Pick a specific start from the owner's free
  time: never inside a busy window, weekdays 10:00-18:00 in the owner's zone unless the conversation said
  otherwise, at least one day after now, on the agreed day when one was agreed. Read days from "Days ahead":
  "Friday" is the first Friday after today; "next week" is the week that starts on the Monday marked there, so
  "next week, Wednesday" is the Wednesday of that week, not this one. 30 minutes unless stated. Put it
  in `when` as ISO 8601 with the owner's offset; body is the invitation message; why says what the slot avoids.
- kind "email" when the promise is to send a document, deck, link or introduction; fill subject.
- attach: "deck" when the promise is about slides, a deck or a pitch; "one_pager" for a one-pager, overview or
  intro document; "blurb" when they asked for a short bio or intro text; else "". Use only links the owner has.
  Do not paste the link into body; the phone adds it.
- remind_at: when to nudge the owner if the move is still not sent. "tonight" → 20:00 today; "tomorrow" →
  10:00 tomorrow; a named day → 09:00 that day; a meeting → 09:00 the day before; no due → empty. nudge is the
  notification line: what, to whom, by when, under ten words.
- Sign off with the owner's first name only."""


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
- preferred_language: a language the person spoke other than English (an aside, a murmur, a phrase), or one
  they asked for; follow-ups go in that language. Empty if they only spoke English.
- translations: one entry for every turn that is partly or wholly not in English, with the whole turn in
  English. People mutter to themselves in their own language mid-conversation; that is still conversation.
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


def build_prompt(
    turns: list[Turn], owner_name: str, owner_company: str, vocabulary: list[str], known: list[str] | None = None
) -> str:
    lines = [
        f"Owner: {owner_name or 'unknown'}" + (f", from {owner_company}" if owner_company else ""),
        "Vocabulary (names and terms the owner has confirmed before): " + (", ".join(vocabulary) or "none"),
        "People the owner has met at earlier events (use these spellings when one of them turns up): "
        + ("; ".join(known) if known else "none"),
        "",
        "Transcript:",
        *(t.line() for t in turns),
    ]
    return "\n".join(lines)


LLM = Callable[..., Awaitable[dict[str, Any]]]  # (system, user, schema=..., name=...) -> JSON matching the schema


def build_next_prompt(
    record: dict[str, Any],
    *,
    owner_name: str,
    owner_company: str,
    event: str = "",
    venue: str = "",
    now: str = "",
    tz: str = "",
    busy: list[list[str]] | None = None,
    links: dict[str, str] | None = None,
) -> str:
    translations = record.get("translations", {})
    kinds = record.get("turn_kinds", {})
    # a provisional "met before" (a name heard, not yet confirmed by Muse Spark) never reaches a draft
    history = {k: h for k, h in record.get("history", {}).items() if not h.get("provisional")}

    def met(h: dict[str, Any]) -> str:
        return "; ".join(
            (e.get("event") or "an earlier evening") + (f" ({_day(e.get('started'))})" if e.get("started") else "")
            for e in h.get("encounters", [])
        )

    hook_lines = [
        f"- {key}: {h.get('title', '')}" + (f" | {h['reason']}" if h.get("reason") else "")
        + "".join(f" | “{e.get('quote', '')}”" for e in (h.get("evidence") or [])[:2] if e.get("quote"))
        for key, hooks in (record.get("hooks") or {}).items() for h in hooks
        if key in {p["key"] for p in record.get("people", [])}
    ] or ["- none"]
    met_lines = [
        f"- {key}" + (f" ({h['name']})" if h.get("name") else "") + ": " + met(h) + (
            " | earlier promises: " + "; ".join(
                f"{q.get('what', '')}" + (f" ({q.get('due')})" if q.get("due") else "") for q in h.get("promises", [])
            ) if h.get("promises") else ""
        )
        for key, h in history.items()
    ] or ["- none"]
    lines = [
        f"Owner: {owner_name or 'unknown'}" + (f", from {owner_company}" if owner_company else ""),
        f"Now: {now or 'unknown'}" + (f" ({tz})" if tz else ""),
        *_days_ahead(now),
        "Event: " + (", ".join(x for x in (event, venue) if x) or "unknown"),
        "Owner busy (ISO ranges): " + ("; ".join(f"{a} to {b}" for a, b in (busy or [])) or "none"),
        "Owner can share: " + (", ".join(sorted(k for k, v in (links or {}).items() if v)) or "nothing"),
        "",
        "People:",
        *(
            f"- {p['key']} | {p.get('name', '')}, {p.get('company', '')}"
            + (f", {p['role']}" if p.get("role") else "")
            + f" | preferred_language: {p.get('preferred_language') or 'not set'}"
            + f" | met before: {met(history[p['key']]) if p['key'] in history and history[p['key']].get('encounters') else 'none'}"
            for p in record.get("people", [])
        ),
        "",
        "Promises:",
        *(
            f"- {q['key']} | owed_by: {q.get('owed_by', '')} | owed_to: {q.get('owed_to', '')} | what: {q.get('what', '')}"
            + (f" | due: {q['due']}" if q.get("due") else "")
            + (f" | replaces: {q['replaces']}" if q.get("replaces") else "")
            + f" | turns: {', '.join(str(t) for t in q.get('evidence_turns', []))}"
            for q in record.get("promises", [])
        ),
        "",
        "Met before (earlier evenings with the owner, per person; a follow-up may refer to that person's own, and only those):",
        *met_lines,
        "",
        "Reasons to write (from earlier evenings, per person key; use one only for that person):",
        *hook_lines,
        "",
        "Transcript (conversation turns):",
    ]
    for t in record.get("turns", []):
        if kinds.get(t["turn"], "conversation") != "conversation":
            continue
        line = f"turn {t['turn']} [{t.get('speaker', '?')}]: {t.get('text', '')}"
        tr = translations.get(t["turn"])
        if tr:
            line += f"  (English: {tr.get('english', '')})"
        lines.append(line)
    return "\n".join(lines)


def _days_ahead(now: str) -> list[str]:
    """Today and the next 13 days with their weekdays, and where next week starts: models miscount weekdays."""
    try:
        today = datetime.fromisoformat(now).date()
    except (TypeError, ValueError):
        return []
    days = [today + timedelta(days=i) for i in range(14)]
    monday = today + timedelta(days=7 - today.weekday())
    return [
        "Days ahead: " + ", ".join(
            d.strftime("%a %Y-%m-%d") + (" (today)" if d == today else "") + (" (next week starts)" if d == monday else "")
            for d in days
        )
    ]


def _day(started: Any) -> str:
    try:
        return time.strftime("%b %-d", time.localtime(float(started)))
    except (TypeError, ValueError):
        return ""


async def draft_next_moves(llm: LLM, record: dict[str, Any], **context: Any) -> list[dict[str, Any]]:
    """One ready-to-send move per promise, from Muse Spark; keys normalised, attachments limited to what exists."""
    if not record.get("promises"):
        return []
    result = await llm(NEXT_SYSTEM, build_next_prompt(record, **context), schema=NEXT_SCHEMA, name="hallwise_next_moves")
    have = {k for k, v in (context.get("links") or {}).items() if v}
    known = {q["key"] for q in record["promises"]}
    moves = []
    for m in result.get("moves", []):
        m = dict(m)
        m["promise_key"] = slug(m.get("promise_key", ""))
        m["person_key"] = slug(m.get("person_key", ""))
        if m["promise_key"] not in known:
            continue
        if m.get("attach") not in have:
            m["attach"] = ""
        m["duration_minutes"] = int(m.get("duration_minutes") or 30)
        moves.append(m)
    return moves


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

    async def __call__(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] = SCHEMA,
        name: str = "hallwise_record",
        images: list[tuple[str, str]] | None = None,  # (mime, base64)
    ) -> dict[str, Any]:
        content: Any = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}} for mime, b64 in images
            ]
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
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
        self.known: list[str] = []  # "Name, Company" of people met at earlier events
        self.turns: list[Turn] = []
        self.state: dict[str, Any] = {}

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    async def run(self) -> list[tuple[str, int, dict[str, Any]]]:
        """Run Muse Spark on the transcript so far; return (type, t_ms, data) for everything new or changed."""
        if not self.turns:
            return []
        turns = list(self.turns)
        result = await self.llm(SYSTEM, build_prompt(turns, self.owner_name, self.owner_company, self.vocabulary, self.known))
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

        # Each run is the whole picture, so anything the new run no longer lists is withdrawn: the model may
        # merge two people, rename a promise's key, or drop a suspect word once a name is confirmed.
        for section, event, ident, id_fields in (
            ("people", "person", lambda x: x["key"], ("key",)),
            ("promises", "promise", lambda x: x["key"], ("key",)),
            ("mentioned", "mention", lambda x: x["name"].lower(), ("name", "turn")),
            ("suspect_words", "suspect_word", lambda x: (x["heard"].lower(), x["turn"]), ("heard", "turn")),
            ("translations", "translation", lambda x: x["turn"], ("turn",)),
        ):
            before = {ident(x): x for x in old.get(section, [])}
            after = {ident(x): x for x in new.get(section, [])}
            for key, item in after.items():
                previous = before.get(key)
                if previous != item:
                    out.append((event, t_ms, {**item, "new": previous is None}))
            for key, item in before.items():
                if key not in after:
                    out.append((f"{event}_removed", t_ms, {f: item[f] for f in id_fields}))

        if new.get("room_topics", []) != old.get("room_topics", []):
            out.append(("room_topics", t_ms, {"topics": list(new.get("room_topics", []))}))
        return out
