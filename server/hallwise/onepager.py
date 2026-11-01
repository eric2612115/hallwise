"""The deck, quietly rebuilt for the person who'll read it.

The owner keeps his pitch as Markdown (HALLWISE_DECK: one `##` per slide, an HTML comment under a number saying
where it comes from). When someone he owes a follow-up has an edge (extract.py: what they said not to him that
shows what they want, with `act`, e.g. "one page, numbers first"), Muse Spark rewrites the deck for them along that
act, from the deck's own facts and numbers only, and the follow-up carries it. Margaux complained to Julien in
French that yesterday's founder had twenty slides and not one number; the next morning her follow-up has Eric's
deck as one page, the numbers first. The model gets the act, never what was said, and the page never lets on.

Numbers are held to the deck: every number on the page (in digits, or a number word) must be one the slides state;
the comments only back a figure's source, so a date in one never lets a claim through. A page with a number the
deck does not have is written once more, told which; a line that still has one after that is dropped, and so is
a line with the reader's own words (`said`, or its English), which no page should carry back to them.

The model answers JSON (title, lede, figures, sections, close) and never writes markup: `render` makes the page,
every text escaped, black on white, one printed page, the owner's company name as text and no logo.

Saved per recording and person: data/onepagers/<recording>/<person key>.html, with a .json beside it (the acts,
the page, what was dropped, the tokens). The same deck, acts, reader and promise come back from there without a
call. HALLWISE_DECK unset or unreadable, or no MODEL_API_KEY: off, and nothing is sent.

The `rebuilt` event (`rebuilt_event`) says a page is ready, for the phone to buzz and open the viewer. For the demo
a page made beforehand (HTML or PDF, HALLWISE_ONEPAGER_CUE) is put into a live recording on cue (`cue`, POST
/api/recordings/{id}/onepager/cue, server/scripts/cue_rebuilt.py), and `router` serves whichever page a person has.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .extract import LLM, _STR, _STR_LIST, _obj, SparkClient, fold_words
from .ids import is_key, is_rid

MAX_FIGURES, MAX_SECTIONS, MAX_POINTS, MAX_CHARS = 6, 5, 4, 300  # whatever the act, the page stays one page

ONEPAGER_SCHEMA: dict[str, Any] = _obj(
    applies={"type": "boolean", "description": "false when the act is not about what the reader is sent to read; then leave the rest empty"},
    shape={**_STR, "description": "for the owner, never on the page: what this version is, under 6 words, e.g. 'one page, numbers first'"},
    title={**_STR, "description": "the page's title: the product's name as the deck writes it"},
    lede={**_STR, "description": "one sentence under the title: what it is, in the deck's words"},
    figures={
        "type": "array",
        "items": _obj(
            value={**_STR, "description": "the number exactly as the deck writes it, e.g. '24 of 25'"},
            label={**_STR, "description": "what it counts, under 12 words"},
            source={**_STR, "description": "who and when, from the deck's comment under that number, e.g. 'Product Hunt, 2026-10-28'; empty if none"},
        ),
    },
    sections={
        "type": "array",
        "items": _obj(heading=_STR, points={**_STR_LIST, "description": "one line each"}),
    },
    close={**_STR, "description": "one closing line from the deck: where it stands; empty if the deck has none"},
)

ONEPAGER_SYSTEM = """You rewrite the owner's pitch deck for one reader: someone he met at a networking event, who
will get it with his follow-up. You get the deck (Markdown, one ## per slide; an HTML comment under a line says
where that line's numbers come from), who the reader is, what the owner promised them, and how the page should be
shaped for this reader (the act, e.g. "one page, numbers first").

Rules:
- applies: true when the act is about what the reader is sent to read (its length, its order, what it leads with,
  how much detail). False when it is about something else (a time, a call, a person to meet): then leave the rest
  empty.
- Follow the act. "numbers first": the deck's strongest numbers lead, as figures, before any prose. "one page": it
  fits one printed page: at most 6 figures, at most 4 sections of at most 3 points, every point one line.
- Only what the deck says. Every fact, name and number comes from the deck; nothing from outside it, nothing
  inferred. Copy each number exactly as the deck writes it, in digits, with what it counts beside it. Never round,
  convert, add up, compare or work out a number (no percentage, total or multiple the deck does not state).
- A figure's source is the deck's comment under that number, cut to who and when ("Product Hunt, 2026-10-28");
  empty when the deck gives none. Never cite a file path.
- The deck's stage stays exactly as it says: never claim users, customers, revenue, pilots or traction it does not
  state, and keep what it says about having none.
- The page reads as the owner's own one-pager. Never say it was shortened, reordered or made for this reader;
  never mention slides, a deck or a longer version; never refer to the reader's wishes, taste or anything they
  said.
- Write in {language}. Names of people, companies, products and models exactly as the deck spells them.
- Never join two of the deck's facts into one claim it does not make (a count with a span of time it was not
  counted over, a cause, a comparison).
