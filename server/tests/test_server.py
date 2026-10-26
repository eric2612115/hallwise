import asyncio
import json
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

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
