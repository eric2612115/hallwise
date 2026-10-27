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
- Names and companies: spell them as the People lines do, never as the transcript heard them; "Spellings the owner
  corrected" lists what the transcriber got wrong.
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
- When the prompt names the owner's voice (a speaker key the badge hears from just above, where his mouth is), that
  key is the owner whatever is said in it: list it in owner_speakers. A commitment spoken under it is owed_by
  "owner"; one made to it is owed_to "owner".
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
  - Never offer a known person's name for someone with a different first name at a different company: "I'm Ken from
    Vexi" is not a mishearing of Kenji Watanabe from Hoshizora Robotics, it is someone else. A mishearing sounds the
    same ("Margot" for Margaux) or splits one name ("Raghoo Nathan" for Raghunathan).
  - Spellings the owner corrected are settled: write the right one everywhere and never list them as suspects.
    A suggestion the owner rejected is never listed again.
  - In people, use the spelling from the person's own introduction, unless the owner corrected that person: then
    keep the key and use exactly the owner's name and company.
- Never infer accent, nationality, ethnicity or personality.
- Every person and promise must cite the turns it comes from. Keep keys stable between runs."""


@dataclass
class Turn:
    turn: int
    speaker: str  # "<session>:<label>"
    start_ms: int
    end_ms: int
    text: str

    def line(self, who: str = "") -> str:
        def mmss(ms: int) -> str:
            return f"{ms // 60000}:{ms // 1000 % 60:02d}.{ms // 100 % 10}"

        label = f"{self.speaker}, {who}" if who else self.speaker
        return f"turn {self.turn} [{label}] {mmss(self.start_ms)}-{mmss(self.end_ms)}: {self.text}"


def owner_label(owner_name: str) -> str:
    """How the owner's own voice is marked in the transcript: "Eric (owner)"."""
    return f"{owner_name or 'the owner'} (owner)"


def spelling_pairs(*groups: list[dict[str, str]]) -> list[tuple[str, str]]:
    """(heard, right) pairs from lists of {heard, use}, each heard word once (the last word on it wins)."""
    out: dict[str, tuple[str, str]] = {}
    for group in groups:
        for w in group or []:
            heard, use = str(w.get("heard", "")).strip(), str(w.get("use", "")).strip()
            if heard and use and heard.casefold() != use.casefold():
                out.pop(heard.casefold(), None)
                out[heard.casefold()] = (heard, use)
    return list(out.values())


