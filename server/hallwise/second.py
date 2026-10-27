"""The second listener: Muse Spark Open, on Baseten, re-hears the same transcript and the two Meta models compare.

Every Nth Muse Spark run (HALLWISE_SECOND_EVERY, default 3), and always at the end of a recording, the transcript
Spark just read goes to Muse Spark Open with a smaller schema: people (name, company, speakers), promises (owed_by,
owed_to, what, due) and suspect words. What both models agree on gets a `confirmed` event; a name spelled
differently for the same voice, or a promise one model has and the other does not, becomes a `disagreement`
event with both readings, for the owner to settle on the Words page. Each call logs a `second_run` event with its
token usage and time, so a recording's cost can be read off its log.

The comparison does not trust keys, because the two models do not share them: people are paired by speaker label
(by first name when one side has no label), promises by who they are owed to plus a normalised "what".

Rate: one call in flight at most, at least HALLWISE_SECOND_GAP_S (10) seconds apart, at most
HALLWISE_SECOND_MAX_CALLS (30) per recording. HALLWISE_SECOND=off turns it off. A failure only logs
`second_error`; the main path never waits on it, except for the last call, which runs beside the drafts.

Baseten serves the model OpenAI-style. It thinks before it answers, so max_tokens must leave room for the
reasoning or the content comes back empty (finish_reason "length"). On a rehearsal transcript it reasoned about
6,100 tokens in 20 s at its default effort and about 1,000 in 5 s with reasoning_effort "low", which it honours;
low is the default here (HALLWISE_SECOND_EFFORT). `json_schema` response formats are enforced (the output follows
the schema even where the prompt asks for another shape); `json_object` works too and is the fallback.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from .extract import _STR, _STR_LIST, _obj, slug
from .hooks import same_first_name
from .recall import fold, words

OPEN_URL = "https://inference.baseten.co/v1/chat/completions"
OPEN_MODEL = "meta-models/muse-spark-open-1026"
MAIN = "muse-spark-1.3"
OPEN = "muse-spark-open"

SECOND_SCHEMA: dict[str, Any] = _obj(
    people={
        "type": "array",
        "items": _obj(
            name={**_STR, "description": "as the person introduced themselves"},
            company=_STR,
            speakers={**_STR_LIST, "description": "speaker keys this person spoke as"},
        ),
    },
    promises={
        "type": "array",
        "items": _obj(
            owed_by={**_STR, "description": "'owner' or a name from people"},
            owed_to={**_STR, "description": "'owner' or a name from people"},
            what={**_STR, "description": "a few words, e.g. 'send the deck'"},
            due={**_STR, "description": "as finally agreed, e.g. 'Friday'; empty if none"},
            turn={"type": "integer", "description": "the turn where it was agreed"},
        ),
    },
    suspect_words={
        "type": "array",
        "items": _obj(heard=_STR, turn={"type": "integer"}, likely=_STR),
    },
)

SECOND_SYSTEM = """You read a live transcript from a badge worn at a networking event and list, for the person
wearing it (the owner), who he met and what was promised.

The transcript has numbered turns with a speaker key ("<session>:<label>"). Labels come from automatic speaker
separation: they are not names.

Rules:
- Name people only from what is said: self-introductions ("I'm Sarah from Acme"), being addressed by name, a
  spelled-out name. Never guess. Use the spelling from the person's own introduction. A person may speak under more
  than one speaker key; list them all in speakers.
- The owner is given below. Never put him in people.
- Only exchanges with the owner count. Ignore small talk with staff ("something to drink?") and other people's
  conversations nearby.
- A promise is a commitment to do something later, by the owner or to the owner. owed_by and owed_to are "owner"
  or the person's name exactly as in people. When it is corrected ("Thursday — no, Friday"), keep one promise with
  the final version in due.
