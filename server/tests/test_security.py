"""The security review's server findings, each pinned where the request arrives: the key on every route and socket
(C1), no paid call before the id checks out and limits on what costs money (H1), no planted transcript or face
(H2), no replay that spins (H3), Host and Origin (M1), size caps (M2), the export's people snapshot (M4), ids that
become paths (L3), and run.sh: the key, umask and the bind address (L5)."""

import asyncio
import base64
import json
import shutil
import stat
import subprocess
import sys
import time
import wave
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from auth import AUTH, TOKEN
from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient
from PIL import Image
from pictures import noisy_jpeg, picture, picture_b64
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect
from week import week

import hallwise.app as app_module
from hallwise import guard
from hallwise.app import create_app
from hallwise.events import replay
from hallwise.ids import is_key, is_rid

SERVER = Path(__file__).resolve().parents[1]
RATE = 24_000
HELLO = json.dumps({"sample_rate": RATE, "channels": 1, "layout": "mono"})


def finished(data: Path, rid: str = "r1", started: float | None = None) -> Path:
    """A finished recording on disk; started now unless told otherwise."""
    root = data / "recordings" / rid
    root.mkdir(parents=True)
    (root / "meta.json").write_text(json.dumps({"id": rid, "event": "Dinner", "started": time.time() if started is None else started}))
    events = [{"type": "recording_start", "t_ms": 0}, {"type": "turn", "t_ms": 500, "turn": 1, "text": "Hi, I'm Sarah."},
              {"type": "recording_end", "t_ms": 1500}]
    (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return root


def app_for(data: Path, **kw):
    return create_app(data, asr="fake", make_extractor=None, **kw)


def refused(client: TestClient, url: str, **kw) -> WebSocketDenialResponse:
    """The HTTP answer to a socket that was turned away before it opened."""
    with pytest.raises(WebSocketDenialResponse) as info:
        with client.websocket_connect(url, **kw):
            pass
    return info.value


def asgi(app, method: str, path: str, headers: list[tuple[bytes, bytes]] = (), key: bool = True, body: bytes | None = None):
    """One HTTP request straight into the app, with `path` exactly as given (no client tidies up `..`). Without
    `body`, reading the body fails the test. Returns (status, JSON body)."""
    sent: list[dict] = []

    async def receive():
        if body is None:
            raise AssertionError("the body was read")
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    auth = [(b"authorization", f"Bearer {TOKEN}".encode())] if key else []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "headers": [(b"host", b"testserver"), *auth, *headers], "client": ("127.0.0.1", 50000), "server": ("testserver", 80)}
    asyncio.run(app(scope, receive, send))
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return sent[0]["status"], json.loads(body or b"null")


class SilentMeta:
    """Stands in for Muse Voice Transcribe: counts sessions started and audio sent, and hears nothing."""

    started: list[str] = []
    sent: list[int] = []

    def __init__(self, key, sink, **kw):
        pass

    async def start(self):
        SilentMeta.started.append("start")

    async def send(self, pcm):
        SilentMeta.sent.append(len(pcm))

    async def finish(self):
        pass


@pytest.fixture
def silent_meta(monkeypatch):
    """A dummy MODEL_API_KEY with every paid client stubbed or off: nothing here leaves the machine."""
    SilentMeta.started, SilentMeta.sent = [], []
    monkeypatch.setenv("MODEL_API_KEY", "dummy-key")
    monkeypatch.setenv("HALLWISE_REPORT", "off")
    monkeypatch.setenv("HALLWISE_RESEARCH", "off")
    monkeypatch.setenv("HALLWISE_SECOND", "off")
    monkeypatch.setenv("HALLWISE_SAM", "off")
    monkeypatch.setattr(app_module, "MetaRealtimeAsr", SilentMeta)
    import hallwise.asr as asr_module

    monkeypatch.setattr(asr_module, "MetaRealtimeAsr", SilentMeta)
    return SilentMeta


# C1: the key ---------------------------------------------------------------------------------------------------


