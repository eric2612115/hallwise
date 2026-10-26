"""Build a synthetic first-order-ambisonics WAV plus a fake-recogniser script from a transcript fixture, so the
whole pipeline (direction, extraction, dashboard) can be exercised without a microphone.

    uv run python scripts/make_demo_foa.py tests/fixtures/demo_transcript.json out_dir

Writes out_dir/demo.wav (4 ch, 48 kHz, ~2 min) and out_dir/script.json. Each speaker label stands at a fixed
bearing; its turns are noise bursts shaped like speech, over a quiet diffuse room.
"""

from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

RATE = 48_000
BEARINGS = {"A": 30, "B": -90, "C": 150, "D": 170, "E": 175, "F": 60, "G": 95, "H": 125, "I": -40}
LEVELS = {"D": 0.05, "E": 0.05, "C": 0.08}  # ambient and staff quieter than conversation


def main(fixture: Path, out: Path) -> None:
    turns = json.loads(fixture.read_text())
    out.mkdir(parents=True, exist_ok=True)
    total = max(t["end_ms"] for t in turns) + 2000
    n = total * RATE // 1000
    rng = np.random.default_rng(1)
    foa = rng.standard_normal((n, 4)) * 0.012  # the room
    for t in turns:
        label = t["speaker"].split(":")[-1]
        a, b = t["start_ms"] * RATE // 1000, t["end_ms"] * RATE // 1000
        length = b - a
        tt = np.arange(length) / RATE
        voice = rng.standard_normal(length) * (0.5 + 0.5 * np.sin(2 * math.pi * 4.5 * tt)) * LEVELS.get(label, 0.16)
        az = math.radians(BEARINGS.get(label, 0))
        foa[a:b, 0] += voice
        foa[a:b, 1] += voice * math.sin(az)
        foa[a:b, 3] += voice * math.cos(az)
    pcm = (np.clip(foa, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out / "demo.wav"), "wb") as w:
        w.setnchannels(4)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    script = [
        {"start_ms": t["start_ms"], "end_ms": t["end_ms"], "speaker": t["speaker"].split(":")[-1], "text": t["text"]}
        for t in turns
    ]
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1))
    print(f"{out / 'demo.wav'}: {total / 1000:.0f} s, {len(turns)} turns")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
