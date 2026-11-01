"""Precompute the X-ray sidecar for one recording: what the badge's own code did with the sound, from audio.wav and
events.jsonl, for the replay page's X-ray mode (apps/replay, data/<id>.xray.json).

    uv run python scripts/export_xray.py 20261027-064036-3f3e
    uv run python scripts/export_xray.py /path/to/recordings/20261029-015514-51b4 --out ../apps/replay/data
    uv run python scripts/export_xray.py 20261027-064036-3f3e --accents /path/to/asr_cast.json

The argument is a recording id (looked up in $HALLWISE_DATA/recordings, default server/data) or the path to a
recording folder. Writes <out>/<id>.xray.json and nothing else: the recording folder is only read, and the modules
it imports (direction.py, leveler.py, extract.py) are the shipping ones, called through their public API, so every
value in the sidecar is what the server's own code computes for this audio and this log.

The audio is streamed a second at a time (wave.readframes), never loaded whole: a one-hour four-channel take stays
within a few tens of MB however long it is. Each chunk goes, as in recording.on_audio, to the direction tracker
(DirectionTracker.add), then as the W (or mono) channel through the same soxr stream resampler, 48 -> 24 kHz, and
into the Leveler. The socket's own chunk sizes are not in the log, so the leveler here takes whole 10 ms blocks;
the live path steps the same blocks plus one partial block at each socket chunk's end.

What goes in, all on the recording's millisecond clock:
  blocks.rms_db[c][i]   per-channel RMS in dBFS of each 20 ms block (W, Y, Z, X for first-order ambisonics; one
                        row for a mono recording), rounded to whole dB: the "four channels in"
  win400.*              every 100 ms, direction.direction() over the surrounding 400 ms: az_device (the wearer's own
                        left / right, as direction() returns azimuth_device), az_room (with the phone's yaw at that
                        moment), yaw, elevation, confidence, confidence_3d, level_db. FOA recordings only. The page
                        draws these as soft regions and never as a number.
  lev.gain_db / speech  the Leveler's gain at the end of each 20 ms and whether it heard speech, on the transcriber's
                        copy (W or mono, resampled to 24 kHz, Leveler(24000)). audio.wav itself never passes through
                        the leveler.
  lev.params            the Leveler's own constants (target, ratio, caps), read off the instance
  turns[]               every logged turn, with the mean leveler gain over it and, on FOA, its direction recomputed
                        with the current direction.py beside the `position` the server logged at the time
  wearer                direction.Wearer fed those recomputed turns: medians per label, find(), and the code's
                        constants (so the page can draw the threshold as a code constant, not a measurement)
  checks.edges[]        every logged `edge` event put back through extract.kept_edges with the people and turns the
                        log had at that moment: kept or not, and the turn in that person's own voice that carries
                        their words. The live server only logs the edges that passed, so this is a replay of the
                        verdict, not a new one; the page stamps it as re-run offline.
  accents               the 25-voice transcriber test (asr_cast.json), counted here: names right without and with
                        hints, per voice, and the accent labels. From --accents, or apps/replay/data/asr_cast.json
                        when that file exists; --no-accents leaves it out.

Whether the live server ran the leveler is not in the log (HALLWISE_LEVELER), so the page marks the gain ribbon as
re-run offline. The direction values are marked PENDING on the page until the FOA comparison lands.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import wave
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import soxr

SERVER = Path(__file__).resolve().parents[1]
REPO = SERVER.parent
sys.path.insert(0, str(SERVER))
sys.dont_write_bytecode = True

from hallwise.direction import (  # noqa: E402
    BLOCK_MS, WEARER_MARGIN, WEARER_MIN_CONFIDENCE, WEARER_MIN_ELEVATION, WEARER_MIN_TURNS, DirectionTracker, Wearer,
)
from hallwise.leveler import FULL_SCALE, Leveler  # noqa: E402

try:  # the transcriber's rate and the badge's device name live in recording.py; keep going without it
    from hallwise.recording import ASR_RATE, IPHONE_BADGE, to_mono
except Exception:  # pragma: no cover - recording.py pulls in the whole server
    ASR_RATE = 24_000
    IPHONE_BADGE = "iPhone badge"

    def to_mono(frames: np.ndarray, layout: str) -> np.ndarray:
        if layout == "stereo":
            return ((frames[:, 0].astype(np.int32) + frames[:, 1]) // 2).astype(np.int16)
        return frames[:, 0].copy()

try:  # the edge check, to replay each logged edge's verdict with the shipping function
    from hallwise.extract import Turn, fold_words, kept_edges
except Exception:  # pragma: no cover - extract.py pulls in the model client
    Turn = fold_words = kept_edges = None  # type: ignore[assignment]

FORMAT = 2
WIN_STEP_MS = 100
WIN_MS = 400
CHUNK_S = 1  # seconds of audio per read, as the socket delivers it
FLOOR_DB = -99  # a silent block, after rounding
CHANNEL_NAMES = {"foa": ["W", "Y", "Z", "X"], "stereo": ["L", "R"], "mono": ["mono"]}
DEFAULT_ACCENTS = REPO / "apps" / "replay" / "data" / "asr_cast.json"


def r1(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), 1)


def r2(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), 2)


def locate(arg: str, data: Path) -> Path:
    path = Path(arg).expanduser()
    if (path / "events.jsonl").exists():
        return path.resolve()
    candidate = data / "recordings" / arg
    if (candidate / "events.jsonl").exists():
        return candidate.resolve()
    raise SystemExit(f"no recording {arg!r}: not a folder with events.jsonl, and not in {data / 'recordings'}")


def read_events(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a line cut short when the server stopped
    return out


def wav_info(path: Path) -> tuple[int, int, int]:
    """(rate, channels, frames) of a 16-bit WAV, without reading the samples."""
    with wave.open(str(path)) as w:
        if w.getsampwidth() != 2:
            raise SystemExit(f"{path}: {w.getsampwidth() * 8}-bit samples; the badge records 16-bit")
        return w.getframerate(), w.getnchannels(), w.getnframes()


def stream_wav(path: Path, chunk_frames: int) -> Iterator[np.ndarray]:
    """The file a chunk at a time, as (frames, channels) int16, so memory never depends on the take's length."""
    with wave.open(str(path)) as w:
        ch = w.getnchannels()
        while True:
            raw = w.readframes(chunk_frames)
            if not raw:
                return
            yield np.frombuffer(raw, dtype="<i2").reshape(-1, ch)


