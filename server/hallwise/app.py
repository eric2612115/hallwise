"""HTTP and WebSocket entry points.

    /ingest                     the badge streams here: a JSON hello, then binary PCM frames and JSON pose messages
    /events/{recording}         watch a recording: everything so far, then live events until it ends
    /api/recordings             recordings, newest first
    /api/recordings/{id}/events one recording's event log
    /api/recordings/{id}/ask    a typed question about the recording, answered by Muse Spark
    /api/people                 everyone met across recordings, with each encounter and promise
    /api/recordings/{id}/photo  a photo of the people around the badge; SAM 3.1 finds the faces, Muse Spark says who is who
    /ask/{recording}            a spoken question: PCM in, Muse Voice Transcribe, then the same answer

Run: ./run.sh (reads ../.env; HALLWISE_ASR=fake runs offline). Port 8790.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ask import answer, latest_moves
from .asr import MetaRealtimeAsr, make_asr_factory
from .events import fold_record, read_events
from .extract import Extractor, SparkClient
from .people import people_index
from .photo import match_photo, save_photo
from .sam import SamClient
from .events import EventLog
from .recording import Hello, Recording


class Question(BaseModel):
    question: str
    history: list[dict[str, str]] = []
    keywords: list[str] = []


class Photo(BaseModel):
    image_b64: str
    mime: str = "image/jpeg"
    people: list[dict[str, Any]] = []  # key, name, company, bearing
    hint: str = ""


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
    key = os.environ.get("MODEL_API_KEY")
    spark = SparkClient(key, model=os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")) if key else None
    sam = SamClient(key) if key and os.environ.get("HALLWISE_SAM", "on") != "off" else None  # off: Spark finds faces

    def record_of(rid: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        """The record, the drafted moves and the meta of a recording, live or finished."""
        rec = live.get(rid)
        if rec is not None:
            events = rec.log.events()
            meta = json.loads((data / "recordings" / rid / "meta.json").read_text())
        else:
            path = data / "recordings" / rid / "events.jsonl"
            if not path.exists():
                raise HTTPException(404, "no such recording")
            events = read_events(path)
            meta = json.loads((data / "recordings" / rid / "meta.json").read_text())
        return fold_record(events), latest_moves(events), meta

    async def ask(rid: str, question: str, history: list[dict[str, str]], keywords: list[str]) -> dict[str, Any]:
        if spark is None:
            raise HTTPException(503, "MODEL_API_KEY is not set")
        record, moves, meta = record_of(rid)
        result = await answer(
            spark, record, moves,
            owner_name=meta.get("owner_name", ""), owner_company=meta.get("owner_company", ""),
            event=meta.get("event", ""), venue=meta.get("venue", ""),
            keywords=keywords or meta.get("keywords") or [], history=history, question=question,
        )
        return {"question": question, **result}

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
                    elif control.get("type") == "ask_start":
                        await rec.start_ask()
                    elif control.get("type") == "ask_end":
                        question = await rec.end_ask()
                        if not question:
                            result: dict[str, Any] = {"question": "", "answer": "", "actions": [], "error": "nothing heard"}
                        else:
                            try:
                                result = await ask(rec.id, question, control.get("history") or [], hello.keywords or [])
                            except HTTPException as err:
                                result = {"question": question, "answer": "", "actions": [], "error": str(err.detail)}
                        rec.log.emit("ask_answer", rec.now_ms, question=question, answer=result.get("answer", ""))
                        await ws.send_json({"type": "ask_answer", **result})
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

    @app.post("/api/recordings/{rid}/photo")
    async def photo(rid: str, body: Photo) -> dict[str, Any]:
        """A photo of the people around the badge: SAM finds the faces (Spark when SAM cannot), Spark says which
        face is which; the original is kept."""
        if spark is None:
            raise HTTPException(503, "MODEL_API_KEY is not set")
        root = data / "recordings" / rid
        if not (root / "meta.json").exists():
            raise HTTPException(404, "no such recording")
        result = await match_photo(spark, body.image_b64, body.mime, body.people, body.hint, sam=sam)
        name = save_photo(root, body.image_b64, body.mime)
        rec = live.get(rid)
        event = {"file": name, "faces": result["faces"], "finder": result["finder"]}
        if rec is not None:
            rec.log.emit("photo", rec.now_ms, **event)
        else:
            log = EventLog(root / "events.jsonl")
            last = max((e.get("t_ms", 0) for e in read_events(root / "events.jsonl")), default=0)
            log.emit("photo", last, **event)
            log.close()
        return {"file": name, **result}

    @app.get("/api/people")
    def people(exclude: str | None = None) -> list[dict[str, Any]]:
        """Everyone the owner has met, across recordings, newest encounter first."""
        return people_index(data, exclude)

    @app.get("/api/recordings/{rid}/events")
    def recording_events(rid: str) -> list[dict[str, Any]]:
        path = data / "recordings" / rid / "events.jsonl"
        if not path.exists():
            raise HTTPException(404, "no such recording")
        return read_events(path)

    @app.post("/api/recordings/{rid}/ask")
    async def ask_typed(rid: str, q: Question) -> dict[str, Any]:
        return await ask(rid, q.question, q.history, q.keywords)

    @app.websocket("/ask/{rid}")
    async def ask_spoken(ws: WebSocket, rid: str) -> None:
        """A spoken question: JSON hello {sample_rate, language_bias?, keywords?, history?}, then 16-bit mono PCM
        frames, then {"type": "end"}. Partials come back as they are heard, then the question and the answer."""
        await ws.accept()
        if key is None:
            await ws.close(code=1011, reason="MODEL_API_KEY is not set")
            return
        try:
            hello = json.loads(await ws.receive_text())
        except (json.JSONDecodeError, WebSocketDisconnect):
            return
        turns: list[str] = []
        pending: list[str] = []

        def sink(type: str, t_ms: int, **d: Any) -> None:
            if type == "partial":
                pending.append(d.get("text", ""))
            elif type == "turn" and d.get("text"):
                turns.append(d["text"])

        asr = MetaRealtimeAsr(
            key, sink, rate=int(hello.get("sample_rate", 16_000)),
            language_bias=hello.get("language_bias"), keywords=hello.get("keywords") or None,
        )
        try:
            await asr.start()
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("bytes"):
                    await asr.send(msg["bytes"])
                    if pending:
                        await ws.send_json({"type": "partial", "text": pending[-1]})
                        pending.clear()
                elif msg.get("text") and json.loads(msg["text"]).get("type") == "end":
                    break
            await asr.finish()
            question = " ".join(turns).strip()
            await ws.send_json({"type": "question", "text": question})
            if not question:
                await ws.send_json({"type": "answer", "answer": "", "actions": [], "error": "nothing heard"})
            else:
                try:
                    result = await ask(rid, question, hello.get("history") or [], hello.get("keywords") or [])
                except HTTPException as err:
                    result = {"answer": "", "actions": [], "error": err.detail}
                await ws.send_json({"type": "answer", **result})
            await ws.close()
        except WebSocketDisconnect:
            pass

    # The built dashboard (apps/web/dist), when it exists, so one server gives judges one URL.
    dist = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
