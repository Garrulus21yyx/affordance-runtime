"""BrowserGym observation capture and adapter-owned grounding enrichment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.benchmarks.browsergym_types import (
    BROWSERGYM_BACKEND,
    BrowserGymEpisodeState,
)
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import Affordance, AffordanceLease, RiskLevel, Surface
from affordance_runtime.grounding import ActivePerceptionRequest, GroundingCandidate, PerceptionRequirements
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)


@dataclass
class BrowserGymObserver:
    """Capture one coherent BrowserGym epoch and enrich adapter geometry."""

    session: BrowserSession
    episode: BrowserGymEpisodeState
    screenshot_dir: Path
    perception_requirements: PerceptionRequirements | None = None
    task_terms: tuple[str, ...] = ()
    sequence: int = 0
    lease_ttl_ms: int = 120_000
    max_capture_attempts: int = 2

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot = self.screenshot_dir / f"observation-{self.sequence:04d}.png"
        for attempt in range(1, self.max_capture_attempts + 1):
            try:
                snapshot = self.session.capture(
                    page_id=self.episode.task_id,
                    ttl_ms=self.lease_ttl_ms,
                    screenshot_path=str(screenshot),
                    perception_requirements=self.perception_requirements,
                    task_terms=self.task_terms,
                    task_instruction=self.episode.goal,
                )
                break
            except RuntimeError as exc:
                if "coherent observation epoch drifted" not in str(exc) or attempt >= self.max_capture_attempts:
                    raise
        else:  # pragma: no cover - loop either returns or raises
            raise RuntimeError("BrowserGym observation capture did not produce a snapshot")
        return self._attach_browsergym_metadata(snapshot, capture_attempt=attempt)

    def capture_targeted(
        self,
        requests: Sequence[ActivePerceptionRequest],
    ) -> BrowserSnapshot:
        snapshot = self.session.capture_targeted(tuple(requests))
        return self._attach_browsergym_metadata(
            snapshot,
            capture_attempt=1,
            capture_mode="targeted",
        )

    def _attach_browsergym_metadata(
        self,
        snapshot: BrowserSnapshot,
        *,
        capture_attempt: int,
        capture_mode: str = "full",
    ) -> BrowserSnapshot:
        metadata = {
            **snapshot.observation.metadata,
            "browsergym": {
                "goal": self.episode.goal,
                "reward": self.episode.reward,
                "terminated": self.episode.terminated,
                "truncated": self.episode.truncated,
                "task_info": json_safe(self.episode.info.get("task_info", {})),
                "capture_attempt": capture_attempt,
                "capture_mode": capture_mode,
            },
        }
        observation = replace(snapshot.observation, metadata=metadata)
        return self._attach_drag_geometry(replace(snapshot, observation=observation))

    def _attach_drag_geometry(self, snapshot: BrowserSnapshot) -> BrowserSnapshot:
        drag_affordances = [item for item in snapshot.affordance_model.affordances if item.action == "drag"]
        gesture_affordances = [
            item for item in snapshot.affordance_model.affordances if item.action in {"drag", "drop"}
        ]
        boxes = self.session.bounding_boxes_for_selectors(
            {
                str(item.locator.get("backend_handle") or ""): str(
                    item.locator.get("selector") or ""
                )
                for item in gesture_affordances
                if item.locator.get("backend_handle") and item.locator.get("selector")
            }
        )
        if not boxes:
            return snapshot
        sortable_position = {
            item.id: (index, len(drag_affordances))
            for index, item in enumerate(drag_affordances, start=1)
        }
        areas = {
            item.id: boxes[str(item.locator.get("backend_handle") or "")][2]
            * boxes[str(item.locator.get("backend_handle") or "")][3]
            for item in drag_affordances
            if str(item.locator.get("backend_handle") or "") in boxes
        }
        relative_sizes: dict[str, str] = {}
        inside_largest: set[str] = set()
        if len(set(areas.values())) > 1:
            smallest = min(areas.values())
            largest = max(areas.values())
            relative_sizes = {
                item_id: "smallest" if area == smallest else "largest" if area == largest else ""
                for item_id, area in areas.items()
            }
            smallest_ids = [item_id for item_id, area in areas.items() if area == smallest]
            largest_ids = [item_id for item_id, area in areas.items() if area == largest]
            if len(smallest_ids) == 1 and len(largest_ids) == 1:
                by_id = {item.id: item for item in drag_affordances}
                source = boxes[str(by_id[smallest_ids[0]].locator.get("backend_handle") or "")]
                destination = boxes[str(by_id[largest_ids[0]].locator.get("backend_handle") or "")]
                if (
                    source[0] > destination[0]
                    and source[1] > destination[1]
                    and source[0] + source[2] < destination[0] + destination[2]
                    and source[1] + source[3] < destination[1] + destination[3]
                ):
                    inside_largest.add(smallest_ids[0])
        affordances: list[Affordance] = []
        for item in snapshot.affordance_model.affordances:
            backend_handle = str(item.locator.get("backend_handle") or "")
            box = boxes.get(backend_handle)
            if box is None:
                affordances.append(item)
                continue
            fingerprint = "sha256:" + hashlib.sha256(
                f"{item.target_fingerprint}\0{box}".encode("utf-8")
            ).hexdigest()
            affordances.append(
                replace(
                    item,
                    locator={
                        **item.locator,
                        "bbox": list(box),
                        "coordinate_space": "viewport_pixels",
                        **(
                            {
                                "sortable_index": sortable_position[item.id][0],
                                "sortable_count": sortable_position[item.id][1],
                            }
                            if item.id in sortable_position
                            else {}
                        ),
                    },
                    state={
                        **item.state,
                        **(
                            {"relative_size": relative_sizes[item.id]}
                            if relative_sizes.get(item.id)
                            else {}
                        ),
                        **({"inside_largest": True} if item.id in inside_largest else {}),
                    },
                    lease=replace(item.lease, target_fingerprint=fingerprint),
                )
            )
        model = replace(snapshot.affordance_model, affordances=affordances)
        refreshed = replace(
            snapshot,
            observation=replace(
                snapshot.observation,
                target_fingerprints={item.id: item.target_fingerprint for item in affordances},
            ),
            affordance_model=model,
        )
        return refresh_dom_grounding_candidates(refreshed)


def visual_fallback_affordance(snapshot: BrowserSnapshot) -> Affordance | None:
    """Offer one screenshot-bound target only when structured controls are absent."""

    screenshot_ref = snapshot.observation.screenshot_ref
    if not screenshot_ref or snapshot.affordance_model.affordances:
        return None
    try:
        screenshot_digest = hashlib.sha256(Path(screenshot_ref).read_bytes()).hexdigest()
    except OSError:
        screenshot_digest = "artifact-unavailable"
    fingerprint = (
        "sha256:"
        + hashlib.sha256(
            f"{snapshot.observation.page_revision}\0{screenshot_digest}".encode("utf-8")
        ).hexdigest()
    )
    return Affordance(
        id="visual_current_screenshot",
        surface=Surface.VISUAL,
        role="button",
        label="current screenshot visual target",
        action="point_activate",
        locator={"screenshot_ref": screenshot_ref, "coordinate_space": "screenshot_pixels"},
        lease=AffordanceLease.issue(
            environment_revision=snapshot.observation.environment_revision,
            ttl_ms=120_000,
            provenance=["browsergym", "screenshot"],
            snapshot_id=snapshot.observation.snapshot_id,
            page_revision=snapshot.observation.page_revision,
            target_fingerprint=fingerprint,
        ),
        backend_candidates=[BROWSERGYM_BACKEND],
        confidence=0.0,
        risk=RiskLevel.LOW,
        evidence=[screenshot_ref],
    )


def refresh_dom_grounding_candidates(snapshot: BrowserSnapshot) -> BrowserSnapshot:
    """Rebind DOM candidates after observer enrichment changes target identity."""

    existing_by_source = {
        candidate.source_affordance_id: candidate
        for candidate in snapshot.grounding_candidates
        if candidate.source_affordance_id
    }
    descriptors: list[CandidateDescriptor] = []
    for affordance in snapshot.affordance_model.affordances:
        candidate: GroundingCandidate | None
        if affordance.surface in {Surface.DOM, Surface.ACCESSIBILITY}:
            candidate = candidate_from_affordance(
                affordance,
                snapshot.observation,
                semantic_target_id="pending",
                compatible_executor=BROWSERGYM_BACKEND,
            )
        else:
            candidate = existing_by_source.get(affordance.id)
        if candidate is None:
            continue
        descriptors.append(
            CandidateDescriptor(
                role=affordance.role,
                label=affordance.label,
                action=affordance.action,
                container_context=str(affordance.state.get("container_context") or ""),
                candidate=candidate,
            )
        )
    unified = SemanticEntityResolver().resolve(descriptors)
    candidates = tuple(candidate for target in unified for candidate in target.grounding_candidates)
    return replace(
        snapshot,
        observation=replace(
            snapshot.observation,
            target_fingerprints={
                **snapshot.observation.target_fingerprints,
                **candidate_fingerprints(unified),
            },
        ),
        grounding_candidates=candidates,
        unified_affordances=unified,
    )


def fuse_visual_candidates(
    snapshot: BrowserSnapshot,
    affordances: list[Affordance],
    image_size: tuple[int, int],
) -> BrowserSnapshot:
    """Fuse adapter-produced visual candidates into the coherent epoch."""

    descriptors: list[CandidateDescriptor] = []
    linked_affordances: list[Affordance] = []
    existing_candidates = {
        candidate.source_affordance_id: candidate
        for candidate in snapshot.grounding_candidates
        if candidate.source_affordance_id
    }
    for affordance in snapshot.affordance_model.affordances:
        candidate = existing_candidates.get(affordance.id)
        if candidate is None:
            continue
        descriptors.append(
            CandidateDescriptor(
                role=affordance.role,
                label=affordance.label,
                action=affordance.action,
                container_context=str(affordance.state.get("container_context") or ""),
                candidate=candidate,
            )
        )
    for affordance in affordances:
        candidate = candidate_from_affordance(
            affordance,
            snapshot.observation,
            semantic_target_id="pending",
            image_size=image_size,
        )
        descriptors.append(
            CandidateDescriptor(
                role=affordance.role,
                label=affordance.label,
                action=affordance.action,
                container_context=str(affordance.state.get("container_context") or ""),
                candidate=candidate,
            )
        )
        linked_affordances.append(
            replace(
                affordance,
                locator={**affordance.locator, "grounding_candidate_id": candidate.candidate_id},
            )
        )
    unified = SemanticEntityResolver().resolve(descriptors)
    candidates = tuple(candidate for target in unified for candidate in target.grounding_candidates)
    return replace(
        snapshot,
        observation=replace(
            snapshot.observation,
            target_fingerprints={
                **snapshot.observation.target_fingerprints,
                **{item.id: item.target_fingerprint for item in linked_affordances},
                **candidate_fingerprints(unified),
            },
        ),
        affordance_model=replace(
            snapshot.affordance_model,
            affordances=[*snapshot.affordance_model.affordances, *linked_affordances],
            kept_node_count=len(snapshot.affordance_model.affordances) + len(linked_affordances),
        ),
        grounding_candidates=candidates,
        unified_affordances=unified,
    )


def json_safe(value: Any) -> Any:
    """Convert adapter metadata to JSON-safe values without executing it."""

    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        return str(value)
