"""Single facade for the active admitted TaskPlan step execution state.

This module owns no task semantics.  It exposes a stable lifecycle/authority
API over the existing sequence, set, and aggregate reducers so AgentLoop,
projection, and admission do not dispatch the variants independently.
"""

from __future__ import annotations

import hashlib
import json

from affordance_runtime.evaluation.contracts import ActionEvaluationStatus
from affordance_runtime.task.aggregate_objective import (
    AggregateDisposition,
    AggregateObjectiveState,
    aggregate_allowed_action_ids,
    refresh_aggregate_objective_state,
)
from affordance_runtime.task.objective_sequence import (
    ObjectiveSequenceState,
    SequenceDisposition,
    refresh_objective_sequence_state,
    sequence_allowed_action_ids,
)
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort
from affordance_runtime.task.set_objective import SetDisposition
from affordance_runtime.task.set_objective_state import (
    SetObjectiveState,
    refresh_set_objective_state,
    set_allowed_action_ids,
)
from affordance_runtime.task.step_execution import StepExecutionState
from affordance_runtime.task_action_family_resolution import action_family_value
from affordance_runtime.world.contracts import ActionSpace, WorldObservation


def step_execution_complete(state: StepExecutionState | None) -> bool:
    return bool(
        isinstance(state, ObjectiveSequenceState) and state.disposition is SequenceDisposition.COMPLETE
        or isinstance(state, SetObjectiveState) and state.reduction.disposition is SetDisposition.CERTIFIED
        or isinstance(state, AggregateObjectiveState) and state.disposition is AggregateDisposition.COMPLETE
    )


def step_execution_allowed_action_ids(
    state: StepExecutionState,
    action_space: ActionSpace,
) -> frozenset[str]:
    if isinstance(state, ObjectiveSequenceState):
        return sequence_allowed_action_ids(state, action_space)
    if isinstance(state, SetObjectiveState):
        return set_allowed_action_ids(state, action_space)
    if isinstance(state, AggregateObjectiveState):
        return aggregate_allowed_action_ids(state, action_space)
    raise TypeError("unsupported step execution state")


def step_execution_action_parameters(state: StepExecutionState) -> dict[str, object]:
    if isinstance(state, ObjectiveSequenceState):
        return dict(state.active_step.action_template.parameters) if state.active_step is not None else {}
    if isinstance(state, SetObjectiveState):
        return dict(state.objective.action_template.parameters)
    if isinstance(state, AggregateObjectiveState):
        return state.action_parameters
    raise TypeError("unsupported step execution state")


def step_execution_semantic_action(state: StepExecutionState) -> str:
    if isinstance(state, ObjectiveSequenceState):
        return state.active_step.action_template.semantic_action if state.active_step is not None else ""
    if isinstance(state, SetObjectiveState):
        return state.objective.action_template.semantic_action
    if isinstance(state, AggregateObjectiveState):
        return state.objective.semantic_action
    raise TypeError("unsupported step execution state")


def step_execution_observation_id(state: StepExecutionState) -> str:
    if isinstance(state, ObjectiveSequenceState):
        return state.observation_epoch
    if isinstance(state, SetObjectiveState | AggregateObjectiveState):
        return state.universe.observation_epoch
    raise TypeError("unsupported step execution state")


def step_execution_authority_digest(state: StepExecutionState | None, action_space: ActionSpace) -> str:
    if state is None:
        return ""
    payload = (
        type(state).__name__,
        step_execution_observation_id(state),
        state.revision,
        step_execution_complete(state),
        tuple(sorted(step_execution_allowed_action_ids(state, action_space))),
    )
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def refresh_step_execution(
    state: StepExecutionState,
    observation: WorldObservation,
    *,
    acted_entity_id: str = "",
    semantic_action: str = "",
    action_status: ActionEvaluationStatus | None = None,
    effect_evidence_refs: tuple[str, ...] = (),
    enumerator: ScopeEnumeratorPort,
) -> StepExecutionState:
    """Re-resolve durable planned semantics against one fresh observation."""

    admitted_entity_id = (
        acted_entity_id
        if acted_entity_id
        and action_family_value(semantic_action) == action_family_value(step_execution_semantic_action(state))
        else ""
    )
    common = {
        "acted_entity_id": admitted_entity_id,
        "action_status": action_status if admitted_entity_id else None,
        "effect_evidence_refs": effect_evidence_refs if admitted_entity_id else (),
        "enumerator": enumerator,
    }
    if isinstance(state, ObjectiveSequenceState):
        return refresh_objective_sequence_state(state, observation, **common)
    if isinstance(state, SetObjectiveState):
        return refresh_set_objective_state(state, observation, **common)
    if isinstance(state, AggregateObjectiveState):
        return refresh_aggregate_objective_state(state, observation, **common)
    raise TypeError("unsupported step execution state")
