"""Canonical executable semantics attached to one admitted TaskPlan step.

These contracts are plan data, not model-policy commands.  Runtime materializes
exactly one current execution state from the active StepSpec on each observation;
model projections can describe that state but can never reconstruct it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from affordance_runtime.task.aggregate_objective import (
    AggregateObjective,
    AggregateObjectiveState,
    establish_aggregate_objective_state,
)
from affordance_runtime.task.objective_sequence import (
    EntitySelector,
    ObjectiveSequence,
    ObjectiveSequenceState,
    ObjectiveStep,
    establish_objective_sequence_state,
)
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort
from affordance_runtime.task.set_objective import ActionTemplate, SetObjective, predicate_digest
from affordance_runtime.task.set_objective_state import SetObjectiveState, establish_set_objective_state
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class EntityStepExecution:
    """Resolve one semantic entity selector and execute one action template."""

    selector: EntitySelector
    action_template: ActionTemplate
    postcondition: EntitySelector | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action_template, ActionTemplate):
            raise TypeError("entity step action template must be typed")


@dataclass(frozen=True)
class SetStepExecution:
    objective: SetObjective


@dataclass(frozen=True)
class AggregateStepExecution:
    objective: AggregateObjective


StepExecutionSpec: TypeAlias = EntityStepExecution | SetStepExecution | AggregateStepExecution
StepExecutionState: TypeAlias = SetObjectiveState | ObjectiveSequenceState | AggregateObjectiveState


def materialize_step_execution(
    step_id: str,
    execution: object,
    observation: WorldObservation,
    *,
    enumerator: ScopeEnumeratorPort,
) -> StepExecutionState:
    """Create observation-bound runtime state directly from admitted plan data."""

    if not isinstance(execution, EntityStepExecution | SetStepExecution | AggregateStepExecution):
        raise TypeError("unsupported planned step execution")
    if isinstance(execution, EntityStepExecution):
        step = ObjectiveStep(
            step_id,
            execution.selector,
            execution.action_template,
            execution.postcondition,
        )
        return establish_objective_sequence_state(
            ObjectiveSequence(f"plan-step:{step_id}", (step,)),
            observation,
            enumerator=enumerator,
        )
    if isinstance(execution, AggregateStepExecution):
        return establish_aggregate_objective_state(
            execution.objective,
            observation,
            enumerator=enumerator,
        )
    objective = execution.objective
    return establish_set_objective_state(
        predicate=objective.predicate,
        quantifier=objective.quantifier,
        semantic_action=objective.action_template.semantic_action,
        candidate_entity_ids=(),
        observation=observation,
        parameters=dict(objective.action_template.parameters),
        scope=objective.scope,
        enumerator=enumerator,
    )


def planned_execution_identity(execution: object) -> str:
    if not isinstance(execution, EntityStepExecution | SetStepExecution | AggregateStepExecution):
        raise TypeError("unsupported planned step execution")
    if isinstance(execution, EntityStepExecution):
        return execution.selector.digest
    if isinstance(execution, AggregateStepExecution):
        return execution.objective.digest
    return predicate_digest(execution.objective.predicate)
