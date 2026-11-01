"""Hooks: reasons to reach out that the owner had forgotten, found across evenings.

A hook rests on what was said: a promise still open from an earlier evening ("I'll introduce you two on Monday"),
someone mentioning a person met later ("my colleague Margaux would want to see this"), a question left hanging
("Did Kenji ever write back?"), or a recent public fact research found, with its source.

Two kinds of finder:
- `Threads`, during a recording, with no model: when a person turns up, the open introductions and the mentions
  of them from earlier evenings, as `hook` events for the room ("Chloé's colleague · Oct 23").
- `find_hooks`, for the morning report: one Muse Spark call over the people index, every promise and mention
  across evenings, tonight's record and the research. Everything it says must cite evidence ids from the prompt;
  a hook naming a person or evidence the prompt did not contain is dropped, and the quotes come from the logs,
  never from the model.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .events import fold_record, read_events
from .extract import LLM, _STR, _STR_LIST, _obj, slug
from .people import index_key_of, match, people_index, person_key

HOOK_TYPES = ("introduction", "mutual_connection", "open_thread", "timely")
MAX_HOOKS = 8
MAX_LINES = 400

RELATIONS = ("colleague", "co-founder", "cofounder", "partner", "business partner", "boss", "manager", "friend",
             "cto", "ceo", "investor", "advisor", "sister", "brother", "wife", "husband")


def name_sound(name: str) -> str:
    """A first name as it sounds, so a transcriber's spelling still matches: Margot and Margaux, Julien and
    Julian come out close. Accents go, silent French endings go, doubled letters collapse."""
    n = unicodedata.normalize("NFKD", name.lower())
    n = "".join(c for c in n if c.isalpha() and not unicodedata.combining(c))
    for a, b in (("eaux", "o"), ("aux", "o"), ("eau", "o"), ("au", "o"), ("ph", "f"), ("y", "i")):
        n = n.replace(a, b)
    if len(n) > 3:
        n = re.sub(r"[tdsx]$", "", n)
    return re.sub(r"(.)\1+", r"\1", n)


def same_first_name(a: str, b: str) -> bool:
    fa, fb = (a.split() or [""])[0], (b.split() or [""])[0]
    if not fa or not fb:
        return False
    sa, sb = name_sound(fa), name_sound(fb)
    if sa == sb:
        return True
    if min(len(sa), len(sb)) < 4:
        return False
    import difflib

    return difflib.SequenceMatcher(None, sa, sb).ratio() >= 0.8


def day(started: Any, tz: str = "") -> str:
    """'Oct 23' in the owner's zone."""
    try:
        ts = float(started)
    except (TypeError, ValueError):
        return ""
    if tz:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            d = datetime.fromtimestamp(ts, ZoneInfo(tz))
            return f"{d:%b} {d.day}"
        except Exception:
            pass
    return time.strftime("%b %-d", time.localtime(ts))


@dataclass
class Evening:
    rid: str
    meta: dict[str, Any]
    record: dict[str, Any]
    index_keys: dict[str, str]  # record key -> people index key
    speakers: dict[str, str]  # speaker key -> name ("Eric" for the owner)
    turns: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def started(self) -> float:
        return float(self.meta.get("started", 0) or 0)

    @property
    def event(self) -> str:
        return self.meta.get("event", "") or "an evening"

    def name(self, key: str) -> str:
        if key == "owner":
            return self.meta.get("owner_name", "") or "the owner"
        for p in self.record.get("people", []):
            if p.get("key") == key:
                return p.get("name", key)
        return key

    def said_by(self, turn: int) -> str:
        t = self.turns.get(turn)
        if t is None:
            return ""
        return self.speakers.get(f"{t.get('session', 1)}:{t.get('speaker') or '?'}", "someone")

    def quote(self, turn: int) -> str:
        t = self.turns.get(turn)
        return str(t.get("text", "")).strip() if t else ""


