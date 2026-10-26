"""Render the living-room party (demo/SCRIPT.md) with Kokoro: the badge's first-order-ambisonics rehearsal mix, and
the per-device files the shoot's rig plays.

    ~/.venvs/kokoro/bin/python scripts/make_party_audio.py OUT_DIR [--rig ../demo/rig] [--julien michael|script]

Runs in the Kokoro venv (kokoro_onnx, numpy), not the server's. Writes:

    OUT_DIR/party_foa.wav      4 ch, 48 kHz, ACN W Y Z X, SN3D: what the badge on Eric's chest would hear
    OUT_DIR/timeline.json      ground truth: every turn with speaker, text, start/end, intended azimuth and distance
    OUT_DIR/cache/             one dry clip per line, reused between runs
    RIG/*.wav, RIG/CUES.md     with --rig: each device's own lines, dry, mono 48 kHz 16-bit, plus the TV's hall bed

Every line is phonemized with espeak-ng (language-switch flags removed, so no "(en)" is spoken), with names in
their own language's phonemes and light L2 shaping per persona, then voiced by Kokoro from the phonemes. Japanese
is written out in phonemes, the way Kokoro's Japanese voices were trained: espeak reads kanji as "Chinese letter",
and its kana reading drops ん and the long vowels (きんようび came out "kiyoubi"), which Muse Voice Transcribe heard
as "起用めめ" or not at all.

Each voice is placed by azimuth (0 = ahead, positive = wearer's left) and distance: the direct sound falls as 1/r,
the room's diffuse tail (RT60 0.4 s, critical distance 1.2 m) does not, so a far talker is quieter and less
directional. Eric's voice comes from just above the badge: loud, near-omni.

What the second rehearsal changed: Julien is am_michael in both languages (ff_siwis pitched down for French got a
second speaker label); hm_omega and jm_kumo get a presence lift (they render very dark); Mac-3 and iPhone-K play
6 dB louder (at the sofa's level the transcriber dropped their turns); hand-offs between devices are 1.0-1.8 s.

What the third changed: Siddharth says his name once, with his company ("Siddharth Raghunathan, Quill Mesh, we met
at Blockchain Week"), so the badge can match him; Kenji's murmur is the phoneme version above, which the
transcriber writes as 金曜日ね、メモしておこう。 alone and after his English, and it is no longer 3 dB down. From
2.2 m in the simulated room it is still lost: about half the time in a short session with languageBias en,fr,ja,
never without, and never at the end of the whole take (see HALLWISE_LANGUAGE_BIAS in recording.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import wave
from pathlib import Path

import numpy as np

try:
    import onnxruntime

    onnxruntime.disable_telemetry_events()  # its exit-time upload spins forever without network
except Exception:
    pass

import kokoro_onnx  # noqa: E402
import phonemizer  # noqa: E402
from kokoro_onnx.config import DEFAULT_VOCAB  # noqa: E402

RATE = 48_000
KOKORO = Path.home() / ".cache/hyperframes/tts"
RT60 = 0.4
CRITICAL_M = 1.2  # furnished living room, talker facing Eric
LEVEL_1M = -26.0  # dBFS RMS of a talker's active speech at 1 m, omni channel
BED_DB = -45.0  # the hall bed's RMS in the omni channel: low, under every voice
SEMITONES = 2 ** (1 / 12)

# Light L2 shaping on English phonemes, per persona. Kept off the words the pipeline must hear (weekdays).
SHAPING = {
    "french": [("ð", "z"), ("θ", "s"), ("ɹ", "ʁ"), ("ɚ", "œʁ")],
    "french_light": [("ð", "z"), ("θ", "s")],  # ff_siwis already sounds French; heavier shaping lost "pre-seed"
    "indian": [("θ", "t"), ("ð", "d"), ("ɹ", "ɾ"), ("ɚ", "əɾ"), ("oʊ", "oː"), ("eɪ", "eː")],
    "japanese": [("ɹ", "ɾ"), ("ɚ", "aː"), ("æ", "a")],
}

# Who speaks with which Kokoro voice, where they stand (azimuth°, metres, elevation°) and which device plays them.
CAST = {
    "eric": {"voice": "am_fenrir", "lang": "en-us", "az": 0, "r": 0.3, "el": 70, "device": None},
    "leo": {"voice": "bm_george", "lang": "en-gb", "az": 0, "r": 1.0, "device": None},
    "margaux": {"voice": "ff_siwis", "lang": "en-us", "shape": "french_light", "az": 20, "r": 0.9, "device": "mac1"},
    "julien": {"voice": "am_michael", "lang": "en-us", "shape": "french", "az": 5, "r": 1.9, "device": "mac2"},
    "waiter": {"voice": "bf_emma", "lang": "en-gb", "az": 75, "r": 2.0, "device": "mac3"},
    "siddharth": {"voice": "hm_omega", "lang": "en-us", "shape": "indian", "az": 0, "r": 1.6, "device": "mac3", "presence": 10, "level": 6},
    "kenji": {"voice": "jm_kumo", "lang": "en-us", "shape": "japanese", "az": 35, "r": 2.2, "device": "iphoneK", "presence": 10, "level": 6},
}

FR, JA = "fr-fr", "ja"

# The take, in order. gap: seconds of silence before the line starts (after the previous voice ends).
# A part is (text, lang) | {"ph": phonemes} | a pause in seconds; "gain" lowers an aside.
# scene sets where the TV (the hall bed) is relative to Eric.
TAKE: list[dict] = [
    {"scene": "door", "tv_az": 135},
    {"who": "leo", "gap": 7.0, "parts": [("Eric! Hey, you made it.", None)]},
    {"who": "eric", "gap": 0.6, "parts": [("Leo! Good to see you.", None)]},
    {"who": "leo", "gap": 0.7, "parts": [("So, for the badge: Leo Huang, Brightpath. We build wallet infrastructure for apps.", None)]},
    {"who": "eric", "gap": 0.6, "parts": [("I'm Eric, from Hallwise. This badge.", None)]},
    {"who": "leo", "gap": 0.6, "parts": [("A name badge that listens. Okay, I want to see that.", None)]},
    {"who": "eric", "gap": 0.7, "parts": [("I'll send you our deck tonight.", None)]},
    {"who": "leo", "gap": 0.5, "parts": [("Tonight. I'll hold you to that.", None)]},
    {"who": "eric", "gap": 1.0, "parts": [("One photo?", None), 3.4, ("There. Now you have a face.", None)]},
    {"who": "eric", "gap": 2.5, "parts": [("It takes a few seconds.", None)]},
    {"who": "leo", "gap": 4.5, "parts": [("Come, you should meet Margaux and Julien.", None)], "az": 10},
    {"scene": "sofa", "tv_az": 90},
    {"who": "margaux", "gap": 7.0, "cue": True, "click": "2", "note": "Eric stops at the sofa's west end; ", "parts": [("Franchement, le deck d'hier, j'ai rien compris à leur modèle.", FR)]},
    {"who": "julien", "gap": 1.0, "cue": True, "click": "chained", "parts": [("Pareil. Vingt slides, zéro chiffre.", FR)]},
    {"who": "leo", "gap": 2.8, "az": -40, "r": 1.3, "parts": [("Margaux, Julien, this is Eric. Eric makes the badge.", None)]},
    {"who": "eric", "gap": 0.6, "parts": [("Hi. Eric, from Hallwise. May I join your conversation?", None)]},
    {"who": "margaux", "gap": 0.8, "cue": True, "click": "3", "parts": [("Margaux Lefèvre,", FR), ("Corvane Capital.", None)]},
    {"who": "julien", "gap": 1.8, "cue": True, "click": "chained", "parts": [("Julien Caron.", FR), ("I'm with", None), ("Margaux;", FR), ("I do the diligence.", None)]},
    {"who": "eric", "gap": 3.0, "parts": [("Margaux, are you investing this quarter?", None)]},
    {"who": "margaux", "gap": 1.0, "cue": True, "click": "4", "parts": [("Pre-seed, yes. Send me your one-pager.", None), 0.8, {"text": "Bon, une page, avec des chiffres.", "lang": FR, "gain": -6}]},
    {"who": "eric", "gap": 0.7, "parts": [("One page, with numbers. Tomorrow.", None)]},
    {"who": "julien", "gap": 1.0, "cue": True, "click": "5", "parts": [("Come by our office next week and show us the demo? Wednesday afternoon?", None)]},
    {"who": "eric", "gap": 0.6, "parts": [("Wednesday works.", None)]},
    {"scene": "walk", "tv_az": 180},
    {"who": "waiter", "gap": 8.0, "cue": True, "click": "Mac-3 waiter key", "note": "as Eric walks past the table's west end, after ", "gain": -3, "parts": [("Something to drink?", None)]},
    {"who": "eric", "gap": 0.5, "parts": [("I'm good, thanks.", None)]},
    {"scene": "table", "tv_az": 70},
    {"who": "siddharth", "gap": 6.0, "cue": True, "click": "6", "note": "Eric at the table's west end, at least 3 s after cue 7; after ", "parts": [
        ("Eric!", None), {"ph": "sˈɪdɑːɾt ɾˌɑːɡʊnˈɑːtən,", "text": "Siddharth Raghunathan,"},
        ("Quill Mesh, we met at Blockchain Week. You know Kenji.", None)]},
    {"who": "kenji", "gap": 1.5, "cue": True, "click": "chained", "parts": [
        {"ph": "kˈendʒi wˌatanˈabe,", "text": "Kenji Watanabe,"}, {"ph": "hˌoʊʃizˈoːɾə", "text": "Hoshizora"}, ("Robotics. We keep running into each other.", None)]},
    {"who": "eric", "gap": 6.5, "parts": [("It remembered both before I did.", None)]},
    {"who": "eric", "gap": 1.5, "parts": [("Kenji! The coffee. Thursday?", None)]},
    {"who": "kenji", "gap": 1.0, "cue": True, "click": "7", "parts": [
        ("Thursday is...", None), 0.7, ("no, Friday. Friday is better.", None), 0.9,
        {"ph": "kʲiɴjoːbʲi ne, memo ɕite okoː.", "text": "金曜日ね、メモしておこう。", "lang": JA, "speed": 0.95}]},
    {"scene": "out", "tv_az": 150, "tail": 16.0},
]

BED_LINES_EN = [
    "We closed our seed round in March, mostly angels.", "The panel ran long, so I missed the first half.",
    "Are you staying for the after party?", "Our biggest customer is a logistics company in Kaohsiung.",
    "I flew in from Singapore this morning.", "We pivoted from consumer to enterprise last year.",
    "The traffic on the way here was terrible.", "Have you tried the dumplings? They're really good.",
    "We're hiring two engineers, mostly backend.", "Honestly, the hardest part is distribution.",
    "I think the market will come back next year.", "She used to run growth at a payments startup.",
    "We're doing a pilot with three hospitals.", "It's my first time in Taipei, actually.",
    "Do you know where the bathroom is?", "The food here is better than last time.",
    "The keynote was better than I expected.", "We're still pre-revenue, but the waitlist is long.",
    "I'm mostly here to listen, to be honest.", "They raised a lot, but I'm not sure about the team.",
    "Did you read that article about the chip shortage?", "The projector broke halfway, but people loved it.",
    "We moved the office to Neihu last month.", "I'm advising a couple of climate startups.",
    "The weather has been so nice this week.", "Let's take a picture before everyone leaves.",
    "I met him at a conference in Seoul.", "We're building tooling for small game studios.",
]
BED_LINES_ZH = ["你們公司現在多少人？", "下個月我們要去新加坡參展。", "這個活動每年都辦嗎？", "我覺得他們的產品還不錯。",
                "等一下要不要一起去吃宵夜？", "最近募資真的比較難。"]
BED_VOICES_EN = ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_adam", "am_liam", "bm_daniel", "bm_lewis", "bf_isabella"]
BED_VOICES_ZH = ["zf_xiaoxiao", "zm_yunxi"]


class Voices:
    def __init__(self, cache: Path):
        self.k = kokoro_onnx.Kokoro(str(KOKORO / "models/kokoro-v1.0.onnx"), str(KOKORO / "voices/voices-v1.0.bin"))
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def phonemes(text: str, lang: str, shape: str | None = None) -> str:
        p = phonemizer.phonemize(text, lang, preserve_punctuation=True, with_stress=True, language_switch="remove-flags")
        if shape and lang.startswith("en"):
            for a, b in SHAPING[shape]:
                p = p.replace(a, b)
        return "".join(c for c in p if c in DEFAULT_VOCAB).strip()

    def say(self, ph: str, voice: str, speed: float = 1.0, pitch: float = 0.0) -> np.ndarray:
        """Phonemes → float mono at 48 kHz; pitch in semitones (down is negative), duration kept."""
        key = hashlib.sha1(f"{voice}|{speed}|{pitch}|{ph}".encode()).hexdigest()[:16]
        path = self.cache / f"{key}.npy"
        if path.exists():
            return np.load(path)
        factor = SEMITONES ** -pitch  # >1 renders faster, then the stretch lowers pitch and restores the length
        audio, sr = self.k.create(ph, voice=voice, speed=speed * factor, is_phonemes=True)
        audio = np.asarray(audio, dtype=np.float64)
        out = resample(audio, int(round(len(audio) * RATE / sr * factor)))
        np.save(path, out)
        return out


def resample(x: np.ndarray, n_out: int) -> np.ndarray:
    """Band-limited resampling to n_out samples by FFT, padded so the ends do not wrap."""
    pad = 4096
    xp = np.concatenate([np.zeros(pad), x, np.zeros(pad)])
    n, m = len(xp), int(round(len(xp) * n_out / len(x)))
    spec = np.fft.rfft(xp)
    out_spec = np.zeros(m // 2 + 1, dtype=complex)
    k = min(len(spec), len(out_spec))
    out_spec[:k] = spec[:k]
    y = np.fft.irfft(out_spec, m) * (m / n)
    start = int(round(pad * m / n))
    return y[start : start + n_out]


def active_rms(x: np.ndarray) -> float:
    """RMS over the louder 20 ms blocks (speech, not the pauses)."""
    b = RATE // 50
    blocks = x[: len(x) // b * b].reshape(-1, b)
    e = (blocks**2).mean(axis=1)
    loud = e[e >= 0.1 * e.max()] if len(e) else np.array([1e-12])
    return float(np.sqrt(loud.mean()))


def db(x: float) -> float:
    return 10 ** (x / 20)


def presence(x: np.ndarray, gain_db: float) -> np.ndarray:
    """Lift 1-4 kHz and above by up to gain_db and thin the rumble below 120 Hz. hm_omega and jm_kumo come out of
    this Kokoro build very dark (spectral centroid ~400 Hz, under 1% of the energy above 4 kHz, against ~800 Hz and
    4-7% for ff_siwis or am_michael); from across the room the transcriber did not hear Kenji as speech at all."""
    if not gain_db:
        return x
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    shelf = np.clip(np.log2(np.maximum(f, 1) / 1000) / 2, 0, 1)  # 0 at 1 kHz, full at 4 kHz
    hp = 1 / np.sqrt(1 + (120 / np.maximum(f, 1)) ** 4)
    return np.fft.irfft(spec * db(gain_db) ** shelf * hp, len(x))


def render_line(v: Voices, line: dict, julien: str) -> np.ndarray:
    who = CAST[line["who"]]
    voice, base_lang, shape = who["voice"], who["lang"], who.get("shape")
    pieces: list[np.ndarray] = []
    run: list[str] = []
    run_gain, run_speed = 0.0, 1.0
    run_voice, run_pitch = voice, 0.0

    def flush() -> None:
        nonlocal run
        if run:
            clip = v.say(" ".join(run), run_voice, run_speed, run_pitch)
            pieces.append(clip / active_rms(clip) * db(run_gain))
        run = []

    for part in line["parts"]:
        if isinstance(part, (int, float)):
            flush()
            pieces.append(np.zeros(int(part * RATE)))
            continue
        if isinstance(part, tuple):
            part = {"text": part[0], "lang": part[1]}
        lang = part.get("lang") or base_lang
        gain, speed = part.get("gain", 0.0), part.get("speed", 1.0)
        # Julien, per SCRIPT.md: French in ff_siwis pitched down four semitones, English in am_michael.
        pv, pp = voice, 0.0
        if line["who"] == "julien" and julien == "script" and lang == FR and all(
            (isinstance(p, tuple) and p[1] == FR) or (isinstance(p, dict) and p.get("lang") == FR) for p in line["parts"]
        ):
            pv, pp = "ff_siwis", -4.0
        if (gain, speed, pv, pp) != (run_gain, run_speed, run_voice, run_pitch):
            flush()
            run_gain, run_speed, run_voice, run_pitch = gain, speed, pv, pp
        run.append(part["ph"] if "ph" in part else Voices.phonemes(part["text"], lang, shape))
    flush()
    return presence(np.concatenate(pieces), who.get("presence", 0)) * db(line.get("gain", 0.0))


def reverb_irs(seed: int) -> np.ndarray:
    """(n, 4) diffuse tails for W, Y, Z, X: decorrelated, exponentially decaying, SN3D-weighted, unit W energy."""
    rng = np.random.default_rng(seed)
    n = int(RT60 * 1.5 * RATE)
    t = np.arange(n) / RATE
    env = np.exp(-6.91 * t / RT60) * np.clip((t - 0.004) / 0.02, 0, 1)
    irs = rng.standard_normal((n, 4)) * env[:, None]
    irs = (irs + np.roll(irs, 1, axis=0) + np.roll(irs, 2, axis=0)) / 3  # a little air absorption
    irs /= np.sqrt((irs[:, 0] ** 2).sum())
    irs[:, 1:] /= np.sqrt((irs[:, 1:] ** 2).sum(axis=0)) * math.sqrt(3)
    return irs


def fftconv(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]


def place(foa: np.ndarray, at: int, s: np.ndarray, az: float, r: float, el: float, irs: np.ndarray) -> None:
    """Add a mono source to the FOA bus: direct sound at (az, el) with gain 1/r, plus the room's diffuse tail."""
    th, ph = math.radians(az), math.radians(el)
    g = 1.0 / r
    gains = np.array([1.0, math.sin(th) * math.cos(ph), math.sin(ph), math.cos(th) * math.cos(ph)]) * g
    end = min(len(foa), at + len(s))
    foa[at:end] += s[: end - at, None] * gains[None, :]
    tails = [fftconv(s, irs[:, c]) for c in range(4)]
    # Scale by the clip's own energy, not the IR's: speech is low-frequency heavy, so a white-noise normalisation
    # would make the room louder than the stated critical distance.
    k = (1.0 / CRITICAL_M) * math.sqrt((s**2).sum() / max((tails[0] ** 2).sum(), 1e-20))
    for c, tail in enumerate(tails):
        e = min(len(foa), at + len(tail))
        foa[at:e, c] += tail[: e - at] * k


