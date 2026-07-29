"""Immutable Step Planner input contracts.

TPA-2 foundation only: these contracts project the runtime into a bounded,
deeply immutable request. They intentionally do not import StateKernel,
TaskEnvelope, BrowserSnapshot, planners, Coordinator, trace, adapters, or
benchmarks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from affordance_runtime.simplified_runtime_contracts import (
    Criterion,
    FrozenScalar,
    StepActivityStatus,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)

FrozenRequestValue = object
FrozenRequestObject = tuple[tuple[str, FrozenRequestValue], ...]
FrozenStateItems = tuple[tuple[str, FrozenRequestValue], ...]


class PlannerStepProjectionStatus(StrEnum):
    PROJECTED = "projected"
    NO_PLAN = "no_plan"
    STALE_PLAN = "stale_plan"
    PROJECTION_INVALID = "projection_invalid"
    UNSUPPORTED_EVIDENCE_POLICY = "unsupported_evidence_policy"


class PlannerAdmissionSource(StrEnum):
    LEGACY_TERMINAL_READINESS = "legacy_terminal_readiness"
    ACTIVE_STEP_SCOPE = "active_step_scope"


class TargetAdmissionStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PlanningRequestIdentity:
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    snapshot_id: str
    page_revision: str
    environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("task_spec_identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("state version cannot be negative")
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)


@dataclass(frozen=True)
class PlannerTaskView:
    task_spec_identity: str
    task_revision: int
    objective: str
    constraints: tuple[str, ...]
    capabilities: tuple[str, ...]
    task_completion_criterion: Criterion | None
    task_completion_projection_status: str
    task_summary: FrozenRequestObject = ()

    def __post_init__(self) -> None:
        _require_nonblank("task_spec_identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        _require_nonblank("objective", self.objective)
        _require_tuple("constraints", self.constraints)
        _require_tuple("capabilities", self.capabilities)
        _require_no_blank_values("capabilities", self.capabilities)
        _require_nonblank(
            "task_completion_projection_status",
            self.task_completion_projection_status,
        )
        _require_tuple("task_summary", self.task_summary)


@dataclass(frozen=True)
class PlannerStepView:
    plan: TaskPlanView | None
    progress: StepProgressView | None
    active_step: StepSpec | None
    activity_status: StepActivityStatus
    projection_status: PlannerStepProjectionStatus = PlannerStepProjectionStatus.NO_PLAN
    projection_reason: str = ""
    active_step_action_family: str = ""
    compatibility_active_step_objective: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.activity_status, StepActivityStatus):
            raise ValueError("unsupported step activity status")
        if not isinstance(self.projection_status, PlannerStepProjectionStatus):
            raise ValueError("unsupported step projection status")
        if self.projection_reason:
            _require_nonblank("projection_reason", self.projection_reason)
        if self.compatibility_active_step_objective:
            _require_nonblank(
                "compatibility_active_step_objective",
                self.compatibility_active_step_objective,
            )
        if self.progress is None:
            if self.plan is not None or self.active_step is not None:
                raise ValueError("step view without progress cannot carry plan data")
            if self.activity_status != StepActivityStatus.NO_PLAN:
                raise ValueError("missing progress requires no-plan status")
            if self.projection_status == PlannerStepProjectionStatus.PROJECTED:
                raise ValueError("projected step view requires progress")
            return
        if self.plan is None:
            raise ValueError("step progress requires a plan view")
        if self.projection_status != PlannerStepProjectionStatus.PROJECTED:
            raise ValueError("step progress requires projected status")
        if self.progress.activity_status != self.activity_status:
            raise ValueError("step activity status mismatch")
        if self.progress.plan_id != self.plan.plan_id:
            raise ValueError("step progress plan identity mismatch")
        if self.progress.plan_version != self.plan.plan_version:
            raise ValueError("step progress plan version mismatch")
        step_by_id = {item.step_id: item for item in self.plan.steps}
        all_progress_ids = (
            self.progress.completed_step_ids
            + self.progress.failed_step_ids
            + self.progress.ready_step_ids
        )
        if set(all_progress_ids) - set(step_by_id):
            raise ValueError("step progress references unknown step")
        if self.activity_status == StepActivityStatus.ACTIVE:
            if self.active_step is None:
                raise ValueError("active status requires active step")
            if self.active_step.step_id != self.progress.active_step_id:
                raise ValueError("active step identity mismatch")
        elif self.active_step is not None:
            raise ValueError("only active status may expose an active step")
        if self.active_step_action_family:
            _require_nonblank("active_step_action_family", self.active_step_action_family)

    @property
    def permits_effectful_actions(self) -> bool:
        return self.projection_status in {
            PlannerStepProjectionStatus.PROJECTED,
            PlannerStepProjectionStatus.NO_PLAN,
        }


@dataclass(frozen=True)
class TargetAdmissionDecision:
    target_id: str
    status: TargetAdmissionStatus
    reason_code: str
    blocking_step_ids: tuple[str, ...] = ()
    unknown_step_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("target_id", self.target_id)
        if not isinstance(self.status, TargetAdmissionStatus):
            raise ValueError("unsupported target admission status")
        _require_nonblank("reason_code", self.reason_code)
        _require_tuple("blocking_step_ids", self.blocking_step_ids)
        _require_tuple("unknown_step_ids", self.unknown_step_ids)
        _require_unique_nonblank("blocking step ids", self.blocking_step_ids)
        _require_unique_nonblank("unknown step ids", self.unknown_step_ids)
        if self.status == TargetAdmissionStatus.BLOCKED and not self.blocking_step_ids:
            raise ValueError("blocked target admission requires blocking step ids")
        if self.status == TargetAdmissionStatus.UNKNOWN and not self.unknown_step_ids:
            raise ValueError("unknown target admission requires unknown step ids")


@dataclass(frozen=True)
class PlannerAdmissionView:
    source: PlannerAdmissionSource
    task_revision: int
    snapshot_id: str
    target_decisions: tuple[TargetAdmissionDecision, ...] = ()
    excluded_target_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, PlannerAdmissionSource):
            raise ValueError("unsupported planner admission source")
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_tuple("target_decisions", self.target_decisions)
        _require_tuple("excluded_target_ids", self.excluded_target_ids)
        _require_unique_nonblank("excluded target ids", self.excluded_target_ids)
        seen: set[str] = set()
        for decision in self.target_decisions:
            if decision.target_id in seen:
                raise ValueError("target admission decisions must be unique")
            seen.add(decision.target_id)
        unknown_excluded = set(self.excluded_target_ids) - seen
        if unknown_excluded:
            raise ValueError("excluded target ids must be present in target decisions")


@dataclass(frozen=True)
class PlannerAdmissionSummary:
    excluded_target_ids: tuple[str, ...] = ()
    blocked_target_ids: tuple[str, ...] = ()
    unknown_target_ids: tuple[str, ...] = ()
    unresolved_target_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple("excluded_target_ids", self.excluded_target_ids)
        _require_tuple("blocked_target_ids", self.blocked_target_ids)
        _require_tuple("unknown_target_ids", self.unknown_target_ids)
        _require_tuple("unresolved_target_ids", self.unresolved_target_ids)
        _require_unique_nonblank("excluded target ids", self.excluded_target_ids)
        _require_unique_nonblank("blocked target ids", self.blocked_target_ids)
        _require_unique_nonblank("unknown target ids", self.unknown_target_ids)
        _require_unique_nonblank("unresolved target ids", self.unresolved_target_ids)


@dataclass(frozen=True)
class PlannerAffordanceView:
    target_id: str
    surface: str
    role: str
    label: str
    supported_actions: tuple[str, ...]
    state: FrozenStateItems
    confidence: float | None = None
    conflict_codes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        target_id: str,
        surface: str,
        role: str,
        label: str,
        supported_actions: tuple[str, ...],
        state: FrozenStateItems | dict[str, object],
        confidence: float | None = None,
        conflict_codes: tuple[str, ...] = (),
        source_refs: tuple[str, ...] = (),
    ) -> None:
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "surface", surface)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "supported_actions", supported_actions)
        object.__setattr__(self, "state", _freeze_state_items(state))
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "conflict_codes", conflict_codes)
        object.__setattr__(self, "source_refs", source_refs)
        self.__post_init__()

    def __post_init__(self) -> None:
        _require_nonblank("target_id", self.target_id)
        _require_nonblank("surface", self.surface)
        _require_nonblank("role", self.role)
        _require_tuple("supported_actions", self.supported_actions)
        _require_unique_nonblank("supported actions", self.supported_actions)
        _require_tuple("state", self.state)
        _validate_state_items(self.state)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        _require_tuple("conflict_codes", self.conflict_codes)
        _require_no_blank_values("conflict_codes", self.conflict_codes)
        _require_tuple("source_refs", self.source_refs)
        _require_no_blank_values("source_refs", self.source_refs)


@dataclass(frozen=True)
class PlannerObservationView:
    snapshot_id: str
    page_revision: str
    environment_revision: str
    observed_text: str
    affordances: tuple[PlannerAffordanceView, ...]
    artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)
        _require_tuple("affordances", self.affordances)
        _require_tuple("artifact_refs", self.artifact_refs)
        _require_no_blank_values("artifact_refs", self.artifact_refs)


@dataclass(frozen=True)
class PlannerOutcomeSummary:
    receipt_status: str
    verification_status: str
    verified_criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    error_code: str = ""

    def __post_init__(self) -> None:
        _require_tuple("verified_criterion_ids", self.verified_criterion_ids)
        _require_tuple("evidence_refs", self.evidence_refs)
        _require_no_blank_values("verified_criterion_ids", self.verified_criterion_ids)
        _require_no_blank_values("evidence_refs", self.evidence_refs)


@dataclass(frozen=True)
class PlannerRecoverySummary:
    kind: str
    reason_code: str
    message: str
    attempted_changes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("kind", self.kind)
        _require_tuple("attempted_changes", self.attempted_changes)
        _require_no_blank_values("attempted_changes", self.attempted_changes)


@dataclass(frozen=True)
class RuntimeBudgetView:
    steps: int
    observations: int
    recoveries: int
    effectful_actions: int
    model_calls: int

    def __post_init__(self) -> None:
        for label, value in (
            ("steps", self.steps),
            ("observations", self.observations),
            ("recoveries", self.recoveries),
            ("effectful_actions", self.effectful_actions),
            ("model_calls", self.model_calls),
        ):
            if value < 0:
                raise ValueError(f"{label} budget cannot be negative")


@dataclass(frozen=True)
class PlanningRequest:
    identity: PlanningRequestIdentity
    task: PlannerTaskView
    step: PlannerStepView
    observation: PlannerObservationView
    recent_outcomes: tuple[PlannerOutcomeSummary, ...] = ()
    recovery: PlannerRecoverySummary | None = None
    latest_outcome: FrozenRequestObject = ()
    recent_proposals: tuple[FrozenRequestObject, ...] = ()
    verified_effects: tuple[str, ...] = ()
    pending_evidence_obligations: tuple[str, ...] = ()
    remaining_budget: RuntimeBudgetView = RuntimeBudgetView(
        steps=0,
        observations=0,
        recoveries=0,
        effectful_actions=0,
        model_calls=0,
    )
    permitted_action_kinds: tuple[str, ...] = ()
    satisfied_action_targets: tuple[tuple[str, tuple[str, ...]], ...] = ()
    admission: PlannerAdmissionView | None = None

    def __post_init__(self) -> None:
        if self.identity.task_spec_identity != self.task.task_spec_identity:
            raise ValueError("request task identity mismatch")
        if self.identity.task_revision != self.task.task_revision:
            raise ValueError("request task revision mismatch")
        if self.identity.snapshot_id != self.observation.snapshot_id:
            raise ValueError("request snapshot identity mismatch")
        if self.identity.page_revision != self.observation.page_revision:
            raise ValueError("request page revision mismatch")
        if self.identity.environment_revision != self.observation.environment_revision:
            raise ValueError("request environment revision mismatch")
        if self.admission is not None:
            if self.admission.task_revision != self.identity.task_revision:
                raise ValueError("request admission task revision mismatch")
            if self.admission.snapshot_id != self.identity.snapshot_id:
                raise ValueError("request admission snapshot identity mismatch")
        _require_tuple("recent_outcomes", self.recent_outcomes)
        _require_tuple("latest_outcome", self.latest_outcome)
        _require_tuple("recent_proposals", self.recent_proposals)
        _require_tuple("verified_effects", self.verified_effects)
        _require_no_blank_values("verified_effects", self.verified_effects)
        _require_tuple(
            "pending_evidence_obligations",
            self.pending_evidence_obligations,
        )
        _require_no_blank_values(
            "pending_evidence_obligations",
            self.pending_evidence_obligations,
        )
        _require_tuple("permitted_action_kinds", self.permitted_action_kinds)
        _require_unique_nonblank("permitted action kinds", self.permitted_action_kinds)
        _validate_string_tuple_map(
            "satisfied_action_targets",
            self.satisfied_action_targets,
        )


def _freeze_state_items(value: FrozenStateItems | dict[str, object]) -> FrozenStateItems:
    if isinstance(value, dict):
        return tuple(
            (str(key), freeze_request_value(item))
            for key, item in sorted(value.items())
        )
    _require_tuple("state", value)
    return tuple((key, freeze_request_value(item)) for key, item in value)


def freeze_request_value(value: object) -> FrozenRequestValue:
    if _is_frozen_scalar(value):
        return value
    if isinstance(value, dict):
        return (
            "__dict__",
            tuple((str(key), freeze_request_value(item)) for key, item in sorted(value.items())),
        )
    if isinstance(value, (list, tuple)):
        return ("__list__", tuple(freeze_request_value(item) for item in value))
    raise ValueError("request summary values must be JSON-like and immutable")


def freeze_request_mapping(value: dict[str, object]) -> FrozenRequestObject:
    return tuple((str(key), freeze_request_value(item)) for key, item in sorted(value.items()))


def thaw_request_value(value: FrozenRequestValue) -> object:
    if _is_frozen_scalar(value):
        return value
    if isinstance(value, tuple):
        if len(value) == 2 and value[0] == "__dict__" and isinstance(value[1], tuple):
            return {
                key: thaw_request_value(item)
                for key, item in value[1]
                if isinstance(key, str)
            }
        if len(value) == 2 and value[0] == "__list__" and isinstance(value[1], tuple):
            return [thaw_request_value(item) for item in value[1]]
    raise ValueError("unsupported frozen request value")


def thaw_request_mapping(value: FrozenRequestObject) -> dict[str, object]:
    return {key: thaw_request_value(item) for key, item in value}


def _freeze_scalar(value: object) -> FrozenScalar:
    if not _is_frozen_scalar(value):
        raise ValueError("state values must be scalar and deeply immutable")
    return cast(FrozenScalar, value)


def _is_frozen_scalar(value: object) -> bool:
    return isinstance(value, (str, bool, int, float)) or value is None


def _validate_state_items(value: FrozenStateItems) -> None:
    seen: set[str] = set()
    for key, item in value:
        _require_nonblank("state key", key)
        if key in seen:
            raise ValueError("state keys must be unique")
        seen.add(key)
        thaw_request_value(item)


def _validate_string_tuple_map(
    label: str,
    values: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    _require_tuple(label, values)
    seen: set[str] = set()
    for key, refs in values:
        _require_nonblank(label, key)
        if key in seen:
            raise ValueError(f"{label} keys must be unique")
        seen.add(key)
        _require_tuple(label, refs)
        _require_unique_nonblank(label, refs)


def _require_nonblank(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be blank")


def _require_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def _require_no_blank_values(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot contain blank values")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    _require_no_blank_values(label, values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