- suspect_words: names, companies and product terms the transcriber probably got wrong; likely = your best guess.
- Never infer accent, nationality, ethnicity or personality."""

LLM = Callable[..., Awaitable[dict[str, Any]]]


class OpenClient:
    """Muse Spark Open over Baseten's Chat Completions endpoint, JSON-schema output."""

    def __init__(self, api_key: str, model: str = OPEN_MODEL, effort: str = "low", max_tokens: int = 8000, timeout: float = 60,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.transport = transport
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.last_usage: dict[str, Any] = {}
        self.last_seconds = 0.0

    async def __call__(self, system: str, user: str, schema: dict[str, Any] = SECOND_SCHEMA, name: str = "hallwise_second") -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
        }
        if self.effort:
            body["reasoning_effort"] = self.effort
        started = time.monotonic()
        usage: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                for attempt in (1, 2):  # now and then the answer is cut off mid-string: one more try, then give up
                    response = await client.post(OPEN_URL, json=body, headers={"Authorization": f"Api-Key {self.api_key}"})
                    if response.status_code in (400, 422) and body["response_format"]["type"] == "json_schema":
                        # a schema the server will not take: ask for JSON and say the shape in the prompt
                        body["response_format"] = {"type": "json_object"}
                        body["messages"][1]["content"] = user + "\n\nReply with JSON matching this schema:\n" + json.dumps(schema)
                        response = await client.post(OPEN_URL, json=body, headers={"Authorization": f"Api-Key {self.api_key}"})
                    response.raise_for_status()
                    data = response.json()
                    usage = _add_usage(usage, data.get("usage") or {})
                    choice = data["choices"][0]
                    content = choice["message"].get("content") or ""
                    why = f"finish_reason {choice.get('finish_reason')}, {(data.get('usage') or {}).get('completion_tokens')} tokens"
                    if not content.strip():
                        error: Exception = ValueError(f"empty content ({why}): max_tokens too low for the reasoning?")
                    else:
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError as err:
                            error = ValueError(f"invalid JSON ({why}): {err}")
                    if attempt == 2:
                        raise error
            raise AssertionError("unreachable")
        finally:
            self.last_usage = usage
            self.last_seconds = time.monotonic() - started


