"""BrowserGym grouped backend behind the product acquisition coordinator."""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Callable, Protocol

from affordance_runtime.execution import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
    ExecutionDiagnostic,
    ExecutionDiagnosticPhase,
    ExecutionTransition,
    SessionHealth,
    SessionHealthStatus,
    execution_diagnostic_from_exception,
)
from affordance_runtime.surfaces.browsergym.binding import (
    BrowserGymBindingStore,
    BrowserGymDragBinding,
    BrowserGymElementBinding,
    BrowserGymFocusedContextBinding,
    BrowserGymNavigationBinding,
    BrowserGymViewportBinding,
    BrowserGymVisualBinding,
)
from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessContext,
    BrowserGymCurrentnessDecision,
    BrowserGymCurrentnessReason,
    BrowserGymCurrentnessSource,
    BrowserGymCurrentnessStatus,
    compare_browsergym_context_currentness,
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
from affordance_runtime.surfaces.browsergym.execution import (
    BrowserGymActionRejection,
    browsergym_action,
)
from affordance_runtime.surfaces.browsergym.lifecycle_identity import (
    episode_identity,
    page_identity,
    probe_episode,
    source_revision,
    task_info,
)
from affordance_runtime.surfaces.browsergym.projection import (
    BrowserGymProjection,
    normalize_browser_navigation_locations,
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
from affordance_runtime.surfaces.browsergym.transition import (
    BrowserGymStabilityStatus,
    BrowserGymStepTransition,
)
from affordance_runtime.surfaces.browsergym.visual_disambiguation import (
    BrowserGymVisualDisambiguationProjectionError,
    project_browsergym_visual_disambiguation_source,
)
from affordance_runtime.surfaces.browsergym.visual_projection import (
    VisualCorrespondenceStatus,
    browsergym_visual_frame,
    project_browsergym_screenshot_source,
    project_browsergym_visual_source,
)
from affordance_runtime.surfaces.visual.currentness import visual_binding_is_current
from affordance_runtime.surfaces.visual.disambiguation import (
    VisualCandidate,
    VisualCandidateDisambiguatorPort,
)
from affordance_runtime.surfaces.visual.grounding import (
    VisualGrounderPort,
    VisualProviderFailure,
    VisualProviderFailureCode,
    VisualProviderStage,
    VisualRegionProposerPort,
    classify_visual_provider_failure,
)
from affordance_runtime.surfaces.visual.predicate_classification import (
    PredicateTruth,
    VisualPredicateClassification,
    VisualPredicateClassificationRequest,
    VisualPredicateClassifierPort,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    EntityAlignmentBasis,
    EntityAlignmentProposal,
    ObservationOffer,
    ObservationPurpose,
    SelectedObservationRequest,
    SelectedObservationResult,
    SemanticTarget,
    SourceAcquisitionStatus,
    SourceEntityEndpoint,
    StateFact,
    SurfaceObservation,
    VisionEvidenceNeed,
)
from affordance_runtime.world.finalization import (
    PLAIN_TEXT_FINAL_RESPONSE_CODEC,
    FinalResponseCodec,
)
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationObservedItem,
    ObservationQueryDisposition,
    ObservationQueryOutcome,
    ObservationUnknownItem,
    VisualQueryFailureReason,
    VisualUnknownReason,
)


class BrowserGymPort(Protocol):
    supports_capture_current: bool

    def reset(self, *, seed: int) -> tuple[dict[str, object], dict[str, object]]: ...
    def step(self, action: str, *, may_navigate: bool) -> BrowserGymStepTransition: ...
    def send_msg_to_user(self, content: str) -> tuple[dict[str, object], object, object, object, dict[str, object]]: ...
    def capture_current(self) -> tuple[dict[str, object], dict[str, object]]: ...
    def currentness_probe(self, bid: str) -> object: ...
    def session_health(self) -> object: ...
    def close(self) -> None: ...


def _may_navigate(request: BoundActionRequest, private: object) -> bool:
    """Closed mechanical hint for actions whose causal lease includes navigation."""

    key = request.intent.parameters.get("key")
    if isinstance(private, BrowserGymNavigationBinding):
        return True
    if isinstance(private, BrowserGymFocusedContextBinding):
        return private.navigation_potential and key == "Enter"
    if not isinstance(private, BrowserGymElementBinding):
        return False
    candidate = (
        private.canonical_control.role == "link"
        or private.canonical_control.private_navigation_potential
    )
    return candidate and (
        private.supported_primitive == "click"
        or (private.supported_primitive == "press" and key == "Enter")
    )


