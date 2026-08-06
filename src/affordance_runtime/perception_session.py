"""Observation acquisition collaborator for the serial Runtime Coordinator."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Protocol, Sequence

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import Affordance, Observation
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    AssertionDecision,
    GroundingCandidate,
    GroundingSource,
    PerceptionRequirements,
    SourceAssertion,
    SourceObservation,
    UnifiedAffordance,
)
from affordance_runtime.perception import (
    PerceptionEscalation,
    derive_perception_requirements,
    perception_task_terms,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.unified_observation import (
    CoverageCompleteness,
    CoverageStatus,
    SourceCoverage,
)


@dataclass(frozen=True)
class PerceptionCapture:
    """One acquisition epoch; never the Runtime semantic authority."""

    observation: Observation
    affordances: tuple[Affordance, ...] = ()
    source_observations: tuple[SourceObservation, ...] = ()
    source_coverage: tuple[SourceCoverage, ...] = ()
    grounding_candidates: tuple[GroundingCandidate, ...] = ()
    semantic_targets: tuple[UnifiedAffordance, ...] = ()
    source_assertions: tuple[SourceAssertion, ...] = ()
    assertion_decisions: tuple[AssertionDecision, ...] = ()
    active_perception_requests: tuple[ActivePerceptionRequest, ...] = ()
    accessibility_tree: object | None = None
    svg_geometry: object | None = None
    perception_requirements: PerceptionRequirements | None = None
    acquisition_payload: object | None = None

    @property
    def unified_affordances(self) -> tuple[UnifiedAffordance, ...]:
        """Acquisition-only compatibility name; never canonical authority."""

        return self.semantic_targets

    @property
    def affordance_model(self) -> object:
        payload = self.acquisition_payload
        model = getattr(payload, "affordance_model", None)
        if model is None:
            raise AttributeError("capture has no adapter-specific affordance model")
        return model

    @classmethod
    def from_browser_snapshot(cls, snapshot: BrowserSnapshot) -> PerceptionCapture:
        coverage = _derive_source_coverage(snapshot)
        return cls(
            observation=snapshot.observation,
            affordances=tuple(snapshot.affordance_model.affordances),
            source_observations=tuple(snapshot.source_observations),
            source_coverage=coverage,
            grounding_candidates=tuple(snapshot.grounding_candidates),
            semantic_targets=tuple(snapshot.unified_affordances),
            source_assertions=tuple(snapshot.source_assertions),
            assertion_decisions=tuple(snapshot.assertion_decisions),
            active_perception_requests=tuple(snapshot.active_perception_requests),
            accessibility_tree=snapshot.accessibility_tree,
            svg_geometry=snapshot.svg_geometry,
            perception_requirements=snapshot.perception_requirements,
            acquisition_payload=snapshot,
        )


def _derive_source_coverage(snapshot: BrowserSnapshot) -> tuple[SourceCoverage, ...]:
    observed_sources = {item.source for item in snapshot.source_observations}
    nested_candidates = tuple(
        candidate for target in snapshot.unified_affordances for candidate in target.grounding_candidates
    )
    candidates = (*snapshot.grounding_candidates, *nested_candidates)
    affordance_sources = tuple(_affordance_grounding_source(item) for item in snapshot.affordance_model.affordances)
    observed_sources.update(affordance_sources)
    candidate_count = {source: sum(1 for item in candidates if item.source == source) for source in GroundingSource}
    for source in affordance_sources:
        candidate_count[source] += 1
    coverage: list[SourceCoverage] = []
    for source in GroundingSource:
        if source in observed_sources or candidate_count[source] > 0:
            coverage.append(
                SourceCoverage.complete(
                    source,
                    captured_item_count=candidate_count[source],
                    capture_policy_id="browser-session",
                )
            )
        else:
            coverage.append(
                SourceCoverage(
                    source=source,
                    capture_policy_id="browser-session",
                    captured_item_count=0,
                    truncated=False,
                    omitted_item_count_estimate=None,
                    completeness=CoverageCompleteness.UNKNOWN,
                    status=CoverageStatus.SOURCE_NOT_ACQUIRED,
                )
            )
    return tuple(coverage)


def _affordance_grounding_source(affordance: Affordance) -> GroundingSource:
    if affordance.surface.value == "visual" and affordance.locator.get("mark_id"):
        return GroundingSource.SOM
    return GroundingSource(affordance.surface.value)


class ObservationSource(Protocol):
    def capture(self) -> BrowserSnapshot | PerceptionCapture: ...


@dataclass(frozen=True)
class PerceptionCaptureRequest:
    envelope: RunRequest
    sequence: int
    active_subgoal: StepSpec | str = ""
    failed_sources: frozenset[GroundingSource] = frozenset()

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("perception capture sequence must be positive")


@dataclass(frozen=True)
class PerceptionSession:
    """Prepare coherent observations without mutating authoritative run state."""

    observer: ObservationSource
    artifacts: ArtifactStore | None = None

    def capture(
        self,
        request: PerceptionCaptureRequest,
    ) -> PerceptionCapture:
        envelope = request.envelope
        if not isinstance(self.observer, BrowserSession):
            return _as_perception_capture(self.observer.capture())

        active_subgoal = request.active_subgoal
        escalation = self.perception_escalation(request.failed_sources)
        requirements = (
            derive_perception_requirements(
                envelope.task_spec,
                active_subgoal=active_subgoal,
                escalation=escalation,
            )
            if envelope.task_spec is not None
            else None
        )
        screenshot_path = None
        if self.artifacts is not None:
            screenshot_path = (
                self.artifacts.run_dir(envelope.task_id) / "screenshots" / f"screenshot_{request.sequence:04d}.png"
            )
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.observer.capture(
            screenshot_path=str(screenshot_path) if screenshot_path is not None else None,
            perception_requirements=requirements,
            task_terms=(
                perception_task_terms(
                    envelope.task_spec,
                    active_subgoal=active_subgoal,
                )
                if envelope.task_spec is not None
                else ()
            ),
            task_instruction=(
                " ".join(
                    dict.fromkeys(
                        item
                        for item in (
                            envelope.task_spec.objective,
                            active_subgoal.objective if isinstance(active_subgoal, StepSpec) else active_subgoal or "",
                        )
                        if item
                    )
                )
                if envelope.task_spec is not None
                else envelope.goal
            ),
        )
        if screenshot_path is not None and self.artifacts is not None:
            if not screenshot_path.exists():
                screenshot_path.write_bytes(self.observer.screenshot())
            self.artifacts.register_file(envelope.task_id, screenshot_path, "image/png")
        return PerceptionCapture.from_browser_snapshot(snapshot)

    @property
    def supports_targeted_capture(self) -> bool:
        return callable(getattr(self.observer, "capture_targeted", None))

    def capture_targeted(
        self,
        requests: Sequence[ActivePerceptionRequest],
    ) -> PerceptionCapture:
        capture = getattr(self.observer, "capture_targeted", None)
        if not callable(capture):
            raise TypeError("observation source has no capture_targeted port")
        captured = capture(requests)
        if inspect.isawaitable(captured):
            captured = resolve_awaitable(captured)
        snapshot = _as_perception_capture(captured)
        epoch_id = snapshot.observation.snapshot_id
        if not epoch_id:
            raise ValueError("targeted perception requires a non-empty observation epoch")
        if any(item.observation_epoch_id != epoch_id for item in snapshot.source_observations):
            raise ValueError("targeted source observations must share one coherent epoch")
        if any(item.observation_epoch_id != epoch_id for item in snapshot.source_assertions):
            raise ValueError("targeted source assertions must share one coherent epoch")
        if any(item.observation_epoch_id != epoch_id for item in snapshot.grounding_candidates):
            raise ValueError("targeted grounding candidates must share one coherent epoch")
        return snapshot

    @staticmethod
    def perception_escalation(
        failed_sources: frozenset[GroundingSource],
    ) -> PerceptionEscalation | None:
        if not failed_sources:
            return None
        return PerceptionEscalation(
            reason="previous grounding route failed before a verified effect",
            failed_sources=frozenset(failed_sources),
        )


def _as_perception_capture(value: object) -> PerceptionCapture:
    if isinstance(value, PerceptionCapture):
        return value
    if isinstance(value, BrowserSnapshot):
        return PerceptionCapture.from_browser_snapshot(value)
    raise TypeError("observation source must return PerceptionCapture or BrowserSnapshot")