def load_evenings(data: Path, upto: str | None = None) -> list[Evening]:
    """Every recording that started no later than `upto` (all of them without it), oldest first."""
    root = data / "recordings"
    if not root.exists():
        return []
    out: list[Evening] = []
    for meta_path in root.glob("*/meta.json"):
        meta = json.loads(meta_path.read_text())
        meta.setdefault("id", meta_path.parent.name)
        record = fold_record(read_events(meta_path.parent / "events.jsonl"))
        speakers = {s: p.get("name", p["key"]) for p in record["people"] for s in p.get("speakers", [])}
        for s in record.get("owner_speakers", []):
            speakers[s] = meta.get("owner_name", "") or "the owner"
        out.append(Evening(
            rid=meta["id"], meta=meta, record=record,
            index_keys={p["key"]: index_key_of(p) for p in record["people"]},
            speakers=speakers, turns={t["turn"]: t for t in record["turns"] if "turn" in t},
        ))
    out.sort(key=lambda e: e.started)
    if upto is not None:
        mine = next((e for e in out if e.rid == upto), None)
        if mine is not None:
            out = [e for e in out if e.started <= mine.started]
    return out


# --- during a recording, no model ------------------------------------------------------------------------------

THANKED = re.compile(r"thanks? (you )?for (the )?intro|for introducing", re.I)


class Threads:
    """Open introductions and mentions from earlier evenings, ready to meet the people they are about."""

    def __init__(self, evenings: list[Evening], tz: str = ""):
        self.tz = tz
        self.intros: list[dict[str, Any]] = []
        self.mentions: list[dict[str, Any]] = []
        for i, ev in enumerate(evenings):
            for q in ev.record.get("promises", []):
                what = str(q.get("what", ""))
                if q.get("owed_by") != "owner" or not re.search(r"introduc|\bintro\b|connect you", what, re.I):
                    continue
                owed_to = ev.name(q.get("owed_to", ""))
                turn = (q.get("evidence_turns") or [None])[-1]
                intro = {
                    "recording": ev.rid, "event": ev.event, "started": ev.started, "promise_key": q.get("key", ""),
                    "owed_to": owed_to, "owed_to_key": ev.index_keys.get(q.get("owed_to", ""), ""), "what": what,
                    "due": q.get("due", ""), "turn": turn, "quote": ev.quote(turn) if turn is not None else "",
                }
                # A thank-you for the introduction, at a later evening, from either side, closes it.
                sides = [owed_to] + re.findall(r"[^\W\d_]+", what)
                if any(
                    THANKED.search(str(t.get("text", ""))) and any(same_first_name(e.said_by(n), s) for s in sides)
                    for e in evenings[i + 1:] for n, t in e.turns.items()
                ):
                    continue
                self.intros.append(intro)
            for m in ev.record.get("mentions", []):
                if m.get("by") in ("", "owner"):
                    continue
                self.mentions.append({
                    "recording": ev.rid, "event": ev.event, "started": ev.started, "name": m.get("name", ""),
                    "by": ev.name(m.get("by", "")), "by_key": ev.index_keys.get(m.get("by", ""), ""),
                    "turn": m.get("turn"), "quote": ev.quote(m.get("turn")),
                })

    @classmethod
    def load(cls, data: Path, exclude: str | None = None, before: float | None = None, tz: str = "") -> "Threads":
        evenings = [e for e in load_evenings(data) if e.rid != exclude and (before is None or e.started < before)]
        return cls(evenings, tz=tz)

    def for_person(self, name: str, company: str, record_key: str) -> list[dict[str, Any]]:
        """The `hook` events for someone who just turned up: strongest first, at most two."""
        out: list[dict[str, Any]] = []
        first = (name.split() or [""])[0]
        if not first:
            return out
        me = person_key(name, company)
        for q in self.intros:
            words = re.findall(r"[^\W\d_]+", q["what"])
            subject = any(same_first_name(w, first) for w in words)
            owed = q["owed_to_key"] == me or (same_first_name(q["owed_to"], name) and not company)
            if not (subject or owed):
                continue
            other = (q["owed_to"].split() or [""])[0]
            when = day(q["started"], self.tz)
            named = next((w for w in words if w[:1].isupper() and w not in ("I", "You")), "")
            if subject:
                title = f"you owe {other} an intro · {when}"
            else:
                title = f"you owe {first} an intro" + (f" to {named}" if named else "") + f" · {when}"
            out.append(self._hook(record_key, "introduction", title, q,
                                  f"At the {q['event']} on {when} you promised {q['owed_to']}: “{q['what']}”"
                                  + (f", due {q['due']}" if q["due"] else "") + "."))
        for m in self.mentions:
            if not same_first_name(m["name"], first) or same_first_name(m["by"], first):
                continue
            by_first = (m["by"].split() or [""])[0]
            when = day(m["started"], self.tz)
            rel = next((r for r in RELATIONS if re.search(rf"\bmy {r}\s+{re.escape(m['name'])}", m["quote"], re.I)), "")
            title = f"{by_first}'s {rel} · {when}" if rel else f"{by_first} mentioned {first} · {when}"
            out.append(self._hook(record_key, "mutual_connection", title, m,
                                  f"{m['by']} at the {m['event']} on {when}: “{m['quote']}”"))
        out.sort(key=lambda h: (h["type"] != "introduction", "'s " not in h["title"]))
        return out[:2]

    @staticmethod
    def _hook(record_key: str, type: str, title: str, src: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "person_key": record_key, "type": type, "title": title, "tag": title, "reason": reason,
            "promise_key": src.get("promise_key", ""),
            "evidence": [{"recording": src["recording"], "event": src["event"], "turn": src["turn"], "quote": src["quote"]}],
        }


