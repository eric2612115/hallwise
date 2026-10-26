"""Ask Hallwise about tonight.

A question, typed or spoken, answered by Muse Spark over the record: who you met, what you promised, what was
said, the follow-ups drafted. The answer comes back in the language of the question, with proper nouns spelled
as the record spells them, and with the few actions the owner can take by asking (mark a promise done, remember
a word, open a draft).
"""

from __future__ import annotations

from typing import Any

from .extract import LLM, _INT_LIST, _STR, _STR_LIST, _obj, slug  # noqa: F401

ASK_SCHEMA: dict[str, Any] = _obj(
    answer={**_STR, "description": "the reply, in the language of the question"},
    actions={
        "type": "array",
        "items": _obj(
            type={"type": "string", "enum": ["mark_done", "add_word", "open_draft", "none"]},
            promise_key={**_STR, "description": "for mark_done / open_draft"},
            word={**_STR, "description": "for add_word: the name or term to remember"},
        ),
    },
)

ASK_SYSTEM = """You are Hallwise, the assistant of the person who wore the badge tonight (the owner). You answer
questions about the record below: the people met, what they said, what was promised, and the follow-ups already
drafted. You also take a few actions when asked.

Rules:
- Answer only from the record. If the record does not say, say that in one short sentence; never invent names,
  dates or quotes.
- Answer in the language the question is asked in. Mixed Chinese and English stays mixed: keep every proper
  noun (people, companies, products, places) exactly as the record spells it, in Latin letters, do not translate
  or transliterate them. A Chinese question gets Traditional Chinese.
- Answer every part of a multi-part question, in order. Be short: under 80 words. When listing, one line per item. Refer to people by first name once their full
  name is clear.
- Promises: say who owes what to whom and the due date as finally agreed; mention a correction only if asked.
- Follow-ups: when a draft exists for a promise, say so and offer it; open_draft with its promise_key when the
  owner asks to see, send or check it.
- Actions: mark_done when the owner says a promise is done, sent, or handled; add_word when the owner says to
  remember, add, or spell a name or term; otherwise none. Actions carry the exact key from the record. Confirm
  what you did in the answer."""


def build_ask_prompt(
    record: dict[str, Any],
    moves: list[dict[str, Any]],
    *,
    owner_name: str,
    owner_company: str,
    event: str = "",
    venue: str = "",
    keywords: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    question: str,
) -> str:
    translations = record.get("translations", {})
    kinds = record.get("turn_kinds", {})
    speakers: dict[str, str] = {}
    for p in record.get("people", []):
        for s in p.get("speakers", []):
            speakers[s] = p.get("name", p["key"])
    for s in record.get("owner_speakers", []):
        speakers[s] = owner_name or "owner"
    people_lines = [
        f"- {p['key']} | {p.get('name', '')}, {p.get('company', '')}"
        + (f", {p['role']}" if p.get("role") else "")
        + (f" | speaks {p['preferred_language']}" if p.get("preferred_language") else "")
        + (f" | introduced by {p['introduced_by']}" if p.get("introduced_by") else "")
        for p in record.get("people", [])
    ] or ["- nobody yet"]
    promise_lines = [
        f"- {q['key']} | owed_by: {q.get('owed_by', '')} | owed_to: {q.get('owed_to', '')} | what: {q.get('what', '')}"
        + (f" | due: {q['due']}" if q.get("due") else "")
        + (f" | earlier: {q['replaces']}" if q.get("replaces") else "")
        for q in record.get("promises", [])
    ] or ["- none yet"]
    move_lines = [
        f"- {m['promise_key']} | {m.get('kind', '')} to {m.get('person_key', '')}"
        + (f" in {m['language']}" if m.get("language") else "")
        + (f" | proposed {m['when']}" if m.get("when") else "")
        + (f" | attach {m['attach']}" if m.get("attach") else "")
        for m in moves
    ] or ["- none yet"]
    lines = [
        f"Owner: {owner_name or 'unknown'}" + (f", from {owner_company}" if owner_company else ""),
        "Event: " + (", ".join(x for x in (event, venue) if x) or "unknown"),
        "Words the owner has confirmed: " + (", ".join(keywords or []) or "none"),
        "",
        "People:",
        *people_lines,
        "",
        "Promises:",
        *promise_lines,
        "",
        "Follow-ups drafted:",
        *move_lines,
        "",
        "Transcript (conversation turns):",
    ]
    for t in record.get("turns", []):
        if kinds.get(t["turn"], "conversation") != "conversation":
            continue
        who = speakers.get(t.get("speaker", ""), "someone")
        line = f"turn {t['turn']} [{who}]: {t.get('text', '')}"
        tr = translations.get(t["turn"])
        if tr:
            line += f"  (English: {tr.get('english', '')})"
        lines.append(line)
    if history:
        lines += ["", "Earlier in this conversation with the owner:"]
        for h in history[-6:]:
            lines += [f"Owner: {h.get('q', '')}", f"Hallwise: {h.get('a', '')}"]
    lines += ["", f"Owner asks: {question}"]
    return "\n".join(lines)


async def answer(llm: LLM, record: dict[str, Any], moves: list[dict[str, Any]], **context: Any) -> dict[str, Any]:
    result = await llm(ASK_SYSTEM, build_ask_prompt(record, moves, **context), schema=ASK_SCHEMA, name="hallwise_ask")
    known = {q["key"] for q in record.get("promises", [])}
    actions = []
    for a in result.get("actions", []):
        a = {"type": a.get("type", "none"), "promise_key": slug(a.get("promise_key", "")), "word": (a.get("word") or "").strip()}
        if a["type"] in ("mark_done", "open_draft") and a["promise_key"] not in known:
            continue
        if a["type"] == "add_word" and not a["word"]:
            continue
        if a["type"] != "none":
            actions.append(a)
    return {"answer": result.get("answer", ""), "actions": actions}


def latest_moves(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The newest next_move per promise, in order of first appearance."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.get("type") == "next_move" and e.get("promise_key"):
            out[e["promise_key"]] = e
    return list(out.values())
