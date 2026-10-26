"""The event log: one append-only JSONL file per recording, and a live fan-out to anyone watching.

Every event carries `t_ms`, its position on the recording's clock (milliseconds of audio since the recording
started). The UI and the harness read nothing else, so a live session and a replay look the same.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator


class EventLog:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")
        self._lines: list[str] = []
        self._watchers: set[asyncio.Queue[str | None]] = set()
        self.closed = False

    def emit(self, type: str, t_ms: int, **data: Any) -> dict[str, Any]:
        event = {"type": type, "t_ms": int(t_ms), **data}
        line = json.dumps(event, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
        self._lines.append(line)
        for queue in self._watchers:
            queue.put_nowait(line)
        return event

    def events(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self._lines]

    def watch(self) -> tuple[list[str], asyncio.Queue[str | None]]:
        """Everything so far, plus a queue of what comes next (None once the recording ends)."""
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._watchers.add(queue)
        return list(self._lines), queue

    def unwatch(self, queue: asyncio.Queue[str | None]) -> None:
        self._watchers.discard(queue)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._file.close()
        for queue in self._watchers:
            queue.put_nowait(None)


REPLAY_TICK_S = 1.0  # a replay_clock tick after this much wall time with nothing sent


async def replay(events: list[dict[str, Any]], pace: float, from_ms: int = 0) -> AsyncIterator[str]:
    """A finished recording's events at its own pace, `pace` times faster, as JSON lines.

    Events keep their log order. Each one is due when the replay clock reaches the latest t_ms so far (an
    event logged after a later one, like an extraction that finished late, goes out right behind it, as it
    did live), and every deadline is measured from one start on the monotonic clock, so time spent sending
    never adds up. Events with the same time go out together. Everything due before `from_ms` goes out at
    once first, so the state is right, then `{"type": "replay_clock", "t_ms": from_ms}` marks the start of
    pacing, and another tick follows each second of wall time with nothing to send, so a client clock keeps
    up with the recording through a silence.
    """
    timed: list[tuple[int, str]] = []
    latest = 0
    for e in events:
        latest = max(latest, int(e.get("t_ms", 0)))
        timed.append((latest, json.dumps(e, ensure_ascii=False)))
    i = 0
    while i < len(timed) and timed[i][0] < from_ms:
        yield timed[i][1]
        i += 1
    loop = asyncio.get_running_loop()
    t0 = loop.time()  # monotonic

    async def until(t_ms: float) -> None:
        delay = t0 + (t_ms - from_ms) / 1000 / pace - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)

    def tick(t_ms: float) -> str:
        return json.dumps({"type": "replay_clock", "t_ms": int(round(t_ms))})

    clock: float = from_ms  # recording time of the last thing sent
    yield tick(clock)
    step = REPLAY_TICK_S * 1000 * pace  # recording time per tick
    while i < len(timed):
        t = timed[i][0]
        while t - clock > step:
            clock += step
            await until(clock)
            yield tick(clock)
        await until(t)
        while i < len(timed) and timed[i][0] == t:
            yield timed[i][1]
            i += 1
        clock = t


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def fold_record(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The latest picture in a log: people, promises, turns, translations, who was mentioned, and the hooks (reasons
    to reach out found across evenings). Removed items are gone, later versions win.
    This is what the follow-up drafts are written from, live or from a file."""
    people: dict[str, dict[str, Any]] = {}
    promises: dict[str, dict[str, Any]] = {}
    translations: dict[int, dict[str, Any]] = {}
    kinds: dict[int, str] = {}
    turns: list[dict[str, Any]] = []
    owner: list[str] = []
    history: dict[str, dict[str, Any]] = {}
    mentions: dict[str, dict[str, Any]] = {}
    hooks: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        t = e.get("type")
        if t == "person_history":
            history[e["key"]] = e
        elif t == "mention":
            mentions[str(e.get("name", "")).lower()] = e
        elif t == "mention_removed":
            mentions.pop(str(e.get("name", "")).lower(), None)
        elif t == "hook":
            same = hooks.setdefault(e.get("person_key", ""), [])
            same[:] = [h for h in same if h.get("title") != e.get("title")] + [e]
        elif t == "turn":
            turns.append(e)
        elif t == "turn_kind":
            kinds[e["turn"]] = e["kind"]
        elif t == "owner":
            owner = list(e.get("speakers", []))
        elif t == "person":
            people[e["key"]] = e
        elif t == "person_removed":
            people.pop(e["key"], None)
        elif t == "promise":
            promises[e["key"]] = e
        elif t == "promise_removed":
            promises.pop(e["key"], None)
        elif t == "translation":
            translations[e["turn"]] = e
        elif t == "translation_removed":
            translations.pop(e["turn"], None)
    return {
        "owner_speakers": owner,
        "people": list(people.values()),
        "promises": list(promises.values()),
        "turns": turns,
        "turn_kinds": kinds,
        "translations": translations,
        "history": history,
        "mentions": list(mentions.values()),
        "hooks": hooks,
    }
