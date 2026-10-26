"""Smoke test for Muse Voice Transcribe: stream a 16 or 24 kHz mono 16-bit WAV at real time through
MetaRealtimeAsr and print every event it produces.

    MODEL_API_KEY=... uv run python scripts/smoke_meta_asr.py path.wav [--keywords "Vexi,Acme"]
"""

from __future__ import annotations

import argparse
import asyncio
import os
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
    asr = MetaRealtimeAsr(os.environ["MODEL_API_KEY"], sink, rate=rate, keywords=keywords)
    await asr.start()
    step = int(rate * FRAME_SECONDS) * 2
    for i in range(0, len(audio), step):
        await asr.send(audio[i : i + step])
        await asyncio.sleep(FRAME_SECONDS)
    await asr.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("--keywords")
    asyncio.run(main(parser.parse_args()))
