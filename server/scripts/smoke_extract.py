"""Smoke test for the Muse Spark extraction: run one pass over a transcript and print what comes out.

    MODEL_API_KEY=... uv run python scripts/smoke_extract.py tests/fixtures/demo_transcript.json \
        --owner Eric --company Vexi --vocabulary Vexi [--effort low]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from hallwise.extract import Extractor, SparkClient, Turn


async def main(args: argparse.Namespace) -> None:
    with open(args.transcript) as f:
        turns = [Turn(**t) for t in json.load(f)]
    client = SparkClient(os.environ["MODEL_API_KEY"], model=args.model, effort=args.effort)
    extractor = Extractor(client, args.owner, args.company, [v for v in args.vocabulary.split(",") if v])
    for turn in turns:
        extractor.add_turn(turn)
    events = await extractor.run()
    print(f"{client.last_seconds:.1f}s  usage {client.last_usage}\n")
    for kind, _, data in events:
        data = {k: v for k, v in data.items() if k != "new"}
        print(f"{kind:13s} {json.dumps(data, ensure_ascii=False)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript")
    parser.add_argument("--owner", default="")
    parser.add_argument("--company", default="")
    parser.add_argument("--vocabulary", default="")
    parser.add_argument("--model", default="muse-spark-1.3")
    parser.add_argument("--effort", default="low")
    asyncio.run(main(parser.parse_args()))
