"""Small executable runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.immutable import FrozenSequence, freeze_json
from affordance_runtime.task_intake import TaskSpec, task_effect_targets
from affordance_runtime.task_spec_authority import AdmittedTaskSpec


class RuntimeStep(StrEnum):
    CREATED = "created"
    OBSERVING = "observing"
    PLANNING = "planning"
    PREFLIGHT = "preflight"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_CLARIFICATION = "waiting_clarification"
    DEFERRED = "deferred"
    ACTING = "acting"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    DONE = "done"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class RunRequest:
    admitted_task: AdmittedTaskSpec
    target: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)

    @property
    def task_spec(self) -> TaskSpec:
        return self.admitted_task.task_spec

    @property
    def task_id(self) -> str:
        return self.task_spec.task_id

    @property
    def goal(self) -> str:
        return self.task_spec.objective

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", freeze_json(self.constraints))
        object.__setattr__(self, "capabilities", FrozenSequence(self.capabilities))
        if not isinstance(self.admitted_task, AdmittedTaskSpec):
            raise ValueError("RunRequest requires an Authority-issued AdmittedTaskSpec")
        task_spec = self.task_spec
        targets = task_effect_targets(task_spec)
        if not self.target and targets:
            object.__setattr__(self, "target", targets[0])


def legacy_run_request(
    *,
    task_spec: TaskSpec | None = None,
    task_id: str = "",
    goal: str = "",
    **kwargs: Any,
) -> RunRequest:
    """P5-3 adapter for explicit pre-Authority fixtures and legacy profiles."""

    from affordance_runtime.task_intake import (
        OperationClass,
        canonical_effect_requirement_refs,
        canonical_effect_requirements,
    )
    from affordance_runtime.task_spec_authority import _admit_legacy_task_spec
    from affordance_runtime.verification.contracts import SuccessExpression

    if task_spec is None:
        if not task_id or not goal:
            raise ValueError("legacy_run_request requires TaskSpec or task_id/goal")
        task_spec = TaskSpec(
            task_id=task_id,
            revision=1,
            objective=goal,
            operation_class=OperationClass.READ_ONLY,
            requirements=canonical_effect_requirements((goal,), OperationClass.READ_ONLY, "legacy-run-request", ()),
            allowed_effect_refs=canonical_effect_requirement_refs((goal,)),
            success=SuccessExpression(
                expression_id="success:legacy-run-request",
                operator="criterion",
                criterion_id="criterion:legacy-run-request",
                requirement_refs=("requirement:effect:1",),
            ),
            source_request_ref="legacy-run-request",
        )
    return RunRequest(admitted_task=_admit_legacy_task_spec(task_spec), **kwargs)


class Executor(Protocol):
    backend: str

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt: ...
