"""The edge finder: Muse Spark Open, on Baseten, reads the transcript as it grows and finds edges.

An edge is what someone said not to the owner (an aside to themselves, side talk with a colleague, words in another
language) that shows what they want, dislike or plan: "Said to herself, in French: 'one page, with numbers'". Every
Nth Muse Spark run (HALLWISE_SECOND_EVERY, default 3), and always at the end of a recording, the transcript Spark
just read, with the people Spark has listed (their keys and speaker keys), goes to Muse Spark Open with the edge
schema (extract.SCHEMA's edges: person, turns, language, said, english, text, act). Its edges go through the same
check as Spark's own (extract.kept_edges: someone in people, their `said` words in one of their own turns), and the
Extractor holds them (Extractor.take_edges), so the record, the drafts and the morning report get them as `edge`
events, as before.

While it is on, Muse Spark looks for no edges itself (extract.SYSTEM_NO_EDGES, SCHEMA_NO_EDGES). Off (HALLWISE_SECOND
=off, or no BASETEN_API_KEY), or once a call fails, Spark's own edge extraction is the fallback, so a recording never
loses its edges: the recording turns the Extractor's flag back off, and its last Spark run finds them (recording.py).

It used to be a second listener that re-heard names and promises; on the rehearsals it caught nothing a second Muse
Spark run would not have (Spark flipped Julien's company between its own runs too), so the comparison and its
`confirmed` and `disagreement` events are gone. A recording logged before still has them, and the app still shows
them on replay.

Each call logs a `second_run` event with its token usage, time and how many edges it found (the event names are
kept, so a recording's cost reads the same way); a failure logs `second_error`. Rate: one call in flight at most, at
least HALLWISE_SECOND_GAP_S (10) seconds apart, at most HALLWISE_SECOND_MAX_CALLS (30) per recording.

Baseten serves the model OpenAI-style. It thinks before it answers, so max_tokens must leave room for the
reasoning or the content comes back empty (finish_reason "length"). On a rehearsal transcript it reasoned about
6,100 tokens in 20 s at its default effort and about 1,000 in 5 s with reasoning_effort "low", which it honours;
low is the default here (HALLWISE_SECOND_EFFORT). `json_schema` response formats are enforced (the output follows
the schema even where the prompt asks for another shape); `json_object` works too and is the fallback.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Awaitable, Callable

import httpx

from .extract import EDGE_RULE, SCHEMA, _obj

OPEN_URL = "https://inference.baseten.co/v1/chat/completions"
OPEN_MODEL = "meta-models/muse-spark-open-1026"
OPEN = "muse-spark-open"

EDGE_SCHEMA: dict[str, Any] = _obj(edges=SCHEMA["properties"]["edges"])

EDGE_SYSTEM = """You read a live transcript from a badge worn at a networking event, for the person wearing it (the
owner). Your one job is the edges: what the people he talks to say not to him that shows what they want, dislike or
plan, so his follow-up can act on it.

The transcript has numbered turns with a speaker key ("<session>:<label>"). The owner is named at the top; the
people he met tonight are listed at the end, each with a key and the speaker keys they spoke as. A turn from before
someone met him (talking to a colleague, to themselves) is theirs when its speaker key is theirs.