- Short, plain sentences, in the deck's own words where they work; no praise or hype the deck does not use."""

# Every number on the page must be one the deck has: digits ("1,000", "3.1", "2025-12-05") and number words.
_DIGITS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
NUMBER_WORDS = {
    w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                               "fifteen sixteen seventeen eighteen nineteen twenty".split())
} | {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "dozen": 12,
     "hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b")


def _canon(token: str) -> str:
    """'1,000' -> '1000', '05' -> '5', '3.10' -> '3.1': one way to write each number."""
    whole, _, frac = token.replace(",", "").partition(".")
    frac = frac.rstrip("0")
    return (whole.lstrip("0") or "0") + (f".{frac}" if frac else "")


def numbers(text: str) -> set[str]:
    """Every number in a text, written one way: '24 of 25' -> {'24', '25'}, 'twenty' -> {'20'}, '20+' -> {'20'}."""
    found = {_canon(m.group()) for m in _DIGITS.finditer(text or "")}
    return found | {str(NUMBER_WORDS[w]) for w in _WORD.findall((text or "").casefold())}


def slides(source: str) -> str:
    """The deck from its first slide on: what comes before the first `##` is the owner's own preface."""
    m = re.search(r"^## ", source or "", re.M)
    return (source[m.start():] if m else source or "").strip()


def slide_titles(source: str) -> list[str]:
    """The deck's slides by title, for the owner's phone: the viewer shows them folding into the one page."""
    return [" ".join(t.split())[:60] for t in re.findall(r"^## +(.+)$", slides(source), re.M)][:20]


def said_in(source: str) -> str:
    """The slides without their comments: what a line of the page may state. The comments only back a figure's
    source, so a date in one ("2025-12-08") never lets "12 accents" through."""
    return re.sub(r"<!--.*?-->", " ", slides(source), flags=re.S)


def _text(x: Any) -> str:
    return " ".join(x.split())[:MAX_CHARS] if isinstance(x, str) else ""


def clean(raw: Any) -> dict[str, Any]:
    """Whatever came back, as a page: strings on one line, empty items gone, the counts capped."""
    raw = raw if isinstance(raw, dict) else {}
    figures = [{"value": _text(f.get("value")), "label": _text(f.get("label")), "source": _text(f.get("source"))}
               for f in raw.get("figures") or [] if isinstance(f, dict) and _text(f.get("value"))]
    sections = []
    for s in raw.get("sections") or []:
        if not isinstance(s, dict):
            continue
        points = [_text(p) for p in s.get("points") or [] if _text(p)][:MAX_POINTS]
        if points:
            sections.append({"heading": _text(s.get("heading")), "points": points})
    return {"applies": raw.get("applies") is not False, "shape": " ".join(_text(raw.get("shape")).split()[:8]),
            "title": _text(raw.get("title")), "lede": _text(raw.get("lede")),
            "figures": figures[:MAX_FIGURES], "sections": sections[:MAX_SECTIONS], "close": _text(raw.get("close"))}


def _parts(page: dict[str, Any]) -> list[tuple[tuple[Any, ...], str, str]]:
    """Each line of a page with where it sits, so the check can drop that line and only that line, and the part
    of it that only cites (a figure's source)."""
    out: list[tuple[tuple[Any, ...], str, str]] = [(("title",), page["title"], ""), (("lede",), page["lede"], "")]
    out += [(("figures", i), " ".join(x for x in (f["value"], f["label"]) if x), f["source"]) for i, f in enumerate(page["figures"])]
    for i, s in enumerate(page["sections"]):
        out.append((("sections", i, "heading"), s["heading"], ""))
        out += [(("sections", i, "points", j), p, "") for j, p in enumerate(s["points"])]
    return out + [(("close",), page["close"], "")]


