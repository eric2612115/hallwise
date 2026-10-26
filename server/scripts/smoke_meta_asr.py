"""Smoke test for Muse Voice Transcribe: stream a 16 or 24 kHz mono 16-bit WAV at real time through
MetaRealtimeAsr and print every event it produces.

    MODEL_API_KEY=... uv run python scripts/smoke_meta_asr.py path.wav [--keywords "Vexi,Acme"] [--language-bias ja,en]

Paced against the wall clock: sleeping a fixed frame after each send drifts below real time, and the service
closes a session whose ingress falls behind.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import wave

from hallwise.asr import MetaRealtimeAsr

FRAME_SECONDS = 0.08


async def main(args: argparse.Namespace) -> None:
    with wave.open(args.wav) as w:
        if (w.getnchannels(), w.getsampwidth()) != (1, 2):
            raise SystemExit("needs a mono 16-bit WAV")
        rate = w.getframerate()
        audio = w.readframes(w.getnframes())

    def sink(type: str, t_ms: int, **data: object) -> None:
        if type == "partial":
            return
        print(f"{t_ms / 1000:6.2f}s  {type:13s} {data}")

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
    bias = [b.strip() for b in args.language_bias.split(",")] if args.language_bias else None
    asr = MetaRealtimeAsr(os.environ["MODEL_API_KEY"], sink, rate=rate, keywords=keywords, language_bias=bias, mode=args.mode)
    await asr.start()
    step = int(rate * FRAME_SECONDS) * 2
    started = time.monotonic()
    for k, i in enumerate(range(0, len(audio), step)):
        await asr.send(audio[i : i + step])
        delay = started + (k + 1) * FRAME_SECONDS - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
    await asr.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("--keywords")
    parser.add_argument("--language-bias", help="comma-separated, sent as languageBias in the handshake")
    parser.add_argument("--mode", default="DIARIZATION")
    asyncio.run(main(parser.parse_args()))
