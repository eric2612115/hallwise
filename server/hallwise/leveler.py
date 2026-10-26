"""A gentle automatic gain for the recogniser's copy of the mono mix.

At the badge the wearer's own voice is 10-17 dB louder than a guest a metre or two away, and Muse Voice Transcribe
dropped far guests' turns next to it. `Leveler` evens that out before the audio goes to the recogniser: it follows
the level of whoever is talking, lifts quiet talkers and turns the wearer down, with a ceiling for peaks. The saved
audio.wav never passes through it.

How, per 10 ms block:
- the room's level is a low percentile (5 %) of the last ten seconds of blocks, and only blocks 14 dB above it
  count as speech;
- over speech, the talker's level is the block power averaged over a few hundred milliseconds, and the gain moves
  it three quarters of the way to the target (4:1), at most +12 / -12 dB; a talker barely above the room (the
  hall's own babble) gets no lift: below a knee 16 dB over the room the lift fades out;
- in a pause the gain holds, then after 0.8 s drifts back to 0 dB, so the room is not pumped up in a silence;
- the gain ramps across each block, and is cut at once when a block's peak would pass the ceiling.

Slow on purpose. A first version followed every syllable (20 ms attack) and squashed the syllables against the
room; from 2.2 m the recogniser then lost Kenji's Japanese aside in all of seven tries, against 7 of 12 without
levelling. Moving at the pace of phrases, it lifts a far talker by ~5 dB relative to the wearer on the rehearsal
mix, and Julien's introduction right after the wearer came through as a turn of its own in 4 of 4 tries (16 of 16
across the variants tried), against 4 of 8 without levelling.
A Python loop over 100 blocks a second with a few numpy operations each: well under 1 % of real time.
"""

from __future__ import annotations

import math

import numpy as np

FULL_SCALE = 32768.0


class Leveler:
    def __init__(
        self,
        rate: int,
        *,
        target_db: float = -22.0,
        ratio: float = 4.0,
        max_boost_db: float = 12.0,
        max_cut_db: float = 12.0,
        ceiling_db: float = -1.0,
        speech_above_floor_db: float = 14.0,
        knee_above_floor_db: float = 16.0,
        expand: float = 2.0,
        speech_min_db: float = -58.0,
        block_ms: int = 10,
        level_up_ms: float = 300.0,
        level_down_ms: float = 200.0,
        gain_up_ms: float = 300.0,
        gain_down_ms: float = 100.0,
        hold_ms: float = 800.0,
        return_ms: float = 1500.0,
        floor_window_s: float = 10.0,
        floor_percentile: float = 5.0,
    ):
        self.rate = rate
        self.block = max(1, rate * block_ms // 1000)
        self.target_db = target_db
        self.slope = 1.0 - 1.0 / ratio
        self.max_boost_db = max_boost_db
        self.max_cut_db = max_cut_db
        self.ceiling = FULL_SCALE * 10 ** (ceiling_db / 20)
        self.speech_above_floor_db = speech_above_floor_db
        self.knee_above_floor_db = knee_above_floor_db
        self.expand = expand
        self.speech_min_db = speech_min_db
        self.hold_ms = hold_ms
        self._k = {
            name: ms for name, ms in
            (("level_up", level_up_ms), ("level_down", level_down_ms), ("gain_up", gain_up_ms),
             ("gain_down", gain_down_ms), ("return", return_ms))
        }
        self._history = np.zeros(max(1, int(floor_window_s * 1000 / block_ms)))
        self._filled = 0
        self.floor_percentile = floor_percentile
        self.floor_db = -60.0
        self.level_db: float | None = None  # the current talker's level, None before any speech
        self._power: float | None = None
        self.gain_db = 0.0  # applied gain at the end of the last block
        self._quiet_ms = 0.0

    @staticmethod
    def _coeff(ms: float, dt_ms: float) -> float:
        return 1.0 - math.exp(-dt_ms / max(ms, 1e-6))

    def _curve(self, level: float) -> float:
        """The gain for a talker at `level`: 3:1 toward the target, and below the knee (near the room's own level)
        the lift fades out, so the hall's babble is not raised to the level of a guest."""
        def toward_target(at: float) -> float:
            return min(self.max_boost_db, max(-self.max_cut_db, (self.target_db - at) * self.slope))

        knee = max(self.floor_db + self.knee_above_floor_db, self.speech_min_db)
        if level >= knee:
            return toward_target(level)
        return max(0.0, min(toward_target(level), toward_target(knee) - (knee - level) * self.expand))

    def process(self, pcm: np.ndarray) -> np.ndarray:
        """int16 mono in, int16 mono out, same length; keeps its state between calls."""
        if not len(pcm):
            return pcm.astype(np.int16)
        x = pcm.astype(np.float64)
        out = np.empty_like(x)
        for a in range(0, len(x), self.block):
            b = x[a : a + self.block]
            out[a : a + len(b)] = b * self._step(b)
        return np.clip(np.round(out), -32768, 32767).astype(np.int16)

    def _step(self, b: np.ndarray) -> np.ndarray:
        """Advance over one block; return its per-sample linear gain."""
        dt = len(b) * 1000.0 / self.rate
        power = float(np.mean(b * b)) / FULL_SCALE**2
        level = 10 * math.log10(power + 1e-12)
        # The room's own level: a low percentile of the last few seconds. Even mid-sentence a tenth of the blocks
        # fall between syllables, so it stays the room's level while someone talks; a single silent block does not
        # drag it down the way a running minimum would.
        self._history[self._filled % len(self._history)] = level
        self._filled += 1
        self.floor_db = float(np.percentile(self._history[: min(self._filled, len(self._history))], self.floor_percentile))
        speech = level > max(self.floor_db + self.speech_above_floor_db, self.speech_min_db)

        if speech:
            self._quiet_ms = 0.0
            # Averaged as power, not in dB: syllable peaks dominate, as they do in what we hear as loudness, so the
            # gaps between syllables do not read as a quieter talker, and the gain hardly moves within a phrase.
            if self._power is None:
                self._power = power
            else:
                k = self._coeff(self._k["level_up" if power > self._power else "level_down"], dt)
                self._power += (power - self._power) * k
            self.level_db = 10 * math.log10(self._power + 1e-12)
            want = self._curve(self.level_db)
            new = self.gain_db + (want - self.gain_db) * self._coeff(
                self._k["gain_up" if want > self.gain_db else "gain_down"], dt
            )
        else:
            self._quiet_ms += dt
            new = self.gain_db  # hold through a pause between words or talkers
            if self._quiet_ms > self.hold_ms:  # then let go: a long silence is the room, not a quiet talker
                new = self.gain_db * (1 - self._coeff(self._k["return"], dt))
        peak = float(np.max(np.abs(b)))
        if peak > 0:
            new = min(new, 20 * math.log10(self.ceiling / peak))
        start, self.gain_db = self.gain_db, new
        if new < start:  # a cut takes effect at the start of the block, so the ramp cannot overshoot the ceiling
            return np.full(len(b), 10 ** (new / 20))
        return 10 ** (np.linspace(start, new, len(b) + 1)[1:] / 20)
