"""Met before, the moment someone says who they are: a known person's name in a new turn, with no model.

Muse Spark re-reads the transcript after each turn, so a guest the owner had met before used to get the "met
before" ring only once the next run finished: 17-24 s after he introduced himself, in rehearsal. `Recall` looks at
each turn as it arrives. When the text holds the full name of someone in the people index (the surname matched
loosely, since that is what transcribers get wrong: "Ragoo Nathan" for Raghunathan), or their first name with their
company, or their first name with an event they are known by, it binds that person to the turn's speaker at once:
a `person_history` flagged `provisional`, with the hooks for that person. The next Muse Spark run that has seen the
turn settles it: the same person for that voice confirms it, someone else withdraws it (`person_history_removed`),
and one never confirmed by the end of the recording is withdrawn too, so the drafts never lean on a guess.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .extract import Turn, slug
from .hooks import Threads, same_first_name
from .people import history_event, match

# Words that say little about which company: "Corvane Capital" is known by Corvane.
GENERIC_COMPANY = {
    "inc", "ltd", "llc", "co", "corp", "corporation", "company", "the", "labs", "lab", "group", "capital", "ventures",
    "venture", "partners", "robotics", "health", "pay", "optics", "mobility", "grid", "technologies", "technology",
    "tech", "ai", "systems", "studio", "studios", "fund", "holdings", "network", "networks", "software", "energy",
    "solutions", "and", "of",
}
# Words that say little about which evening: "Blockchain Week side event" is known by Blockchain Week.
GENERIC_EVENT = {
    "side", "event", "events", "party", "afterparty", "after", "meetup", "meet", "up", "dinner", "night", "mixer",
    "drinks", "the", "a", "an", "of", "at", "in", "and", "founder", "founders", "rehearsal", "living", "room",
    "evening", "lunch", "breakfast", "session",
}
# Just before a name, these mean someone else is being talked about ("you should meet Kenji Watanabe",
# "this is Eric", "Siddharth said"), not introducing himself.
ABOUT_SOMEONE_ELSE = {
    "meet", "met", "know", "knows", "knew", "introduce", "introduced", "introducing", "intro", "with", "and", "ask",
    "asked", "tell", "told", "said", "say", "says", "call", "called", "see", "saw", "seen", "like", "about", "to",
    "for", "of", "sent", "send", "email", "emailed", "ping", "contact", "find", "found", "remember", "is", "this",
    "that", "where", "wheres", "colleague", "partner", "friend", "boss", "cofounder", "ceo", "cto", "mr", "ms", "mrs",
    "dr", "his", "her", "their", "your", "my", "our",
}
AFTER_SOMEONE_ELSE = {"said", "says", "told", "mentioned", "s", "is", "was", "will", "would", "has", "had"}
SELF = (("i", "m"), ("im",), ("i", "am"), ("name", "is"), ("call", "me"), ("it", "s"))

_WORD = re.compile(r"[a-z0-9]+")


def fold(text: str) -> str:
    """Lowercase, accents gone: 'Chloé Lefèvre' -> 'chloe lefevre'."""
    n = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in n if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    return _WORD.findall(fold(text))


def close(a: str, b: str, floor: float = 0.8) -> bool:
    """The same word as heard: equal, or near enough for words of five letters or more."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= floor


def phrase_at(tokens: list[str], start: int, target: list[str]) -> int:
    """How many tokens from `start` spell `target` (spacing ignored: "Ragoo Nathan" spells raghunathan, loosely),
    0 when they do not."""
    want = "".join(target)
    if not want:
        return 0
    for n in range(1, min(len(target) + 2, len(tokens) - start) + 1):
        got = "".join(tokens[start:start + n])
        if close(got, want):
            return n
        if len(got) > len(want) + 3:
            break
    return 0


def find_phrase(tokens: list[str], target: list[str]) -> int | None:
    for i in range(len(tokens)):
        if phrase_at(tokens, i, target):
            return i
    return None


@dataclass
class Hit:
    entry: dict[str, Any]
    why: str  # "full name", "first name and company", "first name and event"
    at: int  # token index of the first name
    score: float


