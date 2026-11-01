"""The connector (牽線): introductions the owner never thought of, and where to meet the right people next.

Hooks (hooks.py) find what was promised: an introduction the owner owes, a colleague someone mentioned. By design
they never invent one. The connector does the other half, after an evening, from what the people the owner has
met said about themselves, across every evening:

1. Introductions to make. Muse Spark reads each person's own lines (what they need, offer, build or plan) and
   their edges (what they said not to the owner) and proposes at most three introductions between two of them,
   toward one concrete collaboration: Kenji said on the phone tonight, in Japanese, that the badge might work for
   his robots' field logs; Ben said at the founder dinner that he is looking for a small robot arm to pilot on his
   frame line. Each side cites the lines it rests on (E ids) and quotes them; it may add what the report's research
   found about their company (R ids, each with its page), never in place of a line of theirs. `kept_proposals`
   drops a proposal whose lines do not exist, are not that person's own, or do not contain the words it quotes, and
   any pair already connected (an introduction the owner promised, one of them naming the other, the same company,
   one bringing the other). The quotes and lines shown come from the logs, never from the model; whoever said
   something tonight comes first. No proposal is better than an invented one.
2. Where to meet them next. Muse Spark with search (research.py's client; HALLWISE_RESEARCH_CORPUS gives it the
   demo's fictional web instead) looks for an event in the next fourteen days where someone matching one of those
   needs will speak or attend, and says why to go and whom to bring. `kept_events` keeps an event only when a page
   the search returned backs it: its URL among the results (research.source_for), its date written on that page
   and inside the window, the person it names on that page, and the need it serves resting on that person's own
   line. No event is better than an invented evening out.

Off unless HALLWISE_CONNECTOR=on (it needs MODEL_API_KEY too); HALLWISE_CONNECTOR_LOOKAHEAD=off keeps part 2 off.
Muse Spark runs at HALLWISE_CONNECTOR_EFFORT (medium, as the hooks do). Two calls per recording: one Chat
Completions call for the introductions, one Responses call with search for the look-ahead. Each result carries its
tokens, searches, seconds and cost, and `event` is what a recording's log keeps of a run (a `connector` event, as
`second_run` is for the edge finder). Saved as data/connector/<recording>.json; asking again returns that one.

On the rehearsed week (four evenings, plus tonight's living-room rehearsal with Kenji's call as an edge), with the
real Muse Spark: as recorded, every run proposed nothing (nobody else's words fit Kenji's); with one line added for
Ben at the founder dinner, every run proposed Kenji and Ben, and found the Nangang meetup on the demo corpus. The
introductions took 13-28 s (4,100 tokens in, 3,600-7,600 out, mostly reasoning; 53 s and 13,800 out once, looking
hard and finding nothing), the look-ahead 4-10 s (5,000 in, 900-2,100 out): $0.03-0.08 a run.

Wiring (not done here): at Stop, after the morning report (Reports.later, which already has the research), run
`Connector.run(rid, research=report["checked"])` in the same background task, log `event(result)` as a `connector`
event, and serve the result at GET /api/connector/{rid} and /api/connector/latest (the app's ConnectorView reads
them); `notice(result)` is the notification for when the owner sits down.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .extract import LLM, _STR, _STR_LIST, _obj, SparkClient, fold_words, slug
from .hooks import day, load_evenings, same_first_name
from .ids import is_rid
from .people import people_index
from .research import CorpusSearch, Search, SearchClient, _host, source_for

MAX_PROPOSALS = 3
MAX_EVENTS = 2
HORIZON_DAYS = 14
MAX_LINES = 400

INTRO = re.compile(r"introduc|\bintro\b|connect you", re.I)  # a promise to introduce
NAME_WORD = re.compile(r"[A-ZÀ-ÖØ-Þ][^\W\d_]+")  # a capitalised word: maybe a first name
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")  # scripts written without spaces between words

_SIDE = _obj(
    person={**_STR, "description": "a person key from People"},
    wants={**_STR, "description": "what they need, offer, build or plan: one short sentence in English that starts with a verb, e.g. 'Needs a small robot arm for his line', 'Builds compact robot arms'"},
    quote={**_STR, "description": "their own words that bear on it, copied exactly from one of the cited E lines: its original words, or its English as given"},
    evidence={**_STR_LIST, "description": "E ids of their own lines this rests on, and R ids of their public findings it uses"},
)

INTRO_SCHEMA: dict[str, Any] = _obj(
    proposals={
        "type": "array",
        "items": _obj(
            a=_SIDE,
            b=_SIDE,
            collaboration={**_STR, "description": "what the two could do together, one concrete line under 18 words, e.g. 'a pilot of X on Y'"},
            why={**_STR, "description": "one plain sentence, about 20 words: why these two, from what each said"},
            ask_first={**_STR, "description": "the person key to ask before making the introduction: the one whose need it is"},
            title={**_STR, "description": "under 8 words"},
        ),
    },
)

INTRO_SYSTEM = """You are the assistant of the person who wore the badge (the owner). The evening is over. Propose
introductions he has not thought of: two people he has met, ideally at different evenings, whose own words show that
one has what the other needs, or that together they could do one concrete thing (a pilot, a first customer, a
supplier, a shared test site).

