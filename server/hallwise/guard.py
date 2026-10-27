"""Who may use the server, from where, and how much they may send.

The key. Every request and every socket carries the shared key HALLWISE_TOKEN (run.sh keeps it in ../.env, mode
600, and makes one the first time: 32 random bytes, URL-safe base64), as `Authorization: Bearer <key>` or as the
`hallwise_token` cookie that POST /login sets for the browser dashboard, which cannot put a header on a WebSocket.
It is compared in constant time. Without it an HTTP request gets 401 {"error": "unauthorized"}, and a socket is
turned away before it opens: HTTP 401 on the upgrade, or, where the server cannot answer an upgrade with a status,
accepted and closed at once with code 4401. The badge app says "Server key is wrong" on either. Only the
dashboard's shell loads without the key (/, /index.html, /assets/..., POST /login); it holds no data. The server
does not start without a key unless HALLWISE_INSECURE=1.

Hosts. The server answers only to the names it is reached by: localhost, this Mac's addresses and name, the
address it is bound to, and HALLWISE_HOSTS (a Tailscale name, say), so a web page cannot rebind its own name onto
this Mac and read the API as if it were same-origin.

Origins. A socket opened by a web page must come from the server's own origin (the dashboard); the badge app and
the scripts send no Origin at all. A POST that rides on the cookie must be same-origin too: SameSite=Strict still
lets a page on another port of the same host send it.

Bodies. A request with a body says how long it is (no chunked uploads: 411) and stays under its route's cap,
which is checked from Content-Length before anything is read (413).
"""

from __future__ import annotations

import hmac
import os
import socket
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import cookie_parser
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket

TOKEN_COOKIE = "hallwise_token"
COOKIE_MAX_AGE_S = 30 * 86400
MIN_TOKEN_CHARS = 16
SHELL = {"/", "/index.html", "/favicon.ico", "/favicon.svg"}  # GET without the key, like /assets/*
OPEN_POSTS = {"/login", "/logout"}
READS = {"GET", "HEAD"}
DEFAULT_BODY_MAX = 256 * 1024
REPO = Path(__file__).resolve().parents[2]
LOCAL = ("localhost", "127.0.0.1", "::1", "[::1]")
HOST_RECHECK_S = 10.0


def server_token() -> str | None:
    """HALLWISE_TOKEN; None only when HALLWISE_INSECURE=1 runs the server open. Missing otherwise: no start."""
    token = os.environ.get("HALLWISE_TOKEN", "").strip()
    if token:
        if len(token) < MIN_TOKEN_CHARS:
            raise RuntimeError(f"HALLWISE_TOKEN is shorter than {MIN_TOKEN_CHARS} characters; run.sh makes a 32-byte one")
        return token
    if os.environ.get("HALLWISE_INSECURE") == "1":
        print("hallwise: HALLWISE_INSECURE=1 and no HALLWISE_TOKEN: anyone who can reach this port can use the server")
        return None
    raise RuntimeError("HALLWISE_TOKEN is not set: start with ./run.sh (it makes one in .env), or HALLWISE_INSECURE=1 to run open")


def client_token(env_file: Path = REPO / ".env") -> str:
    """The key for a script on this Mac talking to the server: $HALLWISE_TOKEN, else its line in the repo's .env."""
    token = os.environ.get("HALLWISE_TOKEN", "").strip()
    if token:
        return token
    try:
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip().removeprefix("export ").strip() == "HALLWISE_TOKEN":
                token = value.strip().strip("'\"")  # the last one wins, as when the shell sources the file
    except OSError:
        pass
    return token


def client_headers() -> dict[str, str]:
    token = client_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def bearer(headers: Headers) -> str:
    scheme, _, value = headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def matches(given: str, token: str) -> bool:
    return bool(given) and hmac.compare_digest(given.encode(), token.encode())


def same_origin(headers: Headers) -> bool:
    """No Origin (the badge app, the scripts, curl), or the server's own: http(s) and the very host:port asked for."""
    origin = headers.get("origin")
    if origin is None:
        return True
    parts = urlsplit(origin)
    return parts.scheme in ("http", "https") and bool(parts.netloc) and parts.netloc.lower() == headers.get("host", "").lower()


async def refuse_socket(ws: WebSocket, status: int, error: str) -> None:
    """Turn a socket away before it opens: HTTP `status` with {"error": ...} on the upgrade where the server can
    answer one (uvicorn can), else accept and close at once with 4000 + status (4401 for a wrong key)."""
    if "websocket.http.response" in ws.scope.get("extensions", {}):
        await ws.send_denial_response(JSONResponse({"error": error}, status_code=status))
    else:
        await ws.accept()
        await ws.close(code=4000 + status, reason=error)


