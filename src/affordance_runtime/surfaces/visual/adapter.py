"""Visual-only acquisition and dispatch behind one surface adapter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.execution.contracts import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.visual.contracts import (
    VisualRegionBinding,
    project_visual_semantic_state,
)
from affordance_runtime.surfaces.visual.currentness import visual_binding_is_current
from affordance_runtime.surfaces.visual.execution import dispatch_point_activate, integer_click_point
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.visual_grounding import VisualRegionProposalRequest, VisualRegionProposerPort
from affordance_runtime.world.action_classification import classify_surface_action
from affordance_runtime.world.action_vocabulary import action_metadata
from affordance_runtime.world.contracts import (
    ActionBinding,
    CoverageState,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)

if TYPE_CHECKING:
    from affordance_runtime.browser_session import BrowserSession


@dataclass
class VisualSurfaceAdapter:
    session: BrowserSession
    proposer: VisualRegionProposerPort
    surface: str = field(default="visual", init=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)
    _observation_id: str = field(default="", init=False)
    _source_revision: str = field(default="", init=False)
    _regions: dict[str, VisualRegionBinding] = field(default_factory=dict, init=False, repr=False)

    async def reset(self, task: TaskGoal) -> None:
        self._task = task
        self.session.reset()
        self._observation_id = ""
        self._source_revision = ""
        self._regions.clear()

    async def observe(self, reason: str) -> SurfaceObservation:
        del reason
        if self._task is None:
            raise RuntimeError("Visual surface adapter must be reset before observation")
        observation_id = f"visual:{uuid.uuid4().hex}"
        frame = self.session.capture_visual_frame(observation_id)
        proposal_request = VisualRegionProposalRequest(
            observation_id,
            None,
            frame.image_bytes,
            (frame.image_width, frame.image_height),
            self._task.instruction,
        )
        proposed = tuple(self.proposer.propose(proposal_request))
        if len(proposed) > proposal_request.max_regions:
            raise ValueError("visual proposer exceeded the region bound")
        regions = tuple(
            VisualRegionBinding.from_region(frame, f"region:{index}", region)
            for index, region in enumerate(proposed)
        )
        targets = tuple(
            SemanticTarget(
                region.region_id,
                region.role,
                region.label,
                project_visual_semantic_state(dict(region.state)),
            )
            for region in regions
        )
        candidate_bindings = tuple(self._binding(self._task, frame.source_revision, region) for region in regions)
        bindings = tuple(binding for binding in candidate_bindings if binding is not None)
        self._regions = {
            binding.binding_id: region
            for binding, region in zip(candidate_bindings, regions, strict=True)
            if binding is not None
        }
        self._observation_id = observation_id
        self._source_revision = frame.source_revision
        facts = tuple(
            StateFact(f"{observation_id}:{target.target_id}:{key}", target.target_id, key, value, observation_id)
            for target in targets
            for key, value in target.state.items()
        )
        unsupported = tuple(region.primitive_action for region, binding in zip(regions, candidate_bindings, strict=True) if binding is None)
        return SurfaceObservation(
            observation_id,
            self.surface,
            frame.source_revision,
            targets,
            facts,
            bindings,
            CoverageState.COMPLETE
            if bool(getattr(self.proposer, "acquisition_exhaustive", False))
            else CoverageState.TRUNCATED,
            {"screenshot_ref": frame.screenshot_ref, "unsupported_actions": unsupported},
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        binding = request.binding
        return (
            binding.surface == self.surface
            and binding.source_observation_id == self._observation_id
            and binding.source_revision == self._source_revision
            and binding.binding_id in self._regions
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        if not self.is_current(request):
            return self._not_sent(request, ActionError.STALE_BINDING, 0)
        region = self._regions[request.binding.binding_id]
        try:
            live = self.session.capture_visual_frame(f"probe:{uuid.uuid4().hex}")
        except Exception as exc:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                self.surface,
                False,
                ActionError.CURRENTNESS_UNAVAILABLE,
                {"error_type": type(exc).__name__, "currentness_probe_count": 1},
            )
        if not visual_binding_is_current(region, live):
            return self._not_sent(request, ActionError.STALE_BINDING, 1)
        try:
            click_point = integer_click_point(region)
        except ValueError:
            return self._not_sent(request, ActionError.INVALID_PARAMETERS, 1)
        if request.binding.primitive_action != "point_activate":
            return self._not_sent(request, ActionError.UNSUPPORTED_ACTION, 1)
        try:
            dispatch_point_activate(self.session, click_point)
        except Exception as exc:
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                self.surface,
                False,
                ActionError.EXECUTION_FAILED,
                {"error_type": type(exc).__name__, "currentness_probe_count": 1},
            )
        return ActionResult(
            request.request_id,
            DispatchStatus.SENT,
            self.surface,
            True,
            adapter_evidence={"dispatched_action": request.intent.semantic_action, "currentness_probe_count": 1},
        )

    def _binding(self, task: TaskGoal, revision: str, region: VisualRegionBinding) -> ActionBinding | None:
        if region.primitive_action != "point_activate":
            return None
        try:
            metadata = action_metadata(self.surface, region.primitive_action)
        except ValueError:
            return None
        classification = classify_surface_action(task, region.role, metadata.semantic_action)
        binding_id = f"{region.source_observation_id}:{region.region_id}:{region.primitive_action}"
        return ActionBinding(
            binding_id,
            region.source_observation_id,
            region.source_observation_id,
            revision,
            region.region_fingerprint,
            region.region_id,
            region.region_id,
            self.surface,
            self.surface,
            metadata.semantic_action,
            metadata.primitive_action,
            classification.category.value,
            classification.semantic_effects,
            dict(metadata.parameter_schema),
            region.private_payload(),
            classification.observation_barrier,
            confidence=region.confidence,
            risk=classification.risk,
        )

    def _not_sent(self, request: BoundActionRequest, error: ActionError, probes: int) -> ActionResult:
        return ActionResult(
            request.request_id,
            DispatchStatus.NOT_SENT,
            self.surface,
            False,
            error,
            {"currentness_probe_count": probes},
        )