You get every person he has met, with every line each of them said, across every evening (E ids). A line marked "not
to the owner" was said on the phone, to themselves or to someone else; its edge says what it shows. R ids are public
research about them, each from a page a search returned.

Rules:
- Read only what each person said themselves; what the owner or anyone else said about them is not theirs. A line
  also shows what they work on: "our robots' field logs" says their robots are out in the field. A line about the
  owner's badge is read for that, never as a need the owner meets.
- An introduction joins one side's need or plan, in their own words, to what the other side builds, offers or
  needs, from their own lines or their public findings (R ids).
- Each side: wants is what they need, offer, build or plan, in one sentence; quote is their own words that bear on
  it, copied exactly from one of their cited E lines (the original words, or the English given for that line);
  evidence is the E ids of those lines, and the R ids of any public finding the sentence uses.
- Cite the line that shows it most directly; a self-introduction alone shows nothing. What someone said tonight,
  above all what they said not to the owner, is the freshest sign of what they are working on: when a line of
  tonight's bears on the introduction, it is the one to quote, and the collaboration should answer it.
- Never assume someone is raising, hiring, buying or looking for a partner unless their own words say so. A company
  name alone is not a need; the same industry alone is not a reason.
- collaboration: one concrete thing the two could do together ("a pilot of Hoshizora's arm on Stride's frame line"),
  never "they should talk".
- Never pair two people listed under "Already connected", two from the same company, or anyone with the owner. The
  owner selling his own product to someone is not an introduction.
- ask_first: the person whose need it is; the owner checks with them before introducing anyone.
- At most three, strongest first. No proposal is better than a weak or invented one: an empty list is a good answer."""

LOOK_SCHEMA: dict[str, Any] = _obj(
    events={
        "type": "array",
        "items": _obj(
            title={**_STR, "description": "the event's name as the page gives it"},
            date={**_STR, "description": "the day the page gives, as YYYY-MM-DD"},
            time={**_STR, "description": "the start time as the page gives it, e.g. '19:00'; empty if none"},
            place={**_STR, "description": "where, as the page gives it"},
            url={**_STR, "description": "the search result this comes from, exactly as the result gave it"},
            who={**_STR, "description": "the person at the event who matches a need, named as the page names them"},
            role={"type": "string", "enum": ["speaks", "attends", "hosts", "exhibits"]},
            for_people={**_STR_LIST, "description": "person keys whose need this event serves"},
            evidence={**_STR_LIST, "description": "E ids: those people's own lines that show the need"},
            quote={**_STR, "description": "their own words that show the need, copied exactly from one of those lines (its original words, or its English as given)"},
            bring={**_STR_LIST, "description": "person keys the owner should bring along"},
            why={**_STR, "description": "one plain sentence, about 20 words, from the page and their lines: why go, and why bring them"},
        ),
    },
)

LOOK_SYSTEM = """You look ahead for the person who wore the badge (the owner). From what the people he met said they
need, offer, build or plan, find an upcoming event, inside the dates given and near his city, where someone who
matches one of those needs will speak, attend, host or exhibit: a meetup, a talk, a demo night. Search the web, at
most three searches. Report only what the search results say.

- An event is listed only when a search result shows it: its name, its date, where, and the person who matches,
  named on that page. Copy the result's url exactly; never build, guess or shorten a URL, and do not open pages.
- date: the day the page gives, as YYYY-MM-DD, and only days inside the window.
- who: the person on the page who matches the need, named as the page names them.
- for_people, evidence and quote: the people (keys) whose need it serves, the E ids of their own lines that show
  that need, and their words that show it, copied exactly. Their need is what they said; what the page says
  someone at the event wants is not a need of theirs.
- bring: whom the owner should bring along: the person whose need it serves, or someone from the proposed
  introductions who should meet the person on the page; never the person on the page.
- A line about the owner's badge counts for what it shows about their work (their robots out in the field), never
  as a need for the badge: the owner's product is his to sell, not a reason to go.