def _probe_open_pages(raw: dict[str, object]) -> tuple[str, ...]:
    values = raw.get("open_pages_urls")
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, tuple | list):
        return tuple(item for item in values if isinstance(item, str) and item)
    current = raw.get("url")
    return (current,) if isinstance(current, str) and current else ()


@dataclass(frozen=True)
class _BrowserGymCurrentnessLifecycle:
    live_episode_identity: str
    task_ready: bool
    task_done: bool
    task_state_source: BrowserGymCurrentnessSource
    episode_source: BrowserGymCurrentnessSource


def _accepts_registration_modules(factory: Callable[..., BrowserGymPort]) -> bool:
    try:
        parameters = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return True
    return (
        any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
        or "registration_modules" in parameters
    )


async def _run_blocking_close(gym_environment: BrowserGymPort) -> None:
    """Keep the synchronous BrowserGym/Playwright owner close off the asyncio loop."""

    loop = asyncio.get_running_loop()
    completed = loop.create_future()

    def invoke() -> None:
        try:
            gym_environment.close()
            unwrapped = getattr(gym_environment, "unwrapped", gym_environment)
            for name in ("browser", "context"):
                if getattr(unwrapped, name, None) is not None:
                    raise RuntimeError(
                        "BrowserGym cleanup left an owned browser resource open"
                    )
        except BaseException as exc:
            callback = completed.set_exception
            value = exc
        else:
            callback = completed.set_result
            value = None
        try:
            loop.call_soon_threadsafe(_settle_close_future, completed, callback, value)
        except RuntimeError:
            return

    threading.Thread(
        target=invoke,
        name="affordance-browsergym-close",
        daemon=True,
    ).start()
    await completed


