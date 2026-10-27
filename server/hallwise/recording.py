"""One live recording.

Takes the badge's audio and orientation messages, keeps the original multichannel audio, feeds a mono mix to
speech recognition, and writes everything to the recording's event log. The recogniser's copy of the mix is
levelled first (see leveler.py), so a guest two metres away is not lost next to the wearer's own voice; audio.wav
keeps the audio exactly as it arrived.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
import wave
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soxr

from .asr import Asr
from .direction import FRAME_ROTATION, DirectionTracker, SpeakerPositions, Wearer
from .events import EventLog, fold_record
from .extract import Extractor, Turn, build_prompt, draft_next_moves
from .leveler import Leveler
from .hooks import Threads
from .people import history_event, match, people_index
from .recall import Recall
from .second import SecondListener
from .places import parse_place

ASR_RATE = 24_000
LAYOUT_CHANNELS = {"mono": 1, "stereo": 2, "foa": 4}
IPHONE_BADGE = "iPhone badge"  # what the app's hello says for `device`
MAX_HINT_NAMES = 40
MAX_HINT_COMPANIES = 20


def recognition_hints(own: list[str], index: list[dict[str, Any]]) -> list[str]:
    """The badge's own hints, then the names of people met at earlier evenings, then their companies (each once):
    in rehearsal "Corvane Capital" was never transcribed while only Chloé Martin's name was a hint."""
    names = [e["name"] for e in index[:MAX_HINT_NAMES] if e.get("name")]
    companies = list(dict.fromkeys(e["company"] for e in index if e.get("company")))[:MAX_HINT_COMPANIES]
    out: dict[str, str] = {}
    for word in [*own, *names, *companies]:
        out.setdefault(word.strip().casefold(), word.strip())
    return [w for w in out.values() if w]


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
    place: dict[str, Any] | None = None  # {name, lat, lon}: the phone's one location fix at Start, as it took it
    language_bias: list[str] | None = None
    keywords: list[str] | None = None
    busy: list[list[str]] | None = None  # the owner's calendar for the week, ISO ranges, for proposing times
    links: dict[str, str] | None = None  # deck / one_pager / blurb the owner can hand over
    tz: str = ""
    now: str = ""  # the phone's clock at start, ISO 8601 with offset
    # Whose axes the FOA is in (direction.py): "screen", +X out of the screen, as the rig and rehearsal audio are; or
    # "camera", Apple's frame, +X out of the back, which is what an iPhone's own ambisonics uses. Left out, an
    # "iPhone badge" is "camera" (the app sends no field, so it needs no update) and anything else is "screen".
    # What is stored here, and in meta.json, is the frame used.
    foa_frame: str = ""
    fake_script: list[dict[str, Any]] | None = field(default=None, repr=False)  # rig ground truth, offline only

    def __post_init__(self) -> None:
        if not self.foa_frame:
            self.foa_frame = "camera" if self.device == IPHONE_BADGE else "screen"
        if self.foa_frame not in FRAME_ROTATION:
            raise ValueError(f"foa_frame must be one of {sorted(FRAME_ROTATION)}")

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
            place=parse_place(msg.get("place"), name=str(msg.get("venue", ""))),
            language_bias=msg.get("language_bias"),
            keywords=msg.get("keywords"),
            busy=msg.get("busy"),
            links=msg.get("links"),
            tz=str(msg.get("tz", "")),
            now=str(msg.get("now", "")),
            foa_frame="" if msg.get("foa_frame") is None else str(msg["foa_frame"]),
            fake_script=msg.get("fake_script"),
        )
        if hello.place and not hello.venue:  # older readers of the recording only look at venue
            hello.venue = hello.place["name"]
        if hello.layout not in LAYOUT_CHANNELS:
            raise ValueError(f"layout must be one of {sorted(LAYOUT_CHANNELS)}")
        if hello.channels != LAYOUT_CHANNELS[hello.layout]:
            raise ValueError(f"layout {hello.layout} has {LAYOUT_CHANNELS[hello.layout]} channels, not {hello.channels}")
        if not 8_000 <= hello.sample_rate <= 96_000:
            raise ValueError(f"unsupported sample rate {hello.sample_rate}")
        return hello


