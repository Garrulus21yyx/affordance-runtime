"""Single owner for rolling, observation-resolvable GUI objectives.

The concrete reducers retain their focused algebras.  AgentLoop consumers use
this facade so variant dispatch, refresh lineage, completion and action
authorization have one owner instead of being reimplemented at every boundary.
"""

from __future__ import annotations

import hashlib
import json
from typing import TypeAlias

from affordance_runtime.evaluation.contracts import ActionEvaluationStatus
from affordance_runtime.task.aggregate_objective import (
    AggregateDisposition,
    AggregateObjective,
    AggregateObjectiveState,
    aggregate_allowed_action_ids,
    establish_aggregate_objective_state,
    refresh_aggregate_objective_state,
)
from affordance_runtime.task.objective_sequence import (
    ObjectiveSequence,
    ObjectiveSequenceState,
    SequenceDisposition,
    establish_objective_sequence_state,
    refresh_objective_sequence_state,
    sequence_allowed_action_ids,
)
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort
from affordance_runtime.task.set_objective import SetDisposition, SetObjective
from affordance_runtime.task.set_objective_state import (
    SetObjectiveState,
    establish_set_objective,
    refresh_set_objective_state,
    set_allowed_action_ids,
)
from affordance_runtime.world.contracts import ActionSpace, WorldObservation

LocalObjective: TypeAlias = ObjectiveSequence | SetObjective | AggregateObjective
LocalObjectiveState: TypeAlias = ObjectiveSequenceState | SetObjectiveState | AggregateObjectiveState


def establish_local_objective(
    objective: LocalObjective,
    observation: WorldObservation,
    *,
    enumerator: ScopeEnumeratorPort,
) -> LocalObjectiveState:
    if isinstance(objective, ObjectiveSequence):
        return establish_objective_sequence_state(objective, observation, enumerator=enumerator)
    if isinstance(objective, SetObjective):
        return establish_set_objective(objective, observation, enumerator=enumerator)
    if isinstance(objective, AggregateObjective):
        return establish_aggregate_objective_state(objective, observation, enumerator=enumerator)
    raise TypeError("local objective variant is unsupported")


def refresh_local_objective(
    state: LocalObjectiveState,
    observation: WorldObservation,
    *,
    acted_entity_id: str = "",
    semantic_action: str = "",
    action_status: ActionEvaluationStatus | None = None,
    effect_evidence_refs: tuple[str, ...] = (),
    enumerator: ScopeEnumeratorPort,
) -> LocalObjectiveState:
    """Re-resolve durable semantics against one fresh observation.

    Entity IDs are admitted only when the current reducer already authorized
    the matching semantic action.  Stale action IDs, E-refs and bindings never
    enter this lifecycle.
    """

    admitted_entity_id = (
        acted_entity_id
        if acted_entity_id and semantic_action == local_objective_semantic_action(state)
        else ""
    )
    if isinstance(state, ObjectiveSequenceState):
        return refresh_objective_sequence_state(
            state,
            observation,
            acted_entity_id=admitted_entity_id,
            action_status=action_status if admitted_entity_id else None,
            effect_evidence_refs=effect_evidence_refs if admitted_entity_id else (),
            enumerator=enumerator,
        )
    if isinstance(state, SetObjectiveState):
        return refresh_set_objective_state(
            state,
            observation,
            acted_entity_id=admitted_entity_id,
            action_status=action_status if admitted_entity_id else None,
            effect_evidence_refs=effect_evidence_refs if admitted_entity_id else (),
            enumerator=enumerator,
        )
    if isinstance(state, AggregateObjectiveState):
        return refresh_aggregate_objective_state(
            state,
            observation,
            acted_entity_id=admitted_entity_id,
            action_status=action_status if admitted_entity_id else None,
            effect_evidence_refs=effect_evidence_refs if admitted_entity_id else (),
            enumerator=enumerator,
        )
    raise TypeError("local objective state variant is unsupported")


def local_objective_complete(state: LocalObjectiveState | None) -> bool:
    return (
        state is None
        or isinstance(state, ObjectiveSequenceState)
        and state.disposition is SequenceDisposition.COMPLETE
        or isinstance(state, SetObjectiveState)
        and state.reduction.disposition is SetDisposition.CERTIFIED
        or isinstance(state, AggregateObjectiveState)
        and state.disposition is AggregateDisposition.COMPLETE
    )


def local_objective_allowed_action_ids(
    state: LocalObjectiveState,
    action_space: ActionSpace,
) -> frozenset[str]:
    if isinstance(state, ObjectiveSequenceState):
        return sequence_allowed_action_ids(state, action_space)
    if isinstance(state, SetObjectiveState):
        return set_allowed_action_ids(state, action_space)
    if isinstance(state, AggregateObjectiveState):
        return aggregate_allowed_action_ids(state, action_space)
    raise TypeError("local objective state variant is unsupported")


def local_objective_authority_digest(
    state: LocalObjectiveState | None,
    action_space: ActionSpace,
) -> str:
    if state is None:
        return ""
    payload = (
        type(state).__name__,
        local_objective_observation_id(state),
        state.revision,
        local_objective_complete(state),
        tuple(sorted(local_objective_allowed_action_ids(state, action_space))),
    )
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def local_objective_action_parameters(state: LocalObjectiveState) -> dict[str, object]:
    if isinstance(state, ObjectiveSequenceState):
        step = state.active_step
        return dict(step.action_template.parameters) if step is not None else {}
    if isinstance(state, SetObjectiveState):
        return dict(state.objective.action_template.parameters)
    if isinstance(state, AggregateObjectiveState):
        return state.action_parameters
    raise TypeError("local objective state variant is unsupported")


def local_objective_semantic_action(state: LocalObjectiveState) -> str:
    if isinstance(state, ObjectiveSequenceState):
        step = state.active_step
        return step.action_template.semantic_action if step is not None else ""
    if isinstance(state, SetObjectiveState):
        return state.objective.action_template.semantic_action
    if isinstance(state, AggregateObjectiveState):
        return state.objective.semantic_action
    raise TypeError("local objective state variant is unsupported")


def local_objective_observation_id(state: LocalObjectiveState) -> str:
    if isinstance(state, ObjectiveSequenceState):
        return state.observation_epoch
    if isinstance(state, SetObjectiveState | AggregateObjectiveState):
        return state.universe.observation_epoch
    raise TypeError("local objective state variant is unsupported")