# --- the morning report, one model call -----------------------------------------------------------------------

HOOK_SCHEMA: dict[str, Any] = _obj(
    hooks={
        "type": "array",
        "items": _obj(
            type={"type": "string", "enum": list(HOOK_TYPES)},
            people={**_STR_LIST, "description": "person keys from People; the person to write to first"},
            title={**_STR, "description": "under 10 words"},
            tag={**_STR, "description": "2-6 words shown under the first person's name in the room, e.g. \"Chloé's colleague · Oct 23\", \"you owe Lena an intro\""},
            reason={**_STR, "description": "one sentence: who said or promised what, where, when"},
            evidence={**_STR_LIST, "description": "evidence ids: E.. transcript lines, R.. research findings"},
            promise_key={**_STR, "description": "the promise this rests on, from Promises; empty if none"},
            language={**_STR, "description": "the draft's language: the language the first person spoke with the owner (People shows it when not English), else English"},
            draft={**_STR, "description": "the message to send: always for an introduction, else only when the first person has no draft ready tonight; else empty"},
            draft_english={**_STR, "description": "the draft in English; empty when the draft is English or empty"},
        ),
    },
)

HOOK_SYSTEM = """You are the assistant of the person who wore the badge (the owner). It is the morning after an
evening of networking. Find the reasons to reach out that he may have forgotten: hooks, from the people he met across
evenings, what they said and what was promised. You get the people, every promise and mention across the evenings,
the transcript lines (E ids) and research from public sources (R ids).

Kinds:
- introduction: the owner promised to introduce two people, and no later line shows them connected. A thank-you
  for the introduction, or both saying they are in touch, closes it; a later question about it ("Did Kenji ever
  write back?") or a new promise to pass something on keeps it open: cite those lines too. Both people go in people.
- mutual_connection: someone the owner met at one evening mentioned, by name, a person he met at a different
  evening ("my colleague Margaux would want to see this"). A mention links two people only when the text says so:
  the name must match (allow transcription spellings such as Margot/Margaux or Julian/Julien) and nothing may
  contradict it, such as a different company. Say "colleague" only when the line says colleague. When only a first
  name matches, the reason says "likely". Never link people because they share a company or an evening.
- open_thread: an earlier promise between the owner and someone that is still open, or a question left hanging
  ("Did Kenji ever write back?"). A promise a later line shows done is not a hook. Tonight's own promises are not
  hooks by themselves; they already have drafts. A thread becomes a hook when an earlier evening adds a reason.
- timely: a recent public fact from research (R ids) about the person or their company. Only from research.

Rules:
- Only from the evidence given. Every hook cites the evidence ids it rests on; never invent names, dates, quotes,
  relations or facts. Use the people keys exactly as listed.
- people: the person met most recently first (someone from tonight when there is one), then the others it ties in.
- Hooks that touch someone met tonight come first. Then up to three open threads from earlier evenings that touch
  nobody from tonight, the most overdue first.
- title: under 10 words. tag: the shortest form, for the room, from the owner's side ("you owe Lena an intro · Oct 20",
  "Chloé's colleague · Oct 23").
- reason: one sentence naming who said or promised what, at which event, on which day.
- draft: for an introduction, always the message that introduces the two, to both, in English unless they share
  another language. Otherwise only when the first person has no draft ready tonight (People shows "draft ready"):
  a message ready to send to them, 2-4 sentences, in their language when People shows one (the language they
  spoke with the owner), else English. Sign with the owner's first name only. A draft says only what the lines
  say: the promise, the mention, the question. Never claim how someone reacted, what was decided, or that
  something was sent. It may use research only as given. Otherwise empty.
- edge (on a People line): what that person said not to the owner, translated. A draft may act on it (a
  one-pager, the numbers first), never quote it or let on that it was heard.
- At most 8 hooks, strongest first. No hook is better than a weak one."""