def test_every_route_and_socket_needs_the_key(tmp_path):
    finished(tmp_path)
    app = app_for(tmp_path)
    anon = TestClient(app)
    wrong = TestClient(app, headers={"Authorization": "Bearer not-the-key-not-the-key"}, cookies={"hallwise_token": "nope-nope-nope-nope"})
    checked = []
    for route in app.routes:
        path = getattr(route, "path", "").replace("{rid}", "r1").replace("{key}", "kenji")
        if isinstance(route, APIRoute) and route.path not in ("/login", "/logout"):
            for method in route.methods:
                for client in (anon, wrong):
                    r = client.request(method, path, params={"recording": "r1"})
                    assert (r.status_code, r.json()) == (401, {"error": "unauthorized"}), (method, path)
                checked.append(path)
        elif isinstance(route, APIWebSocketRoute):
            for client in (anon, wrong):
                denial = refused(client, path)
                assert (denial.status_code, denial.json()) == (401, {"error": "unauthorized"}), path
            checked.append(path)
    assert len(checked) == 16  # every API route (the three correction routes too) and all three sockets
    assert TestClient(app, headers=AUTH).get("/api/recordings").status_code == 200


def test_without_denial_responses_a_socket_is_accepted_and_closed_with_4401():
    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "websocket", "path": "/ingest", "query_string": b"", "headers": [(b"host", b"testserver")], "extensions": {}}
    asyncio.run(guard.Guard(None, token=TOKEN, body_cap=lambda m, p: 0)(scope, receive, send))
    assert [m["type"] for m in sent] == ["websocket.accept", "websocket.close"] and sent[1]["code"] == 4401


def test_only_the_dashboard_shell_loads_without_the_key(tmp_path):
    web = tmp_path / "dist"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Hallwise</title>")
    (web / "assets" / "app.js").write_text("console.log('shell')")
    (web / "notes.txt").write_text("not part of the shell")
    anon = TestClient(app_for(tmp_path / "data", web=web))
    assert anon.get("/").status_code == 200 and "Hallwise" in anon.get("/").text
    assert anon.get("/assets/app.js").status_code == 200
    assert anon.get("/notes.txt").status_code == 401
    assert anon.get("/api/recordings").status_code == 401


def test_the_dashboard_logs_in_once_and_its_cookie_opens_the_api_and_the_sockets(tmp_path):
    finished(tmp_path)
    browser = TestClient(app_for(tmp_path))
    assert browser.post("/login", json={"token": "wrong-key-wrong-key"}).status_code == 401
    assert browser.get("/api/recordings").status_code == 401
    r = browser.post("/login", json={"token": TOKEN})
    cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 200 and "hallwise_token=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert browser.get("/api/recordings").status_code == 200
    with browser.websocket_connect("/events/r1", headers={"Origin": "http://testserver"}) as ws:
        assert ws.receive_json()["type"] == "recording_start"
    # A plain form post works too, and lands back on the dashboard.
    form = TestClient(app_for(tmp_path)).post("/login", data={"token": TOKEN}, follow_redirects=False)
    assert form.status_code == 303 and form.headers["location"] == "/" and "hallwise_token=" in form.headers["set-cookie"]
    browser.post("/logout")
    assert browser.get("/api/recordings").status_code == 401


def test_the_cookie_does_not_open_the_server_to_another_origin(tmp_path):
    finished(tmp_path)
    browser = TestClient(app_for(tmp_path))
    browser.post("/login", json={"token": TOKEN})
    for origin in ("http://evil.example", "http://testserver:8000", "null"):
        assert browser.post("/login", json={"token": TOKEN}, headers={"Origin": origin}).status_code == 403
        r = browser.post("/api/report/run", params={"recording": "r1", "force": 1}, headers={"Origin": origin})
        assert (r.status_code, r.json()) == (403, {"error": "forbidden origin"})
    # the dashboard's own origin gets through to the route (no MODEL_API_KEY here, so 503 from the route itself)
    assert browser.post("/api/recordings/r1/ask", json={"question": "who?"}, headers={"Origin": "http://testserver"}).status_code == 503


def test_ten_wrong_keys_a_minute_at_most(tmp_path):
    browser = TestClient(app_for(tmp_path))
    codes = [browser.post("/login", json={"token": f"guess-number-{i:04d}"}).status_code for i in range(11)]
    assert codes == [401] * 10 + [429]
    assert browser.post("/login", json={"token": TOKEN}).status_code == 429  # even the right one waits out the minute