- why: one plain sentence, about 20 words, from the page and their lines: why go, and why bring them.
- At most two events, the best first. If nothing fits, return no events: an invented event costs the owner an
  evening."""


@dataclass
class Line:
    """One thing a person said, at one evening: the evidence a proposal cites by id."""

    id: str
    person: str  # the people-index key of who said it
    recording: str
    event: str
    day: str
    turn: int
    text: str
    tonight: bool = False
    english: str = ""
    language: str = ""
    aside: bool = False  # not said to the owner: on the phone, to themselves, to someone else
    edge: dict[str, Any] | None = None  # the edge resting on it, when there is one

    def prompt_line(self) -> str:
        where = "tonight" if self.tonight else f"{self.event} ({self.day})"
        lang = self.language if self.language and self.language.casefold() != "english" else ""
        line = f"{self.id} | {where}" + (" | not to the owner" if self.aside else "") + (f" | {lang}" if lang else "")
        return line + f": {self.text}" + (f"  (English: {self.english})" if self.english and self.english != self.text else "")

    def evidence(self) -> dict[str, Any]:
        out = {"id": self.id, "recording": self.recording, "event": self.event, "day": self.day, "turn": self.turn,
               "tonight": self.tonight, "quote": self.text, "english": self.english, "language": self.language,
               "aside": self.aside}
        if self.edge is not None:
            out["edge"] = {k: self.edge.get(k, "") for k in ("text", "act")}
        return out


@dataclass
class ConnectContext:
    rid: str
    meta: dict[str, Any]
    today: date
    owner: str
    city: str
    people: dict[str, dict[str, Any]]  # index key -> person, newest encounter first
    lines: dict[str, Line]  # id -> line
    connected: dict[frozenset[str], str]  # a pair already connected -> how
    research: dict[str, dict[str, Any]]  # R id -> a public finding with a source, and whose it is
    by_record: dict[str, str]  # tonight's record key -> index key

    def key(self, raw: Any) -> str:
        """A person key as the model wrote it, as the index has it: tonight's record keys count too."""
        k = slug(_s(raw))
        return self.by_record.get(k, k)

    def lines_of(self, key: str) -> list[Line]:
        return [x for x in self.lines.values() if x.person == key]

    def people_block(self) -> list[str]:
        out: list[str] = []
        for key, p in self.people.items():
            mine = self.lines_of(key)
            if not mine:
                continue  # met, but nothing they said is left: nothing to propose from
            out.append(f"- {key} | {p['name']}" + (f", {p['company']}" if p["company"] else "")
                       + (f", {p['role']}" if p["role"] else "") + f" | met: {'; '.join(p['met'])}")
            for x in mine:
                out.append("  " + x.prompt_line())
                if x.edge is not None:
                    out.append(f"    edge: {x.edge.get('text', '')}" + (f" | act: {x.edge['act']}" if x.edge.get("act") else ""))
            out += [f"  {rid} | public: {f['text']} (source: {f['source']})" for rid, f in self.research.items() if f["person"] == key]
        return out

    def connected_block(self) -> list[str]:
        return [f"- {' + '.join(sorted(pair))}: {why}" for pair, why in self.connected.items()] or ["- none"]

    def header(self) -> list[str]:
        return [
            f"Owner: {self.owner}" + (f", from {self.meta['owner_company']}" if self.meta.get("owner_company") else ""),
            f"Tonight: {self.meta.get('event') or 'an evening'}" + (f", {self.city}" if self.city else "")
            + f" ({self.today:%a %Y-%m-%d})",
        ]

    def intro_prompt(self) -> str:
        return "\n".join([
            *self.header(),
            "",
            "People, and every line each of them said (their own words only; E ids):",
            *self.people_block(),
            "",
            "Already connected (never propose these pairs):",
            *self.connected_block(),
        ])


def _s(x: Any) -> str:
    return " ".join(x.split()) if isinstance(x, str) else ""


def today_of(meta: dict[str, Any], clock: Callable[[], float] = time.time) -> date:
    """The evening's day: from the phone's `now`, else when it started, in the owner's zone."""
    try:
        return datetime.fromisoformat(str(meta.get("now") or "")).date()
    except ValueError:
        pass
    ts = float(meta.get("started") or 0) or clock()
    try:
        from zoneinfo import ZoneInfo

        return datetime.fromtimestamp(ts, ZoneInfo(meta["tz"])).date() if meta.get("tz") else datetime.fromtimestamp(ts).date()
    except Exception:
        return datetime.fromtimestamp(ts).date()


