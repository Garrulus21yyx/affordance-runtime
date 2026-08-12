"""Immutable screenshot and region values owned by the Visual surface."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from affordance_runtime.immutable import freeze_json
from affordance_runtime.visual_grounding import VisualRegion

_SEMANTIC_STATE_KEYS = frozenset({"visible", "enabled", "selected", "checked", "expanded", "value"})
_MAX_STATE_LIST_ITEMS = 32
_MAX_STATE_STRING_LENGTH = 256


@dataclass(frozen=True)
class VisualViewport:
    width: int
    height: int
    scroll_x: float
    scroll_y: float
    device_pixel_ratio: float
    zoom: float
    orientation: str

    def __post_init__(self) -> None:
        numeric = (self.scroll_x, self.scroll_y, self.device_pixel_ratio, self.zoom)
        if self.width <= 0 or self.height <= 0 or not self.orientation.strip():
            raise ValueError("visual viewport requires positive dimensions and orientation")
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("visual viewport values must be finite")
        if self.device_pixel_ratio <= 0 or self.zoom <= 0:
            raise ValueError("visual viewport DPR and zoom must be positive")

    def private_payload(self) -> dict[str, object]:
        return {
            "viewport_width": self.width,
            "viewport_height": self.height,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "device_pixel_ratio": self.device_pixel_ratio,
            "zoom": self.zoom,
            "orientation": self.orientation,
        }


@dataclass(frozen=True)
class VisualFrame:
    observation_id: str
    screenshot_ref: str
    screenshot_digest: str
    image_width: int
    image_height: int
    viewport: VisualViewport
    image_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        required = (self.observation_id, self.screenshot_ref, self.screenshot_digest)
        if not all(value.strip() for value in required) or not self.image_bytes:
            raise ValueError("visual frame requires screenshot-bound identity and bytes")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("visual frame image dimensions must be positive")
        actual = "sha256:" + hashlib.sha256(self.image_bytes).hexdigest()
        if self.screenshot_digest != actual:
            raise ValueError("visual frame screenshot digest does not match bytes")

    @property
    def source_revision(self) -> str:
        payload = {
            "screenshot": self.screenshot_digest,
            "image": [self.image_width, self.image_height],
            "viewport": self.viewport.private_payload(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class VisualRegionBinding:
    source_observation_id: str
    screenshot_ref: str
    screenshot_digest: str
    image_width: int
    image_height: int
    viewport: VisualViewport
    region_id: str
    region_fingerprint: str
    bbox_xywh: tuple[float, float, float, float]
    action_point_xy: tuple[float, float]
    confidence: float
    label: str
    role: str
    primitive_action: str
    state: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = (
            self.source_observation_id,
            self.screenshot_ref,
            self.screenshot_digest,
            self.region_id,
            self.region_fingerprint,
            self.role,
            self.primitive_action,
        )
        if not all(value.strip() for value in required):
            raise ValueError("visual region binding requires screenshot, region, and action identity")
        if self.image_width <= 0 or self.image_height <= 0 or not 0 <= self.confidence <= 1:
            raise ValueError("visual region binding dimensions or confidence are invalid")
        x, y, width, height = self.bbox_xywh
        point_x, point_y = self.action_point_xy
        if width <= 0 or height <= 0 or x < 0 or y < 0:
            raise ValueError("visual region bbox must be positive")
        if not (x <= point_x <= x + width and y <= point_y <= y + height):
            raise ValueError("visual action point must remain inside its region")
        object.__setattr__(self, "bbox_xywh", tuple(float(value) for value in self.bbox_xywh))
        object.__setattr__(self, "action_point_xy", tuple(float(value) for value in self.action_point_xy))
        object.__setattr__(self, "state", freeze_json(self.state))

    @classmethod
    def from_region(cls, frame: VisualFrame, region_id: str, region: VisualRegion) -> VisualRegionBinding:
        image_x, image_y, image_width, image_height = region.pixel_bbox(
            (frame.image_width, frame.image_height)
        )
        if image_x + image_width > frame.image_width or image_y + image_height > frame.image_height:
            raise ValueError("visual region extends beyond screenshot")
        scale_x = frame.viewport.width / frame.image_width
        scale_y = frame.viewport.height / frame.image_height
        bbox = (
            image_x * scale_x,
            image_y * scale_y,
            image_width * scale_x,
            image_height * scale_y,
        )
        point = (bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2)
        fingerprint = region_fingerprint(frame.screenshot_digest, region_id, region, bbox)
        return cls(
            frame.observation_id,
            frame.screenshot_ref,
            frame.screenshot_digest,
            frame.image_width,
            frame.image_height,
            frame.viewport,
            region_id,
            fingerprint,
            bbox,
            point,
            region.confidence,
            region.label or region_id,
            region.role,
            region.primitive_action,
            dict(region.state),
        )

    def private_payload(self) -> dict[str, object]:
        return {
            "screenshot_ref": self.screenshot_ref,
            "screenshot_digest": self.screenshot_digest,
            "image_width": self.image_width,
            "image_height": self.image_height,
            **self.viewport.private_payload(),
            "region_id": self.region_id,
            "region_fingerprint": self.region_fingerprint,
            "bbox_xywh": self.bbox_xywh,
            "action_point_xy": self.action_point_xy,
        }

    @property
    def source_revision(self) -> str:
        payload = {
            "screenshot": self.screenshot_digest,
            "image": [self.image_width, self.image_height],
            "viewport": self.viewport.private_payload(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def region_fingerprint(
    screenshot_digest: str,
    region_id: str,
    region: VisualRegion,
    bbox_xywh: tuple[float, float, float, float],
) -> str:
    payload = {
        "screenshot": screenshot_digest,
        "region_id": region_id,
        "bbox": bbox_xywh,
        "label": region.label,
        "role": region.role,
        "primitive": region.primitive_action,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def project_visual_semantic_state(state: dict[str, object]) -> dict[str, object]:
    """Project proposer output onto a small, bounded semantic-state vocabulary."""

    projected: dict[str, object] = {}
    for key, value in state.items():
        if key not in _SEMANTIC_STATE_KEYS:
            continue
        bounded = _bounded_state_value(value, depth=0)
        if bounded is not _INVALID_STATE:
            projected[key] = bounded
    return projected


_INVALID_STATE = object()


def _bounded_state_value(value: object, *, depth: int) -> object:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _INVALID_STATE
    if isinstance(value, str):
        return value if len(value) <= _MAX_STATE_STRING_LENGTH else _INVALID_STATE
    if isinstance(value, list | tuple) and depth < 2 and len(value) <= _MAX_STATE_LIST_ITEMS:
        items = tuple(_bounded_state_value(item, depth=depth + 1) for item in value)
        return items if all(item is not _INVALID_STATE for item in items) else _INVALID_STATE
    return _INVALID_STATE
