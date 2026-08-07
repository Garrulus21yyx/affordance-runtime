"""Observation acquisition collaborator for the serial Runtime Coordinator."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Protocol, Sequence, cast
from uuid import uuid4

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import Affordance, Observation
from affordance_runtime.execution_context import (
    CoordinateBinding,
    ExecutionContextRequirementRef,
    ExecutorCapabilityDescriptor,
    LiveSurfaceBinding,
    issue_surface_binding,
)
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
    CoverageTermination,
    SourceCoverage,
)
from affordance_runtime.verification.contracts import PredicateEvidence


class AcquisitionAffordanceModel(Protocol):
    affordances: tuple[Affordance, ...]


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
    live_surface_binding: LiveSurfaceBinding | None = None
    coordinate_binding: CoordinateBinding | None = None
    capability_descriptor: ExecutorCapabilityDescriptor | None = None
    predicate_evidence: tuple[PredicateEvidence, ...] = ()

    @property
    def unified_affordances(self) -> tuple[UnifiedAffordance, ...]:
        """Acquisition-only compatibility name; never canonical authority."""

        return self.semantic_targets

    @property
    def affordance_model(self) -> AcquisitionAffordanceModel:
        payload = self.acquisition_payload
        model = getattr(payload, "affordance_model", None)
        if model is None:
            raise AttributeError("capture has no adapter-specific affordance model")
        return cast(AcquisitionAffordanceModel, model)

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
            predicate_evidence=tuple(snapshot.predicate_evidence),
            acquisition_payload=snapshot,
        )


def _derive_source_coverage(snapshot: BrowserSnapshot) -> tuple[SourceCoverage, ...]:
    if snapshot.source_coverage:
        return snapshot.source_coverage
    observed_sources = {item.source for item in snapshot.source_observations}
    coverage: list[SourceCoverage] = []
    for source in GroundingSource:
        if (
            source == GroundingSource.DOM
            and bool(getattr(snapshot.affordance_model, "acquisition_exhaustive", False))
            and bool(getattr(snapshot.affordance_model, "acquisition_adapter_id", ""))
        ):
            coverage.append(
                SourceCoverage.complete(
                    source,
                    captured_item_count=int(getattr(snapshot.affordance_model, "kept_node_count", 0)),
                    capture_policy_id="dom-full-document@v1",
                    acquisition_epoch_ref=snapshot.observation.snapshot_id,
                    source_scope="full-document-dom",
                    adapter_version=str(snapshot.affordance_model.acquisition_adapter_id),
                )
            )
            continue
        source_records = tuple(item for item in snapshot.source_observations if item.source == source)
        if source_records:
            if all(item.acquisition_exhaustive and item.source_scope for item in source_records):
                coverage.append(
                    SourceCoverage.complete(
                        source,
                        captured_item_count=len(source_records),
                        capture_policy_id="+".join(sorted({item.parser_id for item in source_records})),
                        acquisition_epoch_ref=snapshot.observation.snapshot_id,
                        source_scope="+".join(sorted({item.source_scope for item in source_records})),
                        adapter_version="source-observation@v2",
                    )
                )
                continue
            coverage.append(
                SourceCoverage(
                    source=source,
                    capture_policy_id="+".join(sorted({item.parser_id for item in source_records})),
                    captured_item_count=len(source_records),
                    truncated=False,
                    omitted_item_count_estimate=None,
                    completeness=CoverageCompleteness.BOUNDED,
                    status=CoverageStatus.OBSERVED,
                    acquisition_epoch_ref=snapshot.observation.snapshot_id,
                    source_scope="adapter-declared-bounded-source",
                    adapter_version="source-observation@v1",
                    termination_reason=CoverageTermination.LIMIT_REACHED,
                )
            )
            continue
        coverage.append(
            SourceCoverage(
                source=source,
                capture_policy_id="legacy-browser-snapshot-unknown",
                captured_item_count=0,
                truncated=False,
                omitted_item_count_estimate=None,
                completeness=CoverageCompleteness.UNKNOWN,
                status=(CoverageStatus.OBSERVED if source in observed_sources else CoverageStatus.SOURCE_NOT_ACQUIRED),
                acquisition_epoch_ref=snapshot.observation.snapshot_id,
                source_scope="unspecified",
                adapter_version="legacy-snapshot@v1",
                termination_reason=CoverageTermination.UNKNOWN,
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


@dataclass
class PerceptionSession:
    """Prepare coherent observations without mutating authoritative run state."""

    observer: ObservationSource
    artifacts: ArtifactStore | None = None
    capability_descriptor: ExecutorCapabilityDescriptor | None = None
    session_generation: str = field(default_factory=lambda: f"session:{uuid4().hex}")
    _last_context_requirement: ExecutionContextRequirementRef | None = field(default=None, init=False, repr=False)
    _last_run_id: str = field(default="", init=False, repr=False)
    _current_surface_binding: LiveSurfaceBinding | None = field(default=None, init=False, repr=False)
    _current_coordinate_binding: CoordinateBinding | None = field(default=None, init=False, repr=False)
    _surface_lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def capture(
        self,
        request: PerceptionCaptureRequest,
    ) -> PerceptionCapture:
        envelope = request.envelope
        self._last_context_requirement = envelope.execution_context_requirement
        self._last_run_id = envelope.task_id
        if not isinstance(self.observer, BrowserSession):
            return self._bind_runtime_context(_as_perception_capture(self.observer.capture()), envelope)

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
        return self._bind_runtime_context(PerceptionCapture.from_browser_snapshot(snapshot), envelope)

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
        if self._last_context_requirement is None or not self._last_run_id:
            return snapshot
        return self._bind_runtime_context(
            snapshot,
            _ContextEnvelope(self._last_run_id, self._last_context_requirement),
        )

    def _bind_runtime_context(
        self,
        capture: PerceptionCapture,
        envelope: RunRequest | _ContextEnvelope,
    ) -> PerceptionCapture:
        observation = capture.observation
        metadata = observation.metadata
        requirement = envelope.execution_context_requirement
        run_id = envelope.task_id
        frame_id = str(metadata.get("frame_id") or "frame:top")
        document_generation = str(metadata.get("document_generation") or observation.page_revision)
        binding = issue_surface_binding(
            requirement,
            run_id=run_id,
            session_generation=self.session_generation,
            window_id=str(metadata.get("window_id") or "window:primary"),
            tab_id=str(metadata.get("tab_id") or "tab:primary"),
            frame_id=frame_id,
            document_generation=document_generation,
            focus_generation=str(metadata.get("focus_generation") or metadata.get("active_control") or "focus:default"),
            issued_at_s=observation.observed_at_s,
        )
        viewport = metadata.get("viewport_size")
        width, height = (viewport if isinstance(viewport, (list, tuple)) and len(viewport) == 2 else (1, 1))
        scroll = metadata.get("scroll_xy")
        scroll_xy = scroll if isinstance(scroll, (list, tuple)) and len(scroll) == 2 else (0.0, 0.0)
        coordinate = CoordinateBinding(
            screenshot_ref=observation.screenshot_ref,
            viewport_width=max(1, int(width)),
            viewport_height=max(1, int(height)),
            crop_xywh=tuple(metadata.get("crop_xywh") or (0.0, 0.0, float(width), float(height))),
            scroll_xy=(float(scroll_xy[0]), float(scroll_xy[1])),
            device_pixel_ratio=float(metadata.get("device_pixel_ratio") or 1.0),
            zoom=float(metadata.get("zoom") or 1.0),
            scale=float(metadata.get("scale") or 1.0),
            orientation=str(metadata.get("orientation") or "landscape"),
            origin=str(metadata.get("coordinate_origin") or "viewport-top-left"),
            frame_id=frame_id,
            document_generation=document_generation,
        )
        bound = replace(
            capture,
            live_surface_binding=binding,
            coordinate_binding=coordinate,
            capability_descriptor=self.capability_descriptor,
        )
        with self._surface_lock:
            self._current_surface_binding = binding
            self._current_coordinate_binding = coordinate
        return bound

    def surface_is_current(self, expected: LiveSurfaceBinding) -> bool:
        """Check the live identity fence, not merely the lease embedded in a contract."""

        with self._surface_lock:
            current = self._current_surface_binding
            stored_current = current is not None and current.digest == expected.digest
        if not stored_current:
            return False
        probe = getattr(self.observer, "surface_binding_is_current", None)
        if callable(probe):
            try:
                return bool(probe(expected))
            except (RuntimeError, TypeError, ValueError):
                return False
        return not isinstance(self.observer, BrowserSession)

    @property
    def surface_lock(self) -> RLock:
        """Shared owner lock used to fence the final live-provider call."""

        return self._surface_lock

    def coordinate_is_current(self, expected: CoordinateBinding, *, require_live_probe: bool) -> bool:
        """Compare the sealed transform with current adapter-owned geometry."""

        with self._surface_lock:
            current = self._current_coordinate_binding
            if current is None or current.transform_digest != expected.transform_digest:
                return False
        if not require_live_probe:
            return True
        probe = getattr(self.observer, "coordinate_transform_is_current", None)
        if not callable(probe):
            return False
        try:
            return bool(probe(expected))
        except (RuntimeError, TypeError, ValueError):
            return False

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


@dataclass(frozen=True)
class _ContextEnvelope:
    task_id: str
    execution_context_requirement: ExecutionContextRequirementRef
