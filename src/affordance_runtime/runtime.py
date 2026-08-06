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
    task_id: str = ""
    goal: str = ""
    target: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    admitted_task: AdmittedTaskSpec | None = None

    @property
    def task_spec(self) -> TaskSpec | None:
        return self.admitted_task.task_spec if self.admitted_task is not None else None

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", freeze_json(self.constraints))
        object.__setattr__(self, "capabilities", FrozenSequence(self.capabilities))
        task_spec = self.task_spec
        if task_spec is None:
            if not self.task_id or not self.goal:
                raise ValueError("legacy RunRequest requires task_id and goal")
            return
        if self.task_id and self.task_id != task_spec.task_id:
            raise ValueError("RunRequest task_id does not match TaskSpec")
        if self.goal and self.goal != task_spec.objective:
            raise ValueError("RunRequest goal does not match TaskSpec objective")
        object.__setattr__(self, "task_id", task_spec.task_id)
        object.__setattr__(self, "goal", task_spec.objective)
        targets = task_effect_targets(task_spec)
        if not self.target and targets:
            object.__setattr__(self, "target", targets[0])


def legacy_run_request(*, task_spec: TaskSpec, **kwargs: Any) -> RunRequest:
    """P5-3 adapter for explicit pre-Authority fixtures and legacy profiles."""

    from affordance_runtime.task_spec_authority import admit_legacy_task_spec

    return RunRequest(admitted_task=admit_legacy_task_spec(task_spec), **kwargs)


class Executor(Protocol):
    backend: str

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt: ...
