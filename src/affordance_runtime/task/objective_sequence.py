"""Persistent typed GUI steps resolved against every fresh observation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.evaluation.contracts import ActionEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort
from affordance_runtime.task.selector_resolution import (
    SelectorResolutionDisposition,
    SelectorResolutionState,
    resolve_entity_selector,
)
from affordance_runtime.task.set_objective import (
    ActionTemplate,
    PredicateExpr,
    predicate_public_value,
)
from affordance_runtime.task_action_family_resolution import action_family_value
from affordance_runtime.world.contracts import ActionSpace, WorldObservation

MAX_OBJECTIVE_SEQUENCE_STEPS = 8
SUPPORTED_SEQUENCE_ACTIONS = (
    "activate",
    "drag",
    "navigate",
    "press_key",
    "scroll",
    "select_option",
    "set_value",
    "type_text",
)


@dataclass(frozen=True)
class EntitySelector:
    predicate: PredicateExpr

    @property
    def digest(self) -> str:
        payload = json.dumps(
            predicate_public_value(self.predicate),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ObjectiveStep:
    step_id: str
    selector: EntitySelector
    action_template: ActionTemplate
    postcondition: EntitySelector | None = None

    def __post_init__(self) -> None:
        if (
            not self.step_id.strip()
            or len(self.step_id) > 120
            or self.action_template.semantic_action not in SUPPORTED_SEQUENCE_ACTIONS
        ):
            raise ValueError("objective step identity is invalid")


@dataclass(frozen=True)
class ObjectiveSequence:
    sequence_id: str
    steps: tuple[ObjectiveStep, ...]

    def __post_init__(self) -> None:
        steps = tuple(self.steps)
        if (
            not self.sequence_id.strip()
            or not 1 <= len(steps) <= MAX_OBJECTIVE_SEQUENCE_STEPS
            or len({item.step_id for item in steps}) != len(steps)
        ):
            raise ValueError("objective sequence is invalid")
        object.__setattr__(self, "steps", steps)


class SequenceDisposition(StrEnum):
    READY = "ready"
    NEED_EVIDENCE = "need_evidence"
    WAITING_POSTCONDITION = "waiting_postcondition"
    AMBIGUOUS = "ambiguous"
    BLOCKED = "blocked"
    COMPLETE = "complete"


@dataclass(frozen=True)
class ObjectiveSequenceState:
    sequence: ObjectiveSequence
    active_index: int
    observation_epoch: str
    disposition: SequenceDisposition
    resolved_target_id: str = ""
    unknown_target_ids: tuple[str, ...] = ()
    reason_code: str = ""
    pending_postcondition: EntitySelector | None = None
    completed_step_ids: tuple[str, ...] = ()
    effect_evidence_refs: tuple[str, ...] = ()
    revision: int = 1
    selector_resolution: SelectorResolutionState | None = None

    def __post_init__(self) -> None:
        if (
            not 0 <= self.active_index <= len(self.sequence.steps)
            or not self.observation_epoch.strip()
            or not isinstance(self.disposition, SequenceDisposition)
            or self.revision < 1
        ):
            raise ValueError("objective sequence state is invalid")
        object.__setattr__(self, "unknown_target_ids", tuple(self.unknown_target_ids))
        object.__setattr__(self, "completed_step_ids", tuple(self.completed_step_ids))
        object.__setattr__(self, "effect_evidence_refs", tuple(self.effect_evidence_refs))

    @property
    def active_step(self) -> ObjectiveStep | None:
        return self.sequence.steps[self.active_index] if self.active_index < len(self.sequence.steps) else None


def establish_objective_sequence_state(
    sequence: ObjectiveSequence,
    observation: WorldObservation,
    *,
    enumerator: ScopeEnumeratorPort | None = None,
) -> ObjectiveSequenceState:
    return _resolve(
        ObjectiveSequenceState(
            sequence,
            0,
            observation.observation_id,
            SequenceDisposition.BLOCKED,
            reason_code="unresolved",
        ),
        observation,
        enumerator=enumerator,
    )


def refresh_objective_sequence_state(
    state: ObjectiveSequenceState,
    observation: WorldObservation,
    *,
    acted_entity_id: str = "",
    action_status: ActionEvaluationStatus | None = None,
    effect_evidence_refs: tuple[str, ...] = (),
    enumerator: ScopeEnumeratorPort | None = None,
) -> ObjectiveSequenceState:
    """Re-resolve selectors and advance only after a confirmed current effect."""

    if state.disposition is SequenceDisposition.COMPLETE:
        return replace(
            state,
            observation_epoch=observation.observation_id,
            revision=state.revision + 1,
        )
    if acted_entity_id:
        if (
            state.disposition is not SequenceDisposition.READY
            or acted_entity_id != state.resolved_target_id
            or action_status is None
        ):
            return replace(
                state,
                observation_epoch=observation.observation_id,
                disposition=SequenceDisposition.BLOCKED,
                reason_code="sequence_effect_lineage_mismatch",
                revision=state.revision + 1,
            )
        if action_status is not ActionEvaluationStatus.EFFECT_CONFIRMED:
            return replace(
                state,
                observation_epoch=observation.observation_id,
                disposition=SequenceDisposition.BLOCKED,
                reason_code=f"sequence_effect_{action_status.value}",
                revision=state.revision + 1,
            )
        step = state.active_step
        assert step is not None
        state = replace(
            state,
            active_index=state.active_index + 1,
            observation_epoch=observation.observation_id,
            resolved_target_id="",
            unknown_target_ids=(),
            pending_postcondition=step.postcondition,
            completed_step_ids=(*state.completed_step_ids, step.step_id),
            effect_evidence_refs=(*state.effect_evidence_refs, *effect_evidence_refs),
            revision=state.revision + 1,
            selector_resolution=None,
        )
    else:
        state = replace(
            state,
            observation_epoch=observation.observation_id,
            revision=state.revision + 1,
            selector_resolution=(
                state.selector_resolution
                if state.selector_resolution is not None
                and state.selector_resolution.universe.observation_epoch == observation.observation_id
                else None
            ),
        )
    return _resolve(state, observation, enumerator=enumerator)


def install_sequence_selector_resolution(
    state: ObjectiveSequenceState,
    resolution: SelectorResolutionState,
) -> ObjectiveSequenceState:
    expected = (
        state.pending_postcondition.predicate
        if state.pending_postcondition is not None
        else state.active_step.selector.predicate
        if state.active_step is not None
        else None
    )
    if expected is None or predicate_public_value(expected) != predicate_public_value(resolution.predicate):
        raise ValueError("sequence selector evidence does not match the active selector")
    return _apply_resolution(
        state,
        resolution,
        postcondition=state.pending_postcondition is not None,
    )


def sequence_allowed_action_ids(
    state: ObjectiveSequenceState,
    action_space: ActionSpace,
) -> frozenset[str]:
    step = state.active_step
    if state.disposition is not SequenceDisposition.READY or step is None:
        return frozenset()
    return frozenset(
        option.action_id
        for option in action_space.options
        if option.target_id == state.resolved_target_id
        and action_family_value(option.semantic_action) == step.action_template.semantic_action
    )


def sequence_public_value(sequence: ObjectiveSequence) -> dict[str, object]:
    return {
        "sequence_id": sequence.sequence_id,
        "steps": [
            {
                "step_id": step.step_id,
                "selector": predicate_public_value(step.selector.predicate),
                "semantic_action": step.action_template.semantic_action,
                "parameters": to_json_compatible(step.action_template.parameters),
                "postcondition": (
                    predicate_public_value(step.postcondition.predicate) if step.postcondition is not None else None
                ),
            }
            for step in sequence.steps
        ],
    }


def _resolve(
    state: ObjectiveSequenceState,
    observation: WorldObservation,
    *,
    enumerator: ScopeEnumeratorPort | None,
) -> ObjectiveSequenceState:
    if state.pending_postcondition is not None:
        resolution = _resolution(
            state,
            state.pending_postcondition.predicate,
            observation,
            f"sequence:{state.sequence.sequence_id}:postcondition:{state.active_index}",
            enumerator,
        )
        state = _apply_resolution(state, resolution, postcondition=True)
        if state.pending_postcondition is not None:
            return state
    step = state.active_step
    if step is None:
        return replace(
            state,
            disposition=SequenceDisposition.COMPLETE,
            resolved_target_id="",
            unknown_target_ids=(),
            reason_code="sequence_complete",
            selector_resolution=None,
        )
    resolution = _resolution(
        state,
        step.selector.predicate,
        observation,
        f"sequence:{state.sequence.sequence_id}:step:{state.active_index}",
        enumerator,
    )
    return _apply_resolution(state, resolution, postcondition=False)


def _resolution(
    state: ObjectiveSequenceState,
    predicate: PredicateExpr,
    observation: WorldObservation,
    selector_id: str,
    enumerator: ScopeEnumeratorPort | None,
) -> SelectorResolutionState:
    prior = state.selector_resolution
    return resolve_entity_selector(
        selector_id,
        predicate,
        observation,
        enumerator=enumerator,
        semantic_leaf_assessments=(
            prior.semantic_leaf_assessments
            if prior is not None and predicate_public_value(prior.predicate) == predicate_public_value(predicate)
            else ()
        ),
    )


def _apply_resolution(
    state: ObjectiveSequenceState,
    resolution: SelectorResolutionState,
    *,
    postcondition: bool,
) -> ObjectiveSequenceState:
    disposition = resolution.disposition
    if disposition in {
        SelectorResolutionDisposition.NEED_SCOPE_CLOSURE,
        SelectorResolutionDisposition.NEED_EVIDENCE,
    }:
        return replace(
            state,
            disposition=SequenceDisposition.NEED_EVIDENCE,
            resolved_target_id="",
            unknown_target_ids=resolution.unknown_entity_ids,
            reason_code=(
                "sequence_postcondition_evidence_required" if postcondition else "sequence_selector_evidence_required"
            ),
            selector_resolution=resolution,
        )
    if disposition is SelectorResolutionDisposition.AMBIGUOUS:
        return replace(
            state,
            disposition=SequenceDisposition.AMBIGUOUS,
            resolved_target_id="",
            unknown_target_ids=(),
            reason_code=("sequence_postcondition_ambiguous" if postcondition else "sequence_selector_ambiguous"),
            selector_resolution=resolution,
        )
    if disposition is SelectorResolutionDisposition.NO_MATCH:
        return replace(
            state,
            disposition=(SequenceDisposition.WAITING_POSTCONDITION if postcondition else SequenceDisposition.BLOCKED),
            resolved_target_id="",
            unknown_target_ids=(),
            reason_code=("sequence_postcondition_not_observed" if postcondition else "sequence_selector_no_match"),
            selector_resolution=resolution,
        )
    if postcondition:
        return replace(
            state,
            pending_postcondition=None,
            selector_resolution=None,
        )
    return replace(
        state,
        disposition=SequenceDisposition.READY,
        resolved_target_id=resolution.resolved_entity_id,
        unknown_target_ids=(),
        reason_code="sequence_step_ready",
        selector_resolution=resolution,
    )
