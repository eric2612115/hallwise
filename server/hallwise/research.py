"""Who they are in public: for each person met, Muse Spark with search grounding checks that the company exists,
whether a public profile ties the person to it, and one recent public fact, each with the page it came from.

Search grounding runs on the Responses API only, so this module has its own small client:

    POST https://api.meta.ai/v1/responses
    {"model": "muse-spark-1.3", "instructions": ..., "input": ...,
     "tools": [{"type": "web_search", "search_context_size": "low"}],
     "include": ["web_search_call.results"],
     "text": {"format": {"type": "json_schema", "name": ..., "schema": ...}},
     "reasoning": {"effort": "low"}}

The answer is the last `message` item in `output`; each `web_search_call` item carries the `results` it saw
(url, title, snippet). Nothing is trusted that the search did not return: a finding whose source is not one of
those results (or of the message's url_citation annotations) is dropped, and the status follows what is left.
So research only reports what public sources say, and a fictional person comes back "no_public_record".

Rate limited: at most `max_people` lookups per run, one request at a time with at least `min_gap_s` between
requests, a token budget per run, and each result cached per person for seven days under data/research/.
HALLWISE_RESEARCH=off turns it off.

Corpus mode, for a demo whose guests are fictional: HALLWISE_RESEARCH_CORPUS=<a JSON file of pages> keeps the
same model, instructions and schema but drops the web_search tool and puts the file's pages (url, title, text)
in the input as the search results. Those pages are the `results`, so `ground` holds findings to them exactly as
it holds real ones to a real search. Results say "corpus": true and are cached apart, under data/research/corpus/.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from .extract import _STR, _obj, slug
from .people import person_key

RESPONSES_URL = "https://api.meta.ai/v1/responses"
MAX_PEOPLE = 8
MIN_GAP_S = 3.0
CACHE_S = 7 * 86400
TOKEN_BUDGET = 150_000
REQUEST_RESERVE = 12_000  # what one lookup usually costs; a run stops before a lookup would cross the budget

STATUSES = ("no_public_record", "partial", "matched")  # weakest first

RESEARCH_SCHEMA: dict[str, Any] = _obj(
    findings={
        "type": "array",
        "items": _obj(
            kind={"type": "string", "enum": ["company", "profile", "recent"]},
            text={**_STR, "description": "one sentence, what the source says"},
            url={**_STR, "description": "the search result this comes from, exactly as the result gave it"},
        ),
    },
    status={"type": "string", "enum": list(STATUSES)},
)

RESEARCH_SYSTEM = """You check the public footprint of someone the owner met at a networking event, so he knows who
he is writing to. Search the web, at most three searches. Report only what the search results say.

- company: does the company exist? One finding saying what it does, from its own site or a reliable page.
- profile: a result that ties this person's name to this company (a team page, a profile, an article). A person
  with the same name at another company is not a match; say nothing about them.
- recent: one recent public fact about the person or the company (a launch, a round, a talk), if any.

Every finding cites the url of the search result it comes from, copied exactly; never build, guess or shorten a
URL, and do not open pages. status: matched when a result ties the person to the company; partial when the
company exists but nothing ties the person to it; no_public_record when neither turns up. If nothing is found,
return no findings. Never guess, never describe the person beyond what a source says."""

CORPUS_NOTE = """

