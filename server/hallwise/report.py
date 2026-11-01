"""The morning report: what to send today and why, built once a recording is over.

research (who they are in public, rate limited) → hooks (reasons to write, across evenings) → the report:
- reach_out: one row per person to write to today, with the hook that gives the reason and the ready follow-up
  (the recording's next_move for that promise, else the hook's own draft), what research says about them, and
  their edges (what they said not to the owner, translated, and what the follow-up should do about it);
- edges: every edge of the night, by person;
- introductions: the introductions still owed;
- checked: research status per person, with sources;
- due_today: follow-ups whose reminder falls on the report's day or earlier.

Stored as data/reports/<recording>.json with `generated_at`; asking again within an hour returns that one.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .ask import latest_moves
from .events import fold_record, read_events
from .extract import LLM, draft_next_moves
from .hooks import Threads, find_hooks
from .ids import is_rid
from .people import index_key_of
from .research import Researcher, candidates
from .vocabulary import Vocabulary

REPORT_TTL_S = 3600

# Muse Spark list prices, for the cost line: $ per token, $ per search.
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 1.25e-6, 4.25e-6, 2.5e-3


def _zone(tz: str):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz) if tz else datetime.now().astimezone().tzinfo
    except Exception:
        return datetime.now().astimezone().tzinfo


def report_day(now: float, tz: str) -> str:
    """The morning the report is for: today before 15:00, else tomorrow (a report built at night is read at eight)."""
    d = datetime.fromtimestamp(now, _zone(tz))
    return (d.date() if d.hour < 15 else d.date() + timedelta(days=1)).isoformat()


def _parse(iso: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def assemble(
    rid: str,
    meta: dict[str, Any],
    record: dict[str, Any],
    moves: list[dict[str, Any]],
    hooks: list[dict[str, Any]],
    research: dict[str, Any],
    *,
    now: float,
    hooks_note: str = "",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tz = meta.get("tz", "")
    people = {p["key"]: p for p in record.get("people", [])}
    promises = {q["key"]: q for q in record.get("promises", [])}
    checks = {r.get("record_key") or r["key"]: r for r in research.get("people", [])}
    skipped = {s.get("record_key") or s["key"]: s for s in research.get("skipped", [])}

    index_of = {rk: ik for h in hooks for ik, rk in h.get("record_keys", {}).items()}

    def person(key: str, hook: dict[str, Any] | None = None) -> dict[str, Any]:
        p = people.get(key)
        if p is not None:
            return {"key": key, "index_key": index_of.get(key) or index_key_of(p),
                    "name": p.get("name", key), "company": p.get("company", ""),
                    "language": p.get("preferred_language", ""), "tonight": True}
        if hook is not None:
            i = hook["people"].index(key) if key in hook["people"] else 0
            return {"key": key, "index_key": hook["people"][i], "name": hook["names"][i], "company": "", "language": "", "tonight": False}
        return {"key": key, "index_key": key, "name": key, "company": "", "language": "", "tonight": False}

    def check(key: str) -> dict[str, Any] | None:
        if key in checks:
            r = checks[key]
            return {"status": r.get("status", "no_public_record"), "sources": r.get("sources", []),
                    "note": {"matched": "public profile matches", "partial": "company found, no public profile for them",
                             "no_public_record": "no public record found, check before sending"}.get(r.get("status", ""), "")}
        if key in skipped:
            return {"status": "unchecked", "sources": [], "note": skipped[key].get("reason", "")}
        return None

    def hooks_for(record_key: str, promise_key: str = "") -> list[dict[str, Any]]:
        return [h for h in hooks if record_key in h.get("record_keys", {}).values() or (promise_key and h.get("promise_key") == promise_key)]

    # What someone said not to the owner, translated, and what a follow-up should do about it: for the owner's eyes,
    # beside the row; the draft acts on it and never quotes it.
    edges = [{"person": person(e["person"]), **{k: e.get(k, "") for k in ("text", "act", "language", "said", "english")},
              "turns": e.get("turns") or []} for e in record.get("edges", [])]

    def edges_for(key: str) -> list[dict[str, Any]]:
        return [{k: v for k, v in e.items() if k != "person"} for e in edges if e["person"]["key"] == key]

    for h in hooks:
        h["tonight"] = bool(h.get("record_keys"))
    reach: list[dict[str, Any]] = []
    covered: set[str] = set()
    for m in moves:
        key = m.get("person_key", "")
        mine = hooks_for(key, m.get("promise_key", ""))
        q = promises.get(m.get("promise_key", ""), {})
        reach.append({
            "person": person(key),
            "hook": mine[0] if mine else None,
            "more_hooks": mine[1:],
            "followup": {"source": "next_move", "promise_key": m.get("promise_key", ""), "move": m,
                         "promise": {k: q.get(k, "") for k in ("what", "due", "replaces", "owed_to", "owed_by")}},
            "check": check(key),
        })
        covered.add(key)
    for h in hooks:
        if h["type"] == "introduction" or not h.get("draft"):
            continue
        first = h["people"][0]
        key = h.get("record_keys", {}).get(first, first)
        if key in covered:
            continue
        covered.add(key)
        reach.append({"person": person(key, h), "hook": h, "more_hooks": [],
                      "followup": {"source": "hook", "promise_key": h.get("promise_key", ""), "language": h.get("language", ""),
                                   "body": h["draft"], "body_english": h.get("draft_english", "")},
                      "check": check(key)})
    for r in reach:
        r["earlier"] = not r["person"]["tonight"] and not (r["hook"] or {}).get("tonight")
        r["edges"] = edges_for(r["person"]["key"])
    # Tonight's people with a reason first, then tonight's others, then people tied to tonight, then older threads.
    reach.sort(key=lambda r: (r["earlier"], not r["person"]["tonight"], r["hook"] is None))

    day = report_day(now, tz)
    due: list[dict[str, Any]] = []
    for m in moves:
        when = _parse(m.get("remind_at", ""))
        if when is None:
            continue
        local = when.astimezone(_zone(tz)).date().isoformat()
        if local <= day:
            q = promises.get(m.get("promise_key", ""), {})
            due.append({"promise_key": m.get("promise_key", ""), "person": person(m.get("person_key", "")),
                        "what": q.get("what", ""), "due": q.get("due", ""), "remind_at": m.get("remind_at", ""),
                        "nudge": m.get("nudge", ""), "overdue": local < day})

    named = [p for p in record.get("people", []) if p.get("name")]
    languages = sorted({m.get("language", "") for m in moves if m.get("language") and m.get("language") != "English"})
    checked = research.get("people", [])
    usage = usage or {}
    hooks_in, hooks_out = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    cost = (hooks_in + int(research.get("input_tokens") or 0)) * PRICE_IN + (
        hooks_out + int(research.get("output_tokens") or 0)) * PRICE_OUT + int(research.get("searches") or 0) * PRICE_SEARCH
    return {
        "recording": rid,
        "event": meta.get("event", ""),
        "venue": meta.get("venue", ""),
        "started": meta.get("started", 0),
        "tz": tz,
        "day": day,
        "generated_at": now,
        "summary": {
            "people": len(named),
            "followups": len([m for m in moves if m.get("kind") != "nudge"]),
            "languages": languages,
            "introductions": len([h for h in hooks if h["type"] == "introduction"]),
            "hooks": len(hooks),
            "edges": len(edges),
            "unverified": len([r for r in checked if r.get("status") == "no_public_record"]),
        },
        "reach_out": reach,
        "redrafted": [m["promise_key"] for m in moves if m.get("redrafted")],
        "introductions": [h for h in hooks if h["type"] == "introduction"],
        "checked": checked,
        "unchecked": research.get("skipped", []),
        "due_today": due,
        "hooks": hooks,
        "edges": edges,
        "notes": [n for n in (hooks_note, research.get("reason", "")) if n],
        "cost": {
            "hooks_tokens": hooks_in + hooks_out,
            "research_tokens": int(research.get("tokens") or 0),
            "research_requests": int(research.get("requests") or 0),
            "searches": int(research.get("searches") or 0),
            "usd": round(cost, 4),
        },
    }


def threads_as_hooks(data: Path, rid: str, record: dict[str, Any], meta: dict[str, Any]) -> list[dict[str, Any]]:
    """The model-free hooks (open introductions, mentions), in the report's shape: the fallback without Spark."""
    threads = Threads.load(data, exclude=rid, before=float(meta.get("started", 0) or 0) or None, tz=meta.get("tz", ""))
    out: list[dict[str, Any]] = []
    for p in record.get("people", []):
        for h in threads.for_person(p.get("name", ""), p.get("company", ""), p["key"]):
            out.append({"type": h["type"], "people": [p["key"]], "names": [p.get("name", "")],
                        "record_keys": {p["key"]: p["key"]}, "title": h["title"], "tag": h["tag"], "reason": h["reason"],
                        "evidence": [{"kind": "turn", **e} for e in h["evidence"]], "promise_key": h.get("promise_key", ""),
                        "language": p.get("preferred_language", "") or "English", "draft": "", "draft_english": ""})
    return out


