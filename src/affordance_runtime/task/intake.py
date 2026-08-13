"""Thin target intake from natural-language requests to TaskGoal authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeAlias

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.task.contracts import (
    EvaluationSpec,
    LoopBudget,
    MaterialBinding,
    RiskProfile,
    TaskGoal,
)
from affordance_runtime.task.intent_context import IntentContext

_PRIVATE_INPUT_KEYS = frozenset({
    "action_id",
    "binding_id",
    "coordinate",
    "coordinates",
    "dom_id",
    "e_ref",
    "executor",
    "screen_point",
    "selector",
})


class TaskIntakeStatus(StrEnum):
    READY = "ready"
    NEEDS_USER_INPUT = "needs_user_input"
    POLICY_REJECTED = "policy_rejected"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class TaskBoundary:
    """Caller-declared stable task boundary; never current GUI structure."""

    constraints: tuple[str, ...] = ()
    allowed_effects: tuple[str, ...] = ()
    forbidden_effects: tuple[str, ...] = ()
    inputs: Mapping[str, Any] = field(default_factory=dict)
    success_criteria: tuple[Mapping[str, Any], ...] = ()
    requested_outputs: tuple[str, ...] = ()
    risk_profile: RiskProfile = RiskProfile.READ_ONLY
    material_bindings: tuple[MaterialBinding, ...] = ()
    loop_budget: LoopBudget = field(default_factory=LoopBudget)
    evaluation_spec: EvaluationSpec | None = None

    def __post_init__(self) -> None:
        for name in ("constraints", "allowed_effects", "forbidden_effects", "requested_outputs"):
            values = tuple(getattr(self, name))
            if any(not value.strip() for value in values) or len(values) != len(set(values)):
                raise ValueError(f"task boundary {name} must be nonblank and unique")
            object.__setattr__(self, name, values)
        if not isinstance(self.risk_profile, RiskProfile):
            raise TypeError("task boundary risk profile must be typed")
        if not isinstance(self.loop_budget, LoopBudget):
            raise TypeError("task boundary loop budget must be typed")
        if self.evaluation_spec is not None and not isinstance(self.evaluation_spec, EvaluationSpec):
            raise TypeError("task boundary evaluation spec must be typed")
        object.__setattr__(self, "inputs", freeze_json(self.inputs))
        object.__setattr__(
            self,
            "success_criteria",
            tuple(freeze_json(item) for item in self.success_criteria),
        )
        object.__setattr__(self, "material_bindings", tuple(self.material_bindings))


@dataclass(frozen=True)
class NaturalLanguageTaskRequest:
    """Natural-language request plus an explicit stable authority boundary."""

    request_id: str
    instruction: str
    boundary: TaskBoundary = field(default_factory=TaskBoundary)
    intent_context: IntentContext | None = None
    source_ref: str = ""
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.instruction.strip():
            raise ValueError("natural-language task request requires identity and instruction")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("natural-language task request revision must be a positive integer")
        if not isinstance(self.boundary, TaskBoundary):
            raise TypeError("natural-language task request requires a typed boundary")
        if self.intent_context is not None and not isinstance(self.intent_context, IntentContext):
            raise TypeError("natural-language task request intent context must be typed")
        if self.source_ref and not self.source_ref.strip():
            raise ValueError("task source reference cannot be blank")


@dataclass(frozen=True)
class ReadyTask:
    request_id: str
    task: TaskGoal
    intent_context: IntentContext | None = None
    source_ref: str = ""
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.READY, init=False)


@dataclass(frozen=True)
class TaskInputRequired:
    request_id: str
    question: str
    requested_fields: tuple[str, ...]
    reason_code: str
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.NEEDS_USER_INPUT, init=False)


@dataclass(frozen=True)
class TaskPolicyRejected:
    request_id: str
    reason_code: str
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.POLICY_REJECTED, init=False)


@dataclass(frozen=True)
class TaskUnsupported:
    request_id: str
    reason_code: str
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.UNSUPPORTED, init=False)


TaskIntakeOutcome: TypeAlias = ReadyTask | TaskInputRequired | TaskPolicyRejected | TaskUnsupported


class TaskIntake(Protocol):
    def compile(self, request: NaturalLanguageTaskRequest) -> TaskIntakeOutcome: ...


@dataclass(frozen=True)
class ThinTaskIntake:
    """Admit stable task meaning without planning or pre-observation GUI identity."""

    def compile(self, request: NaturalLanguageTaskRequest) -> TaskIntakeOutcome:
        if not isinstance(request, NaturalLanguageTaskRequest):
            raise TypeError("thin intake requires a NaturalLanguageTaskRequest")
        boundary = request.boundary
        allowed = frozenset(boundary.allowed_effects)
        forbidden = frozenset(boundary.forbidden_effects)
        if allowed.intersection(forbidden):
            return TaskPolicyRejected(request.request_id, "allowed_forbidden_effect_conflict")
        if boundary.risk_profile is RiskProfile.READ_ONLY and allowed:
            return TaskPolicyRejected(request.request_id, "read_only_effect_conflict")
        if boundary.risk_profile is not RiskProfile.READ_ONLY and not allowed:
            return TaskInputRequired(
                request.request_id,
                "Which semantic effects may this task perform?",
                ("allowed_effects",),
                "effect_authority_required",
            )
        private_path = _private_input_path(to_json_compatible(boundary.inputs))
        if private_path:
            return TaskUnsupported(request.request_id, "runtime_private_input_not_supported")
        try:
            task = TaskGoal(
                request.request_id,
                request.instruction,
                constraints=boundary.constraints,
                allowed_effects=boundary.allowed_effects,
                forbidden_effects=boundary.forbidden_effects,
                inputs=dict(boundary.inputs),
                success_criteria=tuple(dict(item) for item in boundary.success_criteria),
                requested_outputs=boundary.requested_outputs,
                risk_profile=boundary.risk_profile,
                material_bindings=boundary.material_bindings,
                loop_budget=boundary.loop_budget,
                evaluation_spec=boundary.evaluation_spec,
                revision=request.revision,
            )
        except (TypeError, ValueError):
            return TaskUnsupported(request.request_id, "task_goal_contract_invalid")
        return ReadyTask(request.request_id, task, request.intent_context, request.source_ref)


def _private_input_path(value: object, path: str = "inputs") -> str:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().casefold()
            child = f"{path}.{key}"
            if normalized in _PRIVATE_INPUT_KEYS or normalized.startswith("_runtime"):
                return child
            if found := _private_input_path(item, child):
                return found
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            if found := _private_input_path(item, f"{path}[{index}]"):
                return found
    return ""