def test_the_server_does_not_start_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("HALLWISE_TOKEN")
    with pytest.raises(RuntimeError, match="HALLWISE_TOKEN"):
        app_for(tmp_path)
    assert "app" not in vars(app_module)  # importing the module built nothing
    with pytest.raises(RuntimeError, match="HALLWISE_TOKEN"):
        app_module.app  # what `uvicorn hallwise.app:app` does
    monkeypatch.setenv("HALLWISE_TOKEN", "short")
    with pytest.raises(RuntimeError, match="shorter"):
        app_for(tmp_path)
    monkeypatch.delenv("HALLWISE_TOKEN")
    monkeypatch.setenv("HALLWISE_INSECURE", "1")
    assert TestClient(app_for(tmp_path)).get("/api/recordings").status_code == 200


def test_scripts_find_the_key_in_the_repos_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HALLWISE_TOKEN")
    env = tmp_path / ".env"
    env.write_text("MODEL_API_KEY=dummy\nHALLWISE_TOKEN=old-old-old-old-old\nexport HALLWISE_TOKEN='from-the-file-0123456789'\n")
    assert guard.client_token(env) == "from-the-file-0123456789"
    monkeypatch.setenv("HALLWISE_TOKEN", "from-the-environment-0123")
    assert guard.client_token(env) == "from-the-environment-0123"


# H1: no paid call before the id checks out; limits --------------------------------------------------------------


def test_a_spoken_question_about_an_unknown_recording_never_starts_the_transcriber(tmp_path, silent_meta):
    finished(tmp_path)
    client = TestClient(app_for(tmp_path), headers=AUTH)
    for rid in ("nope", "%2e%2e", "r1%0a", "a.b"):
        assert refused(client, f"/ask/{rid}").status_code == 404, rid
    assert silent_meta.started == []


def test_two_questions_at_a_time_and_a_spoken_one_is_cut_at_a_minute(tmp_path, silent_meta, monkeypatch):
    finished(tmp_path)
    monkeypatch.setattr(app_module, "MAX_ASK_MS", 100)
    with TestClient(app_for(tmp_path), headers=AUTH) as client:
        with client.websocket_connect("/ask/r1") as a, client.websocket_connect("/ask/r1") as b:
            for ws in (a, b):
                ws.send_text(json.dumps({"sample_rate": 16_000}))
            assert refused(client, "/ask/r1").status_code == 429
            assert client.post("/api/recordings/r1/ask", json={"question": "who?"}).status_code == 429
            assert silent_meta.started == ["start", "start"]
        with client.websocket_connect("/ask/r1") as c:  # both closed: a slot is free again
            c.send_text(json.dumps({"sample_rate": 16_000}))
            for _ in range(10):
                c.send_bytes(b"\0" * 1000)  # 31.25 ms each: the cap falls inside the fourth
            assert c.receive_json() == {"type": "question", "text": ""}  # the server stopped listening by itself
    assert sum(silent_meta.sent) == 16_000 * 2 // 10  # 100 ms of 16-bit mono reached the transcriber, no more


def test_two_recordings_at_a_time(tmp_path):
    with TestClient(app_for(tmp_path), headers=AUTH) as client:
        with client.websocket_connect("/ingest") as a, client.websocket_connect("/ingest") as b:
            for ws in (a, b):
                ws.send_text(HELLO)
                assert ws.receive_json()["type"] == "ready"
            assert refused(client, "/ingest").status_code == 429
            for ws in (a, b):
                ws.send_text(json.dumps({"type": "end"}))
                assert ws.receive_json()["type"] == "closed"
        with client.websocket_connect("/ingest") as c:
            c.send_text(HELLO)
            assert c.receive_json()["type"] == "ready"


def test_a_forced_report_rebuild_runs_at_most_once_a_minute(tmp_path):
    from test_report import make_app

    week(tmp_path, time.time())
    calls: list[str] = []
    client = make_app(tmp_path, calls)
    assert client.post("/api/report/run", params={"recording": "c-tonight", "force": 1}).status_code == 200
    spent = len(calls)
    again = client.post("/api/report/run", params={"recording": "c-tonight", "force": 1})
    assert again.status_code == 429 and 0 < int(again.headers["retry-after"]) <= 60
    assert len(calls) == spent  # no model call, no search
    assert client.post("/api/report/run", params={"recording": "c-tonight"}).json()["cached"] is True
    assert client.post("/api/report/run", params={"recording": "nope", "force": 1}).status_code == 404