Here the search has already run: the pages below the request are its results, and the only ones. Use them as
search results; every finding cites one of their urls exactly."""


Search = Callable[..., Awaitable[dict[str, Any]]]  # (instructions, input, schema=..., name=...) -> {"answer", "results", "usage"}


class SearchClient:
    """Muse Spark with search grounding, over the Responses API, with JSON-schema output."""

    def __init__(self, api_key: str, model: str = "muse-spark-1.3", effort: str = "low", timeout: float = 120,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.transport = transport

    def body(self, instructions: str, input: str, schema: dict[str, Any], name: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "instructions": instructions,
            "input": input,
            "tools": [{"type": "web_search", "search_context_size": "low"}],
            "include": ["web_search_call.results"],
            "text": {"format": {"type": "json_schema", "name": name, "schema": schema}},
            "reasoning": {"effort": self.effort},
            "max_output_tokens": 4000,
        }

    async def __call__(
        self, instructions: str, input: str, schema: dict[str, Any] = RESEARCH_SCHEMA, name: str = "hallwise_research"
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                RESPONSES_URL, json=self.body(instructions, input, schema, name),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        response.raise_for_status()
        return parse_response(response.json())


class CorpusSearch(SearchClient):
    """The same lookup over a fixed set of pages instead of the web: no search tool, the pages in the input, and
    those pages as the results the findings are held to."""

    def __init__(self, api_key: str, pages: list[dict[str, str]], **kw: Any):
        super().__init__(api_key, **kw)
        self.pages = pages

    @classmethod
    def load(cls, api_key: str, path: Path, **kw: Any) -> "CorpusSearch":
        """Pages from a JSON file: a list of {url, title, text}, or {"pages": [...]}."""
        data = json.loads(Path(path).read_text())
        pages = data.get("pages", []) if isinstance(data, dict) else data
        return cls(api_key, [{"url": str(p["url"]), "title": str(p.get("title", "")), "text": str(p.get("text", ""))}
                             for p in pages if p.get("url")], **kw)

    def body(self, instructions: str, input: str, schema: dict[str, Any], name: str) -> dict[str, Any]:
        listed = "\n\n".join(f"[{i}] {p['url']}\n{p['title']}\n{p['text']}" for i, p in enumerate(self.pages, 1))
        body = super().body(instructions + CORPUS_NOTE, f"{input}\n\nSearch results:\n\n{listed}", schema, name)
        del body["tools"], body["include"]
        return body

    async def __call__(
        self, instructions: str, input: str, schema: dict[str, Any] = RESEARCH_SCHEMA, name: str = "hallwise_research"
    ) -> dict[str, Any]:
        reply = await super().__call__(instructions, input, schema=schema, name=name)
        results = [{"url": p["url"], "title": p["title"], "snippet": p["text"]} for p in self.pages]
        return {**reply, "results": results, "cited": [], "searches": 1}  # no source but the pages, cited or not


def parse_response(data: dict[str, Any]) -> dict[str, Any]:
    """The answer (the last message's JSON), every result the searches returned, cited URLs, and the usage."""
    results: list[dict[str, str]] = []
    cited: list[str] = []
    text = ""
    searches = 0
    for item in data.get("output", []) or []:
        if item.get("type") == "web_search_call":
            searches += 1
            for r in item.get("results", []) or []:
                if r.get("url"):
                    results.append({"url": r["url"], "title": r.get("title", "") or "", "snippet": r.get("snippet", "") or ""})
        elif item.get("type") == "message":
            for block in item.get("content", []) or []:
                if block.get("type") == "output_text":
                    text = block.get("text", "") or text
                    cited += [a["url"] for a in block.get("annotations", []) or [] if a.get("type") == "url_citation" and a.get("url")]
    try:
        answer = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()) if text.strip() else {}
    except json.JSONDecodeError:
        answer = {}
    return {"answer": answer if isinstance(answer, dict) else {}, "results": results, "cited": cited,
            "searches": searches, "usage": data.get("usage") or {}}


