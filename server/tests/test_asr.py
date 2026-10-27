"""MetaRealtimeAsr against a fake Muse Voice Transcribe: sessions that the service closes, for any reason, while
the badge keeps sending audio."""

import asyncio
import json

import numpy as np
import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from hallwise.asr import MetaRealtimeAsr
from hallwise.events import read_events
from hallwise.recording import ASR_RATE, Hello, Recording

RATE = ASR_RATE
CHUNK_MS = 80
CHUNK = b"\x00\x00" * (RATE * CHUNK_MS // 1000)


class FakeSession:
    """One realtime session. `script` maps "audio received so far, in ms" to what the service does then: a list of
    events (dicts, or ("close", code, reason)). On endStream it closes normally."""

    def __init__(self, script: list[tuple[int, list]] | None = None):
        self.script = sorted(script or [], key=lambda s: s[0])
        self.received_ms = 0
        self.messages: asyncio.Queue = asyncio.Queue()
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self.ended = False

    def _close(self, code: int, reason: str) -> None:
        self.close_code, self.close_reason = code, reason
        self.messages.put_nowait(None)

    async def send(self, data) -> None:
        if self.close_code is not None:
            raise ConnectionClosedError(Close(self.close_code, self.close_reason), None)
        if isinstance(data, str):
            assert json.loads(data) == {"type": "endStream"}
            self.ended = True
            self._close(1000, "")
            return
        self.received_ms += len(data) // 2 * 1000 // RATE
        while self.script and self.script[0][0] <= self.received_ms:
            _, actions = self.script.pop(0)
            for action in actions:
                if isinstance(action, tuple):
                    self._close(action[1], action[2])
                    return
                self.messages.put_nowait(json.dumps(action))

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.messages.get()
        if message is None:
            raise StopAsyncIteration
        return message


class FakeService:
    def __init__(self, sessions: list[FakeSession | Exception]):
        self.sessions = list(sessions)
        self.opened: list[FakeSession] = []
        self.connects = 0

    async def connect(self) -> FakeSession:
        self.connects += 1
        session = self.sessions.pop(0) if self.sessions else FakeSession()
        if isinstance(session, Exception):
            raise session
        self.opened.append(session)
        return session


def turn_events(turn_id: int, start: int, end: int, text: str, label: str = "A") -> list[dict]:
    return [
        {"type": "speechStart", "turnId": turn_id, "audioProcessedMs": start},
        {"type": "speaker", "turnId": turn_id, "label": label, "audioProcessedMs": start + 50},
        {"type": "transcript", "turnId": turn_id, "transcript": text, "audioProcessedMs": end - 50},
        {"type": "speechEnd", "turnId": turn_id, "audioProcessedMs": end},
        {"type": "speechComplete", "turnId": turn_id, "transcript": text, "audioProcessedMs": end + 20},
    ]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


async def stream(asr: MetaRealtimeAsr, seconds: float, clock: Clock | None = None) -> None:
    """Send audio at real time on a fake clock, letting the receiver and any reopen run between chunks."""
    for _ in range(int(seconds * 1000 / CHUNK_MS)):
        await asr.send(CHUNK)
        if clock is not None:
            clock.t += CHUNK_MS / 1000
        for _ in range(5):
            await asyncio.sleep(0)


def test_a_stall_close_mid_recording_reopens_and_the_transcript_carries_on(tmp_path):
    # The service closes the first session with 1008 "Ingress below real-time" at 1.52 s of audio, in the middle of
    # a turn. The badge keeps sending; a second session takes over on the same clock.
    first = FakeSession([
        (960, turn_events(0, 100, 900, "Hello, I'm Kenji.")),
        (1520, [
            {"type": "speechStart", "turnId": 1, "audioProcessedMs": 1200},
            {"type": "speaker", "turnId": 1, "label": "B", "audioProcessedMs": 1250},
            {"type": "transcript", "turnId": 1, "transcript": "Hoshizora Robo", "audioProcessedMs": 1450},
            ("close", 1008, "Ingress below real-time"),
        ]),
    ])
    second = FakeSession([(1000, turn_events(0, 200, 800, "We keep running into each other.", label="A"))])
    service = FakeService([first, second])
    hello = Hello(sample_rate=RATE, channels=1, layout="mono")
    rec = Recording(tmp_path, hello, lambda sink, *, rate, hello: MetaRealtimeAsr("key", sink, rate=rate, connect=service.connect))

    async def run():
        await rec.start()
        for _ in range(38):  # 3.04 s
            await rec.on_audio(CHUNK)
            for _ in range(5):
                await asyncio.sleep(0)
        await rec.close()

    asyncio.run(run())
    events = read_events(rec.dir / "events.jsonl")
    turns = [e for e in events if e["type"] == "turn"]
    assert [(t["turn"], t["session"], t["speaker"], t["text"]) for t in turns] == [
        (0, 1, "A", "Hello, I'm Kenji."),
        (1, 1, "B", "Hoshizora Robo"),  # the turn the close cut off, kept as far as it was heard
        (2, 2, "A", "We keep running into each other."),  # ids carry on; labels are the new session's
    ]
    assert turns[1]["cut_short"] is True
    assert (turns[0]["start_ms"], turns[0]["end_ms"]) == (100, 900)
    # The second session's audio starts where the first one's ended, at 1.52 s of the recording.
    assert (turns[2]["start_ms"], turns[2]["end_ms"]) == (1720, 2320)
    (error,) = [e for e in events if e["type"] == "asr_error"]
    assert "1008" in error["message"] and "Ingress below real-time" in error["message"]
    assert 1520 <= error["t_ms"] <= 1700
    # Nothing lost or doubled between the two sessions, and the second one was ended properly.
    assert first.received_ms + second.received_ms == 3040
    assert second.ended and service.connects == 2


def test_audio_sent_into_a_closed_session_goes_to_the_next_one_in_order():
    first = FakeSession([(400, [("close", 1006, "")])])
    second = FakeSession()
    service = FakeService([first, second])
    sink_events = []
    asr = MetaRealtimeAsr("key", lambda *a, **k: sink_events.append((a, k)), connect=service.connect)
    received: list[bytes] = []
    original = second.send

    async def record(data):
        if isinstance(data, bytes):
            received.append(data)
        await original(data)

    second.send = record

    async def run():
        await asr.start()
        for i in range(10):
            await asr.send(bytes([i]) * len(CHUNK))  # no yielding: the close is noticed late
        for _ in range(10):
            await asyncio.sleep(0)
        await asr.send(bytes([10]) * len(CHUNK))
        for _ in range(10):
            await asyncio.sleep(0)
        await asr.finish()

    asyncio.run(run())
    assert first.received_ms == 400  # five chunks, then the service closed
    assert [r[0] for r in received] == list(range(5, 11))
    assert asr._offset_ms == 400


def test_max_session_reopens_quietly():
    first = FakeSession([(800, turn_events(0, 100, 600, "One.")), (960, [("close", 1011, "Max session duration reached")])])
    second = FakeSession([(400, turn_events(0, 100, 300, "Two."))])
    service = FakeService([first, second])
    events = []
    asr = MetaRealtimeAsr("key", lambda type, t, **d: events.append((type, t, d)), connect=service.connect)

    async def run():
        await asr.start()
        await stream(asr, 2.0)
        await asr.finish()

    asyncio.run(run())
    assert not [e for e in events if e[0] == "asr_error"]
    assert [(d["turn"], d["session"], d["text"], d["start_ms"]) for ty, _, d in events if ty == "turn"] == [
        (0, 1, "One.", 100),
        (1, 2, "Two.", 1060),
    ]


def test_sessions_that_keep_dying_back_off_and_stop_after_the_limit_per_minute():
    clock = Clock()

    class Dying(FakeService):
        async def connect(self):
            self.connects += 1
            self.times = getattr(self, "times", []) + [clock.t]
            session = FakeSession([(80, [("close", 1011, "internal error")])])
            self.opened.append(session)
            return session

    service = Dying([])
    events = []
    asr = MetaRealtimeAsr("key", lambda type, t, **d: events.append((type, t, d)), connect=service.connect, clock=clock)

    async def run():
        await asr.start()
        await stream(asr, 120.0, clock)
        await asr.finish()

    asyncio.run(run())
    times = service.times
    reopens = times[1:]
    # Each session dies on its first chunk; each young death waits longer before the next try: 1, 2, 4, 8, 15 s.
    assert list(np.diff(times)[:5]) == pytest.approx([1, 2, 4, 8, 15], abs=0.25)
    for i, t in enumerate(reopens):
        assert sum(1 for u in reopens if t - 60 < u <= t) <= MetaRealtimeAsr.REOPEN_LIMIT
    errors = [d["message"] for ty, _, d in events if ty == "asr_error"]
    assert sum("closed 1011" in m for m in errors) == len(times)
    assert any(m.startswith("transcription paused") for m in errors)
    assert len(times) >= MetaRealtimeAsr.REOPEN_LIMIT + 2  # it pauses, then tries again once the minute has passed


def test_a_failed_reopen_is_reported_and_retried():
    clock = Clock()
    first = FakeSession([(400, [("close", 1006, "")])])
    third = FakeSession([(400, turn_events(0, 100, 300, "Back."))])
    service = FakeService([first, OSError("network unreachable"), third])
    events = []
    asr = MetaRealtimeAsr("key", lambda type, t, **d: events.append((type, t, d)), connect=service.connect, clock=clock)

    async def run():
        await asr.start()
        await stream(asr, 5.0, clock)
        await asr.finish()

    asyncio.run(run())
    errors = [d["message"] for ty, _, d in events if ty == "asr_error"]
    assert errors[0].startswith("transcription closed 1006")
    assert errors[1] == "transcription reopen failed: network unreachable"
    assert service.connects == 3
    assert [d["text"] for ty, _, d in events if ty == "turn"] == ["Back."]
    assert third.ended


def test_finishing_right_after_a_close_still_sends_the_last_words():
    first = FakeSession([(400, [("close", 1008, "Ingress below real-time")])])
    second = FakeSession([(200, turn_events(0, 0, 150, "Bye."))])
    service = FakeService([first, second])
    events = []
    asr = MetaRealtimeAsr("key", lambda type, t, **d: events.append((type, t, d)), connect=service.connect)

    async def run():
        await asr.start()
        for _ in range(8):  # 640 ms, never yielding: the close is noticed only at finish
            await asr.send(CHUNK)
        await asr.finish()

    asyncio.run(run())
    assert service.connects == 2 and second.ended
    assert second.received_ms == 240
    assert [(d["text"], d["start_ms"]) for ty, _, d in events if ty == "turn"] == [("Bye.", 400)]


def test_the_normal_end_of_a_recording_is_not_an_error():
    session = FakeSession([(400, turn_events(0, 100, 300, "Hi."))])
    service = FakeService([session])
    events = []
    asr = MetaRealtimeAsr("key", lambda type, t, **d: events.append((type, t, d)), connect=service.connect)

    async def run():
        await asr.start()
        await stream(asr, 1.0)
        await asr.finish()

    asyncio.run(run())
    assert service.connects == 1 and session.ended
    assert not [e for e in events if e[0] == "asr_error"]


class StallScenario:
    """A badge on Wi-Fi: real time, then nothing for `stall_s` while the clock runs, then the backlog all at once,
    then real time again. Every chunk is tagged, and each session records when (on the fake clock) it got what."""

    def __init__(self, stall_s: float, before_s: float = 5.0, after_s: float = 10.0):
        self.clock = Clock()
        self.arrivals: list[tuple[int, float, int, int]] = []  # (session, clock, ms, tag)
        self.stall_s, self.before_s, self.after_s = stall_s, before_s, after_s
        scenario = self

        class Session(FakeSession):
            async def send(self, data):
                if isinstance(data, bytes) and self.close_code is None:
                    scenario.arrivals.append((scenario.service.opened.index(self), scenario.clock.t,
                                              len(data) // 2 * 1000 // RATE, data[0] + 256 * data[1]))
                await super().send(data)

        self.service = FakeService([Session(), Session(), Session()])
        self.events: list = []
        self.asr = MetaRealtimeAsr("key", lambda type, t, **d: self.events.append((type, t, d)),
                                   connect=self.service.connect, clock=self.clock)
        self.sent = 0

    def chunk(self) -> bytes:
        t, self.sent = self.sent, self.sent + 1
        return bytes([t % 256, t // 256]) * (len(CHUNK) // 2)

    async def run(self) -> None:
        await self.asr.start()
        for _ in range(int(self.before_s * 1000 / CHUNK_MS)):
            await self.asr.send(self.chunk())
            self.clock.t += CHUNK_MS / 1000
            await asyncio.sleep(0)
        self.clock.t += self.stall_s  # nothing arrives
        for _ in range(int(self.stall_s * 1000 / CHUNK_MS)):  # then all of it at once
            await self.asr.send(self.chunk())
            await asyncio.sleep(0)
        for _ in range(int(self.after_s * 1000 / CHUNK_MS)):
            await self.asr.send(self.chunk())
            self.clock.t += CHUNK_MS / 1000
            for _ in range(3):
                await asyncio.sleep(0)
        await self.asr.finish()

    def worst_burst(self, session: int) -> float:
        queued, last, worst = 0.0, 0.0, 0.0
        for s, t, ms, _ in self.arrivals:
            if s != session:
                continue
            queued = max(0.0, queued - (t - last) * 1000 * MetaRealtimeAsr.DRAIN_RATE) + ms
            last, worst = t, max(worst, queued)
        return worst


def test_a_short_stall_sends_the_backlog_at_once_to_the_same_session():
    # Live, a 9 s backlog in one go was fine; up to STALL_MS the session carries on.
    sc = StallScenario(stall_s=7.0)
    asyncio.run(sc.run())
    assert [a[3] for a in sc.arrivals] == list(range(sc.sent))  # everything, in order
    assert {a[0] for a in sc.arrivals} == {0} and sc.service.connects == 1
    assert sc.worst_burst(0) == pytest.approx(7000 + CHUNK_MS, abs=CHUNK_MS)
    assert not [e for e in sc.events if e[0] == "asr_error"]


def test_a_long_stall_ends_the_session_cleanly_and_a_fresh_one_takes_the_backlog_in_bursts():
    # Live, a 12 s stall ended the session either way ("Audio backlog too large" when sent at once, "Ingress below
    # real-time" when sent slowly). Past STALL_MS the session is ended with endStream, so its turns complete, and a
    # fresh session, never behind, gets the backlog at most FRESH_BURST_MS ahead of what it has worked through.
    sc = StallScenario(stall_s=12.0)
    first_turn = turn_events(0, 1000, 3000, "Before the stall.")
    sc.service.sessions[0].script = [(3200, first_turn)]
    sc.service.sessions[1].script = [(2000, turn_events(0, 500, 1500, "From the backlog."))]
    asyncio.run(sc.run())
    first, second = sc.service.opened[:2]
    assert sc.service.connects == 2 and first.ended and second.ended
    assert [a[3] for a in sc.arrivals] == list(range(sc.sent))  # nothing lost or doubled, in order
    before_ms = int(5000 / CHUNK_MS) * CHUNK_MS
    assert first.received_ms == before_ms  # the stall's backlog went to the fresh session
    assert sc.worst_burst(1) <= MetaRealtimeAsr.FRESH_BURST_MS + CHUNK_MS
    assert sc.worst_burst(1) >= MetaRealtimeAsr.FRESH_BURST_MS - CHUNK_MS
    turns = [(d["turn"], d["session"], d["text"], d["start_ms"]) for ty, _, d in sc.events if ty == "turn"]
    assert turns == [(0, 1, "Before the stall.", 1000), (1, 2, "From the backlog.", before_ms + 500)]
    assert not [e for e in sc.events if e[0] == "asr_error"]  # a planned hand-over, not an error