def _settle_close_future(future, callback, value) -> None:
    if not future.done():
        callback(value)


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
    browser_action_primitives: tuple[str, ...] = ()
    browser_navigation_locations: tuple[str, ...] | None = None
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
    scroll_calls: int = 0
    press_calls: int = 0
    keyboard_press_calls: int = 0
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
    _pending_execution_diagnostics: list[ExecutionDiagnostic] = field(
        default_factory=list,
        init=False,
        repr=False,
    )
    _final_response_sent: bool = field(default=False, init=False, repr=False)

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
    def supports_finalization(self) -> bool:
        return callable(getattr(self.gym_environment, "send_msg_to_user", None))

    @property
    def final_response_codec(self) -> FinalResponseCodec:
        return PLAIN_TEXT_FINAL_RESPONSE_CODEC

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
        if self.visual_predicate_classifier is not None:
            visual_purposes.append(ObservationPurpose.VISUAL_PROPERTY)
        if self.visual_point_grounder is not None:
            visual_purposes.append(ObservationPurpose.POINT_GROUNDING)
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
        registration_modules: tuple[str, ...] = ("browsergym.miniwob",),
        browser_action_primitives: tuple[str, ...] = (),
        browser_navigation_urls: tuple[str, ...] | None = None,
        task_instruction_transform: Callable[[str], str] | None = None,
    ) -> BrowserGymSurfaceAdapter:
        if not task_id.strip():
            raise ValueError("BrowserGym task ID must be nonempty")
        if gym_factory is None:
            from affordance_runtime.surfaces.browsergym.backend import ThreadBoundBrowserGym

            gym_factory = ThreadBoundBrowserGym
        navigation_locations = (
            None
            if browser_navigation_urls is None
            else normalize_browser_navigation_locations(browser_navigation_urls)
        )
        gym_kwargs: dict[str, object] = {"headless": True}
        if _accepts_registration_modules(gym_factory):
            gym_kwargs["registration_modules"] = registration_modules
        gym_environment = gym_factory(task_id, **gym_kwargs)
        try:
            raw, info = gym_environment.reset(seed=seed)
            prepared_info = task_info(info)
            goal = raw.get("goal") if isinstance(raw, dict) else None
            if not isinstance(goal, str) or not goal.strip():
                raise RuntimeError("BrowserGym reset omitted the public task instruction")
            if task_instruction_transform is not None:
                goal = task_instruction_transform(goal)
                if not isinstance(goal, str) or not goal.strip():
                    raise RuntimeError("BrowserGym task instruction transform returned no public task")
            task_run_id = f"run:{uuid.uuid4().hex}"
            environment = cls(
                task_id=task_id,
                seed=seed,
                gym_environment=gym_environment,
                task_run_id=task_run_id,
                goal_instruction=goal,
                _prepared_initial_raw=raw,
                _prepared_task_info=prepared_info,
                _page_identity=page_identity(raw),
                _episode_identity=episode_identity(prepared_info, fallback=task_run_id),
                browser_action_primitives=tuple(browser_action_primitives),
                browser_navigation_locations=navigation_locations,
                visual_region_proposer=visual_region_proposer,
                visual_point_grounder=visual_point_grounder,
                visual_candidate_disambiguator=visual_candidate_disambiguator,
                visual_predicate_classifier=visual_predicate_classifier,
                marked_candidate_policy_available=marked_candidate_policy_available,
            )
            return environment
        except BaseException as primary:
            cleanup_started = perf_counter()
            try:
                gym_environment.close()
            except BaseException as cleanup:
                try:
                    setattr(
                        primary,
                        "__affordance_cleanup_diagnostic__",
                        execution_diagnostic_from_exception(
                            cleanup,
                            phase=ExecutionDiagnosticPhase.CLEANUP,
                            started_at=cleanup_started,
                            dispatch_crossed=False,
                        ),
                    )
                except BaseException:
                    pass
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
        started = perf_counter()
        try:
            if self._pending_error_code in {"navigation_pending", "acquisition_unstable"}:
                # The causal step owns the first post-action acquisition.  A
                # later acquisition id is the runtime's single read-only
                # recovery attempt. An unstable post-state may be recaptured
                # without replaying the action; an uncommitted navigation may
                # not be admitted by a generic current-page snapshot.
                recovery_allowed = bool(
                    self._pending_error_code == "acquisition_unstable"
                    and self._pending_acquisition_id
                    and self._pending_acquisition_id != acquisition_id
                )
                if not self._pending_acquisition_id:
                    self._pending_acquisition_id = acquisition_id
                if not recovery_allowed:
                    return tuple(
                        SelectedObservationResult.failed(
                            request,
                            SourceAcquisitionStatus.FAILED,
                            self._pending_error_code,
                        )
                        for request in requests
                    )
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
                raw, probe = await asyncio.to_thread(
                    self.gym_environment.capture_current,
                )
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
        except Exception as exc:
            if (
                not self._pending_error_code
                and self._pending_snapshot is not None
                and self._pending_snapshot.source is BrowserGymTaskStateSource.POST_ACTION
            ):
                self._pending_error_code = "post_action_projection_failed"
            if self._pending_error_code in {
                "step_failed_after_dispatch",
                "post_action_projection_failed",
                "final_response_failed_after_dispatch",
                "post_final_projection_failed",
            }:
                self._pending_execution_diagnostics.append(
                    execution_diagnostic_from_exception(
                        exc,
                        phase=ExecutionDiagnosticPhase.POST_CAPTURE,
                        started_at=started,
                        dispatch_crossed=True,
                    )
                )
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
        error, physical_probe_count = await asyncio.to_thread(
            self._probe_currentness,
            request,
            private,
        )
        if error is not None:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                error,
                self._currentness_evidence(physical_probe_count, 0),
            )
        assert private is not None
        try:
            action = browsergym_action(request, private)
        except BrowserGymActionRejection as rejection:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                rejection.error,
                self._currentness_evidence(1, 0),
            )
        except ValueError:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                request.binding.executor_id,
                False,
                ActionError.INVALID_PARAMETERS,
                self._currentness_evidence(1, 0),
            )
        self._record_dispatch(request)
        self._pending_raw = None
        self._pending_snapshot = None
        self._pending_projection = None
        self._pending_acquisition_id = ""
        self._pending_error_code = ""
        started = perf_counter()
        try:
            transition = await asyncio.to_thread(
                self.gym_environment.step,
                action,
                may_navigate=_may_navigate(request, private),
            )
        except BaseException as exc:
            self._pending_error_code = "step_failed_after_dispatch"
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                "browsergym",
                False,
                ActionError.EXECUTION_FAILED,
                self._currentness_evidence(1, 1),
                (
                    execution_diagnostic_from_exception(
                        exc,
                        phase=ExecutionDiagnosticPhase.DISPATCH_WAIT,
                        started_at=started,
                        dispatch_crossed=True,
                    ),
                ),
            )
        transition_evidence = transition.trace.as_evidence()
        result = ActionResult(
            request.request_id,
            DispatchStatus.SENT,
            "browsergym",
            True,
            adapter_evidence={
                **self._currentness_evidence(1, 1),
                "browsergym_transition": transition_evidence,
            },
            causal_transition=(
                ExecutionTransition.STABLE_NAVIGATION
                if transition.trace.stability_status
                is BrowserGymStabilityStatus.STABLE_NAVIGATION
                else None
            ),
        )
        if not transition.stable:
            self._pending_error_code = transition.trace.stability_status.value
            return result
        raw = transition.raw
        reward = transition.reward
        terminated = transition.terminated
        truncated = transition.truncated
        info = transition.info
        assert raw is not None
        try:
            current_task_info = task_info(info)
            self._terminated = terminated is True or truncated is True
            self._page_identity = page_identity(raw)
            self._episode_identity = episode_identity(current_task_info, fallback=self._episode_identity)
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
        except Exception as exc:
            self._pending_error_code = "post_action_projection_failed"
            result = replace(
                result,
                diagnostics=(
                    *result.diagnostics,
                    execution_diagnostic_from_exception(
                        exc,
                        phase=ExecutionDiagnosticPhase.POST_CAPTURE,
                        started_at=started,
                        dispatch_crossed=True,
                    ),
                ),
            )
        return result

    async def finalize(self, content: str) -> ActionResult:
        if self._final_response_sent:
            return ActionResult(
                "final-response",
                DispatchStatus.NOT_SENT,
                "browsergym",
                False,
                ActionError.UNSUPPORTED_ACTION,
                {"effectful_dispatch_count": 0},
            )
        self._final_response_sent = True
        self._pending_raw = None
        self._pending_snapshot = None
        self._pending_projection = None
        self._pending_acquisition_id = ""
        started = perf_counter()
        try:
            raw, reward, terminated, truncated, info = await asyncio.to_thread(
                self.gym_environment.send_msg_to_user,
                content,
            )
        except BaseException as exc:
            self._pending_error_code = "final_response_failed_after_dispatch"
            return ActionResult(
                "final-response",
                DispatchStatus.SENT_UNKNOWN,
                "browsergym",
                False,
                ActionError.EXECUTION_FAILED,
                {"effectful_dispatch_count": 1},
                (
                    execution_diagnostic_from_exception(
                        exc,
                        phase=ExecutionDiagnosticPhase.DISPATCH_WAIT,
                        started_at=started,
                        dispatch_crossed=True,
                    ),
                ),
            )
        result = ActionResult(
            "final-response",
            DispatchStatus.SENT,
            "browsergym",
            True,
            adapter_evidence={"effectful_dispatch_count": 1},
        )
        try:
            current_task_info = task_info(info)
            self._terminated = terminated is True or truncated is True
            self._page_identity = page_identity(raw)
            self._episode_identity = episode_identity(current_task_info, fallback=self._episode_identity)
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
        except Exception as exc:
            self._pending_error_code = "post_final_projection_failed"
            result = replace(
                result,
                diagnostics=(
                    *result.diagnostics,
                    execution_diagnostic_from_exception(
                        exc,
                        phase=ExecutionDiagnosticPhase.POST_CAPTURE,
                        started_at=started,
                        dispatch_crossed=True,
                    ),
                ),
            )
        return result

    async def session_health(self) -> SessionHealth:
        if self._closed:
            return SessionHealth(SessionHealthStatus.LOST, page_closed=True, browser_connected=False)
        probe = getattr(self.gym_environment, "session_health", None)
        if not callable(probe):
            return SessionHealth(SessionHealthStatus.UNKNOWN)
        try:
            raw = await asyncio.to_thread(probe)
        except BaseException:
            return SessionHealth(SessionHealthStatus.UNKNOWN)
        raw = raw if isinstance(raw, dict) else {}
        page_closed = raw.get("page_closed") if type(raw.get("page_closed")) is bool else None
        browser_connected = (
            raw.get("browser_connected")
            if type(raw.get("browser_connected")) is bool
            else None
        )
        status = (
            SessionHealthStatus.LOST
            if page_closed is True or browser_connected is False
            else SessionHealthStatus.ALIVE
            if page_closed is False and browser_connected is True
            else SessionHealthStatus.UNKNOWN
        )
        return SessionHealth(status, page_closed, browser_connected)

    def take_execution_diagnostics(self) -> tuple[ExecutionDiagnostic, ...]:
        diagnostics = tuple(self._pending_execution_diagnostics)
        self._pending_execution_diagnostics.clear()
        return diagnostics

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
        await _run_blocking_close(self.gym_environment)

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
                browser_global_primitives=self.browser_action_primitives,
                browser_navigation_locations=self.browser_navigation_locations,
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
        disambiguation_provider_invoked = False
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
                disambiguation = project_browsergym_visual_disambiguation_source(
                    self._pending_raw,
                    observation_id=visual_observation_id,
                    acquisition_root_id=self._pending_observation_id,
                    instruction=_visual_query_text(
                        request,
                        ObservationPurpose.TARGET_DISAMBIGUATION,
                        "disambiguate the supplied current candidates",
                    ),
                    structured_source=projection.source,
                    disambiguator=self.visual_candidate_disambiguator,
                    evidence_need=VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,
                )
                self.visual_disambiguator_calls += 1
                disambiguation_provider_invoked = True
                visual_source = disambiguation.source
                visual_private_bindings = ()
                target_disambiguated = bool(disambiguation.selected_target_id)
                if target_disambiguated:
                    self.visual_disambiguator_selection_count += 1
                    self.visual_correspondence_matched_count += 1
            elif visual_purpose is ObservationPurpose.VISUAL_PROPERTY:
                assert self.visual_predicate_classifier is not None
                result = self._project_visual_predicate_request(request, projection)
                self.visual_source_acquired_count += 1
                return result
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
                    visual_query=_visual_query_text(
                        request,
                        visual_purpose,
                        "inspect the current visible interface",
                    ),
                    proposer=self.visual_region_proposer,
                    point_grounder=(
                        self.visual_point_grounder
                        if visual_purpose is ObservationPurpose.POINT_GROUNDING
                        else None
                    ),
                    structured_source=projection.source,
                )
                visual_source = visual.source
                visual_private_bindings = visual.private_bindings
                if visual.provider_failure is not None:
                    self._record_visual_provider_failure(visual.provider_failure)
                if visual.point_grounding_attempted:
                    self.visual_point_grounder_calls += 1
                    self.visual_point_grounder_success_count += int(visual.point_grounding_succeeded)
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
        except BrowserGymVisualDisambiguationProjectionError as exc:
            return SelectedObservationResult.failed(
                request,
                SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                exc.reason_code,
            )
        except Exception as exc:
            if (
                self._visual_purpose(request) is ObservationPurpose.TARGET_DISAMBIGUATION
                and self.visual_candidate_disambiguator is not None
                and not disambiguation_provider_invoked
            ):
                self.visual_disambiguator_calls += 1
            purpose = self._visual_purpose(request)
            stage = (
                VisualProviderStage.CANDIDATE_DISAMBIGUATION
                if purpose is ObservationPurpose.TARGET_DISAMBIGUATION
                and self.visual_candidate_disambiguator is not None
                else VisualProviderStage.PREDICATE_CLASSIFICATION
                if purpose is ObservationPurpose.VISUAL_PROPERTY
                else VisualProviderStage.POINT_GROUNDING
                if purpose is ObservationPurpose.POINT_GROUNDING
                else VisualProviderStage.REGION_PROPOSAL
            )
            failure = classify_visual_provider_failure(stage, exc)
            self._record_visual_provider_failure(failure)
            failed_outcomes = tuple(
                ObservationQueryOutcome(
                    item.need_id,
                    item.purpose,
                    ObservationQueryDisposition.FAILED,
                    failure_reason=_query_failure_reason(failure.code),
                )
                for item in request.needs
                if item.purpose in {
                    ObservationPurpose.ENTITY_DISCOVERY,
                    ObservationPurpose.TARGET_DISAMBIGUATION,
                    ObservationPurpose.VISUAL_PROPERTY,
                    ObservationPurpose.POINT_GROUNDING,
                    ObservationPurpose.TEXT_IN_IMAGE,
                    ObservationPurpose.SPATIAL_RELATIONSHIP,
                    ObservationPurpose.VISUAL_CHANGE,
                }
            )
            return SelectedObservationResult.failed(
                request,
                SourceAcquisitionStatus.FAILED,
                failure.reason_code,
                query_outcomes=failed_outcomes,
            )

    def _project_visual_predicate_request(
        self,
        request: SelectedObservationRequest,
        projection: BrowserGymProjection,
    ) -> SelectedObservationResult:
        assert self._pending_raw is not None and self.visual_predicate_classifier is not None
        classifier = self.visual_predicate_classifier
        needs = tuple(item for item in request.needs if item.purpose is ObservationPurpose.VISUAL_PROPERTY)
        if len(needs) != 1:
            raise ValueError("visual predicate acquisition requires one typed query")
        need = needs[0]
        observation_id = f"{self._pending_observation_id}:visual-predicate"
        frame = browsergym_visual_frame(self._pending_raw, observation_id)
        structured_targets = {item.target_id: item for item in projection.source.targets}
        boxes = {
            region.target_id: region.bbox
            for media in projection.source.media
            for region in media.grounding_regions
        }
        candidates: list[VisualCandidate] = []
        input_index_by_ref: dict[str, int] = {}
        for index, subject_id in enumerate(need.subject_ids):
            target = structured_targets.get(subject_id)
            bbox = boxes.get(subject_id)
            if target is None or bbox is None:
                continue
            ref = f"E{len(candidates) + 1}"
            candidates.append(
                VisualCandidate(ref, subject_id, target.role, target.label, bbox, target.state)
            )
            input_index_by_ref[ref] = index

        assessments: tuple[VisualPredicateClassification, ...] = ()
        if candidates:
            self.visual_predicate_classifier_calls += 1
            assessments = classifier.classify(
                VisualPredicateClassificationRequest(
                    need.need_id,
                    frame.image_bytes,
                    (frame.image_width, frame.image_height),
                    need.evidence_property,
                    tuple(candidates),
                )
            )
            self.visual_predicate_assessment_count += len(assessments)
        by_ref = {item.ref: item for item in assessments}
        observed_items: list[ObservationObservedItem] = []
        unknown_items: list[ObservationUnknownItem] = []
        visual_targets: list[SemanticTarget] = []
        facts: list[StateFact] = []
        proposals: list[EntityAlignmentProposal] = []
        candidate_by_ref = {item.ref: item for item in candidates}
        visible_indices = set(input_index_by_ref.values())
        for index, _subject_id in enumerate(need.subject_ids):
            if index not in visible_indices:
                unknown_items.append(
                    ObservationUnknownItem(
                        InputLocator((index,)),
                        VisualUnknownReason.PROPERTY_NOT_OBSERVABLE,
                    )
                )
        for ref, index in input_index_by_ref.items():
            candidate = candidate_by_ref[ref]
            assessment = by_ref[ref]
            if assessment.truth is PredicateTruth.UNKNOWN:
                unknown_items.append(
                    ObservationUnknownItem(
                        InputLocator((index,)),
                        VisualUnknownReason.PROPERTY_NOT_OBSERVABLE,
                    )
                )
                continue
            local_id = f"visual-predicate:{index}"
            value = assessment.truth is PredicateTruth.TRUE
            fact_id = f"fact:{observation_id}:{index}:{need.evidence_property}"
            visual_targets.append(
                SemanticTarget(local_id, candidate.role, candidate.label, {need.evidence_property: value})
            )
            facts.append(StateFact(fact_id, local_id, need.evidence_property, value, observation_id))
            proposals.append(
                EntityAlignmentProposal(
                    f"proposal:{observation_id}:{index}",
                    SourceEntityEndpoint(observation_id, local_id),
                    SourceEntityEndpoint(projection.source.observation_id, candidate.target_id),
                    EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
                    (fact_id,),
                    assessment.confidence,
                )
            )
            observed_items.append(
                ObservationObservedItem(
                    InputLocator((index,)),
                    (candidate.target_id,),
                    (fact_id,),
                )
            )

        screenshot = project_browsergym_screenshot_source(
            self._pending_raw,
            observation_id=observation_id,
            acquisition_root_id=self._pending_observation_id,
        )
        source = SurfaceObservation(
            observation_id,
            "browsergym_visual",
            frame.source_revision,
            screenshot.source_profile,
            tuple(visual_targets),
            tuple(facts),
            (),
            CoverageState.COMPLETE,
            {"screenshot_semantic_state": {"public_summary": "Bounded visual predicate evidence."}},
            media=screenshot.media,
            acquisition_root_id=self._pending_observation_id,
            alignment_proposals=tuple(proposals),
        )
        disposition = (
            ObservationQueryDisposition.PARTIAL
            if observed_items and unknown_items
            else ObservationQueryDisposition.OBSERVED
            if observed_items
            else ObservationQueryDisposition.UNKNOWN
        )
        outcome = ObservationQueryOutcome(
            need.need_id,
            need.purpose,
            disposition,
            tuple(observed_items),
            tuple(unknown_items),
        )
        return SelectedObservationResult.acquired(
            request,
            source,
            fulfilled_need_ids=(need.need_id,),
            query_outcomes=(outcome,),
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
            ObservationPurpose.VISUAL_PROPERTY,
            ObservationPurpose.POINT_GROUNDING,
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
        if isinstance(
            private,
            BrowserGymViewportBinding
            | BrowserGymFocusedContextBinding
            | BrowserGymNavigationBinding,
        ):
            return self._probe_context_currentness(request, private)
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
        lifecycle = self._resolve_currentness_lifecycle(task)
        if lifecycle is None:
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
            lifecycle.live_episode_identity,
            lifecycle.task_ready,
            lifecycle.task_done,
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
        self.last_currentness_decision = self._with_currentness_sources(decision, lifecycle)
        if decision.status is BrowserGymCurrentnessStatus.CURRENT:
            return None, 1
        if decision.status is BrowserGymCurrentnessStatus.UNAVAILABLE:
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        return ActionError.STALE_BINDING, 1

    def _probe_context_currentness(
        self,
        request: BoundActionRequest,
        private: (
            BrowserGymViewportBinding
            | BrowserGymFocusedContextBinding
            | BrowserGymNavigationBinding
        ),
    ) -> tuple[ActionError | None, int]:
        try:
            raw, probe = self.gym_environment.capture_current()
            if not isinstance(probe, dict):
                raise ValueError("context currentness probe must be structured")
            lifecycle = self._resolve_currentness_lifecycle(probe)
            if lifecycle is None:
                return ActionError.CURRENTNESS_UNAVAILABLE, 1
            live_page = page_identity(raw)
        except Exception:
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        context = BrowserGymCurrentnessContext(
            self.is_current(request),
            private.page_identity,
            live_page,
            private.episode_identity,
            lifecycle.live_episode_identity,
            lifecycle.task_ready,
            lifecycle.task_done,
            request.binding.primitive_action,
        )
        decision = compare_browsergym_context_currentness(context)
        reason = decision.reason if decision.status is not BrowserGymCurrentnessStatus.CURRENT else None
        if (
            reason is None
            and isinstance(private, BrowserGymFocusedContextBinding)
            and private.focused_private_element_id
            and not _focused_bid_is_current(raw, private.focused_private_element_id)
        ):
            reason = BrowserGymCurrentnessReason.STATE_CHANGED
        if (
            reason is None
            and isinstance(private, BrowserGymNavigationBinding)
            and private.supported_primitive == "tab_focus"
            and _probe_open_pages(raw) != private.open_pages_urls
        ):
            reason = BrowserGymCurrentnessReason.STATE_CHANGED
        if reason is None:
            self.last_currentness_decision = self._with_currentness_sources(BrowserGymCurrentnessDecision(
                BrowserGymCurrentnessStatus.CURRENT,
                BrowserGymCurrentnessReason.CURRENT,
            ), lifecycle)
            return None, 1
        self.last_currentness_decision = self._with_currentness_sources(BrowserGymCurrentnessDecision(
            BrowserGymCurrentnessStatus.STALE,
            reason,
        ), lifecycle)
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
            lifecycle = self._resolve_currentness_lifecycle(probe)
            if lifecycle is None:
                return ActionError.CURRENTNESS_UNAVAILABLE, 1
            live_page = page_identity(raw)
            live = browsergym_visual_frame(raw, f"probe:{uuid.uuid4().hex}")
        except Exception:
            self.last_currentness_decision = unavailable_currentness()
            return ActionError.CURRENTNESS_UNAVAILABLE, 1
        context = BrowserGymCurrentnessContext(
            self.is_current(request),
            private.page_identity,
            live_page,
            private.episode_identity,
            lifecycle.live_episode_identity,
            lifecycle.task_ready,
            lifecycle.task_done,
            request.binding.primitive_action,
        )
        decision = compare_browsergym_context_currentness(context)
        reason = decision.reason if decision.status is not BrowserGymCurrentnessStatus.CURRENT else None
        if reason is None and not visual_binding_is_current(private.region, live):
            reason = BrowserGymCurrentnessReason.STATE_CHANGED
        if reason is None:
            self.last_currentness_decision = self._with_currentness_sources(BrowserGymCurrentnessDecision(
                BrowserGymCurrentnessStatus.CURRENT,
                BrowserGymCurrentnessReason.CURRENT,
            ), lifecycle)
            return None, 1
        self.last_currentness_decision = self._with_currentness_sources(BrowserGymCurrentnessDecision(
            BrowserGymCurrentnessStatus.STALE,
            reason,
        ), lifecycle)
        return ActionError.STALE_BINDING, 1

    def _resolve_currentness_lifecycle(
        self,
        probe: dict[str, object],
    ) -> _BrowserGymCurrentnessLifecycle | None:
        episode = probe.get("episode")
        if "episode" in probe:
            if not isinstance(episode, str | int) or isinstance(episode, bool):
                self.last_currentness_decision = unavailable_currentness(
                    task_state_source=self._task_state_source_for_probe(probe),
                    episode_source=BrowserGymCurrentnessSource.NATIVE,
                )
                return None
            live_episode_identity = str(episode)
            episode_source = BrowserGymCurrentnessSource.NATIVE
        else:
            live_episode_identity = self._episode_identity
            episode_source = BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK

        ready = probe.get("ready")
        if "ready" in probe:
            if not isinstance(ready, bool):
                self.last_currentness_decision = unavailable_currentness(
                    task_state_source=BrowserGymCurrentnessSource.NATIVE,
                    episode_source=episode_source,
                )
                return None
            task_ready = ready
            ready_source = BrowserGymCurrentnessSource.NATIVE
        else:
            task_ready = self._task is not None and not self._closed and not self._terminated
            ready_source = BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK

        done = probe.get("done")
        if "done" in probe:
            if not isinstance(done, bool):
                self.last_currentness_decision = unavailable_currentness(
                    task_state_source=BrowserGymCurrentnessSource.NATIVE,
                    episode_source=episode_source,
                )
                return None
            task_done = done or self._terminated
            done_source = BrowserGymCurrentnessSource.NATIVE
        else:
            task_done = self._terminated
            done_source = BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK

        task_sources = {ready_source, done_source}
        if task_sources == {BrowserGymCurrentnessSource.NATIVE}:
            task_state_source = BrowserGymCurrentnessSource.NATIVE
        elif task_sources == {BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK}:
            task_state_source = BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK
        else:
            task_state_source = BrowserGymCurrentnessSource.MIXED
        return _BrowserGymCurrentnessLifecycle(
            live_episode_identity,
            task_ready,
            task_done,
            task_state_source,
            episode_source,
        )

    def _task_state_source_for_probe(self, probe: dict[str, object]) -> BrowserGymCurrentnessSource:
        ready_source = (
            BrowserGymCurrentnessSource.NATIVE
            if "ready" in probe
            else BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK
        )
        done_source = (
            BrowserGymCurrentnessSource.NATIVE
            if "done" in probe
            else BrowserGymCurrentnessSource.LIFECYCLE_FALLBACK
        )
        return ready_source if ready_source is done_source else BrowserGymCurrentnessSource.MIXED

    def _with_currentness_sources(
        self,
        decision: BrowserGymCurrentnessDecision,
        lifecycle: _BrowserGymCurrentnessLifecycle,
    ) -> BrowserGymCurrentnessDecision:
        return BrowserGymCurrentnessDecision(
            decision.status,
            decision.reason,
            lifecycle.task_state_source,
            lifecycle.episode_source,
        )

    def _currentness_evidence(self, probe_count: int, dispatch_count: int) -> dict[str, object]:
        decision = self.last_currentness_decision or unavailable_currentness()
        return {
            "currentness_probe_count": probe_count,
            "currentness_status": decision.status.value,
            "currentness_reason": decision.reason.value,
            "currentness_task_state_source": decision.task_state_source.value,
            "currentness_episode_source": decision.episode_source.value,
            "effectful_dispatch_count": dispatch_count,
        }

    def _record_dispatch(self, request: BoundActionRequest) -> None:
        self.step_calls += 1
        self.dom_action_calls += int(request.binding.surface == "browsergym")
        self.structural_binding_dispatch_count += int(request.binding.surface == "browsergym")
        self.visual_binding_dispatch_count += int(request.binding.surface == "browsergym_visual")
        self.dispatched_request_ids.append(request.request_id)
        self.fill_calls += int(request.binding.primitive_action == "fill")
        self.select_calls += int(request.binding.primitive_action == "select_option")
        self.scroll_calls += int(request.binding.primitive_action == "scroll")
        self.press_calls += int(request.binding.primitive_action == "press")
        self.keyboard_press_calls += int(request.binding.primitive_action == "keyboard_press")


def _focused_bid_is_current(raw: dict[str, object], private_bid: str) -> bool:
    try:
        live = canonical_control_for_bid(raw, private_bid)
    except (BrowserGymSemanticError, RuntimeError):
        return False
    return bool(live and dict(live.public_state).get("focused") is True)


def _query_failure_reason(code: VisualProviderFailureCode) -> VisualQueryFailureReason:
    if code is VisualProviderFailureCode.TRANSPORT:
        return VisualQueryFailureReason.TRANSPORT
    if code is VisualProviderFailureCode.STRUCTURED_OUTPUT:
        return VisualQueryFailureReason.STRUCTURED_OUTPUT
    return VisualQueryFailureReason.PROVIDER_ERROR


def _visual_query_text(
    request: SelectedObservationRequest,
    purpose: ObservationPurpose,
    fallback: str,
) -> str:
    return next(
        (
            item.query_text.strip()
            for item in request.needs
            if item.purpose is purpose and item.query_text.strip()
        ),
        fallback,
    )
