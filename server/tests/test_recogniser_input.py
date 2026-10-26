"""What the recogniser gets. Its copy of the mix is levelled: quiet guests lifted, the wearer turned down, peaks kept
under a ceiling, the room not pumped up in the pauses, while the saved audio.wav is untouched. And it is told which
languages to expect when the badge says none."""

import asyncio
import json
import math
import time
import wave

import numpy as np
import pytest

from hallwise.leveler import Leveler
from hallwise.recording import ASR_RATE, Hello, Recording

RNG = np.random.default_rng(11)


def talker(seconds: float, rms_db: float, rate: int = ASR_RATE) -> np.ndarray:
    """Speech-like: noise in four syllables a second that fall silent between them, at `rms_db` dBFS RMS."""
    n = int(seconds * rate)
    t = np.arange(n) / rate
    x = RNG.standard_normal(n) * np.sin(2 * np.pi * 2 * t) ** 2
    return x / np.sqrt(np.mean(x**2)) * 32768 * 10 ** (rms_db / 20)


def room(seconds: float, rms_db: float, rate: int = ASR_RATE) -> np.ndarray:
    return RNG.standard_normal(int(seconds * rate)) * 32768 * 10 ** (rms_db / 20)


def db(x: np.ndarray) -> float:
    x = x.astype(np.float64)
    return 10 * math.log10(np.mean(x**2) / 32768**2 + 1e-20)


def level(chunks: list[np.ndarray]) -> np.ndarray:
    lev = Leveler(ASR_RATE)
    return np.concatenate([lev.process(c) for c in chunks])


def in_chunks(x: np.ndarray, ms: int = 80) -> list[np.ndarray]:
    n = ASR_RATE * ms // 1000
    pcm = np.clip(np.round(x), -32768, 32767).astype(np.int16)
    return [pcm[i : i + n] for i in range(0, len(pcm), n)]


def test_a_quiet_guest_after_the_loud_wearer_comes_up_and_the_wearer_goes_down():
    # The room alone, the wearer at -17 dBFS, a pause, then a guest two metres away at -29, over a room at -50:
    # the levels of the rehearsal mix.
    lead, wearer, pause, guest = np.zeros(2 * ASR_RATE), talker(4, -17), np.zeros(int(0.8 * ASR_RATE)), talker(4, -29)
    x = np.concatenate([lead, wearer, pause, guest])
    x = x + room(len(x) / ASR_RATE, -50)
    y = level(in_chunks(x))
    assert len(y) == len(x) and y.dtype == np.int16
    w0, w1 = len(lead), len(lead) + len(wearer)
    g0 = w1 + len(pause)
    settle = ASR_RATE // 2  # judge each talker after half a second
    before = db(x[g0 + settle :]) - db(x[w0 + settle : w1])
    after = db(y[g0 + settle :]) - db(y[w0 + settle : w1])
    assert before == pytest.approx(-12, abs=1)
    assert after - before >= 6  # the gap to the wearer shrinks by at least half
    assert db(y[w0 + settle : w1]) < db(x[w0 + settle : w1]) - 2  # the wearer is turned down
    assert db(y[g0 + settle :]) > db(x[g0 + settle :]) + 3  # the guest is lifted


def test_peaks_stay_under_the_ceiling():
    x = np.concatenate([room(2, -50), talker(2, -35), talker(0.5, -3) * 2.5])  # a shout right after a quiet stretch
    y = level(in_chunks(x))
    assert np.abs(y).max() <= 32768 * 10 ** (-1 / 20) * 1.01


def test_a_long_pause_does_not_pump_the_room_up():
    # After a quiet guest the room alone for six seconds: the gain does not climb on the room, and drifts back.
    x = np.concatenate([np.zeros(2 * ASR_RATE), talker(3, -32), np.zeros(6 * ASR_RATE)]) + room(11, -50)
    y = level(in_chunks(x))
    tail = slice(9 * ASR_RATE, 11 * ASR_RATE)
    assert db(y[tail]) - db(x[tail]) < 2.5


def test_the_gain_does_not_pump_within_a_steady_talker():
    # A far guest talking for six seconds after two of the room alone: lifted, and the gain holds within the phrase
    # instead of ducking on every syllable (which is what made the recogniser lose a far Japanese aside).
    lev = Leveler(ASR_RATE)
    gains = []
    for c in in_chunks(np.concatenate([np.zeros(2 * ASR_RATE), talker(6, -30)]) + room(8, -52), ms=10):
        lev.process(c)
        gains.append(lev.gain_db)
    steady = np.array(gains[350:])  # from 1.5 s into the talker, every 10 ms
    assert steady.mean() > 3  # lifted
    assert steady.std() < 0.75 and np.ptp(steady) < 3.0