@dataclass
class Matcher:
    """Known people, ready to be found in a line of transcript."""

    index: list[dict[str, Any]]
    owner_name: str = ""
    owner_company: str = ""
    _people: list[tuple[dict[str, Any], list[str], list[str], list[list[str]]]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        owner_first = (self.owner_name.split() or [""])[0]
        for entry in self.index:
            name = words(entry.get("name", ""))
            if not name:
                continue
            company = words(entry.get("company", ""))
            # the owner himself, if an old log ever listed him, is never "met before"
            if owner_first and same_first_name(entry.get("name", ""), owner_first) and (
                not company or slug(entry.get("company", "")) == slug(self.owner_company)
            ):
                continue
            core = [w for w in company if w not in GENERIC_COMPANY] or company
            events = []
            for e in entry.get("encounters", []):
                ev = [w for w in words(e.get("event", "")) if w not in GENERIC_EVENT]
                if any(len(w) >= 4 for w in ev) and ev not in events:
                    events.append(ev)
            self._people.append((entry, name, core, events))

    def find(self, text: str) -> Hit | None:
        """The known person this line is someone introducing himself as, if any."""
        tokens = words(text)
        hits: list[Hit] = []
        for entry, name, company, events in self._people:
            first, surname = name[0], name[1:]
            best: Hit | None = None
            for i, tok in enumerate(tokens):
                if not (tok == first or (len(tok) >= 3 and same_first_name(tok, first))):
                    continue
                span = 1 + (phrase_at(tokens, i + 1, surname) if surname else 0)
                full = bool(surname) and span > 1
                rest = tokens[:i] + tokens[i + span:]
                has_company = bool(company) and find_phrase(rest, company) is not None
                has_event = any(find_phrase(rest, ev) is not None for ev in events)
                if not (full or has_company or has_event):
                    continue
                if self._about_someone_else(tokens, i, span):
                    continue
                why = "full name" if full else "first name and company" if has_company else "first name and event"
                hit = Hit(entry, why, i, 2 * full + has_company + 0.5 * has_event)
                if best is None or hit.score > best.score:
                    best = hit  # "Siddharth, Siddharth Raghunathan": the second one is the full name
            if best is not None:
                hits.append(best)
        if not hits:
            return None
        hits.sort(key=lambda h: (-h.score, h.at))
        return hits[0]

    @staticmethod
    def _about_someone_else(tokens: list[str], i: int, span: int) -> bool:
        before = tokens[max(0, i - 3):i]
        if any(tuple(before[-len(s):]) == s for s in SELF if len(before) >= len(s)):
            return False
        if any(t in ABOUT_SOMEONE_ELSE for t in tokens[max(0, i - 2):i]):
            return True
        after = tokens[i + span:i + span + 1]
        return bool(after) and after[0] in AFTER_SOMEONE_ELSE


@dataclass
class Provisional:
    key: str  # the person key the history went out under
    entry: dict[str, Any]
    speaker: str
    turn: int
    hooks: list[str]  # titles of the hooks sent with it


Emit = tuple[str, int, dict[str, Any]]


class Recall:
    """The fast path for "met before", and its settling against Muse Spark's runs."""

    def __init__(
        self,
        index: list[dict[str, Any]],
        owner_name: str = "",
        owner_company: str = "",
        threads: Threads | None = None,
        exclude: str | None = None,
        before: float | None = None,
    ):
        self.index = index
        self.matcher = Matcher(index, owner_name, owner_company)
        self.threads = threads
        self.exclude = exclude
        self.before = before
        self.pending: dict[str, Provisional] = {}  # by speaker
        self._tried: set[str] = set()  # index keys already sent provisionally: once per recording

    def _same(self, person: dict[str, Any], entry: dict[str, Any]) -> bool:
        """Spark's person is this index entry: the people match, or the same first name with the surname or the
        company heard loosely alike."""
        found = match(self.index, person.get("name", ""), person.get("company", ""))
        if found is not None:
            return found["key"] == entry["key"]
        if not same_first_name(person.get("name", ""), entry.get("name", "")):
            return False
        sa, sb = words(person.get("name", ""))[1:], words(entry.get("name", ""))[1:]
        ca, cb = slug(person.get("company", "")), slug(entry.get("company", ""))
        return (bool(sa) and bool(sb) and close("".join(sa), "".join(sb))) or (bool(ca) and ca == cb)

    def on_turn(self, turn: Turn, state: dict[str, Any], sent: set[str], t_ms: int) -> list[Emit]:
        """Events for a turn just heard: a provisional person_history and its hooks, or nothing."""
        speaker = turn.speaker
        if speaker.endswith(":?") or speaker in state.get("owner_speakers", []) or speaker in self.pending:
            return []
        hit = self.matcher.find(turn.text)
        if hit is None or hit.entry["key"] in self._tried:
            return []
        entry = hit.entry
        people = state.get("people", [])
        if any(p.get("key") in sent and self._same(p, entry) for p in people):
            return []  # Spark already has him, ringed
        voice = next((p for p in people if speaker in p.get("speakers", [])), None)
        if voice is not None and not same_first_name(voice.get("name", ""), entry.get("name", "")):
            return []  # Spark already says this voice is someone else
        key = voice["key"] if voice is not None else entry["key"]
        if key in sent:
            return []
        history = history_event(entry, key, exclude=self.exclude, before=self.before)
        if not history["encounters"]:
            return []
        self._tried.add(entry["key"])
        out: list[Emit] = [("person_history", t_ms, {
            **history, "speaker": speaker, "turn": turn.turn, "provisional": True, "matched": hit.why,
        })]
        titles = []
        if self.threads is not None:
            for hook in self.threads.for_person(entry.get("name", ""), entry.get("company", ""), key):
                titles.append(hook["title"])
                out.append(("hook", t_ms, {**{("kind" if k == "type" else k): v for k, v in hook.items()}, "provisional": True}))
        self.pending[speaker] = Provisional(key, entry, speaker, turn.turn, titles)
        return out

    def after_run(self, state: dict[str, Any], seen_turn: int, sent: set[str], t_ms: int) -> list[Emit]:
        """Settle every provisional whose turn this Spark run has seen. `sent` gains the keys confirmed here."""
        out: list[Emit] = []
        people = state.get("people", [])
        for speaker, prov in list(self.pending.items()):
            if prov.turn > seen_turn:
                continue
            same = [p for p in people if self._same(p, prov.entry)]
            same.sort(key=lambda p: speaker not in p.get("speakers", []))  # this voice first
            if same:
                confirmed = same[0]["key"]
                if confirmed not in sent:  # Spark's own match did not fire (a looser spelling): confirm it here
                    sent.add(confirmed)
                    out.append(("person_history", t_ms, history_event(prov.entry, confirmed, exclude=self.exclude, before=self.before)))
                if confirmed != prov.key:
                    out += self._withdraw(prov, t_ms, f"confirmed as {confirmed}", replaced_by=confirmed)
                del self.pending[speaker]
                continue
            other = next((p for p in people if speaker in p.get("speakers", [])), None)
            if other is not None:
                out += self._withdraw(prov, t_ms, f"Muse Spark heard {other.get('name', '')} for this voice")
                del self.pending[speaker]
        return out

    def close(self, t_ms: int) -> list[Emit]:
        """The recording is over: whatever Spark never confirmed is withdrawn."""
        out: list[Emit] = []
        for speaker, prov in list(self.pending.items()):
            out += self._withdraw(prov, t_ms, "not confirmed by Muse Spark")
            del self.pending[speaker]
        return out

    @staticmethod
    def _withdraw(prov: Provisional, t_ms: int, reason: str, replaced_by: str = "") -> list[Emit]:
        data = {"key": prov.key, "speaker": prov.speaker, "reason": reason}
        if replaced_by:
            data["replaced_by"] = replaced_by
        return [("person_history_removed", t_ms, data)] + [
            ("hook_removed", t_ms, {"person_key": prov.key, "title": title}) for title in prov.hooks
        ]
