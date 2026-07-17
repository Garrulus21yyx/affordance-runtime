"""Set-of-Marks visual adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affordance_runtime.contracts import Affordance, AffordanceLease, RiskLevel, Surface


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


class SomAdapter:
    def parse(
        self,
        regions: list[dict[str, Any]],
        *,
        environment_revision: str,
        screenshot_ref: str = "",
        ttl_ms: int = 2_000,
        min_confidence: float = 0.0,
    ) -> list[Affordance]:
        lease = AffordanceLease.issue(
            environment_revision=environment_revision,
            ttl_ms=ttl_ms,
            provenance=["screenshot", "som"],
        )
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
            mark_id = f"M{mark_index}"
            action = str(region.get("action", "click"))
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
                    confidence=confidence,
                    state={"ocr": region.get("ocr", "")},
                    risk=RiskLevel.LOW,
                    evidence=[screenshot_ref] if screenshot_ref else [],
                )
            )
            mark_index += 1
        return affordances

    def select(self, affordances: list[Affordance], mark_id: str) -> Affordance:
        for affordance in affordances:
            if affordance.locator.get("mark_id") == mark_id:
                return affordance
        raise KeyError(f"mark_id {mark_id!r} not present")

