"""Shared immutable protocol for the five top-level Runtime stages."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType, MethodType
from typing import Any, Generic, Mapping, TypeAlias, TypeVar

from affordance_runtime.active_perception import (
    EvidenceGap,
    PerceptionResolution,
    ProbePlan,
    ProbeReceipt,
)
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    RuntimeErrorCode,
)
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.observation_store import ObservationCommit
from affordance_runtime.recovery_protocol import FailureOwner
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.simplified_runtime_contracts import ExecutionAttempt
from affordance_runtime.verification.contracts import TaskCompletionEvaluation
from affordance_runtime.verification.mechanical import VerificationReport


class LoopDirective(StrEnum):
    CONTINUE = "continue"
    REPEAT_OBSERVATION = "repeat_observation"
    NEXT_STAGE = "next_stage"
    WAIT_USER = "wait_user"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class RuntimeEvent:
    kind: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("runtime event kind is required")
        object.__setattr__(self, "payload", freeze_json(dict(self.payload)))


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    """Detached read-only attribute view supplied to pure stages."""

    values: Mapping[str, Any]
    prototype: Any

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def excluded_candidates_for(self, target_id: str) -> frozenset[str]:
        return frozenset(self.current_excluded_candidates.get(target_id, ()))

    def fallback_lineage_for(self, target_id: str) -> dict[str, str]:
        return dict(self.current_grounding_fallback.get(target_id, {}))

    def current_revision(self) -> str:
        return self.current_observation_environment_revision

    def current_page_revision(self) -> str:
        return self.current_observation_page_revision

    def check_progress_guard(self, signature: str) -> Any | None:
        payload = json.loads(signature)
        parameters: dict[str, object] = {"parameters": payload.get("parameters", {})}
        if payload.get("destination"):
            parameters["destination"] = str(payload["destination"])
        if payload.get("subgoal"):
            parameters["subgoal"] = str(payload["subgoal"])
        digest = hashlib.sha256(
            json.dumps(
                to_json_compatible(freeze_json(parameters)),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        previous = next(
            (
                item
                for item in reversed(self.recent_action_outcomes.records)
                if item.key.action_kind == str(payload.get("action_kind") or "")
                and item.key.target_id == str(payload.get("target") or "")
                and item.key.parameter_digest == f"sha256:{digest}"
            ),
            None,
        )
        if previous is None:
            return None
        current_page = self.current_page_revision()
        current_revision = self.current_revision()
        same_page = (
            previous.post_page_revision == current_page
            if previous.post_page_revision and current_page
            else previous.post_environment_revision == current_revision
        )
        if previous.effect_satisfied and same_page:
            return "effect_already_satisfied"
        if not previous.verification_passed and previous.post_environment_revision == current_revision:
            return "no_progress_repeat"
        return None

    def projection(self) -> RuntimeStateProjection:
        """Create a detached change-tracking projection for pure computation."""

        return RuntimeStateProjection(self)


class RuntimeStateProjection:
    """Detached state calculator; it cannot mutate the live StateKernel."""

    def __init__(self, snapshot: RuntimeStateSnapshot) -> None:
        object.__setattr__(self, "_prototype_type", type(snapshot.prototype))
        values = deepcopy(dict(snapshot.values))
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_initial", deepcopy(values))

    def __getattr__(self, name: str) -> Any:
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        method = getattr(object.__getattribute__(self, "_prototype_type"), name, None)
        if callable(method):
            return MethodType(method, self)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self._values[name] = value

    def changes(self) -> dict[str, Any]:
        initial = object.__getattribute__(self, "_initial")
        return {
            name: deepcopy(value)
            for name, value in self._values.items()
            if name not in initial or value != initial[name]
        }


@dataclass(frozen=True)
class RuntimeEventNode:
    id: str
    kind: str
    payload: Mapping[str, Any]


class RuntimeEventBuffer:
    """Minimal TraceDag-compatible collector used inside pure stages."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []
        self.artifact_index: list[str] = []

    def add(
        self,
        kind: str,
        payload: Mapping[str, Any],
        parents: list[str] | None = None,
    ) -> RuntimeEventNode:
        del parents
        event = RuntimeEvent(kind, payload)
        self.events.append(event)
        return RuntimeEventNode(f"stage-event-{len(self.events)}", kind, event.payload)

    def root(self) -> RuntimeEventNode:
        return RuntimeEventNode("stage-root", "StageStarted", MappingProxyType({}))


