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
import time
import uuid
from typing import Any, Awaitable, Callable, Protocol

import numpy as np

Sink = Callable[..., Any]  # sink(type, t_ms, **data)


class Asr(Protocol):
    async def start(self) -> None: ...
    async def send(self, pcm: bytes) -> None: ...
    async def finish(self) -> None: ...


class MetaRealtimeAsr:
    """Muse Voice Transcribe over its realtime WebSocket, on the recording's clock, across as many sessions as it takes.

    The service ends a session for its own reasons: "max session" after a long one, "Ingress below real-time"
    after the badge's Wi-Fi stalls, a dropped connection. Whatever the reason, while audio keeps coming a new
    session opens and carries on: its turn ids continue after the last one and its speaker labels are a new
    session's (labels restart every session). Audio that arrives while no session is open is kept, up to
    BUFFER_MS, and sent first when the next one opens, so a short stall loses no words. Every close that was not
    asked for and not a long session's natural end is an asr_error. Reopening backs off when sessions keep
    dying young, and stops for a while after REOPEN_LIMIT attempts in REOPEN_WINDOW_S.

    Stalls themselves: a badge whose Wi-Fi stalls delivers its backlog all at once. Live, the service took a 9 s
    backlog in one go, closed the session with "Audio backlog too large" at 12 s, and with a 12 s backlog sent
    more slowly it closed it with "Ingress below real-time" instead. So up to STALL_MS behind, the backlog goes
    out at once to the same session; further behind, the session is ended cleanly with endStream, so its turns
    complete, and the backlog goes to a fresh session, which is never behind, FRESH_BURST_MS at a time (a fresh
    session given 8 s at once closed with "Audio backlog too large"), then DRAIN_RATE times real time.
    """

    URI = "wss://api.meta.ai/v1/asr/realtime"
    ENCODINGS = {16_000: "PCM_16KHZ", 24_000: "PCM_24KHZ"}
    BACKOFF_S = (0.0, 1.0, 2.0, 4.0, 8.0, 15.0)  # wait before reopening, by how many sessions in a row died young
    YOUNG_S = 30.0  # a session that ends sooner than this counts as dying young
    REOPEN_LIMIT = 6
    REOPEN_WINDOW_S = 60.0
    BUFFER_MS = 30_000  # audio kept while no session is open; older audio is dropped
    BURST_MS = 9_000  # at most this much ahead of what the service has presumably worked through
    FRESH_BURST_MS = 4_000  # the same for a new session until it has caught up; live, 8 s killed a fresh one
    FRESH_S = 5.0  # a new session counts as new for at least this long, while a backlog may still be arriving
    DRAIN_RATE = 2.0  # seconds of queued audio it works through per second, conservatively
    STALL_MS = 8_000  # this far behind real time, roll over to a fresh session
    ROLLOVER_WAIT_S = 5.0  # for the old session to complete its turns after endStream

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
        connect: Callable[[], Awaitable[Any]] | None = None,
        clock: Callable[[], float] = time.monotonic,
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
        self._connect_ws = connect or self._connect  # tests pass a fake service
        self._clock = clock
        self._ws: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._reopening: asyncio.Task[None] | None = None
        self._reopen = False  # the last session ended; open another when audio comes
        self._rolling = False  # ending a session that fell behind, on purpose
        self._finishing = False
        self._received_ms = 0.0  # all audio handed to send(), across sessions: the recording clock
        self._buffer: list[bytes] = []  # audio waiting for the next session
        self._buffered_ms = 0.0
        self._queued_ms = 0.0  # audio the service has presumably not worked through yet
        self._queued_at = 0.0
        self._caught_up = False  # the current session has been open FRESH_S and has nothing waiting
        self._offset_ms = 0  # recording time at which the current session's audio starts
        self._opened_at = 0.0
        self._young = 0  # sessions in a row that died young
        self._attempts: list[float] = []  # clock times of recent reopen attempts
        self._next_attempt = 0.0
        self._paused_reported = False
        self._session = 0
        self._turn_base = 0  # turn ids restart at 0 in every session; ours carry on after the last one
        self._max_turn = -1
        self._current: int | None = None
        self._turns: dict[int, dict[str, Any]] = {}

    @property
    def sessions(self) -> int:
        return self._session

    async def start(self) -> None:
        await self._open()

    async def _connect(self) -> Any:
        import websockets

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
        return ws

    async def _open(self) -> None:
        """Open a session, then send it whatever audio arrived while there was none."""
        ws = await self._connect_ws()
        self._session += 1
        self._turn_base = self._max_turn + 1
        self._current = None
        self._offset_ms = int(round(self._received_ms - self._buffered_ms))
        self._opened_at = self._clock()
        self._queued_ms, self._queued_at = 0.0, self._opened_at
        self._caught_up = False
        self._ws = ws
        self._reopen = False
        self._rolling = False
        self._paused_reported = False
        self._receiver = asyncio.create_task(self._receive(ws))
        await self._drain()

    async def _reopen_session(self) -> None:
        if self._receiver is not None:
            await self._receiver  # the old session's last events are mapped with its own offsets first
        self._attempts.append(self._clock())
        try:
            await self._open()
        except Exception as err:  # the service or the network is down; try again later
            self._young += 1
            self._next_attempt = self._clock() + self.BACKOFF_S[min(self._young, len(self.BACKOFF_S) - 1)]
            self.sink("asr_error", int(self._received_ms), message=f"transcription reopen failed: {err}"[:300])

    async def _roll_over(self) -> None:
        """End a session that fell too far behind real time, cleanly, then open a fresh one for the backlog."""
        from websockets.exceptions import ConnectionClosed

        ws, receiver = self._ws, self._receiver
        try:
            await ws.send(json.dumps({"type": "endStream"}))
        except ConnectionClosed:
            pass
        if receiver is not None:
            try:
                await asyncio.wait_for(asyncio.shield(receiver), self.ROLLOVER_WAIT_S)
            except asyncio.TimeoutError:
                await ws.close()
                await receiver
        await self._reopen_session()

    def _recent_attempts(self) -> int:
        now = self._clock()
        self._attempts = [t for t in self._attempts if now - t < self.REOPEN_WINDOW_S]
        return len(self._attempts)

    def _may_reopen(self) -> bool:
        if self._recent_attempts() >= self.REOPEN_LIMIT:
            if not self._paused_reported:
                self._paused_reported = True
                self.sink(
                    "asr_error",
                    int(self._received_ms),
                    message=f"transcription paused: {len(self._attempts)} reopens in the last "
                    f"{int(self.REOPEN_WINDOW_S)} s; trying again shortly",
                )
            return False
        return self._clock() >= self._next_attempt

    def _keep(self, pcm: bytes, live: bool = False) -> None:
        """Hold audio to send. Without a live session, the oldest beyond BUFFER_MS is dropped; the next session's
        clock starts after it. A live session's audio is never dropped: its clock is the audio it was sent."""
        self._buffer.append(pcm)
        self._buffered_ms += self._ms(pcm)
        while not live and self._buffered_ms > self.BUFFER_MS and len(self._buffer) > 1:
            self._buffered_ms -= self._ms(self._buffer.pop(0))

    def _ms(self, pcm: bytes) -> float:
        return len(pcm) / 2 / self.rate * 1000

    async def _drain(self, wait: bool = False) -> bool:
        """Send the kept audio, oldest first, in bursts of at most BURST_MS; what is left waits for the next call
        (or, with `wait`, for the service to catch up). What the session refuses stays kept, in order. False when
        the session turned out to be closed."""
        from websockets.exceptions import ConnectionClosed

        while self._buffer:
            pcm = self._buffer[0]
            now = self._clock()
            self._queued_ms = max(0.0, self._queued_ms - (now - self._queued_at) * 1000 * self.DRAIN_RATE)
            self._queued_at = now
            over = self._queued_ms + self._ms(pcm) - (self.BURST_MS if self._caught_up else self.FRESH_BURST_MS)
            if self._queued_ms > 0 and over > 0:
                if not wait:
                    return True
                pause = over / 1000 / self.DRAIN_RATE
                await asyncio.sleep(pause)
                self._queued_ms = max(0.0, self._queued_ms - pause * 1000 * self.DRAIN_RATE)
                self._queued_at = self._clock()
                continue
            try:
                await self._ws.send(pcm)
            except ConnectionClosed:
                return False
            self._queued_ms += self._ms(pcm)
            if self._buffer and self._buffer[0] is pcm:
                self._buffer.pop(0)
                self._buffered_ms -= self._ms(pcm)
        self._buffered_ms = 0.0
        if self._clock() - self._opened_at >= self.FRESH_S:
            self._caught_up = True
        return True

    async def send(self, pcm: bytes) -> None:
        self._received_ms += self._ms(pcm)
        if self._finishing:
            return
        if self._reopening is not None and self._reopening.done():
            self._reopening = None
        if self._reopening is not None or self._reopen or self._ws is None:
            self._keep(pcm)
            if self._reopening is None and self._reopen and self._may_reopen():
                self._reopening = asyncio.create_task(self._reopen_session())
            return
        behind = (self._clock() - self._opened_at) * 1000 - (self._received_ms - self._ms(pcm) - self._offset_ms)
        if behind > self.STALL_MS:
            # The badge went quiet for longer than the service waits. End this session cleanly and give what
            # comes now to a fresh one.
            self._keep(pcm)
            self._rolling = self._reopen = True
            self._reopening = asyncio.create_task(self._roll_over())
            return
        self._keep(pcm, live=True)  # behind anything still waiting to go out
        await self._drain()

    async def finish(self) -> None:
        from websockets.exceptions import ConnectionClosed

        self._finishing = True
        if self._reopening is not None:
            await self._reopening
            self._reopening = None
        for _ in range(2):  # the session may turn out to have closed with the last words still kept
            if self._reopen and self._buffer and self._recent_attempts() < self.REOPEN_LIMIT:
                await self._reopen_session()  # the last words of the evening still go out
            if self._ws is None:
                return
            if not self._reopen and await self._drain(wait=True):
                try:
                    await self._ws.send(json.dumps({"type": "endStream"}))
                except ConnectionClosed:
                    pass
            if self._receiver is not None:
                await self._receiver
            if not (self._reopen and self._buffer):
                break
        self._ws = None

    async def _receive(self, ws: Any) -> None:
        from websockets.exceptions import ConnectionClosed

        try:
            async for message in ws:
                if isinstance(message, str):
                    try:
                        self.handle(json.loads(message))
                    except Exception as err:  # one malformed event must not end the evening's transcript
                        self.sink("asr_error", int(self._received_ms), message=f"unreadable transcription event: {err}"[:300])
        except ConnectionClosed:
            pass
        self._flush_open_turns()
        code, reason = getattr(ws, "close_code", None), getattr(ws, "close_reason", None) or ""
        if (self._finishing or self._rolling) and code in (1000, None):
            return  # we asked for this end
        lived = self._clock() - self._opened_at
        self._young = 0 if lived >= self.YOUNG_S else self._young + 1
        self._next_attempt = self._clock() + self.BACKOFF_S[min(self._young, len(self.BACKOFF_S) - 1)]
        self._reopen = True
        if not (code == 1011 and "max session" in reason.lower()):
            # Not a long session's natural end: say so, then carry on in a new session when audio comes.
            self.sink("asr_error", int(self._received_ms), message=f"transcription closed {code}: {reason}; reopening")

    def _flush_open_turns(self) -> None:
        """A session that ends mid-turn never completes it: keep what was heard so far as the turn's text."""
        for turn, info in sorted(self._turns.items()):
            text = info.get("partial", "")
            if text:
                end = info.get("end_ms", info.get("last_ms", info["start_ms"]))
                self.sink(
                    "turn",
                    end,
                    turn=turn,
                    text=text,
                    speaker=info.get("speaker"),
                    session=self._session,
                    start_ms=info["start_ms"],
                    end_ms=end,
                    cut_short=True,
                )
        self._turns.clear()
        self._current = None

    def handle(self, event: dict[str, Any]) -> None:
        """Map one Muse Voice Transcribe server event onto Hallwise events."""
        kind = event.get("type")
        if "audioProcessedMs" in event:
            t = self._offset_ms + int(event["audioProcessedMs"])
        else:
            t = int(self._received_ms)  # e.g. a warning: it is about now
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
            text = event.get("transcript", "").strip()
            if turn is not None:
                info = self._turns.setdefault(turn, {"start_ms": t, "speaker": None})
                info["partial"], info["last_ms"] = text, t
            self.sink("partial", t, turn=turn, text=text)
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
                text=event.get("transcript", "").strip(),
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
    """Pick a backend by name: "meta" (needs MODEL_API_KEY) or "fake".

    A recording whose hello carries a `fake_script` (the rig's ground truth) always gets the scripted
    recogniser, whatever the server default: the rig knows what was said, and synthetic audio is not speech.
    """
    if kind == "meta":
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise RuntimeError("HALLWISE_ASR=meta needs MODEL_API_KEY in the environment")

        def meta(sink: Sink, *, rate: int, hello: Any) -> Asr:
            if hello.fake_script is not None:
                return FakeAsr(sink, rate=rate, script=hello.fake_script)
            return MetaRealtimeAsr(key, sink, rate=rate, language_bias=hello.language_bias, keywords=hello.keywords)

        return meta
    if kind == "fake":

        def fake(sink: Sink, *, rate: int, hello: Any) -> Asr:
            return FakeAsr(sink, rate=rate, script=hello.fake_script)

        return fake
    raise ValueError(f"unknown ASR backend {kind!r}; use 'meta' or 'fake'")