def default_language_bias() -> list[str] | None:
    """HALLWISE_LANGUAGE_BIAS, e.g. "en,fr,ja": the languages the transcriber is told to expect when the badge's
    hello names none (the app sends none). Unset by default. In rehearsal, en,fr,ja brought Kenji's Japanese
    aside back about half the time in a short session, but never after the rest of the evening (0 of 8 either
    way), and it cost Siddharth's name, which the transcriber hears as Hindi (1 of 4 with it, 8 of 8 without)."""
    langs = [x.strip() for x in os.environ.get("HALLWISE_LANGUAGE_BIAS", "").split(",") if x.strip()]
    return langs or None


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
        make_second: Callable[[], SecondListener | None] | None = None,
    ):
        self.id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.dir = root / "recordings" / self.id
        self.dir.mkdir(parents=True)
        self.known = people_index(root, exclude=self.id)  # everyone met at earlier recordings
        self.hello = hello
        bias = hello.language_bias or default_language_bias()
        meta = {k: v for k, v in hello.__dict__.items() if k != "fake_script"}
        meta["asr_language_bias"] = bias
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
        # Only the recogniser's copy; audio.wav is written before it. HALLWISE_LEVELER=off sends the mix as it came.
        self._leveler = Leveler(ASR_RATE) if os.environ.get("HALLWISE_LEVELER", "on") != "off" else None
        self._frames = 0
        self._pending = b""
        self.direction = DirectionTracker(hello.sample_rate, hello.layout, hello.foa_frame)
        self.speaker_positions = SpeakerPositions()
        # The owner's own voice, by where it comes from: only an iPhone's own audio (the camera frame), measured on
        # the chest. The rehearsal audio keeps naming the owner from the transcript alone.
        self.wearer = Wearer() if hello.layout == "foa" and hello.foa_frame == "camera" else None
        self._wearer_found = ""
        # Names from earlier evenings go to the transcriber as hints, so a hard surname is heard the way
        # it was spelled before, and their companies after them.
        hello.keywords = recognition_hints(hello.keywords or [], self.known)
        # The conversation's transcriber gets the server's default languages when the badge names none; a question
        # asked by voice (start_ask) keeps the badge's own, so it is not steered away from the owner's language.
        self.asr = make_asr(self._on_asr, rate=ASR_RATE, hello=replace(hello, language_bias=bias))
        self._make_asr = make_asr
        self._ask_asr: Asr | None = None  # while the owner holds to talk, audio goes here instead
        self._ask_turns: list[str] = []
        self.extractor = make_extractor(hello) if make_extractor else None
        self._history_sent: set[str] = set()
        # Open introductions and mentions from earlier evenings: a person who turns up gets a `hook` event, the
        # reason to write that the room shows under their name and the drafts use at Stop.
        try:
            self.threads: Threads | None = Threads.load(root, exclude=self.id, before=self.started, tz=hello.tz)
        except Exception:  # an unreadable old log must not stop a recording
            self.threads = None
        self._hooks_sent: set[tuple[str, str]] = set()
        if self.extractor is not None:
            self.extractor.known = [
                e["name"] + (f", {e['company']}" if e["company"] else "") for e in self.known[:60]
            ]
        # "Met before" the moment a known person says who they are, before Muse Spark runs (recall.py), and a
        # second Meta model re-hearing the transcript (second.py). Both only beside Spark, and neither can stop it.
        self.recall = (
            Recall(self.known, hello.owner_name, hello.owner_company, threads=self.threads, exclude=self.id, before=self.started)
            if self.extractor is not None else None
        )
        self.second = (make_second or SecondListener.from_env)() if self.extractor is not None else None
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
            pcm = (self._leveler.process(mono) if self._leveler else mono).astype("<i2").tobytes()
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
            turn = Turn(
                turn=data["turn"],
                speaker=f"{data.get('session', 1)}:{data.get('speaker') or '?'}",
                start_ms=data["start_ms"],
                end_ms=data["end_ms"],
                text=data["text"],
            )
            self.extractor.add_turn(turn)
            self._recall(turn)
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
        self._find_wearer(speaker, where, turn["end_ms"])

    def _find_wearer(self, speaker: str, where: dict[str, Any], t_ms: int) -> None:
        """Once one label's turns clearly come from above the badge, that label is the owner: an `owner` event with
        source "elevation", carrying it beside whatever Muse Spark already named, and every prompt from then on
        marks it as the owner, so promises come out owed by or to the right person."""
        if self.wearer is None or speaker.endswith(":?"):
            return
        self.wearer.update(speaker, where.get("elevation"), where.get("confidence_3d"))
        found = self.wearer.find()
        label = found[0] if found else ""
        if label == self._wearer_found:
            return
        self._wearer_found = label
        if self.extractor is not None:
            speakers = self.extractor.set_wearer(label)
        else:
            speakers = [label] if label else []
        extra = {"elevation": found[1]} if found else {}
        self.log.emit("owner", t_ms, speakers=speakers, source="elevation", **extra)

    def _recall(self, turn: Turn) -> None:
        """A known name in this turn rings "met before" now, provisionally, for that turn's speaker."""
        if self.recall is None or self.extractor is None:
            return
        try:
            for kind, t_ms, data in self.recall.on_turn(turn, self.extractor.state, self._history_sent, self.now_ms):
                self.log.emit(kind, t_ms, **data)
        except Exception as err:  # the fast path is a bonus; Spark still runs
            self.log.emit("extract_error", self.now_ms, message=f"recall: {err.__class__.__name__}: {err}"[:300])

    def _prompt(self, upto: int) -> Callable[[], str]:
        """The transcript Muse Spark read, for the second listener: the same prompt, the same turns."""
        ex = self.extractor
        assert ex is not None
        turns, wearer = list(ex.turns[:upto]), ex.wearer
        return lambda: build_prompt(turns, ex.owner_name, ex.owner_company, ex.vocabulary, ex.known, wearer)

    async def _extract(self) -> None:
        """Run until the latest run has seen every turn; a turn arriving mid-run triggers one more run."""
        while self.extractor is not None and self._extracted_upto < len(self.extractor.turns):
            seen = len(self.extractor.turns)
            try:
                for kind, t_ms, data in await self.extractor.run():
                    self.log.emit(kind, t_ms, **data)
                    if kind == "person" and self.threads is not None:
                        for hook in self.threads.for_person(data.get("name", ""), data.get("company", ""), data["key"]):
                            if (data["key"], hook["title"]) not in self._hooks_sent:
                                self._hooks_sent.add((data["key"], hook["title"]))
                                # the event's own type is "hook"; what kind of hook it is rides as "kind"
                                self.log.emit("hook", t_ms, **{("kind" if k == "type" else k): v for k, v in hook.items()})
                    if kind == "person" and data["key"] not in self._history_sent:
                        entry = match(self.known, data.get("name", ""), data.get("company", ""))
                        if entry is not None:
                            self._history_sent.add(data["key"])
                            history = history_event(entry, data["key"], exclude=self.id, before=self.started)
                            if history["encounters"]:
                                self.log.emit("person_history", t_ms, **history)
                seen_turn = self.extractor.turns[seen - 1].turn
                if self.recall is not None:  # confirm or withdraw what the fast path rang
                    for kind, t, data in self.recall.after_run(self.extractor.state, seen_turn, self._history_sent, self.now_ms):
                        self.log.emit(kind, t, **data)
                if self.second is not None:
                    ex = self.extractor
                    self.second.after_spark_run(self.log.emit, self._prompt(seen), lambda: ex.state, seen_turn, lambda: self.now_ms)
            except Exception as err:  # a failed run must not stop the recording
                self.log.emit("extract_error", self.now_ms, message=f"{err.__class__.__name__}: {err}"[:300])
            self._extracted_upto = seen

    async def close(self) -> None:
        if self._resampler is not None:
            tail = self._resampler.resample_chunk(np.zeros(0, dtype=np.int16), last=True)
            if len(tail):
                await self.asr.send((self._leveler.process(tail) if self._leveler else tail).astype("<i2").tobytes())
        await self.asr.finish()
        if self._extract_task is not None:
            await self._extract_task
        await self._extract()
        if self.recall is not None:  # a ring Spark never confirmed does not outlive the recording
            for kind, t_ms, data in self.recall.close(self.now_ms):
                self.log.emit(kind, t_ms, **data)
        await asyncio.gather(self._next_moves(), self._second_last())
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

    async def _second_last(self) -> None:
        """The second listener's last call, on the whole transcript, beside the drafts."""
        ex = self.extractor
        if self.second is None or ex is None or not ex.turns:
            return
        try:
            await self.second.finish(self.log.emit, self._prompt(len(ex.turns)), lambda: ex.state, ex.turns[-1].turn,
                                     lambda: self.now_ms)
        except Exception as err:
            self.log.emit("second_error", self.now_ms, message=f"{err.__class__.__name__}: {err}"[:300])

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
