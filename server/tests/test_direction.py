import asyncio
import json
import math

import numpy as np
import pytest

from hallwise.asr import FakeAsr
from hallwise.direction import (
    WEARER_MIN_ELEVATION,
    DirectionTracker,
    SpeakerPositions,
    Wearer,
    circular_mean,
    wrap,
)
from hallwise.events import fold_record, read_events
from hallwise.extract import Extractor
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


def test_a_confident_position_is_not_moved_by_low_confidence_turns():
    positions = SpeakerPositions()
    assert positions.update("1:A", 60, 0.9, 2000)["azimuth"] == pytest.approx(60)
    assert positions.update("1:A", -90, 0.1, 4000) is None  # far off and long, but mostly room: ignored
    placed = positions.update("1:A", 64, 0.9, 2000)
    assert placed["azimuth"] == pytest.approx(62, abs=0.1)
    assert placed["turns"] == 2
    assert "low_confidence" not in placed


def test_a_speaker_heard_only_at_low_confidence_still_gets_a_flagged_position():
    positions = SpeakerPositions()
    first = positions.update("1:G", 30, 0.2, 2000, -25.0)
    assert first == {"azimuth": 30.0, "spread": 0.0, "turns": 1, "level_db": -25.0, "low_confidence": True}
    second = positions.update("1:G", 40, 0.2, 2000, -27.0)
    assert second["azimuth"] == pytest.approx(35, abs=0.1)
    assert second["turns"] == 2 and second["low_confidence"] is True
    assert second["level_db"] == pytest.approx(-26)


def test_the_first_confident_turn_replaces_a_provisional_position():
    positions = SpeakerPositions()
    positions.update("1:D", -60, 0.25, 3000)
    placed = positions.update("1:D", 10, 0.5, 1000)
    assert placed["azimuth"] == pytest.approx(10)  # not pulled toward the provisional -60
    assert placed["turns"] == 1
    assert "low_confidence" not in placed
    assert positions.update("1:D", -60, 0.25, 3000) is None


def test_recording_places_a_far_talker_heard_only_at_low_confidence(tmp_path):
    # A talks near the badge at 60°; B is far off at 35°, and the room around B's turn is loud enough that every
    # one of B's turns comes in below the 0.3 floor. B still gets a dot, flagged, where B stands.
    near = encode(voice(1.0), 60) + diffuse(1.0, 0.01)
    far = encode(voice(1.5) * 0.3, 35) + diffuse(1.5, 0.08)
    gap = np.zeros((int(0.5 * RATE), 4))
    foa = to_int16(np.concatenate([near, gap, far, gap]))
    script = [
        {"start_ms": 0, "end_ms": 1000, "speaker": "A", "text": "This is Kenji."},
        {"start_ms": 1500, "end_ms": 3000, "speaker": "B", "text": "Kenji Watanabe, Hoshizora Robotics."},
    ]
    events = run_recording(tmp_path, foa, script, [{"t_ms": 0, "yaw": 0.0}])
    (b_turn,) = [e for e in events if e["type"] == "position" and e["speaker"] == "1:B"]
    assert b_turn["confidence"] < 0.3
    placed = {e["speaker"]: e for e in events if e["type"] == "speaker_position"}
    assert placed["1:B"]["azimuth"] == pytest.approx(35, abs=5)
    assert placed["1:B"]["low_confidence"] is True
    assert placed["1:A"]["azimuth"] == pytest.approx(60, abs=5)
    assert "low_confidence" not in placed["1:A"]


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


def heard(wearer_azimuth: float, inverted: bool) -> float:
    """Where the badge's microphones hear a talker who stands at `wearer_azimuth` relative to the wearer. Hanging
    top-down, the phone is turned 180° about the screen normal: ahead stays ahead, left and right swap."""
    return -wearer_azimuth if inverted else wearer_azimuth


