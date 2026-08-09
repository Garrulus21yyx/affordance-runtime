"""Pinned BrowserGym/MiniWoB WorldEnvironment with private execution handles."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from affordance_runtime.benchmarks.external_smoke.browsergym_binding import (
    BrowserGymBindingStore,
    BrowserGymElementBinding,
    semantic_fingerprint,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_execution import browsergym_action
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import project_browsergym_observation
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
    as_external_result,
    verifier_snapshot,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalVerifierResult
from affordance_runtime.execution import (
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
)
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.world import WorldObservation


class BrowserGymPort(Protocol):
    def reset(self, *, seed: int) -> tuple[dict[str, object], dict[str, object]]: ...

    def step(self, action: str) -> tuple[dict[str, object], object, object, object, dict[str, object]]: ...

    def close(self) -> None: ...


@dataclass
class BrowserGymMiniWobEnvironment:
    benchmark_task_id: str
    seed: int
    gym_environment: BrowserGymPort
    task_run_id: str
    goal_instruction: str
    _raw_cache: dict[str, object] | None
    _outcome: tuple[object, object, object, object]
    _page_identity: str
    _episode_identity: str
    bindings: BrowserGymBindingStore = field(default_factory=BrowserGymBindingStore)
    executed_requests: list[str] = field(default_factory=list)
    reset_calls: int = 1
    step_calls: int = 0
    probe_calls: int = 0
    full_observation_count: int = 1
    dom_action_calls: int = 0
    fill_calls: int = 0
    select_calls: int = 0
    verifier_queries: int = 0
    _observation_serial: int = 0
    _current_observation_id: str = ""
    _current_source_revision: str = ""
    _verifier: BrowserGymVerifierSnapshot | None = None
    _task: TaskGoal | None = None
    _terminated: bool = False
    _closed: bool = False

    @classmethod
    def open(
        cls,
        benchmark_task_id: str,
        seed: int,
        *,
        gym_factory: Callable[..., BrowserGymPort] | None = None,
        max_turns: int = 20,
    ) -> tuple[BrowserGymMiniWobEnvironment, TaskGoal]:
        if gym_factory is None:
            from affordance_runtime.benchmarks.external_smoke.browsergym_backend import (
                ThreadBoundBrowserGym,
            )

            gym_factory = ThreadBoundBrowserGym
        gym_environment = gym_factory(benchmark_task_id, headless=True)
        try:
            raw, info = gym_environment.reset(seed=seed)
            task_info = _task_info(info)
            goal = raw.get("goal") if isinstance(raw, dict) else None
            if not isinstance(goal, str) or not goal.strip():
                raise RuntimeError("BrowserGym reset omitted the public task instruction")
            page_identity = _page_identity(raw)
            episode_identity = _episode_identity(task_info)
            run_id = f"run:{uuid.uuid4().hex}"
            environment = cls(
                benchmark_task_id, seed, gym_environment, run_id, goal,
                raw, (0.0, False, False, task_info), page_identity, episode_identity,
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

    async def reset(self, task: TaskGoal) -> None:
        if self._closed or self._raw_cache is None:
            raise RuntimeError("BrowserGym environment is not a fresh prepared episode")
        if task.instruction != self.goal_instruction:
            raise ValueError("TaskGoal instruction must be the public BrowserGym goal")
        self._task = task
        self.bindings.clear()
        self.executed_requests.clear()
        self._current_observation_id = ""
        self._current_source_revision = ""

    async def observe(self, reason: str) -> WorldObservation:
        del reason
        if self._closed or self._task is None:
            raise RuntimeError("BrowserGym environment must be reset before observation")
        if self._raw_cache is None:
            raise RuntimeError("fresh BrowserGym post-step observation is unavailable")
        raw = self._raw_cache
        self._raw_cache = None
        self._observation_serial += 1
        observation_id = f"browsergym-observation:{self.task_run_id.removeprefix('run:')}:{self._observation_serial}"
        revision = _revision(self._page_identity, self._episode_identity, self._observation_serial)
        reward, terminated, truncated, task_info = self._outcome
        snapshot = verifier_snapshot(
            task_run_id=self.task_run_id,
            observation_id=observation_id,
            source_observation_id=observation_id,
            reward=reward,
            terminated=terminated,
            truncated=truncated,
            task_info=task_info,
        )
        projection = project_browsergym_observation(
            raw,
            observation_id=observation_id,
            source_revision=revision,
            page_identity=self._page_identity,
            episode_identity=self._episode_identity,
            verifier=snapshot,
        )
        self.bindings.replace(projection.private_bindings)
        self._current_observation_id = observation_id
        self._current_source_revision = revision
        self._verifier = snapshot
        return projection.world

    def is_current(self, request: BoundActionRequest) -> bool:
        private = self.bindings.get(request.binding.binding_id)
        return bool(
            private
            and request.world_observation_id == self._current_observation_id
            and request.binding.source_revision == self._current_source_revision
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        private = self.bindings.get(request.binding.binding_id)
        error = self._probe_currentness(request, private)
        if error is not None:
            return ActionResult(
                request.request_id, DispatchStatus.NOT_SENT, "browsergym", False, error,
                {"currentness_probe_count": 1, "effectful_dispatch_count": 0},
            )
        assert private is not None
        try:
            action = browsergym_action(request, private)
        except ValueError:
            return ActionResult(
                request.request_id, DispatchStatus.NOT_SENT, "browsergym", False,
                ActionError.INVALID_PARAMETERS,
                {"currentness_probe_count": 1, "effectful_dispatch_count": 0},
            )
        self._record_dispatch(request)
        try:
            raw, reward, terminated, truncated, info = self.gym_environment.step(action)
        except BaseException as exc:
            return ActionResult(
                request.request_id, DispatchStatus.SENT_UNKNOWN, "browsergym", False,
                ActionError.EXECUTION_FAILED,
                {
                    "currentness_probe_count": 1, "effectful_dispatch_count": 1,
                    "error_type": type(exc).__name__,
                },
            )
        self._raw_cache = raw
        self.full_observation_count += 1
        task_info = _task_info(info)
        self._outcome = (reward, terminated, truncated, task_info)
        self._terminated = terminated is True or truncated is True
        self._page_identity = _page_identity(raw)
        self._episode_identity = _episode_identity(task_info)
        return ActionResult(
            request.request_id, DispatchStatus.SENT, "browsergym", True,
            adapter_evidence={"currentness_probe_count": 1, "effectful_dispatch_count": 1},
        )

    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
        if benchmark_task_id != self.benchmark_task_id or self._verifier is None:
            raise ValueError("mechanical verifier request does not match the private task run")
        self.verifier_queries += 1
        return as_external_result(self._verifier)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.bindings.clear()
        self._raw_cache = None
        self.gym_environment.close()
        unwrapped = getattr(self.gym_environment, "unwrapped", self.gym_environment)
        for name in ("browser", "context"):
            if getattr(unwrapped, name, None) is not None:
                raise RuntimeError("BrowserGym cleanup left an owned browser resource open")

    def _probe_currentness(
        self,
        request: BoundActionRequest,
        private: BrowserGymElementBinding | None,
    ) -> ActionError | None:
        self.probe_calls += 1
        if private is None or not self.is_current(request) or self._terminated:
            return ActionError.STALE_BINDING
        try:
            live = _probe(self.gym_environment, private.private_element_id)
        except BaseException:
            return ActionError.CURRENTNESS_UNAVAILABLE
        if not isinstance(live, dict):
            return ActionError.CURRENTNESS_UNAVAILABLE
        if live.get("exists") is not True or live.get("ready") is not True or live.get("done") is True:
            return ActionError.STALE_BINDING
        raw_state = live.get("state")
        state: dict[str, object] = raw_state if isinstance(raw_state, dict) else {}
        selected_state = {key: state.get(key) for key in private.state_keys}
        fingerprint = semantic_fingerprint(str(live.get("role", "")), str(live.get("label", "")), selected_state)
        identity_matches = (
            _digest_text(str(live.get("url", ""))) == private.page_identity
            and str(live.get("episode", "")) == private.episode_identity
            and str(live.get("role", "")) == private.role
            and str(live.get("label", "")) == private.label
            and fingerprint == private.state_fingerprint
            and request.binding.primitive_action == private.supported_primitive
        )
        return None if identity_matches else ActionError.STALE_BINDING

    def _record_dispatch(self, request: BoundActionRequest) -> None:
        self.step_calls += 1
        self.dom_action_calls += 1
        self.executed_requests.append(request.request_id)
        if request.binding.primitive_action == "fill":
            self.fill_calls += 1
        if request.binding.primitive_action == "select_option":
            self.select_calls += 1


def _probe(gym_environment: object, private_element_id: str) -> object:
    custom = getattr(gym_environment, "probe_element", None)
    if custom is None:
        raise RuntimeError("BrowserGym backend does not provide a narrow currentness probe")
    return custom(private_element_id)


def _task_info(info: object) -> dict[str, object]:
    value = info.get("task_info") if isinstance(info, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError("BrowserGym omitted environment-native task status")
    return value


def _page_identity(raw: object) -> str:
    url = raw.get("url") if isinstance(raw, dict) else None
    if not isinstance(url, str) or not url:
        raise RuntimeError("BrowserGym observation omitted current page identity")
    return _digest_text(url)


def _episode_identity(task_info: dict[str, object]) -> str:
    episode = task_info.get("EPISODE_ID")
    if not isinstance(episode, int | str) or isinstance(episode, bool):
        raise RuntimeError("BrowserGym task status omitted episode identity")
    return str(episode)


def _revision(page_identity: str, episode_identity: str, serial: int) -> str:
    return _digest_text(f"{page_identity}\0{episode_identity}\0{serial}")


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
