"""Small real images for the endpoints that now decode what they are sent."""

import base64
from io import BytesIO

from PIL import Image


def picture(fmt: str = "JPEG", size: tuple[int, int] = (64, 48), colour: tuple[int, int, int] = (200, 120, 60)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, colour).save(out, fmt)
    return out.getvalue()


def picture_b64(fmt: str = "JPEG", **kw) -> str:
    return base64.b64encode(picture(fmt, **kw)).decode()


def noisy_jpeg(size: tuple[int, int] = (320, 240)) -> bytes:
    """A JPEG with real scan data (noise does not compress away), so a cut copy keeps whole headers and only fails
    when it is decoded."""
    out = BytesIO()
    Image.effect_noise(size, 80).convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()