@pytest.mark.parametrize("inverted", [False, True])
def test_a_talker_on_the_left_stays_on_the_left_when_the_badge_hangs_upside_down(inverted):
    # The talker stands 60° to the wearer's left; the wearer faces 30° in the room, so the talker is at 90°.
    tracker = DirectionTracker(RATE, "foa")
    tracker.add(to_int16(encode(voice(1.0), heard(60, inverted)) + diffuse(1.0, 0.02)))
    tracker.add_pose(0, 30.0, inverted)
    where = tracker.direction(0, 1000)
    assert where["inverted"] is inverted
    assert where["azimuth_device"] == pytest.approx(60, abs=5)
    assert where["azimuth_room"] == pytest.approx(90, abs=5)


def test_an_upright_badge_hearing_a_talker_on_the_right_puts_them_on_the_right():
    # The contrast: the same mirrored signal as the top-down case above, from an upright badge, is a talker on the right.
    tracker = DirectionTracker(RATE, "foa")
    tracker.add(to_int16(encode(voice(1.0), -60) + diffuse(1.0, 0.02)))
    tracker.add_pose(0, 30.0, False)
    where = tracker.direction(0, 1000)
    assert where["azimuth_device"] == pytest.approx(-60, abs=5)
    assert where["azimuth_room"] == pytest.approx(-30, abs=5)


def run_recording(
    tmp_path, foa: np.ndarray, script: list[dict], poses: list[dict], hello: Hello | None = None
) -> list[dict]:
    hello = hello or Hello(sample_rate=RATE, channels=4, layout="foa", fake_script=script)
    rec = Recording(tmp_path, hello, lambda sink, *, rate, hello: FakeAsr(sink, rate=rate, script=hello.fake_script))

    async def run():
        await rec.start()
        for pose in poses:
            rec.on_pose(pose)
        data = foa.tobytes()
        for i in range(0, len(data), 4 * 2 * 4800):
            await rec.on_audio(data[i : i + 4 * 2 * 4800])
        await rec.close()

    asyncio.run(run())
    return read_events(rec.dir / "events.jsonl")


@pytest.mark.parametrize("inverted", [False, True])
def test_recording_places_a_talker_on_the_left_whichever_way_up_the_badge_hangs(tmp_path, inverted):
    # A on the wearer's left at 50°, B on the right at -40°; the wearer faces 20° in the room.
    gap = np.zeros((int(0.5 * RATE), 4))
    foa = np.concatenate(
        [encode(voice(1.0), heard(50, inverted)), gap, encode(voice(1.0), heard(-40, inverted)), gap]
    )
    script = [
        {"start_ms": 0, "end_ms": 1000, "speaker": "A", "text": "Hi, I'm Sarah."},
        {"start_ms": 1500, "end_ms": 2500, "speaker": "B", "text": "I'm Eric."},
    ]
    poses = [
        {"type": "pose", "t_ms": t, "yaw": 20.0, "pitch": 88.0, "roll": 0.0, "inverted": inverted}
        for t in range(0, 3000, 100)
    ]
    events = run_recording(tmp_path, to_int16(foa + diffuse(3.0, 0.01)), script, poses)
    placed = {e["speaker"]: e["azimuth"] for e in events if e["type"] == "speaker_position"}
    assert placed["1:A"] == pytest.approx(70, abs=5)  # left of the wearer: positive
    assert placed["1:B"] == pytest.approx(-20, abs=5)  # right of the wearer: negative
    assert {e["inverted"] for e in events if e["type"] == "position"} == {inverted}
    assert {e["inverted"] for e in events if e["type"] == "device_pose"} == {inverted}


def test_a_badge_that_flips_over_between_turns_keeps_the_talker_where_they_stand(tmp_path):
    # One talker stays put 60° to the wearer's left (room 60°, wearer facing 0°). Halfway through, the lanyard turns
    # the phone top-down; the microphones now hear the same talker at -60°.
    gap = np.zeros((int(0.5 * RATE), 4))
    foa = np.concatenate([encode(voice(1.0), 60), gap, encode(voice(1.0), heard(60, True)), gap])
    script = [
        {"start_ms": 0, "end_ms": 1000, "speaker": "A", "text": "Before the flip."},
        {"start_ms": 1500, "end_ms": 2500, "speaker": "A", "text": "After the flip."},
    ]
    poses = [{"type": "pose", "t_ms": t, "yaw": 0.0, "pitch": 89.0, "roll": 0.0, "inverted": t >= 1250} for t in range(0, 3000, 100)]
    events = run_recording(tmp_path, to_int16(foa + diffuse(3.0, 0.01)), script, poses)
    rooms = [e["azimuth_room"] for e in events if e["type"] == "position"]
    assert rooms == [pytest.approx(60, abs=5), pytest.approx(60, abs=5)]
    assert [e["inverted"] for e in events if e["type"] == "position"] == [False, True]


