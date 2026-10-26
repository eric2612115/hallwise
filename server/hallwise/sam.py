"""SAM 3.1 finds things in a photo: a box (and a mask, which we ignore) for every match of a short noun phrase.

Meta Model API, Responses protocol: POST /v1/responses with model "sam-3.1" and a user message holding an
`input_text` (the noun phrase) and an `input_image` (a data URL). The answer is not JSON but one line of tokens in
output[].content[].text, one record per match:

    <0f>0<|box;x1=491;y1=585;x2=828;y2=838;w=2400;h=1600;c=0.949|><|mask;x=0;y=0;c=0.949;data=...|>,1<|box;...

Boxes are source pixels with x2 and y2 inclusive; w and h are the image size; c is the confidence, present when
the request asks for it. No match is an empty text. See dev.meta.ai/docs/sam/segmenting and
dev.meta.ai/docs/sam/reading-segmentation.
"""

from __future__ import annotations

import re
import time
from typing import Any, Awaitable, Callable

import httpx

SAM_URL = "https://api.meta.ai/v1/responses"

# Only key=number fields, so nothing inside a mask payload can be mistaken for a box.
_BOX = re.compile(r"<\|box;((?:[a-z0-9]+=[-+0-9.eE]+;?)+)\|>")

Finder = Callable[[str, str, str], Awaitable[list[dict[str, Any]]]]  # (image_b64, mime, phrase) -> [{box, score}]


def parse_boxes(text: str) -> list[dict[str, Any]]:
    """Every box token in SAM's output as {box: [x0, y0, x1, y1] fractions of the image, score}, in output order."""
    found = []
    for match in _BOX.finditer(text):
        f = {k: float(v) for k, v in (kv.split("=", 1) for kv in match.group(1).split(";") if kv)}
        w, h = f.get("w", 0), f.get("h", 0)
        if w <= 0 or h <= 0 or not {"x1", "y1", "x2", "y2"} <= f.keys():
            continue
        box = [f["x1"] / w, f["y1"] / h, (f["x2"] + 1) / w, (f["y2"] + 1) / h]  # inclusive corner -> edge
        box = [max(0.0, min(1.0, v)) for v in box]
        if box[2] > box[0] and box[3] > box[1]:
            found.append({"box": box, "score": f.get("c", 1.0)})
    return found


class SamClient:
    """SAM 3.1 over the Responses endpoint; one call per noun phrase."""

    def __init__(self, api_key: str, model: str = "sam-3.1", timeout: float = 20):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.last_seconds = 0.0

    async def __call__(self, image_b64: str, mime: str, phrase: str) -> list[dict[str, Any]]:
        body = {
            "model": self.model,
            "input": [{
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": phrase},
                    {"type": "input_image", "image_url": f"data:{mime};base64,{image_b64}"},
                ],
            }],
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},  # one_bit: smaller masks
        }
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(SAM_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        self.last_seconds = time.monotonic() - started
        response.raise_for_status()
        text = "".join(
            part.get("text", "")
            for item in response.json().get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
        return parse_boxes(text)
