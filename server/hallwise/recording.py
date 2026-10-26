"""One live recording.

Takes the badge's audio and orientation messages, keeps the original multichannel audio, feeds a mono mix to
speech recognition, and writes everything to the recording's event log.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
import wave
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soxr

from .asr import Asr
from .direction import DirectionTracker, SpeakerPositions
from .events import EventLog, fold_record
from .extract import Extractor, Turn, draft_next_moves
from .people import history_event, match, people_index

ASR_RATE = 24_000
LAYOUT_CHANNELS = {"mono": 1, "stereo": 2, "foa": 4}


@dataclass
class Hello:
    """The first message from a capture device."""

    sample_rate: int
    channels: int
    layout: str  # "mono", "stereo", or "foa" (ambisonics, ACN order, SN3D: W Y Z X)
    device: str = ""
    owner_name: str = ""
    owner_company: str = ""
    event: str = ""  # which event and where, so a list of recordings reads like a diary
    venue: str = ""
    language_bias: list[str] | None = None
    keywords: list[str] | None = None
    busy: list[list[str]] | None = None  # the owner's calendar for the week, ISO ranges, for proposing times
    links: dict[str, str] | None = None  # deck / one_pager / blurb the owner can hand over
    tz: str = ""
    now: str = ""  # the phone's clock at start, ISO 8601 with offset
    fake_script: list[dict[str, Any]] | None = field(default=None, repr=False)  # rig ground truth, offline only

    @classmethod
    def parse(cls, msg: dict[str, Any]) -> "Hello":
        hello = cls(
            sample_rate=int(msg["sample_rate"]),
            channels=int(msg["channels"]),
            layout=str(msg["layout"]),
            device=str(msg.get("device", "")),
            owner_name=str(msg.get("owner_name", "")),
            owner_company=str(msg.get("owner_company", "")),
            event=str(msg.get("event", "")),
            venue=str(msg.get("venue", "")),
            language_bias=msg.get("language_bias"),
            keywords=msg.get("keywords"),
            busy=msg.get("busy"),
            links=msg.get("links"),
            tz=str(msg.get("tz", "")),
            now=str(msg.get("now", "")),
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
    def __init__(
        self,
        root: Path,
        hello: Hello,
        make_asr: Callable[..., Asr],
        make_extractor: Callable[[Hello], Extractor | None] | None = None,
    ):
        self.id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.dir = root / "recordings" / self.id
        self.dir.mkdir(parents=True)
        self.known = people_index(root, exclude=self.id)  # everyone met at earlier recordings
        self.hello = hello
        meta = {k: v for k, v in hello.__dict__.items() if k != "fake_script"}
        self.started = time.time()
        (self.dir / "meta.json").write_text(json.dumps({"id": self.id, "started": self.started, **meta}))
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
        self.direction = DirectionTracker(hello.sample_rate, hello.layout)
        self.speaker_positions = SpeakerPositions()
        # Names from earlier evenings go to the transcriber as hints, so a hard surname is heard the way
        # it was spelled before.
        names = [e["name"] for e in self.known[:40] if e.get("name")]
        hello.keywords = list(dict.fromkeys((hello.keywords or []) + names))
        self.asr = make_asr(self._on_asr, rate=ASR_RATE, hello=hello)
        self._make_asr = make_asr
        self._ask_asr: Asr | None = None  # while the owner holds to talk, audio goes here instead
        self._ask_turns: list[str] = []
        self.extractor = make_extractor(hello) if make_extractor else None
        self._history_sent: set[str] = set()
        if self.extractor is not None:
            self.extractor.known = [
                e["name"] + (f", {e['company']}" if e["company"] else "") for e in self.known[:60]
            ]
        self._extract_task: asyncio.Task[None] | None = None
        self._extracted_upto = 0  # how many turns the latest finished run had seen

    @property
    def now_ms(self) -> int:
        return int(self._frames * 1000 / self.hello.sample_rate)

    async def start(self) -> None:
        self.log.emit(
            "recording_start",
            0,
            recording=self.id,
            device=self.hello.device,
            event=self.hello.event,
            venue=self.hello.venue,
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
        self.direction.add(frames)
        mono = to_mono(frames, self.hello.layout)
        if self._resampler is not None:
            mono = self._resampler.resample_chunk(mono)
        if len(mono):
            pcm = mono.astype("<i2").tobytes()
            if self._ask_asr is not None:
                await self._ask_asr.send(pcm)  # the question is not part of the conversation
            else:
                await self.asr.send(pcm)

    def on_pose(self, msg: dict[str, Any]) -> None:
        t_ms = int(msg.get("t_ms", self.now_ms))
        inverted = bool(msg.get("inverted", False))  # older badges never send it: upright
        if msg.get("yaw") is not None:
            self.direction.add_pose(t_ms, float(msg["yaw"]), inverted)
        extra = {"inverted": inverted} if "inverted" in msg else {}
        self.log.emit("device_pose", t_ms, yaw=msg.get("yaw"), pitch=msg.get("pitch"), roll=msg.get("roll"), **extra)

    def _on_asr(self, type: str, t_ms: int, **data: Any) -> None:
        self.log.emit(type, t_ms, **data)
        if type == "turn":
            self._locate(data)
        if type == "turn" and self.extractor is not None and data.get("text"):
            self.extractor.add_turn(
                Turn(
                    turn=data["turn"],
                    speaker=f"{data.get('session', 1)}:{data.get('speaker') or '?'}",
                    start_ms=data["start_ms"],
                    end_ms=data["end_ms"],
                    text=data["text"],
                )
            )
            if self._extract_task is None or self._extract_task.done():
                self._extract_task = asyncio.get_running_loop().create_task(self._extract())

    def _locate(self, turn: dict[str, Any]) -> None:
        """Where this turn came from, and where its speaker stands in the room so far."""
        where = self.direction.direction(turn["start_ms"], turn["end_ms"])
        if where is None:
            return
        speaker = f"{turn.get('session', 1)}:{turn.get('speaker') or '?'}"
        self.log.emit("position", turn["end_ms"], turn=turn["turn"], speaker=speaker, **where)
        placed = self.speaker_positions.update(
            speaker, where["azimuth_room"], where["confidence"], turn["end_ms"] - turn["start_ms"], where["level_db"]
        )
        if placed is not None:
            self.log.emit("speaker_position", turn["end_ms"], speaker=speaker, **placed)

    async def _extract(self) -> None:
        """Run until the latest run has seen every turn; a turn arriving mid-run triggers one more run."""
        while self.extractor is not None and self._extracted_upto < len(self.extractor.turns):
            seen = len(self.extractor.turns)
            try:
                for kind, t_ms, data in await self.extractor.run():
                    self.log.emit(kind, t_ms, **data)
                    if kind == "person" and data["key"] not in self._history_sent:
                        entry = match(self.known, data.get("name", ""), data.get("company", ""))
                        if entry is not None:
                            self._history_sent.add(data["key"])
                            history = history_event(entry, data["key"], exclude=self.id, before=self.started)
                            if history["encounters"]:
                                self.log.emit("person_history", t_ms, **history)
            except Exception as err:  # a failed run must not stop the recording
                self.log.emit("extract_error", self.now_ms, message=f"{err.__class__.__name__}: {err}"[:300])
            self._extracted_upto = seen

    async def close(self) -> None:
        if self._resampler is not None:
            tail = self._resampler.resample_chunk(np.zeros(0, dtype=np.int16), last=True)
            if len(tail):
                await self.asr.send(tail.astype("<i2").tobytes())
        await self.asr.finish()
        if self._extract_task is not None:
            await self._extract_task
        await self._extract()
        await self._next_moves()
        self._wav.close()
        self.log.emit("recording_end", self.now_ms)
        self.log.close()

    async def start_ask(self) -> None:
        """Hold to talk: from now until end_ask the badge's audio is a question, transcribed on its own."""
        if self._ask_asr is not None:
            return
        self._ask_turns = []

        def sink(type: str, t_ms: int, **d: Any) -> None:
            if type == "turn" and d.get("text"):
                self._ask_turns.append(str(d["text"]))

        self._ask_asr = self._make_asr(sink, rate=ASR_RATE, hello=replace(self.hello, fake_script=None))
        await self._ask_asr.start()

    async def end_ask(self) -> str:
        asr, self._ask_asr = self._ask_asr, None
        if asr is None:
            return ""
        await asr.finish()
        question = " ".join(self._ask_turns).strip()
        self.log.emit("ask", self.now_ms, question=question)
        return question

    async def _next_moves(self) -> None:
        """After the last extraction: one ready-to-send follow-up per promise, before the log closes, so a
        phone still watching gets them the moment it stops."""
        if self.extractor is None or not self.extractor.state.get("promises"):
            return
        try:
            moves = await draft_next_moves(
                self.extractor.llm,
                fold_record(self.log.events()),
                owner_name=self.hello.owner_name,
                owner_company=self.hello.owner_company,
                event=self.hello.event,
                venue=self.hello.venue,
                now=self.hello.now or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                tz=self.hello.tz,
                busy=self.hello.busy or [],
                links=self.hello.links or {},
            )
        except Exception as err:  # drafts are a bonus; the record is already safe
            self.log.emit("extract_error", self.now_ms, message=f"next moves: {err.__class__.__name__}: {err}"[:300])
            return
        for move in moves:
            self.log.emit("next_move", self.now_ms, **move)