def test_poses_without_the_inverted_field_mean_upright(tmp_path):
    gap = np.zeros((int(0.5 * RATE), 4))
    foa = np.concatenate([encode(voice(1.0), 60), gap])
    script = [{"start_ms": 0, "end_ms": 1000, "speaker": "A", "text": "Hello."}]
    events = run_recording(tmp_path, to_int16(foa + diffuse(1.5, 0.01)), script, [{"t_ms": 0, "yaw": 10.0}])
    (position,) = [e for e in events if e["type"] == "position"]
    assert position["inverted"] is False
    assert position["azimuth_room"] == pytest.approx(70, abs=5)
    (pose,) = [e for e in events if e["type"] == "device_pose"]
    assert "inverted" not in pose


# --- an iPhone's own ambisonics is in Apple's camera frame: +X out of the back of the phone ---------------------------


def camera_axes(foa: np.ndarray) -> np.ndarray:
    """The same sound as the iPhone's `.firstOrderAmbisonics` reports it: Apple's camera frame, +X out of the back, so
    X and Y change sign and W and Z stay (columns W, Y, Z, X)."""
    return foa * np.array([1.0, -1.0, 1.0, -1.0])


def angle_off(found: float, expected: float) -> float:
    return abs(wrap(found - expected))


def badge_hello(script: list[dict] | None = None, **fields) -> Hello:
    """The hello as the app sends it (a dict over the socket), through the same parser."""
    msg = {"sample_rate": RATE, "channels": 4, "layout": "foa", "device": "iPhone badge", **fields}
    return Hello.parse({**msg, "fake_script": script} if script else msg)


def meta_of(tmp_path) -> dict:
    (folder,) = (tmp_path / "recordings").iterdir()
    return json.loads((folder / "meta.json").read_text())


@pytest.mark.parametrize("wearer_azimuth", [0, 180, 90, -90, 60, -135])
def test_camera_frame_audio_puts_a_talker_where_they_stand_relative_to_the_screen(wearer_azimuth):
    # 0 = out of the screen, 180 = out of the back, + = the phone's left looking out of the screen.
    tracker = DirectionTracker(RATE, "foa", "camera")
    foa = camera_axes(encode(voice(1.5), wearer_azimuth) + diffuse(1.5, 0.02))
    tracker.add(to_int16(foa))
    tracker.add_pose(0, 0.0)
    where = tracker.direction(0, 1500)
    assert angle_off(where["azimuth_device"], wearer_azimuth) < 5, where
    assert angle_off(where["azimuth_room"], wearer_azimuth) < 5, where
    assert where["confidence"] > 0.7


def test_the_take_measured_on_the_phone_reads_front_at_zero_and_back_at_a_half_turn():
    # The calibration take: the phone standing still, the owner walking round it. Read as the screen frame, the
    # screen side came out near ±175° and the back near -10°; as the camera frame they are near 5° and 170°.
    front, back = 175.0, -10.0
    for frame, front_expected, back_expected in (("screen", 175, -10), ("camera", -5, 170)):
        tracker = DirectionTracker(RATE, "foa", frame)
        tracker.add(to_int16(encode(voice(1.0), front) + diffuse(1.0, 0.02)))
        tracker.add(to_int16(encode(voice(1.0), back) + diffuse(1.0, 0.02)))
        a, b = tracker.direction(0, 1000), tracker.direction(1000, 2000)
        assert angle_off(a["azimuth_device"], front_expected) < 5
        assert angle_off(b["azimuth_device"], back_expected) < 5


