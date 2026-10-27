"""Where a recording happened: the badge takes one location fix at Start and names it, and the hello carries it as
`place: {name, lat, lon}`.

The server keeps the fix as the phone took it. Anything published (the replay page) gets `public_place`: two
decimals, about a kilometre, so an evening shows its part of town and never a doorstep.
"""

from __future__ import annotations

import math
from typing import Any

PUBLIC_DECIMALS = 2  # 0.01 degree of latitude is 1.1 km; of longitude at Taipei, 1.0 km


def parse_place(value: Any, name: str = "") -> dict[str, Any] | None:
    """{name, lat, lon} from whatever arrived, or None when it carries no usable fix. `name` stands in when the
    place has none of its own (the venue typed or guessed for the same recording)."""
    if not isinstance(value, dict):
        return None
    try:
        lat, lon = float(value["lat"]), float(value["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:  # what an empty fix looks like, not a party in the Gulf of Guinea
        return None
    return {"name": str(value.get("name") or name or ""), "lat": lat, "lon": lon}


def public_place(value: Any, name: str = "") -> dict[str, Any] | None:
    place = parse_place(value, name)
    if place is None:
        return None
    return {**place, "lat": round(place["lat"], PUBLIC_DECIMALS), "lon": round(place["lon"], PUBLIC_DECIMALS)}


def public_places(obj: Any) -> Any:
    """A copy of obj with every `place` inside it, however deep, rounded by public_place (or emptied when it is
    not a readable fix), so nothing published carries the precise one."""
    if isinstance(obj, dict):
        return {k: public_place(v) if k == "place" and isinstance(v, dict) else public_places(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [public_places(v) for v in obj]
    return obj