def hall_bed(v: Voices, seconds: float, seed: int = 7) -> np.ndarray:
    """Mono babble from eleven voices in seven overlapping streams, loopable: the last 5 s crossfade into the start."""
    rng = np.random.default_rng(seed)
    fade = 5.0
    n = int((seconds + fade) * RATE)
    bed = np.zeros(n)
    streams = BED_VOICES_EN[:6] + BED_VOICES_ZH[:1]
    pool = {voice: [] for voice in BED_VOICES_EN + BED_VOICES_ZH}
    for i, voice in enumerate(BED_VOICES_EN):
        for text in BED_LINES_EN[i::len(BED_VOICES_EN)]:
            pool[voice].append(v.say(Voices.phonemes(text, "en-us"), voice, 1.05))
    for i, voice in enumerate(BED_VOICES_ZH):
        for text in BED_LINES_ZH[i::len(BED_VOICES_ZH)]:
            pool[voice].append(v.say(Voices.phonemes(text, "cmn"), voice, 1.05))
    for k, voice in enumerate(streams):
        voices = [voice] + [x for x in pool if x not in streams][k % 4 :: 4]
        t = rng.uniform(0, 2.0)
        gain = db(rng.uniform(-4, 0))
        while t < seconds + fade:
            who = voices[rng.integers(len(voices))]
            clip = pool[who][rng.integers(len(pool[who]))]
            a = int(t * RATE)
            e = min(n, a + len(clip))
            bed[a:e] += clip[: e - a] / active_rms(clip) * gain
            t += len(clip) / RATE + rng.uniform(0.25, 1.4)
    loop = int(seconds * RATE)
    f = int(fade * RATE)
    ramp = np.linspace(0, 1, f)
    out = bed[:loop].copy()
    out[:f] = bed[:f] * ramp + bed[loop : loop + f] * (1 - ramp)
    return out / np.sqrt((out**2).mean())