def test_the_screen_frame_is_the_default_and_leaves_the_audio_as_it_is():
    default, screen = DirectionTracker(RATE, "foa"), DirectionTracker(RATE, "foa", "screen")
    signal = to_int16(encode(voice(1.0), 135) + diffuse(1.0, 0.02))
    for tracker in (default, screen):
        tracker.add(signal)
        tracker.add_pose(0, 0.0)
    assert default.direction(0, 1000) == screen.direction(0, 1000)
    assert angle_off(screen.direction(0, 1000)["azimuth_device"], 135) < 5


def test_an_unknown_frame_is_refused():
    with pytest.raises(ValueError, match="foa frame"):
        DirectionTracker(RATE, "foa", "world")


@pytest.mark.parametrize(
    "msg, frame",
    [
        ({"device": "iPhone badge"}, "camera"),  # what the app sends today: no field, no app update
        ({"device": "iPhone badge", "foa_frame": None}, "camera"),
        ({"device": "iPhone badge", "foa_frame": "camera"}, "camera"),
        ({"device": "iPhone badge", "foa_frame": "screen"}, "screen"),  # said outright, so it wins
        ({"device": "simulator"}, "screen"),  # stream_wav.py and the rig
        ({"device": "simulator", "foa_frame": "camera"}, "camera"),
        ({"device": "simulator", "foa_frame": "screen"}, "screen"),
        ({}, "screen"),
    ],
)
def test_the_hello_names_the_frame_or_the_device_decides(msg, frame):
    base = {"sample_rate": RATE, "channels": 4, "layout": "foa"}
    assert Hello.parse({**base, **msg}).foa_frame == frame


def test_a_hello_with_an_unknown_frame_is_refused():
    with pytest.raises(ValueError, match="foa_frame"):
        Hello.parse({"sample_rate": RATE, "channels": 4, "layout": "foa", "foa_frame": "world"})


@pytest.mark.parametrize(
    "fields, frame",
    [({}, "camera"), ({"foa_frame": "screen"}, "screen"), ({"device": "simulator"}, "screen")],
)
def test_the_recording_keeps_the_frame_it_used_in_meta(tmp_path, fields, frame):
    run_recording(tmp_path, np.zeros((RATE, 4), dtype=np.int16), [], [], hello=badge_hello(**fields))
    assert meta_of(tmp_path)["foa_frame"] == frame


def test_a_recording_without_a_device_in_the_hello_keeps_the_screen_frame_in_meta(tmp_path):
    run_recording(tmp_path, np.zeros((RATE, 4), dtype=np.int16), [], [])
    assert meta_of(tmp_path)["foa_frame"] == "screen"


def two_talkers() -> tuple[np.ndarray, list[dict]]:
    """A at the wearer's front, B behind them, C on the left, D on the right (screen-frame audio, one turn each)."""
    gap = np.zeros((int(0.5 * RATE), 4))
    parts, script = [], []
    for i, (who, az) in enumerate((("A", 0), ("B", 180), ("C", 90), ("D", -90))):
        parts += [encode(voice(1.0), az), gap]
        script.append({"start_ms": i * 1500, "end_ms": i * 1500 + 1000, "speaker": who, "text": f"This is {who}."})
    return np.concatenate(parts) + diffuse(6.0, 0.01), script


def test_recording_places_the_screen_side_ahead_and_the_back_behind_for_an_iphone_badge(tmp_path):
    foa, script = two_talkers()
    hello = badge_hello(script)  # no foa_frame, as the app sends it
    events = run_recording(tmp_path, to_int16(camera_axes(foa)), script, [{"t_ms": 0, "yaw": 0.0}], hello=hello)
    placed = {e["speaker"]: e["azimuth"] for e in events if e["type"] == "speaker_position"}
    assert angle_off(placed["1:A"], 0) < 5
    assert angle_off(placed["1:B"], 180) < 5
    assert placed["1:C"] == pytest.approx(90, abs=5)  # the phone's left looking out of the screen: positive
    assert placed["1:D"] == pytest.approx(-90, abs=5)