def _where(path: tuple[Any, ...]) -> str:
    """('sections', 1, 'points', 0) -> 'sections[1].points[0]'."""
    return "".join(f"[{p}]" if isinstance(p, int) else (f".{p}" if i else p) for i, p in enumerate(path))


def reader_words(edges: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """What the reader said, as `extract.overheard` counts it: their own words from two, the English from four."""
    return [(str(e.get(f) or ""), least) for e in edges for f, least in (("said", 2), ("english", 4)) if str(e.get(f) or "").strip()]


def problems(page: dict[str, Any], allowed: set[str], said: list[tuple[str, int]],
             cited: set[str] | None = None) -> list[dict[str, Any]]:
    """The lines with a number the deck does not have, or with the reader's own words in them. `allowed`: the
    numbers the slides state (said_in); `cited`: those and their comments', for a figure's source."""
    out = []
    for path, line, source in _parts(page):
        text = " ".join(x for x in (line, source) if x)
        if not text:
            continue
        bad = sorted((numbers(line) - allowed) | (numbers(source) - (allowed | (cited or set()))), key=lambda n: (len(n), n))
        folded = f" {fold_words(text)} "
        quoted = next((w.strip() for w, least in said
                       if len(fold_words(w).split()) >= least and f" {fold_words(w)} " in folded), "")
        if bad or quoted:
            out.append({"path": path, "where": _where(path), "text": text, "numbers": bad, "quoted": bool(quoted)})
    return out


def prune(page: dict[str, Any], found: list[dict[str, Any]]) -> dict[str, Any]:
    """The page without the lines `problems` found; a section left with no points goes too."""
    drop = {p["path"] for p in found}
    sections = []
    for i, s in enumerate(page["sections"]):
        points = [p for j, p in enumerate(s["points"]) if ("sections", i, "points", j) not in drop]
        if points:
            sections.append({"heading": "" if ("sections", i, "heading") in drop else s["heading"], "points": points})
    return {**page, "title": "" if ("title",) in drop else page["title"], "lede": "" if ("lede",) in drop else page["lede"],
            "figures": [f for i, f in enumerate(page["figures"]) if ("figures", i) not in drop],
            "sections": sections, "close": "" if ("close",) in drop else page["close"]}


def retry_note(found: list[dict[str, Any]]) -> str:
    lines = [f"- {p['text']}" + (f" (not in the deck: {', '.join(p['numbers'])})" if p["numbers"] else "")
             + (" (too close to the reader's own words: say it another way)" if p["quoted"] else "") for p in found]
    return ("Your page had lines the deck does not back. Write the page again: copy every number from the deck "
            "exactly as it is written there, or leave it out. These lines must change:\n" + "\n".join(lines))


def acts_of(record: dict[str, Any], person_key: str) -> tuple[list[dict[str, Any]], list[str]]:
    """The person's edges that say what to do, and those acts, each once."""
    edges = [e for e in record.get("edges") or [] if e.get("person") == person_key and str(e.get("act") or "").strip()]
    return edges, list(dict.fromkeys(str(e["act"]).strip() for e in edges))


def build_prompt(source: str, person: dict[str, Any], acts: list[str], promise: dict[str, Any], *,
                 owner_name: str = "", owner_company: str = "") -> str:
    """The deck and what to do with it. Only the acts: what the reader said, and how, never reaches the model."""
    reader = ", ".join(x for x in (person.get("name", ""), person.get("company", ""), person.get("role", "")) if x)
    what = str(promise.get("what") or "").strip()
    return "\n".join([
        f"Owner: {owner_name or 'unknown'}" + (f", from {owner_company}" if owner_company else ""),
        f"Reader: {reader or person.get('key', '')}",
        f"Promised: {what or 'a follow-up'}" + (f" (due: {promise['due']})" if promise.get("due") else ""),
        "Act (how the page should be shaped for this reader):",
        *(f"- {a}" for a in acts),
        "",
        "Deck:",
        "",
        slides(source),
    ])


def language_of(person: dict[str, Any]) -> str:
    """The follow-up's language, so the page reads like the message it comes with."""
    lang = str(person.get("preferred_language") or "").strip()
    return lang if lang and lang.casefold() != "english" else "the deck's language"


# On screen, the app's ink and teal on white; printed, black on white. Either way one A4 page.
PAGE_CSS = """@page { size: A4; margin: 14mm; }
:root { color-scheme: light; --ink: #1A1613; --soft: #6E675E; --rule: #D3CBB9; --accent: #2F7F72; }
html { background: #fff; }
body { margin: 0 auto; max-width: 182mm; padding: 22px 20px; color: var(--ink); background: #fff;
  font: 15px/1.5 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; -webkit-text-size-adjust: 100%;
  -webkit-font-smoothing: antialiased; }
@media (min-width: 560px) { body { padding: 40px 48px; } }
@media (max-width: 480px) { header { flex-direction: column; gap: 2px; } h1 { font-size: 36px; } }
header { display: flex; justify-content: space-between; gap: 12px; color: var(--soft); font-size: 11px;
  letter-spacing: 0.06em; text-transform: uppercase; border-bottom: 1px solid var(--rule); padding-bottom: 8px;
  margin-bottom: 22px; }
h1, .figure .value { font-family: ui-serif, "New York", Georgia, serif; }
h1 { font-size: 40px; line-height: 1.05; margin: 0 0 8px; letter-spacing: -0.015em; }
.lede { font-size: 18px; line-height: 1.4; margin: 0 0 22px; }
.figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px 22px;
  border-top: 3px solid var(--accent); border-bottom: 1px solid var(--rule); padding: 16px 0 18px; margin: 0 0 22px; }
.figure .value { font-size: 34px; font-weight: 700; line-height: 1.05; letter-spacing: -0.01em;
  font-variant-numeric: lining-nums; }
.figure .label { font-size: 13.5px; line-height: 1.35; margin-top: 4px; }
.figure .source { color: var(--soft); font-size: 10.5px; margin-top: 4px; }
section { break-inside: avoid; margin: 0 0 14px; }
h2 { color: var(--accent); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 5px; }
ul { margin: 0; padding-left: 18px; }
li { margin: 0 0 3px; }
li::marker { color: var(--accent); }
.close { font-size: 16px; font-weight: 600; border-top: 1px solid var(--rule); padding-top: 12px; margin: 20px 0 0; }
footer { color: var(--soft); font-size: 11px; letter-spacing: 0.04em; margin-top: 22px; }
footer b { color: var(--accent); font-weight: 700; }
@media print {
  :root { --ink: #000; --soft: #000; --rule: #000; --accent: #000; }
  body { padding: 0; max-width: none; }
}"""


def render(page: dict[str, Any], *, brand: str = "Hallwise", reader: str = "", owner: str = "", day: str = "") -> str:
    """The page as one printable HTML file: no script, no image, nothing fetched; every text escaped. A hyphen
    between digits does not break ("2025-12-08", "5-8")."""
    def e(text: str) -> str:
        return html.escape(re.sub(r"(?<=\d)-(?=\d)", "\u2011", text))

    title = page["title"] or brand
    figures = "".join(
        '<div class="figure">' + f'<div class="value">{e(f["value"])}</div>'
        + (f'<div class="label">{e(f["label"])}</div>' if f["label"] else "")
        + (f'<div class="source">{e(f["source"])}</div>' if f["source"] else "") + "</div>"
        for f in page["figures"])
    sections = "".join(
        "<section>" + (f"<h2>{e(s['heading'])}</h2>" if s["heading"] else "")
        + "<ul>" + "".join(f"<li>{e(p)}</li>" for p in s["points"]) + "</ul></section>"
        for s in page["sections"])
    by = f"<b>{e(brand)}</b>" + (f" · {e(owner)}" if owner else "")
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="color-scheme" content="light">',
        f"<title>{e(title + (f' for {reader}' if reader else ''))}</title>",
        f"<style>\n{PAGE_CSS}\n</style>",
        "</head>",
        "<body>",
        "<header>" + f"<span>{e(f'For {reader}' if reader else '')}</span><span>{e(day)}</span>" + "</header>",
        f"<h1>{e(title)}</h1>",
        f'<p class="lede">{e(page["lede"])}</p>' if page["lede"] else "",
        f'<div class="figures">{figures}</div>' if figures else "",
        sections,
        f'<p class="close">{e(page["close"])}</p>' if page["close"] else "",
        f"<footer>{by}</footer>",
        "</body>",
        "</html>",
        "",
    ])


