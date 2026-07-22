"""Bind one selected SVG/visual route to a fresh executable contract."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from affordance_runtime.contracts import ActionContract, Observation, RiskLevel, VerifierSpec
from affordance_runtime.grounding import (
    GroundingCandidate,
    RoutePlan,
    SvgGroundingPayload,
    VisualGroundingPayload,
)


@dataclass(frozen=True)
class VisualContractBinder:
    """Trusted geometry binder; semantic planners never call it with x/y."""

    def bind_point_activate(
        self,
        route: RoutePlan,
        observation: Observation,
        *,
        intent: str,
        verifier_plan: Sequence[VerifierSpec],
        required_capabilities: Sequence[str] = (),
        risk: RiskLevel = RiskLevel.LOW,
        supersedes_contract_id: str = "",
        source_contract_id: str = "",
        fallback_reason: str = "",
    ) -> ActionContract:
        candidate = route.selected_candidate
        if "point_activate" not in candidate.supported_actions:
            raise ValueError("selected grounding candidate does not support point_activate")
        if not candidate.is_current(observation):
            raise ValueError("selected grounding candidate is stale")
        point, bbox = self._viewport_geometry(candidate, observation)
        self._validate_viewport_point(point, observation)
        if self._blocked(point, observation.metadata.get("blocking_overlays")):
            raise ValueError("selected grounding point is blocked by an overlay")
        return ActionContract(
            id=(
                f"contract_{candidate.candidate_id.replace(':', '_')}_"
                f"{candidate.observation_epoch_id}"
            ),
            intent=intent,
            affordance_id=route.semantic_target_id,
            action="point_activate",
            backend=candidate.compatible_executor,
            environment_revision=candidate.environment_revision,
            locator={
                "point": [point[0], point[1]],
                "bbox": [*bbox],
                "coordinate_space": "viewport_pixels",
                "candidate_id": candidate.candidate_id,
            },
            grounding_candidate=candidate,
            route_plan=route,
            verifier_plan=list(verifier_plan),
            required_capabilities=list(required_capabilities),
            risk=risk,
            snapshot_id=candidate.observation_epoch_id,
            page_revision=candidate.page_revision,
            target_fingerprint=candidate.target_fingerprint,
            target_fingerprint_key=candidate.fingerprint_key or candidate.candidate_id,
            expires_at_s=candidate.expires_at_s,
            supersedes_contract_id=supersedes_contract_id,
            source_contract_id=source_contract_id,
            fallback_reason=fallback_reason,
        )

    def _viewport_geometry(
        self,
        candidate: GroundingCandidate,
        observation: Observation,
    ) -> tuple[tuple[float, float], tuple[float, float, float, float]]:
        payload = candidate.payload
        if isinstance(payload, SvgGroundingPayload):
            geometry = payload.geometry_bbox_xywh
            transformed_center = payload.transform.apply(
                (geometry[0] + geometry[2] / 2, geometry[1] + geometry[3] / 2)
            )
            if not _point_in_box(transformed_center, payload.viewport_bbox_xywh, tolerance=2.0):
                raise ValueError("SVG transform does not agree with current viewport geometry")
            return transformed_center, payload.viewport_bbox_xywh
        if isinstance(payload, VisualGroundingPayload):
            image_width, image_height = payload.image_size
            if image_width <= 0 or image_height <= 0:
                raise ValueError("visual grounding image dimensions must be positive")
            if payload.screenshot_ref != observation.screenshot_ref:
                raise ValueError("visual grounding screenshot does not match the current observation")
            if payload.point_xy is not None:
                image_point = payload.point_xy
                image_bbox = (image_point[0], image_point[1], 1.0, 1.0)
            elif payload.bbox_xywh is not None:
                image_bbox = payload.bbox_xywh
                image_point = (
                    image_bbox[0] + image_bbox[2] / 2,
                    image_bbox[1] + image_bbox[3] / 2,
                )
            else:
                raise ValueError("visual grounding candidate requires a point or box")
            if not _point_in_box(image_point, (0.0, 0.0, float(image_width), float(image_height))):
                raise ValueError("visual grounding point is outside the screenshot")
            viewport = _viewport_size(observation.metadata, payload.image_size)
            if viewport is None:  # The visual payload image size is the fallback above.
                raise ValueError("visual grounding requires current viewport dimensions")
            scale_x = viewport[0] / image_width
            scale_y = viewport[1] / image_height
            point = (image_point[0] * scale_x, image_point[1] * scale_y)
            bbox = (
                image_bbox[0] * scale_x,
                image_bbox[1] * scale_y,
                image_bbox[2] * scale_x,
                image_bbox[3] * scale_y,
            )
            return point, bbox
        raise ValueError("VisualContractBinder requires an SVG or visual grounding payload")

    def _validate_viewport_point(self, point: tuple[float, float], observation: Observation) -> None:
        if not all(math.isfinite(value) for value in point):
            raise ValueError("grounding point must contain finite coordinates")
        viewport = _viewport_size(observation.metadata, None)
        if viewport is not None and not _point_in_box(point, (0.0, 0.0, viewport[0], viewport[1])):
            raise ValueError("grounding point is outside the current viewport")

    def _blocked(self, point: tuple[float, float], raw_overlays: Any) -> bool:
        if not isinstance(raw_overlays, list):
            return False
        return any(
            _point_in_box(point, box)
            for item in raw_overlays
            if (box := _box_from_mapping(item)) is not None
        )


def _viewport_size(
    metadata: Mapping[str, Any],
    fallback: tuple[int, int] | None,
) -> tuple[float, float] | None:
    raw = metadata.get("viewport_size")
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        width, height = float(raw[0]), float(raw[1])
        if width > 0 and height > 0:
            return width, height
    if fallback is not None:
        return float(fallback[0]), float(fallback[1])
    return None


def _point_in_box(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
    *,
    tolerance: float = 0.0,
) -> bool:
    x, y = point
    left, top, width, height = box
    return (
        left - tolerance <= x <= left + width + tolerance
        and top - tolerance <= y <= top + height + tolerance
    )


def _box_from_mapping(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("bbox")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    left, top, width, height = (float(item) for item in raw)
    return (left, top, width, height) if width > 0 and height > 0 else None
