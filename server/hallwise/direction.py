"""Where each voice comes from.

The badge sends first-order ambisonics: ACN channel order W, Y, Z, X with SN3D weights, so a single source at
azimuth θ (counter-clockwise from the X axis) arrives as W = s, X = s·cos θ, Y = s·sin θ. The active intensity
(Σ W·X, Σ W·Y) over a turn therefore points at whoever was talking, relative to the phone. Adding the phone's yaw
at that moment gives a bearing in the room, which stays put when the wearer turns or leans in to listen.

Only the louder half of a turn's 20 ms blocks counts, so the talker's own voice outweighs the room around them.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

import numpy as np

BLOCK_MS = 20


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
    def __init__(self, sample_rate: int, layout: str):
        self.layout = layout
        self.block = sample_rate * BLOCK_MS // 1000
        self._carry = np.zeros((0, 4))
        self._ix: list[float] = []
        self._iy: list[float] = []
        self._energy: list[float] = []
        self._pose_t: list[int] = []
        self._pose_yaw: list[float] = []

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
        w, y, x = b[:, :, 0], b[:, :, 1], b[:, :, 3]
        self._ix.extend((w * x).sum(axis=1).tolist())
        self._iy.extend((w * y).sum(axis=1).tolist())
        self._energy.extend((w * w).sum(axis=1).tolist())

    def add_pose(self, t_ms: int, yaw_deg: float) -> None:
        i = bisect_right(self._pose_t, t_ms)
        self._pose_t.insert(i, t_ms)
        self._pose_yaw.insert(i, yaw_deg)

    def yaw(self, start_ms: int, end_ms: int) -> float | None:
        """The phone's mean yaw over [start, end), or the last reading before it."""
        lo, hi = bisect_left(self._pose_t, start_ms), bisect_left(self._pose_t, end_ms)
        if hi > lo:
            return circular_mean(self._pose_yaw[lo:hi], [1.0] * (hi - lo))[0]
        if lo > 0:
            return self._pose_yaw[lo - 1]
        return self._pose_yaw[0] if self._pose_yaw else None  # the first reading, if it came late

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
        device = math.degrees(math.atan2(iy, ix))
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
            "confidence": round(min(1.0, math.hypot(ix, iy) / e), 2),
            "level_db": round(level_db, 1),
        }


@dataclass
class SpeakerPositions:
    """Each speaker's position in the room: the confidence- and duration-weighted mean of their turns."""

    min_confidence: float = 0.3
    _angles: dict[str, list[float]] = field(default_factory=dict)
    _weights: dict[str, list[float]] = field(default_factory=dict)
    _levels: dict[str, list[float]] = field(default_factory=dict)

    def update(
        self, speaker: str, azimuth: float, confidence: float, duration_ms: int, level_db: float | None = None
    ) -> dict[str, float] | None:
        if confidence < self.min_confidence:
            return None
        self._angles.setdefault(speaker, []).append(azimuth)
        self._weights.setdefault(speaker, []).append(confidence * max(duration_ms, 1) / 1000)
        if level_db is not None:
            self._levels.setdefault(speaker, []).append(level_db)
        mean, spread = circular_mean(self._angles[speaker], self._weights[speaker])
        out: dict[str, float] = {"azimuth": round(mean, 1), "spread": round(spread, 1), "turns": len(self._angles[speaker])}
        if self._levels.get(speaker):
            levels = self._levels[speaker]
            out["level_db"] = round(sum(levels) / len(levels), 1)
        return out