def test_recording_leaves_simulator_audio_in_the_screen_frame(tmp_path):
    # The rehearsal and rig audio is synthesised in the screen frame and streamed with device "simulator".
    foa, script = two_talkers()
    hello = badge_hello(script, device="simulator")
    events = run_recording(tmp_path, to_int16(foa), script, [{"t_ms": 0, "yaw": 0.0}], hello=hello)
    placed = {e["speaker"]: e["azimuth"] for e in events if e["type"] == "speaker_position"}
    assert angle_off(placed["1:A"], 0) < 5
    assert angle_off(placed["1:B"], 180) < 5
    assert placed["1:C"] == pytest.approx(90, abs=5)
    assert placed["1:D"] == pytest.approx(-90, abs=5)


@pytest.mark.parametrize("inverted", [False, True])
def test_a_camera_frame_badge_hanging_upside_down_still_puts_left_on_the_left(tmp_path, inverted):
    # A on the wearer's left at 50°, B on the right at -40°, C straight behind; the wearer faces 20° in the room.
    # iOS turns its ambisonic frame with the phone, so hanging top-down the audio is not mirrored (see the next test).
    gap = np.zeros((int(0.5 * RATE), 4))
    screen = np.concatenate(
        [encode(voice(1.0), 50), gap, encode(voice(1.0), -40), gap, encode(voice(1.0), 180), gap]
    )
    script = [
        {"start_ms": 0, "end_ms": 1000, "speaker": "A", "text": "Hi, I'm Sarah."},
        {"start_ms": 1500, "end_ms": 2500, "speaker": "B", "text": "I'm Eric."},
        {"start_ms": 3000, "end_ms": 4000, "speaker": "C", "text": "And I'm Leo."},
    ]
    poses = [
        {"type": "pose", "t_ms": t, "yaw": 20.0, "pitch": 88.0, "roll": 0.0, "inverted": inverted}
        for t in range(0, 4500, 100)
    ]
    events = run_recording(
        tmp_path, to_int16(camera_axes(screen) + diffuse(4.5, 0.01)), script, poses, hello=badge_hello(script)
    )
    placed = {e["speaker"]: e["azimuth"] for e in events if e["type"] == "speaker_position"}
    assert placed["1:A"] == pytest.approx(70, abs=5)  # left of the wearer: positive
    assert placed["1:B"] == pytest.approx(-20, abs=5)  # right of the wearer: negative
    assert angle_off(placed["1:C"], 200) < 5  # behind the wearer, who faces 20°
    positions = [e for e in events if e["type"] == "position"]
    assert {e["inverted"] for e in positions} == {inverted}
    device = {e["speaker"]: e["azimuth_device"] for e in positions}
    assert device["1:A"] == pytest.approx(50, abs=5) and device["1:B"] == pytest.approx(-40, abs=5)
    assert angle_off(device["1:C"], 180) < 5


# --- measured on the owner's iPhone 17 Pro, hanging upside down on his chest ------------------------------------------


def encode_up(signal: np.ndarray, azimuth: float, elevation: float) -> np.ndarray:
    """A plane wave from `azimuth`, `elevation` degrees above the horizontal, as FOA: W, Y, Z, X (SN3D)."""
    a, e = math.radians(azimuth), math.radians(elevation)
    return np.stack(
        [signal, signal * math.sin(a) * math.cos(e), signal * math.sin(e), signal * math.cos(a) * math.cos(e)], axis=1
    )


def test_a_camera_frame_badge_upside_down_is_not_negated_again():
    # 73b5, "这是左边": the guest on the wearer's left came in at -34° in the microphones' own (camera) axes with the
    # phone top-down. iOS had already turned the frame with the phone: after the half turn that is +146°, left.
    tracker = DirectionTracker(RATE, "foa", "camera")
    tracker.add(to_int16(encode(voice(1.0), -34) + diffuse(1.0, 0.02)))
    tracker.add_pose(0, 0.0, True)
    where = tracker.direction(0, 1000)
    assert where["inverted"] is True  # still reported as the poses said
    assert where["azimuth_device"] == pytest.approx(146, abs=5)  # positive: the wearer's left
    assert where["azimuth_room"] == pytest.approx(146, abs=5)


