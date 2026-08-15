"""Route-free screenshot annotation values used at the model boundary."""

from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def xywh(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0 or self.w <= 0 or self.h <= 0:
            raise ValueError("visual bbox requires a non-negative origin and positive size")


@dataclass(frozen=True)
class VisualMark:
    mark_id: str
    label: str
    bbox: BoundingBox
    confidence: float
    screenshot_ref: str
    snapshot_id: str
    page_revision: str
    target_fingerprint: str

    def __post_init__(self) -> None:
        if not self.mark_id or not 0 <= self.confidence <= 1:
            raise ValueError("visual mark requires an id and confidence within [0, 1]")


def annotate_screenshot(screenshot_bytes: bytes, marks: tuple[VisualMark, ...]) -> bytes:
    """Return PNG bytes with mark boxes; Pillow remains an optional dependency."""

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return screenshot_bytes
    image = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for mark in marks:
        x, y, width, height = mark.bbox.xywh
        draw.rectangle((x, y, x + width, y + height), outline=(0, 200, 0), width=2)
        text_box = draw.textbbox((0, 0), mark.mark_id, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        label_x = min(max(0, x), max(0, image.width - text_width - 4))
        label_y = y - text_height - 4 if y >= text_height + 4 else y + height + 2
        label_y = min(max(0, label_y), max(0, image.height - text_height - 4))
        draw.rectangle(
            (label_x, label_y, label_x + text_width + 3, label_y + text_height + 3),
            fill=(0, 200, 0),
        )
        draw.text((label_x + 2, label_y + 1), mark.mark_id, fill=(0, 0, 0), font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