def build_context(data: Path, rid: str, research: list[dict[str, Any]] | None = None,
                  clock: Callable[[], float] = time.time) -> ConnectContext:
    """Every evening up to `rid`: each person met, under their people-index key, with every line they said (a
    conversation turn of theirs, or a turn one of their edges rests on), and the pairs already connected."""
    evenings = load_evenings(data, upto=rid)
    tonight = next((e for e in evenings if e.rid == rid), None)
    if tonight is None:
        raise KeyError(rid)
    tz = tonight.meta.get("tz", "")
    known = {e.rid for e in evenings}

    # One key per person across evenings: the people index's, found from each evening's record key.
    where: dict[tuple[str, str], str] = {}
    people: dict[str, dict[str, Any]] = {}
    for entry in people_index(data):
        mine = sorted((x for x in entry["encounters"] if x["recording"] in known), key=lambda x: x["started"])
        if not mine:
            continue
        for x in mine:
            where[(x["recording"], x["record_key"])] = entry["key"]
        people[entry["key"]] = {
            "key": entry["key"], "name": entry["name"], "company": entry["company"], "role": entry.get("role", ""),
            "met": list(dict.fromkeys("tonight" if x["recording"] == rid else f"{x['event'] or 'an evening'} ({day(x['started'], tz)})"
                                      for x in mine)),
            "evenings": list(dict.fromkeys(x["recording"] for x in mine)),
            "tonight": any(x["recording"] == rid for x in mine),
        }

    connected: dict[frozenset[str], str] = {}

    def link(a: str | None, b: str | None, why: str) -> None:
        if a and b and a != b and a in people and b in people:
            connected.setdefault(frozenset((a, b)), why)

    def first(key: str) -> str:
        return (people[key]["name"].split() or [key])[0]

    lines: dict[str, Line] = {}
    for ev in evenings:
        when = day(ev.started, tz)
        label = "tonight" if ev.rid == rid else f"{ev.event} ({when})"
        speakers = {s: p["key"] for p in ev.record.get("people", []) for s in p.get("speakers") or []}
        owner = set(ev.record.get("owner_speakers") or [])
        kinds = ev.record.get("turn_kinds", {})
        translations = ev.record.get("translations", {})
        edges: dict[int, dict[str, Any]] = {}
        for e in ev.record.get("edges", []):
            for n in e.get("turns") or []:
                edges.setdefault(n, e)
        for t in ev.record.get("turns", []):
            speaker = f"{t.get('session', 1)}:{t.get('speaker') or '?'}"
            rk = speakers.get(speaker)
            ik = where.get((ev.rid, rk or ""))
            text = str(t.get("text", "")).strip()
            if speaker in owner or not ik or not text:
                continue
            kind = kinds.get(t["turn"], "conversation")
            edge = edges.get(t["turn"])
            if edge is not None and edge.get("person") != rk:
                edge = None  # someone else's edge resting on this turn
            if kind != "conversation" and edge is None:
                continue  # small talk, the room, the stage: not what they want
            tr = translations.get(t["turn"]) or {}
            lid = f"E{len(lines) + 1}"
            lines[lid] = Line(
                id=lid, person=ik, recording=ev.rid, event=ev.event, day=when, turn=t["turn"], text=text,
                tonight=ev.rid == rid, english=str(tr.get("english") or "").strip(), language=str(tr.get("language") or ""),
                aside=edge is not None or kind != "conversation" or bool(tr.get("aside")), edge=edge,
            )
        # An introduction the owner promised is the hooks' to chase, not a new idea.
        for q in ev.record.get("promises", []):
            what = str(q.get("what", ""))
            if q.get("owed_by") != "owner" or not INTRO.search(what):
                continue
            a = where.get((ev.rid, q.get("owed_to", "")))
            for b, p in people.items():
                if any(same_first_name(w, p["name"]) for w in NAME_WORD.findall(what)):
                    link(a, b, f"the owner promised to introduce them ({label})")
        for p in ev.record.get("people", []):
            a, b = where.get((ev.rid, p.get("key", ""))), where.get((ev.rid, p.get("introduced_by", "")))
            if a and b:
                link(a, b, f"{first(b)} brought {first(a)} ({label})")
    if len(lines) > MAX_LINES:
        lines = dict(list(lines.items())[-MAX_LINES:])
    # Someone who names another already knows them, or knows of them: "You know Kenji, no?"
    for x in lines.values():
        for w in set(NAME_WORD.findall(x.text)):
            for b, p in people.items():
                if b != x.person and same_first_name(w, p["name"]):
                    link(x.person, b, f"{first(x.person)} named {first(b)} ({'tonight' if x.tonight else f'{x.event} ({x.day})'})")
    keys = list(people)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if slug(people[a]["company"]) and slug(people[a]["company"]) == slug(people[b]["company"]):
                link(a, b, f"the same company ({people[a]['company']})")

    # Research (the report's lookups): only findings with a source, under the person they are about.
    found: dict[str, dict[str, Any]] = {}
    for r in research or []:
        key = r.get("key", "")
        if key not in people:
            key = next((k for k, p in people.items() if slug(p["name"]) == slug(r.get("name", ""))), "")
        for f in r.get("findings") or [] if key else []:
            if f.get("source") and str(f.get("text", "")).strip():
                found[f"R{len(found) + 1}"] = {"person": key, "kind": str(f.get("kind", "")), "text": str(f["text"]).strip(),
                                               "source": str(f["source"])}

    place = tonight.meta.get("place") if isinstance(tonight.meta.get("place"), dict) else {}
    city = str(tonight.meta.get("venue") or place.get("name") or "")
    return ConnectContext(
        rid=rid, meta=tonight.meta, today=today_of(tonight.meta, clock),
        owner=tonight.meta.get("owner_name", "") or "the owner", city=city, people=people, lines=lines,
        connected=connected, research=found,
        by_record={rk: ik for (r, rk), ik in where.items() if r == rid},
    )


