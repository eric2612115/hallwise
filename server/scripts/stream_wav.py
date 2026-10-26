"""Stream a WAV file to a Hallwise server as if it were the badge, at real-time speed, and print what comes back.

    uv run python scripts/stream_wav.py path.wav [--server ws://127.0.0.1:8790] [--layout auto]
                                        [--script turns.json] [--keywords "Vexi,Raghunathan"] [--speed 1]

The WAV must be 16-bit PCM: 1 channel (mono), 2 (stereo) or 4 (first-order ambisonics, ACN/SN3D).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import wave

import websockets

FRAME_SECONDS = 0.08
LAYOUTS = {1: "mono", 2: "stereo", 4: "foa"}


async def watch(server: str, recording: str) -> None:
    async with websockets.connect(f"{server}/events/{recording}", max_size=None) as ws:
        async for message in ws:
            event = json.loads(message)
            t = f"{event['t_ms'] / 1000:7.2f}s"
            if event["type"] == "turn":
                print(f"{t}  [{event.get('speaker')}] {event.get('text')}")
            elif event["type"] in ("recording_start", "recording_end", "asr_error"):
                print(f"{t}  {event['type']} {event.get('message', '')}")


async def main(args: argparse.Namespace) -> None:
    with wave.open(args.wav) as w:
        channels, rate, width = w.getnchannels(), w.getframerate(), w.getsampwidth()
        audio = w.readframes(w.getnframes())
    if width != 2:
        raise SystemExit("the WAV must be 16-bit PCM")
    layout = LAYOUTS[channels] if args.layout == "auto" else args.layout
    hello: dict = {
        "sample_rate": rate,
        "channels": channels,
        "layout": layout,
        "device": "simulator",
        "owner_name": args.owner,
        "owner_company": args.company,
        "event": args.event,
        "venue": args.venue,
    }
    if args.script:
        with open(args.script) as f:
            hello["fake_script"] = json.load(f)
    if args.keywords:
        hello["keywords"] = [k.strip() for k in args.keywords.split(",") if k.strip()]

    async with websockets.connect(f"{args.server}/ingest", max_size=None) as ws:
        await ws.send(json.dumps(hello))
        ready = json.loads(await ws.recv())
        print(f"recording {ready['recording']}: {channels} ch, {rate} Hz, {layout}")
        watcher = asyncio.create_task(watch(args.server, ready["recording"]))
        await ws.send(json.dumps({"type": "pose", "t_ms": 0, "yaw": 0.0, "pitch": 0.0, "roll": 0.0}))
        step = int(rate * FRAME_SECONDS) * channels * 2
        for i in range(0, len(audio), step):
            await ws.send(audio[i : i + step])
            await asyncio.sleep(FRAME_SECONDS / args.speed)
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.wait_for(ws.recv(), timeout=120)
    await watcher


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wav")
    parser.add_argument("--server", default="ws://127.0.0.1:8790")
    parser.add_argument("--layout", default="auto", choices=["auto", "mono", "stereo", "foa"])
    parser.add_argument("--script", help="ground-truth turns for the offline fake recogniser")
    parser.add_argument("--keywords", help="comma-separated recognition hints")
    parser.add_argument("--owner", default="Eric", help="the badge wearer's name, so they are not listed as a person met")
    parser.add_argument("--company", default="Hallwise")
    parser.add_argument("--event", default="Living-room rehearsal")
    parser.add_argument("--venue", default="Taipei")
    parser.add_argument("--speed", type=float, default=1.0, help="1 = real time (Muse Voice Transcribe needs it)")
    asyncio.run(main(parser.parse_args()))