@pytest.fixture
def photo_client(tmp_path, silent_meta, monkeypatch):
    calls: list[str] = []

    class Spark:
        def __init__(self, key, model="", **kw):
            pass

        async def __call__(self, *args, **kwargs):
            calls.append(kwargs.get("name", ""))
            return {"faces": [], "notes": ""}

    monkeypatch.setattr(app_module, "SparkClient", Spark)
    monkeypatch.setattr(app_module, "PHOTOS_PER_MINUTE", 2)
    finished(tmp_path, "tonight")
    finished(tmp_path, "lastweek", started=time.time() - 7 * 86400)
    return TestClient(app_for(tmp_path), headers=AUTH), calls


def test_a_photo_must_decode_and_land_on_tonights_recording_before_any_model_sees_it(photo_client):
    client, calls = photo_client
    photo = {"image_b64": picture_b64(), "mime": "image/jpeg", "people": []}
    junk = {**photo, "image_b64": "/9j/" + "A" * 40}  # a JPEG's first bytes, then nothing that decodes
    cut = noisy_jpeg()
    cut = {**photo, "image_b64": base64.b64encode(cut[: len(cut) * 2 // 3]).decode()}  # whole headers, cut scan
    assert client.post("/api/recordings/lastweek/photo", json=photo).status_code == 409
    assert client.post("/api/recordings/nope/photo", json=photo).status_code == 404
    assert client.post("/api/recordings/tonight/photo", json=junk).status_code == 415
    assert client.post("/api/recordings/tonight/photo", json=cut).status_code == 415
    assert client.post("/api/recordings/tonight/photo", json={**photo, "image_b64": "not base64!"}).status_code == 400
    assert client.post("/api/recordings/tonight/photo", json={**photo, "mime": "image/gif"}).status_code == 422
    assert client.post("/api/recordings/tonight/photo", json={**photo, "mime": "image/png"}).status_code == 415
    assert calls == []
    assert client.post("/api/recordings/tonight/photo", json=photo).status_code == 200
    assert client.post("/api/recordings/tonight/photo", json=photo).status_code == 200
    third = client.post("/api/recordings/tonight/photo", json=photo)
    assert third.status_code == 429 and "retry-after" in third.headers
    assert calls == ["hallwise_photo", "hallwise_photo"]


def test_a_photo_field_has_a_length_cap(photo_client):
    client, calls = photo_client
    big = "A" * (app_module.PHOTO_B64_MAX + 4)
    assert client.post("/api/recordings/tonight/photo", json={"image_b64": big, "mime": "image/jpeg"}).status_code == 422
    assert calls == []


# H2: no planted transcript, no planted face ----------------------------------------------------------------------


def test_a_scripted_hello_cannot_plant_a_conversation_on_the_meta_backend(tmp_path, silent_meta):
    client = TestClient(create_app(tmp_path, asr="meta", make_extractor=None), headers=AUTH)
    script = [{"start_ms": 100, "end_ms": 600, "speaker": "A", "text": "Hi, I'm Mallory Probe from Evil Corp."}]
    with client.websocket_connect("/ingest") as ws:
        ws.send_text(json.dumps({"sample_rate": RATE, "channels": 1, "layout": "mono", "fake_script": script}))
        rid = ws.receive_json()["recording"]
        ws.send_bytes(np.zeros(RATE, dtype=np.int16).tobytes())
        ws.send_text(json.dumps({"type": "end"}))
        assert ws.receive_json()["type"] == "closed"
    events = client.get(f"/api/recordings/{rid}/events").json()
    assert silent_meta.started == ["start"]  # the real transcriber heard it, not the script
    assert [e for e in events if e["type"] == "turn"] == []


def test_a_face_must_be_an_image_that_decodes(tmp_path):
    client = TestClient(app_for(tmp_path), headers=AUTH)
    url = "/api/people/kenji-watanabe/face"

    def post(body: bytes, mime: str) -> int:
        return client.post(url, content=body, headers={"Content-Type": mime}).status_code

    assert post(b"\xff\xd8" + b"x" * 13, "image/jpeg") == 415  # the review's 15-byte overwrite
    assert post(picture()[:80], "image/jpeg") == 415  # a JPEG cut short in its headers
    cut = noisy_jpeg()
    assert Image.open(BytesIO(cut[: len(cut) * 2 // 3])).size == (320, 240)  # its headers still read
    assert post(cut[: len(cut) * 2 // 3], "image/jpeg") == 415  # but it does not decode
    assert post(picture(), "text/plain") == 415  # what a cross-site no-cors fetch can send
    assert post(json.dumps({"image_b64": picture_b64()}).encode(), "application/json") == 415
    assert post(picture("PNG"), "image/jpeg") == 415  # it must be what it says it is
    bomb = BytesIO()
    Image.new("1", (8000, 7000)).save(bomb, "PNG")  # 56 MP in a few kilobytes
    assert post(bomb.getvalue(), "image/png") == 413
    assert not (tmp_path / "faces" / "kenji-watanabe.jpg").exists()
    assert post(picture(size=(2000, 1500)), "image/jpeg") == 200
    with Image.open(tmp_path / "faces" / "kenji-watanabe.jpg") as kept:
        assert max(kept.size) == 1024 and not kept.info.get("exif")


# H3: a replay cannot spin ------------------------------------------------------------------------------------------


def test_a_pace_outside_a_tenth_to_a_hundred_is_refused_before_the_socket_opens(tmp_path):
    finished(tmp_path)
    client = TestClient(app_for(tmp_path), headers=AUTH)
    for pace in ("1e-17", "0", "0.05", "101", "nan", "inf"):
        with pytest.raises(WebSocketDisconnect) as info:
            with client.websocket_connect(f"/events/r1?pace={pace}&from_ms=1000"):
                pass
        assert info.value.code == 1008, pace
    assert refused(client, "/events/r1?pace=1&from_ms=1501").status_code == 400
    assert refused(client, "/events/nope?pace=1").status_code == 404
    with client.websocket_connect("/events/r1?pace=100&from_ms=1500") as ws:  # from the very end is fine
        got = [ws.receive_json()["type"] for _ in range(4)]
    assert got == ["recording_start", "turn", "replay_clock", "recording_end"]


def test_replay_refuses_a_pace_outside_its_range():
    async def first(pace):
        async for _ in replay([{"type": "a", "t_ms": 0}], pace):
            break

    for pace in (1e-17, 0.0, -1.0, 100.5, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            asyncio.run(first(pace))


def test_the_replay_loop_ends_even_where_a_tick_cannot_move_its_clock(monkeypatch):
    """Far out on the float line one tick (100 s of recording at pace 100) is less than half a step between two
    floats, so `clock += step` leaves the clock where it was: before the guard this ticked forever."""
    async def no_wait(delay):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    far = 10**22  # floats here are 2**21 apart
    events = [{"type": "a", "t_ms": 0}, {"type": "b", "t_ms": far}]

    async def run():
        out = []
        async for line in replay(events, 100.0, from_ms=far - 2 * 2**21):
            out.append(json.loads(line)["type"])
            if len(out) > 50:
                break
        return out

    assert asyncio.run(run()) == ["a", "replay_clock", "b"]


# M1: Host and Origin ----------------------------------------------------------------------------------------------


def test_the_server_answers_only_to_its_own_names(tmp_path, monkeypatch):
    finished(tmp_path)
    client = TestClient(app_for(tmp_path), headers=AUTH)
    assert client.get("/api/recordings", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/recordings", headers={"Host": "rebind.evil.example:8790"}).status_code == 400
    for host in ("localhost:8790", "127.0.0.1:8790", "[::1]:8790"):
        assert client.get("/api/recordings", headers={"Host": host}).status_code == 200, host
    assert refused(client, "/events/r1", headers={"Host": "evil.example"}).status_code == 400
    monkeypatch.setenv("HALLWISE_HOSTS", "testserver, mac.tail1234.ts.net 100.101.102.103")
    tail = TestClient(app_for(tmp_path), headers=AUTH)
    for host in ("mac.tail1234.ts.net", "100.101.102.103:8790"):
        assert tail.get("/api/recordings", headers={"Host": host}).status_code == 200, host


def test_a_new_lan_address_is_picked_up_after_a_network_change(monkeypatch):
    addresses = {"192.168.0.142"}
    monkeypatch.setattr(guard, "HOST_RECHECK_S", 0.0)
    inner = FastAPI()
    inner.get("/x")(lambda: {})
    client = TestClient(guard.Hosts(inner, fixed=["localhost"], lookup=lambda: set(addresses)))
    assert client.get("/x", headers={"Host": "192.168.0.142:8790"}).status_code == 200
    assert client.get("/x", headers={"Host": "172.20.10.2:8790"}).status_code == 400
    addresses.clear()
    addresses.add("172.20.10.2")  # the Mac joined the phone's hotspot
    assert client.get("/x", headers={"Host": "172.20.10.2:8790"}).status_code == 200


def test_sockets_take_no_origin_or_the_servers_own(tmp_path):
    finished(tmp_path)
    client = TestClient(app_for(tmp_path), headers=AUTH)
    with client.websocket_connect("/events/r1") as ws:  # the badge app sends no Origin
        assert ws.receive_json()["type"] == "recording_start"
    with client.websocket_connect("/events/r1", headers={"Origin": "http://testserver"}) as ws:  # the dashboard
        assert ws.receive_json()["type"] == "recording_start"
    for origin in ("http://evil.example", "null", "http://testserver.evil.example", "http://testserver:8000", ""):
        denial = refused(client, "/events/r1", headers={"Origin": origin})
        assert (denial.status_code, denial.json()) == (403, {"error": "forbidden origin"}), origin
        assert refused(client, "/ingest", headers={"Origin": origin}).status_code == 403


# M2: size caps ----------------------------------------------------------------------------------------------------


def test_a_recording_stops_taking_audio_at_its_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_RECORDING_MS", 500)
    client = TestClient(app_for(tmp_path), headers=AUTH)
    chunk = np.zeros(RATE // 10, dtype=np.int16).tobytes()  # 100 ms
    with client.websocket_connect("/ingest") as ws:
        ws.send_text(HELLO)
        rid = ws.receive_json()["recording"]
        for _ in range(20):
            ws.send_bytes(chunk)
        ws.send_text(json.dumps({"type": "end"}))  # Stop after two seconds; the server should not have waited for it
        assert ws.receive_json() == {"type": "closed", "recording": rid}
    with wave.open(str(tmp_path / "recordings" / rid / "audio.wav")) as w:
        assert w.getnframes() == RATE // 2
    events = client.get(f"/api/recordings/{rid}/events").json()
    assert {"type": "recording_limit", "t_ms": 500, "max_ms": 500} in events and events[-1]["type"] == "recording_end"


def test_a_body_over_its_cap_is_refused_from_content_length_before_it_is_read(tmp_path):
    finished(tmp_path)
    app = app_for(tmp_path)
    jpeg, as_json = (b"content-type", b"image/jpeg"), (b"content-type", b"application/json")
    assert asgi(app, "POST", "/api/people/kenji/face", [jpeg, (b"content-length", b"5000001")]) == (413, {"error": "body too large"})
    assert asgi(app, "POST", "/api/recordings/r1/ask", [as_json, (b"content-length", b"300000")])[0] == 413
    assert asgi(app, "POST", "/api/recordings/r1/photo", [as_json, (b"content-length", b"17000000")])[0] == 413
    assert asgi(app, "POST", "/api/people/kenji/face", [jpeg, (b"transfer-encoding", b"chunked")])[0] == 411
    assert asgi(app, "POST", "/login", [as_json, (b"content-length", b"300000")], key=False)[0] == 413


# M4: the export's people snapshot -----------------------------------------------------------------------------------


def evening(data: Path, rid: str, started: float, name: str, company: str, promise: str) -> None:
    d = data / "recordings" / rid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": rid, "event": "Dinner", "venue": "Taipei", "started": started}))
    key = name.split()[0].lower()
    lines = [
        {"type": "recording_start", "t_ms": 0},
        {"type": "person", "t_ms": 1000, "key": key, "name": name, "company": company, "role": "CFO"},
        {"type": "promise", "t_ms": 1200, "key": f"p-{key}", "what": promise, "owed_by": "owner", "owed_to": key},
        {"type": "recording_end", "t_ms": 2000},
    ]
    (d / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))


def export(data: Path, out: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SERVER / "scripts" / "export_replay.py"), *args, "--data", str(data),
                           "--out", str(out)], capture_output=True, text=True, cwd=SERVER)


def test_an_export_publishes_only_the_people_of_the_recordings_it_names(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    now = time.time()
    evening(data, "a-private", now - 7200, "Secret Person", "Hidden Co", "PRIVATE term sheet")
    evening(data, "b-public", now - 3600, "Kenji Watanabe", "Hoshizora", "Send the deck")
    assert export(data, out, "b-public").returncode == 0
    alone = (out / "b-public.json").read_text()
    assert "Kenji Watanabe" in alone
    assert "Secret Person" not in alone and "PRIVATE term sheet" not in alone and "a-private" not in alone
    assert export(data, out, "b-public", "--include", "a-private").returncode == 0
    both = json.loads((out / "b-public.json").read_text())
    assert {p["name"] for p in both["people_index"]["people"]} == {"Secret Person", "Kenji Watanabe"}
    for bad in ("../a-private", "nope"):
        r = export(data, out, "b-public", "--include", bad)
        assert r.returncode != 0 and "--include" in r.stderr


# L3: ids that become paths ----------------------------------------------------------------------------------------


def test_a_recording_id_or_person_key_that_is_not_one_never_reaches_a_path(tmp_path):
    finished(tmp_path)
    # What one `..` above a recording folder would reach: <data>/events.jsonl and <data>/meta.json.
    (tmp_path / "events.jsonl").write_text(json.dumps({"type": "planted", "t_ms": 0}) + "\n")
    (tmp_path / "meta.json").write_text(json.dumps({"id": "..", "started": time.time()}))
    app = app_for(tmp_path)
    for path in ("/api/recordings/../events", "/api/recordings/r1\n/events", "/api/report/..", "/api/people/../face"):
        status, body = asgi(app, "GET", path)
        assert status in (400, 404) and "planted" not in json.dumps(body), path
    question = json.dumps({"question": "what did they say?"}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(question)).encode())]
    assert asgi(app, "POST", "/api/recordings/../ask", headers, body=question)[0] == 404
    client = TestClient(app, headers=AUTH)
    assert client.post("/api/report/run", params={"recording": ".."}).status_code == 404
    assert client.get("/api/recordings/r1/events").status_code == 200
    assert not is_rid("r1\n") and not is_rid("..") and not is_rid("a/b") and is_rid("20261027-064036-3f3e")
    assert not is_key("kenji\n") and not is_key("..secret") and is_key("kenji-watanabe-hoshizora-robotics")


# L5 and the bind address: run.sh ----------------------------------------------------------------------------------


def test_run_sh_makes_the_key_once_keeps_files_private_and_binds_where_asked(tmp_path):
    repo = tmp_path / "repo"
    (repo / "server").mkdir(parents=True)
    shutil.copy(SERVER / "run.sh", repo / "server" / "run.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"  # stands in for `uv run uvicorn ...`: says what it was started with, and nothing else
    uv.write_text('#!/bin/sh\necho "umask=$(umask) bind=$HALLWISE_BIND chars=${#HALLWISE_TOKEN} args=$*"\n')
    uv.chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    first = subprocess.run(["sh", str(repo / "server" / "run.sh")], env=env, capture_output=True, text=True, check=True)
    dotenv = repo / ".env"
    token = dotenv.read_text().split("HALLWISE_TOKEN=", 1)[1].strip()
    assert len(token) == 43 and token not in first.stdout + first.stderr  # 32 random bytes, never printed
    assert stat.S_IMODE(dotenv.stat().st_mode) == 0o600
    assert "umask=0077" in first.stdout and "chars=43" in first.stdout
    assert "bind=0.0.0.0" in first.stdout and "--host 0.0.0.0 --port 8790" in first.stdout
    again = subprocess.run(["sh", str(repo / "server" / "run.sh")], env={**env, "HALLWISE_BIND": "127.0.0.1"},
                           capture_output=True, text=True, check=True)
    assert dotenv.read_text().count("HALLWISE_TOKEN=") == 1 and f"HALLWISE_TOKEN={token}" in dotenv.read_text()
    assert "--host 127.0.0.1" in again.stdout and "made a server key" not in again.stdout
