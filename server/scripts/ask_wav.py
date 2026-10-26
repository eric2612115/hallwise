"""Ask a spoken question about a recording: stream a mono 16-bit WAV (16 or 24 kHz) to /ask/{recording}.

    uv run python scripts/ask_wav.py 20261027-012559-ec28 question.wav [--server ws://127.0.0.1:8790] [--bias zh,en] [--keywords "Hallwise,Kenji"]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import wave

FRAME_SECONDS = 0.08


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("wav")
    ap.add_argument("--server", default="ws://127.0.0.1:8790")
    ap.add_argument("--bias", default="")
    ap.add_argument("--keywords", default="")
    args = ap.parse_args()
    import websockets

    with wave.open(args.wav) as w:
        if (w.getnchannels(), w.getsampwidth()) != (1, 2):
            raise SystemExit("needs a mono 16-bit WAV")
        rate, audio = w.getframerate(), w.readframes(w.getnframes())
    hello = {"sample_rate": rate}
    if args.bias:
        hello["language_bias"] = args.bias.split(",")
    if args.keywords:
        hello["keywords"] = [k.strip() for k in args.keywords.split(",")]
    async with websockets.connect(f"{args.server}/ask/{args.recording}", max_size=None) as ws:
        await ws.send(json.dumps(hello))

        async def reader() -> None:
            async for msg in ws:
                e = json.loads(msg)
                if e["type"] == "partial":
                    print("  …", e["text"][-80:])
                elif e["type"] == "question":
                    print("HEARD:", e["text"])
                elif e["type"] == "answer":
                    print("ANSWER:", e.get("answer") or e.get("error"))
                    print("ACTIONS:", e.get("actions"))

        task = asyncio.create_task(reader())
        step = int(rate * FRAME_SECONDS) * 2
        for i in range(0, len(audio), step):
            await ws.send(audio[i : i + step])
            await asyncio.sleep(FRAME_SECONDS)
        await ws.send(json.dumps({"type": "end"}))
        await task


if __name__ == "__main__":
    asyncio.run(main())
