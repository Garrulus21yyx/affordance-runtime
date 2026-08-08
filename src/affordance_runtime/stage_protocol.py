"""Shared immutable protocol for the five top-level Runtime stages."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Generic, Mapping, TypeAlias, TypeVar

from affordance_runtime.active_perception import (
    EvidenceGap,
    PerceptionResolution,
    ProbePlan,
    ProbeReceipt,
)
from affordance_runtime.contracts import (
    ExecutionReceipt,
    RuntimeErrorCode,
)
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.observation_store import ObservationCommit
from affordance_runtime.recovery_protocol import FailureOwner, RecoveryDecision, RecoveryOutcome
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
        settlement = getattr(self, "latest_effect_settlement", None)
        settlement_status = getattr(getattr(settlement, "status", None), "value", "")
        settlement_attempt_id = str(getattr(settlement, "attempt_id", ""))
        verified_absence = bool(
            settlement_status == "not_occurred"
            and previous.attempt_id
            and settlement_attempt_id == previous.attempt_id
        )
        if (
            not previous.verification_passed
            and previous.post_environment_revision == current_revision
            and not verified_absence
        ):
            return "no_progress_repeat"
        return None

    def projection(self) -> ProgressWorkingState:
        """Compatibility bridge pending the dedicated ProgressStateView cutover."""

        return ProgressWorkingState(self)


class ProgressWorkingState:
    """Detached progress working set; it never aliases the live StateKernel."""

    def __init__(self, snapshot: RuntimeStateSnapshot) -> None:
        values = deepcopy(dict(snapshot.values))
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_initial", deepcopy(values))

    def __getattr__(self, name: str) -> Any:
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self._values[name] = value

    def delta_values(self) -> dict[str, Any]:
        initial = object.__getattribute__(self, "_initial")
        return {
            name: deepcopy(value)
            for name, value in self._values.items()
            if name not in initial or value != initial[name]
        }

    def record_action_progress(
        self,
        signature: str,
        post_environment_revision: str,
        *,
        verification_passed: bool,
        effect_satisfied: bool | None = None,
        post_page_revision: str = "",
        attempt_id: str = "",
    ) -> None:
        from affordance_runtime.state_kernel import ActionKey

        index = self._values["recent_action_outcomes"]
        index.record(
            ActionKey.from_signature(signature),
            post_environment_revision,
            verification_passed=verification_passed,
            effect_satisfied=(verification_passed if effect_satisfied is None else effect_satisfied),
            post_page_revision=post_page_revision,
            attempt_id=attempt_id,
        )

    def transition(self, next_phase: str) -> None:
        self._values["phase"] = next_phase

    def complete_step(
        self,
        step_id: str,
        evidence: tuple[str, ...],
        criterion_ids: tuple[str, ...] = (),
    ) -> None:
        self._values["task_progress"].complete(
            plan=self._values["task_plan"],
            step_id=step_id,
            criterion_ids=criterion_ids,
            evidence_refs=evidence,
            state_version=self._values["version"],
        )


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
class RuntimeDelta:
    """Closed base type for committed state changes."""


@dataclass(frozen=True)
class PhaseDelta(RuntimeDelta):
    phase: RuntimeStep


@dataclass(frozen=True)
class ObservationDelta(RuntimeDelta):
    commits: tuple[ObservationCommit, ...] = ()


@dataclass(frozen=True)
class PlanningDelta(RuntimeDelta):
    task_plan_transition: Any | None = None
    planner_proposal: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PerceptionDelta(RuntimeDelta):
    commits: tuple[ObservationCommit, ...] = ()
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    active_probe_plan: ProbePlan | None = None
    probe_receipts: tuple[ProbeReceipt, ...] = ()
    perception_resolution: PerceptionResolution | None = None
    active_perception_count_delta: int = 0


@dataclass(frozen=True)
class VerificationDelta(RuntimeDelta):
    report: VerificationReport


@dataclass(frozen=True)
class StepProgressDelta(RuntimeDelta):
    task_progress: Any | None = None
    recent_action_outcomes: Any | None = None
    latest_effect_settlement: Any | None = None
    latest_progress_guard: Mapping[str, str] | None = None
    replan_count: int | None = None


@dataclass(frozen=True)
class CounterDelta(RuntimeDelta):
    step_count: int = 0
    subgoal_action_count: int = 0
    effectful_action_count: int = 0
    replan_count: int = 0


@dataclass(frozen=True)
class VersionDelta(RuntimeDelta):
    delta: int


@dataclass(frozen=True)
class ResultDelta(RuntimeDelta):
    result_payload: Mapping[str, Any]


@dataclass(frozen=True)
class UncertainEffectDelta(RuntimeDelta):
    attempt: ExecutionAttempt


@dataclass(frozen=True)
class ReceiptDelta(RuntimeDelta):
    attempt_id: str
    contract_id: str
    contract_hash: str
    receipt: ExecutionReceipt


@dataclass(frozen=True)
class EffectSettlementDelta(RuntimeDelta):
    attempt_id: str
    contract_hash: str
    settlement: Any
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProgressDelta(RuntimeDelta):
    latest_verification: VerificationReport | None = None
    progress_guard: tuple[str, str] | None = None
    verification: VerificationReport | None = None


@dataclass(frozen=True)
class GroundingRecoveryDelta(RuntimeDelta):
    excluded_candidates: Mapping[str, frozenset[str]] | None = None
    grounding_fallback: Mapping[str, Mapping[str, str]] | None = None


@dataclass(frozen=True)
class RecoveryDelta(RuntimeDelta):
    failure: FailureEnvelope | None = None
    decision: RecoveryDecision | None = None
    outcome: RecoveryOutcome | None = None
    attempted_strategy_ids: frozenset[str] | None = None
    recovery_count: int | None = None
    disproved_assumption: str | None = None
    excluded_candidates: Mapping[str, frozenset[str]] | None = None
    grounding_fallback: Mapping[str, Mapping[str, str]] | None = None
    clear_decision: bool = False
    clear_outcome: bool = False


@dataclass(frozen=True)
class CompletionDelta(RuntimeDelta):
    evaluation: TaskCompletionEvaluation


@dataclass(frozen=True)
class ArtifactIndexDelta(RuntimeDelta):
    refs: tuple[str, ...] = ()


RuntimeDeltaUnion: TypeAlias = (
    PhaseDelta
    | ObservationDelta
    | PlanningDelta
    | PerceptionDelta
    | VerificationDelta
    | StepProgressDelta
    | CounterDelta
    | VersionDelta
    | ResultDelta
    | UncertainEffectDelta
    | ReceiptDelta
    | EffectSettlementDelta
    | ProgressDelta
    | RecoveryDelta
    | GroundingRecoveryDelta
    | CompletionDelta
    | ArtifactIndexDelta
)


@dataclass(frozen=True)
class RuntimeTransition:
    expected_state_version: int
    deltas: tuple[RuntimeDeltaUnion, ...] = ()

    def __post_init__(self) -> None:
        if self.expected_state_version < 0:
            raise ValueError("runtime transition requires an expected state version")
        object.__setattr__(self, "deltas", tuple(self.deltas))


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