class Reports:
    """Builds, keeps and serves morning reports; one build per recording at a time."""

    def __init__(self, data: Path, make_llm: Callable[[], LLM | None], researcher: Researcher,
                 clock: Callable[[], float] = time.time):
        self.data = data
        self.dir = data / "reports"
        self.make_llm = make_llm
        self.researcher = researcher
        self.clock = clock
        self._locks: dict[str, asyncio.Lock] = {}

    def path(self, rid: str) -> Path:
        return self.dir / f"{rid}.json"

    def get(self, rid: str) -> dict[str, Any] | None:
        if not is_rid(rid):
            return None
        try:
            return json.loads(self.path(rid).read_text())
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

    async def run(self, rid: str, force: bool = False) -> dict[str, Any]:
        root = self.data / "recordings" / rid
        if not is_rid(rid) or not (root / "meta.json").exists():
            raise KeyError(rid)
        lock = self._locks.setdefault(rid, asyncio.Lock())
        async with lock:
            have = self.get(rid)
            if have is not None and not force and self.clock() - float(have.get("generated_at", 0)) < REPORT_TTL_S:
                return {**have, "cached": True}
            report = await self.build(rid)
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.path(rid).with_suffix(".tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1))
            tmp.replace(self.path(rid))
            return {**report, "cached": False}

    async def build(self, rid: str) -> dict[str, Any]:
        root = self.data / "recordings" / rid
        meta = json.loads((root / "meta.json").read_text())
        events = read_events(root / "events.jsonl")
        record = fold_record(events)
        moves = latest_moves(events)
        people, skipped = candidates(record, context=", ".join(x for x in (meta.get("event", ""), meta.get("venue", "")) if x))
        research = await self.researcher.run(people, skipped)
        llm = self.make_llm()
        note = ""
        usage: dict[str, Any] = {}
        if llm is None:
            hooks, note = threads_as_hooks(self.data, rid, record, meta), "hooks without Muse Spark: open introductions and mentions only"
        else:
            try:
                hooks, _ = await find_hooks(llm, self.data, rid, research.get("people", []), moves)
                usage = _add(usage, getattr(llm, "last_usage", {}) or {})
            except Exception as err:  # the report still goes out, with the model-free hooks
                hooks = threads_as_hooks(self.data, rid, record, meta)
                note = f"hooks fell back to open introductions and mentions ({err.__class__.__name__})"
            moves, redrafted = await self.redraft(llm, record, meta, moves, hooks)
            if redrafted:
                usage = _add(usage, getattr(llm, "last_usage", {}) or {})
        return assemble(rid, meta, record, moves, hooks, research, now=self.clock(), hooks_note=note, usage=usage)

    async def redraft(
        self, llm: LLM, record: dict[str, Any], meta: dict[str, Any], moves: list[dict[str, Any]], hooks: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], bool]:
        """Drafts written at Stop without a reason to write (the recording had no `hook` events) are written
        once more with the hooks the report found, so Margaux's can say Chloé suggested it. The rest stay."""
        if record.get("hooks") or not moves:
            return moves, False
        by_person: dict[str, list[dict[str, Any]]] = {}
        for h in hooks:
            for rk in h.get("record_keys", {}).values():
                by_person.setdefault(rk, []).append(h)
        if not any(m.get("person_key") in by_person for m in moves):
            return moves, False
        try:
            fresh = await draft_next_moves(
                llm, {**record, "hooks": by_person},
                owner_name=meta.get("owner_name", ""), owner_company=meta.get("owner_company", ""),
                event=meta.get("event", ""), venue=meta.get("venue", ""), now=meta.get("now", ""), tz=meta.get("tz", ""),
                busy=meta.get("busy") or [], links=meta.get("links") or {},
                spellings=Vocabulary(self.data).load()["words"],
            )
        except Exception:  # the night's drafts are still good
            return moves, False
        new = {m["promise_key"]: {**m, "redrafted": True} for m in fresh if m.get("person_key") in by_person}
        return [new.get(m.get("promise_key", ""), m) for m in moves], bool(new)

    async def later(self, rid: str, delay_s: float) -> None:
        """The automatic run, some minutes after a recording ends: by then the drafts are in."""
        await asyncio.sleep(delay_s)
        try:
            await self.run(rid)
        except Exception as err:  # nobody is waiting on it; the POST can run it again
            print(f"report {rid}: {err.__class__.__name__}: {err}")


def _add(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {k: int(a.get(k) or 0) + int(b.get(k) or 0) for k in ("prompt_tokens", "completion_tokens")}


def report_delay_s() -> float | None:
    """HALLWISE_REPORT=off turns the automatic run off; HALLWISE_REPORT_DELAY_S sets the wait (300 s)."""
    if os.environ.get("HALLWISE_REPORT", "on") == "off":
        return None
    return float(os.environ.get("HALLWISE_REPORT_DELAY_S", 300))
