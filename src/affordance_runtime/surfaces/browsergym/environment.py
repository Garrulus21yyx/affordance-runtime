"""BrowserGym grouped backend behind the product acquisition coordinator."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from affordance_runtime.execution import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.browsergym.binding import (
    BrowserGymBindingStore,
    BrowserGymDragBinding,
    BrowserGymElementBinding,
    BrowserGymVisualBinding,
)
from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessContext,
    BrowserGymCurrentnessDecision,
    BrowserGymCurrentnessReason,
    BrowserGymCurrentnessStatus,
    compare_browsergym_currentness,
    compare_browsergym_drag_currentness,
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
from affordance_runtime.surfaces.browsergym.lifecycle_identity import (
    episode_identity,
    page_identity,
    probe_episode,
    source_revision,
    task_info,
)
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
    ObservationOffer,
    ObservationPurpose,
    SelectedObservationRequest,
    SelectedObservationResult,
    SourceAcquisitionStatus,
    VisionEvidenceNeed,
)


class BrowserGymPort(Protocol):
    supports_capture_current: bool

    def reset(self, *, seed: int) -> tuple[dict[str, object], dict[str, object]]: ...
    def step(self, action: str) -> tuple[dict[str, object], object, object, object, dict[str, object]]: ...
    def capture_current(self) -> tuple[dict[str, object], dict[str, object]]: ...
    def currentness_probe(self, bid: str) -> object: ...
    def close(self) -> None: ...


@dataclass
class BrowserGymSurfaceAdapter:
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
    _current_source_revision: str = ""
    _task_state: BrowserGymTaskStateSnapshot | None = None
    _diagnostic: BrowserGymDiagnosticSnapshot | None = None
    _task: TaskGoal | None = None
    _terminated: bool = False
    _closed: bool = False
    last_currentness_decision: BrowserGymCurrentnessDecision | None = None
    entity_identity: BrowserGymEntityIdentityMap = field(
        default_factory=BrowserGymEntityIdentityMap,
        repr=False,
    )
    _pending_raw: dict[str, object] | None = field(default=None, init=False, repr=False)
    _pending_snapshot: BrowserGymTaskStateSnapshot | None = field(default=None, init=False, repr=False)
    _pending_observation_id: str = field(default="", init=False, repr=False)
    _pending_revision: str = field(default="", init=False, repr=False)
    _pending_acquisition_id: str = field(default="", init=False, repr=False)
    _pending_projection: BrowserGymProjection | None = field(default=None, init=False, repr=False)
    _pending_error_code: str = field(default="", init=False, repr=False)

    surface: str = field(default="browsergym", init=False)

    @property
    def physical_environment_id(self) -> str:
        return f"browsergym:{self.task_run_id}"

    @property
    def owns_physical_reset(self) -> bool:
        return True

    @property
    def supports_independent_capture(self) -> bool:
        return bool(getattr(self.gym_environment, "supports_capture_current", False))

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        group = f"browsergym:{self.task_run_id}"
        visual_purposes = [ObservationPurpose.WORLD_GROUNDING]
        if self.visual_region_proposer is not None:
            visual_purposes.extend(
                (
                    ObservationPurpose.ENTITY_DISCOVERY,
                    ObservationPurpose.EFFECT_VERIFICATION,
                    ObservationPurpose.CRITERION_VERIFICATION,
                )
            )
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
    ) -> BrowserGymSurfaceAdapter:
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

    def initialize_task(self, task: TaskGoal) -> None:
        if self._closed:
            raise RuntimeError("BrowserGym backend is closed")
        if task.instruction != self.goal_instruction:
            raise ValueError("TaskGoal instruction must be the public BrowserGym goal")
        if self._task is not None and (
            task.task_id != self._task.task_id or task.revision not in {self._task.revision, self._task.revision + 1}
        ):
            raise ValueError("BrowserGym task revision must be current or consecutive")
        self._task = task

    async def reset_physical(self) -> None:
        self.logical_reset_calls += 1
        if self._closed or self._prepared_initial_raw is None or self.logical_reset_calls != 1:
            raise RuntimeError("prepared_initial_observation_unavailable")
        if self._task is None:
            raise RuntimeError("BrowserGym task must be initialized before reset")
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
        self._prepare_frame(raw, snapshot, observation_id, revision)

    async def acquire(
        self,
        request: SelectedObservationRequest,
    ) -> SelectedObservationResult:
        return (await self.acquire_group((request,)))[0]

    async def acquire_group(
        self,
        requests: tuple[SelectedObservationRequest, ...],
    ) -> tuple[SelectedObservationResult, ...]:
        if not requests:
            return ()
        if self._closed or self._task is None:
            return tuple(
                SelectedObservationResult.failed(request, SourceAcquisitionStatus.FAILED, "environment_not_ready")
                for request in requests
            )
        if len({item.acquisition_id for item in requests}) != 1:
            raise ValueError("BrowserGym grouped acquisition must conserve one identity")
        acquisition_id = requests[0].acquisition_id
        try:
            if self._pending_raw is not None and not self._pending_acquisition_id:
                self._pending_acquisition_id = acquisition_id
            elif self._pending_acquisition_id != acquisition_id:
                if not getattr(self.gym_environment, "supports_capture_current", False):
                    return tuple(
                        SelectedObservationResult.failed(
                            request,
                            SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                            "independent_capture_unsupported",
                        )
                        for request in requests
                    )
                self.capture_calls += 1
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
                self._prepare_frame(raw, snapshot, observation_id, revision)
            self._pending_acquisition_id = acquisition_id
            return self._project_requests(requests)
        except Exception:
            return tuple(
                SelectedObservationResult.failed(
                    request,
                    SourceAcquisitionStatus.FAILED,
                    self._pending_error_code or "browsergym_capture_failed",
                )
                for request in requests
            )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        private = self.bindings.get(request.binding.binding_id)
        error, physical_probe_count = self._probe_currentness(request, private)
        if error is not None:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                error,
                {"currentness_probe_count": physical_probe_count, "effectful_dispatch_count": 0},
            )
        assert private is not None
        try:
            action = browsergym_action(request, private)
        except ValueError:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.INVALID_PARAMETERS,
                {"currentness_probe_count": 1, "effectful_dispatch_count": 0},
            )
        self._record_dispatch(request)
        self._pending_raw = None
        self._pending_snapshot = None
        self._pending_projection = None
        self._pending_acquisition_id = ""
        try:
            raw, reward, terminated, truncated, info = self.gym_environment.step(action)
        except BaseException:
            self._pending_error_code = "step_failed_after_dispatch"
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                "browsergym",
                False,
                ActionError.EXECUTION_FAILED,
                {"currentness_probe_count": 1, "effectful_dispatch_count": 1},
            )
        result = ActionResult(
            request.request_id,
            DispatchStatus.SENT,
            "browsergym",
            True,
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
            self._prepare_frame(raw, snapshot, observation_id, revision)
        except Exception:
            self._pending_error_code = "post_action_projection_failed"
        return result

    def is_current(self, request: BoundActionRequest) -> bool:
        private = self.bindings.get(request.binding.binding_id)
        return bool(
            private
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

    def _prepare_frame(
        self,
        raw: dict[str, object],
        snapshot: BrowserGymTaskStateSnapshot,
        observation_id: str,
        revision: str,
    ) -> None:
        self._pending_raw = raw
        self._pending_snapshot = snapshot
        self._pending_observation_id = observation_id
        self._pending_revision = revision
        self._pending_acquisition_id = ""
        self._pending_projection = None
        self._pending_error_code = ""

    def _structural_projection(self) -> BrowserGymProjection:
        if self._pending_projection is not None:
            return self._pending_projection
        if self._pending_raw is None or self._pending_snapshot is None:
            raise RuntimeError(self._pending_error_code or "browsergym_frame_unavailable")
        try:
            projection = project_browsergym_observation(
                self._pending_raw,
                observation_id=self._pending_observation_id,
                source_revision=self._pending_revision,
                page_identity=self._page_identity,
                episode_identity=self._episode_identity,
                task_state=self._pending_snapshot,
                entity_identity=self.entity_identity,
            )
        except BrowserGymSemanticError as exc:
            raise RuntimeError(f"browsergym_semantic_{exc.code.value}") from exc
        self._pending_projection = projection
        self.bindings.replace(tuple(projection.private_bindings))
        self._current_source_revision = self._pending_revision
        self._task_state = self._pending_snapshot
        self._diagnostic = diagnostic_snapshot(
            projection.semantic_analysis,
            projection.source.semantic_inventory,
        )
        return projection

    def _project_requests(
        self,
        requests: tuple[SelectedObservationRequest, ...],
    ) -> tuple[SelectedObservationResult, ...]:
        projection = self._structural_projection()
        results: list[SelectedObservationResult] = []
        for request in requests:
            if request.source == "browsergym":
                results.append(
                    SelectedObservationResult.acquired(
                        request,
                        projection.source,
                        fulfilled_need_ids=tuple(item.need_id for item in request.needs),
                    )
                )
                self.structural_source_acquired_count += 1
                continue
            if request.source != "browsergym_visual":
                results.append(
                    SelectedObservationResult.failed(
                        request,
                        SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                        "source_not_owned",
                    )
                )
                continue
            results.append(self._project_visual_request(request, projection))
        self.full_observation_count += int(bool(results))
        return tuple(results)

    def _project_visual_request(
        self,
        request: SelectedObservationRequest,
        projection: BrowserGymProjection,
    ) -> SelectedObservationResult:
        self.visual_gate_selected_count += 1
        try:
            assert self._task is not None and self._pending_raw is not None
            visual_observation_id = f"{self._pending_observation_id}:visual"
            visual_purpose = self._visual_purpose(request)
            target_disambiguated = False
            if visual_purpose is ObservationPurpose.WORLD_GROUNDING or (
                visual_purpose is ObservationPurpose.TARGET_DISAMBIGUATION
                and self.visual_candidate_disambiguator is None
                and self.marked_candidate_policy_available
            ):
                visual_source = project_browsergym_screenshot_source(
                    self._pending_raw,
                    observation_id=visual_observation_id,
                    acquisition_root_id=self._pending_observation_id,
                )
                visual_private_bindings: tuple[BrowserGymVisualBinding, ...] = ()
                target_disambiguated = visual_purpose is ObservationPurpose.TARGET_DISAMBIGUATION
            elif visual_purpose is ObservationPurpose.TARGET_DISAMBIGUATION:
                assert self.visual_candidate_disambiguator is not None
                self.visual_disambiguator_calls += 1
                disambiguation = project_browsergym_visual_disambiguation_source(
                    self._pending_raw,
                    observation_id=visual_observation_id,
                    acquisition_root_id=self._pending_observation_id,
                    instruction=self._task.instruction,
                    structured_source=projection.source,
                    disambiguator=self.visual_candidate_disambiguator,
                    evidence_need=VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,
                )
                visual_source = disambiguation.source
                visual_private_bindings = ()
                target_disambiguated = bool(disambiguation.selected_target_id)
                if target_disambiguated:
                    self.visual_disambiguator_selection_count += 1
                    self.visual_correspondence_matched_count += 1
            else:
                if self.visual_region_proposer is not None:
                    self.visual_proposer_calls += 1
                visual = project_browsergym_visual_source(
                    self._pending_raw,
                    observation_id=visual_observation_id,
                    acquisition_root_id=self._pending_observation_id,
                    page_identity=self._page_identity,
                    episode_identity=self._episode_identity,
                    task=self._task,
                    proposer=self.visual_region_proposer,
                    point_grounder=None,
                    structured_source=projection.source,
                )
                visual_source = visual.source
                visual_private_bindings = visual.private_bindings
                if visual.provider_failure is not None:
                    self._record_visual_provider_failure(visual.provider_failure)
                self._record_correspondence_metrics(visual.correspondence_decisions)
            if visual_private_bindings:
                self.bindings.replace((*self.bindings.values, *visual_private_bindings))
            fulfilled = self._fulfilled_visual_needs(
                request,
                visual_source,
                visual_purpose,
                target_disambiguated,
            )
            self.visual_source_acquired_count += 1
            self.visual_binding_acquired_count += len(visual_private_bindings)
            return SelectedObservationResult.acquired(
                request,
                visual_source,
                fulfilled_need_ids=fulfilled,
                unfulfilled_reason_code="visual_need_unresolved",
            )
        except Exception as exc:
            stage = (
                VisualProviderStage.CANDIDATE_DISAMBIGUATION
                if self._visual_purpose(request) is ObservationPurpose.TARGET_DISAMBIGUATION
                and self.visual_candidate_disambiguator is not None
                else VisualProviderStage.REGION_PROPOSAL
            )
            self._record_visual_provider_failure(classify_visual_provider_failure(stage, exc))
            return SelectedObservationResult.failed(
                request, SourceAcquisitionStatus.FAILED, "source_acquisition_failed"
            )

    @staticmethod
    def _fulfilled_visual_needs(
        request: SelectedObservationRequest,
        visual_source,
        visual_purpose: ObservationPurpose,
        target_disambiguated: bool,
    ) -> tuple[str, ...]:
        if visual_purpose is ObservationPurpose.WORLD_GROUNDING:
            return tuple(item.need_id for item in request.needs if item.purpose is ObservationPurpose.WORLD_GROUNDING)
        if visual_purpose is ObservationPurpose.TARGET_DISAMBIGUATION:
            return tuple(
                item.need_id
                for item in request.needs
                if item.purpose is ObservationPurpose.TARGET_DISAMBIGUATION and target_disambiguated
            )
        return tuple(
            item.need_id
            for item in request.needs
            if (item.purpose is ObservationPurpose.ENTITY_DISCOVERY and bool(visual_source.targets))
            or (
                item.purpose
                in {
                    ObservationPurpose.EFFECT_VERIFICATION,
                    ObservationPurpose.CRITERION_VERIFICATION,
                }
                and bool(visual_source.facts)
                and (
                    not item.subject_ids
                    or bool(set(item.subject_ids) & {target.target_id for target in visual_source.targets})
                )
            )
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
        assert isinstance(private, BrowserGymElementBinding | BrowserGymDragBinding)
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
        if isinstance(private, BrowserGymDragBinding):
            try:
                destination = private.destination(request.intent.destination_id)
                live_destination = canonical_control_for_bid(raw, destination.private_element_id)
            except (BrowserGymSemanticError, RuntimeError, ValueError):
                self.last_currentness_decision = unavailable_currentness()
                return ActionError.CURRENTNESS_UNAVAILABLE, 1
            decision = compare_browsergym_drag_currentness(
                private.canonical_control,
                live,
                destination.canonical_control,
                live_destination,
                context,
            )
        else:
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
