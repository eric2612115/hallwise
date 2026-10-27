"""The owner's vocabulary: spellings fixed on the phone, and suggestions turned down, kept across recordings.

    data/vocabulary.json  {"words": [{"heard": "Vexy", "use": "Vexi"}, ...],
                           "rejected": [{"heard": "Ken", "likely": "Kenji Watanabe"}, ...]}

A word the owner accepted or typed on the Words page goes to the transcriber as a keyword hint and to Muse Spark as a
preferred spelling on every later recording, after the app's own Words and before the names from earlier evenings
(recording.recognition_hints). A suggestion the owner rejected is never offered again (corrections.refine drops it,
and its mirror image, from every later suspect_word). The file is written whole to a temporary file beside it and
moved over, so a crash never leaves half of it; it takes the server's umask (run.sh: 077), like everything in data/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_WORDS = 500  # the newest are kept
MAX_REJECTED = 1000
MAX_HINT_WORDS = 100  # how many of the newest spellings ride as transcriber hints
MAX_CHARS = 120


def clean(text: Any, limit: int = MAX_CHARS) -> str:
    """One line of plain text: whitespace runs (newlines and tabs included) become one space, control characters go,
    and it is cut at `limit`. What the owner types here ends up in prompts, so it never brings its own lines."""
    s = "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in str(text or ""))
    return " ".join(s.split())[:limit]


def _fold(text: str) -> str:
    return clean(text).casefold()


class Vocabulary:
    def __init__(self, data: Path):
        self.path = data / "vocabulary.json"

    def load(self) -> dict[str, list[dict[str, str]]]:
        """What is on disk, with anything malformed left out; empty lists when there is no file yet."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        words = [
            {"heard": clean(w.get("heard")), "use": clean(w.get("use"))}
            for w in raw.get("words", []) if isinstance(w, dict)
        ]
        rejected = [
            {"heard": clean(r.get("heard")), "likely": clean(r.get("likely"), 200)}
            for r in raw.get("rejected", []) if isinstance(r, dict)
        ]
        return {
            "words": [w for w in words if w["heard"] and w["use"]][-MAX_WORDS:],
            "rejected": [r for r in rejected if r["heard"] and r["likely"]][-MAX_REJECTED:],
        }

    def add_word(self, heard: str, use: str) -> dict[str, list[dict[str, str]]]:
        """The owner says `heard` should be `use`: one entry per heard word (the newest wins), and the pairing is no
        longer rejected if it was."""
        heard, use = clean(heard), clean(use)
        v = self.load()
        v["words"] = [w for w in v["words"] if _fold(w["heard"]) != heard.casefold()] + [{"heard": heard, "use": use}]
        v["rejected"] = [r for r in v["rejected"] if (_fold(r["heard"]), _fold(r["likely"])) != (heard.casefold(), use.casefold())]
        return self._save(v)

    def reject(self, heard: str, likely: str) -> dict[str, list[dict[str, str]]]:
        """Never suggest `likely` for `heard` again."""
        heard, likely = clean(heard), clean(likely, 200)
        v = self.load()
        pair = (heard.casefold(), likely.casefold())
        v["rejected"] = [r for r in v["rejected"] if (_fold(r["heard"]), _fold(r["likely"])) != pair] + [
            {"heard": heard, "likely": likely}
        ]
        return self._save(v)

    def _save(self, v: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
        v = {"words": v["words"][-MAX_WORDS:], "rejected": v["rejected"][-MAX_REJECTED:]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
        return v


def keywords(v: dict[str, list[dict[str, str]]]) -> list[str]:
    """The spellings to hint, newest first, each once."""
    out: dict[str, str] = {}
    for w in reversed(v.get("words", [])):
        out.setdefault(w["use"].casefold(), w["use"])
    return list(out.values())[:MAX_HINT_WORDS]


def rejected_pairs(v: dict[str, list[dict[str, str]]]) -> set[tuple[str, str]]:
    """(heard, likely), casefolded, both ways round: turning down "Ken → Kenji Watanabe" turns down its mirror too."""
    out: set[tuple[str, str]] = set()
    for r in v.get("rejected", []):
        a, b = _fold(r["heard"]), _fold(r["likely"])
        out |= {(a, b), (b, a)}
    return out