class SoundPass:
    """One pass over the audio, chunk by chunk, feeding the direction tracker and the leveler the way
    recording.on_audio does, and keeping only per-block summaries."""

    def __init__(self, rate: int, channels: int, layout: str, frame: str, events: list[dict[str, Any]]):
        self.rate, self.channels, self.layout = rate, channels, layout
        self.blk = rate * BLOCK_MS // 1000
        self.rms: list[list[int]] = [[] for _ in range(channels)]
        self._carry = np.zeros((0, channels), dtype=np.int16)
        self.tracker: DirectionTracker | None = None
        if layout == "foa":
            self.tracker = DirectionTracker(rate, "foa", frame)
            for e in events:
                if e.get("type") == "device_pose" and isinstance(e.get("yaw"), (int, float)):
                    self.tracker.add_pose(int(e["t_ms"]), float(e["yaw"]), bool(e.get("inverted", False)))
        self._resampler = None if rate == ASR_RATE else soxr.ResampleStream(rate, ASR_RATE, 1, dtype="int16")
        self.lev = Leveler(ASR_RATE)
        self._b10 = self.lev.block
        self._mono = np.zeros(0, dtype=np.int16)
        self.gains: list[float] = []   # per 10 ms block the leveler took
        self.speech: list[bool] = []
        self.floors: list[float] = []

    def feed(self, frames: np.ndarray) -> None:
        self._levels(frames)
        if self.tracker is not None:
            self.tracker.add(frames)
        mono = to_mono(frames, self.layout)
        if self._resampler is not None:
            mono = self._resampler.resample_chunk(mono)
        self._level(mono)

    def finish(self) -> None:
        if self._resampler is not None:
            self._level(self._resampler.resample_chunk(np.zeros(0, dtype=np.int16), last=True))

    def _levels(self, frames: np.ndarray) -> None:
        """Per-channel RMS of each whole 20 ms block in this chunk, in whole dBFS; the tail waits for the next."""
        data = np.concatenate([self._carry, frames]) if len(self._carry) else frames
        n = len(data) // self.blk
        self._carry = data[n * self.blk:].copy()
        if not n:
            return
        x = data[: n * self.blk].astype(np.float32).reshape(n, self.blk, self.channels)
        rms = np.sqrt(np.mean(x * x, axis=1))
        db = 20 * np.log10(np.maximum(rms, 1e-9) / FULL_SCALE)
        db = np.maximum(np.round(db), FLOOR_DB).astype(int)
        for c in range(self.channels):
            self.rms[c].extend(db[:, c].tolist())

    def _level(self, mono: np.ndarray) -> None:
        """The leveler, a whole 10 ms block at a time, its gain and speech flag kept after each."""
        if not len(mono):
            return
        data = np.concatenate([self._mono, mono]) if len(self._mono) else mono
        n = len(data) // self._b10
        self._mono = data[n * self._b10:].copy()
        lev = self.lev
        for k in range(n):
            lev.process(data[k * self._b10: (k + 1) * self._b10])
            self.gains.append(lev.gain_db)
            self.speech.append(lev._quiet_ms == 0.0)  # the block it just took was speech (recording.py sees the same flag)
            self.floors.append(lev.floor_db)

    def leveler(self) -> dict[str, Any]:
        """The Leveler's track sampled at the end of every 20 ms, plus its constants."""
        lev, gains, speech, floors = self.lev, self.gains, self.speech, self.floors
        steps = BLOCK_MS // 10
        pairs = len(gains) // steps
        gain20 = [r1(gains[steps * k + steps - 1]) for k in range(pairs)]
        speech20 = "".join("1" if any(speech[steps * k: steps * k + steps]) else "0" for k in range(pairs))
        floor_step = WIN_STEP_MS // 10
        floor100 = [r1(floors[k]) for k in range(floor_step - 1, len(floors), floor_step)]
        params = {
            "rate": ASR_RATE,
            "target_db": lev.target_db,
            "ratio": round(1 / (1 - lev.slope), 2),
            "max_boost_db": lev.max_boost_db,
            "max_cut_db": lev.max_cut_db,
            "ceiling_db": round(20 * math.log10(lev.ceiling / FULL_SCALE), 1),
            "speech_above_floor_db": lev.speech_above_floor_db,
            "knee_above_floor_db": lev.knee_above_floor_db,
            "hold_ms": lev.hold_ms,
            "floor_percentile": lev.floor_percentile,
            "block_ms": 10,
        }
        return {"step_ms": BLOCK_MS, "gain_db": gain20, "speech": speech20,
                "floor": {"step_ms": WIN_STEP_MS, "db": floor100}, "params": params}

    def windows(self) -> dict[str, Any] | None:
        """direction() every 100 ms over the surrounding 400 ms: the wearer's own frame (az_device), the room frame
        and the yaw that joins them, so the page never has to apply a later yaw to an earlier sample."""
        tr = self.tracker
        if tr is None:
            return None
        n = len(tr._energy)
        win: dict[str, list[Any]] = {k: [] for k in ("az_device", "az_room", "yaw", "elevation", "conf", "conf3d", "level_db")}
        half = WIN_MS // 2
        for t in range(0, n * BLOCK_MS, WIN_STEP_MS):
            a, b = max(0, t - half), t + half
            d = tr.direction(a, b)
            win["az_device"].append(None if d is None else r1(d["azimuth_device"]))
            win["az_room"].append(None if d is None else r1(d["azimuth_room"]))
            win["yaw"].append(r1(tr.yaw(a, b)))
            win["elevation"].append(None if d is None else r1(d["elevation"]))
            win["conf"].append(None if d is None else r2(d["confidence"]))
            win["conf3d"].append(None if d is None else r2(d["confidence_3d"]))
            win["level_db"].append(None if d is None else r1(d["level_db"]))
        return {"step_ms": WIN_STEP_MS, "window_ms": WIN_MS, **win}


