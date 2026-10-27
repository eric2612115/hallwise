"""What the owner corrected on the phone, held against what Muse Spark reads and writes.

A recording's log carries the owner's corrections as `correction` events (app.py appends them):

    {"kind": "person", "key", "name", "company", "was": {"name", "company"}}   a person's name or company, fixed
    {"kind": "word", "heard", "use"}                                           a misheard word, spelled right
    {"kind": "word_rejected", "heard", "likely"}                               a suggestion that was wrong

fold_record applies the person ones (the record, the people index and the drafts read the owner's spelling); the
word ones also go to the owner's vocabulary (vocabulary.py), which every later recording starts from.

`refine` runs on each Muse Spark result before it becomes events. A corrected person keeps the owner's name,
company and key, whatever Spark wrote. A suspect word is dropped when the owner has already settled it (spelled that
word, or rejected that pairing either way round), and when it offers a known person for someone else: on his phone
"Ken" (Ken from Vexi) came back as "maybe Kenji Watanabe", a contact with another first name at another company,
and the owner could only stare at it. A real mishearing stays: a name that sounds the same ("Margot" for Margaux),
a surname split in two ("Raghoo Nathan" for Raghunathan), or a different first name when nothing says the company
differs.
"""

from __future__ import annotations

import re
from typing import Any

from .extract import Turn, slug
from .hooks import same_first_name
from .recall import GENERIC_COMPANY
from .vocabulary import rejected_pairs

# "I'm Ken from Vexi", "I work at Corvane Capital": the company a turn names, up to four capitalised words.
COMPANY_IN_TURN = re.compile(r"\b(?:from|at)\s+([A-Z0-9][\w&'.-]*(?:\s+[A-Z0-9][\w&'.-]*){0,3})")


def apply_person_corrections(result: dict[str, Any], corrections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The owner's name and company for every corrected person key. When Spark, told about the correction, lists the
    person under a new key (the corrected spelling's, "ken-vexi"), the person and every reference to them go back
    to the key the owner corrected, so the room, the index and the drafts keep one person."""
    if not corrections:
        return result
    people = result.get("people", [])
    keys = {p.get("key", "") for p in people}

    def same(p: dict[str, Any], name: str, company: str) -> bool:
        return bool(slug(name)) and slug(p.get("name", "")) == slug(name) and slug(p.get("company", "")) == slug(company)

    rename: dict[str, str] = {}
    for p in people:
        if p.get("key") in corrections:
            continue
        for key, c in corrections.items():
            if key in keys or key in rename.values():
                continue
            was = c.get("was") or {}
            if same(p, c.get("name", ""), c.get("company", "")) or same(p, was.get("name", ""), was.get("company", "")):
                rename[p["key"]] = key
                break
    for p in people:
        p["key"] = rename.get(p.get("key", ""), p.get("key", ""))
        if p.get("introduced_by") in rename:
            p["introduced_by"] = rename[p["introduced_by"]]
        c = corrections.get(p["key"])
        if c is not None:
            p["name"], p["company"] = c.get("name", p.get("name", "")), c.get("company", p.get("company", ""))
    for q in result.get("promises", []):
        for f in ("owed_by", "owed_to"):
            if q.get(f) in rename:
                q[f] = rename[q[f]]
    for m in result.get("mentioned", []):
        if m.get("by") in rename:
            m["by"] = rename[m["by"]]
    return result


def _fold(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def settled(suspect: dict[str, Any], spellings: list[dict[str, str]], rejected: set[tuple[str, str]]) -> bool:
    """The owner already answered this one: the pairing was rejected (either way round), or the heard word is one the
    owner has spelled, as heard or as written ("Hall wise" fixed to Hallwise: "Hall wise -> Hallways" on a later
    evening asks again what the owner already said)."""
    heard, likely = _fold(suspect.get("heard")), _fold(suspect.get("likely"))
    if (heard, likely) in rejected:
        return True
    return any(heard in (_fold(w.get("heard")), _fold(w.get("use"))) for w in spellings)


def _company_words(company: str) -> set[str]:
    words = set(slug(company).split("-")) - {""}
    return (words - GENERIC_COMPANY) or words


def same_company(a: str, b: str) -> bool:
    """One company named two ways ("Corvane" and "Corvane Capital"): they share a word that says which company."""
    return bool(_company_words(a) & _company_words(b))


def offers_someone_else(
    suspect: dict[str, Any], people: list[dict[str, Any]], known: list[tuple[str, str]], turn_text: str
) -> bool:
    """The suggestion names a known person (full name or first name), the heard name is another first name, and the
    company of whoever was heard differs from that person's: the company of the person tonight who goes by the heard
    name or cites the turn, or a company the turn itself names ("I'm Ken from Vexy"). With no company to compare,
    the suggestion stays."""
    heard, likely = str(suspect.get("heard", "")), slug(str(suspect.get("likely", "")))
    if not likely or not slug(heard):
        return False
    turn = suspect.get("turn")
    theirs = [
        p.get("company", "") for p in people
        if p.get("company") and (turn in (p.get("evidence_turns") or []) or same_first_name(p.get("name", ""), heard))
    ] + COMPANY_IN_TURN.findall(turn_text or "")
    for name, company in known:
        full = slug(name)
        if likely not in (full, full.split("-")[0]):
            continue
        if same_first_name(heard, name):
            return False  # the same first name, heard another way: a real question about the spelling
        if not company or not theirs:
            return False
        return not any(same_company(c, company) for c in theirs)
    return False


def refine(
    result: dict[str, Any],
    *,
    turns: list[Turn],
    corrections: dict[str, dict[str, Any]] | None = None,
    spellings: list[dict[str, str]] | None = None,
    rejected: list[dict[str, str]] | None = None,
    known: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """A Muse Spark result with the owner's corrections held: see the module docstring."""
    result = apply_person_corrections(result, corrections or {})
    people = result.get("people", [])
    texts = {t.turn: t.text for t in turns}
    pairs = rejected_pairs({"rejected": rejected or []})
    candidates = list(known or []) + [(p.get("name", ""), p.get("company", "")) for p in people]
    result["suspect_words"] = [
        s for s in result.get("suspect_words", [])
        if not settled(s, spellings or [], pairs)
        and not offers_someone_else(s, people, candidates, texts.get(s.get("turn"), ""))
    ]
    return result
