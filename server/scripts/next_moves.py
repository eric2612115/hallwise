"""Draft the follow-ups for a finished recording and append them to its event log.

    uv run python scripts/next_moves.py 20261027-012559-ec28 --deck https://... --busy 2026-10-29T10:00:00+08:00/2026-10-29T12:00:00+08:00

Reads MODEL_API_KEY from the environment or ../.env. Earlier next_move events for the same promise are superseded
on the phone and the dashboard by the later ones (same promise_key).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hallwise.events import EventLog, fold_record, read_events  # noqa: E402
from hallwise.extract import SparkClient, draft_next_moves  # noqa: E402


def load_env() -> None:
    env = Path(__file__).resolve().parents[2] / ".env"
    if "MODEL_API_KEY" in os.environ or not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("--data", default=os.environ.get("HALLWISE_DATA", "data"))
    ap.add_argument("--busy", nargs="*", default=[], help="ISO start/end pairs, e.g. 2026-10-29T10:00:00+08:00/2026-10-29T12:00:00+08:00")
    ap.add_argument("--deck", default="")
    ap.add_argument("--one-pager", default="")
    ap.add_argument("--blurb", default="")
    ap.add_argument("--dry-run", action="store_true", help="print the moves, append nothing")
    args = ap.parse_args()
    load_env()
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        sys.exit("MODEL_API_KEY missing")
    root = Path(args.data) / "recordings" / args.recording
    meta = json.loads((root / "meta.json").read_text())
    record = fold_record(read_events(root / "events.jsonl"))
    links = {k: v for k, v in {"deck": args.deck, "one_pager": args.one_pager, "blurb": args.blurb}.items() if v}
    busy = [b.split("/", 1) for b in args.busy]
    llm = SparkClient(key, model=os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3"))
    moves = await draft_next_moves(
        llm, record,
        owner_name=meta.get("owner_name", ""), owner_company=meta.get("owner_company", ""),
        event=meta.get("event", ""), venue=meta.get("venue", ""),
        now=time.strftime("%Y-%m-%dT%H:%M:%S%z"), tz=time.strftime("%Z"), busy=busy, links=links,
    )
    print(f"{len(moves)} moves in {llm.last_seconds:.1f}s, usage {llm.last_usage}")
    for m in moves:
        print(json.dumps(m, ensure_ascii=False, indent=1))
    if args.dry_run or not moves:
        return
    last = max((e.get("t_ms", 0) for e in read_events(root / "events.jsonl")), default=0)
    log = EventLog(root / "events.jsonl")
    for m in moves:
        log.emit("next_move", last, **m)
    log.close()
    print(f"appended {len(moves)} next_move events to {root / 'events.jsonl'}")


if __name__ == "__main__":
    asyncio.run(main())
