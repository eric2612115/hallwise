import asyncio
import math

import numpy as np
import pytest

from hallwise.asr import FakeAsr
from hallwise.direction import DirectionTracker, SpeakerPositions, circular_mean, wrap
from hallwise.events import read_events
from hallwise.recording import Hello, Recording

RATE = 48_000
RNG = np.random.default_rng(7)


def voice(seconds: float) -> np.ndarray:
    """Speech-like signal: noise shaped into 4 Hz syllables."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return RNG.standard_normal(n) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)) * 0.15


def encode(signal: np.ndarray, azimuth: float) -> np.ndarray:
    """A plane wave from `azimuth` (degrees, counter-clockwise from X) as FOA: W, Y, Z, X."""
    a = math.radians(azimuth)
    return np.stack([signal, signal * math.sin(a), np.zeros_like(signal), signal * math.cos(a)], axis=1)


def diffuse(seconds: float, level: float) -> np.ndarray:
    return RNG.standard_normal((int(seconds * RATE), 4)) * level


def to_int16(foa: np.ndarray) -> np.ndarray:
    return (np.clip(foa, -1, 1) * 32767).astype(np.int16)


def test_wrap_and_circular_mean_handle_the_seam():
    assert wrap(190) == -170
    assert wrap(-180) == 180
    mean, spread = circular_mean([170, -170], [1, 1])
    assert mean == pytest.approx(180, abs=0.01)
    assert spread == pytest.approx(10, abs=0.5)


@pytest.mark.parametrize("azimuth", [0, 60, -45, 135, -150])
def test_a_talker_is_found_where_they_stand_over_room_noise(azimuth):
    tracker = DirectionTracker(RATE, "foa")
    tracker.add(to_int16(encode(voice(1.5), azimuth) + diffuse(1.5, 0.02)))
    tracker.add_pose(0, 0.0)
    where = tracker.direction(0, 1500)
    assert where["azimuth_device"] == pytest.approx(azimuth, abs=5)
    assert where["azimuth_room"] == pytest.approx(azimuth, abs=5)
    assert where["confidence"] > 0.7


def test_a_quieter_talker_reports_a_lower_level():
    tracker = DirectionTracker(RATE, "foa")
    tracker.add(to_int16(encode(voice(1.0), 20)))
    tracker.add(to_int16(encode(voice(1.0) * 0.25, 20)))  # 12 dB quieter, like someone further away
    near, far = tracker.direction(0, 1000), tracker.direction(1000, 2000)
    assert near["level_db"] - far["level_db"] == pytest.approx(12, abs=1.5)


def test_diffuse_room_noise_alone_has_low_confidence():
    tracker = DirectionTracker(RATE, "foa")
    tracker.add(to_int16(diffuse(1.0, 0.1)))
    assert tracker.direction(0, 1000)["confidence"] < 0.3


def test_turning_the_badge_keeps_the_talker_in_the_same_place_in_the_room():
    tracker = DirectionTracker(RATE, "foa")
    # The talker stands at 60° in the room. For the second turn the wearer has turned 40° to the left,
    # so the badge hears them at 20°.
    tracker.add(to_int16(encode(voice(1.0), 60) + diffuse(1.0, 0.02)))
    tracker.add(to_int16(encode(voice(1.0), 20) + diffuse(1.0, 0.02)))
    tracker.add_pose(0, 0.0)
    tracker.add_pose(1000, 40.0)
    first, second = tracker.direction(0, 1000), tracker.direction(1000, 2000)
    assert first["azimuth_device"] == pytest.approx(60, abs=5)
    assert second["azimuth_device"] == pytest.approx(20, abs=5)
    assert first["azimuth_room"] == pytest.approx(60, abs=5)
    assert second["azimuth_room"] == pytest.approx(60, abs=5)


def test_stereo_and_mono_badges_carry_no_direction():
    tracker = DirectionTracker(RATE, "stereo")
    tracker.add(np.zeros((RATE, 2), dtype=np.int16))
    assert tracker.direction(0, 1000) is None


def test_speaker_position_ignores_low_confidence_turns():
    positions = SpeakerPositions()
    assert positions.update("1:A", 50, 0.1, 2000) is None
    assert positions.update("1:A", 60, 0.9, 2000)["azimuth"] == pytest.approx(60)
    placed = positions.update("1:A", 64, 0.9, 2000)
    assert placed["azimuth"] == pytest.approx(62, abs=0.1)
    assert placed["turns"] == 2


def test_recording_emits_positions_for_each_turn_and_each_speaker(tmp_path):
    a = encode(voice(1.0), 60)
    b = encode(voice(1.0), -45)
    gap = np.zeros((int(0.5 * RATE), 4))
    foa = to_int16(np.concatenate([a, gap, b, gap]) + diffuse(3.0, 0.01))
    script = [
        {"start_ms": 0, "end_ms": 1000, "speaker": "A", "text": "Hi, I'm Sarah."},
        {"start_ms": 1500, "end_ms": 2500, "speaker": "B", "text": "I'm Eric."},
    ]
    hello = Hello(sample_rate=RATE, channels=4, layout="foa", fake_script=script)
    rec = Recording(tmp_path, hello, lambda sink, *, rate, hello: FakeAsr(sink, rate=rate, script=hello.fake_script))

    async def run():
        await rec.start()
        rec.on_pose({"t_ms": 0, "yaw": 0.0})
        data = foa.tobytes()
        for i in range(0, len(data), 4 * 2 * 4800):
            await rec.on_audio(data[i : i + 4 * 2 * 4800])
        await rec.close()

    asyncio.run(run())
    events = read_events(rec.dir / "events.jsonl")
    placed = {e["speaker"]: e["azimuth"] for e in events if e["type"] == "speaker_position"}
    assert placed["1:A"] == pytest.approx(60, abs=5)
    assert placed["1:B"] == pytest.approx(-45, abs=5)
    assert len([e for e in events if e["type"] == "position"]) == 2