def _add(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Two calls' tokens as one: the second try costs too."""
    reasoning = int((b.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    out = {k: int(a.get(k) or 0) + int(b.get(k) or 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {**out, "reasoning_tokens": int(a.get("reasoning_tokens") or 0) + reasoning, "calls": int(a.get("calls") or 0) + 1}


async def rebuild(
    llm: LLM, record: dict[str, Any], person_key: str, promise: dict[str, Any], source: str, *,
    owner_name: str = "", owner_company: str = "", day: str = "",
) -> dict[str, Any]:
    """The deck rebuilt for one person met tonight, along their edges' acts. `record` is a folded recording
    (events.fold_record), `promise` the one the follow-up keeps, `source` the deck's Markdown.

    status: "ok" (with `page` and `html`), "no_person", "no_edge" or "no_source" (no call made), "not_applicable"
    (the act is not about something to read), "empty" (nothing was left after the check). `dropped` lists the
    lines the check took out; `usage` sums the tokens of every call."""
    person = next((p for p in record.get("people", []) if p.get("key") == person_key), None)
    edges, acts = acts_of(record, person_key)
    out: dict[str, Any] = {"person_key": person_key, "promise_key": str(promise.get("key") or ""), "acts": acts,
                           "slides": slide_titles(source), "status": "", "dropped": [], "retried": False, "usage": {},
                           "seconds": 0.0}
    if person is None:
        return {**out, "status": "no_person"}
    if not acts:
        return {**out, "status": "no_edge"}
    if not slides(source):
        return {**out, "status": "no_source"}
    prompt = build_prompt(source, person, acts, promise, owner_name=owner_name, owner_company=owner_company)
    system = ONEPAGER_SYSTEM.replace("{language}", language_of(person))
    allowed, cited, said = numbers(said_in(source)), numbers(slides(source)), reader_words(edges)
    started, usage = time.monotonic(), {}

    async def ask(text: str) -> dict[str, Any]:
        nonlocal usage
        try:
            return clean(await llm(system, text, schema=ONEPAGER_SCHEMA, name="hallwise_onepager"))
        finally:
            usage = _add(usage, getattr(llm, "last_usage", {}) or {})

    page = await ask(prompt)
    found = problems(page, allowed, said, cited) if page["applies"] else []
    if found:
        again = await ask(prompt + "\n\n" + retry_note(found))
        if again["applies"]:
            page, found = again, problems(again, allowed, said, cited)
        out["retried"] = True
    out.update(usage=usage, seconds=round(time.monotonic() - started, 2),
               dropped=[{k: p[k] for k in ("where", "text", "numbers", "quoted")} for p in found])
    if not page["applies"]:
        return {**out, "status": "not_applicable"}
    page = prune(page, found)
    if not (page["figures"] or page["sections"]):
        return {**out, "status": "empty"}
    reader = ", ".join(x for x in (person.get("name", ""), person.get("company", "")) if x)
    html_ = render(page, brand=owner_company or "Hallwise", reader=reader, owner=owner_name,
                   day=day or time.strftime("%B %-d, %Y"))
    return {**out, "status": "ok", "page": page, "html": html_}


def event(result: dict[str, Any]) -> dict[str, Any]:
    """What a recording's log keeps of a rebuild (an `onepager` event): no page, no HTML."""
    return {k: result[k] for k in ("person_key", "promise_key", "acts", "slides", "status", "reason", "file", "dropped",
                                   "retried", "usage", "seconds", "model", "cached") if k in result}


class Onepagers:
    """Rebuilds, keeps and serves the tailored pages; off without a deck or a key."""

    def __init__(self, data: Path, llm: LLM | None, deck: Path | None, *, model: str = "", off_reason: str = ""):
        self.dir = data / "onepagers"
        self.llm = llm
        self.deck = deck
        self.model = model
        self.off_reason = off_reason or ("" if llm is not None and deck is not None else "no deck or no model")
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    @classmethod
    def from_env(cls, data: Path) -> "Onepagers":
        """HALLWISE_DECK: the deck's Markdown; unset, off. The model is Muse Spark (HALLWISE_SPARK_MODEL), at
        HALLWISE_ONEPAGER_EFFORT (low; "minimal" halves the wait, from about 9 s to 5 s on Margaux's page)."""
        deck = os.environ.get("HALLWISE_DECK", "").strip()
        if not deck:
            return cls(data, None, None, off_reason="HALLWISE_DECK is not set")
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            return cls(data, None, None, off_reason="MODEL_API_KEY is not set")
        model = os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")
        effort = os.environ.get("HALLWISE_ONEPAGER_EFFORT", "low")
        return cls(data, SparkClient(key, model=model, effort=effort, timeout=180), Path(deck), model=model)

    @property
    def enabled(self) -> bool:
        return not self.off_reason

    def path(self, rid: str, person_key: str, suffix: str = ".html") -> Path | None:
        """Where a page lives; None for anything that is not a recording id and a person key (ids.py)."""
        if not (is_rid(rid) and is_key(person_key)):
            return None
        return self.dir / rid / f"{person_key}{suffix}"

    def html(self, rid: str, person_key: str) -> str | None:
        """A rebuilt page, for the route that serves it."""
        path = self.path(rid, person_key)
        try:
            return path.read_text() if path is not None else None
        except OSError:
            return None

    def get(self, rid: str, person_key: str) -> dict[str, Any] | None:
        path = self.path(rid, person_key, ".json")
        try:
            return json.loads(path.read_text()) if path is not None else None
        except (OSError, json.JSONDecodeError):
            return None

    async def rebuild(self, rid: str, record: dict[str, Any], person_key: str, promise: dict[str, Any], *,
                      owner_name: str = "", owner_company: str = "", day: str = "") -> dict[str, Any]:
        """`rebuild` for one person of one recording, kept on disk; the same inputs come back from there."""
        base = {"person_key": person_key, "promise_key": str(promise.get("key") or ""), "model": self.model}
        if self.path(rid, person_key) is None:
            return {**base, "status": "error", "reason": "not a recording id and a person key"}
        if not self.enabled:
            return {**base, "status": "off", "reason": self.off_reason}
        try:
            source = self.deck.read_text()  # each time: the owner may have changed the deck
        except OSError as err:
            return {**base, "status": "off", "reason": f"HALLWISE_DECK unreadable ({err.__class__.__name__})"}
        person = next((p for p in record.get("people", []) if p.get("key") == person_key), {})
        _, acts = acts_of(record, person_key)
        inputs = hashlib.sha256(json.dumps([
            slides(source), acts, [person.get(k, "") for k in ("name", "company", "role", "preferred_language")],
            [promise.get(k, "") for k in ("what", "due")], owner_name, owner_company, self.model, ONEPAGER_SYSTEM,
        ], ensure_ascii=False).encode()).hexdigest()
        lock = self._locks.setdefault((rid, person_key), asyncio.Lock())
        async with lock:
            have = self.get(rid, person_key)
            if have is not None and (have.get("cued") or (have.get("inputs") == inputs and (
                    have.get("status") != "ok" or self.html(rid, person_key)))):
                return {**have, "cached": True}  # a page put in on cue (see `cue`) stays the one that is sent
            try:
                result = await rebuild(self.llm, record, person_key, promise, source,
                                       owner_name=owner_name, owner_company=owner_company, day=day)
            except Exception as err:  # the follow-up still goes, with the deck as it is
                return {**base, "status": "error", "reason": f"{err.__class__.__name__}: {err}"[:300]}
            result = {**result, "model": self.model, "inputs": inputs, "generated_at": time.time()}
            if result["status"] in ("ok", "not_applicable", "empty"):
                self._save(rid, person_key, result)
            return {**{k: v for k, v in result.items() if k != "html"}, "cached": False}

    def _save(self, rid: str, person_key: str, result: dict[str, Any]) -> None:
        folder = self.dir / rid
        folder.mkdir(parents=True, exist_ok=True)
        if result.get("html"):
            result["file"] = f"onepagers/{rid}/{person_key}.html"
            tmp = folder / f"{person_key}.html.tmp"
            tmp.write_text(result["html"])
            tmp.replace(folder / f"{person_key}.html")
        tmp = folder / f"{person_key}.json.tmp"
        tmp.write_text(json.dumps({k: v for k, v in result.items() if k != "html"}, ensure_ascii=False, indent=1))
        tmp.replace(folder / f"{person_key}.json")

    async def for_moves(self, rid: str, record: dict[str, Any], moves: list[dict[str, Any]], *,
                        owner_name: str = "", owner_company: str = "", day: str = "") -> dict[str, dict[str, Any]]:
        """One page per person with an edge that says what to do, whom the owner writes to: for the move that
        attaches the deck or a one-pager when there is one, else their first message, email or invitation.
        Nudges (what they owe the owner) get none. Keyed by person key; off, it asks nothing."""
        if not self.enabled:
            return {}
        promises = {q.get("key"): q for q in record.get("promises", [])}
        chosen: dict[str, dict[str, Any]] = {}
        for m in sorted(moves, key=lambda m: (m.get("attach") not in ("deck", "one_pager"), m.get("kind") == "calendar")):
            key = m.get("person_key", "")
            if m.get("kind") != "nudge" and key not in chosen and acts_of(record, key)[1]:
                chosen[key] = m
        out = {}
        for key, m in chosen.items():
            promise = promises.get(m.get("promise_key"), {"key": m.get("promise_key", ""), "what": m.get("subject", "")})
            out[key] = await self.rebuild(rid, record, key, promise, owner_name=owner_name, owner_company=owner_company, day=day)
        return out


# --- ready: the event, the demo's cue, the routes ------------------------------------------------------------

FORMATS = {".html": "text/html; charset=utf-8", ".pdf": "application/pdf"}
CUE_MAX_BYTES = 10_000_000


def page_url(rid: str, person_key: str) -> str:
    """Where the app reads a page: the route `router` serves it from."""
    return f"/api/recordings/{rid}/onepager/{person_key}"


def rebuilt_event(rid: str, person_key: str, name: str, *, shape: str = "", acts: list[str] | None = None,
                  slides: list[str] | None = None, title: str = "", format: str = "html", **extra: Any) -> dict[str, Any]:
    """The `rebuilt` event's data: who, what this version is (shape, for the owner's notification), the acts it
    follows, the deck's slide titles (the viewer folds them into the page; titles may be empty, the count is what
    shows), and where to read it, as HTML or PDF."""
    return {"person_key": person_key, "name": name, "status": "ok", "title": title, "shape": shape,
            "acts": list(acts or []), "slides": list(slides or [])[:20], "format": format,
            "url": page_url(rid, person_key), **extra}


def find_person(record: dict[str, Any], name: str) -> dict[str, Any] | None:
    """The person in a recording a first name points to, as the transcriber may have spelled it: "Margaux" finds
    Margot Lefebvre (the same first four letters, or a close spelling). None when nobody, or more than one, fits."""
    want = fold_words(name).split()[:1]
    if not want:
        return None

    def close(heard: str) -> bool:
        return heard == want[0] or (len(heard) >= 4 and heard[:4] == want[0][:4]) or (
            heard[:1] == want[0][:1] and difflib.SequenceMatcher(None, heard, want[0]).ratio() >= 0.75)

    fits = [p for p in record.get("people", []) if (fold_words(p.get("name", "")).split() or [""])[0]
            and close(fold_words(p.get("name", "")).split()[0])]
    return fits[0] if len(fits) == 1 else None


def cue(data: Path, rid: str, record: dict[str, Any], asset: Path, name: str, *, shape: str = "",
        slides: list[str] | None = None) -> dict[str, Any]:
    """A page made beforehand, put into a recording on cue: `asset` (an .html or a .pdf) is kept where a rebuilt
    page is, under the key the recording has the person `name` points to, and stays the one that is sent (the
    morning's pass does not replace it). Returns the `rebuilt` event's data for the caller to log. LookupError
    when the recording has nobody by that name; ValueError for a file that is not an HTML or PDF page."""
    asset = Path(asset)
    suffix = asset.suffix.lower()
    if suffix not in FORMATS or not asset.is_file() or asset.stat().st_size > CUE_MAX_BYTES:
        raise ValueError(f"the cue's page must be an .html or .pdf file under {CUE_MAX_BYTES} bytes")
    person = find_person(record, name)
    if person is None:
        raise LookupError(f"nobody in this recording is called {name!r}")
    key = str(person.get("key", ""))
    pages = Onepagers(data, None, None)
    path = pages.path(rid, key, suffix)
    if path is None:
        raise ValueError("not a recording id and a person key")
    path.parent.mkdir(parents=True, exist_ok=True)
    for other in FORMATS:  # one page per person: the cued one
        if other != suffix:
            pages.path(rid, key, other).unlink(missing_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(asset.read_bytes())
    tmp.replace(path)
    ready = rebuilt_event(rid, key, str(person.get("name", "")), shape=shape, slides=slides, format=suffix[1:], cued=True)
    pages.path(rid, key, ".json").write_text(json.dumps(
        {**ready, "asset": asset.name, "file": f"onepagers/{rid}/{key}{suffix}", "generated_at": time.time()},
        ensure_ascii=False, indent=1))
    return ready


def router(data: Path, record_of: Any, append: Any) -> Any:
    """The routes, for app.py to include (`app.include_router(onepager.router(data, record_of, append))`):

    GET  /api/recordings/{rid}/onepager/{key}  a person's page, HTML or PDF, as kept (rebuilt or cued)
    POST /api/recordings/{rid}/onepager/cue?name=Margaux[&shape=...]
         the demo's page on cue: HALLWISE_ONEPAGER_CUE (an .html or .pdf on the server, never a path from the
         request) put in for that person, and a `rebuilt` event logged, so the phone buzzes and opens it. The
         slide titles for the viewer's fold come from HALLWISE_DECK when it is Markdown with `##` slides, else
         HALLWISE_ONEPAGER_SLIDES (a count of untitled slides).

    `record_of(rid)` gives (record, moves, meta) and raises HTTPException 404 for no such recording; `append(rid,
    type, **data)` logs an event (live: watchers see it at once)."""
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import Response

    api = APIRouter()
    pages = Onepagers(data, None, None)

    @api.post("/api/recordings/{rid}/onepager/cue")
    def cue_page(rid: str, name: str, shape: str = "") -> dict[str, Any]:
        asset = os.environ.get("HALLWISE_ONEPAGER_CUE", "").strip()
        if not asset:
            raise HTTPException(503, "HALLWISE_ONEPAGER_CUE is not set")
        record, _, _ = record_of(rid)
        deck = os.environ.get("HALLWISE_DECK", "").strip()
        try:
            titles = slide_titles(Path(deck).read_text()) if deck else []
        except OSError:
            titles = []
        count = os.environ.get("HALLWISE_ONEPAGER_SLIDES", "").strip()
        titles = titles or ([""] * min(int(count), 20) if count.isdigit() else [])
        try:
            event = cue(data, rid, record, Path(asset), name[:80],
                        shape=(shape or os.environ.get("HALLWISE_ONEPAGER_SHAPE", "one page, numbers first"))[:60],
                        slides=titles)
        except LookupError as err:
            raise HTTPException(404, str(err))
        except (ValueError, OSError) as err:
            raise HTTPException(500, str(err))
        return append(rid, "rebuilt", **event)

    @api.get("/api/recordings/{rid}/onepager/{key}")
    def get_page(rid: str, key: str) -> Response:
        for suffix, media in FORMATS.items():
            path = pages.path(rid, key, suffix)
            if path is not None and path.is_file():
                return Response(path.read_bytes(), media_type=media.split(";")[0], headers={
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                    "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
        raise HTTPException(404, "no page for this person")

    return api