def build_prompt(
    turns: list[Turn],
    owner_name: str,
    owner_company: str,
    vocabulary: list[str],
    known: list[str] | None = None,
    wearer: str = "",
    *,
    spellings: list[dict[str, str]] | None = None,
    rejected: list[dict[str, str]] | None = None,
    corrections: dict[str, dict[str, Any]] | None = None,
) -> str:
    """`wearer`: the speaker key the badge hears from just above, the owner's own voice (direction.Wearer), or "".
    `spellings` ({heard, use}), `rejected` ({heard, likely}) and `corrections` (person key -> {name, company}) are
    what the owner fixed on the phone (corrections.py); each adds its line only when there is something in it."""
    who = owner_label(owner_name)
    pairs = spelling_pairs(spellings or [])
    lines = [
        f"Owner: {owner_name or 'unknown'}" + (f", from {owner_company}" if owner_company else ""),
        *(
            [f"Owner's voice: speaker {wearer}, which the badge hears from just above it, where the owner's mouth is; "
             f"its turns are marked [{wearer}, {who}]. Whatever is said under {wearer}, the owner says it."]
            if wearer else []
        ),
        "Vocabulary (names and terms the owner has confirmed before): " + (", ".join(vocabulary) or "none"),
        *(
            ["Spellings the owner corrected (heard -> right; the transcript may still have the heard one): "
             + "; ".join(f"{h} -> {u}" for h, u in pairs)] if pairs else []
        ),
        *(
            ["Suggestions the owner rejected (never list these as suspect words): "
             + "; ".join(f"{r.get('heard', '')} -> {r.get('likely', '')}" for r in rejected)] if rejected else []
        ),
        *(
            ["People the owner corrected (keep each key; use exactly this name and company): "
             + "; ".join(f"{key} is {c.get('name', '')}" + (f", from {c['company']}" if c.get("company") else "")
                         for key, c in corrections.items())] if corrections else []
        ),
        "People the owner has met at earlier events (use these spellings when one of them turns up): "
        + ("; ".join(known) if known else "none"),
        "",
        "Transcript:",
        *(t.line(who if wearer and t.speaker == wearer else "") for t in turns),
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
    spellings: list[dict[str, str]] | None = None,
) -> str:
    """`spellings`: the owner's vocabulary ({heard, use}); this recording's own word corrections and every corrected
    person's heard name and company join it, so a draft never repeats what the transcriber misheard."""
    translations = record.get("translations", {})
    kinds = record.get("turn_kinds", {})
    heard = [
        {"heard": p.get(f"heard_{f}", ""), "use": p.get(f, "")}
        for p in record.get("people", []) if p.get("corrected") for f in ("name", "company")
    ]
    pairs = spelling_pairs(spellings or [], record.get("spellings") or [], heard)
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
        *(
            ["Spellings the owner corrected (heard -> right; the transcript may still have the heard one, always write "
             "the right one): " + "; ".join(f"{h} -> {u}" for h, u in pairs)] if pairs else []
        ),
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
        self.known_people: list[tuple[str, str]] = []  # (name, company) of the same, for corrections.refine
        # What the owner fixed on the phone (corrections.py): the vocabulary's spellings and rejected suggestions, and
        # this recording's corrected people (key -> {name, company, was}). Every run's prompt and result hold them.
        self.spellings: list[dict[str, str]] = []
        self.rejected: list[dict[str, str]] = []
        self.corrections: dict[str, dict[str, Any]] = {}
        self.turns: list[Turn] = []
        self.state: dict[str, Any] = {}
        # The speaker key the badge hears from just above (direction.Wearer): the owner's own voice, measured rather
        # than read from the transcript. It joins whatever Muse Spark lists as the owner; it never replaces it.
        self.wearer = ""
        self._spark_owner: list[str] = []  # owner_speakers as Muse Spark last listed them

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    def owner_speakers(self) -> list[str]:
        return sorted(set(self._spark_owner) | ({self.wearer} if self.wearer else set()))

    def set_wearer(self, speaker: str) -> list[str]:
        """The owner's own voice, found from elevation ("" withdraws it); returns every speaker key of the owner now.
        The next run's prompt marks it as the owner; the picture so far has it at once, so no run re-announces it."""
        self.wearer = speaker
        self.state = {**self.state, "owner_speakers": self.owner_speakers()}
        return self.state["owner_speakers"]

    def prompt(self, turns: list[Turn], wearer: str | None = None) -> str:
        """The prompt for these turns, with everything the extractor knows; the second listener reads the same one."""
        return build_prompt(
            turns, self.owner_name, self.owner_company, self.vocabulary, self.known,
            self.wearer if wearer is None else wearer,
            spellings=self.spellings, rejected=self.rejected,
            corrections={k: {"name": c.get("name", ""), "company": c.get("company", "")} for k, c in self.corrections.items()},
        )

    async def run(self) -> list[tuple[str, int, dict[str, Any]]]:
        """Run Muse Spark on the transcript so far; return (type, t_ms, data) for everything new or changed."""
        if not self.turns:
            return []
        turns = list(self.turns)
        result = await self.llm(SYSTEM, self.prompt(turns))
        from .corrections import refine  # here, not at the top: corrections reads helpers that import this module

        result = refine(
            normalize_keys(result), turns=turns, corrections=self.corrections, spellings=self.spellings,
            rejected=self.rejected, known=self.known_people,
        )
        return self.diff(result, t_ms=turns[-1].end_ms)

    def diff(self, new: dict[str, Any], t_ms: int) -> list[tuple[str, int, dict[str, Any]]]:
        old = self.state
        self._spark_owner = list(new.get("owner_speakers", []))
        new["owner_speakers"] = self.owner_speakers()
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