def lan_addresses() -> set[str]:
    """Every address on this Mac's interfaces (Wi-Fi, Ethernet, a hotspot, Tailscale's 100.x while it is up), from
    ifconfig; the default route's address where there is no ifconfig; and the Mac's name, with .local as Bonjour
    has it. An IP literal never helps a rebinding page, which can only send its own host name."""
    out: set[str] = set()
    try:
        text = subprocess.run(["/sbin/ifconfig"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        text = ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "inet":
            out.add(parts[1])
        elif len(parts) >= 2 and parts[0] == "inet6":
            out.add(f"[{parts[1].split('%')[0].lower()}]")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # UDP connect sends nothing; it only picks the outgoing interface
            out.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        name = socket.gethostname().lower()
    except OSError:
        name = ""
    if name:
        out |= {name, name if name.endswith(".local") else name + ".local"}
    return out


def configured_hosts() -> list[str]:
    """localhost, HALLWISE_BIND when it is one address, and HALLWISE_HOSTS (commas or spaces)."""
    hosts = list(LOCAL)
    bind = os.environ.get("HALLWISE_BIND", "").strip()
    if bind and bind not in ("0.0.0.0", "::"):
        hosts.append(f"[{bind}]" if ":" in bind else bind)
    hosts += [h for h in os.environ.get("HALLWISE_HOSTS", "").replace(",", " ").split() if h]
    return hosts


def host_of(header: str) -> str:
    h = header.strip().lower()
    if h.startswith("["):
        return h.split("]", 1)[0] + "]"
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


class Hosts(TrustedHostMiddleware):
    """TrustedHostMiddleware over the configured names plus this Mac's addresses; on a miss they are looked up again
    (at most every ten seconds), so moving from venue Wi-Fi to a hotspot does not lock the badge out."""

    def __init__(self, app: ASGIApp, fixed: Iterable[str], lookup: Callable[[], set[str]] = lan_addresses):
        self.fixed = {h.lower() for h in fixed}
        self.lookup = lookup
        self.looked = time.monotonic()
        super().__init__(app, allowed_hosts=sorted(self.fixed | {h.lower() for h in lookup()}))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and not self.allow_any:
            host = host_of(Headers(scope=scope).get("host", ""))
            if host not in self.allowed_hosts and time.monotonic() - self.looked > HOST_RECHECK_S:
                self.looked = time.monotonic()
                self.allowed_hosts = sorted(self.fixed | {h.lower() for h in self.lookup()})
        await super().__call__(scope, receive, send)


class Guard:
    """The key on every request and socket, the Origin rule, and the body caps (see the module docstring)."""

    def __init__(self, app: ASGIApp, token: str | None, body_cap: Callable[[str, str], int]):
        self.app = app
        self.token = token
        self.body_cap = body_cap

    def credential(self, headers: Headers) -> str | None:
        """How the request proved it has the key: "header", "cookie", "open" (no key configured), or None."""
        if self.token is None:
            return "open"
        if matches(bearer(headers), self.token):
            return "header"
        if matches(cookie_parser(headers.get("cookie", "")).get(TOKEN_COOKIE, ""), self.token):
            return "cookie"
        return None

    @staticmethod
    def public(method: str, path: str) -> bool:
        if ".." in path:
            return False
        if method in READS:
            return path in SHELL or path.startswith("/assets/")
        return method == "POST" and path in OPEN_POSTS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            ws = WebSocket(scope, receive, send)
            if not same_origin(ws.headers):
                await refuse_socket(ws, 403, "forbidden origin")
            elif self.credential(ws.headers) is None:
                await refuse_socket(ws, 401, "unauthorized")
            else:
                await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        method, path = scope["method"], scope["path"]

        async def reply(status: int, error: str, **extra: str) -> None:
            await JSONResponse({"error": error}, status_code=status, headers=extra or None)(scope, receive, send)

        if not self.public(method, path):
            how = self.credential(headers)
            if how is None:
                return await reply(401, "unauthorized", **{"WWW-Authenticate": "Bearer"})
            if how == "cookie" and method not in READS and not same_origin(headers):
                return await reply(403, "forbidden origin")
        if "transfer-encoding" in headers:
            return await reply(411, "say how long the body is (Content-Length)")
        length = headers.get("content-length")
        if length is not None:
            if not length.strip().isdigit():
                return await reply(400, "bad Content-Length")
            if int(length) > self.body_cap(method, path):
                return await reply(413, "body too large")
        await self.app(scope, receive, send)


class Window:
    """At most `n` in any `per` seconds. wait() is 0 when one may go now, else the seconds until one may; take()
    counts one when it may go and returns what wait() said."""

    def __init__(self, n: int, per: float, clock: Callable[[], float] = time.monotonic):
        self.n, self.per, self.clock = n, per, clock
        self.times: deque[float] = deque()

    def wait(self) -> float:
        now = self.clock()
        while self.times and now - self.times[0] >= self.per:
            self.times.popleft()
        return 0.0 if len(self.times) < self.n else self.per - (now - self.times[0])

    def take(self) -> float:
        wait = self.wait()
        if not wait:
            self.times.append(self.clock())
        return wait


class Slots:
    """At most `n` at once: take() is False when all are in use; give() hands one back."""

    def __init__(self, n: int):
        self.n, self.used = n, 0

    def take(self) -> bool:
        if self.used >= self.n:
            return False
        self.used += 1
        return True

    def give(self) -> None:
        self.used = max(0, self.used - 1)