def _add_usage(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Two calls' usage as one: a retry costs tokens too."""
    out = {k: int(a.get(k) or 0) + int(b.get(k) or 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    out["completion_tokens_details"] = {"reasoning_tokens": int((a.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
                                        + int((b.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)}
    return out


def validate(raw: Any) -> dict[str, Any]:
    """Whatever came back, in the reduced schema's shape: malformed items dropped, fields as strings."""
    def s(x: Any) -> str:
        return x.strip() if isinstance(x, str) else ""

    def n(x: Any) -> int:
        try:
            return int(x)
        except (TypeError, ValueError):
            return -1

    raw = raw if isinstance(raw, dict) else {}
    people = [
        {"name": s(p.get("name")), "company": s(p.get("company")),
         "speakers": [x for x in p.get("speakers", []) if isinstance(x, str)] if isinstance(p.get("speakers"), list) else []}
        for p in raw.get("people", []) if isinstance(p, dict) and s(p.get("name"))
    ]
    promises = [
        {"owed_by": s(q.get("owed_by")), "owed_to": s(q.get("owed_to")), "what": s(q.get("what")), "due": s(q.get("due")),
         "turn": n(q.get("turn"))}
        for q in raw.get("promises", []) if isinstance(q, dict) and s(q.get("what"))
    ]
    suspects = [
        {"heard": s(w.get("heard")), "turn": n(w.get("turn")), "likely": s(w.get("likely"))}
        for w in raw.get("suspect_words", []) if isinstance(w, dict) and s(w.get("heard"))
    ]
    return {"people": people, "promises": promises, "suspect_words": suspects}


# --- comparing the two readings -------------------------------------------------------------------------------

STOP = {
    "the", "a", "an", "to", "our", "your", "my", "his", "her", "their", "of", "for", "with", "on", "by", "at", "in",
    "and", "send", "sends", "sending", "give", "share", "me", "you", "him", "them", "us", "i", "we", "will", "some",
    "it", "over", "up", "get", "do", "make", "about", "this", "that",
}


def what_words(text: str) -> list[str]:
    """'Send our one-pager!' -> ['one', 'pager']: the words that say what the promise is."""
    out = []
    for w in words(text):
        if w in STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def what_similarity(a: str, b: str) -> float:
    """0..1: how far two promises' "what" say the same thing, forgiving wording and near spellings."""
    wa, wb = what_words(a), what_words(b)
    if not wa or not wb:
        return 0.0

    def near(x: str, y: str) -> bool:
        return x == y or (min(len(x), len(y)) >= 4 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.8)

    shared = sum(1 for x in wa if any(near(x, y) for y in wb))
    contain = shared / min(len(wa), len(wb))
    joined = difflib.SequenceMatcher(None, " ".join(wa), " ".join(wb)).ratio()
    return max(contain, joined)


def same_due(a: str, b: str) -> bool:
    """Empty on either side, or a word in common ("Wednesday afternoon" and "next week, Wednesday")."""
    wa = set(words(a)) - {"by", "on", "the", "at", "in", "next", "this"}
    wb = set(words(b)) - {"by", "on", "the", "at", "in", "next", "this"}
    return not wa or not wb or bool(wa & wb)


def same_name(a: str, b: str) -> bool:
    """The same spelling once case, accents, spacing and punctuation are set aside."""
    return "".join(words(a)) == "".join(words(b))


def first_evidence(item: dict[str, Any]) -> int:
    turns = [t for t in item.get("evidence_turns", []) if isinstance(t, int)]
    return min(turns) if turns else -1


@dataclass
class Comparison:
    confirmed: dict[str, dict[str, Any]] = field(default_factory=dict)  # id ("person:key") -> event data
    disagreements: dict[str, dict[str, Any]] = field(default_factory=dict)  # id -> event data


def compare(spark: dict[str, Any], other: dict[str, Any], upto_turn: int) -> Comparison:
    """Spark's current picture against Spark Open's reading of the transcript up to `upto_turn`. Spark items
    first evidenced after that turn are left out: Open never heard them."""
    out = Comparison()
    by = [MAIN, OPEN]
    s_people = [p for p in spark.get("people", []) if first_evidence(p) <= upto_turn]
    o_people = list(other.get("people", []))

    # People: by speaker label first, the most shared labels win; then by first name for whoever is left (one side
    # had no label for them, or the labels split differently).
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    free = list(range(len(o_people)))
    rest: list[dict[str, Any]] = []
    for p in s_people:
        mine = set(p.get("speakers", []))
        overlaps = [(len(mine & set(o_people[j].get("speakers", []))), -j) for j in free]
        k, j = max(overlaps, default=(0, 0))
        if k > 0:
            free.remove(-j)
            pairs.append((p, o_people[-j]))
        else:
            rest.append(p)
    for p in rest:
        j = next((j for j in free if same_first_name(o_people[j]["name"], p.get("name", ""))), None)
        if j is not None:
            free.remove(j)
            pairs.append((p, o_people[j]))
    open_to_spark: dict[str, str] = {}  # Open's name (folded) -> Spark key
    for p, o in pairs:
        open_to_spark[fold(o["name"])] = p["key"]
        speaker = next(iter(sorted(set(p.get("speakers", [])) & set(o.get("speakers", [])))), (p.get("speakers") or [""])[0])
        turn = first_evidence(p)
        name_ok = same_name(p.get("name", ""), o["name"])
        prefix = not name_ok and (words(o["name"]) == words(p.get("name", ""))[:len(words(o["name"]))]
                                  or words(p.get("name", "")) == words(o["name"])[:len(words(p.get("name", "")))])
        company_ok = not p.get("company") or not o["company"] or same_name(p["company"], o["company"])
        if not name_ok and not prefix:
            out.disagreements[f"person:{p['key']}:name"] = {
                "kind": "person", "field": "name", "key": p["key"], "speaker": speaker, "turn": turn,
                "a": {"by": MAIN, "text": p.get("name", "")}, "b": {"by": OPEN, "text": o["name"]},
            }
        if not company_ok:
            out.disagreements[f"person:{p['key']}:company"] = {
                "kind": "person", "field": "company", "key": p["key"], "speaker": speaker, "turn": turn,
                "a": {"by": MAIN, "text": p.get("company", "")}, "b": {"by": OPEN, "text": o["company"]},
            }
        if name_ok and company_ok:
            out.confirmed[f"person:{p['key']}"] = {"kind": "person", "key": p["key"], "by": by}

    # Promises: who it is owed to (and by), resolved to Spark's keys, plus what it is. Spark's promises may point at a
    # person it never listed (a voice the transcriber merged into someone else's turn): their keys count too.
    spark_names = {p["key"]: p.get("name", "") for p in spark.get("people", [])}
    for q in spark.get("promises", []):
        for f in ("owed_by", "owed_to"):
            k = q.get(f, "")
            if k and k != "owner" and k not in spark_names:
                spark_names[k] = ""

    def party(name: str) -> str:
        n = fold(name).strip()
        if not n or n in ("owner", "me", "the owner"):
            return "owner" if n else ""
        if n in open_to_spark:
            return open_to_spark[n]
        if slug(name) in spark_names:
            return slug(name)
        for key, sname in spark_names.items():
            if same_name(sname, name) or (not sname and key.startswith(slug(name) + "-")):
                return key
        firsts = [key for key, sname in spark_names.items()
                  if same_first_name(sname or key.split("-")[0], name)]
        return firsts[0] if len(firsts) == 1 else "?" + slug(name)

    s_promises = [q for q in spark.get("promises", []) if first_evidence(q) <= upto_turn]
    o_promises = [{**q, "_by": party(q["owed_by"]), "_to": party(q["owed_to"])} for q in other.get("promises", [])]
    used: set[int] = set()
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unmatched_s: list[dict[str, Any]] = []
    for q in s_promises:
        cands = [(what_similarity(q.get("what", ""), o["what"]), j) for j, o in enumerate(o_promises)
                 if j not in used and o["_to"] == q.get("owed_to") and o["_by"] == q.get("owed_by")]
        cands.sort(reverse=True)
        if cands and cands[0][0] >= 0.5:
            used.add(cands[0][1])
            matched.append((q, o_promises[cands[0][1]]))
        else:
            unmatched_s.append(q)
    # One promise each between the owner and that person, worded differently: still the same promise.
    for q in list(unmatched_s):
        same_pair = [j for j, o in enumerate(o_promises)
                     if j not in used and o["_to"] == q.get("owed_to") and o["_by"] == q.get("owed_by")]
        others = [x for x in unmatched_s if x is not q and x.get("owed_to") == q.get("owed_to") and x.get("owed_by") == q.get("owed_by")]
        if len(same_pair) == 1 and not others:
            used.add(same_pair[0])
            matched.append((q, o_promises[same_pair[0]]))
            unmatched_s.remove(q)

    def who(key: str) -> str:
        return "you" if key == "owner" else spark_names.get(key, key.lstrip("?").replace("-", " ").title())

    def reading(what: str, due: str, owed_by: str, owed_to: str) -> str:
        """'our deck · tonight · to Leo Wong', 'intro to his CTO · from Leo Wong'."""
        side = f"to {who(owed_to)}" if owed_by == "owner" else f"from {who(owed_by)}"
        return what + (f" · {due}" if due else "") + f" · {side}"

    for q, o in matched:
        if same_due(q.get("due", ""), o["due"]):
            out.confirmed[f"promise:{q['key']}"] = {"kind": "promise", "key": q["key"], "by": by}
        else:
            out.disagreements[f"promise:{q['key']}:due"] = {
                "kind": "promise", "field": "due", "key": q["key"], "turn": first_evidence(q),
                "owed_by": q.get("owed_by", ""), "owed_to": q.get("owed_to", ""),
                "a": {"by": MAIN, "text": q.get("due", "")}, "b": {"by": OPEN, "text": o["due"]},
            }
    for q in unmatched_s:
        out.disagreements[f"promise:{q['key']}:exists"] = {
            "kind": "promise", "field": "exists", "key": q["key"], "turn": first_evidence(q),
            "owed_by": q.get("owed_by", ""), "owed_to": q.get("owed_to", ""), "what": q.get("what", ""), "due": q.get("due", ""),
            "a": {"by": MAIN, "text": reading(q.get("what", ""), q.get("due", ""), q.get("owed_by", ""), q.get("owed_to", ""))},
            "b": {"by": OPEN, "text": ""},
        }
    for j, o in enumerate(o_promises):
        if j in used or not o["_by"] or not o["_to"]:
            continue
        to = o["_to"] if o["_by"] == "owner" else o["_by"]
        key = f"open-{slug(o['what'])}-{slug(to.lstrip('?'))}"
        out.disagreements[f"promise:{key}:exists"] = {
            "kind": "promise", "field": "exists", "key": "", "open_key": key, "turn": o.get("turn", -1),
            "owed_by": o["_by"].lstrip("?"), "owed_to": o["_to"].lstrip("?"), "what": o["what"], "due": o["due"],
            "a": {"by": MAIN, "text": ""}, "b": {"by": OPEN, "text": reading(o["what"], o["due"], o["_by"], o["_to"])},
        }
    return out


# --- the listener, rate-limited, inside a recording -----------------------------------------------------------

Emit = tuple[str, int, dict[str, Any]]
Sink = Callable[..., Any]  # (type, t_ms, **data): the recording's log


class SecondListener:
    """Decides when Spark Open runs, runs it, and turns each comparison into events (new or withdrawn only)."""

    def __init__(self, llm: LLM, *, every: int = 3, min_gap_s: float = 10.0, max_calls: int = 30,
                 model: str = OPEN, clock: Callable[[], float] = time.monotonic):
        self.llm = llm
        self.every = max(1, every)
        self.min_gap_s = min_gap_s
        self.max_calls = max_calls
        self.model = model
        self.clock = clock
        self.calls = 0
        self.runs = 0  # Muse Spark runs seen
        self.wanted = False  # a call is due and waits for the gap
        self.last_start = float("-inf")
        self.task: asyncio.Task[None] | None = None
        self.confirmed: dict[str, dict[str, Any]] = {}
        self.disagreements: dict[str, dict[str, Any]] = {}
        self.totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "seconds": 0.0}

    @classmethod
    def from_env(cls) -> "SecondListener | None":
        key = os.environ.get("BASETEN_API_KEY")
        if os.environ.get("HALLWISE_SECOND", "on") == "off" or not key:
            return None
        return cls(
            OpenClient(key, model=os.environ.get("HALLWISE_SECOND_MODEL", OPEN_MODEL),
                       effort=os.environ.get("HALLWISE_SECOND_EFFORT", "low"),
                       max_tokens=int(os.environ.get("HALLWISE_SECOND_MAX_TOKENS", "8000"))),
            every=int(os.environ.get("HALLWISE_SECOND_EVERY", "3")),
            min_gap_s=float(os.environ.get("HALLWISE_SECOND_GAP_S", "10")),
            max_calls=int(os.environ.get("HALLWISE_SECOND_MAX_CALLS", "30")),
        )

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    def can_start(self) -> bool:
        return not self.busy and self.calls < self.max_calls and self.clock() - self.last_start >= self.min_gap_s

    def after_spark_run(self, sink: Sink, prompt: Callable[[], str], spark: Callable[[], dict[str, Any]],
                        upto_turn: int, now_ms: Callable[[], int]) -> bool:
        """Count one Muse Spark run, and start a call in the background when one is due and allowed. A call
        that is due but too soon after the last one starts after a later run."""
        self.runs += 1
        if self.runs % self.every == 0:
            self.wanted = True
        if not (self.wanted and self.can_start()):
            return False
        text, call = prompt(), self._begin()
        self.task = asyncio.get_running_loop().create_task(self._run(sink, text, spark, upto_turn, now_ms, False, call))
        return True

    def _begin(self) -> int:
        """Book a call the moment it is decided on, so the gap and the cap count from then."""
        self.wanted = False
        self.calls += 1
        self.last_start = self.clock()
        return self.calls

    async def finish(self, sink: Sink, prompt: Callable[[], str], spark: Callable[[], dict[str, Any]],
                     upto_turn: int, now_ms: Callable[[], int]) -> None:
        """The recording ended: wait for a call in flight, keep the gap, then one last call on everything."""
        if self.task is not None:
            await self.task
        if self.calls >= self.max_calls:
            return
        wait = self.min_gap_s - (self.clock() - self.last_start)
        if wait > 0:
            await asyncio.sleep(wait)
        await self._run(sink, prompt(), spark, upto_turn, now_ms, True, self._begin())

    async def _run(self, sink: Sink, prompt: str, spark: Callable[[], dict[str, Any]], upto_turn: int,
                   now_ms: Callable[[], int], final: bool, call: int) -> None:
        try:
            events = await self.listen(prompt, spark, upto_turn, now_ms, final=final, call=call)
        except Exception as err:  # never the main path's problem
            events = [("second_error", now_ms(), {"model": self.model, "message": f"{err.__class__.__name__}: {err}"[:300]})]
        for kind, t_ms, data in events:
            try:
                sink(kind, t_ms, **data)
            except Exception:
                return  # the log is closed

    async def listen(self, prompt: str, spark: Callable[[], dict[str, Any]], upto_turn: int, now_ms: Callable[[], int],
                     final: bool = False, call: int | None = None) -> list[Emit]:
        """One call and its comparison. `spark` gives Spark's picture when the answer is back, so the comparison
        is against what the room shows now."""
        if call is None:
            call = self._begin()
        started = time.monotonic()
        try:
            raw = await self.llm(SECOND_SYSTEM, prompt, schema=SECOND_SCHEMA, name="hallwise_second")
        except Exception as err:
            return [("second_error", now_ms(), {"model": self.model, "call": call, "final": final,
                                                "message": f"{err.__class__.__name__}: {err}"[:300]})]
        seconds = round(getattr(self.llm, "last_seconds", 0.0) or (time.monotonic() - started), 2)
        usage_raw = getattr(self.llm, "last_usage", {}) or {}
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
            "reasoning_tokens": int((usage_raw.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
            "total_tokens": int(usage_raw.get("total_tokens") or 0),
        }
        result = validate(raw)
        picture = spark()
        cmp = compare(picture, result, upto_turn)
        t = now_ms()
        out: list[Emit] = []
        for cid, data in cmp.confirmed.items():
            if cid not in self.confirmed:
                out.append(("confirmed", t, data))
        for cid, data in self.confirmed.items():
            if cid not in cmp.confirmed:
                out.append(("confirmed_removed", t, {"kind": data["kind"], "key": data["key"]}))
        self.confirmed = cmp.confirmed
        # A disagreement stays until the two models agree on that item, Spark drops the item, or the owner settles
        # it on the phone: a later run that words an Open-only promise differently does not raise it twice.
        keys = {"person": {p.get("key") for p in picture.get("people", [])},
                "promise": {q.get("key") for q in picture.get("promises", [])}}
        for did, data in list(self.disagreements.items()):
            key = data.get("key")
            if did in cmp.disagreements:
                continue
            if key:
                settled = f"{data['kind']}:{key}" in cmp.confirmed or key not in keys.get(data["kind"], set())
            else:  # a promise only Open heard: gone once Open no longer has it on its own, in any wording
                settled = not any(self._same_open_only(data, d) for d in cmp.disagreements.values())
            if settled:
                del self.disagreements[did]
                out.append(("disagreement_removed", t, {"id": did}))
        for did, data in cmp.disagreements.items():
            if did in self.disagreements or any(self._same_open_only(data, d) for d in self.disagreements.values()):
                continue
            self.disagreements[did] = data
            out.append(("disagreement", t, {"id": did, **data}))
        self.totals["calls"] += 1
        self.totals["seconds"] = round(self.totals["seconds"] + seconds, 2)
        for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
            self.totals[k] += usage[k]
        out.insert(0, ("second_run", t, {
            "model": self.model, "call": call, "final": final, "upto_turn": upto_turn, "seconds": seconds,
            "usage": usage, "people": len(result["people"]), "promises": len(result["promises"]),
            "suspect_words": result["suspect_words"][:12],
            "agreed": len(cmp.confirmed), "disagreed": len(cmp.disagreements), "totals": dict(self.totals),
        }))
        return out

    @staticmethod
    def _same_open_only(a: dict[str, Any], b: dict[str, Any]) -> bool:
        """Two readings of one promise only Open heard, worded differently from one run to the next."""
        return all(not d.get("key") and d.get("field") == "exists" for d in (a, b)) and a.get("owed_to") == b.get(
            "owed_to") and a.get("owed_by") == b.get("owed_by") and what_similarity(a.get("what", ""), b.get("what", "")) >= 0.5