def test_the_screen_frame_still_negates_a_top_down_badge_and_the_camera_frame_does_not():
    signal = to_int16(encode_up(voice(1.0), 60, 30) + diffuse(1.0, 0.02))
    screen, camera = DirectionTracker(RATE, "foa", "screen"), DirectionTracker(RATE, "foa", "camera")
    for tracker in (screen, camera):
        tracker.add(signal)
        tracker.add_pose(0, 0.0, True)
    s, c = screen.direction(0, 1000), camera.direction(0, 1000)
    assert s["azimuth_device"] == pytest.approx(-60, abs=5)  # top-down in the screen frame: mirrored back
    assert s["elevation"] == pytest.approx(-30, abs=5)  # and turned over
    assert angle_off(c["azimuth_device"], wrap(60 + 180)) < 5  # only the camera frame's half turn
    assert c["elevation"] == pytest.approx(30, abs=5)  # iOS keeps up up


@pytest.mark.parametrize("elevation", [70, 20, -15])
def test_a_turn_reports_how_far_above_the_badge_it_came_from(elevation):
    tracker = DirectionTracker(RATE, "foa", "camera")
    tracker.add(to_int16(camera_axes(encode_up(voice(1.0), 30, elevation)) + diffuse(1.0, 0.01)))
    where = tracker.direction(0, 1000)
    assert where["elevation"] == pytest.approx(elevation, abs=5)
    assert where["confidence_3d"] > 0.7
    if elevation == 70:  # mostly vertical: the flat confidence calls it room, the 3-D one does not
        assert where["confidence"] < 0.5


def test_the_wearer_is_the_label_whose_confident_turns_come_from_high_above():
    w = Wearer()
    for elevation in (11.3, 35.7, 22.8, 8.1, 28.8):  # Ken, 73b5
        w.update("1:A", elevation, 0.7)
    w.update("1:B", 72.5, 0.72)
    assert w.find() is None  # one turn is not enough
    w.update("1:B", 64.4, 0.57)
    assert w.find() == ("1:B", 68.5)


def test_no_wearer_while_no_label_is_clearly_high():
    level = Wearer()
    for s, elevation in (("1:A", 20), ("1:A", 30), ("1:B", 35), ("1:B", 40)):
        level.update(s, elevation, 0.8)
    assert level.find() is None  # nobody above the threshold
    split = Wearer()
    for s, elevation in (("1:A", 70), ("1:A", 64), ("1:B", 55), ("1:B", 60)):
        split.update(s, elevation, 0.8)
    assert split.find() is None  # two voices from above: not clearly one of them
    room = Wearer()
    for elevation in (70, 66):
        room.update("1:A", elevation, 0.2)  # mostly room, whichever way it leans
    assert room.find() is None


def test_one_guest_turn_that_reads_high_does_not_hide_the_wearer():
    # e144: Ken's only turn opens with two seconds of the owner, the louder voice, so it can read high.
    w = Wearer()
    w.update("1:A", 49.8, 0.94)
    w.update("1:A", 69.4, 0.73)
    w.update("1:B", 71.5, 0.49)
    assert w.find() == ("1:A", 59.6)
    w.update("1:B", 68.0, 0.5)  # but a second one makes it a second voice from above
    assert w.find() is None
    assert WEARER_MIN_ELEVATION == 45.0


def wearer_and_guest() -> tuple[np.ndarray, list[dict]]:
    """Screen-frame audio: A, a guest at the wearer's left, nearly level; B, the wearer, from high above (so high that
    the flat confidence reads mostly room, as the owner's turns did in 73b5); two turns each."""
    gap = np.zeros((int(0.5 * RATE), 4))
    parts, script = [], []
    for i, (who, az, el, text) in enumerate((
        ("A", 60, 15, "Hey, Eric. I'm Ken from Vexy."),
        ("B", 0, 75, "Ken! I'll send you the deck tonight."),
        ("A", 50, 25, "Great, thanks."),
        ("B", 10, 78, "And you'll intro me to your CTO?"),
    )):
        parts += [encode_up(voice(1.0), az, el), gap]
        script.append({"start_ms": i * 1500, "end_ms": i * 1500 + 1000, "speaker": who, "text": text})
    return np.concatenate(parts) + diffuse(6.0, 0.01), script


