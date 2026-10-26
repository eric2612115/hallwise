"""HTTP and WebSocket entry points.

    /ingest                     the badge streams here: a JSON hello, then binary PCM frames and JSON pose messages
    /events/{recording}         watch a recording: everything so far, then live events until it ends
    /api/recordings             recordings, newest first
    /api/recordings/{id}/events one recording's event log

Run: HALLWISE_ASR=fake|meta uv run uvicorn hallwise.app:app --port 8787
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from .asr import make_asr_factory
from .events import read_events
from .extract import Extractor, SparkClient
from .recording import Hello, Recording


def spark_extractor_factory() -> Callable[[Hello], Extractor | None] | None:
    """Muse Spark extraction when HALLWISE_EXTRACT is "spark" (the default whenever MODEL_API_KEY is set)."""
    key = os.environ.get("MODEL_API_KEY")
    mode = os.environ.get("HALLWISE_EXTRACT", "spark" if key else "off")
    if mode == "off":
        return None
    if mode != "spark" or not key:
        raise RuntimeError("HALLWISE_EXTRACT=spark needs MODEL_API_KEY")
    model = os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")
    effort = os.environ.get("HALLWISE_SPARK_EFFORT", "low")

    def make(hello: Hello) -> Extractor:
        return Extractor(
            SparkClient(key, model=model, effort=effort),
            owner_name=hello.owner_name,
            owner_company=hello.owner_company,
            vocabulary=hello.keywords or [],
        )

    return make


def create_app(
    data_dir: Path | None = None,
    asr: str | None = None,
    make_extractor: Callable[[Hello], Extractor | None] | None | str = "env",
) -> FastAPI:
    data = Path(data_dir or os.environ.get("HALLWISE_DATA", "data"))
    make_asr = make_asr_factory(asr or os.environ.get("HALLWISE_ASR", "fake"))
    if make_extractor == "env":
        make_extractor = spark_extractor_factory()
    app = FastAPI(title="Hallwise")
    live: dict[str, Recording] = {}

    @app.websocket("/ingest")
    async def ingest(ws: WebSocket) -> None:
        await ws.accept()
        try:
            hello = Hello.parse(json.loads(await ws.receive_text()))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
            await ws.close(code=1008, reason=str(err)[:120])
            return
        rec = Recording(data, hello, make_asr, make_extractor)
        live[rec.id] = rec
        await rec.start()
        await ws.send_json({"type": "ready", "recording": rec.id})
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    await rec.on_audio(msg["bytes"])
                elif msg.get("text"):
                    control = json.loads(msg["text"])
                    if control.get("type") == "pose":
                        rec.on_pose(control)
                    elif control.get("type") == "end":
                        break
        except WebSocketDisconnect:
            pass
        finally:
            await rec.close()
            live.pop(rec.id, None)
        try:
            await ws.send_json({"type": "closed", "recording": rec.id})
            await ws.close()
        except (WebSocketDisconnect, RuntimeError):
            pass

    @app.websocket("/events/{rid}")
    async def events(ws: WebSocket, rid: str) -> None:
        await ws.accept()
        rec = live.get(rid)
        try:
            if rec is None:
                for event in read_events(data / "recordings" / rid / "events.jsonl"):
                    await ws.send_text(json.dumps(event, ensure_ascii=False))
            else:
                backlog, queue = rec.log.watch()
                try:
                    for line in backlog:
                        await ws.send_text(line)
                    while (line := await queue.get()) is not None:
                        await ws.send_text(line)
                finally:
                    rec.log.unwatch(queue)
            await ws.close()
        except WebSocketDisconnect:
            pass

    @app.get("/api/recordings")
    def recordings() -> list[dict[str, Any]]:
        root = data / "recordings"
        if not root.exists():
            return []
        metas = [json.loads(p.read_text()) for p in root.glob("*/meta.json")]
        for meta in metas:
            meta["live"] = meta["id"] in live
        return sorted(metas, key=lambda m: m["started"], reverse=True)

    @app.get("/api/recordings/{rid}/events")
    def recording_events(rid: str) -> list[dict[str, Any]]:
        path = data / "recordings" / rid / "events.jsonl"
        if not path.exists():
            raise HTTPException(404, "no such recording")
        return read_events(path)

    return app


app = create_app()