@dataclass
class HookContext:
    rid: str
    meta: dict[str, Any]
    record: dict[str, Any]
    prompt: str
    people: dict[str, dict[str, Any]]  # index key -> person
    tonight: dict[str, str]  # index key -> tonight's record key
    evidence: dict[str, dict[str, Any]]  # id -> what it points at
    promises: dict[str, dict[str, Any]]  # promise key -> promise
    drafted: set[str]  # index keys with a next_move tonight


def build_hook_context(
    data: Path, rid: str, research: list[dict[str, Any]] | None = None, moves: list[dict[str, Any]] | None = None
) -> HookContext:
    evenings = load_evenings(data, upto=rid)
    tonight = next((e for e in evenings if e.rid == rid), None)
    if tonight is None:
        raise KeyError(rid)
    tz = tonight.meta.get("tz", "")
    owner = tonight.meta.get("owner_name", "") or "the owner"

    # People: the index as it stood before tonight, plus tonight's people under the key they had before (the
    # same match the live recording used), so one person has one key across evenings.
    known = [e for e in people_index(data, exclude=rid) if any(x["started"] < tonight.started for x in e["encounters"])]
    for e in known:
        e["encounters"] = [x for x in e["encounters"] if x["started"] < tonight.started]
        e["promises"] = [x for x in e["promises"] if x["started"] < tonight.started]
    people: dict[str, dict[str, Any]] = {e["key"]: {**e, "tonight": ""} for e in known}
    index_of: dict[str, str] = {}
    for p in tonight.record.get("people", []):
        if not slug(p.get("name", "")):
            continue
        entry = match(known, p.get("name", ""), p.get("company", ""))
        ik = entry["key"] if entry else index_key_of(p)
        index_of[p["key"]] = ik
        people.setdefault(ik, {"key": ik, "name": p.get("name", ""), "company": p.get("company", ""), "role": p.get("role", ""),
                               "language": p.get("preferred_language", ""), "encounters": [], "promises": []})
        people[ik]["tonight"] = p["key"]
        # How they spoke with the owner tonight wins over an earlier evening's (which may have come from an aside).
        people[ik]["language"] = p.get("preferred_language", "")
        people[ik]["edges"] = [e.get("text", "") for e in tonight.record.get("edges", []) if e.get("person") == p["key"] and e.get("text")]
    tonight.index_keys.update(index_of)
    drafted = {index_of.get(m.get("person_key", ""), m.get("person_key", "")) for m in (moves or [])}
    drafted_promises = {m.get("promise_key", "") for m in (moves or [])}

    # Evidence: every conversation line of every evening up to tonight, by id.
    evidence: dict[str, dict[str, Any]] = {}
    line_id: dict[tuple[str, int], str] = {}
    lines: list[str] = []
    for ev in evenings:
        kinds = ev.record.get("turn_kinds", {})
        when = day(ev.started, tz)
        for t in ev.record.get("turns", []):
            if kinds.get(t["turn"], "conversation") != "conversation" or not str(t.get("text", "")).strip():
                continue
            eid = f"E{len(evidence) + 1}"
            who = ev.said_by(t["turn"])
            evidence[eid] = {"kind": "turn", "recording": ev.rid, "event": ev.event, "day": when, "turn": t["turn"],
                             "speaker": who, "quote": str(t["text"]).strip()}
            line_id[(ev.rid, t["turn"])] = eid
            label = "tonight" if ev.rid == rid else f"{ev.event} ({when})"
            line = f"{eid} | {label} | {who}: {str(t['text']).strip()}"
            tr = ev.record.get("translations", {}).get(t["turn"])
            if tr and tr.get("english"):
                line += f"  (English: {tr['english']})"
            lines.append(line)
    if len(lines) > MAX_LINES:
        lines = lines[-MAX_LINES:]

    def ids(ev: Evening, turns: list[Any]) -> str:
        found = [line_id[(ev.rid, t)] for t in turns if (ev.rid, t) in line_id]
        return ", ".join(found) or "none"

    def who(ev: Evening, key: str) -> str:
        if key == "owner":
            return owner
        ik = ev.index_keys.get(key, key)
        p = people.get(ik)
        return f"{p['name']} [{ik}]" if p else ev.name(key)

    promises: dict[str, dict[str, Any]] = {}
    promise_lines: list[str] = []
    mention_lines: list[str] = []
    for ev in evenings:
        label = "tonight" if ev.rid == rid else f"{ev.event} ({day(ev.started, tz)})"
        for q in ev.record.get("promises", []):
            promises[q["key"]] = {**q, "recording": ev.rid, "event": ev.event}
            promise_lines.append(
                f"- {q['key']} | {label} | {who(ev, q.get('owed_by', ''))} owes {who(ev, q.get('owed_to', ''))}: {q.get('what', '')}"
                + (f" | due: {q['due']}" if q.get("due") else "")
                + (f" (was {q['replaces']})" if q.get("replaces") else "")
                + (" | draft ready" if ev.rid == rid and q["key"] in drafted_promises else "")
                + f" | evidence: {ids(ev, q.get('evidence_turns') or [])}"
            )
        for m in ev.record.get("mentions", []):
            mention_lines.append(f"- {label} | {who(ev, m.get('by', ''))} said the name “{m.get('name', '')}” | evidence: {ids(ev, [m.get('turn')])}")

    research_lines: list[str] = []
    for r in research or []:
        head = f"- {r.get('name', '')}, {r.get('company', '')}: {r.get('status', 'no_public_record')}"
        if not r.get("findings"):
            research_lines.append(head + " (nothing found)")
            continue
        research_lines.append(head)
        for f in r["findings"]:
            if not f.get("source"):
                continue  # research without a source never reaches a draft
            rid_ = f"R{sum(1 for k in evidence if k.startswith('R')) + 1}"
            evidence[rid_] = {"kind": "research", "person": r.get("key", ""), "name": r.get("name", ""),
                              "quote": f.get("text", ""), "source": f["source"]}
            research_lines.append(f"  {rid_} | {f.get('kind', '')}: {f.get('text', '')} (source: {f['source']})")

    def person_line(p: dict[str, Any]) -> str:
        met = [f"{x.get('event') or 'an evening'} ({day(x.get('started'), tz)})" for x in sorted(p["encounters"], key=lambda x: x["started"])]
        if p.get("tonight"):
            met.append("tonight")
        return (
            f"- {p['key']} | {p.get('name', '')}" + (f", {p['company']}" if p.get("company") else "")
            + (f", {p['role']}" if p.get("role") else "")
            + f" | met: {'; '.join(met) or 'never (only mentioned)'}"
            + (f" | language: {p['language']}" if p.get("language") else "")
            + (" | draft ready tonight" if p["key"] in drafted else "")
            + "".join(f" | edge: {text}" for text in p.get("edges") or [])
        )

    prompt = "\n".join([
        f"Owner: {owner}" + (f", from {tonight.meta['owner_company']}" if tonight.meta.get("owner_company") else ""),
        f"Tonight: {tonight.event}" + (f", {tonight.meta['venue']}" if tonight.meta.get("venue") else "") + f" ({day(tonight.started, tz)})",
        "",
        "People (key | name | where met):",
        *(person_line(p) for p in people.values()),
        "",
        "Promises across evenings (done only if a later line says so):",
        *(promise_lines or ["- none"]),
        "",
        "Mentions across evenings (a name someone said):",
        *(mention_lines or ["- none"]),
        "",
        "Research (public sources; the only facts from outside the transcript you may use):",
        *(research_lines or ["- none"]),
        "",
        "Transcript lines (conversation only, every evening up to tonight):",
        *lines,
    ])
    return HookContext(rid=rid, meta=tonight.meta, record=tonight.record, prompt=prompt, people=people,
                       tonight={ik: rk for rk, ik in index_of.items()}, evidence=evidence, promises=promises,
                       drafted=drafted)


