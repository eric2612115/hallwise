"""Export one recording for the static replay page in apps/replay: its events, a snapshot of the people index
for the week map, and the audio as a small mono MP3.

    uv run python scripts/export_replay.py 20261027-030551-c42b
    uv run python scripts/export_replay.py /path/to/recordings/20261027-012559-ec28 --out ../apps/replay/data

The argument is a recording id (looked up in $HALLWISE_DATA/recordings, default server/data) or the path to a
recording folder. Writes <out>/<id>.json and <out>/<id>.mp3, and adds the recording to <out>/index.json, which
the page reads first. The newest export becomes the page's default unless --keep-default is given.

Audio: the W (omni) channel of a four-channel badge recording, loudness-normalised, 64 kbps mono (lower for very
long recordings, so the file stays under --max-audio-mb). A silent or missing WAV exports no audio, and the page
runs on a clock instead.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SERVER = Path(__file__).resolve().parents[1]
REPO = SERVER.parent
sys.path.insert(0, str(SERVER))

from hallwise.events import read_events  # noqa: E402
from hallwise.people import match, people_index  # noqa: E402

FORMAT = 1
WEEK_DAYS = 7
# Never shipped: transcriber partials beyond the last one per change, error messages, private calendar windows.
DROP_TYPES = {"extract_error", "asr_error"}
DROP_META = {"links", "busy"}


def find_ffmpeg(name: str) -> str:
    for candidate in (shutil.which(name), f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit(f"{name} not found; install ffmpeg (brew install ffmpeg)")


def locate(arg: str, data: Path) -> Path:
    path = Path(arg).expanduser()
    if (path / "events.jsonl").exists():
        return path.resolve()
    candidate = data / "recordings" / arg
    if (candidate / "events.jsonl").exists():
        return candidate.resolve()
    raise SystemExit(f"no recording {arg!r}: not a folder with events.jsonl, and not in {data / 'recordings'}")


def slim_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Everything the page can show, minus repeats: one partial per change of text, a pose every half second or
    two degrees, and no error messages."""
    out: list[dict[str, Any]] = []
    last_partial: dict[Any, str] = {}
    last_pose: dict[str, Any] | None = None
    for e in events:
        t = e.get("type")
        if t in DROP_TYPES:
            continue
        if t == "partial":
            text = e.get("text", "")
            if not text or last_partial.get(e.get("turn")) == text:
                continue
            last_partial[e.get("turn")] = text
        if t == "device_pose" and last_pose is not None and isinstance(e.get("yaw"), (int, float)):
            prev = last_pose.get("yaw")
            if (
                isinstance(prev, (int, float))
                and e["t_ms"] - last_pose["t_ms"] < 500
                and abs((e["yaw"] - prev + 180) % 360 - 180) < 2
                and e.get("inverted") == last_pose.get("inverted")
            ):
                continue
        if t == "device_pose":
            last_pose = e
        out.append(e)
    return out