def write_wav(path: Path, x: np.ndarray) -> None:
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1] if pcm.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--rig", help="also export each device's lines and the hall bed here")
    ap.add_argument("--julien", default="michael", choices=["script", "michael"],
                    help="michael: am_michael for French and English (SCRIPT.md's fallback; the rehearsal showed the "
                    "split voice gets two speaker labels); script: French in ff_siwis -4 st, English in am_michael")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    v = Voices(out / "cache")

    # Lay the take out on a timeline.
    turns, t, scenes = [], 0.0, []
    for line in TAKE:
        if "scene" in line:
            scenes.append({"scene": line["scene"], "t": t, "tv_az": line["tv_az"]})
            t += line.get("tail", 0.0)
            continue
        clip = render_line(v, line, args.julien)
        start = t + max(line["gap"], 0.35)
        who = CAST[line["who"]]
        turns.append({
            **{k: line[k] for k in ("who",)}, "clip": clip, "start": start, "end": start + len(clip) / RATE,
            "az": line.get("az", who["az"]), "r": line.get("r", who["r"]), "el": line.get("el", who.get("el", 0)),
            "cue": line.get("cue", False), "click": line.get("click", ""), "gap": line["gap"], "note": line.get("note", ""), "scene": scenes[-1]["scene"],
            "text": " ".join(p[0] if isinstance(p, tuple) else p.get("show", p.get("text", "")) for p in line["parts"] if not isinstance(p, (int, float))).strip(),
        })
        t = turns[-1]["end"]
    total = t
    n = int(total * RATE)
    print(f"take: {total:.1f} s, {len(turns)} turns")

    # The FOA mix: voices at their places, the hall bed from the TV, a little room noise.
    foa = np.zeros((n, 4))
    for i, turn in enumerate(turns):
        # The far devices play louder: at the same source level as the sofa, Muse Voice Transcribe dropped
        # Siddharth's and Kenji's turns next to Eric's voice at the badge, 11-12 dB louder.
        s = turn["clip"] * db(LEVEL_1M + CAST[turn["who"]].get("level", 0))
        place(foa, int(turn["start"] * RATE), s, turn["az"], turn["r"], turn["el"], reverb_irs(100 + int(hashlib.sha1(turn["who"].encode()).hexdigest()[:4], 16)))
    bed = hall_bed(v, 185.0)
    bed_bus = np.zeros((n, 4))
    for i, sc in enumerate(scenes):
        a = int(sc["t"] * RATE)
        b = int((scenes[i + 1]["t"] if i + 1 < len(scenes) else total) * RATE)
        lo, hi = max(0, a - RATE // 2), min(n, b + RATE // 2)
        piece = np.zeros(n)
        piece[lo:hi] = np.resize(bed, n)[lo:hi]
        w = np.ones(hi - lo)
        ramp = min(RATE, (hi - lo) // 2)
        w[:ramp] = np.linspace(0, 1, ramp) if lo > 0 else 1
        w[-ramp:] = np.linspace(1, 0, ramp) if hi < n else 1
        piece[lo:hi] *= w
        place(bed_bus, 0, piece, sc["tv_az"], 3.5, 10, reverb_irs(900 + i))
    bed_bus *= db(BED_DB) / np.sqrt((bed_bus[:, 0] ** 2).mean())
    foa += bed_bus
    rng = np.random.default_rng(3)
    foa += rng.standard_normal((n, 4)) * db(-68) * np.array([1, 0.58, 0.58, 0.58])
    peak = np.abs(foa).max()
    if peak > db(-1):
        foa *= db(-1) / peak
        print(f"mix scaled by {20 * math.log10(db(-1) / peak):.1f} dB to keep 1 dB of headroom")
    write_wav(out / "party_foa.wav", foa)
    timeline = [{k: v_ for k, v_ in x.items() if k != "clip"} for x in turns]
    for x in timeline:
        x["start_ms"], x["end_ms"] = int(x.pop("start") * 1000), int(x.pop("end") * 1000)
    (out / "timeline.json").write_text(json.dumps({"seconds": round(total, 2), "julien": args.julien, "scenes": scenes, "turns": timeline}, ensure_ascii=False, indent=1))
    print(f"wrote {out / 'party_foa.wav'} and {out / 'timeline.json'}")

    if args.rig:
        export_rig(Path(args.rig), turns, bed, args.julien)
    sys.stdout.flush()
    os._exit(0)  # onnxruntime's teardown can hang the interpreter at exit


def export_rig(rig: Path, turns: list[dict], bed: np.ndarray, julien: str) -> None:
    rig.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    rows = []
    last_eric = "(start)"
    previous = None
    for turn in turns:
        if turn["who"] == "eric":
            last_eric = f"ERIC: “{turn['text']}”"
            previous = turn
            continue
        if turn["who"] == "leo":
            last_eric = f"[FRIEND]: “{turn['text']}” (live)"
            previous = turn
            continue
        device = CAST[turn["who"]]["device"]
        counts[device] = counts.get(device, 0) + 1
        k = counts[device]
        name = f"{device}-{k:02d}-{turn['who']}.wav" if device == "mac3" else f"{device}-{turn['who']}-{k:02d}.wav"
        head, tail = np.zeros(int(0.15 * RATE)), np.zeros(int(0.4 * RATE))
        x = np.concatenate([head, turn["clip"], tail])
        x = x / active_rms(x) * db(-20)
        x *= min(1.0, db(-1) / np.abs(x).max())
        write_wav(rig / name, x)
        follows = turn["note"] + last_eric
        if previous is not None and previous["who"] not in ("eric", "leo"):
            follows = f"cue {len(rows)} ends ({previous['who'].capitalize()})"
        click = {"chained": f"auto, {turn['gap']:.1f} s after the previous cue ends", "": "-"}.get(turn["click"], turn["click"])
        rows.append((len(rows) + 1, click, device, name, turn["text"], follows, round(len(x) / RATE, 1)))
        previous = turn
    loud = bed * db(-23) * min(1.0, db(-1) / (np.abs(bed).max() * db(-23)))
    write_wav(rig / "tv-hall-bed.wav", loud)
    devices = {"mac1": "Mac-1 (sofa 1, near cushion)", "mac2": "Mac-2 (sofa 1, far cushion)",
               "mac3": "Mac-3 (dining table, east end)", "iphoneK": "iPhone-K (sofa 2, south armrest, head height)"}
    lines = [
        "# Rig cues",
        "",
        "Each device plays only its own files, in its own order, when the controller cues it. Eric and [FRIEND] speak",
        "live; their lines are listed only as the prompt for the next cue. The TV (Mac-0 over HDMI) loops",
        "`tv-hall-bed.wav` from the first click (“They sound like this.”) until Stop.",
        "",
        "Files are dry (no room added), mono, 48 kHz, 16-bit, levelled to -20 dBFS active speech with 0.15 s of lead-in.",
        "Set each device's volume in the room, measured at Eric's marks: Margaux (near cushion) a little louder than",
        "Julien (far cushion); Mac-3 (Siddharth) and iPhone-K (Kenji) about 6 dB louder at the source than Mac-1/Mac-2.",
        "In rehearsal, at equal source level, the transcriber dropped their turns next to Eric's own voice at the badge.",
        "Mac-3 plays the waiter, then waits at least three seconds before Siddharth (separate presenter keys).",
        "",
        "Rendered by `server/scripts/make_party_audio.py` with Kokoro: Margaux `ff_siwis`; Julien "
        + ("`ff_siwis` four semitones down for French, `am_michael` for English" if julien == "script" else "`am_michael` for French and English")
        + "; waiter `bf_emma`; Siddharth `hm_omega`; Kenji `jm_kumo`; hall bed eleven other voices (English and Mandarin).",
        "",
        "Clicks follow SCRIPT.md's `[click]` marks; click 1 unmutes the TV. A chained cue fires by itself once the",
        "previous file ends, so one click plays both halves of an exchange.",
        "",
        "| Cue | Click | Device | File | Line | After | Length |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.append("| 0 | 1 | TV (Mac-0, HDMI) | `tv-hall-bed.wav` | hall babble, 3:05, loops seamlessly until Stop | ERIC: “They sound like this.” | loop |")
    for cue, click, device, name, text, follows, seconds in rows:
        lines.append(f"| {cue} | {click} | {devices[device]} | `{name}` | {text} | {follows} | {seconds} s |")
    lines.append("")
    (rig / "CUES.md").write_text("\n".join(lines))
    total = sum(p.stat().st_size for p in rig.glob("*.wav"))
    print(f"rig: {len(rows)} cues + hall bed in {rig}, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
