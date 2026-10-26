"""Who the owner has met, across every recording: one entry per person, with each encounter and every
promise between them. Built by folding the event logs, so it is always as fresh as the logs are.

A person is the same person when name and company match; a name alone matches when one side has no company.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import fold_record, read_events
from .extract import slug


def person_key(name: str, company: str) -> str:
    return slug(name) + ("-" + slug(company) if slug(company) else "")


def people_index(data: Path, exclude: str | None = None) -> list[dict[str, Any]]:
    """Every person met, newest encounter first; `exclude` leaves one recording out (the one in progress)."""
    index: dict[str, dict[str, Any]] = {}
    root = data / "recordings"
    if not root.exists():
        return []
    for meta_path in sorted(root.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text())
        rid = meta.get("id") or meta_path.parent.name
        if rid == exclude:
            continue
        record = fold_record(read_events(meta_path.parent / "events.jsonl"))
        names = {p["key"]: p.get("name", p["key"]) for p in record["people"]}
        for p in record["people"]:
            key = person_key(p.get("name", ""), p.get("company", ""))
            if not slug(p.get("name", "")):
                continue
            entry = index.setdefault(key, {
                "key": key, "name": p.get("name", ""), "company": p.get("company", ""), "role": p.get("role", ""),
                "language": p.get("preferred_language", ""), "encounters": [], "promises": [],
            })
            for field, value in (("company", p.get("company", "")), ("role", p.get("role", "")), ("language", p.get("preferred_language", ""))):
                if value and not entry[field]:
                    entry[field] = value
            entry["encounters"].append({
                "recording": rid, "event": meta.get("event", ""), "venue": meta.get("venue", ""),
                "started": meta.get("started", 0.0),
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
    out = list(index.values())
    for entry in out:
        entry["encounters"].sort(key=lambda e: e["started"], reverse=True)
        entry["promises"].sort(key=lambda e: e["started"], reverse=True)
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
    return None


def history_event(entry: dict[str, Any], record_key: str, exclude: str | None = None) -> dict[str, Any]:
    """The person_history payload: where the owner met them before and what passed between them."""
    return {
        "key": record_key,
        "name": entry["name"],
        "company": entry["company"],
        "encounters": [
            {k: e[k] for k in ("recording", "event", "venue", "started", "introduced_by")}
            for e in entry["encounters"] if e["recording"] != exclude
        ],
        "promises": [
            {k: q[k] for k in ("recording", "event", "started", "what", "due", "direction")}
            for q in entry["promises"] if q["recording"] != exclude
        ],
    }