def test_it_runs_far_faster_than_real_time():
    x = in_chunks(talker(30, -25) + room(30, -50))
    started = time.perf_counter()
    level(x)
    assert time.perf_counter() - started < 3.0  # 30 s of audio; measured ~0.1 s


class CapturingAsr:
    def __init__(self):
        self.pcm = bytearray()

    async def start(self):
        pass

    async def send(self, pcm: bytes):
        self.pcm += pcm

    async def finish(self):
        pass


def test_recording_levels_what_the_recogniser_hears_and_keeps_audio_wav_as_it_came(tmp_path):
    # A badge at 48 kHz FOA: the wearer, then a quiet guest. The recogniser gets them closer together; the file
    # on disk is byte for byte what the badge sent.
    rate = 48_000
    lead, wearer, guest = np.zeros(2 * rate), talker(3, -17, rate), talker(3, -29, rate)
    w = np.concatenate([lead, wearer, np.zeros(rate // 2), guest]) + room(8.5, -50, rate)
    foa = np.stack([w, w * 0.3, np.zeros_like(w), w * 0.5], axis=1)
    pcm = np.clip(np.round(foa), -32768, 32767).astype("<i2").tobytes()
    asr = CapturingAsr()
    rec = Recording(tmp_path, Hello(sample_rate=rate, channels=4, layout="foa"), lambda sink, *, rate, hello: asr)

    async def run():
        await rec.start()
        step = 4 * 2 * rate * 80 // 1000
        for i in range(0, len(pcm), step):
            await rec.on_audio(pcm[i : i + step])
        await rec.close()

    asyncio.run(run())
    with wave.open(str(rec.dir / "audio.wav")) as f:
        assert (f.getnchannels(), f.getframerate()) == (4, rate)
        assert f.readframes(f.getnframes()) == pcm
    heard = np.frombuffer(bytes(asr.pcm), dtype="<i2")
    assert abs(len(heard) - len(w) // 2) < ASR_RATE // 10
    a, b = slice(int(2.5 * ASR_RATE), 5 * ASR_RATE), slice(6 * ASR_RATE, int(8.4 * ASR_RATE))
    raw = w[::2]  # the omni channel at the recogniser's rate, near enough for levels
    assert db(raw[b]) - db(raw[a]) == pytest.approx(-12, abs=1)
    assert db(heard[b]) - db(heard[a]) > -12 + 5


def test_the_server_default_language_bias_goes_to_the_transcriber_when_the_badge_names_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HALLWISE_LANGUAGE_BIAS", "en, fr,ja")
    seen = []

    def make_asr(sink, *, rate, hello):
        seen.append(hello.language_bias)
        return FakeAsrStub()

    rec = Recording(tmp_path, Hello(sample_rate=ASR_RATE, channels=1, layout="mono"), make_asr)
    own = Recording(tmp_path, Hello(sample_rate=ASR_RATE, channels=1, layout="mono", language_bias=["zh"]), make_asr)
    assert seen == [["en", "fr", "ja"], ["zh"]]
    assert json.loads((rec.dir / "meta.json").read_text())["asr_language_bias"] == ["en", "fr", "ja"]
    assert rec.hello.language_bias is None  # a question asked by voice keeps the badge's own (none)

    async def ask():
        await rec.start_ask()
        await rec.end_ask()

    asyncio.run(ask())
    assert seen[-1] is None
    monkeypatch.delenv("HALLWISE_LANGUAGE_BIAS")
    Recording(tmp_path, Hello(sample_rate=ASR_RATE, channels=1, layout="mono"), make_asr)
    assert seen[-1] is None
    assert own.hello.language_bias == ["zh"]


class FakeAsrStub:
    async def start(self):
        pass

    async def send(self, pcm):
        pass

    async def finish(self):
        pass


def test_the_leveler_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("HALLWISE_LEVELER", "off")
    asr = CapturingAsr()
    rec = Recording(tmp_path, Hello(sample_rate=ASR_RATE, channels=1, layout="mono"), lambda sink, *, rate, hello: asr)
    x = np.concatenate([talker(2, -17), talker(2, -29)]) + room(4, -50)
    pcm = np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes()

    async def run():
        await rec.start()
        await rec.on_audio(pcm)
        await rec.close()

    asyncio.run(run())
    assert bytes(asr.pcm) == pcm
