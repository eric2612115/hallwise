"""Images that arrive from outside: a face to keep, a photo to look at. Each must be a JPEG or a PNG that really
decodes, under a pixel cap, before it is kept or sent to a model; a face is kept re-encoded, without metadata."""

from __future__ import annotations

import base64
import binascii
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG"}
MAX_PIXELS = 50_000_000  # a 48 MP phone photo fits; a decompression bomb does not
FACE_SIDE = 1024  # the app sends 480 px; anything bigger is scaled down before it is kept


class BadImage(ValueError):
    def __init__(self, message: str, status: int = 415):
        super().__init__(message)
        self.status = status


def open_image(raw: bytes, mime: str) -> Image.Image:
    """The decoded image, if `raw` is the JPEG or PNG `mime` says; BadImage otherwise."""
    fmt = FORMATS.get(mime)
    if fmt is None:
        raise BadImage("expected image/jpeg or image/png")
    try:
        img = Image.open(BytesIO(raw), formats=[fmt])
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise BadImage(f"not a {fmt} image")
    width, height = img.size
    if width * height > MAX_PIXELS:
        raise BadImage("image has too many pixels", status=413)
    try:
        img.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise BadImage(f"the {fmt} does not decode")
    return img


def face_jpeg(raw: bytes, mime: str) -> bytes:
    """A face as kept: upright, RGB, at most FACE_SIDE on a side, JPEG, no EXIF."""
    img = ImageOps.exif_transpose(open_image(raw, mime)).convert("RGB")
    img.thumbnail((FACE_SIDE, FACE_SIDE))
    out = BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def photo_bytes(image_b64: str, mime: str, max_bytes: int) -> bytes:
    """A photo's bytes, once they are known to be the image `mime` says and no bigger than `max_bytes`."""
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise BadImage("image_b64 is not base64", status=400)
    if len(raw) > max_bytes:
        raise BadImage("photo too large", status=413)
    open_image(raw, mime)
    return raw
