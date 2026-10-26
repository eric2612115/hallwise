import asyncio
import json
import time
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hallwise.app import create_app
from hallwise.asr import FakeAsr, MetaRealtimeAsr
from hallwise.events import EventLog, read_events
from hallwise.recording import Hello, Recording, to_mono


def tone(seconds: float, rate: int, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * 32767 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)


def silence(seconds: float, rate: int) -> np.ndarray:
    return np.zeros(int(seconds * rate), dtype=np.int16)


def test_event_log_keeps_order_and_replays_to_late_watchers(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    log.emit("a", 0)
    backlog, queue = log.watch()
    log.emit("b", 10, x=1)
    log.close()
    assert [json.loads(line)["type"] for line in backlog] == ["a"]
    assert json.loads(queue.get_nowait()) == {"type": "b", "t_ms": 10, "x": 1}
    assert queue.get_nowait() is None
    assert [e["type"] for e in read_events(tmp_path / "events.jsonl")] == ["a", "b"]


def test_to_mono_uses_w_for_foa_and_averages_stereo():
    foa = np.array([[100, 1, 2, 3], [200, 4, 5, 6]], dtype=np.int16)
    assert to_mono(foa, "foa").tolist() == [100, 200]
    stereo = np.array([[100, 300], [-100, 100]], dtype=np.int16)
    assert to_mono(stereo, "stereo").tolist() == [200, 0]


def test_hello_rejects_a_layout_that_does_not_match_the_channels():
    with pytest.raises(ValueError):
        Hello.parse({"sample_rate": 48000, "channels": 2, "layout": "foa"})


def test_recording_keeps_multichannel_audio_and_finds_two_turns(tmp_path):
    rate = 48_000
    mono = np.concatenate(
        [silence(0.5, rate), tone(1.0, rate, 0.3), silence(1.0, rate), tone(0.8, rate, 0.3), silence(0.7, rate)]
    )
    foa = np.stack([mono, mono // 2, mono // 3, mono // 4], axis=1)  # W, Y, Z, X
    hello = Hello(sample_rate=rate, channels=4, layout="foa")

    def make_asr(sink, *, rate, hello):
        return FakeAsr(sink, rate=rate)

    rec = Recording(tmp_path, hello, make_asr)

    async def run():
        await rec.start()
        data = foa.astype("<i2").tobytes()
        step = 4 * 2 * 1003  # odd size: frames split across messages
        for i in range(0, len(data), step):
            await rec.on_audio(data[i : i + step])
        await rec.close()

    asyncio.run(run())
    with wave.open(str(rec.dir / "audio.wav")) as w:
        assert (w.getnchannels(), w.getframerate(), w.getnframes()) == (4, rate, len(mono))
    events = read_events(rec.dir / "events.jsonl")
    turns = [e for e in events if e["type"] == "turn"]
    assert len(turns) == 2
    assert turns[0]["start_ms"] == pytest.approx(500, abs=60)
    assert turns[0]["end_ms"] == pytest.approx(1500, abs=60)
    assert turns[1]["start_ms"] == pytest.approx(2500, abs=60)
    assert [events[0]["type"], events[-1]["type"]] == ["recording_start", "recording_end"]
    assert events[-1]["t_ms"] == pytest.approx(len(mono) / rate * 1000, abs=1)


def test_a_scripted_hello_gets_the_fake_recogniser_even_on_the_meta_backend(monkeypatch):
    from hallwise.asr import make_asr_factory

    monkeypatch.setenv("MODEL_API_KEY", "key")
    make = make_asr_factory("meta")
    scripted = Hello(sample_rate=24_000, channels=1, layout="mono", fake_script=[])
    real = Hello(sample_rate=24_000, channels=1, layout="mono")
    assert isinstance(make(lambda *a, **k: None, rate=24_000, hello=scripted), FakeAsr)
    assert isinstance(make(lambda *a, **k: None, rate=24_000, hello=real), MetaRealtimeAsr)


def test_meta_events_map_onto_turns_with_speaker_and_times():
    out = []
    asr = MetaRealtimeAsr("key", lambda type, t, **d: out.append((type, t, d)))
    for event in [
        {"type": "speechStart", "turnId": 1, "audioProcessedMs": 1200},
        {"type": "transcript", "transcript": "how is the", "final": False, "audioProcessedMs": 2400},
        {"type": "speaker", "label": "B", "audioProcessedMs": 2480},
        {"type": "speechEnd", "turnId": 1, "audioProcessedMs": 3600},
        {"type": "speechComplete", "turnId": 1, "transcript": "How is the weather?", "audioProcessedMs": 3600},
    ]:
        asr.handle(event)
    assert [o[0] for o in out] == ["speech_start", "partial", "speaker", "turn"]
    assert out[-1] == (
        "turn",
        3600,
        {"turn": 1, "text": "How is the weather?", "speaker": "B", "session": 0, "start_ms": 1200, "end_ms": 3600},
    )


def test_ingest_streams_a_recording_and_replays_its_events(tmp_path):
    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=None))
    script = [
        {"start_ms": 200, "end_ms": 900, "speaker": "A", "text": "Hi, I'm Sarah from Acme."},
        {"start_ms": 1000, "end_ms": 1800, "speaker": "B", "text": "I'm Eric, from Vexi."},
    ]
    rate = 24_000
    audio = silence(2.0, rate).tobytes()
    with client.websocket_connect("/ingest") as ws:
        ws.send_text(json.dumps({"sample_rate": rate, "channels": 1, "layout": "mono", "fake_script": script}))
        recording = ws.receive_json()["recording"]
        for i in range(0, len(audio), 3840):
            ws.send_bytes(audio[i : i + 3840])
        ws.send_text(json.dumps({"type": "pose", "t_ms": 500, "yaw": 12.5, "pitch": 0, "roll": 0}))
        ws.send_text(json.dumps({"type": "end"}))
        assert ws.receive_json() == {"type": "closed", "recording": recording}

    events = client.get(f"/api/recordings/{recording}/events").json()
    assert [e["text"] for e in events if e["type"] == "turn"] == [t["text"] for t in script]
    assert {"type": "device_pose", "t_ms": 500, "yaw": 12.5, "pitch": 0, "roll": 0} in events
    assert client.get("/api/recordings").json()[0]["id"] == recording

    with client.websocket_connect(f"/events/{recording}") as ws:
        replayed = [ws.receive_json() for _ in events]
    assert replayed == events


def test_holding_to_talk_diverts_audio_to_a_question(tmp_path):
    """ask_start / ask_end on the ingest socket: the audio in between is not a conversation turn, and the
    owner gets an ask_answer back (here with no Spark key and a scriptless fake, so an error, not a crash)."""
    client = TestClient(create_app(tmp_path, asr="fake", make_extractor=None))
    rate = 24_000
    audio = silence(1.0, rate).tobytes()
    script = [{"start_ms": 200, "end_ms": 900, "speaker": "A", "text": "Hi, I'm Sarah from Acme."}]
    with client.websocket_connect("/ingest") as ws:
        ws.send_text(json.dumps({"sample_rate": rate, "channels": 1, "layout": "mono", "fake_script": script}))
        recording = ws.receive_json()["recording"]
        ws.send_bytes(audio)
        ws.send_text(json.dumps({"type": "ask_start"}))
        ws.send_bytes(audio)
        ws.send_text(json.dumps({"type": "ask_end", "history": []}))
        reply = ws.receive_json()
        assert reply["type"] == "ask_answer"
        assert reply["answer"] == "" and "error" in reply
        ws.send_bytes(audio)
        ws.send_text(json.dumps({"type": "end"}))
        assert ws.receive_json() == {"type": "closed", "recording": recording}
    events = client.get(f"/api/recordings/{recording}/events").json()
    assert [e["text"] for e in events if e["type"] == "turn"] == ["Hi, I'm Sarah from Acme."]
    assert [e["type"] for e in events if e["type"] in ("ask", "ask_answer")] == ["ask", "ask_answer"]


def finished_recording(tmp_path, events, rid="r1"):
    """A server with one finished recording on disk, written straight to its event log."""
    root = tmp_path / "recordings" / rid
    root.mkdir(parents=True)
    (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return TestClient(create_app(tmp_path, asr="fake", make_extractor=None))


def watch_to_the_end(client, url):
    """Every message on an /events socket until the server closes it, each with its arrival time in seconds
    since just before connecting (so no message can be due before its time on this clock)."""
    start = time.monotonic()
    out = []
    with client.websocket_connect(url) as ws:
        while True:
            try:
                msg = ws.receive_json()
            except WebSocketDisconnect:
                return out
            out.append((time.monotonic() - start, msg))


def tick(t_ms):
    return {"type": "replay_clock", "t_ms": t_ms}


THREE = [
    {"type": "recording_start", "t_ms": 0},
    {"type": "turn", "t_ms": 500, "turn": 1, "text": "Hi, I'm Sarah."},
    {"type": "recording_end", "t_ms": 1500},
]


def test_a_finished_recording_replays_at_its_own_pace(tmp_path):
    got = watch_to_the_end(finished_recording(tmp_path, THREE), "/events/r1?pace=10")
    # The clock starts at 0; the gaps here are shorter than a tick, so no tick in between.
    assert [m for _, m in got] == [tick(0), *THREE]
    # Due at 0, 50 and 150 ms: never early, and nowhere near the 1.5 s it took live.
    for (arrived, _), due in zip(got[1:], [0.0, 0.05, 0.15]):
        assert due - 0.005 <= arrived <= due + 0.5


def test_without_pace_a_finished_recording_comes_all_at_once(tmp_path):
    got = watch_to_the_end(finished_recording(tmp_path, THREE), "/events/r1")
    assert [m for _, m in got] == THREE  # no clock ticks either
    assert got[-1][0] < 1.0  # at its own pace the last one would be 1.5 s in


def test_from_ms_sends_everything_before_it_at_once_then_paces(tmp_path):
    events = [
        {"type": "recording_start", "t_ms": 0},
        {"type": "turn", "t_ms": 4000, "turn": 1, "text": "Hi, I'm Sarah."},
        {"type": "person", "t_ms": 2000, "key": "sarah", "name": "Sarah"},  # extracted late: logged after the turn
        {"type": "turn", "t_ms": 10_500, "turn": 2, "text": "Eric, from Vexi."},
        {"type": "recording_end", "t_ms": 11_000},
    ]
    got = watch_to_the_end(finished_recording(tmp_path, events), "/events/r1?pace=2&from_ms=10000")
    # Log order holds, the late person included; pacing starts at from_ms.
    assert [m for _, m in got] == [*events[:3], tick(10_000), *events[3:]]
    assert all(arrived < 0.5 for arrived, _ in got[:4])  # at pace 2 from 0, the first turn alone is 2 s in
    for (arrived, _), due in zip(got[4:], [0.25, 0.5]):
        assert due - 0.005 <= arrived <= due + 0.5


def test_a_long_silence_gets_a_clock_tick_each_second(tmp_path):
    events = [
        {"type": "recording_start", "t_ms": 0},
        {"type": "turn", "t_ms": 60_000, "turn": 1, "text": "Finally."},
        {"type": "recording_end", "t_ms": 60_000},
    ]
    got = watch_to_the_end(finished_recording(tmp_path, events), "/events/r1?pace=50")
    # 60 s at pace 50 is 1.2 s: one tick a second in (50 s of recording), then the two equal-time events together.
    assert [m for _, m in got] == [tick(0), events[0], tick(50_000), *events[1:]]
    assert 0.995 <= got[2][0] <= 1.5
    assert 1.195 <= got[3][0] <= 1.7
    assert got[4][0] - got[3][0] < 0.2


def test_a_live_recording_ignores_pace(tmp_path):
    with TestClient(create_app(tmp_path, asr="fake", make_extractor=None)) as client:  # one event loop for both sockets
        script = [{"start_ms": 200, "end_ms": 900, "speaker": "A", "text": "Hi, I'm Sarah from Acme."}]
        rate = 24_000
        with client.websocket_connect("/ingest") as ingest:
            ingest.send_text(json.dumps({"sample_rate": rate, "channels": 1, "layout": "mono", "fake_script": script}))
            recording = ingest.receive_json()["recording"]
            with client.websocket_connect(f"/events/{recording}?pace=1&from_ms=999999") as ws:
                assert ws.receive_json()["type"] == "recording_start"
                ingest.send_bytes(silence(1.0, rate).tobytes())
                ingest.send_text(json.dumps({"type": "end"}))
                assert ingest.receive_json() == {"type": "closed", "recording": recording}
                rest = []
                while True:
                    try:
                        rest.append(ws.receive_json())
                    except WebSocketDisconnect:
                        break
        assert "replay_clock" not in [m["type"] for m in rest]
        assert [m["text"] for m in rest if m["type"] == "turn"] == ["Hi, I'm Sarah from Acme."]
        assert rest[-1]["type"] == "recording_end"
