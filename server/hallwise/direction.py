"""Where each voice comes from.

The badge sends first-order ambisonics: ACN channel order W, Y, Z, X with SN3D weights, so a single source at
azimuth θ (counter-clockwise from the X axis) arrives as W = s, X = s·cos θ, Y = s·sin θ. The active intensity
(Σ W·X, Σ W·Y) over a turn therefore points at whoever was talking, relative to the phone. Adding the phone's yaw
at that moment gives a bearing in the room, which stays put when the wearer turns or leans in to listen.

Which way "X" points depends on who made the audio. The rig and the rehearsal audio are in the screen frame: +X is
the screen normal, "ahead" is the screen side, and a positive azimuth is the wearer's left. An iPhone's own
`.firstOrderAmbisonics` is in Apple's camera frame, built for filming: +X points out of the BACK of the phone, where
the rear camera looks, so front and back come out swapped (measured on an iPhone 17 Pro: the screen side at ±175°,
the back at -10°, in a take with the phone standing still). That is a half turn about the vertical axis (X and Y
negate, Z stays), so a `camera` frame is rotated by 180° before anything else; a source on the phone's left stays
on its left because the half turn also turns the left itself round. Which frame a recording is in is the hello's
`foa_frame` (recording.py).

The badge's "yaw" is the direction its screen faces (taken from the attitude matrix, not Euler yaw, which locks up
on an upright phone). A phone hanging top-down on its lanyard is turned 180° about the screen normal, so its left
and right swap, and so do its up and down: its poses say `inverted`. In the screen frame the azimuth it hears is
negated back into the wearer's frame before the yaw is added (and the elevation with it). An iPhone's own
ambisonics needs none of that: iOS already turns the ambisonic frame with the phone (FRAME_UPRIGHT).

The elevation (Z, ACN channel 2, against the horizontal intensity) is what tells the wearer apart: the mouth is a
hand's width above a badge on the chest, so the wearer's own voice arrives from high above and everyone else's
from about level (Wearer).

Only the louder half of a turn's 20 ms blocks counts, so the talker's own voice outweighs the room around them.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

import numpy as np

BLOCK_MS = 20

# How far the microphones' azimuth is turned to reach the screen frame, per `foa_frame`.
FRAME_ROTATION = {"screen": 0.0, "camera": 180.0}

# Whether the audio already arrives upright when the phone hangs top-down, per `foa_frame`. An iPhone's own
# ambisonics does: measured on an iPhone 17 Pro hanging upside down on the owner's chest (recordings
# 20261027-195430-73b5 and 20261027-195003-e144), the owner's own voice still read from above (+52° to +83°), and
# with the top-down negation a guest on the wearer's left came out negative and one on the right positive; without
# it, left came out near +145° and right near -160°. The screen frame (the rig, the rehearsal audio) does not.
FRAME_UPRIGHT = {"screen": False, "camera": True}

# The wearer's own voice arrives from above the badge. Measured on that iPhone on the owner's chest, per second,
# 300-4000 Hz: the owner read +52° to +83°, a guest standing at his front, left, back or right -24° to +39°, and a
# threshold near +45° split them every time. Per turn (broadband, the louder half of the blocks, as here) the owner's
# four turns read +50° to +73° and the guest's five confident ones +8° to +36°: medians +68.5° against +22.8° (73b5).
WEARER_MIN_ELEVATION = 45.0
WEARER_MARGIN = 20.0  # "clearly above": the wearer's median beats every other voice's by at least this much
WEARER_MIN_TURNS = 2
# Of the 3-D intensity (confidence_3d): the wearer's voice comes from nearly straight up, so the flat `confidence`
# reads it as mostly room (0.22 and 0.25 for the owner's two turns in 73b5) when it is mostly direct sound (0.72, 0.57).
WEARER_MIN_CONFIDENCE = 0.3


def wrap(degrees: float) -> float:
    """Angle in (-180, 180]."""
    a = (degrees + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def circular_mean(angles: list[float], weights: list[float]) -> tuple[float, float]:
    """Weighted mean direction and circular standard deviation, both in degrees."""
    c = sum(w * math.cos(math.radians(a)) for a, w in zip(angles, weights))
    s = sum(w * math.sin(math.radians(a)) for a, w in zip(angles, weights))
    total = sum(weights)
    r = math.hypot(c, s) / total if total else 0.0
    spread = math.degrees(math.sqrt(-2 * math.log(r))) if 0 < r < 1 else (0.0 if r >= 1 else 180.0)
    return wrap(math.degrees(math.atan2(s, c))), spread


class DirectionTracker:
    def __init__(self, sample_rate: int, layout: str, frame: str = "screen"):
        if frame not in FRAME_ROTATION:
            raise ValueError(f"foa frame must be one of {sorted(FRAME_ROTATION)}")
        self.layout = layout
        self.frame = frame
        self.block = sample_rate * BLOCK_MS // 1000
        self._carry = np.zeros((0, 4))
        self._ix: list[float] = []
        self._iy: list[float] = []
        self._iz: list[float] = []
        self._energy: list[float] = []
        self._pose_t: list[int] = []
        self._pose_yaw: list[float] = []
        self._pose_inverted: list[bool] = []

    def add(self, frames: np.ndarray) -> None:
        """frames: (n, channels) int16 as received. Only first-order ambisonics carries direction."""
        if self.layout != "foa":
            return
        data = np.concatenate([self._carry, frames.astype(np.float64)])
        blocks = len(data) // self.block
        self._carry = data[blocks * self.block :]
        if not blocks:
            return
        b = data[: blocks * self.block].reshape(blocks, self.block, 4)
        b = b - b.mean(axis=1, keepdims=True)  # drop DC per block
        w, y, z, x = b[:, :, 0], b[:, :, 1], b[:, :, 2], b[:, :, 3]
        self._ix.extend((w * x).sum(axis=1).tolist())
        self._iy.extend((w * y).sum(axis=1).tolist())
        self._iz.extend((w * z).sum(axis=1).tolist())
        self._energy.extend((w * w).sum(axis=1).tolist())

    def add_pose(self, t_ms: int, yaw_deg: float, inverted: bool = False) -> None:
        i = bisect_right(self._pose_t, t_ms)
        self._pose_t.insert(i, t_ms)
        self._pose_yaw.insert(i, yaw_deg)
        self._pose_inverted.insert(i, bool(inverted))

    def yaw(self, start_ms: int, end_ms: int) -> float | None:
        """The phone's mean yaw over [start, end), or the last reading before it."""
        lo, hi = bisect_left(self._pose_t, start_ms), bisect_left(self._pose_t, end_ms)
        if hi > lo:
            return circular_mean(self._pose_yaw[lo:hi], [1.0] * (hi - lo))[0]
        if lo > 0:
            return self._pose_yaw[lo - 1]
        return self._pose_yaw[0] if self._pose_yaw else None  # the first reading, if it came late

    def inverted(self, start_ms: int, end_ms: int) -> bool:
        """Whether the phone hung top-down over [start, end): most of the readings in it, else the same fallbacks as
        yaw(). With no orientation data at all, upright."""
        lo, hi = bisect_left(self._pose_t, start_ms), bisect_left(self._pose_t, end_ms)
        if hi > lo:
            return 2 * sum(self._pose_inverted[lo:hi]) > hi - lo
        if lo > 0:
            return self._pose_inverted[lo - 1]
        return self._pose_inverted[0] if self._pose_inverted else False

    def direction(self, start_ms: int, end_ms: int) -> dict[str, float | None] | None:
        i0 = max(0, start_ms // BLOCK_MS)
        i1 = min(len(self._energy), max(i0 + 1, end_ms // BLOCK_MS))
        if i1 <= i0:
            return None
        energy = np.array(self._energy[i0:i1])
        loud = energy >= np.median(energy)
        e = float(energy[loud].sum())
        if e <= 0:
            return None
        ix = float(np.array(self._ix[i0:i1])[loud].sum())
        iy = float(np.array(self._iy[i0:i1])[loud].sum())
        iz = float(np.array(self._iz[i0:i1])[loud].sum())
        # The one place the audio's own frame becomes the screen frame; everything after it is in the screen frame.
        # The half turn of the camera frame is about the vertical axis, so it leaves the elevation alone.
        device = math.degrees(math.atan2(iy, ix)) + FRAME_ROTATION[self.frame]
        elevation = math.degrees(math.atan2(iz, math.hypot(ix, iy)))
        inverted = self.inverted(start_ms, end_ms)
        if inverted and not FRAME_UPRIGHT[self.frame]:
            device = -device  # top-down, the microphones' left is the wearer's right
            elevation = -elevation  # and their up is the wearer's down
        yaw = self.yaw(start_ms, end_ms)
        # Loudness of the talker over their louder blocks, in dBFS of the omni channel: nearer is louder.
        # Together with confidence (direct sound vs room reverberation) it is the cue for distance; the UI
        # turns it into near/far relative to the other voices in the room.
        rms = math.sqrt(e / (int(loud.sum()) * self.block))
        level_db = 20 * math.log10(max(rms, 1e-9) / 32768)
        # With no orientation data at all, the room frame is the badge frame.
        return {
            "azimuth_device": round(wrap(device), 1),
            "azimuth_room": round(wrap(device + (yaw or 0.0)), 1),
            "has_pose": yaw is not None,
            "inverted": inverted,
            "confidence": round(min(1.0, math.hypot(ix, iy) / e), 2),
            # Degrees above the horizontal: the wearer's own voice comes from high up (Wearer). confidence_3d is the
            # same share of direct sound as `confidence`, counting the vertical part too.
            "elevation": round(elevation, 1),
            "confidence_3d": round(min(1.0, math.sqrt(ix * ix + iy * iy + iz * iz) / e), 2),
            "level_db": round(level_db, 1),
        }


@dataclass
class SpeakerPositions:
    """Each speaker's position in the room: the confidence- and duration-weighted mean of their turns.

    Only turns at or above `min_confidence` (mostly direct sound) make a position. A far or quiet talker can have
    none: two metres away, in a room, their turns come in at 0.2-0.3, and in rehearsal Julien, Kenji and the
    waiter got no dot at all. So until a speaker has a confident turn, their low-confidence turns make a
    provisional position, flagged `low_confidence`; the first confident turn replaces it, and from then on
    low-confidence turns no longer move it.
    """

    min_confidence: float = 0.3
    _angles: dict[str, list[float]] = field(default_factory=dict)
    _weights: dict[str, list[float]] = field(default_factory=dict)
    _levels: dict[str, list[float]] = field(default_factory=dict)
    _weak: dict[str, list[tuple[float, float, float | None]]] = field(default_factory=dict)  # azimuth, weight, level

    def update(
        self, speaker: str, azimuth: float, confidence: float, duration_ms: int, level_db: float | None = None
    ) -> dict[str, float | bool] | None:
        """Add one turn; return the speaker's position if it changed, else None."""
        weight = max(confidence, 0.0) * max(duration_ms, 1) / 1000
        if confidence < self.min_confidence:
            if speaker in self._angles:
                return None  # a confident position already stands
            weak = self._weak.setdefault(speaker, [])
            weak.append((azimuth, max(weight, 1e-6), level_db))
            return self._position([a for a, _, _ in weak], [w for _, w, _ in weak],
                                  [l for _, _, l in weak if l is not None], low_confidence=True)
        self._angles.setdefault(speaker, []).append(azimuth)
        self._weights.setdefault(speaker, []).append(weight)
        if level_db is not None:
            self._levels.setdefault(speaker, []).append(level_db)
        return self._position(self._angles[speaker], self._weights[speaker], self._levels.get(speaker, []))

    @staticmethod
    def _position(
        angles: list[float], weights: list[float], levels: list[float], low_confidence: bool = False
    ) -> dict[str, float | bool]:
        mean, spread = circular_mean(angles, weights)
        out: dict[str, float | bool] = {"azimuth": round(mean, 1), "spread": round(spread, 1), "turns": len(angles)}
        if levels:
            out["level_db"] = round(sum(levels) / len(levels), 1)
        if low_confidence:
            out["low_confidence"] = True
        return out


@dataclass
class Wearer:
    """Which speaker label is the badge's wearer: the one whose confident turns arrive from high above it.

    A label is the wearer once it has at least WEARER_MIN_TURNS turns at or above WEARER_MIN_CONFIDENCE (of the 3-D
    intensity), their median elevation is at least WEARER_MIN_ELEVATION, and that median is WEARER_MARGIN above the
    median of every other label with as many confident turns. A label with fewer turns does not count against it: a
    guest's turn often starts while the wearer is still talking (the speaker labels are wrong at the edges), and the
    wearer, a hand's width from the microphones, is the louder voice, so a single guest turn can read high (Ken's
    only turn in 20261027-195003-e144 opens with two seconds of the owner from +70° to +87°).

    Only for an iPhone's own audio (recording.py): the rehearsal audio places Eric at +70° too, and it keeps naming
    the owner from the transcript alone, as it always has.
    """

    _elevations: dict[str, list[float]] = field(default_factory=dict)

    def update(self, speaker: str, elevation: float | None, confidence: float | None) -> None:
        if elevation is None or (confidence or 0.0) < WEARER_MIN_CONFIDENCE:
            return
        self._elevations.setdefault(speaker, []).append(float(elevation))

    def medians(self) -> dict[str, float]:
        """Median elevation per label with enough confident turns to count."""
        return {s: float(np.median(e)) for s, e in self._elevations.items() if len(e) >= WEARER_MIN_TURNS}

    def find(self) -> tuple[str, float] | None:
        """The wearer's label and its median elevation, or None while no label is clearly high."""
        medians = self.medians()
        if not medians:
            return None
        top = max(medians, key=medians.__getitem__)
        rest = [m for s, m in medians.items() if s != top]
        if medians[top] < WEARER_MIN_ELEVATION or (rest and medians[top] - max(rest) < WEARER_MARGIN):
            return None
        return top, round(medians[top], 1)
