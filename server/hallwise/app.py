"""HTTP and WebSocket entry points.

    /ingest                     the badge streams here: a JSON hello, then binary PCM frames and JSON pose messages
    /events/{recording}         watch a recording: everything so far, then live events until it ends;
                                a finished one with ?pace=1 (2 = twice as fast) and ?from_ms= plays at its own pace
    /api/recordings             recordings, newest first
    /api/recordings/{id}/events one recording's event log
    /api/recordings/{id}/ask    a typed question about the recording, answered by Muse Spark
    /api/people                 everyone met across recordings, with each encounter and promise
    /api/recordings/{id}/photo  a photo of the people around the badge; SAM 3.1 finds the faces, Muse Spark says who is who
    /api/people/{key}/face      a person's face, kept across evenings (POST a JPEG or PNG, GET a JPEG back)
    /api/report/run?recording=  the morning report: research, hooks, follow-ups (cached for an hour; force=1 rebuilds)
    /api/report/latest          the newest morning report; /api/report/{id} one recording's
    /ask/{recording}            a spoken question: PCM in, Muse Voice Transcribe, then the same answer
    /login                      POST the server key once (form field or JSON "token"); a cookie keeps the dashboard in

Every route and socket needs the server key, HALLWISE_TOKEN: `Authorization: Bearer <key>`, or the dashboard's
cookie (guard.py, which also checks Host, Origin and body sizes). With the key, the limits still hold, so a stuck
or stolen client cannot run up the bill or fill the disk: MAX_RECORDINGS recordings and MAX_ASKS questions at a
time, six hours of audio per recording, a minute per spoken question, a forced report rebuild once a minute,
PHOTOS_PER_MINUTE photos a minute, and a cap on every body. Ids are checked (ids.py) before any file or paid call.

Run: ./run.sh (reads ../.env and makes the key there if it is missing; HALLWISE_ASR=fake runs offline). Port 8790.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from contextlib import aclosing
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ask import answer, latest_moves
from .asr import MetaRealtimeAsr, make_asr_factory
from .events import MAX_PACE, MIN_PACE, EventLog, fold_record, read_events, replay
from .extract import Extractor, SparkClient
from .guard import (
    COOKIE_MAX_AGE_S, DEFAULT_BODY_MAX, TOKEN_COOKIE, Guard, Hosts, Slots, Window, configured_hosts, matches,
    refuse_socket, same_origin, server_token,
)
from .ids import is_key, is_rid
from .images import FORMATS, BadImage, face_jpeg, photo_bytes
from .people import match, people_index
from .places import parse_place
from .photo import match_photo, save_photo
from .recording import Hello, Recording
from .report import Reports, report_delay_s
from .research import Researcher
from .sam import SamClient

MAX_RECORDINGS = 2  # badge sessions at once: the phone's, and one reconnecting while the old one still closes
MAX_ASKS = 2  # questions being heard or answered at once, spoken (/ask) or typed (/api/recordings/{id}/ask)
MAX_RECORDING_MS = 6 * 3600 * 1000  # audio per recording; the recording ends there, as if Stop was pressed
MAX_ASK_MS = 60_000  # a spoken question is cut here and answered
FORCE_EVERY_S = 60.0  # /api/report/run?force=1 at most this often, across recordings
PHOTOS_PER_MINUTE = 6
PHOTO_AFTER_S = 6 * 3600  # how long after a recording ends it still takes photos (see photo())
PHOTO_MAX_BYTES = 12_000_000  # the decoded image
PHOTO_B64_MAX = 4 * ((PHOTO_MAX_BYTES + 2) // 3)
PHOTO_BODY_MAX = PHOTO_B64_MAX + 256 * 1024  # with the people and the hint
FACE_MAX_BYTES = 5_000_000
LOGIN_FAILURES_PER_MINUTE = 10


class Question(BaseModel):
    question: str = Field(max_length=4000)
    history: list[dict[str, str]] = Field(default=[], max_length=50)
    keywords: list[str] = Field(default=[], max_length=200)


class Photo(BaseModel):
    image_b64: str = Field(max_length=PHOTO_B64_MAX)
    mime: Literal["image/jpeg", "image/png"] = "image/jpeg"
    people: list[dict[str, Any]] = Field(default=[], max_length=60)  # key, name, company, bearing
    hint: str = Field(default="", max_length=2000)


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


def body_cap(method: str, path: str) -> int:
    """The most a request body may be, by route, checked from Content-Length before it is read."""
    if method == "POST" and path.startswith("/api/people/") and path.endswith("/face"):
        return FACE_MAX_BYTES
    if method == "POST" and path.startswith("/api/recordings/") and path.endswith("/photo"):
        return PHOTO_BODY_MAX
    return DEFAULT_BODY_MAX


def too_soon(wait: float, what: str) -> HTTPException:
    return HTTPException(429, f"{what}; try again in {math.ceil(wait)} s", headers={"Retry-After": str(math.ceil(wait))})


def create_app(
    data_dir: Path | None = None,
    asr: str | None = None,
    make_extractor: Callable[[Hello], Extractor | None] | None | str = "env",
    reports: Reports | None = None,
    hosts: list[str] | None = None,
    web: Path | None = None,
) -> FastAPI:
    token = server_token()  # refuses to build the app without HALLWISE_TOKEN, unless HALLWISE_INSECURE=1
    data = Path(data_dir or os.environ.get("HALLWISE_DATA", "data"))
    make_asr = make_asr_factory(asr or os.environ.get("HALLWISE_ASR", "fake"))
    if make_extractor == "env":
        make_extractor = spark_extractor_factory()
    app = FastAPI(title="Hallwise")
    app.add_middleware(Guard, token=token, body_cap=body_cap)
    app.add_middleware(Hosts, fixed=hosts if hosts is not None else configured_hosts())  # outermost: Host first
    live: dict[str, Recording] = {}
    key = os.environ.get("MODEL_API_KEY")
    spark = SparkClient(key, model=os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")) if key else None
    sam = SamClient(key) if key and os.environ.get("HALLWISE_SAM", "on") != "off" else None  # off: Spark finds faces
    if reports is None:
        hooks_model = os.environ.get("HALLWISE_SPARK_MODEL", "muse-spark-1.3")
        hooks_effort = os.environ.get("HALLWISE_HOOKS_EFFORT", "medium")
        reports = Reports(
            data,
            lambda: SparkClient(key, model=hooks_model, effort=hooks_effort, timeout=180) if key else None,
            Researcher.from_env(data),
        )
    auto_report = report_delay_s() if key else None
    background: set[asyncio.Task[None]] = set()  # the automatic report runs, kept until they finish
    recording_slots, ask_slots = Slots(MAX_RECORDINGS), Slots(MAX_ASKS)
    forced, photos, login_failures = Window(1, FORCE_EVERY_S), Window(PHOTOS_PER_MINUTE, 60), Window(LOGIN_FAILURES_PER_MINUTE, 60)
    max_recording_ms, max_ask_ms = MAX_RECORDING_MS, MAX_ASK_MS

    def folder(rid: str) -> Path:
        """A recording's folder, for a string that is a recording id (ids.py); 404 for anything else."""
        if not is_rid(rid):
            raise HTTPException(404, "no such recording")
        return data / "recordings" / rid

    def exists(rid: str) -> bool:
        """Live, or finished with its log and meta on disk."""
        if not is_rid(rid):
            return False
        root = data / "recordings" / rid
        return rid in live or ((root / "events.jsonl").exists() and (root / "meta.json").exists())

    def record_of(rid: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        """The record, the drafted moves and the meta of a recording, live or finished."""
        root = folder(rid)
        rec = live.get(rid)
        if rec is not None:
            events = rec.log.events()
        else:
            if not exists(rid):
                raise HTTPException(404, "no such recording")
            events = read_events(root / "events.jsonl")
        meta = json.loads((root / "meta.json").read_text())
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

    @app.post("/login")
    async def login(request: Request) -> Response:
        """The dashboard's way in: the server key once, as a form field `token` (back to / with a 303) or as JSON
        {"token": ...}. Back comes an HttpOnly, SameSite=Strict cookie that the API and the sockets take in place
        of the header. Same-origin only, and ten wrong keys a minute at most."""
        if not same_origin(request.headers):
            return JSONResponse({"error": "forbidden origin"}, status_code=403)
        if wait := login_failures.wait():
            return JSONResponse({"error": "too many wrong keys"}, status_code=429, headers={"Retry-After": str(math.ceil(wait))})
        raw = await request.body()
        is_json = request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"
        given = ""
        try:
            if is_json:
                body = json.loads(raw or b"{}")
                given = str(body.get("token", "")) if isinstance(body, dict) else ""
            else:
                given = parse_qs(raw.decode("utf-8", "replace")).get("token", [""])[0]
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        if token is not None and not matches(given.strip(), token):
            login_failures.take()
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        out: Response = JSONResponse({"ok": True}) if is_json else RedirectResponse("/", status_code=303)
        if token is not None:
            out.set_cookie(TOKEN_COOKIE, token, max_age=COOKIE_MAX_AGE_S, path="/", httponly=True, samesite="strict",
                           secure=request.url.scheme == "https")
        return out

    @app.post("/logout")
    def logout() -> Response:
        out = JSONResponse({"ok": True})
        out.delete_cookie(TOKEN_COOKIE, path="/", httponly=True, samesite="strict")
        return out

    @app.websocket("/ingest")
    async def ingest(ws: WebSocket) -> None:
        if not recording_slots.take():
            await refuse_socket(ws, 429, f"{MAX_RECORDINGS} recordings are already running")
            return
        try:
            await ingest_session(ws)
        finally:
            recording_slots.give()

    async def ingest_session(ws: WebSocket) -> None:
        await ws.accept()
        try:
            hello = Hello.parse(json.loads(await ws.receive_text()))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
            await ws.close(code=1008, reason=str(err)[:120])
            return
        except WebSocketDisconnect:
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
                    if rec.now_ms >= max_recording_ms:  # six hours: the recording ends as if Stop was pressed
                        rec.log.emit("recording_limit", rec.now_ms, max_ms=max_recording_ms)
                        break
                    await rec.on_audio(msg["bytes"])
                elif msg.get("text"):
                    try:
                        control = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(control, dict):
                        continue
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
            if auto_report is not None:
                task = asyncio.get_running_loop().create_task(reports.later(rec.id, auto_report))
                background.add(task)
                task.add_done_callback(background.discard)
        try:
            await ws.send_json({"type": "closed", "recording": rec.id})
            await ws.close()
        except (WebSocketDisconnect, RuntimeError):
            pass

    @app.websocket("/events/{rid}")
    async def events(
        ws: WebSocket, rid: str, pace: float | None = Query(None, ge=MIN_PACE, le=MAX_PACE), from_ms: int = Query(0, ge=0)
    ) -> None:
        """A live recording: the backlog, then events as they happen. A finished one: every event at once, or
        with `pace` (0.1 to 100; 2 is twice as fast), at its own pace from `from_ms` on (no later than its end),
        with replay_clock ticks through the silences (see events.replay). A live recording ignores pace and
        from_ms. An unknown id is turned away before the socket opens."""
        rec = live.get(rid) if is_rid(rid) else None
        log: list[dict[str, Any]] = []
        if rec is None:
            if not is_rid(rid) or not (data / "recordings" / rid / "events.jsonl").exists():
                await refuse_socket(ws, 404, "no such recording")
                return
            log = read_events(data / "recordings" / rid / "events.jsonl")
            if pace is not None and from_ms > max((int(e.get("t_ms", 0)) for e in log), default=0):
                await refuse_socket(ws, 400, "from_ms is past the end of the recording")
                return
        await ws.accept()
        try:
            if rec is None and pace is not None:
                async with aclosing(replay(log, pace, from_ms)) as lines:
                    async for line in lines:
                        await ws.send_text(line)
            elif rec is None:
                for event in log:
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
            meta["place"] = parse_place(meta.get("place"), name=meta.get("venue", ""))
        return sorted(metas, key=lambda m: m["started"], reverse=True)

    @app.post("/api/recordings/{rid}/photo")
    async def photo(rid: str, body: Photo) -> dict[str, Any]:
        """A photo of the people around the badge: SAM finds the faces (Spark when SAM cannot), Spark says which
        face is which; the original is kept.

        Which recordings take a photo: a live one, and a finished one for PHOTO_AFTER_S (six hours) after its last
        event, so the group photo taken just after Stop still lands on the evening it belongs to; an older one
        answers 409, so nobody adds photos to last week's log. Only a JPEG or PNG that decodes, PHOTO_MAX_BYTES at
        most, and PHOTOS_PER_MINUTE a minute (429 past that), all checked before SAM or Spark is called."""
        if spark is None:
            raise HTTPException(503, "MODEL_API_KEY is not set")
        root = folder(rid)
        if not (root / "meta.json").exists():
            raise HTTPException(404, "no such recording")
        rec = live.get(rid)
        if rec is None:
            meta = json.loads((root / "meta.json").read_text())
            last = max((int(e.get("t_ms", 0)) for e in read_events(root / "events.jsonl")), default=0)
            if time.time() - (float(meta.get("started", 0) or 0) + last / 1000) > PHOTO_AFTER_S:
                raise HTTPException(409, "this recording ended too long ago to take photos")
        try:
            await asyncio.to_thread(photo_bytes, body.image_b64, body.mime, PHOTO_MAX_BYTES)
        except BadImage as err:
            raise HTTPException(err.status, str(err))
        if wait := photos.take():
            raise too_soon(wait, f"at most {PHOTOS_PER_MINUTE} photos a minute")
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

    @app.post("/api/people/{key}/face")
    async def put_face(key: str, request: Request) -> dict[str, Any]:
        """Keep a face for a person across evenings, under their people-index key. The body is the image itself,
        Content-Type image/jpeg or image/png, FACE_MAX_BYTES at most (the guard refuses a larger Content-Length
        before reading it), and must decode; it is kept re-encoded as a JPEG, without metadata."""
        if not is_key(key):
            raise HTTPException(400, "not a person key")
        mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if mime not in FORMATS:
            raise HTTPException(415, "a face is a JPEG or a PNG")
        raw = await request.body()
        if len(raw) > FACE_MAX_BYTES:
            raise HTTPException(413, "face too large")
        try:
            jpeg = await asyncio.to_thread(face_jpeg, raw, mime)
        except BadImage as err:
            raise HTTPException(err.status, str(err))
        faces = data / "faces"
        faces.mkdir(parents=True, exist_ok=True)
        tmp = faces / f"{key}.tmp"
        tmp.write_bytes(jpeg)
        tmp.replace(faces / f"{key}.jpg")
        return {"key": key, "bytes": len(jpeg)}

    @app.get("/api/people/{key}/face")
    def get_face(key: str, name: str = "", company: str = "") -> FileResponse:
        """A person's face; with name and company, the face of whoever the index matches them to."""
        if not is_key(key):
            raise HTTPException(400, "not a person key")
        path = data / "faces" / f"{key}.jpg"
        if not path.exists() and name:
            entry = match(people_index(data), name, company)
            if entry is not None and is_key(entry["key"]):
                path = data / "faces" / f"{entry['key']}.jpg"
        if not path.exists():
            raise HTTPException(404, "no face for this person")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/report/run")
    async def run_report(recording: str, force: int = 0) -> dict[str, Any]:
        """Research, hooks, the report. Within an hour of the last build the stored one comes back; force=1
        rebuilds, at most once every FORCE_EVERY_S across recordings (429 with Retry-After before that)."""
        if not is_rid(recording) or not (data / "recordings" / recording / "meta.json").exists():
            raise HTTPException(404, "no such recording")
        if force and (wait := forced.take()):
            raise too_soon(wait, "a forced rebuild ran less than a minute ago")
        try:
            return await reports.run(recording, force=bool(force))
        except KeyError:
            raise HTTPException(404, "no such recording")

    @app.get("/api/report/latest")
    def latest_report() -> dict[str, Any]:
        report = reports.latest()
        if report is None:
            raise HTTPException(404, "no report yet")
        return report

    @app.get("/api/report/{rid}")
    def get_report(rid: str) -> dict[str, Any]:
        report = reports.get(rid)
        if report is None:
            raise HTTPException(404, "no report for this recording")
        return report

    @app.get("/api/recordings/{rid}/events")
    def recording_events(rid: str) -> list[dict[str, Any]]:
        path = folder(rid) / "events.jsonl"
        if not path.exists():
            raise HTTPException(404, "no such recording")
        return read_events(path)

    @app.post("/api/recordings/{rid}/ask")
    async def ask_typed(rid: str, q: Question) -> dict[str, Any]:
        if not exists(rid):
            raise HTTPException(404, "no such recording")
        if not ask_slots.take():
            raise HTTPException(429, f"{MAX_ASKS} questions are already being answered")
        try:
            return await ask(rid, q.question, q.history, q.keywords)
        finally:
            ask_slots.give()

    @app.websocket("/ask/{rid}")
    async def ask_spoken(ws: WebSocket, rid: str) -> None:
        """A spoken question: JSON hello {sample_rate, language_bias?, keywords?, history?}, then 16-bit mono PCM
        frames, then {"type": "end"}. Partials come back as they are heard, then the question and the answer.
        The recording must exist and a question slot be free before the socket opens and the transcriber starts;
        the question is cut at MAX_ASK_MS of audio."""
        if not exists(rid):
            await refuse_socket(ws, 404, "no such recording")
            return
        if key is None:
            await ws.accept()
            await ws.close(code=1011, reason="MODEL_API_KEY is not set")
            return
        if not ask_slots.take():
            await refuse_socket(ws, 429, f"{MAX_ASKS} questions are already being answered")
            return
        try:
            await ask_session(ws, rid, key)
        finally:
            ask_slots.give()

    async def ask_session(ws: WebSocket, rid: str, key: str) -> None:
        await ws.accept()
        try:
            hello = json.loads(await ws.receive_text())
            rate = int(hello.get("sample_rate", 16_000))
            if not 8_000 <= rate <= 96_000:
                raise ValueError(f"unsupported sample rate {rate}")
        except WebSocketDisconnect:
            return
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as err:
            await ws.close(code=1008, reason=str(err)[:120])
            return
        turns: list[str] = []
        pending: list[str] = []

        def sink(type: str, t_ms: int, **d: Any) -> None:
            if type == "partial":
                pending.append(d.get("text", ""))
            elif type == "turn" and d.get("text"):
                turns.append(d["text"])

        asr = MetaRealtimeAsr(
            key, sink, rate=rate,
            language_bias=hello.get("language_bias"), keywords=hello.get("keywords") or None,
        )
        budget = rate * 2 * max_ask_ms // 1000  # bytes of 16-bit mono audio in MAX_ASK_MS
        try:
            await asr.start()
            heard = 0
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("bytes"):
                    chunk = msg["bytes"][: max(0, budget - heard)]
                    heard += len(chunk)
                    if chunk:
                        await asr.send(chunk)
                    if pending:
                        await ws.send_json({"type": "partial", "text": pending[-1]})
                        pending.clear()
                    if heard >= budget:
                        break
                elif msg.get("text"):
                    try:
                        done = json.loads(msg["text"]).get("type") == "end"
                    except (json.JSONDecodeError, AttributeError):
                        done = False
                    if done:
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

    # The built dashboard (apps/web/dist), when it exists, so one server gives judges one URL. Its shell loads
    # without the key (guard.py); everything it shows comes from the API, which needs it.
    dist = web or Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


def __getattr__(name: str) -> Any:
    """`uvicorn hallwise.app:app` builds the app on first use, so importing this module needs no key; building
    it without HALLWISE_TOKEN (and without HALLWISE_INSECURE=1) stops the server from starting."""
    if name == "app":
        globals()["app"] = built = create_app()
        return built
    raise AttributeError(name)