Rules:
""" + EDGE_RULE + """- person is a key from the People list, exactly as written; turns are turn numbers from the transcript.
- Nothing about accent, nationality, ethnicity or personality."""

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

    async def __call__(self, system: str, user: str, schema: dict[str, Any] = EDGE_SCHEMA, name: str = "hallwise_edges") -> dict[str, Any]:
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


def clean(raw: Any) -> list[dict[str, Any]]:
    """Whatever came back, as edges: malformed items dropped, fields as strings, turns as integers."""
    def s(x: Any) -> str:
        return x.strip() if isinstance(x, str) else ""

    out = []
    for e in (raw if isinstance(raw, dict) else {}).get("edges", []) or []:
        if not isinstance(e, dict) or not s(e.get("person")) or not s(e.get("said")):
            continue
        turns = [t for t in (e.get("turns") if isinstance(e.get("turns"), list) else []) if isinstance(t, int)]
        out.append({"person": s(e["person"]), "turns": turns,
                    **{k: s(e.get(k)) for k in ("language", "said", "english", "text", "act")}})
    return out


def people_lines(picture: dict[str, Any]) -> list[str]:
    return [f"- {p.get('key', '')} | {p.get('name', '')}" + (f", {p['company']}" if p.get("company") else "")
            + f" | speaker keys: {', '.join(p.get('speakers') or []) or 'none'}" for p in picture.get("people", [])]


# --- the finder, rate-limited, inside a recording -------------------------------------------------------------

Emit = tuple[str, int, dict[str, Any]]
Sink = Callable[..., Any]  # (type, t_ms, **data): the recording's log
Found = Callable[[list[dict[str, Any]] | None, int], None]  # its edges (None: the call failed), on the recording clock


class EdgeFinder:
    """Decides when Spark Open runs, runs it, logs each call, and hands its edges to the recording."""

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
        self.totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "seconds": 0.0}

    @classmethod
    def from_env(cls) -> "EdgeFinder | None":
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

    def after_spark_run(self, sink: Sink, found: Found, prompt: Callable[[], str], spark: Callable[[], dict[str, Any]],
                        upto_turn: int, now_ms: Callable[[], int]) -> bool:
        """Count one Muse Spark run, and start a call in the background when one is due and allowed. A call
        that is due but too soon after the last one starts after a later run."""
        self.runs += 1
        if self.runs % self.every == 0:
            self.wanted = True
        if not (self.wanted and self.can_start()):
            return False
        text, call = prompt(), self._begin()
        self.task = asyncio.get_running_loop().create_task(self._run(sink, found, text, spark, upto_turn, now_ms, False, call))
        return True

    def _begin(self) -> int:
        """Book a call the moment it is decided on, so the gap and the cap count from then."""
        self.wanted = False
        self.calls += 1
        self.last_start = self.clock()
        return self.calls

    async def finish(self, sink: Sink, found: Found, prompt: Callable[[], str], spark: Callable[[], dict[str, Any]],
                     upto_turn: int, now_ms: Callable[[], int]) -> bool:
        """The recording ended: wait for a call in flight, keep the gap, then one last call on everything. True when
        that call answered; False (the cap was reached, or it failed) and the recording falls back on Muse Spark."""
        if self.task is not None:
            await self.task
        if self.calls >= self.max_calls:
            return False
        wait = self.min_gap_s - (self.clock() - self.last_start)
        if wait > 0:
            await asyncio.sleep(wait)
        return await self._run(sink, found, prompt(), spark, upto_turn, now_ms, True, self._begin())

    async def _run(self, sink: Sink, found: Found, prompt: str, spark: Callable[[], dict[str, Any]], upto_turn: int,
                   now_ms: Callable[[], int], final: bool, call: int) -> bool:
        try:
            events, edges = await self.listen(prompt, spark, upto_turn, now_ms, final=final, call=call)
        except Exception as err:  # never the main path's problem
            events, edges = [("second_error", now_ms(), {"model": self.model, "message": f"{err.__class__.__name__}: {err}"[:300]})], None
        for kind, t_ms, data in events:
            try:
                sink(kind, t_ms, **data)
            except Exception:
                return False  # the log is closed
        try:
            found(edges, now_ms())
        except Exception:
            return False
        return edges is not None

    async def listen(self, prompt: str, spark: Callable[[], dict[str, Any]], upto_turn: int, now_ms: Callable[[], int],
                     final: bool = False, call: int | None = None) -> tuple[list[Emit], list[dict[str, Any]] | None]:
        """One call: its `second_run` event and its edges, or a `second_error` event and None. The people are Spark's
        picture as the call starts, so the edges use the keys the room shows."""
        if call is None:
            call = self._begin()
        people = people_lines(spark())
        if not people:  # nobody met yet: nobody an edge could be about
            return [], []
        user = prompt + "\n\nPeople the owner has met tonight (key | name, company | speaker keys):\n" + "\n".join(people)
        started = time.monotonic()
        try:
            raw = await self.llm(EDGE_SYSTEM, user, schema=EDGE_SCHEMA, name="hallwise_edges")
        except Exception as err:
            return [("second_error", now_ms(), {"model": self.model, "call": call, "final": final,
                                                "message": f"{err.__class__.__name__}: {err}"[:300]})], None
        seconds = round(getattr(self.llm, "last_seconds", 0.0) or (time.monotonic() - started), 2)
        usage_raw = getattr(self.llm, "last_usage", {}) or {}
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
            "reasoning_tokens": int((usage_raw.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
            "total_tokens": int(usage_raw.get("total_tokens") or 0),
        }
        edges = clean(raw)
        self.totals["calls"] += 1
        self.totals["seconds"] = round(self.totals["seconds"] + seconds, 2)
        for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
            self.totals[k] += usage[k]
        return [("second_run", now_ms(), {
            "model": self.model, "role": "edge_finder", "call": call, "final": final, "upto_turn": upto_turn,
            "seconds": seconds, "usage": usage, "edges": len(edges), "totals": dict(self.totals),
        })], edges