def _norm(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^[a-z]+://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def _host(url: str) -> str:
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    host = (urlsplit(u).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def source_for(claimed: str, text: str, results: list[dict[str, str]], cited: list[str]) -> str | None:
    """The real page behind a finding: a result or citation with exactly that URL; failing that, when the model
    named only a site, the result on that site whose title and snippet share the most words with the finding.
    None when the search never returned anything like it, so the finding goes."""
    if not claimed.strip():
        return None
    pages = [r["url"] for r in results] + cited
    for url in pages:
        if _norm(url) == _norm(claimed):
            return url
    host = _host(claimed)
    if not host:
        return None
    same = [r for r in results if _host(r["url"]) == host] + [{"url": u, "title": "", "snippet": ""} for u in cited if _host(u) == host]
    if not same:
        return None
    if "/" in _norm(claimed):
        return None  # a full URL the search never returned: made up
    words = set(re.findall(r"[a-z0-9]{4,}", text.lower()))
    return max(same, key=lambda r: len(words & set(re.findall(r"[a-z0-9]{4,}", (r["title"] + " " + r["snippet"]).lower()))))["url"]


def ground(answer: dict[str, Any], results: list[dict[str, str]], cited: list[str]) -> tuple[str, list[dict[str, str]]]:
    """Keep the findings a search result backs, and a status no stronger than what they show."""
    findings: list[dict[str, str]] = []
    for f in answer.get("findings", []) or []:
        text = str(f.get("text", "")).strip()
        kind = f.get("kind", "")
        if not text or kind not in ("company", "profile", "recent"):
            continue
        source = source_for(str(f.get("url", "")), text, results, cited)
        if source is not None:
            findings.append({"kind": kind, "text": text, "source": source})
    shown = "matched" if any(f["kind"] == "profile" for f in findings) else (
        "partial" if any(f["kind"] == "company" for f in findings) else "no_public_record")
    claimed = answer.get("status") if answer.get("status") in STATUSES else "no_public_record"
    status = min(claimed, shown, key=STATUSES.index)
    if status == "no_public_record":
        findings = []
    elif status == "partial":
        findings = [f for f in findings if f["kind"] != "profile"]
    return status, findings


def research_prompt(person: dict[str, Any]) -> str:
    lines = [f"Person: {person['name']}", f"Company: {person['company']}"]
    if person.get("role"):
        lines.append(f"Role: {person['role']}")
    if person.get("context"):
        lines.append(f"Met at: {person['context']}")
    lines.append("Check: does the company exist; does a public profile tie this person to it; one recent public fact.")
    return "\n".join(lines)


def candidates(record: dict[str, Any], context: str = "") -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Who to look up from one recording: everyone named with a company. The owner is never in people; someone
    with a first name only, or no company, has too little to search and is listed as skipped."""
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for p in record.get("people", []):
        name = str(p.get("name", "")).strip()
        company = str(p.get("company", "")).strip()
        if not slug(name):
            continue
        entry = {"key": person_key(name, company), "record_key": p.get("key", ""), "name": name, "company": company,
                 "role": p.get("role", ""), "context": context}
        if not company:
            skipped.append({"key": entry["key"], "record_key": entry["record_key"], "name": name, "reason": "no company to search"})
        elif len(name.split()) < 2:
            skipped.append({"key": entry["key"], "record_key": entry["record_key"], "name": name, "reason": "first name only"})
        else:
            out.append(entry)
    return out, skipped


class Researcher:
    """Looks people up, politely: one at a time, spaced, capped per run, within a token budget, cached a week."""

    def __init__(
        self,
        data: Path,
        search: Search | None,
        *,
        max_people: int = MAX_PEOPLE,
        min_gap_s: float = MIN_GAP_S,
        budget: int = TOKEN_BUDGET,
        reserve: int = REQUEST_RESERVE,
        cache_s: float = CACHE_S,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        off_reason: str = "",
    ):
        self.corpus = isinstance(search, CorpusSearch)
        self.dir = data / "research" / "corpus" if self.corpus else data / "research"  # never mixed with the web's
        self.search = search
        self.max_people = max_people
        self.min_gap_s = min_gap_s
        self.budget = budget
        self.reserve = reserve
        self.cache_s = cache_s
        self.clock = clock
        self.sleep = sleep
        self.off_reason = off_reason or ("" if search is not None else "no search client")
        self._lock = asyncio.Lock()
        self._last = -1e18  # when the last request went out, on `clock`

    @classmethod
    def from_env(cls, data: Path) -> "Researcher":
        key = os.environ.get("MODEL_API_KEY")
        if os.environ.get("HALLWISE_RESEARCH", "on") == "off":
            return cls(data, None, off_reason="HALLWISE_RESEARCH=off")
        if not key:
            return cls(data, None, off_reason="MODEL_API_KEY is not set")
        model = os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")
        corpus = os.environ.get("HALLWISE_RESEARCH_CORPUS", "")
        try:
            search = CorpusSearch.load(key, Path(corpus), model=model) if corpus else SearchClient(key, model=model)
        except (OSError, ValueError, TypeError, AttributeError) as err:  # a bad file never falls back to the web
            return cls(data, None, off_reason=f"HALLWISE_RESEARCH_CORPUS unreadable ({err.__class__.__name__})")
        return cls(
            data,
            search,
            max_people=int(os.environ.get("HALLWISE_RESEARCH_MAX", MAX_PEOPLE)),
            min_gap_s=float(os.environ.get("HALLWISE_RESEARCH_GAP_S", MIN_GAP_S)),
            budget=int(os.environ.get("HALLWISE_RESEARCH_TOKENS", TOKEN_BUDGET)),
        )

    def _cache_path(self, key: str) -> Path:
        return self.dir / f"{slug(key) or 'unknown'}.json"

    def cached(self, key: str) -> dict[str, Any] | None:
        path = self._cache_path(key)
        try:
            result = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if self.clock() - float(result.get("checked_at", 0)) > self.cache_s:
            return None
        return {**result, "cached": True}

    async def run(self, people: list[dict[str, Any]], skipped: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Results for `people` (from `candidates`): cached ones as they are, the rest looked up within the limits."""
        out: list[dict[str, Any]] = []
        skipped = list(skipped or [])
        if self.search is None:
            return {"enabled": False, "reason": self.off_reason, "people": [], "requests": 0, "tokens": 0,
                    "searches": 0, "skipped": skipped + [{**_who(p), "reason": f"research off ({self.off_reason})"} for p in people]}
        requests = tokens = tokens_in = tokens_out = searches = 0
        async with self._lock:  # one run, and so one request, at a time
            for p in people:
                hit = self.cached(p["key"])
                if hit is not None:
                    out.append({**hit, "record_key": p.get("record_key", "")})
                    continue
                if requests >= self.max_people:
                    skipped.append({**_who(p), "reason": f"over {self.max_people} lookups this run"})
                    continue
                if tokens + self.reserve > self.budget:
                    skipped.append({**_who(p), "reason": f"token budget ({self.budget}) spent"})
                    continue
                wait = self._last + self.min_gap_s - self.clock()
                if wait > 0:
                    await self.sleep(wait)
                self._last = self.clock()
                requests += 1
                try:
                    reply = await self.search(RESEARCH_SYSTEM, research_prompt(p), schema=RESEARCH_SCHEMA, name="hallwise_research")
                except Exception as err:  # one failed lookup must not stop the report
                    skipped.append({**_who(p), "reason": f"lookup failed: {err.__class__.__name__}"})
                    self._last = self.clock()
                    continue
                self._last = self.clock()
                usage = reply.get("usage") or {}
                used = int(usage.get("total_tokens") or 0)
                tokens += used
                tokens_in += int(usage.get("input_tokens") or 0)
                tokens_out += int(usage.get("output_tokens") or 0)
                searches += int(reply.get("searches") or 0)
                status, findings = ground(reply.get("answer") or {}, reply.get("results") or [], reply.get("cited") or [])
                result = {
                    "key": p["key"], "name": p["name"], "company": p["company"], "role": p.get("role", ""),
                    "status": status, "findings": findings,
                    "sources": list(dict.fromkeys(f["source"] for f in findings)),
                    "searched": bool(reply.get("searches")), "checked_at": self.clock(), "tokens": used,
                }
                if self.corpus:
                    result["corpus"] = True
                self.dir.mkdir(parents=True, exist_ok=True)
                self._cache_path(p["key"]).write_text(json.dumps(result, ensure_ascii=False, indent=1))
                out.append({**result, "cached": False, "record_key": p.get("record_key", "")})
        return {"enabled": True, "reason": "", "people": out, "skipped": skipped, "requests": requests,
                "tokens": tokens, "input_tokens": tokens_in, "output_tokens": tokens_out, "searches": searches}


def _who(p: dict[str, Any]) -> dict[str, str]:
    return {"key": p.get("key", ""), "record_key": p.get("record_key", ""), "name": p.get("name", "")}