class StubSpark:
    """Muse Spark stand-in: keeps every prompt, and names the owner as it is told to (no network)."""

    def __init__(self, owner=()):
        self.owner, self.prompts = list(owner), []

    async def __call__(self, system, user, **kw):
        self.prompts.append(user)
        await asyncio.sleep(0)
        return {"owner_speakers": list(self.owner), "turns": [], "people": [], "mentioned": [], "promises": [],
                "suspect_words": [], "translations": [], "room_topics": []}


def run_with_spark(tmp_path, foa, script, hello, spark, inverted=True):
    rec = Recording(
        tmp_path, hello, lambda sink, *, rate, hello: FakeAsr(sink, rate=rate, script=hello.fake_script),
        lambda h: Extractor(spark, h.owner_name, h.owner_company, []), make_second=lambda: None,
    )

    async def run():
        await rec.start()
        rec.on_pose({"t_ms": 0, "yaw": 0.0, "inverted": inverted})
        data = foa.tobytes()
        for i in range(0, len(data), 4 * 2 * 4800):
            await rec.on_audio(data[i : i + 4 * 2 * 4800])
            await asyncio.sleep(0)
        await rec.close()

    asyncio.run(run())
    return read_events(rec.dir / "events.jsonl")


def test_an_iphone_badge_names_the_owner_by_elevation_and_the_prompt_marks_him(tmp_path):
    foa, script = wearer_and_guest()
    spark = StubSpark()  # names no owner itself: only the elevation can
    events = run_with_spark(tmp_path, to_int16(camera_axes(foa)), script, badge_hello(script, owner_name="Eric"), spark)
    positions = [e for e in events if e["type"] == "position"]
    assert [e["elevation"] for e in positions] == [pytest.approx(x, abs=5) for x in (15, 75, 25, 78)]
    assert all(e["confidence"] < 0.3 for e in positions if e["speaker"] == "1:B")  # the 3-D share is what counts
    (owner,) = [e for e in events if e["type"] == "owner"]
    assert owner["speakers"] == ["1:B"] and owner["source"] == "elevation"
    assert owner["elevation"] == pytest.approx(76.5, abs=5)
    assert owner["t_ms"] == script[3]["end_ms"]  # at the wearer's second turn
    assert fold_record(events)["owner_speakers"] == ["1:B"]  # a later Spark run listing nobody does not undo it
    last = spark.prompts[-1]
    assert "Owner's voice: speaker 1:B" in last
    assert "turn 4 [1:B, Eric (owner)]" in last and "turn 3 [1:A]" in last


def test_the_elevation_joins_the_owner_spark_named_and_does_not_replace_it(tmp_path):
    foa, script = wearer_and_guest()
    spark = StubSpark(owner=["1:C"])  # say Spark had heard him introduce himself under another label too
    events = run_with_spark(tmp_path, to_int16(camera_axes(foa)), script, badge_hello(script, owner_name="Eric"), spark)
    assert fold_record(events)["owner_speakers"] == ["1:B", "1:C"]


def test_rehearsal_audio_never_names_the_owner_by_elevation(tmp_path):
    # The same voices, synthesised in the screen frame and streamed as the simulator (upright, as stream_wav.py
    # sends it): Eric still reads from high above, but the owner comes from the transcript only.
    foa, script = wearer_and_guest()
    spark = StubSpark()
    hello = badge_hello(script, owner_name="Eric", device="simulator")
    events = run_with_spark(tmp_path, to_int16(foa), script, hello, spark, inverted=False)
    assert [e["elevation"] > 45 for e in events if e["type"] == "position"] == [False, True, False, True]
    assert not [e for e in events if e["type"] == "owner"]
    assert all("(owner)" not in p and "Owner's voice" not in p for p in spark.prompts)


def test_no_owner_by_elevation_when_nobody_speaks_from_above(tmp_path):
    foa, script = wearer_and_guest()
    level = np.concatenate([
        encode_up(voice(1.0), az, el) if i % 2 == 0 else np.zeros((int(0.5 * RATE), 4))
        for az, el in ((60, 15), (0, 20), (50, 25), (10, 30)) for i in range(2)
    ]) + diffuse(6.0, 0.01)
    events = run_with_spark(tmp_path, to_int16(camera_axes(level)), script, badge_hello(script), StubSpark())
    assert not [e for e in events if e["type"] == "owner"]