def snapshot_people(data: Path, folder: Path, rid: str, started: float, days: int) -> dict[str, Any]:
    """The people index as the server would build it with this recording on file, merged the way live matching
    merges ("Ragoo Nathan" and "Raghunathan" at the same company are one person), limited to the week up to and
    including this recording."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "recordings"
        root.mkdir()
        source = data / "recordings"
        if source.exists():
            for d in source.iterdir():
                if (d / "meta.json").exists() and d.name != rid:
                    (root / d.name).symlink_to(d.resolve(), target_is_directory=True)
        (root / rid).symlink_to(folder, target_is_directory=True)
        index = people_index(Path(tmp))

    merged: list[dict[str, Any]] = []
    for entry in sorted(index, key=lambda e: -len(e["encounters"])):  # the better-attested spelling wins
        same = match(merged, entry["name"], entry["company"])
        if same is None:
            merged.append({**entry, "encounters": list(entry["encounters"]), "promises": list(entry["promises"]),
                           "aliases": []})
            continue
        same["aliases"].append(entry["name"])
        seen = {(e["recording"], e["record_key"]) for e in same["encounters"]}
        same["encounters"] += [e for e in entry["encounters"] if (e["recording"], e["record_key"]) not in seen]
        same["promises"] += entry["promises"]
        for field in ("company", "role", "language"):
            if entry.get(field) and not same.get(field):
                same[field] = entry[field]

    until = started
    since = started - days * 86400
    people = []
    for p in merged:
        before = [e for e in p["encounters"] if e.get("started", 0) <= until + 1]
        week = [e for e in before if e.get("started", 0) > since]
        if not week:
            continue
        before.sort(key=lambda e: e.get("started", 0))
        people.append({
            "key": p["key"], "name": p["name"], "company": p.get("company", ""), "role": p.get("role", ""),
            "language": p.get("language", ""), "aliases": p["aliases"],
            "met_total": len(before),
            "encounters": before,  # every meeting up to tonight; the page draws the ones inside the week
            "promises": [q for q in p["promises"] if q.get("started", 0) <= until + 1],
        })
    people.sort(key=lambda p: (min(e.get("started", 0) for e in p["encounters"] if e.get("started", 0) > since), p["name"]))
    return {"since": since, "until": until, "days": days, "people": people}


def probe(ffprobe: str, wav: Path) -> dict[str, Any]:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=channels,sample_rate:format=duration", "-of", "json", str(wav)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return {}
    info = json.loads(out.stdout or "{}")
    stream = (info.get("streams") or [{}])[0]
    return {"channels": int(stream.get("channels") or 0), "sample_rate": int(stream.get("sample_rate") or 0),
            "duration": float((info.get("format") or {}).get("duration") or 0)}


def peak_db(ffmpeg: str, wav: Path, pan: str) -> float:
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(wav), "-af", f"{pan},volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    found = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", out.stderr)
    if not found or found.group(1) == "-inf":
        return float("-inf")
    return float(found.group(1))


def export_audio(folder: Path, dest: Path, max_mb: float, keep_silent: bool) -> dict[str, Any] | None:
    wav = folder / "audio.wav"
    if not wav.exists() or wav.stat().st_size < 1024:
        print("audio: none (no audio.wav); the page will run on a clock")
        return None
    ffmpeg, ffprobe = find_ffmpeg("ffmpeg"), find_ffmpeg("ffprobe")
    info = probe(ffprobe, wav)
    channels = info.get("channels", 1)
    # W is channel 0 in both ACN and FuMa ordering; stereo is averaged.
    pan = "pan=mono|c0=c0" if channels >= 3 else ("pan=mono|c0=0.5*c0+0.5*c1" if channels == 2 else "anull")
    peak = peak_db(ffmpeg, wav, pan)
    if peak <= -60 and not keep_silent:
        print(f"audio: silent (peak {peak} dB); the page will run on a clock")
        return None
    duration = info.get("duration", 0.0)
    kbps = 64
    if duration > 0:
        kbps = max(24, min(64, int(max_mb * 8 * 1024 / duration)))
    out = dest.with_suffix(".mp3")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
         "-af", f"{pan},highpass=f=70,loudnorm=I=-18:TP=-1.5:LRA=11",
         "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", f"{kbps}k", str(out)],
        check=True,
    )
    print(f"audio: {out.name}  {out.stat().st_size / 1024:.0f} KB, {kbps} kbps, {duration:.1f} s "
          f"from {channels} channel(s), peak {peak} dB")
    return {"file": out.name, "duration_ms": int(round(duration * 1000)), "kbps": kbps, "source_channels": channels}


def update_index(out: Path, entry: dict[str, Any], make_default: bool) -> dict[str, Any]:
    path = out / "index.json"
    index: dict[str, Any] = {"default": "", "recordings": []}
    if path.exists():
        try:
            index = json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    rows = [r for r in index.get("recordings", []) if r.get("id") != entry["id"] and (out / r.get("file", "")).exists()]
    rows.append(entry)
    rows.sort(key=lambda r: r.get("started", 0), reverse=True)
    index["recordings"] = rows
    if make_default or not index.get("default") or index["default"] not in {r["id"] for r in rows}:
        index["default"] = entry["id"]
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("recording", help="recording id, or path to a recording folder")
    parser.add_argument("--out", default=str(REPO / "apps" / "replay" / "data"), help="output folder")
    parser.add_argument("--data", default=os.environ.get("HALLWISE_DATA", str(SERVER / "data")),
                        help="server data folder (for the people index and id lookup)")
    parser.add_argument("--week-days", type=int, default=WEEK_DAYS, help="days of people index for the week map")
    parser.add_argument("--max-audio-mb", type=float, default=8.0, help="audio size cap; bitrate drops to fit")
    parser.add_argument("--keep-silent", action="store_true", help="export the audio even if it is silent")
    parser.add_argument("--keep-default", action="store_true", help="do not make this the page's default recording")
    args = parser.parse_args()

    data = Path(args.data).resolve()
    folder = locate(args.recording, data)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    meta = json.loads((folder / "meta.json").read_text()) if (folder / "meta.json").exists() else {}
    rid = meta.get("id") or folder.name
    events = read_events(folder / "events.jsonl")
    start = next((e for e in events if e.get("type") == "recording_start"), {})
    meta = {k: v for k, v in meta.items() if k not in DROP_META}
    meta.setdefault("id", rid)
    for field in ("event", "venue", "device", "layout"):
        if not meta.get(field) and start.get(field):
            meta[field] = start[field]
    started = float(meta.get("started") or 0) or time.time()

    slim = slim_events(events)
    audio = export_audio(folder, out / rid, args.max_audio_mb, args.keep_silent)
    end_ms = max((e.get("t_ms", 0) for e in slim), default=0)
    duration_ms = max(end_ms, audio["duration_ms"] if audio else 0)
    people = snapshot_people(data, folder, rid, started, args.week_days)

    payload = {
        "format": FORMAT,
        "id": rid,
        "exported": time.time(),
        "meta": meta,
        "duration_ms": duration_ms,
        "audio": audio,
        "events": slim,
        "people_index": people,
    }
    target = out / f"{rid}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    update_index(out, {
        "id": rid, "file": target.name, "event": meta.get("event", ""), "venue": meta.get("venue", ""),
        "started": started, "duration_ms": duration_ms, "audio": bool(audio),
    }, make_default=not args.keep_default)

    kinds: dict[str, int] = {}
    for e in slim:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    total = target.stat().st_size + ((out / audio["file"]).stat().st_size if audio else 0)
    print(f"events: {len(slim)} of {len(events)} kept  {target.stat().st_size / 1024:.0f} KB  "
          + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:8]))
    print(f"people index: {len(people['people'])} people in the {args.week_days} days up to this recording")
    print(f"wrote {target}  (total {total / 1024:.0f} KB with audio)")


if __name__ == "__main__":
    main()
