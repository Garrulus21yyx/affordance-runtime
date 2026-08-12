"""Set-of-Marks visual adapter."""

from __future__ import annotations

import hashlib
import html
import io
import json
from dataclasses import dataclass
from typing import Any

from affordance_runtime.contracts import Affordance, AffordanceLease, Observation, RiskLevel, Surface
from affordance_runtime.immutable import FrozenSequence


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
class SomOverlay:
    marks: tuple[VisualMark, ...]
    svg: str
    screenshot_ref: str
    snapshot_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "marks", FrozenSequence(self.marks))


class SomAdapter:
    def parse(
        self,
        regions: list[dict[str, Any]],
        *,
        environment_revision: str,
        screenshot_ref: str = "",
        ttl_ms: int = 2_000,
        min_confidence: float = 0.0,
        snapshot_id: str = "",
        page_revision: str = "",
    ) -> list[Affordance]:
        affordances: list[Affordance] = []
        mark_index = 0
        for region in regions:
            confidence = float(region.get("confidence", 1.0))
            if confidence < min_confidence:
                continue
            bbox = [int(value) for value in region["bbox"]]
            if len(bbox) != 4:
                raise ValueError(f"bbox must be [x, y, w, h], got {bbox!r}")
            x, y, w, h = bbox
            BoundingBox(x, y, w, h)
            mark_id = f"M{mark_index}"
            action = str(region.get("action", "click"))
            target_fingerprint = "sha256:" + hashlib.sha256(
                json.dumps({"mark_id": mark_id, "bbox": bbox, "label": region.get("label", ""), "action": action}, sort_keys=True).encode()
            ).hexdigest()
            lease = AffordanceLease.issue(
                environment_revision=environment_revision,
                ttl_ms=ttl_ms,
                provenance=["screenshot", "som"],
                snapshot_id=snapshot_id,
                page_revision=page_revision or environment_revision,
                target_fingerprint=target_fingerprint,
            )
            affordances.append(
                Affordance(
                    id=f"vis_{mark_id}",
                    surface=Surface.VISUAL,
                    role="input" if action in {"type", "select"} else "button",
                    label=str(region.get("label") or mark_id),
                    action=action,
                    locator={
                        "mark_id": mark_id,
                        "bbox": bbox,
                        "center": [x + w // 2, y + h // 2],
                        "screenshot_ref": screenshot_ref,
                    },
                    lease=lease,
                    backend_candidates=["visual"],
                    confidence=confidence,
                    state={"ocr": region.get("ocr", "")},
                    risk=RiskLevel.LOW,
                    evidence=[screenshot_ref] if screenshot_ref else [],
                )
            )
            mark_index += 1
        return affordances

    def select(self, affordances: list[Affordance], mark_id: str) -> Affordance:
        """Look up a mark only; this method does not authorize execution."""

        for affordance in affordances:
            if affordance.locator.get("mark_id") == mark_id:
                return affordance
        raise KeyError(f"mark_id {mark_id!r} not present")

    def select_current(
        self,
        affordances: list[Affordance],
        mark_id: str,
        observation: Observation,
    ) -> Affordance:
        affordance = self.select(affordances, mark_id)
        if not affordance.lease.is_current(observation, affordance_id=affordance.id):
            raise ValueError(f"mark_id {mark_id!r} is stale for the current observation")
        return affordance

    def marks_from_affordances(self, affordances: list[Affordance]) -> tuple[VisualMark, ...]:
        marks: list[VisualMark] = []
        for affordance in affordances:
            mark_id = affordance.locator.get("mark_id")
            raw_bbox = affordance.locator.get("bbox")
            if not mark_id or not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
                continue
            bbox = BoundingBox(*(int(value) for value in raw_bbox))
            marks.append(
                VisualMark(
                    mark_id=str(mark_id),
                    label=affordance.label,
                    bbox=bbox,
                    confidence=affordance.confidence,
                    screenshot_ref=str(affordance.locator.get("screenshot_ref") or ""),
                    snapshot_id=affordance.lease.snapshot_id,
                    page_revision=affordance.lease.page_revision,
                    target_fingerprint=affordance.lease.target_fingerprint,
                )
            )
        return tuple(marks)

    def render_overlay_svg(
        self,
        affordances: list[Affordance],
        *,
        width: int,
        height: int,
    ) -> SomOverlay:
        if width <= 0 or height <= 0:
            raise ValueError("overlay dimensions must be positive")
        marks = self.marks_from_affordances(affordances)
        identities = {(mark.screenshot_ref, mark.snapshot_id) for mark in marks}
        if len(identities) > 1:
            raise ValueError("overlay marks must belong to one screenshot observation")
        elements: list[str] = []
        for mark in marks:
            x, y, box_width, box_height = mark.bbox.xywh
            mark_id = html.escape(mark.mark_id, quote=True)
            elements.append(
                f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" '
                'fill="none" stroke="#e2001a" stroke-width="2"/>'
                f'<text x="{x + 2}" y="{y + 14}" fill="#e2001a" '
                f'font-family="monospace" font-size="13">{mark_id}</text>'
            )
        screenshot_ref, snapshot_id = next(iter(identities), ("", ""))
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            + "".join(elements)
            + "</svg>"
        )
        return SomOverlay(marks, svg, screenshot_ref, snapshot_id)


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
