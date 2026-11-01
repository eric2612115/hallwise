"""Who the owner has met, across every recording: one entry per person, with each encounter and every
promise between them. Built by folding the event logs, so it is always as fresh as the logs are.

A person is the same person when name and company match; a name alone matches when one side has no company.

A person the owner corrected on the phone (fold_record applies the `correction`) keeps the key they had as heard,
so their face, their research and the app's references stay where they are, while the entry shows, and matches on,
the owner's spelling: "Ken, Vexy" corrected to Vexi stays `ken-vexy`, reads "Ken, Vexi", and a later evening that
hears "Ken from Vexi" lands on the same entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import fold_record, read_events
from .extract import slug
from .places import parse_place


def person_key(name: str, company: str) -> str:
    return slug(name) + ("-" + slug(company) if slug(company) else "")


def index_key_of(person: dict[str, Any]) -> str:
    """A folded person's people-index key: from the name and company as first heard when the owner corrected them,
    so a correction never moves them to another key; from the name and company otherwise."""
    if person.get("corrected") and slug(person.get("heard_name", "")):
        return person_key(person.get("heard_name", ""), person.get("heard_company", ""))
    return person_key(person.get("name", ""), person.get("company", ""))


def people_index(data: Path, exclude: str | None = None) -> list[dict[str, Any]]:
    """Every person met, newest encounter first; `exclude` leaves one recording out (the one in progress)."""
    index: dict[str, dict[str, Any]] = {}
    root = data / "recordings"
    if not root.exists():
        return []
    records: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for meta_path in sorted(root.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text())
        rid = meta.get("id") or meta_path.parent.name
        if rid == exclude:
            continue
        records.append((meta, rid, fold_record(read_events(meta_path.parent / "events.jsonl"))))
    # The owner's spelling of a corrected person leads to the key they keep, from any evening. Except when that
    # spelling is someone met before the correction's evening: then the owner has said who it was ("Ken, Vexy" is
    # Kenji Watanabe), and the corrected person joins that entry rather than taking it over.
    def started(meta: dict[str, Any]) -> float:
        return float(meta.get("started", 0) or 0)

    first_heard: dict[str, float] = {}
    for meta, _, record in records:
        for p in record["people"]:
            if not p.get("corrected"):
                k = person_key(p.get("name", ""), p.get("company", ""))
                first_heard[k] = min(first_heard.get(k, started(meta)), started(meta))
    aliases: dict[str, str] = {}
    for meta, _, record in records:
        for p in record["people"]:
            if p.get("corrected") and slug(p.get("name", "")):
                fixed, kept = person_key(p.get("name", ""), p.get("company", "")), index_key_of(p)
                if fixed == kept:
                    continue
                if first_heard.get(fixed, started(meta)) < started(meta):
                    aliases.setdefault(kept, fixed)
                else:
                    aliases.setdefault(fixed, kept)
    for meta, rid, record in records:
        names = {p["key"]: p.get("name", p["key"]) for p in record["people"]}
        place = parse_place(meta.get("place"), name=meta.get("venue", ""))
        for p in record["people"]:
            key = index_key_of(p)
            key = aliases.get(key, key)
            if not slug(p.get("name", "")):
                continue
            entry = index.setdefault(key, {
                "key": key, "name": p.get("name", ""), "company": p.get("company", ""), "role": p.get("role", ""),
                "language": p.get("preferred_language", ""), "encounters": [], "promises": [], "edges": [],
            })
            if p.get("corrected"):  # the owner's spelling wins over any evening's hearing of it
                entry["name"], entry["company"] = p.get("name", ""), p.get("company", "")
            for field, value in (("company", p.get("company", "")), ("role", p.get("role", "")), ("language", p.get("preferred_language", ""))):
                if value and not entry[field]:
                    entry[field] = value
            entry["encounters"].append({
                "recording": rid, "event": meta.get("event", ""), "venue": meta.get("venue", ""),
                "place": place, "started": meta.get("started", 0.0),
                "introduced_by": names.get(p.get("introduced_by", ""), "" if p.get("introduced_by", "") != "owner" else ""),
                "record_key": p["key"],
            })
            for q in record["promises"]:
                if p["key"] in (q.get("owed_by"), q.get("owed_to")):
                    entry["promises"].append({
                        "recording": rid, "event": meta.get("event", ""), "started": meta.get("started", 0.0),
                        "what": q.get("what", ""), "due": q.get("due", ""),
                        "direction": "owner_owes" if q.get("owed_by") == "owner" else ("they_owe" if q.get("owed_to") == "owner" else "between_others"),
                    })
            for e in record.get("edges", []):  # what they said not to the owner, and what it shows they want
                if e.get("person") == p["key"]:
                    entry["edges"].append({"recording": rid, "event": meta.get("event", ""), "started": meta.get("started", 0.0),
                                           "text": e.get("text", ""), "act": e.get("act", "")})
    out = list(index.values())
    faces = data / "faces"
    for entry in out:
        entry["face"] = (faces / f"{entry['key']}.jpg").exists()
        entry["encounters"].sort(key=lambda e: e["started"], reverse=True)
        entry["promises"].sort(key=lambda e: e["started"], reverse=True)
        entry["edges"].sort(key=lambda e: e["started"], reverse=True)
    out.sort(key=lambda e: e["encounters"][0]["started"] if e["encounters"] else 0, reverse=True)
    return out


def match(index: list[dict[str, Any]], name: str, company: str) -> dict[str, Any] | None:
    """The index entry for a person just introduced, if the owner has met them before."""
    key = person_key(name, company)
    for entry in index:
        if entry["key"] == key:
            return entry
    n = slug(name)
    if not n:
        return None
    for entry in index:
        if slug(entry["name"]) == n and (not slug(company) or not slug(entry["company"])):
            return entry
    # Surnames are what transcribers get wrong ("Ragoo Nathan" for Raghunathan): first name plus company
    # is the same person.
    first, co = n.split("-")[0], slug(company)
    if co:
        for entry in index:
            if slug(entry["name"]).split("-")[0] == first and slug(entry["company"]) == co:
                return entry
    return None


def history_event(
    entry: dict[str, Any], record_key: str, exclude: str | None = None, before: float | None = None
) -> dict[str, Any]:
    """The person_history payload: where the owner met them before this recording and what passed between
    them. `before` is this recording's start, so a later evening never counts as "before"."""
    def earlier(x: dict[str, Any]) -> bool:
        return x["recording"] != exclude and (before is None or x.get("started", 0) < before)

    return {
        "key": record_key,
        "index_key": entry["key"],  # where their face and their research are kept
        "name": entry["name"],
        "company": entry["company"],
        "encounters": [
            {k: e[k] for k in ("recording", "event", "venue", "started", "introduced_by")}
            for e in entry["encounters"] if earlier(e)
        ],
        "promises": [
            {k: q[k] for k in ("recording", "event", "started", "what", "due", "direction")}
            for q in entry["promises"] if earlier(q)
        ],
    }