# --- the checks: nothing reaches the owner that the logs and the pages do not back ------------------------------

def quoted(quote: str, texts: list[str]) -> bool:
    """Whether `quote` is in one of `texts`, word for word (accents, case and punctuation aside): two words at
    least, or four characters of a language written without spaces (「現場ログ」 in Kenji's call)."""
    q = fold_words(quote)
    if not q:
        return False
    if CJK.search(q):
        q = q.replace(" ", "")
        return len(q) >= 4 and any(q in fold_words(t).replace(" ", "") for t in texts if t)
    return len(q.split()) >= 2 and any(f" {q} " in f" {fold_words(t)} " for t in texts if t)


def _side(raw: Any, ctx: ConnectContext) -> tuple[dict[str, Any], str]:
    """One side of a proposal as the logs have it, or why it goes."""
    raw = raw if isinstance(raw, dict) else {}
    key = ctx.key(raw.get("person"))
    if key not in ctx.people:
        return {}, f"{_s(raw.get('person')) or 'nobody'} is not someone the owner met"
    name = ctx.people[key]["name"]
    ids = list(dict.fromkeys(str(e).strip().upper() for e in raw.get("evidence") or [] if str(e).strip()))
    public = [e for e in ids if e in ctx.research]
    ids = [e for e in ids if e not in ctx.research]
    if not ids:
        return {}, f"no line of {name}'s cited"
    for e in ids:
        if e not in ctx.lines:
            return {}, f"{e} is not a line"
        if ctx.lines[e].person != key:
            return {}, f"{e} is not {name}'s own line"
    if any(ctx.research[e]["person"] != key for e in public):
        return {}, f"a public finding cited for {name} is someone else's"
    cited = [ctx.lines[e] for e in ids]
    quote, wants = _s(raw.get("quote")), _s(raw.get("wants"))
    if not quoted(quote, [x.text for x in cited] + [x.english for x in cited]):
        return {}, f"{name}'s lines {', '.join(ids)} do not say “{quote}”"
    if not wants:
        return {}, f"no need or offer for {name}"
    p = ctx.people[key]
    return {
        "key": key, "record_key": next((rk for rk, ik in ctx.by_record.items() if ik == key), ""),
        "name": p["name"], "company": p["company"], "role": p["role"], "met": p["met"], "tonight": p["tonight"],
        "wants": wants, "quote": quote, "aside": any(x.aside for x in cited),
        "evidence": [x.evidence() for x in cited],
        "public": [{"id": e, **{k: ctx.research[e][k] for k in ("kind", "text", "source")}} for e in public],
    }, ""


