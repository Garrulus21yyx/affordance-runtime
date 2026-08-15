"""Reusable BrowserGym WorldEnvironment with active typed acquisition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import Callable, Protocol

from affordance_runtime.execution import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.browsergym.acquisition import (
    episode_identity,
    failed_acquisition,
    not_sent_outcome,
    page_identity,
    probe_episode,
    source_revision,
    task_info,
)
from affordance_runtime.surfaces.browsergym.binding import (
    BrowserGymBindingStore,
    BrowserGymElementBinding,
    BrowserGymPrivateBinding,
    BrowserGymVisualBinding,
)
from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessContext,
    BrowserGymCurrentnessDecision,
    BrowserGymCurrentnessReason,
    BrowserGymCurrentnessStatus,
    compare_browsergym_currentness,
    unavailable_currentness,
)
from affordance_runtime.surfaces.browsergym.diagnostics import (
    BrowserGymDiagnosticSnapshot,
    diagnostic_snapshot,
)
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.execution import browsergym_action
from affordance_runtime.surfaces.browsergym.projection import (
    BrowserGymProjection,
    project_browsergym_observation,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    BrowserGymSemanticError,
    canonical_control_for_bid,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BrowserGymTaskStateSnapshot,
    BrowserGymTaskStateSource,
    task_state_from_probe,
    task_state_from_transition,
)
from affordance_runtime.surfaces.browsergym.visual_disambiguation import (
    project_browsergym_visual_disambiguation_source,
)
from affordance_runtime.surfaces.browsergym.visual_projection import (
    VisualCorrespondenceStatus,
    browsergym_visual_frame,
    project_browsergym_screenshot_source,
    project_browsergym_visual_source,
)
from affordance_runtime.surfaces.visual.currentness import visual_binding_is_current
from affordance_runtime.surfaces.visual.disambiguation import VisualCandidateDisambiguatorPort
from affordance_runtime.surfaces.visual.grounding import (
    VisualGrounderPort,
    VisualProviderFailure,
    VisualProviderFailureCode,
    VisualProviderStage,
    VisualRegionProposerPort,
    classify_visual_provider_failure,
)
from affordance_runtime.surfaces.visual.predicate_classification import VisualPredicateClassifierPort
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationOffer,
    ObservationPurpose,
    ObservationRequestKind,
    ObservationSelectionPlan,
    SelectedObservationRequest,
    SourceAcquisitionResult,
    SourceAcquisitionStatus,
    SourceRequirement,
    VisionEvidenceNeed,
    WorldObservationRequest,
    selected_observation_requests,
)
from affordance_runtime.world.fusion import FusionStatus, WorldFusion
from affordance_runtime.world.observation_orchestrator import ObservationOrchestrator


class BrowserGymPort(Protocol):
    supports_capture_current: bool

    def reset(self, *, seed: int) -> tuple[dict[str, object], dict[str, object]]: ...
    def step(self, action: str) -> tuple[dict[str, object], object, object, object, dict[str, object]]: ...
    def capture_current(self) -> tuple[dict[str, object], dict[str, object]]: ...
    def currentness_probe(self, bid: str) -> object: ...
    def close(self) -> None: ...


@dataclass
class BrowserGymEnvironment:
    task_id: str
    seed: int
    gym_environment: BrowserGymPort
    task_run_id: str
    goal_instruction: str
    _prepared_initial_raw: dict[str, object] | None
    _prepared_task_info: dict[str, object]
    _page_identity: str
    _episode_identity: str
    visual_region_proposer: VisualRegionProposerPort | None = field(default=None, repr=False)
    visual_point_grounder: VisualGrounderPort | None = field(default=None, repr=False)
    visual_candidate_disambiguator: VisualCandidateDisambiguatorPort | None = field(
        default=None,
        repr=False,
    )
    visual_predicate_classifier: VisualPredicateClassifierPort | None = field(default=None, repr=False)
    marked_candidate_policy_available: bool = False
    bindings: BrowserGymBindingStore = field(default_factory=BrowserGymBindingStore)
    dispatched_request_ids: list[str] = field(default_factory=list)
    backend_reset_calls: int = 1
    logical_reset_calls: int = 0
    reset_calls: int = 1
    capture_calls: int = 0
    step_calls: int = 0
    probe_calls: int = 0
    currentness_probe_latencies_ms: list[float] = field(default_factory=list)
    full_observation_count: int = 0
    dom_action_calls: int = 0
    fill_calls: int = 0
    select_calls: int = 0
    visual_proposer_calls: int = 0
    visual_point_grounder_calls: int = 0
    visual_point_grounder_success_count: int = 0
    visual_disambiguator_calls: int = 0
    visual_disambiguator_selection_count: int = 0
    visual_predicate_classifier_calls: int = 0
    visual_predicate_assessment_count: int = 0
    visual_provider_failure_count: int = 0
    visual_provider_structured_output_failure_count: int = 0
    visual_provider_abstained_count: int = 0
    visual_provider_transport_failure_count: int = 0
    visual_provider_other_failure_count: int = 0
    visual_point_grounding_failure_count: int = 0
    visual_region_proposal_failure_count: int = 0
    visual_candidate_disambiguation_failure_count: int = 0
    visual_predicate_classification_failure_count: int = 0
    visual_provider_failures: list[VisualProviderFailure] = field(default_factory=list)
    structural_source_acquired_count: int = 0
    visual_source_acquired_count: int = 0
    visual_binding_acquired_count: int = 0
    visual_gate_selected_count: int = 0
    visual_gate_skipped_count: int = 0
    visual_correspondence_matched_count: int = 0
    visual_correspondence_unmatched_count: int = 0
    visual_correspondence_ambiguous_count: int = 0
    visual_correspondence_conflict_count: int = 0
    structural_binding_dispatch_count: int = 0
    visual_binding_dispatch_count: int = 0
    _observation_serial: int = 0
    _current_observation_id: str = ""
    _current_source_revision: str = ""
    _task_state: BrowserGymTaskStateSnapshot | None = None
    _diagnostic: BrowserGymDiagnosticSnapshot | None = None
    _task: TaskGoal | None = None
    _terminated: bool = False
    _closed: bool = False
    last_currentness_decision: BrowserGymCurrentnessDecision | None = None
    observation_orchestrator: ObservationOrchestrator = field(default_factory=ObservationOrchestrator)
    entity_identity: BrowserGymEntityIdentityMap = field(
        default_factory=BrowserGymEntityIdentityMap,
        repr=False,
    )

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        group = f"browsergym:{self.task_run_id}"
        visual_purposes = [ObservationPurpose.WORLD_GROUNDING]
        if self.visual_region_proposer is not None:
            visual_purposes.extend((
                ObservationPurpose.ENTITY_DISCOVERY,
                ObservationPurpose.EFFECT_VERIFICATION,
                ObservationPurpose.CRITERION_VERIFICATION,
            ))
        if self.visual_candidate_disambiguator is not None or self.marked_candidate_policy_available:
            visual_purposes.append(ObservationPurpose.TARGET_DISAMBIGUATION)
        return (
            ObservationOffer("browsergym", "structural", "structural", "medium", group),
            ObservationOffer(
                "browsergym_visual",
                "visual",
                "weak",
                "medium",
                group,
                tuple(visual_purposes),
            ),
        )

    @property
    def observation_capabilities(self) -> ObservationCapabilities:
        independent = bool(getattr(self.gym_environment, "supports_capture_current", False))
        return ObservationCapabilities(independent, True, self.observation_offers)

    @classmethod
    def open(
        cls,
        task_id: str,
        seed: int,
        *,
        gym_factory: Callable[..., BrowserGymPort] | None = None,
        visual_region_proposer: VisualRegionProposerPort | None = None,
        visual_point_grounder: VisualGrounderPort | None = None,
        visual_candidate_disambiguator: VisualCandidateDisambiguatorPort | None = None,
        visual_predicate_classifier: VisualPredicateClassifierPort | None = None,
        marked_candidate_policy_available: bool = False,
    ) -> BrowserGymEnvironment:
        if not task_id.strip():
            raise ValueError("BrowserGym task ID must be nonempty")
        if gym_factory is None:
            from affordance_runtime.surfaces.browsergym.backend import ThreadBoundBrowserGym

            gym_factory = ThreadBoundBrowserGym
        gym_environment = gym_factory(task_id, headless=True)
        try:
            raw, info = gym_environment.reset(seed=seed)
            prepared_info = task_info(info)
            goal = raw.get("goal") if isinstance(raw, dict) else None
            if not isinstance(goal, str) or not goal.strip():
                raise RuntimeError("BrowserGym reset omitted the public task instruction")
            environment = cls(
                task_id=task_id,
                seed=seed,
                gym_environment=gym_environment,
                task_run_id=f"run:{uuid.uuid4().hex}",
                goal_instruction=goal,
                _prepared_initial_raw=raw,
                _prepared_task_info=prepared_info,
                _page_identity=page_identity(raw),
                _episode_identity=episode_identity(prepared_info),
                visual_region_proposer=visual_region_proposer,
                visual_point_grounder=visual_point_grounder,
                visual_candidate_disambiguator=visual_candidate_disambiguator,
                visual_predicate_classifier=visual_predicate_classifier,
                marked_candidate_policy_available=marked_candidate_policy_available,
            )
            return environment
        except BaseException:
            gym_environment.close()
            raise

    async def reset(self, task: TaskGoal) -> ObservationAcquisition:
        self.logical_reset_calls += 1
        if self._closed or self._prepared_initial_raw is None or self.logical_reset_calls != 1:
            return failed_acquisition(AcquisitionOrigin.RESET, "prepared_initial_observation_unavailable")
        if task.instruction != self.goal_instruction:
            raise ValueError("TaskGoal instruction must be the public BrowserGym goal")
        self._task = task
        self.bindings.clear()
        self.dispatched_request_ids.clear()
        raw = self._prepared_initial_raw
        self._prepared_initial_raw = None
        observation_id, revision = self._next_identity()
        snapshot = task_state_from_transition(
            task_run_id=self.task_run_id,
            observation_id=observation_id,
            source_observation_id=observation_id,
            source=BrowserGymTaskStateSource.RESET,
            reward=0.0,
            terminated=False,
            truncated=False,
            task_info=self._prepared_task_info,
        )
        request = WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST,
            "initial task grounding",
        )
        selection = self.observation_orchestrator.select(self.observation_offers, request)
        if selection.plan is None:
            return ObservationAcquisition(
                selection.status,
                AcquisitionOrigin.RESET,
                None,
                selection.reason_code,
            )
        return self._project(
            raw,
            snapshot,
            AcquisitionOrigin.RESET,
            observation_id,
            revision,
            selection.plan,
            request,
            selected_observation_requests(
                selection.plan, request, self.observation_offers, observation_id
            ),
        )

    async def revise_task(self, task: TaskGoal) -> None:
        if self._closed or self._task is None:
            raise RuntimeError("BrowserGym environment must be reset before task revision")
        if task.task_id != self._task.task_id or task.revision != self._task.revision + 1:
            raise ValueError("BrowserGym task revision must be consecutive for the active task")
        self._task = task

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        if self._closed or self._task is None:
            return failed_acquisition(AcquisitionOrigin.INDEPENDENT_CAPTURE, "environment_not_ready")
        if not self.observation_capabilities.independent_capture:
            return ObservationAcquisition(
                AcquisitionStatus.CAPABILITY_UNAVAILABLE,
                AcquisitionOrigin.INDEPENDENT_CAPTURE,
                None,
                "independent_capture_unsupported",
            )
        self.capture_calls += 1
        selection = self.observation_orchestrator.select(
            self.observation_offers,
            request,
        )
        if selection.plan is None:
            return ObservationAcquisition(
                selection.status,
                AcquisitionOrigin.INDEPENDENT_CAPTURE,
                None,
                selection.reason_code,
            )
        try:
            raw, probe = self.gym_environment.capture_current()
            self._page_identity = page_identity(raw)
            self._episode_identity = probe_episode(probe, self._episode_identity)
            observation_id, revision = self._next_identity()
            snapshot = task_state_from_probe(
                task_run_id=self.task_run_id,
                observation_id=observation_id,
                source_observation_id=observation_id,
                probe=probe,
            )
            return self._project(
                raw,
                snapshot,
                AcquisitionOrigin.INDEPENDENT_CAPTURE,
                observation_id,
                revision,
                selection.plan,
                request,
                selected_observation_requests(
                    selection.plan, request, self.observation_offers, observation_id
                ),
            )
        except Exception:
            return failed_acquisition(AcquisitionOrigin.INDEPENDENT_CAPTURE, "browsergym_capture_failed")

    async def execute(self, request: BoundActionRequest) -> ExecutionOutcome:
        private = self.bindings.get(request.binding.binding_id)
        error, physical_probe_count = self._probe_currentness(request, private)
        if error is not None:
            return not_sent_outcome(request, error, probe_count=physical_probe_count)
        assert private is not None
        try:
            action = browsergym_action(request, private)
        except ValueError:
            return not_sent_outcome(request, ActionError.INVALID_PARAMETERS)
        self._record_dispatch(request)
        try:
            raw, reward, terminated, truncated, info = self.gym_environment.step(action)
        except BaseException:
            result = ActionResult(
                request.request_id, DispatchStatus.SENT_UNKNOWN, "browsergym", False,
                ActionError.EXECUTION_FAILED,
                {"currentness_probe_count": 1, "effectful_dispatch_count": 1},
            )
            return ExecutionOutcome(
                result, failed_acquisition(AcquisitionOrigin.POST_ACTION, "step_failed_after_dispatch"),
            )
        result = ActionResult(
            request.request_id, DispatchStatus.SENT, "browsergym", True,
            adapter_evidence={"currentness_probe_count": 1, "effectful_dispatch_count": 1},
        )
        try:
            current_task_info = task_info(info)
            self._terminated = terminated is True or truncated is True
            self._page_identity = page_identity(raw)
            self._episode_identity = episode_identity(current_task_info)
            observation_id, revision = self._next_identity()
            snapshot = task_state_from_transition(
                task_run_id=self.task_run_id,
                observation_id=observation_id,
                source_observation_id=observation_id,
                source=BrowserGymTaskStateSource.POST_ACTION,
                reward=reward,
                terminated=terminated,
                truncated=truncated,
                task_info=current_task_info,
            )
            post_request = WorldObservationRequest(
                ObservationRequestKind.POST_ACTION_FALLBACK,
                "post action",
                request.verification_needs,
            )
            selection = self.observation_orchestrator.select(
                self.observation_offers,
                post_request,
                route_source=request.binding.surface,
            )
            if selection.plan is None:
                post = ObservationAcquisition(
                    selection.status,
                    AcquisitionOrigin.POST_ACTION,
                    None,
                    selection.reason_code,
                )
                return ExecutionOutcome(result, post)
            post = self._project(
                raw,
                snapshot,
                AcquisitionOrigin.POST_ACTION,
                observation_id,
                revision,
                selection.plan,
                post_request,
                selected_observation_requests(
                    selection.plan, post_request, self.observation_offers, observation_id
                ),
            )
        except Exception:
            post = failed_acquisition(AcquisitionOrigin.POST_ACTION, "post_action_projection_failed")
        return ExecutionOutcome(result, post)

    def is_current(self, request: BoundActionRequest) -> bool:
        private = self.bindings.get(request.binding.binding_id)
        return bool(
            private
            and request.world_observation_id == self._current_observation_id
            and request.binding.source_observation_id == private.source_observation_id
            and request.binding.source_revision == private.source_revision
        )

    def current_task_state(self) -> BrowserGymTaskStateSnapshot:
        if self._task_state is None:
            raise RuntimeError("no BrowserGym task-state snapshot is available")
        return self._task_state

    def diagnostic_snapshot(self) -> BrowserGymDiagnosticSnapshot:
        if self._diagnostic is None:
            raise RuntimeError("no BrowserGym acquisition diagnostic is available")
        return self._diagnostic

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.bindings.clear()
        self._prepared_initial_raw = None
        self.gym_environment.close()
        unwrapped = getattr(self.gym_environment, "unwrapped", self.gym_environment)
        for name in ("browser", "context"):
            if getattr(unwrapped, name, None) is not None:
                raise RuntimeError("BrowserGym cleanup left an owned browser resource open")

    def _project(
        self,
        raw,
        snapshot: BrowserGymTaskStateSnapshot,
        origin,
        observation_id,
        revision,
        plan: ObservationSelectionPlan,
        request: WorldObservationRequest,
        acquisition_requests: tuple[SelectedObservationRequest, ...],
    ) -> ObservationAcquisition:
        initial_requests_by_source = {
            item.source: item for item in acquisition_requests
        }
        if "browsergym" not in initial_requests_by_source:
            return failed_acquisition(origin, "structural_source_not_selected")
        try:
            projection: BrowserGymProjection = project_browsergym_observation(
                raw,
                observation_id=observation_id,
                source_revision=revision,
                page_identity=self._page_identity,
                episode_identity=self._episode_identity,
                task_state=snapshot,
                entity_identity=self.entity_identity,
            )
        except BrowserGymSemanticError as exc:
            return failed_acquisition(origin, f"browsergym_semantic_{exc.code.value}")
        refined = self.observation_orchestrator.select_after_baseline(
            self.observation_offers,
            request,
            projection.world.sources[0],
            terminal=snapshot.terminal_hint,
            route_source=next(
                (
                    item.source
                    for item in plan.selections
                    if item.reason_code == "route_source_refresh"
                ),
                "",
            ),
        )
        if refined.plan is None:
            return ObservationAcquisition(
                refined.status,
                origin,
                None,
                refined.reason_code,
            )
        plan = refined.plan
        acquisition_requests = selected_observation_requests(
            plan,
            request,
            self.observation_offers,
            acquisition_requests[0].acquisition_id,
        )
        requests_by_source = {item.source: item for item in acquisition_requests}
        selected = {item.source: item for item in plan.selections}
        if "browsergym_visual" in selected:
            self.visual_gate_selected_count += 1
        else:
            self.visual_gate_skipped_count += 1
        sources = [projection.world.sources[0]]
        private_bindings: list[BrowserGymPrivateBinding] = list(projection.private_bindings)
        results: list[SourceAcquisitionResult] = [SourceAcquisitionResult(
            "browsergym",
            selected["browsergym"].requirement,
            SourceAcquisitionStatus.ACQUIRED,
            "source_acquired",
            projection.world.sources[0],
            tuple(item.need_id for item in requests_by_source["browsergym"].needs),
        )]
        self.structural_source_acquired_count += 1
        visual_selection = selected.get("browsergym_visual")
        visual_request = requests_by_source.get("browsergym_visual")
        candidate_binding_filter: set[str] | None = None
        if visual_selection is None:
            results.append(SourceAcquisitionResult(
                "browsergym_visual",
                SourceRequirement.UNSELECTED,
                SourceAcquisitionStatus.NOT_ACQUIRED,
                "source_not_selected",
            ))
        elif visual_selection is not None:
            try:
                assert self._task is not None
                visual_observation_id = f"{observation_id}:visual"
                visual_private_bindings: tuple[BrowserGymVisualBinding, ...]
                assert visual_request is not None
                visual_purpose = self._visual_purpose(visual_request)
                if visual_purpose is ObservationPurpose.WORLD_GROUNDING or (
                    visual_purpose is ObservationPurpose.TARGET_DISAMBIGUATION
                    and self.visual_candidate_disambiguator is None
                    and self.marked_candidate_policy_available
                ):
                    visual_source = project_browsergym_screenshot_source(
                        raw,
                        observation_id=visual_observation_id,
                        acquisition_root_id=observation_id,
                    )
                    visual_private_bindings = ()
                elif visual_purpose is ObservationPurpose.TARGET_DISAMBIGUATION:
                    assert self.visual_candidate_disambiguator is not None
                    self.visual_disambiguator_calls += 1
                    disambiguation = project_browsergym_visual_disambiguation_source(
                        raw,
                        observation_id=visual_observation_id,
                        acquisition_root_id=observation_id,
                        instruction=self._task.instruction,
                        structured_source=projection.world.sources[0],
                        disambiguator=self.visual_candidate_disambiguator,
                        evidence_need=VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,
                    )
                    visual_source = disambiguation.source
                    if disambiguation.selected_target_id:
                        self.visual_disambiguator_selection_count += 1
                        self.visual_correspondence_matched_count += 1
                    candidate_binding_filter = {
                        binding.binding_id
                        for binding in sources[0].bindings
                        if binding.target_id == disambiguation.selected_target_id
                    }
                    private_bindings = [
                        binding
                        for binding in private_bindings
                        if binding.binding_id in candidate_binding_filter
                    ]
                    visual_private_bindings = ()
                else:
                    if self.visual_region_proposer is not None:
                        self.visual_proposer_calls += 1
                    visual = project_browsergym_visual_source(
                        raw,
                        observation_id=visual_observation_id,
                        acquisition_root_id=observation_id,
                        page_identity=self._page_identity,
                        episode_identity=self._episode_identity,
                        task=self._task,
                        proposer=self.visual_region_proposer,
                        # Point grounders are isolated benchmark arms.  The
                        # BrowserGym mainline may observe unmatched V-refs but
                        # cannot turn them into action authority.
                        point_grounder=None,
                        structured_source=projection.world.sources[0],
                    )
                    visual_source = visual.source
                    visual_private_bindings = visual.private_bindings
                    if visual.point_grounding_attempted:
                        self.visual_point_grounder_calls += 1
                    if visual.point_grounding_succeeded:
                        self.visual_point_grounder_success_count += 1
                    if visual.provider_failure is not None:
                        self._record_visual_provider_failure(visual.provider_failure)
                    self._record_correspondence_metrics(visual.correspondence_decisions)
                sources.append(visual_source)
                private_bindings.extend(visual_private_bindings)
                results.append(SourceAcquisitionResult(
                    "browsergym_visual",
                    visual_selection.requirement,
                    SourceAcquisitionStatus.ACQUIRED,
                    "source_acquired",
                    visual_source,
                    tuple(item.need_id for item in visual_request.needs),
                ))
                self.visual_source_acquired_count += 1
                self.visual_binding_acquired_count += len(visual_private_bindings)
            except Exception as exc:
                stage = VisualProviderStage.REGION_PROPOSAL
                if (
                    visual_request is not None
                    and self._visual_purpose(visual_request)
                    is ObservationPurpose.TARGET_DISAMBIGUATION
                    and self.visual_candidate_disambiguator is not None
                ):
                    stage = VisualProviderStage.CANDIDATE_DISAMBIGUATION
                self._record_visual_provider_failure(
                    classify_visual_provider_failure(stage, exc)
                )
                results.append(SourceAcquisitionResult(
                    "browsergym_visual",
                    visual_selection.requirement,
                    SourceAcquisitionStatus.FAILED,
                    "source_acquisition_failed",
                    None,
                    (),
                    tuple(item.need_id for item in visual_request.needs)
                    if visual_request is not None
                    else (),
                ))
        if any(
            item.requirement is SourceRequirement.REQUIRED
            and item.status is not SourceAcquisitionStatus.ACQUIRED
            for item in results
        ):
            return ObservationAcquisition(
                AcquisitionStatus.FAILED,
                origin,
                None,
                "required_source_exhausted",
                plan,
                tuple(results),
            )
        fused = WorldFusion().fuse(tuple(sources))
        if fused.status is not FusionStatus.FUSED or fused.observation is None:
            return failed_acquisition(origin, fused.reason_code)
        world = fused.observation
        if candidate_binding_filter is not None:
            world = replace(
                world,
                bindings=tuple(
                    binding
                    for binding in world.bindings
                    if binding.binding_id in candidate_binding_filter
                ),
            )
        self.bindings.replace(tuple(private_bindings))
        self._current_observation_id = world.observation_id
        self._current_source_revision = revision
        self._task_state = snapshot
        self._diagnostic = diagnostic_snapshot(
            projection.semantic_analysis,
            projection.world.sources[0].semantic_inventory,
        )
        self.full_observation_count += 1
        return ObservationAcquisition(
            AcquisitionStatus.ACQUIRED,
            origin,
            world,
            "world_acquired_with_optional_gap"
            if any(
                item.requirement is SourceRequirement.OPTIONAL
                and item.status is not SourceAcquisitionStatus.ACQUIRED
                for item in results
            )
            else "browsergym_observation_acquired",
            plan,
            tuple(results),
        )

    def _visual_purpose(
        self,
        request: SelectedObservationRequest,
    ) -> ObservationPurpose:
        purposes = {need.purpose for need in request.needs}
        for purpose in (
            ObservationPurpose.TARGET_DISAMBIGUATION,
            ObservationPurpose.ENTITY_DISCOVERY,
            ObservationPurpose.EFFECT_VERIFICATION,
            ObservationPurpose.CRITERION_VERIFICATION,
            ObservationPurpose.WORLD_GROUNDING,
        ):
            if purpose in purposes:
                return purpose
        raise ValueError("selected visual source has no typed observation purpose")

    def _record_correspondence_metrics(self, decisions) -> None:
        for item in decisions:
            if item.status is VisualCorrespondenceStatus.MATCHED:
                self.visual_correspondence_matched_count += 1
            elif item.status is VisualCorrespondenceStatus.UNMATCHED:
                self.visual_correspondence_unmatched_count += 1
            elif item.status is VisualCorrespondenceStatus.AMBIGUOUS:
                self.visual_correspondence_ambiguous_count += 1
            elif item.status is VisualCorrespondenceStatus.CONFLICT:
                self.visual_correspondence_conflict_count += 1

    def _record_visual_provider_failure(self, failure: VisualProviderFailure) -> None:
        self.visual_provider_failures.append(failure)
        self.visual_provider_failure_count += 1
        if failure.stage is VisualProviderStage.POINT_GROUNDING:
            self.visual_point_grounding_failure_count += 1
        elif failure.stage is VisualProviderStage.REGION_PROPOSAL:
            self.visual_region_proposal_failure_count += 1
        elif failure.stage is VisualProviderStage.PREDICATE_CLASSIFICATION:
            self.visual_predicate_classification_failure_count += 1
        else:
            self.visual_candidate_disambiguation_failure_count += 1
        if failure.code is VisualProviderFailureCode.STRUCTURED_OUTPUT:
            self.visual_provider_structured_output_failure_count += 1
        elif failure.code is VisualProviderFailureCode.ABSTAINED:
            self.visual_provider_abstained_count += 1
        elif failure.code is VisualProviderFailureCode.TRANSPORT:
            self.visual_provider_transport_failure_count += 1
        else:
            self.visual_provider_other_failure_count += 1

    def _next_identity(self) -> tuple[str, str]:
        self._observation_serial += 1
        suffix = self.task_run_id.removeprefix("run:")
        observation_id = f"browsergym-observation:{suffix}:{self._observation_serial}"
        revision = source_revision(self._page_identity, self._episode_identity, self._observation_serial)
        return observation_id, revision

    def _probe_currentness(self, request, private) -> tuple[ActionError | None, int]:
        if private is None:
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 0
        self.probe_calls += 1
        if isinstance(private, BrowserGymVisualBinding):
            return self._probe_visual_currentness(request, private)
        assert isinstance(private, BrowserGymElementBinding)
        try:
            result = self.gym_environment.currentness_probe(private.private_element_id)
        except BaseException:
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        if not isinstance(result, dict):
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        latency = result.get("latency_ms")
        if isinstance(latency, int | float) and not isinstance(latency, bool) and latency >= 0:
            self.currentness_probe_latencies_ms.append(float(latency))
        raw = result.get("raw")
        task = result.get("task")
        if not isinstance(raw, dict) or not isinstance(task, dict):
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        ready, done = task.get("ready"), task.get("done")
        episode = task.get("episode")
        if (
            not isinstance(ready, bool)
            or not isinstance(done, bool)
            or not isinstance(episode, str | int)
            or isinstance(episode, bool)
        ):
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        try:
            live = canonical_control_for_bid(raw, private.private_element_id)
            live_page = page_identity(raw)
        except (BrowserGymSemanticError, RuntimeError):
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        context = BrowserGymCurrentnessContext(
            self.is_current(request),
            private.page_identity,
            live_page,
            private.episode_identity,
            str(episode),
            ready,
            done or self._terminated,
            request.binding.primitive_action,
        )
        decision = compare_browsergym_currentness(private.canonical_control, live, context)
        self.last_currentness_decision = decision
        if decision.status is BrowserGymCurrentnessStatus.CURRENT:
            return None, 1
        if decision.status is BrowserGymCurrentnessStatus.UNAVAILABLE:
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        return ActionError.STALE_BINDING, 1

    def _probe_visual_currentness(
        self,
        request: BoundActionRequest,
        private: BrowserGymVisualBinding,
    ) -> tuple[ActionError | None, int]:
        try:
            raw, probe = self.gym_environment.capture_current()
            if not isinstance(probe, dict):
                raise ValueError("visual currentness probe must be structured")
            ready = probe.get("ready")
            done = probe.get("done")
            if not isinstance(ready, bool) or not isinstance(done, bool):
                raise ValueError("visual currentness probe omitted task state")
            live_page = page_identity(raw)
            live_episode = probe_episode(probe, self._episode_identity)
            live = browsergym_visual_frame(raw, f"probe:{uuid.uuid4().hex}")
        except Exception:
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        reason = None
        if not self.is_current(request):
            reason = BrowserGymCurrentnessReason.BINDING_EPOCH_CHANGED
        elif done or self._terminated:
            reason = BrowserGymCurrentnessReason.TASK_DONE
        elif not ready:
            reason = BrowserGymCurrentnessReason.TASK_NOT_READY
        elif private.page_identity != live_page:
            reason = BrowserGymCurrentnessReason.PAGE_CHANGED
        elif private.episode_identity != live_episode:
            reason = BrowserGymCurrentnessReason.EPISODE_CHANGED
        elif not visual_binding_is_current(private.region, live):
            reason = BrowserGymCurrentnessReason.STATE_CHANGED
        if reason is None:
            self.last_currentness_decision = BrowserGymCurrentnessDecision(
                BrowserGymCurrentnessStatus.CURRENT,
                BrowserGymCurrentnessReason.CURRENT,
            )
            return None, 1
        self.last_currentness_decision = BrowserGymCurrentnessDecision(
            BrowserGymCurrentnessStatus.STALE,
            reason,
        )
        return ActionError.STALE_BINDING, 1

    def _record_dispatch(self, request: BoundActionRequest) -> None:
        self.step_calls += 1
        self.dom_action_calls += int(request.binding.surface == "browsergym")
        self.structural_binding_dispatch_count += int(request.binding.surface == "browsergym")
        self.visual_binding_dispatch_count += int(request.binding.surface == "browsergym_visual")
        self.dispatched_request_ids.append(request.request_id)
        self.fill_calls += int(request.binding.primitive_action == "fill")
        self.select_calls += int(request.binding.primitive_action == "select_option")
