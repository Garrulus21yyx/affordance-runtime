"""Persistent typed task semantics for the short GUI loop.

The program owns only ordered task intent.  Its steps reuse the existing
entity-selector, quantified-set, and aggregate contracts; those reducers keep
their existing evidence and execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeAlias

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.aggregate_objective import AggregateObjective
from affordance_runtime.task.objective_sequence import ObjectiveStep
from affordance_runtime.task.set_objective import SetObjective, predicate_public_value

MAX_TASK_PROGRAM_STEPS = 8

TaskProgramStep: TypeAlias = ObjectiveStep | SetObjective | AggregateObjective
_STEP_TYPES = (ObjectiveStep, SetObjective, AggregateObjective)


class TaskProgramDisposition(StrEnum):
    ACTIVE = "active"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class TaskProgram:
    """One admitted, future-resolvable interpretation of the current task."""

    program_id: str
    steps: tuple[TaskProgramStep, ...]

    def __post_init__(self) -> None:
        values = tuple(self.steps)
        ids = tuple(task_program_step_id(item) for item in values)
        if (
            not self.program_id.startswith("task-program:")
            or not 1 <= len(values) <= MAX_TASK_PROGRAM_STEPS
            or any(not isinstance(item, _STEP_TYPES) for item in values)
            or len(ids) != len(set(ids))
        ):
            raise ValueError("task program is invalid")
        object.__setattr__(self, "steps", values)


@dataclass(frozen=True)
class TaskProgramState:
    program: TaskProgram
    active_index: int = 0
    completed_step_ids: tuple[str, ...] = ()
    issue_code: str = ""
    revision: int = 1

    def __post_init__(self) -> None:
        if (
            not 0 <= self.active_index <= len(self.program.steps)
            or self.revision < 1
            or len(self.completed_step_ids) != len(set(self.completed_step_ids))
        ):
            raise ValueError("task program state is invalid")
        expected = tuple(task_program_step_id(item) for item in self.program.steps[: self.active_index])
        if tuple(self.completed_step_ids) != expected:
            raise ValueError("task program completion lineage is invalid")
        object.__setattr__(self, "completed_step_ids", tuple(self.completed_step_ids))

    @property
    def active_step(self) -> TaskProgramStep | None:
        return self.program.steps[self.active_index] if self.active_index < len(self.program.steps) else None

    @property
    def disposition(self) -> TaskProgramDisposition:
        if self.issue_code:
            return TaskProgramDisposition.BLOCKED
        if self.active_index == len(self.program.steps):
            return TaskProgramDisposition.COMPLETE
        return TaskProgramDisposition.ACTIVE


def establish_task_program_state(program: TaskProgram) -> TaskProgramState:
    return TaskProgramState(program)


def advance_task_program_state(state: TaskProgramState, completed_step_id: str) -> TaskProgramState:
    if state.disposition is not TaskProgramDisposition.ACTIVE or state.active_step is None:
        raise ValueError("only an active task program may advance")
    expected = task_program_step_id(state.active_step)
    if completed_step_id != expected:
        raise ValueError("task program step completion is out of order")
    return replace(
        state,
        active_index=state.active_index + 1,
        completed_step_ids=(*state.completed_step_ids, expected),
        revision=state.revision + 1,
    )


def block_task_program_state(state: TaskProgramState, issue_code: str) -> TaskProgramState:
    if not issue_code.strip():
        raise ValueError("task program block requires a typed issue")
    return replace(state, issue_code=issue_code, revision=state.revision + 1)


def task_program_step_id(step: TaskProgramStep) -> str:
    if isinstance(step, ObjectiveStep):
        return step.step_id
    return step.objective_id


def task_program_public_value(program: TaskProgram) -> dict[str, object]:
    steps: list[dict[str, object]] = []
    for step in program.steps:
        if isinstance(step, ObjectiveStep):
            steps.append(
                {
                    "kind": "entity",
                    "step_id": step.step_id,
                    "predicate": predicate_public_value(step.selector.predicate),
                    "selector_entity_domain": step.selector.entity_domain.value,
                    "semantic_action": step.action_template.semantic_action,
                    "parameters": to_json_compatible(step.action_template.parameters),
                    "postcondition": (
                        predicate_public_value(step.postcondition.predicate)
                        if step.postcondition is not None
                        else None
                    ),
                    "postcondition_entity_domain": (
                        step.postcondition.entity_domain.value if step.postcondition is not None else None
                    ),
                }
            )
        elif isinstance(step, SetObjective):
            steps.append(
                {
                    "kind": "set",
                    "step_id": step.objective_id,
                    "predicate": predicate_public_value(step.predicate),
                    "quantifier": step.quantifier.value,
                    "scope_extent": step.scope.extent.value,
                    "scope_root": step.scope.root_entity_id,
                    "scope_entity_domain": step.scope.entity_domain.value,
                    "semantic_action": step.action_template.semantic_action,
                    "parameters": to_json_compatible(step.action_template.parameters),
                }
            )
        else:
            steps.append(
                {
                    "kind": "aggregate",
                    "step_id": step.objective_id,
                    "scope_extent": step.source_scope.extent.value,
                    "scope_root": step.source_scope.root_entity_id,
                    "scope_entity_domain": step.source_scope.entity_domain.value,
                    "source_predicate": predicate_public_value(step.member_predicate),
                    "value_extractor_kind": step.value_extractor.kind.value,
                    "value_field": step.value_extractor.field_name,
                    "constant": step.value_extractor.constant,
                    "operator": step.operator.value,
                    "destination_predicate": predicate_public_value(step.destination_selector),
                    "semantic_action": step.semantic_action,
                    "parameter_name": step.parameter_name,
                    "output_format": step.output_format.value,
                }
            )
    return {"program_id": program.program_id, "steps": steps}


def task_program_digest(steps: tuple[TaskProgramStep, ...]) -> str:
    provisional = TaskProgram("task-program:provisional", steps)
    encoded = json.dumps(
        task_program_public_value(provisional)["steps"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