def mean_gain(lev: dict[str, Any], start_ms: int, end_ms: int) -> float | None:
    g = lev["gain_db"]
    sp = lev["speech"]
    i0 = max(0, start_ms // BLOCK_MS)
    i1 = min(len(g), max(i0 + 1, end_ms // BLOCK_MS))
    if i1 <= i0:
        return None
    talk = [g[i] for i in range(i0, i1) if g[i] is not None and sp[i] == "1"]
    vals = talk or [g[i] for i in range(i0, i1) if g[i] is not None]
    return r1(sum(vals) / len(vals)) if vals else None


def edge_checks(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Every logged edge back through extract.kept_edges, with the people and turns the log had at that moment."""
    if kept_edges is None:
        return None
    people: dict[str, dict[str, Any]] = {}
    turns: dict[int, Turn] = {}
    rows = []
    for e in events:
        kind = e.get("type")
        if kind == "turn" and isinstance(e.get("turn"), int):
            turns[e["turn"]] = Turn(e["turn"], f"{e.get('session', 1)}:{e.get('speaker') or '?'}",
                                    int(e.get("start_ms") or e["t_ms"]), int(e.get("end_ms") or e["t_ms"]), e.get("text") or "")
        elif kind == "person" and e.get("key"):
            people[e["key"]] = e
        elif kind == "person_removed":
            people.pop(e.get("key"), None)
        elif kind == "edge":
            kept = bool(kept_edges([e], list(people.values()), list(turns.values())))
            p = people.get(e.get("person", ""))
            own = [turns[n] for n in e.get("turns") or [] if n in turns and turns[n].speaker in set((p or {}).get("speakers") or [])]
            said = fold_words(e.get("said", ""))
            in_turn = next((t.turn for t in own if said and f" {said} " in f" {fold_words(t.text)} "), None)
            reason = None if kept else ("no such person yet" if p is None else "no turn in their own voice" if not own else "their words not in that turn")
            rows.append({"t_ms": e["t_ms"], "person": e.get("person"), "turns": list(e.get("turns") or []), "said": e.get("said", ""),
                         "kept": kept, "in_turn": in_turn, "reason": reason})
    return {"source": "hallwise.extract.kept_edges, re-run offline on the logged events", "edges": rows}


def accent_test(path: Path) -> dict[str, Any]:
    """The transcriber test counted from asr_cast.json: one voice per id, each run twice (without and with hints)."""
    rows = json.loads(path.read_text())
    voices: dict[str, dict[str, Any]] = {}
    for r in rows:
        v = voices.setdefault(r["id"], {"id": r["id"], "accent": r.get("accent", ""), "gender": r.get("gender", "")})
        v["hints" if r.get("hints") else "nohints"] = {"name": r.get("name"), "company": r.get("company"), "exact": bool(r.get("exact")), "text": r.get("text", "")}
    nh = [r for r in rows if not r.get("hints")]
    wh = [r for r in rows if r.get("hints")]
    return {
        "source": path.name,
        "voices": len(voices),
        "accents": sorted({r.get("accent", "") for r in rows if r.get("accent")}),
        "name_right": {"nohints": sum(r.get("name") == "yes" for r in nh), "hints": sum(r.get("name") == "yes" for r in wh)},
        "company_right": {"nohints": sum(r.get("company") == "yes" for r in nh), "hints": sum(r.get("company") == "yes" for r in wh)},
        "exact": {"nohints": sum(bool(r.get("exact")) for r in nh), "hints": sum(bool(r.get("exact")) for r in wh)},
        "rows": list(voices.values()),
        "note": "synthetic library voices",
    }


def export(folder: Path, out: Path, accents: Path | None) -> tuple[Path, dict[str, Any], float]:
    """Read one recording folder, write <out>/<id>.xray.json; returns (path, payload, seconds of audio)."""
    meta = json.loads((folder / "meta.json").read_text()) if (folder / "meta.json").exists() else {}
    events = read_events(folder / "events.jsonl")
    start = next((e for e in events if e.get("type") == "recording_start"), {})
    rid = meta.get("id") or start.get("recording") or folder.name
    layout = meta.get("layout") or start.get("layout") or "mono"
    frame = meta.get("foa_frame") or ("camera" if (meta.get("device") or start.get("device")) == IPHONE_BADGE else "screen")

    wav = folder / "audio.wav"
    if not wav.exists():
        raise SystemExit(f"{folder}: no audio.wav; the X-ray needs the sound")
    rate, channels, nframes = wav_info(wav)
    if layout == "foa" and channels != 4:
        raise SystemExit(f"{wav}: layout foa but {channels} channels")
    names = CHANNEL_NAMES.get(layout) or [f"ch{c}" for c in range(channels)]
    names = (names + [f"ch{c}" for c in range(len(names), channels)])[:channels]

    sound = SoundPass(rate, channels, layout, frame, events)
    for chunk in stream_wav(wav, rate * CHUNK_S):
        sound.feed(chunk)
    sound.finish()
    lev = sound.leveler()
    win400 = sound.windows()
    tracker = sound.tracker

    logged = {e.get("turn"): e for e in events if e.get("type") == "position"}
    turns = []
    wearer = Wearer()
    for e in events:
        if e.get("type") != "turn" or not isinstance(e.get("start_ms"), (int, float)):
            continue
        spk = f"{e.get('session', 1)}:{e.get('speaker') or '?'}"
        row: dict[str, Any] = {"turn": e["turn"], "speaker": spk, "start_ms": int(e["start_ms"]), "end_ms": int(e["end_ms"]),
                               "gain_db": mean_gain(lev, int(e["start_ms"]), int(e["end_ms"]))}
        if tracker is not None:
            d = tracker.direction(int(e["start_ms"]), int(e["end_ms"]))
            row["now"] = None if d is None else {
                "azimuth_device": r1(d["azimuth_device"]), "azimuth_room": r1(d["azimuth_room"]), "elevation": r1(d["elevation"]),
                "confidence": r2(d["confidence"]), "confidence_3d": r2(d["confidence_3d"]), "level_db": r1(d["level_db"]),
            }
            if d is not None and not spk.endswith(":?"):
                wearer.update(spk, d.get("elevation"), d.get("confidence_3d"))
            lp = logged.get(e["turn"], {})
            row["logged"] = {k: lp[k] for k in ("azimuth_room", "confidence", "elevation", "confidence_3d", "level_db") if k in lp}
        turns.append(row)

    payload: dict[str, Any] = {
        "format": FORMAT,
        "id": rid,
        "exported": time.time(),
        "layout": layout,
        "frame": frame if layout == "foa" else None,
        "channels": channels,
        "channel_names": names,
        "rate": rate,
        "block_ms": BLOCK_MS,
        "blocks_n": len(sound.rms[0]) if sound.rms else 0,
        "poses": sum(1 for e in events if e.get("type") == "device_pose"),
        "blocks": {"rms_db": sound.rms},
        "lev": lev,
        "turns": turns,
        "owner_events": [e for e in events if e.get("type") == "owner"],
    }
    if win400 is not None:
        found = wearer.find()
        payload["win400"] = win400
        payload["wearer"] = {
            "medians": {k: round(v, 1) for k, v in wearer.medians().items()},
            "found": list(found) if found else None,
            "constants": {"min_elevation": WEARER_MIN_ELEVATION, "margin": WEARER_MARGIN,
                          "min_turns": WEARER_MIN_TURNS, "min_confidence": WEARER_MIN_CONFIDENCE},
        }
    checks = edge_checks(events)
    if checks is not None:
        payload["checks"] = checks
    if accents is not None:
        payload["accents"] = accent_test(accents)

    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{rid}.xray.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return target, payload, nframes / rate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("recording", help="recording id, or path to a recording folder")
    parser.add_argument("--out", default=str(REPO / "apps" / "replay" / "data"), help="output folder")
    parser.add_argument("--data", default=os.environ.get("HALLWISE_DATA", str(SERVER / "data")),
                        help="server data folder (for id lookup)")
    parser.add_argument("--accents", default="", metavar="ASR_CAST_JSON",
                        help=f"the transcriber's 25-voice test (asr_cast.json), counted into the sidecar; default {DEFAULT_ACCENTS} when it exists")
    parser.add_argument("--no-accents", action="store_true", help="leave the transcriber test out")
    args = parser.parse_args()

    folder = locate(args.recording, Path(args.data).resolve())
    accents: Path | None = None
    if not args.no_accents:
        if args.accents:
            accents = Path(args.accents).expanduser().resolve()
        elif DEFAULT_ACCENTS.exists():
            accents = DEFAULT_ACCENTS

    t0 = time.time()
    target, payload, seconds = export(folder, Path(args.out).resolve(), accents)
    lev = payload["lev"]
    msg = [f"{payload['id']}: {payload['layout']} {payload['channels']} ch {payload['rate']} Hz, {seconds:.1f} s, "
           f"{payload['blocks_n']} blocks of {BLOCK_MS} ms, {len(payload['turns'])} turns"]
    g = [v for v in lev["gain_db"] if v is not None]
    if g:
        msg.append(f"leveler gain {min(g):+.1f} to {max(g):+.1f} dB")
    if "wearer" in payload:
        w = payload["wearer"]
        msg.append(f"frame {payload['frame']}, {payload['poses']} poses, wearer {w['found']} (medians {w['medians']})")
    if "checks" in payload:
        rows = payload["checks"]["edges"]
        msg.append(f"edges {sum(r['kept'] for r in rows)} of {len(rows)} kept by kept_edges")
    if "accents" in payload:
        a = payload["accents"]
        msg.append(f"accents: {a['name_right']['nohints']} -> {a['name_right']['hints']} of {a['voices']} names, {len(a['accents'])} accents")
    print("; ".join(msg))
    print(f"wrote {target}  ({target.stat().st_size / 1024:.0f} KB, {time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
