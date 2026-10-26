"""Append person_history events to a finished recording: who in it the owner had met at other recordings.

    uv run python scripts/history.py 20261027-012559-ec28
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hallwise.events import EventLog, fold_record, read_events  # noqa: E402
from hallwise.people import history_event, match, people_index  # noqa: E402

rid = sys.argv[1]
data = Path(os.environ.get("HALLWISE_DATA", "data"))
root = data / "recordings" / rid
events = read_events(root / "events.jsonl")
record = fold_record(events)
known = people_index(data, exclude=rid)
already = {e["key"] for e in events if e.get("type") == "person_history"}
last = max((e.get("t_ms", 0) for e in events), default=0)
log = EventLog(root / "events.jsonl")
n = 0
for p in record["people"]:
    if p["key"] in already:
        continue
    entry = match(known, p.get("name", ""), p.get("company", ""))
    if entry is None:
        continue
    log.emit("person_history", last, **history_event(entry, p["key"], exclude=rid))
    n += 1
    print("seen before:", p.get("name"), "->", [e["event"] for e in entry["encounters"] if e["recording"] != rid])
log.close()
print(f"appended {n} person_history events")
