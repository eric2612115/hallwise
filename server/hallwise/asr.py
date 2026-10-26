"""Speech recognition backends.

Both turn a stream of 16-bit little-endian mono PCM into events on the recording clock:

    speech_start  {turn}                                   a turn began
    partial       {turn, text}                             provisional text while the turn is open
    speaker       {turn, label, session}                   diarization label; labels restart every session
    turn          {turn, text, speaker, session, start_ms, end_ms}   final text of a turn
    asr_error     {message}

`MetaRealtimeAsr` talks to Muse Voice Transcribe over its realtime WebSocket. `FakeAsr` works offline: it replays a
script (the rig's ground truth) as the audio clock reaches each turn, or, with no script, marks speech by energy.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, Callable, Protocol

import numpy as np

Sink = Callable[..., Any]  # sink(type, t_ms, **data)


class Asr(Protocol):
    async def start(self) -> None: ...
    async def send(self, pcm: bytes) -> None: ...
    async def finish(self) -> None: ...


class MetaRealtimeAsr:
    URI = "wss://api.meta.ai/v1/asr/realtime"
    ENCODINGS = {16_000: "PCM_16KHZ", 24_000: "PCM_24KHZ"}

    def __init__(
        self,
        api_key: str,
        sink: Sink,
        *,
        rate: int = 24_000,
        mode: str = "DIARIZATION",
        language_bias: list[str] | None = None,
        keywords: list[str] | None = None,
        model: str = "muse-voice-transcribe-1.0",
    ):
        if rate not in self.ENCODINGS:
            raise ValueError(f"Muse Voice Transcribe takes 16 or 24 kHz audio, not {rate} Hz")
        self.api_key = api_key
        self.sink = sink
        self.rate = rate
        self.mode = mode
        self.language_bias = language_bias
        self.keywords = keywords
        self.model = model
        self._ws: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._expired = False
        self._sent_ms = 0.0  # audio sent so far, across sessions
        self._offset_ms = 0  # recording time at which the current session started
        self._session = 0
        self._turn_base = 0  # turn ids restart in every session
        self._max_turn = 0
        self._current: int | None = None
        self._turns: dict[int, dict[str, Any]] = {}

    async def start(self) -> None:
        await self._open()

    async def _open(self) -> None:
        import websockets

        self._session += 1
        self._offset_ms = int(self._sent_ms)
        self._turn_base = self._max_turn
        ws = await websockets.connect(
            f"{self.URI}?sessionId=hallwise-{uuid.uuid4()}", open_timeout=30, max_size=None
        )
        handshake: dict[str, Any] = {
            "authorization": {"accessToken": f"Bearer {self.api_key}"},
            "audioEncoding": self.ENCODINGS[self.rate],
            "model": self.model,
            "mode": self.mode,
        }
        if self.language_bias:
            handshake["languageBias"] = self.language_bias
        if self.keywords:
            handshake["keywords"] = self.keywords
        await ws.send(json.dumps(handshake))
        ack = json.loads(await ws.recv())
        if "sessionId" not in ack:
            await ws.close()
            raise RuntimeError(f"Muse Voice Transcribe handshake failed: {ack}")
        self._ws = ws
        self._receiver = asyncio.create_task(self._receive(ws))

    async def send(self, pcm: bytes) -> None:
        if self._expired:
            # The service ends long sessions; carry on in a new one on the same recording clock.
            self._expired = False
            if self._receiver is not None:
                await self._receiver
            await self._open()
        if self._ws is None:
            return
        from websockets.exceptions import ConnectionClosed

        try:
            await self._ws.send(pcm)
        except ConnectionClosed:
            return
        self._sent_ms += len(pcm) / 2 / self.rate * 1000

    async def finish(self) -> None:
        if self._ws is None:
            return
        from websockets.exceptions import ConnectionClosed

        try:
            await self._ws.send(json.dumps({"type": "endStream"}))
        except ConnectionClosed:
            pass
        if self._receiver is not None:
            await self._receiver
        self._ws = None

    async def _receive(self, ws: Any) -> None:
        from websockets.exceptions import ConnectionClosed

        try:
            async for message in ws:
                if isinstance(message, str):
                    self.handle(json.loads(message))
        except ConnectionClosed:
            pass
        code, reason = ws.close_code, ws.close_reason or ""
        if code == 1011 and "max session" in reason.lower():
            self._expired = True
        elif code not in (1000, None):
            self.sink("asr_error", int(self._sent_ms), message=f"transcription closed {code}: {reason}")

    def handle(self, event: dict[str, Any]) -> None:
        """Map one Muse Voice Transcribe server event onto Hallwise events."""
        kind = event.get("type")
        t = self._offset_ms + int(event.get("audioProcessedMs", 0))
        if "turnId" in event:
            turn = self._turn_base + int(event["turnId"])
            self._max_turn = max(self._max_turn, turn)
        else:
            turn = self._current
        if kind == "speechStart":
            self._current = turn
            self._turns[turn] = {"start_ms": t, "speaker": None}
            self.sink("speech_start", t, turn=turn)
        elif kind == "transcript":
            self.sink("partial", t, turn=turn, text=event.get("transcript", ""))
        elif kind == "speaker":
            label = event.get("label")
            if turn is not None:
                self._turns.setdefault(turn, {"start_ms": t, "speaker": None})["speaker"] = label
            self.sink("speaker", t, turn=turn, label=label, session=self._session)
        elif kind == "speechEnd":
            self._turns.setdefault(turn, {"start_ms": t, "speaker": None})["end_ms"] = t
        elif kind == "speechComplete":
            info = self._turns.pop(turn, {})
            self.sink(
                "turn",
                t,
                turn=turn,
                text=event.get("transcript", ""),
                speaker=info.get("speaker"),
                session=self._session,
                start_ms=info.get("start_ms", t),
                end_ms=info.get("end_ms", t),
            )
        elif kind == "error":
            self.sink("asr_error", t, message=event.get("message", ""))


class FakeAsr:
    """Offline stand-in for Muse Voice Transcribe."""

    FRAME_MS = 20

    def __init__(
        self,
        sink: Sink,
        *,
        rate: int = 24_000,
        script: list[dict[str, Any]] | None = None,
        threshold_db: float = -40.0,
        start_after_ms: int = 100,
        end_after_ms: int = 500,
        min_turn_ms: int = 300,
    ):
        self.sink = sink
        self.rate = rate
        self.script = sorted(script, key=lambda t: t["end_ms"]) if script is not None else None
        self.threshold = 32768 * 10 ** (threshold_db / 20)
        self.start_after_ms = start_after_ms
        self.end_after_ms = end_after_ms
        self.min_turn_ms = min_turn_ms
        self._ms = 0.0
        self._buffer = np.zeros(0, dtype=np.int16)
        self._next = 0
        self._turns = 0
        self._loud_ms = 0
        self._quiet_ms = 0
        self._start_ms: float | None = None

    async def start(self) -> None:
        pass

    async def send(self, pcm: bytes) -> None:
        samples = np.frombuffer(pcm, dtype="<i2")
        if self.script is not None:
            self._ms += len(samples) / self.rate * 1000
            self._replay(until_ms=self._ms)
            return
        self._buffer = np.concatenate([self._buffer, samples])
        frame = self.rate * self.FRAME_MS // 1000
        while len(self._buffer) >= frame:
            chunk, self._buffer = self._buffer[:frame], self._buffer[frame:]
            self._step(float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2))))

    async def finish(self) -> None:
        if self.script is not None:
            self._replay(until_ms=float("inf"))
        elif self._start_ms is not None:
            self._close_turn(self._ms)

    def _replay(self, until_ms: float) -> None:
        while self._next < len(self.script) and self.script[self._next]["end_ms"] <= until_ms:
            t = self.script[self._next]
            self._next += 1
            self._turns += 1
            self.sink("speech_start", t["start_ms"], turn=self._turns)
            self.sink("speaker", t["start_ms"], turn=self._turns, label=t.get("speaker", "A"), session=1)
            self.sink(
                "turn",
                t["end_ms"],
                turn=self._turns,
                text=t.get("text", ""),
                speaker=t.get("speaker", "A"),
                session=1,
                start_ms=t["start_ms"],
                end_ms=t["end_ms"],
            )

    def _step(self, rms: float) -> None:
        self._ms += self.FRAME_MS
        if rms >= self.threshold:
            self._loud_ms += self.FRAME_MS
            self._quiet_ms = 0
            if self._start_ms is None and self._loud_ms >= self.start_after_ms:
                self._start_ms = self._ms - self._loud_ms
                self._turns += 1
                self.sink("speech_start", int(self._start_ms), turn=self._turns)
                self.sink("speaker", int(self._start_ms), turn=self._turns, label="A", session=1)
        else:
            self._loud_ms = 0
            if self._start_ms is not None:
                self._quiet_ms += self.FRAME_MS
                if self._quiet_ms >= self.end_after_ms:
                    self._close_turn(self._ms - self._quiet_ms)

    def _close_turn(self, end_ms: float) -> None:
        start = self._start_ms
        self._start_ms = None
        self._quiet_ms = 0
        if start is None or end_ms - start < self.min_turn_ms:
            return
        self.sink(
            "turn",
            int(end_ms),
            turn=self._turns,
            text=f"[speech {start / 1000:.1f}–{end_ms / 1000:.1f} s]",
            speaker="A",
            session=1,
            start_ms=int(start),
            end_ms=int(end_ms),
        )


def make_asr_factory(kind: str) -> Callable[..., Asr]:
    """Pick a backend by name: "meta" (needs MODEL_API_KEY) or "fake"."""
    if kind == "meta":
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise RuntimeError("HALLWISE_ASR=meta needs MODEL_API_KEY in the environment")

        def meta(sink: Sink, *, rate: int, hello: Any) -> Asr:
            return MetaRealtimeAsr(key, sink, rate=rate, language_bias=hello.language_bias, keywords=hello.keywords)

        return meta
    if kind == "fake":

        def fake(sink: Sink, *, rate: int, hello: Any) -> Asr:
            return FakeAsr(sink, rate=rate, script=hello.fake_script)

        return fake
    raise ValueError(f"unknown ASR backend {kind!r}; use 'meta' or 'fake'")
