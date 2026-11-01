"""The demo's cue: put the page made beforehand into the recording in progress, for one person, so the phone buzzes
("Margaux · your deck, rebuilt") and opens it.

    uv run python scripts/cue_rebuilt.py Margaux [--recording 20261029-025913-1e23] [--shape "one page, numbers first"]
        [--server http://127.0.0.1:8790]

The server serves the page from HALLWISE_ONEPAGER_CUE (an .html or .pdf on the server's disk), set before it starts;
the request names only the person. Without --recording, the one being recorded is used (else the newest).
Needs the routes from hallwise/onepager.py (`router`) in the app. The server key comes from $HALLWISE_TOKEN or the
repo's .env, and is never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hallwise.guard import client_headers  # noqa: E402  the server key, from $HALLWISE_TOKEN or the repo's .env


def call(method: str, url: str) -> object:
    request = urllib.request.Request(url, method=method, headers=client_headers())
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as err:
        raise SystemExit(f"{method} {urllib.parse.urlsplit(url).path}: {err.code} {err.read().decode(errors='replace')[:300]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="the person's first name, as you would say it: Margaux finds Margot too")
    ap.add_argument("--recording", default="")
    ap.add_argument("--shape", default="", help="what this version is, for the notification")
    ap.add_argument("--server", default="http://127.0.0.1:8790")
    args = ap.parse_args()
    server = args.server.rstrip("/")
    rid = args.recording
    if not rid:
        recordings = call("GET", f"{server}/api/recordings")  # newest first
        if not recordings:
            raise SystemExit("no recording on the server")
        rid = next((r for r in recordings if r.get("live")), recordings[0])["id"]
    query = urllib.parse.urlencode({"name": args.name, **({"shape": args.shape} if args.shape else {})})
    event = call("POST", f"{server}/api/recordings/{urllib.parse.quote(rid)}/onepager/cue?{query}")
    print(f"{rid}: rebuilt for {event.get('name')} ({event.get('person_key')}), {event.get('format')} at {event.get('url')}")


if __name__ == "__main__":
    main()
