"""Collect the real data the film's compositions draw, into public/data/proof.json.

Read-only on server/data, the xray sidecar and the fixtures. Every string or number a composition shows comes from
here, never from a component: events.jsonl, the xray sidecar (server/scripts/export_xray.py), asr_cast.json, the
saved one-pager JSON, the aside take's logs, the research corpus cache, demo/deck/hallwise-deck.md and the app's own
source files (the strings a notice composes, found by line). The one-pager links use the server's own
onepager.numbers and onepager.said_in (imported read-only), so every "found in slide N" is the shipping check's own
verdict; the notice's name comes from onepager.find_person, the way a cued page picks its person. Code constants
come from the modules themselves. Every default path is relative to the repo, so this runs as written:

    cd apps/film
    PYTHONDONTWRITEBYTECODE=1 ../../server/.venv/bin/python -B tools/extract_data.py

For another take: --rec <recording dir> --xray <its export_xray sidecar> [--run <a mono run dir>] --out <json>.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
FILM = HERE.parent
META = FILM.parents[1]
sys.path.insert(0, str(META / "server"))
from hallwise import direction, extract, onepager, recording  # noqa: E402  (read-only imports)

REC_ROOT = META / "server/data/recordings"
TZ = ZoneInfo("Asia/Taipei")

ap = argparse.ArgumentParser()
ap.add_argument("--rec", default=str(REC_ROOT / "20261027-064036-3f3e"), help="the 4-channel recording directory")
ap.add_argument("--xray", default=str(META / "apps/replay/data/20261027-064036-3f3e.xray.json"), help="its sidecar (export_xray.py)")
ap.add_argument("--run", default=str(FILM / "fixtures/recordings/20261029-015514-51b4"), help="a mono run with hooks, recall and second runs")
ap.add_argument("--run-xray", default="", help="the run's export_xray sidecar, for its checks.edges (default: apps/replay/data/<run>.xray.json if present)")
ap.add_argument("--onepager", default=str(FILM / "fixtures/onepager/margaux-lefevre-corvane-capital.json"))
ap.add_argument("--accents", default=str(FILM / "fixtures/asr_cast.json"))
ap.add_argument("--aside", default=str(FILM / "fixtures/aside"), help="raw-c.txt, result-c-final.txt, finder-check-c*.txt")
ap.add_argument("--deck", default=str(META / "demo/deck/hallwise-deck.md"))
ap.add_argument("--research", default=str(META / "server/data/research/corpus/julien-caron-corvane-capital.json"))
ap.add_argument("--web", default=str(META / "demo/rig/fictional-web.json"))
ap.add_argument("--window", default="44000:100000", help="the sofa scene, ms")
ap.add_argument("--freeze-turn", type=int, default=18, help="the X-ray freezes at the end of this turn")
ap.add_argument("--out", default=str(FILM / "public/data/proof.json"))
args = ap.parse_args()


def rel(p: str | Path) -> str:
    """A path as the repo knows it, never a local absolute one."""
    q = Path(p).resolve()
    try:
        return str(q.relative_to(META))
    except ValueError:
        return q.name


def events(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def day(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, TZ).strftime("%b %-d")


def r1(x):
    return None if x is None else round(float(x), 1)


def first_name(name: str) -> str:
    return (name or "").split()[0] if (name or "").split() else name


def cast_of(turns: list[dict], people_final: dict, owner_labels: set[str]) -> dict:
    """Who is who, by speaker label, as the log says: colours in order of first appearance (apps/replay prepare()),
    the owner's label from the owner event, names from the final person events, 'a voice' for a label nobody
    named."""
    order: list[str] = []
    for t in sorted(turns, key=lambda t: t["start_ms"]):
        if t["speaker"] not in order:
            order.append(t["speaker"])
    out = {}
    p = 0
    for label in order:
        if label in owner_labels:
            out[label] = {"label": label, "name": "you", "short": "you", "p": "owner", "key": None}
            continue
        key, person = next(((k, v) for k, v in people_final.items() if label in (v.get("speakers") or [])), (None, None))
        name = person["name"] if person else "a voice"
        out[label] = {"label": label, "name": name, "short": first_name(name) if person else "a voice", "p": p, "key": key}
        p += 1
    return out


def people_log_of(ev: list[dict]) -> list[dict]:
    return [{"t_ms": e["t_ms"], "type": e["type"], "key": e.get("key"), "name": e.get("name"), "company": e.get("company"),
             "speakers": e.get("speakers")} for e in ev if e["type"] in ("person", "person_removed")]


def final_people(ev: list[dict]) -> dict:
    out = {}
    for e in ev:
        if e["type"] == "person":
            out[e["key"]] = {k: e.get(k) for k in ("name", "company", "role", "preferred_language", "speakers", "evidence_turns", "introduced_by")}
        if e["type"] == "person_removed":
            out.pop(e["key"], None)
    return out


def final_promises(ev: list[dict]) -> dict:
    out = {}
    for e in ev:
        if e["type"] == "promise":
            row = out.get(e["key"], {})
            row.update({k: e.get(k) for k in ("what", "due", "replaces", "owed_to", "evidence_turns")})
            row["t_ms"] = e["t_ms"]
            if e.get("replaces") and not row.get("replaced_at"):
                row["replaced_at"] = e["t_ms"]  # the run that first logged the correction
            out[e["key"]] = row
        if e["type"] == "promise_removed":
            out.pop(e["key"], None)
    return out


def translations_of(ev: list[dict]) -> dict:
    """Per turn: the first translation since the last removal (its t_ms is when the badge had it), the latest
    wording."""
    out: dict = {}
    for e in ev:
        if e["type"] == "translation":
            cur = out.get(e["turn"])
            if cur is None or e.get("new"):
                out[e["turn"]] = {"english": e["english"], "language": e["language"], "t_ms": e["t_ms"], "aside": bool(e.get("aside"))}
            else:
                cur.update(english=e["english"], language=e["language"], last_t_ms=e["t_ms"])
        if e["type"] == "translation_removed":
            out.pop(e["turn"], None)
    return out


# ---------------------------------------------------------------- the 4-channel rehearsal and its sidecar
rec_dir = Path(args.rec)
rec = rec_dir.name
meta = json.loads((rec_dir / "meta.json").read_text())
ev = events(rec_dir / "events.jsonl")
side = json.loads(Path(args.xray).read_text())
if side.get("format") not in (1, 2) or "channel_names" not in side or "floor" not in side.get("lev", {}):
    raise SystemExit(f"{args.xray}: not a server/scripts/export_xray.py sidecar (format 1 or 2)")
BLOCK = side["block_ms"]
chan = side["channel_names"]
rms_rows = {c: side["blocks"]["rms_db"][i] for i, c in enumerate(chan)}
lev = side["lev"]
gain = lev["gain_db"]
speech = [1 if c == "1" else 0 for c in lev["speech"]]
floor100 = lev["floor"]["db"]
FLOOR_STEP = lev["floor"]["step_ms"]

turn_events = {e["turn"]: e for e in ev if e["type"] == "turn"}
translations = translations_of(ev)
turn_kind = {e["turn"]: e["kind"] for e in ev if e["type"] == "turn_kind"}
per_turn = []
per_spk: dict[str, list[float]] = {}
for t in side["turns"]:
    te = turn_events.get(t["turn"], {})
    now = t.get("now") or {}
    if t.get("gain_db") is not None:
        per_spk.setdefault(t["speaker"], []).append(t["gain_db"])
    per_turn.append({
        "turn": t["turn"], "speaker": t["speaker"], "start_ms": t["start_ms"], "end_ms": t["end_ms"], "text": te.get("text", ""),
        "az": now.get("azimuth_room"), "el": now.get("elevation"), "conf3d": now.get("confidence_3d"), "level_db": now.get("level_db"),
        "gain_db": t.get("gain_db"), "kind": turn_kind.get(t["turn"]), "translation": translations.get(t["turn"]),
    })

spk_pos = {}
for e in ev:
    if e["type"] == "speaker_position":
        spk_pos[e["speaker"]] = {k: e[k] for k in ("azimuth", "spread", "turns", "level_db") if k in e}
        spk_pos[e["speaker"]]["low_confidence"] = bool(e.get("low_confidence"))
        spk_pos[e["speaker"]]["t_ms"] = e["t_ms"]

W0, W1 = (int(x) for x in args.window.split(":"))
b0, b1 = W0 // BLOCK, W1 // BLOCK
window = {
    "t0": W0, "t1": W1, "step_ms": BLOCK,
    "rms_db": {c: rms_rows[c][b0:b1] for c in chan},
    "gain_db": gain[b0:b1], "speech": speech[b0:b1],
    "floor_step_ms": FLOOR_STEP, "floor_db": floor100[W0 // FLOOR_STEP: W1 // FLOOR_STEP],
}
w4 = side.get("win400") or {}
W4STEP = w4.get("step_ms", 100)
w0, w1 = W0 // W4STEP, W1 // W4STEP
win400 = {"t_ms": [i * W4STEP for i in range(w0, w1)], **{k: w4[k][w0:w1] for k in ("az_room", "elevation", "conf3d", "level_db") if k in w4}}

people_final = final_people(ev)
promises_final = final_promises(ev)
owner_ev = next((e for e in ev if e["type"] == "owner"), None)
owner_labels = set(owner_ev["speakers"]) if owner_ev else set()
cast3 = cast_of(per_turn, people_final, owner_labels)
freeze_ms = next((t["end_ms"] for t in per_turn if t["turn"] == args.freeze_turn), None)
if freeze_ms is None:
    raise SystemExit(f"no turn {args.freeze_turn} in {rec}")

# the X-ray at the freeze may show only what the badge had by then: a region needs a turn that ended, a name a
# person event that was logged
regions_at_freeze = sorted({t["speaker"] for t in per_turn if t["end_ms"] <= freeze_ms and t["speaker"] not in owner_labels})
people_by_freeze: dict = {}
for e in ev:  # the log is not strictly ordered by t_ms, so filter rather than stop
    if e.get("t_ms", 0) > freeze_ms:
        continue
    if e["type"] == "person":
        people_by_freeze[e["key"]] = e
    if e["type"] == "person_removed":
        people_by_freeze.pop(e["key"], None)
named_at_freeze = {s: e["name"] for e in people_by_freeze.values() for s in (e.get("speakers") or [])}
first_turn = {}
for t in sorted(per_turn, key=lambda t: t["start_ms"]):
    first_turn.setdefault(t["speaker"], t["start_ms"])
leak = [s for s in regions_at_freeze if first_turn[s] > freeze_ms]
assert not leak, f"a region's first turn is after the freeze: {leak}"

gains = [g for g in gain if g is not None]
rec3 = {
    "id": rec, "event": meta["event"], "venue": meta["venue"], "device": meta["device"], "sample_rate": side["rate"],
    "channels": side["channels"], "channel_names": chan, "layout": side["layout"], "frame": side.get("frame"),
    "block_ms": BLOCK, "duration_ms": side["blocks_n"] * BLOCK, "poses": side.get("poses"),
    "started": meta["started"], "date": day(meta["started"]), "owner_name": meta.get("owner_name", ""),
    "freeze_ms": freeze_ms, "freeze_turn": args.freeze_turn,
    "at_freeze": {"regions": regions_at_freeze, "named": named_at_freeze},
    "turns": per_turn, "speaker_positions": spk_pos, "wearer": side.get("wearer"),
    "owner_event": ({**owner_ev, "source": owner_ev.get("source") or "transcript"} if owner_ev else None),
    "cast": cast3, "people_log": people_log_of(ev),
    "leveler": {
        "gain_min": min(gains), "gain_max": max(gains), "floor_median": r1(statistics.median(floor100)),
        "per_speaker": {k: {"mean": r1(statistics.mean(v)), "min": r1(min(v)), "max": r1(max(v)), "turns": len(v)} for k, v in per_spk.items()},
        "params": lev["params"],
    },
    "window": window, "win400": win400, "people": people_final, "promises": promises_final,
}

# ---------------------------------------------------------------- the mono run: hooks, recall, second runs, the retired comparison
run_dir = Path(args.run)
run = run_dir.name
rev = events(run_dir / "events.jsonl")
rmeta = json.loads((run_dir / "meta.json").read_text())
hooks = {}
for e in rev:
    if e["type"] == "hook":
        hooks.setdefault(e["title"], e)  # first time it fired
edges_final = {}
for e in rev:
    if e["type"] == "edge":
        edges_final[(e["person"], tuple(e["turns"]))] = e
    if e["type"] == "edge_removed":
        edges_final.pop((e["person"], tuple(e["turns"])), None)
run_turns = [{k: e[k] for k in ("turn", "start_ms", "end_ms", "text")} | {"speaker": f"{e.get('session', 1)}:{e['speaker']}"} for e in rev if e["type"] == "turn"]
run_people = final_people(rev)
run_owner = next((e for e in rev if e["type"] == "owner"), None)
earlier = sorted({x["recording"] for e in rev if e["type"] == "person_history" for x in e.get("encounters", [])}
                 | {x["recording"] for e in rev if e["type"] == "hook" for x in e.get("evidence", [])})
earlier = [r for r in earlier if r != run]
run1 = {
    "id": run, "event": rmeta["event"], "venue": rmeta["venue"], "layout": rmeta["layout"], "date": day(rmeta["started"]),
    # the evening the run simulated (meta "now"), which the hooks' "five days ago" count from
    "now": rmeta.get("now"),
    "now_date": datetime.fromisoformat(rmeta["now"]).strftime("%b %-d") if rmeta.get("now") else day(rmeta["started"]),
    "turns": run_turns,
    "hooks": list(hooks.values()),
    "edges_final": list(edges_final.values()),
    "edge_events": [{k: e.get(k) for k in ("type", "t_ms", "person", "turns", "said", "act", "new")} for e in rev if e["type"] in ("edge", "edge_removed")],
    "second_runs": [{k: e.get(k) for k in ("t_ms", "model", "call", "final", "upto_turn", "seconds", "usage", "people", "promises", "agreed", "disagreed")} for e in rev if e["type"] == "second_run"],
    "person_history": [e for e in rev if e["type"] == "person_history"],
    "confirmed": [e for e in rev if e["type"] == "confirmed"],
    "confirmed_removed": [e for e in rev if e["type"] == "confirmed_removed"],
    "disagreement": next((e for e in rev if e["type"] == "disagreement"), None),
    "suspect_words": [e for e in rev if e["type"] in ("suspect_word", "suspect_word_removed")],
    "next_moves": [e for e in rev if e["type"] == "next_move"],
    "removals": {k: sum(1 for e in rev if e["type"] == k) for k in ("edge_removed", "person_removed", "promise_removed", "confirmed_removed", "suspect_word_removed")},
    "people_final": run_people,
    "people_log": people_log_of(rev),
    "promises_final": final_promises(rev),
    "owner": run_owner,
    "cast": cast_of(run_turns, run_people, set(run_owner["speakers"]) if run_owner else set()),
    "index_evenings": earlier,
}
run_xray = Path(args.run_xray) if args.run_xray else META / "apps/replay/data" / f"{run}.xray.json"
if run_xray.exists():
    rx = json.loads(run_xray.read_text())
    if rx.get("checks"):  # export_xray.py put every logged edge back through extract.kept_edges
        run1["checks"] = {**rx["checks"], "file": rel(run_xray)}

# ---------------------------------------------------------------- the aside take: Muse Spark's raw answer, the check's result, the edge finder's calls
aside_dir = Path(args.aside)
raw_c = (aside_dir / "raw-c.txt").read_text()
raw_json = extract.normalize_keys(json.loads(raw_c[: raw_c.rindex("}") + 1]))
final_txt = (aside_dir / "result-c-final.txt").read_text()


def literal_after(text: str, label: str):
    line = next(l for l in text.splitlines() if l.startswith(label))
    return ast.literal_eval(line[len(label):].strip())


EDGE_RE = re.compile(r"^\s+(\S+) turns (\[[^\]]*\]) \[([^\]]*)\] said=(.*) english=(.*)$")  # finder_check.py
RESULT_RE = re.compile(r"^\s+(\S+) (\[[^\]]*\]) (\S+) said=(.*) english=(.*)$")  # aside_check.py
DROP_RE = re.compile(r"^\s+\(dropped by the check\) (\S+) turns (\[[^\]]*\]) said=(.*)$")
CALL_RE = re.compile(r"^\s+Muse Spark Open, call (\d+) \(raw (\d+)\) \[([\d.]+) s, (\d+) in / (\d+) out\]: (\d+) edge\(s\)$")
SPARK_RE = re.compile(r"^\s+Muse Spark, its own edge rule \[([\d.]+) s, (\d+) in / (\d+) out\]: (\d+) edge\(s\)$")


def parse_edges(lines: list[str], i: int, n: int, rx: re.Pattern = EDGE_RE) -> tuple[list[dict], int]:
    out = []
    while len(out) < n and i < len(lines):
        m = rx.match(lines[i])
        if not m:
            i += 1
            continue
        e = {"person": m.group(1), "turns": ast.literal_eval(m.group(2)), "language": m.group(3),
             "said": ast.literal_eval(m.group(4)), "english": ast.literal_eval(m.group(5)), "text": "", "act": ""}
        for j in (i + 1, i + 2):
            if j < len(lines) and lines[j].strip().startswith("text: "):
                e["text"] = lines[j].strip()[6:]
            if j < len(lines) and lines[j].strip().startswith("act: "):
                e["act"] = lines[j].strip()[5:]
        out.append(e)
        i += 3
    return out, i


def parse_finder(text: str) -> dict:
    """finder_check.py's printout: the people Spark named, then per Muse Spark Open call its raw edge count, the
    edges the check dropped (printed before the call line) and the ones it kept, with seconds and tokens."""
    lines = text.splitlines()
    out = {"aside_turn": "", "people": [], "calls": [], "spark_own": None}
    pending_drops: list[dict] = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("aside turn: "):
            out["aside_turn"] = l[len("aside turn: "):]
        elif l.startswith("people (Spark, edge finder on): "):
            out["people"] = [{"key": k, "speakers": s} for k, s in ast.literal_eval(l.split(": ", 1)[1])]
        elif (m := DROP_RE.match(l)):
            pending_drops.append({"person": m.group(1), "turns": ast.literal_eval(m.group(2)), "said": ast.literal_eval(m.group(3))})
        elif (m := CALL_RE.match(l)):
            kept, i2 = parse_edges(lines, i + 1, int(m.group(6)))
            out["calls"].append({"call": int(m.group(1)), "raw": int(m.group(2)), "seconds": float(m.group(3)),
                                 "usage": {"prompt_tokens": int(m.group(4)), "completion_tokens": int(m.group(5)), "total_tokens": int(m.group(4)) + int(m.group(5))},
                                 "kept": kept, "dropped": pending_drops, "model": "muse-spark-open", "name": "hallwise_edges"})
            pending_drops = []
            i = i2
            continue
        elif (m := SPARK_RE.match(l)):
            kept, i2 = parse_edges(lines, i + 1, int(m.group(4)))
            out["spark_own"] = {"seconds": float(m.group(1)), "usage": {"prompt_tokens": int(m.group(2)), "completion_tokens": int(m.group(3)), "total_tokens": int(m.group(2)) + int(m.group(3))}, "kept": kept}
            i = i2
            continue
        i += 1
    return out


final_people_tuples = literal_after(final_txt, "people:")
aside_people = [{"key": extract.slug(f"{name}-{company}"), "name": name, "company": company, "speakers": speakers, "preferred_language": lang}
                for name, company, speakers, lang in final_people_tuples]
aside_turn_text = next(l for l in final_txt.splitlines() if l.startswith("aside turn: "))[len("aside turn: "):]
final_lines = final_txt.splitlines()
edges_i = next(i for i, l in enumerate(final_lines) if l.startswith("edges:"))
spark_kept, _ = parse_edges(final_lines, edges_i + 1, 99, RESULT_RE)
spark_calls = literal_after(final_txt, "calls (name, prompt tokens, completion tokens):")
aside_cast = {}
for p in aside_people:
    for i_, s in enumerate(p["speakers"]):
        aside_cast[s] = {"label": s, "name": p["name"], "short": first_name(p["name"]), "p": len(aside_cast), "key": p["key"]}
aside = {
    "take": "a 10-27 hinted take whose transcript kept the aside; its events.jsonl was not kept",
    "aside_turn": aside_turn_text,
    "people": aside_people,
    "cast": aside_cast,
    "spark": {
        "raw_edges": raw_json["edges"], "raw_translations": raw_json.get("translations", []),
        "translations": {str(k): {"language": v[0], "aside": v[1], "english": v[2]} for k, v in literal_after(final_txt, "translations:").items()},
        "kept_edges": spark_kept,
        "calls": [{"name": n, "prompt_tokens": a, "completion_tokens": b, "total_tokens": (a or 0) + (b or 0)} for n, a, b in spark_calls],
        "files": ["raw-c.txt", "result-c-final.txt"],
    },
    "finder": {"c": {**parse_finder((aside_dir / "finder-check-c.txt").read_text()), "file": "finder-check-c.txt"},
               "c_final": {**parse_finder((aside_dir / "finder-check-c-final.txt").read_text()), "file": "finder-check-c-final.txt"}},
}
assert aside["spark"]["kept_edges"], "no kept edge parsed from result-c-final.txt"
assert aside["finder"]["c"]["calls"][0]["dropped"], "finder-check-c.txt call 1 should carry a dropped edge"
assert aside["finder"]["c_final"]["calls"][0]["kept"], "finder-check-c-final.txt call 1 should carry a kept edge"

# ---------------------------------------------------------------- the accent test
cast_rows = json.loads(Path(args.accents).read_text())
nh = [r for r in cast_rows if not r["hints"]]
wh = [r for r in cast_rows if r["hints"]]
rows = {}
for r in cast_rows:
    rows.setdefault(r["id"], {"id": r["id"], "accent": r["accent"], "gender": r["gender"]})
    rows[r["id"]]["hints" if r["hints"] else "nohints"] = {k: r[k] for k in ("name", "company", "exact", "text", "seconds")}
accent = {
    "file": Path(args.accents).name,
    "accents": sorted({r["accent"] for r in cast_rows}), "voices": len(rows),
    "name_nohints": sum(r["name"] == "yes" for r in nh), "name_hints": sum(r["name"] == "yes" for r in wh),
    "company_nohints": sum(r["company"] == "yes" for r in nh), "company_hints": sum(r["company"] == "yes" for r in wh),
    "exact_nohints": sum(r["exact"] for r in nh), "exact_hints": sum(r["exact"] for r in wh),
    "rows": list(rows.values()),
    "voices_note": "synthetic library voices",
}

# ---------------------------------------------------------------- the one-pager, the deck, and the notice as the app composes it
op = json.loads(Path(args.onepager).read_text())
deck_src = Path(args.deck).read_text()
slides_text = onepager.said_in(deck_src)
slide_chunks = [c for c in slides_text.split("\n## ") if c.strip()]
slides = []
for c in slide_chunks:
    title, _, body = c.partition("\n")
    title = title.lstrip("# ").strip()
    slides.append({"title": " ".join(title.split())[:60], "numbers": sorted(onepager.numbers(body), key=lambda n: (len(n), n))})
allowed = onepager.numbers(slides_text)
links = []
for f in op["page"]["figures"]:
    nums = sorted(onepager.numbers(f["value"]) | onepager.numbers(f["label"]), key=lambda n: (len(n), n))
    where = [i for i, s in enumerate(slides) if nums and all(n in set(s["numbers"]) for n in nums)]
    if not where:
        where = [i for i, s in enumerate(slides) if any(n in set(s["numbers"]) for n in nums)]
    links.append({"numbers": nums, "in_deck": all(n in allowed for n in nums), "slides": where})
onepager_data = {
    **{k: op[k] for k in ("person_key", "promise_key", "acts", "slides", "status", "dropped", "retried", "usage", "seconds", "model", "page")},
    "file": Path(args.onepager).name,
    "deck": Path(args.deck).name,
    "deck_slides": slides, "allowed_numbers": sorted(allowed, key=lambda n: (len(n), n)), "links": links,
}

# The page was saved for the demo rig's key. Put into run 51b4 the way the demo cues it (onepager.cue -> find_person
# -> rebuilt_event), it lands on the person that run logged under that first name, and the notice carries that
# run's name for her. The event below is exactly what the server would log for the cue.
cue_name = first_name(op["person_key"].replace("-", " "))
cued_person = onepager.find_person({"people": [{"key": k, **v} for k, v in run_people.items()]}, cue_name)
if cued_person is None:
    raise SystemExit(f"run {run} has nobody a cue for {cue_name!r} would find")
rebuilt = onepager.rebuilt_event(run, cued_person["key"], cued_person["name"], shape=op["page"].get("shape", ""), acts=op["acts"],
                                 slides=op["slides"], title=op["page"].get("title", ""), cued=True)


def source_line(path: Path, needle: str) -> int:
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if needle in line:
            return i
    raise SystemExit(f"{path.name}: {needle!r} not found; the app's string moved")


IOS = META / "ios/Sources"
notice = IOS / "RebuiltNotice.swift"
first_line = source_line(notice, "var firstName: String")
head_line = source_line(notice, "· your deck, rebuilt\"")
sub_line = source_line(notice, "+ \". Ready.\"")
# composed as RebuiltNotice.swift composes them (firstName, headline, subline) from the rebuilt event's own fields
rb_first = first_name(rebuilt["name"])
rb_what = rebuilt["shape"] or (rebuilt["acts"][0] if rebuilt["acts"] else "")
morning = IOS / "MorningReport.swift"
report_py = META / "server/hallwise/report.py"
partial_note = re.search(r'"partial": "([^"]+)"', report_py.read_text()).group(1)
partial_pill = re.search(r'case "partial": return \("([^"]+)"', morning.read_text()).group(1)
no_record = re.search(r'"(No public record found\. [^"]+)"', morning.read_text()).group(1)
live_pages = IOS / "LivePages.swift"
script_md = META / "demo/SCRIPT.md"
script_confirm = next((l.strip() for l in script_md.read_text().splitlines() if "confirm before sending the deck" in l), "")
app_labels = {
    "rebuilt_headline": "Your deck, rebuilt" if not rb_first else f"{rb_first} · your deck, rebuilt",
    "rebuilt_subline": "Ready." if not rb_what else rb_what[:1].upper() + rb_what[1:] + ". Ready.",
    "rebuilt_source": f"RebuiltNotice.swift:{first_line},{head_line}-{sub_line}",
    "rebuilt_name_source": f"run {run[-4:]} person {cued_person['key']} · onepager.find_person · cued page",
    "partial_note": partial_note,
    "partial_note_source": f"report.py:{source_line(report_py, '\"partial\": \"')} · MorningReport.swift:{source_line(morning, 'Label(c.note')}",
    "partial_pill": partial_pill,
    "partial_pill_source": f"MorningReport.swift:{source_line(morning, 'case \"partial\": return')}",
    "no_record_line": no_record,
    "no_record_line_source": f"MorningReport.swift:{source_line(morning, 'No public record found. Confirm')}",
    "hook_tag_source": f"LivePages.swift:{source_line(live_pages, 'HookTagLine(text: hook.tag')}",
    "hook_row_source": f"LivePages.swift:{source_line(live_pages, 'struct HookRow')}",
    "radar_tag_source": f"RadarView.swift:{source_line(IOS / 'RadarView.swift', 'var tag = ')}",
    "script_confirm_line": script_confirm,
    "script_confirm_source": f"SCRIPT.md:{source_line(script_md, 'confirm before sending the deck')}",
}

# ---------------------------------------------------------------- research: Julien (corpus run) and the fictional web
research = json.loads(Path(args.research).read_text())
research["file"] = rel(args.research)
web = json.loads(Path(args.web).read_text())
pages = web if isinstance(web, list) else web.get("pages", web)
decoy = next((p for p in pages if "Caron" in json.dumps(p) and ("Chez" in json.dumps(p) or "wine" in json.dumps(p).lower())), None)
meetup = next((p for p in pages if "Nangang Hardware Meetup #19" in json.dumps(p)), None)
if meetup:
    m = re.search(r"\(([A-Z][a-z]+day, [A-Z][a-z]+ \d{1,2}, \d{4})\)", meetup["title"])
    when = datetime.strptime(m.group(1), "%A, %B %d, %Y")
    meetup = {**meetup, "date": m.group(1), "short": when.strftime("%a %b %-d"), "name": meetup["title"].split(" (")[0].split(":")[0]}


def rec_meta(rid: str) -> dict:
    m = json.loads((REC_ROOT / rid / "meta.json").read_text())
    return {"id": rid, "event": m["event"], "venue": m["venue"], "date": day(m["started"]), "started": m["started"]}


badd = events(REC_ROOT / "20261027-032704-badd/events.jsonl")
c42b = events(REC_ROOT / "20261027-030551-c42b/events.jsonl")
c42b_people = final_people(c42b)
c42b_names = {s: v["name"] for v in c42b_people.values() for s in (v.get("speakers") or [])}
c42b_tr = translations_of(c42b)
c42b_turns = [{**e, "speaker": f"{e.get('session', 1)}:{e['speaker']}"} for e in c42b if e["type"] == "turn"]
c42b_owner = next((e for e in c42b if e["type"] == "owner"), None)
evidence = {
    "chloe": {
        **rec_meta("20261027-032704-badd"),
        "turn": next(e for e in badd if e["type"] == "turn" and e["turn"] == 8),
        "person": next(e for e in badd if e["type"] == "person" and e["key"] == "chloe-martin-corvane-capital"),
    },
    "lena": next(({"key": k, "name": v["name"], "company": v["company"]} for k, v in c42b_people.items() if k.startswith("lena")), None),
    "lena_promise": {**rec_meta("20261027-030551-c42b"), "turns": [e for e in c42b if e["type"] == "turn" and e["turn"] in (5, 6, 7)]},
    "lena_asks": rec_meta("20261027-032735-1e3d"),
    "hardware_meetup": rec_meta("20261027-032636-0a72"),
    "kenji_japanese": {
        **rec_meta("20261027-030551-c42b"),
        "turns": [{**e, "speaker": f"{e.get('session', 1)}:{e['speaker']}"} for e in c42b if e["type"] == "turn" and e["turn"] in (8, 9, 10, 11)],
        "names": c42b_names,
        "cast": cast_of(c42b_turns, c42b_people, set(c42b_owner["speakers"]) if c42b_owner else set()),
        "translation": c42b_tr.get(10),
        "turn_kind": next((e["kind"] for e in c42b if e["type"] == "turn_kind" and e["turn"] == 10), None),
    },
}

OUT = {
    "generated_from": {
        "rec": rec, "xray": rel(args.xray), "run": run, "run_xray": rel(run_xray) if run_xray.exists() else None, "onepager": rel(args.onepager), "accents": rel(args.accents),
        "aside": rel(args.aside), "deck": rel(args.deck), "research": rel(args.research), "web": rel(args.web),
        "evidence": [e["id"] for e in (evidence["chloe"], evidence["lena_promise"], evidence["lena_asks"], evidence["hardware_meetup"])],
    },
    "rec3f3e": rec3, "run1": run1, "aside": aside, "accent": accent, "onepager": onepager_data, "rebuilt": rebuilt,
    "research": research, "decoy": decoy, "meetup": meetup, "evidence": evidence, "app_labels": app_labels,
    "code": {
        "WEARER_MIN_ELEVATION": direction.WEARER_MIN_ELEVATION, "WEARER_MARGIN": direction.WEARER_MARGIN,
        "WEARER_MIN_TURNS": direction.WEARER_MIN_TURNS, "WEARER_MIN_CONFIDENCE": direction.WEARER_MIN_CONFIDENCE,
        "BLOCK_MS": direction.BLOCK_MS, "ASR_RATE": recording.ASR_RATE,
        # the Leveler's own settings, read off the instance by export_xray.py (target -22 dBFS, 4:1, cap +/-12 dB, ...)
        "leveler": lev["params"],
        "hints": {"MAX_HINT_NAMES": recording.MAX_HINT_NAMES, "MAX_HINT_MENTIONS": recording.MAX_HINT_MENTIONS, "MAX_HINT_COMPANIES": recording.MAX_HINT_COMPANIES},
    },
}
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(OUT, ensure_ascii=False, separators=(",", ":")) + "\n")
print(rel(out), out.stat().st_size, "bytes")
print(f"freeze at {freeze_ms} ms (turn {args.freeze_turn}): regions {regions_at_freeze}, named {named_at_freeze}")
print("accent:", accent["name_nohints"], "->", accent["name_hints"], "of", accent["voices"], "names;", len(accent["accents"]), "accents")
print("one-pager links:", [(op["page"]["figures"][i]["value"], l["slides"]) for i, l in enumerate(links)])
print("notice:", app_labels["rebuilt_headline"], "/", app_labels["rebuilt_subline"], "<-", app_labels["rebuilt_name_source"])
print("hooks:", [(h["title"], h["t_ms"]) for h in run1["hooks"]])
print("finder c call 1: raw", aside["finder"]["c"]["calls"][0]["raw"], "kept", len(aside["finder"]["c"]["calls"][0]["kept"]), "dropped", len(aside["finder"]["c"]["calls"][0]["dropped"]))
print("finder c-final call 1: raw", aside["finder"]["c_final"]["calls"][0]["raw"], "kept", [e["said"] for e in aside["finder"]["c_final"]["calls"][0]["kept"]])
print("leveler params:", OUT["code"]["leveler"])
