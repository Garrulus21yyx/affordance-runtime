"""Pinned BrowserGym WorldEnvironment with active typed acquisition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from affordance_runtime.benchmarks.external_smoke.browsergym_acquisition import (
    episode_identity,
    failed_acquisition,
    not_sent_outcome,
    page_identity,
    probe_episode,
    source_revision,
    task_info,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_binding import (
    BrowserGymBindingStore,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_currentness import (
    BrowserGymCurrentnessContext,
    BrowserGymCurrentnessDecision,
    BrowserGymCurrentnessStatus,
    compare_browsergym_currentness,
    unavailable_currentness,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_diagnostics import (
    BrowserGymDiagnosticSnapshot,
    diagnostic_snapshot,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_execution import browsergym_action
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import (
    BrowserGymProjection,
    project_browsergym_observation,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    BrowserGymSemanticError,
    canonical_control_for_bid,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
    as_external_result,
    verifier_snapshot,
    verifier_snapshot_from_current_probe,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalVerifierResult
from affordance_runtime.execution import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ExecutionOutcome,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationOffer,
    WorldObservationRequest,
)


class BrowserGymPort(Protocol):
    supports_capture_current: bool

    def reset(self, *, seed: int) -> tuple[dict[str, object], dict[str, object]]: ...
    def step(self, action: str) -> tuple[dict[str, object], object, object, object, dict[str, object]]: ...
    def capture_current(self) -> tuple[dict[str, object], dict[str, object]]: ...
    def currentness_probe(self, bid: str) -> object: ...
    def close(self) -> None: ...


@dataclass
class BrowserGymMiniWobEnvironment:
    benchmark_task_id: str
    seed: int
    gym_environment: BrowserGymPort
    task_run_id: str
    goal_instruction: str
    _prepared_initial_raw: dict[str, object] | None
    _prepared_task_info: dict[str, object]
    _page_identity: str
    _episode_identity: str
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
    verifier_queries: int = 0
    official_success_count: int = 0
    _observation_serial: int = 0
    _current_observation_id: str = ""
    _current_source_revision: str = ""
    _verifier: BrowserGymVerifierSnapshot | None = None
    _diagnostic: BrowserGymDiagnosticSnapshot | None = None
    _task: TaskGoal | None = None
    _terminated: bool = False
    _closed: bool = False
    last_currentness_decision: BrowserGymCurrentnessDecision | None = None

    @property
    def observation_capabilities(self) -> ObservationCapabilities:
        independent = bool(getattr(self.gym_environment, "supports_capture_current", False))
        offers: tuple[ObservationOffer, ...] = ()
        if independent:
            offers = (ObservationOffer("browsergym", "structural", "structural", "medium"),)
        return ObservationCapabilities(independent, True, offers)

    @classmethod
    def open(
        cls,
        benchmark_task_id: str,
        seed: int,
        *,
        gym_factory: Callable[..., BrowserGymPort] | None = None,
        max_turns: int = 20,
        admitted_task_ids: frozenset[str] | None = None,
    ) -> tuple[BrowserGymMiniWobEnvironment, TaskGoal]:
        from affordance_runtime.benchmarks.external_smoke.browsergym_inventory import REVIEWED_TASK_IDS

        admitted = frozenset(REVIEWED_TASK_IDS) if admitted_task_ids is None else admitted_task_ids
        if benchmark_task_id not in admitted:
            raise ValueError("BrowserGym task ID is outside the reviewed fixed manifest")
        if gym_factory is None:
            from affordance_runtime.benchmarks.external_smoke.browsergym_backend import ThreadBoundBrowserGym

            gym_factory = ThreadBoundBrowserGym
        gym_environment = gym_factory(benchmark_task_id, headless=True)
        try:
            raw, info = gym_environment.reset(seed=seed)
            prepared_info = task_info(info)
            goal = raw.get("goal") if isinstance(raw, dict) else None
            if not isinstance(goal, str) or not goal.strip():
                raise RuntimeError("BrowserGym reset omitted the public task instruction")
            environment = cls(
                benchmark_task_id, seed, gym_environment, f"run:{uuid.uuid4().hex}", goal,
                raw, prepared_info, page_identity(raw), episode_identity(prepared_info),
            )
            task = TaskGoal(
                f"task:{uuid.uuid4().hex}", goal,
                allowed_effects=("external_ui_interaction",),
                forbidden_effects=("external_network_side_effect", "credential_use"),
                risk_profile=RiskProfile.LOW,
                loop_budget=LoopBudget(max_turns=max_turns, max_observations=max_turns * 2),
            )
            return environment, task
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
        snapshot = verifier_snapshot(
            task_run_id=self.task_run_id,
            observation_id=observation_id,
            source_observation_id=observation_id,
            reward=0.0,
            terminated=False,
            truncated=False,
            task_info=self._prepared_task_info,
        )
        return self._project(raw, snapshot, AcquisitionOrigin.RESET, observation_id, revision)

    async def capture(self, request: WorldObservationRequest) -> ObservationAcquisition:
        del request
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
        try:
            raw, probe = self.gym_environment.capture_current()
            self._page_identity = page_identity(raw)
            self._episode_identity = probe_episode(probe, self._episode_identity)
            observation_id, revision = self._next_identity()
            snapshot = verifier_snapshot_from_current_probe(
                task_run_id=self.task_run_id,
                observation_id=observation_id,
                source_observation_id=observation_id,
                probe=probe,
            )
            return self._project(
                raw, snapshot, AcquisitionOrigin.INDEPENDENT_CAPTURE, observation_id, revision,
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
            snapshot = verifier_snapshot(
                task_run_id=self.task_run_id,
                observation_id=observation_id,
                source_observation_id=observation_id,
                reward=reward,
                terminated=terminated,
                truncated=truncated,
                task_info=current_task_info,
            )
            post = self._project(
                raw, snapshot, AcquisitionOrigin.POST_ACTION, observation_id, revision,
            )
        except Exception:
            post = failed_acquisition(AcquisitionOrigin.POST_ACTION, "post_action_projection_failed")
        return ExecutionOutcome(result, post)

    def is_current(self, request: BoundActionRequest) -> bool:
        private = self.bindings.get(request.binding.binding_id)
        return bool(
            private
            and request.world_observation_id == self._current_observation_id
            and request.binding.source_revision == self._current_source_revision
        )

    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
        if benchmark_task_id != self.benchmark_task_id or self._verifier is None:
            raise ValueError("mechanical verifier request does not match the private task run")
        self.verifier_queries += 1
        result = as_external_result(self._verifier)
        if str(result.status) == "success":
            self.official_success_count += 1
        return result

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

    def _project(self, raw, snapshot, origin, observation_id, revision) -> ObservationAcquisition:
        try:
            projection: BrowserGymProjection = project_browsergym_observation(
                raw,
                observation_id=observation_id,
                source_revision=revision,
                page_identity=self._page_identity,
                episode_identity=self._episode_identity,
                verifier=snapshot,
            )
        except BrowserGymSemanticError as exc:
            return failed_acquisition(origin, f"browsergym_semantic_{exc.code.value}")
        self.bindings.replace(projection.private_bindings)
        self._current_observation_id = observation_id
        self._current_source_revision = revision
        self._verifier = snapshot
        self._diagnostic = diagnostic_snapshot(raw)
        self.full_observation_count += 1
        return ObservationAcquisition(
            AcquisitionStatus.ACQUIRED, origin, projection.world, "browsergym_observation_acquired",
        )

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

    def _record_dispatch(self, request: BoundActionRequest) -> None:
        self.step_calls += 1
        self.dom_action_calls += 1
        self.dispatched_request_ids.append(request.request_id)
        self.fill_calls += int(request.binding.primitive_action == "fill")
        self.select_calls += int(request.binding.primitive_action == "select_option")