def kept_proposals(raw: Any, ctx: ConnectContext) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """The model's introductions that the logs back, ranked, at most three; and the ones dropped, with why.
    A proposal goes when either side cites a line that does not exist or is not that person's own, or quotes words
    those lines do not have, and when the two are already connected."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    seen: set[frozenset[str]] = set()
    for p in (raw if isinstance(raw, dict) else {}).get("proposals") or []:
        if not isinstance(p, dict):
            continue
        title = " ".join(_s(p.get("title")).split()[:10])
        sides, problem = [], ""
        for which in ("a", "b"):
            side, problem = _side(p.get(which), ctx)
            if problem:
                break
            sides.append(side)
        pair = frozenset(s["key"] for s in sides)
        if not problem:
            if len(pair) < 2:
                problem = "the same person on both sides"
            elif pair in ctx.connected:
                problem = f"already connected: {ctx.connected[pair]}"
            elif pair in seen:
                problem = "the same pair twice"
            elif not _s(p.get("collaboration")):
                problem = "no collaboration"
        if problem:
            dropped.append({"title": title, "reason": problem})
            continue
        seen.add(pair)
        # Whoever said something tonight first: the evening the owner just left is where the idea starts.
        a, b = sorted(sides, key=lambda s: not any(e["tonight"] for e in s["evidence"]))
        ask = ctx.key(p.get("ask_first"))
        kept.append({
            "title": title or f"{a['name']} and {b['name']}",
            "collaboration": _s(p.get("collaboration")),
            "why": _s(p.get("why")),
            "ask_first": ask if ask in pair else a["key"],
            "same_evening": bool(set(ctx.people[a["key"]]["evenings"]) & set(ctx.people[b["key"]]["evenings"])),
            "people": [a, b],
        })
    # Two people met at different evenings first: the ones nobody in a room would have put together.
    kept.sort(key=lambda x: x["same_evening"])
    for i, x in enumerate(kept[:MAX_PROPOSALS], start=1):
        x["rank"] = i
    return kept[:MAX_PROPOSALS], dropped + [{"title": x["title"], "reason": "over three"} for x in kept[MAX_PROPOSALS:]]


def _date(text: Any) -> date | None:
    try:
        return date.fromisoformat(_s(text)[:10])
    except ValueError:
        return None


def date_on_page(d: date, text: str) -> bool:
    """Whether the page writes that day: 2026-11-05, November 5, 5 November, Nov 5, 11/5 or 11月5日."""
    page = f" {fold_words(text)} "
    forms = [f"{d:%Y-%m-%d}", f"{d:%B} {d.day}", f"{d.day} {d:%B}", f"{d:%b} {d.day}", f"{d.day} {d:%b}",
             f"{d.month}/{d.day}/{d.year}", f"{d.year}/{d.month}/{d.day}"]
    return any(f" {fold_words(f)} " in page for f in forms) or f"{d.month}月{d.day}日" in text


def kept_events(answer: Any, results: list[dict[str, str]], cited: list[str], ctx: ConnectContext,
                horizon_days: int = HORIZON_DAYS) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """The events a page the search returned backs: the page is one of the results, its text has the date (inside
    the window) and the person; the need it serves rests on those people's own lines. And the ones dropped."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    until = ctx.today + timedelta(days=horizon_days)
    for e in (answer if isinstance(answer, dict) else {}).get("events") or []:
        if not isinstance(e, dict):
            continue
        title, url, who = _s(e.get("title")), _s(e.get("url")), _s(e.get("who"))

        def drop(reason: str) -> None:
            dropped.append({"title": title, "url": url, "reason": reason})

        source = source_for(url, " ".join([title, who, _s(e.get("why"))]), results, cited)
        if source is None:
            drop("not a page the search returned")
            continue
        page = next((r for r in results if r["url"] == source), {"title": "", "snippet": ""})
        text = f"{page.get('title', '')}\n{page.get('snippet', '')}"
        d = _date(e.get("date"))
        if d is None or not ctx.today <= d <= until:
            drop(f"not in the next {horizon_days} days")
            continue
        if not date_on_page(d, text):
            drop("the date is not on the page")
            continue
        if not fold_words(who) or f" {fold_words(who)} " not in f" {fold_words(text)} ":
            drop("the person is not named on the page")
            continue
        serves = [k for k in map(ctx.key, e.get("for_people") or []) if k in ctx.people]
        ids = [str(x).strip().upper() for x in e.get("evidence") or []]
        lines = [ctx.lines[x] for x in dict.fromkeys(ids) if x in ctx.lines and ctx.lines[x].person in serves]
        quote = _s(e.get("quote"))
        if not lines or not quoted(quote, [x.text for x in lines] + [x.english for x in lines]):
            drop("no line of theirs says the need it serves")
            continue
        met = next((k for k, p in ctx.people.items() if slug(p["name"]) == slug(who)), "")
        bring = [k for k in dict.fromkeys(map(ctx.key, e.get("bring") or [])) if k in ctx.people and k != met]
        if not bring:
            drop("nobody to bring along")
            continue

        def brief(k: str) -> dict[str, str]:
            return {"key": k, "name": ctx.people[k]["name"], "company": ctx.people[k]["company"]}

        kept.append({
            "title": title or page.get("title", ""), "date": d.isoformat(), "weekday": f"{d:%a}", "time": _s(e.get("time")),
            "place": _s(e.get("place")), "url": source, "site": _host(source), "page_title": page.get("title", ""),
            "who": who, "who_key": met, "role": e.get("role") if e.get("role") in ("speaks", "attends", "hosts", "exhibits") else "attends",
            "why": _s(e.get("why")), "quote": quote, "for": [brief(k) for k in dict.fromkeys(x.person for x in lines)],
            "bring": [brief(k) for k in bring], "evidence": [x.evidence() for x in lines],
        })
    return kept[:MAX_EVENTS], dropped + [{"title": x["title"], "url": x["url"], "reason": "over two"} for x in kept[MAX_EVENTS:]]


def look_prompt(ctx: ConnectContext, proposals: list[dict[str, Any]], horizon_days: int = HORIZON_DAYS) -> str:
    until = ctx.today + timedelta(days=horizon_days)
    proposed = [
        f"{x['rank']}. " + " and ".join(f"{s['key']} ({s['name']}" + (f", {s['company']}" if s["company"] else "")
                                         + f"): {s['wants']} [{', '.join(v['id'] for v in s['evidence'])}]" for s in x["people"])
        + f" → {x['collaboration']}"
        for x in proposals
    ]
    return "\n".join([
        *ctx.header(),
        f"Window: {ctx.today:%a %Y-%m-%d} to {until:%a %Y-%m-%d} (the next {horizon_days} days)"
        + (f", in or near {ctx.city}" if ctx.city else ""),
        "",
        "Introductions proposed tonight (their needs first):",
        *(proposed or ["- none"]),
        "",
        "People, and every line each of them said (their own words only; E ids):",
        *ctx.people_block(),
    ])