@dataclass(frozen=True)
class RuntimeTransition:
    phase: RuntimeStep | None = None
    intermediate_phases: tuple[RuntimeStep, ...] = ()
    perception_update: bool = False
    observation_commits: tuple[ObservationCommit, ...] = ()
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    active_probe_plan: ProbePlan | None = None
    probe_receipts: tuple[ProbeReceipt, ...] = ()
    perception_resolution: PerceptionResolution | None = None
    active_perception_count_delta: int = 0
    latest_verification: VerificationReport | None = None
    artifact_refs: tuple[str, ...] = ()
    task_plan_transition: Any | None = None
    planner_proposal: Mapping[str, Any] | None = None
    current_contract: ActionContract | None = None
    execution_attempt: ExecutionAttempt | None = None
    receipt: ExecutionReceipt | None = None
    step_count_delta: int = 0
    subgoal_action_count_delta: int = 0
    effectful_action_count_delta: int = 0
    replan_count_delta: int = 0
    progress_guard: tuple[str, str] | None = None
    clear_recovery_decision: bool = False
    final_result: Mapping[str, Any] | None = None
    task_completion: TaskCompletionEvaluation | None = None
    state_updates: Mapping[str, Any] | None = None
    version_delta: int = 0

    def __post_init__(self) -> None:
        if self.active_perception_count_delta < 0:
            raise ValueError("active perception count delta must be non-negative")
        if (
            min(
                self.step_count_delta,
                self.subgoal_action_count_delta,
                self.effectful_action_count_delta,
                self.replan_count_delta,
                self.version_delta,
            )
            < 0
        ):
            raise ValueError("runtime counter deltas must be non-negative")
        object.__setattr__(self, "observation_commits", tuple(self.observation_commits))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))
        object.__setattr__(self, "probe_receipts", tuple(self.probe_receipts))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        object.__setattr__(self, "intermediate_phases", tuple(self.intermediate_phases))


@dataclass(frozen=True)
class TerminalResult:
    failure_id: str
    reason_code: str
    status: RuntimeStep = RuntimeStep.ABORTED
    error_code: RuntimeErrorCode | None = None
    owner: FailureOwner = FailureOwner.TERMINAL


@dataclass(frozen=True)
class ProgressHandoff:
    failure_id: str
    reason_code: str
    owner: FailureOwner = field(default=FailureOwner.PROGRESS, init=False)


@dataclass(frozen=True)
class StepPlannerHandoff:
    failure_id: str
    reason_code: str
    replan_scope: str = field(default="step", init=False)
    owner: FailureOwner = field(default=FailureOwner.STEP_PLANNER, init=False)


@dataclass(frozen=True)
class TaskPlannerHandoff:
    failure_id: str
    reason_code: str
    replan_scope: str = field(default="task", init=False)
    owner: FailureOwner = field(default=FailureOwner.TASK_PLANNER, init=False)


@dataclass(frozen=True)
class UserInputRequest:
    failure_id: str
    reason_code: str
    question: str
    owner: FailureOwner = field(default=FailureOwner.USER, init=False)


OwnerHandoff: TypeAlias = ProgressHandoff | StepPlannerHandoff | TaskPlannerHandoff | UserInputRequest | TerminalResult


def build_failure_owner_handoff(
    failure: FailureEnvelope,
    owner: FailureOwner,
    reason_code: str,
) -> OwnerHandoff:
    if owner == FailureOwner.RUNTIME_RECOVERY:
        raise ValueError("non-runtime failure owner handoff received runtime recovery owner")
    if not failure.recoverable:
        return TerminalResult(failure.failure_id, reason_code)
    if owner == FailureOwner.PROGRESS:
        return ProgressHandoff(failure.failure_id, reason_code)
    if owner == FailureOwner.STEP_PLANNER:
        return StepPlannerHandoff(failure.failure_id, reason_code)
    if owner == FailureOwner.TASK_PLANNER:
        return TaskPlannerHandoff(failure.failure_id, reason_code)
    if owner == FailureOwner.USER:
        return UserInputRequest(
            failure.failure_id,
            reason_code,
            "What information or authority is required to continue safely?",
        )
    return TerminalResult(failure.failure_id, reason_code)


T = TypeVar("T")


@dataclass(frozen=True)
class StageResult(Generic[T]):
    output: T | None = None
    transition: RuntimeTransition | None = None
    events: tuple[RuntimeEvent, ...] = ()
    failure: FailureEnvelope | None = None
    terminal: TerminalResult | None = None
    directive: LoopDirective = LoopDirective.NEXT_STAGE

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