def clean_hooks(raw: dict[str, Any], ctx: HookContext) -> list[dict[str, Any]]:
    """The model's hooks, keeping only what the prompt backs: known people, known evidence (expanded from the
    logs, not the model), a known promise, and research with a source behind every timely hook."""
    by_record = {rk: ik for ik, rk in ctx.tonight.items()}
    out: list[dict[str, Any]] = []
    for h in raw.get("hooks", []) or []:
        if h.get("type") not in HOOK_TYPES:
            continue
        people: list[str] = []
        for k in h.get("people", []) or []:
            k = slug(str(k))
            k = by_record.get(k, k)
            if k not in ctx.people:
                people = []
                break
            if k not in people:
                people.append(k)
        if not people:
            continue  # someone the prompt never mentioned
        ids = [str(e).strip().upper() for e in h.get("evidence", []) or []]
        if not ids or any(e not in ctx.evidence for e in ids):
            continue  # evidence the prompt never contained
        evidence = [{**ctx.evidence[e], "id": e} for e in dict.fromkeys(ids)]
        if h["type"] == "timely" and not any(e["kind"] == "research" and e.get("source") for e in evidence):
            continue  # timely only from research with a source
        title = " ".join(str(h.get("title", "")).split()[:10]).strip()
        if not title:
            continue
        promise = slug(str(h.get("promise_key", "")))
        draft = str(h.get("draft", "")).strip()
        out.append({
            "type": h["type"],
            "people": people,
            "names": [ctx.people[k]["name"] for k in people],
            "record_keys": {k: ctx.tonight[k] for k in people if k in ctx.tonight},
            "title": title,
            "tag": " ".join(str(h.get("tag", "")).split()[:8]).strip() or title,
            "reason": str(h.get("reason", "")).strip(),
            "evidence": evidence,
            "promise_key": promise if promise in ctx.promises else "",
            "language": str(h.get("language", "")).strip() or (ctx.people[people[0]].get("language") or "English"),
            "draft": draft,
            "draft_english": str(h.get("draft_english", "")).strip() if draft else "",
        })
    return out[:MAX_HOOKS]


async def find_hooks(
    llm: LLM, data: Path, rid: str, research: list[dict[str, Any]] | None = None, moves: list[dict[str, Any]] | None = None
) -> tuple[list[dict[str, Any]], HookContext]:
    ctx = build_hook_context(data, rid, research, moves)
    raw = await llm(HOOK_SYSTEM, ctx.prompt, schema=HOOK_SCHEMA, name="hallwise_hooks")
    return clean_hooks(raw, ctx), ctx