# --- one run ---------------------------------------------------------------------------------------------------

# Muse Spark list prices, as the report counts them: $ per token, $ per search.
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 1.25e-6, 4.25e-6, 2.5e-3


def _spark_usage(llm: Any, seconds: float) -> dict[str, Any]:
    u = getattr(llm, "last_usage", {}) or {}
    return {"calls": 1, "prompt_tokens": int(u.get("prompt_tokens") or 0), "completion_tokens": int(u.get("completion_tokens") or 0),
            "reasoning_tokens": int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
            "seconds": round(getattr(llm, "last_seconds", 0.0) or seconds, 2)}


async def connect(
    data: Path, rid: str, *, llm: LLM, search: Search | None = None, research: list[dict[str, Any]] | None = None,
    horizon_days: int = HORIZON_DAYS, clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Both parts for one recording: `data` holds the recordings the people index is folded from, `research` the
    report's lookups (context only). `llm` is Muse Spark (extract.SparkClient), `search` research.py's client, or
    None for the introductions alone. A failed call leaves its part empty with a note; the other part still runs."""
    started = time.monotonic()
    ctx = build_context(data, rid, research, clock=clock)
    corpus = isinstance(search, CorpusSearch)
    out: dict[str, Any] = {
        "recording": rid, "event": ctx.meta.get("event", ""), "venue": ctx.meta.get("venue", ""), "day": ctx.today.isoformat(),
        "generated_at": clock(), "status": "ok", "introductions": [],
        "lookahead": {"enabled": search is not None, "corpus": corpus, "from": ctx.today.isoformat(),
                      "to": (ctx.today + timedelta(days=horizon_days)).isoformat(), "events": []},
        "dropped": {"introductions": [], "events": []}, "notes": [],
        "usage": {"introductions": {}, "lookahead": {}},
    }
    if not ctx.lines:
        return {**out, "status": "nothing_said", "seconds": round(time.monotonic() - started, 2)}

    t0 = time.monotonic()
    try:
        raw = await llm(INTRO_SYSTEM, ctx.intro_prompt(), schema=INTRO_SCHEMA, name="hallwise_connector")
        out["introductions"], out["dropped"]["introductions"] = kept_proposals(raw, ctx)
    except Exception as err:  # the look-ahead still runs, on everyone's lines
        out["notes"].append(f"introductions failed ({err.__class__.__name__})")
    out["usage"]["introductions"] = _spark_usage(llm, time.monotonic() - t0)

    if search is not None:
        t1 = time.monotonic()
        try:
            reply = await search(LOOK_SYSTEM, look_prompt(ctx, out["introductions"], horizon_days), schema=LOOK_SCHEMA,
                                 name="hallwise_lookahead")
            events, gone = kept_events(reply.get("answer") or {}, reply.get("results") or [], reply.get("cited") or [], ctx, horizon_days)
            out["lookahead"]["events"], out["dropped"]["events"] = events, gone
            u = reply.get("usage") or {}
            out["usage"]["lookahead"] = {
                "calls": 1, "input_tokens": int(u.get("input_tokens") or 0), "output_tokens": int(u.get("output_tokens") or 0),
                "total_tokens": int(u.get("total_tokens") or 0), "searches": 0 if corpus else int(reply.get("searches") or 0),
                "results": len(reply.get("results") or []), "seconds": round(time.monotonic() - t1, 2),
            }
        except Exception as err:
            out["notes"].append(f"look-ahead failed ({err.__class__.__name__})")
    i, l_ = out["usage"]["introductions"], out["usage"]["lookahead"]
    tokens_in = int(i.get("prompt_tokens") or 0) + int(l_.get("input_tokens") or 0)
    tokens_out = int(i.get("completion_tokens") or 0) + int(l_.get("output_tokens") or 0)
    out["usage"].update(tokens=tokens_in + tokens_out,
                        usd=round(tokens_in * PRICE_IN + tokens_out * PRICE_OUT + int(l_.get("searches") or 0) * PRICE_SEARCH, 4))
    out["seconds"] = round(time.monotonic() - started, 2)
    return out


def event(result: dict[str, Any]) -> dict[str, Any]:
    """What a recording's log keeps of a run (a `connector` event): the counts and the cost, no people's words."""
    return {
        "status": result.get("status", ""), "reason": result.get("reason", ""),
        "introductions": len(result.get("introductions") or []), "events": len((result.get("lookahead") or {}).get("events") or []),
        "dropped": sum(len(v) for v in (result.get("dropped") or {}).values()),
        "usage": result.get("usage") or {}, "seconds": result.get("seconds", 0.0), "model": result.get("model", ""),
        "corpus": bool((result.get("lookahead") or {}).get("corpus")), "cached": bool(result.get("cached")),
    }


def notice(result: dict[str, Any]) -> dict[str, str] | None:
    """The line the phone shows when the owner sits down: the strongest introduction, and the event if there is one."""
    intros = result.get("introductions") or []
    events = (result.get("lookahead") or {}).get("events") or []
    if not intros and not events:
        return None
    if intros:
        a, b = intros[0]["people"]
        title = f"{a['name'].split()[0]} and {b['name'].split()[0]} should meet"
        body = intros[0]["collaboration"]
    else:
        title, body = "Where to meet them next", ""
    if events:
        e = events[0]
        body = " · ".join(x for x in (body, f"{e['weekday']} {e['date'][5:]}: {e['who']} at {e['title']}") if x)
    return {"title": title, "body": body}


class Connector:
    """Runs, keeps and serves the connector's results; off unless HALLWISE_CONNECTOR=on."""

    def __init__(self, data: Path, llm: LLM | None, search: Search | None = None, *, model: str = "", off_reason: str = "",
                 notes: list[str] | None = None, horizon_days: int = HORIZON_DAYS, clock: Callable[[], float] = time.time):
        self.data = data
        self.dir = data / "connector"
        self.llm = llm
        self.search = search
        self.model = model
        self.off_reason = off_reason or ("" if llm is not None else "no model")
        self.notes = notes or []
        self.horizon_days = horizon_days
        self.clock = clock
        self._locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def from_env(cls, data: Path) -> "Connector":
        """HALLWISE_CONNECTOR=on and MODEL_API_KEY: on. The look-ahead reads HALLWISE_RESEARCH_CORPUS as research
        does (a file that cannot be read turns the look-ahead off, never to the web), and stays off with
        HALLWISE_CONNECTOR_LOOKAHEAD=off."""
        if os.environ.get("HALLWISE_CONNECTOR", "") != "on":
            return cls(data, None, off_reason="HALLWISE_CONNECTOR is not on")
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            return cls(data, None, off_reason="MODEL_API_KEY is not set")
        model = os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")
        llm = SparkClient(key, model=model, effort=os.environ.get("HALLWISE_CONNECTOR_EFFORT", "medium"), timeout=180)
        search: Search | None = None
        notes: list[str] = []
        corpus = os.environ.get("HALLWISE_RESEARCH_CORPUS", "")
        if os.environ.get("HALLWISE_CONNECTOR_LOOKAHEAD", "on") == "off":
            notes.append("look-ahead off (HALLWISE_CONNECTOR_LOOKAHEAD=off)")
        else:
            try:
                search = CorpusSearch.load(key, Path(corpus), model=model) if corpus else SearchClient(key, model=model)
            except (OSError, ValueError, TypeError, AttributeError, KeyError) as err:
                notes.append(f"look-ahead off: HALLWISE_RESEARCH_CORPUS unreadable ({err.__class__.__name__})")
        return cls(data, llm, search, model=model, notes=notes)

    @property
    def enabled(self) -> bool:
        return not self.off_reason

    def path(self, rid: str) -> Path | None:
        return self.dir / f"{rid}.json" if is_rid(rid) else None

    def get(self, rid: str) -> dict[str, Any] | None:
        path = self.path(rid)
        try:
            return json.loads(path.read_text()) if path is not None else None
        except (OSError, json.JSONDecodeError):
            return None

    def latest(self) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for p in self.dir.glob("*.json") if self.dir.exists() else []:
            try:
                r = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if best is None or r.get("generated_at", 0) > best.get("generated_at", 0):
                best = r
        return best

    async def run(self, rid: str, research: list[dict[str, Any]] | None = None, force: bool = False) -> dict[str, Any]:
        """One recording's introductions and look-ahead, kept on disk; the stored one comes back unless `force`.
        Off, it asks nothing and stores nothing."""
        if self.path(rid) is None or not (self.data / "recordings" / rid / "meta.json").exists():
            raise KeyError(rid)
        if not self.enabled:
            return {"recording": rid, "status": "off", "reason": self.off_reason, "introductions": [],
                    "lookahead": {"enabled": False, "events": []}}
        async with self._locks.setdefault(rid, asyncio.Lock()):
            have = self.get(rid)
            if have is not None and not force:
                return {**have, "cached": True}
            result = await connect(self.data, rid, llm=self.llm, search=self.search, research=research,
                                   horizon_days=self.horizon_days, clock=self.clock)
            result.update(model=self.model, notes=self.notes + result["notes"])
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / f"{rid}.json.tmp"
            tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1))
            tmp.replace(self.dir / f"{rid}.json")
            return {**result, "cached": False}
