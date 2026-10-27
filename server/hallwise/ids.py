"""The ids that become file names, checked in one place.

A recording id names a folder under data/recordings and a report under data/reports; a person key names a face
under data/faces. Anything else that arrives where one of these is expected is refused before it reaches a path,
so `..`, `%2e%2e`, slashes and a trailing newline never do (fullmatch: `$` alone would let "id\\n" through).
"""

from __future__ import annotations

import re

RID = re.compile(r"[0-9A-Za-z_-]{1,80}")
KEY = re.compile(r"[0-9a-z][0-9a-z-]{0,119}")


def is_rid(value: object) -> bool:
    return isinstance(value, str) and RID.fullmatch(value) is not None


def is_key(value: object) -> bool:
    return isinstance(value, str) and KEY.fullmatch(value) is not None
