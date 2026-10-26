"""One live recording.

Takes the badge's audio and orientation messages, keeps the original multichannel audio, feeds a mono mix to
speech recognition, and writes everything to the recording's event log.
"""

from __future__ import annotations

import json
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soxr

from .asr import Asr
from .events import EventLog

ASR_RATE = 24_000
LAYOUT_CHANNELS = {"mono": 1, "stereo": 2, "foa": 4}


@dataclass
class Hello:
    """The first message from a capture device."""

    sample_rate: int
    channels: int
    layout: str  # "mono", "stereo", or "foa" (ambisonics, ACN order, SN3D: W Y Z X)
    device: str = ""
    language_bias: list[str] | None = None
    keywords: list[str] | None = None
    fake_script: list[dict[str, Any]] | None = field(default=None, repr=False)  # rig ground truth, offline only

    @classmethod
    def parse(cls, msg: dict[str, Any]) -> "Hello":
        hello = cls(
            sample_rate=int(msg["sample_rate"]),
            channels=int(msg["channels"]),
            layout=str(msg["layout"]),
            device=str(msg.get("device", "")),
            language_bias=msg.get("language_bias"),
            keywords=msg.get("keywords"),
            fake_script=msg.get("fake_script"),
        )
        if hello.layout not in LAYOUT_CHANNELS:
            raise ValueError(f"layout must be one of {sorted(LAYOUT_CHANNELS)}")
        if hello.channels != LAYOUT_CHANNELS[hello.layout]:
            raise ValueError(f"layout {hello.layout} has {LAYOUT_CHANNELS[hello.layout]} channels, not {hello.channels}")
        if not 8_000 <= hello.sample_rate <= 96_000:
            raise ValueError(f"unsupported sample rate {hello.sample_rate}")
        return hello


def to_mono(frames: np.ndarray, layout: str) -> np.ndarray:
    """frames: (n, channels) int16 → (n,) int16 for speech recognition."""
    if layout == "stereo":
        return ((frames[:, 0].astype(np.int32) + frames[:, 1]) // 2).astype(np.int16)
    return frames[:, 0].copy()  # mono, or the omnidirectional W channel of FOA


class Recording:
    def __init__(self, root: Path, hello: Hello, make_asr: Callable[..., Asr]):
        self.id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.dir = root / "recordings" / self.id
        self.dir.mkdir(parents=True)
        self.hello = hello
        meta = {k: v for k, v in hello.__dict__.items() if k != "fake_script"}
        (self.dir / "meta.json").write_text(json.dumps({"id": self.id, "started": time.time(), **meta}))
        self.log = EventLog(self.dir / "events.jsonl")
        self._wav = wave.open(str(self.dir / "audio.wav"), "wb")
        self._wav.setnchannels(hello.channels)
        self._wav.setsampwidth(2)
        self._wav.setframerate(hello.sample_rate)
        self._resampler = (
            None if hello.sample_rate == ASR_RATE else soxr.ResampleStream(hello.sample_rate, ASR_RATE, 1, dtype="int16")
        )
        self._frames = 0
        self._pending = b""
        self.asr = make_asr(self._on_asr, rate=ASR_RATE, hello=hello)

    @property
    def now_ms(self) -> int:
        return int(self._frames * 1000 / self.hello.sample_rate)

    async def start(self) -> None:
        self.log.emit(
            "recording_start",
            0,
            recording=self.id,
            device=self.hello.device,
            layout=self.hello.layout,
            sample_rate=self.hello.sample_rate,
            channels=self.hello.channels,
        )
        await self.asr.start()

    async def on_audio(self, data: bytes) -> None:
        data = self._pending + data
        frame_bytes = 2 * self.hello.channels
        usable = len(data) - len(data) % frame_bytes
        self._pending = data[usable:]
        if not usable:
            return
        chunk = data[:usable]
        self._wav.writeframes(chunk)
        frames = np.frombuffer(chunk, dtype="<i2").reshape(-1, self.hello.channels)
        self._frames += len(frames)
        mono = to_mono(frames, self.hello.layout)
        if self._resampler is not None:
            mono = self._resampler.resample_chunk(mono)
        if len(mono):
            await self.asr.send(mono.astype("<i2").tobytes())

    def on_pose(self, msg: dict[str, Any]) -> None:
        self.log.emit(
            "device_pose",
            int(msg.get("t_ms", self.now_ms)),
            yaw=msg.get("yaw"),
            pitch=msg.get("pitch"),
            roll=msg.get("roll"),
        )

    def _on_asr(self, type: str, t_ms: int, **data: Any) -> None:
        self.log.emit(type, t_ms, **data)

    async def close(self) -> None:
        if self._resampler is not None:
            tail = self._resampler.resample_chunk(np.zeros(0, dtype=np.int16), last=True)
            if len(tail):
                await self.asr.send(tail.astype("<i2").tobytes())
        await self.asr.finish()
        self._wav.close()
        self.log.emit("recording_end", self.now_ms)
        self.log.close()
