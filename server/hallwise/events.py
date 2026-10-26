"""The event log: one append-only JSONL file per recording, and a live fan-out to anyone watching.

Every event carries `t_ms`, its position on the recording's clock (milliseconds of audio since the recording
started). The UI and the harness read nothing else, so a live session and a replay look the same.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


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


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
