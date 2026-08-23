"""Route-free screenshot annotation values used at the model boundary."""

from __future__ import annotations

import hashlib
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


@dataclass(frozen=True)
class VisualAnnotationResult:
    data: bytes
    mime_type: str
    sha256: str
    marks: tuple[VisualMark, ...]
    available: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "marks", tuple(self.marks))
        if self.mime_type not in {"image/png", "image/jpeg"}:
            raise ValueError("annotation result MIME is unsupported")
        if hashlib.sha256(self.data).hexdigest() != self.sha256:
            raise ValueError("annotation result digest does not match its bytes")


def annotate_screenshot_result(
    screenshot_bytes: bytes,
    input_mime_type: str,
    marks: tuple[VisualMark, ...],
) -> VisualAnnotationResult:
    """Draw only in-frame marks and report the exact output bytes and MIME."""

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return VisualAnnotationResult(
            screenshot_bytes,
            input_mime_type,
            hashlib.sha256(screenshot_bytes).hexdigest(),
            (),
            False,
        )
    try:
        image = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")
    except Exception:
        return VisualAnnotationResult(
            screenshot_bytes,
            input_mime_type,
            hashlib.sha256(screenshot_bytes).hexdigest(),
            (),
            False,
        )
    actual = tuple(
        mark
        for mark in marks
        if mark.bbox.x < image.width
        and mark.bbox.y < image.height
        and mark.bbox.x + mark.bbox.w > 0
        and mark.bbox.y + mark.bbox.h > 0
    )
    if not actual:
        return VisualAnnotationResult(
            screenshot_bytes,
            input_mime_type,
            hashlib.sha256(screenshot_bytes).hexdigest(),
            (),
        )
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for mark in actual:
        x, y, width, height = mark.bbox.xywh
        x2, y2 = min(image.width - 1, x + width), min(image.height - 1, y + height)
        draw.rectangle((max(0, x), max(0, y), x2, y2), outline=(0, 200, 0), width=2)
        text_box = draw.textbbox((0, 0), mark.mark_id, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        label_x = min(max(0, x), max(0, image.width - text_width - 4))
        label_y = y - text_height - 4 if y >= text_height + 4 else y2 + 2
        label_y = min(max(0, label_y), max(0, image.height - text_height - 4))
        draw.rectangle(
            (label_x, label_y, label_x + text_width + 3, label_y + text_height + 3),
            fill=(0, 200, 0),
        )
        draw.text((label_x + 2, label_y + 1), mark.mark_id, fill=(0, 0, 0), font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    return VisualAnnotationResult(data, "image/png", hashlib.sha256(data).hexdigest(), actual)


def annotate_screenshot(screenshot_bytes: bytes, marks: tuple[VisualMark, ...]) -> bytes:
    """Return PNG bytes with mark boxes; Pillow remains an optional dependency."""

    return annotate_screenshot_result(screenshot_bytes, "image/png", marks).data
