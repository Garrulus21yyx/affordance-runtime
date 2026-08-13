"""Runtime-owned aggregate derivation followed by one destination effect.

The model may describe a source set and operation.  It never supplies the
derived value.  Scope closure, membership, value extraction, deterministic
aggregation, destination resolution, and effect settlement remain Runtime
authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from enum import StrEnum
from numbers import Real
from typing import TypeGuard

from affordance_runtime.evaluation.contracts import ActionEvaluationStatus
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort, SnapshotScopeEnumerator
from affordance_runtime.task.selector_resolution import (
    SelectorResolutionDisposition,
    SelectorResolutionState,
    install_selector_visual_leaf_assessments,
    resolve_entity_selector,
)
from affordance_runtime.task.set_objective import (
    CandidateUniverse,
    PredicateAssessment,
    PredicateAssurance,
    PredicateExpr,
    PredicateTruth,
    ScopeCoverage,
    ScopeSpec,
    evaluate_predicate,
    predicate_digest,
    predicate_public_value,
)
from affordance_runtime.task.set_objective_state import target_public_fields
from affordance_runtime.world.contracts import ActionSpace, WorldObservation

MAX_AGGREGATE_MEMBERS = 256


class AggregateOperator(StrEnum):
    COUNT = "count"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


class ValueExtractorKind(StrEnum):
    CONSTANT = "constant"
    FACT = "fact"


class AggregateOutputFormat(StrEnum):
    INTEGER_STRING = "integer_string"
    DECIMAL_STRING = "decimal_string"
    NUMBER = "number"


class AggregateDisposition(StrEnum):
    NEED_SCOPE_CLOSURE = "need_scope_closure"
    NEED_CLASSIFICATION = "need_classification"
    NEED_VALUES = "need_values"
    NEED_DESTINATION = "need_destination"
    READY = "ready"
    NEED_EFFECT_RESOLUTION = "need_effect_resolution"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ValueExtractor:
    kind: ValueExtractorKind
    field_name: str = ""
    constant: int | float = 1

    def __post_init__(self) -> None:
        if self.kind is ValueExtractorKind.FACT and not self.field_name.strip():
            raise ValueError("fact value extractor requires a field")
        if self.kind is ValueExtractorKind.CONSTANT and not _numeric(self.constant):
            raise ValueError("constant value extractor requires a finite number")


@dataclass(frozen=True)
class AggregateObjective:
    objective_id: str
    source_scope: ScopeSpec
    member_predicate: PredicateExpr
    value_extractor: ValueExtractor
    operator: AggregateOperator
    destination_selector: PredicateExpr
    semantic_action: str = "fill"
    parameter_name: str = "value"
    output_format: AggregateOutputFormat = AggregateOutputFormat.INTEGER_STRING

    def __post_init__(self) -> None:
        if (
            not self.objective_id.startswith("aggregate-objective:")
            or not self.semantic_action.strip()
            or not self.parameter_name.strip()
        ):
            raise ValueError("aggregate objective identity/action contract is invalid")

    @property
    def digest(self) -> str:
        return aggregate_objective_digest(self)


@dataclass(frozen=True)
class AggregateValueEvidence:
    entity_id: str
    value: int | float
    observation_epoch: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.entity_id.strip()
            or not self.observation_epoch.strip()
            or not _numeric(self.value)
            or not self.evidence_refs
        ):
            raise ValueError("aggregate value evidence is invalid")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


@dataclass(frozen=True)
class AggregateObjectiveState:
    objective: AggregateObjective
    universe: CandidateUniverse
    member_truth: tuple[tuple[str, PredicateTruth], ...]
    values: tuple[AggregateValueEvidence, ...]
    destination_entity_id: str = ""
    derived_value: object | None = None
    provenance_digest: str = ""
    action_in_flight: bool = False
    effect_confirmed: bool = False
    effect_evidence_refs: tuple[str, ...] = ()
    issue_code: str = ""
    revision: int = 1
    semantic_leaf_assessments: tuple[PredicateAssessment, ...] = ()
    destination_resolution: SelectorResolutionState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "member_truth", tuple(self.member_truth))
        object.__setattr__(self, "values", tuple(self.values))
        object.__setattr__(self, "effect_evidence_refs", tuple(self.effect_evidence_refs))
        object.__setattr__(self, "semantic_leaf_assessments", tuple(self.semantic_leaf_assessments))
        if self.derived_value is not None:
            object.__setattr__(self, "derived_value", freeze_json(self.derived_value))

    @property
    def disposition(self) -> AggregateDisposition:
        if self.issue_code:
            return AggregateDisposition.BLOCKED
        if self.effect_confirmed:
            return AggregateDisposition.COMPLETE
        if self.action_in_flight:
            return AggregateDisposition.NEED_EFFECT_RESOLUTION
        if self.universe.coverage is not ScopeCoverage.COMPLETE:
            return AggregateDisposition.NEED_SCOPE_CLOSURE
        if any(truth is PredicateTruth.UNKNOWN for _, truth in self.member_truth):
            return AggregateDisposition.NEED_CLASSIFICATION
        true_ids = {entity_id for entity_id, truth in self.member_truth if truth is PredicateTruth.TRUE}
        if (
            self.objective.operator is not AggregateOperator.COUNT
            and {item.entity_id for item in self.values} != true_ids
        ):
            return AggregateDisposition.NEED_VALUES
        if (
            self.destination_resolution is None
            or self.destination_resolution.disposition is not SelectorResolutionDisposition.RESOLVED
            or not self.destination_entity_id
        ):
            return AggregateDisposition.NEED_DESTINATION
        if self.derived_value is None or not self.provenance_digest:
            return AggregateDisposition.BLOCKED
        return AggregateDisposition.READY

    @property
    def reason_code(self) -> str:
        return {
            AggregateDisposition.NEED_SCOPE_CLOSURE: "aggregate_scope_not_closed",
            AggregateDisposition.NEED_CLASSIFICATION: "aggregate_membership_unknown",
            AggregateDisposition.NEED_VALUES: "aggregate_values_unknown",
            AggregateDisposition.NEED_DESTINATION: "aggregate_destination_not_unique",
            AggregateDisposition.READY: "aggregate_destination_action_required",
            AggregateDisposition.NEED_EFFECT_RESOLUTION: "aggregate_effect_unsettled",
            AggregateDisposition.COMPLETE: "aggregate_effect_confirmed",
            AggregateDisposition.BLOCKED: self.issue_code or "aggregate_derivation_invalid",
        }[self.disposition]

    @property
    def action_parameters(self) -> dict[str, object]:
        if self.disposition is not AggregateDisposition.READY:
            return {}
        return {self.objective.parameter_name: self.derived_value}


def establish_aggregate_objective_state(
    objective: AggregateObjective,
    observation: WorldObservation,
    *,
    enumerator: ScopeEnumeratorPort | None = None,
) -> AggregateObjectiveState:
    return _derive(
        objective,
        observation,
        revision=1,
        enumerator=enumerator,
        semantic_leaf_assessments=(),
    )


def refresh_aggregate_objective_state(
    state: AggregateObjectiveState,
    observation: WorldObservation,
    *,
    acted_entity_id: str = "",
    action_status: ActionEvaluationStatus | None = None,
    effect_evidence_refs: tuple[str, ...] = (),
    enumerator: ScopeEnumeratorPort | None = None,
) -> AggregateObjectiveState:
    if acted_entity_id == state.destination_entity_id and action_status is not None:
        if action_status is ActionEvaluationStatus.EFFECT_CONFIRMED:
            return replace(
                state,
                universe=_universe(state.objective.source_scope, observation, enumerator),
                action_in_flight=False,
                effect_confirmed=True,
                effect_evidence_refs=effect_evidence_refs,
                revision=state.revision + 1,
            )
        if action_status is ActionEvaluationStatus.UNKNOWN:
            return replace(
                state,
                universe=_universe(state.objective.source_scope, observation, enumerator),
                action_in_flight=True,
                revision=state.revision + 1,
            )
        if action_status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED:
            return replace(
                _derive(
                    state.objective,
                    observation,
                    revision=state.revision + 1,
                    enumerator=enumerator,
                    semantic_leaf_assessments=(),
                ),
                issue_code="aggregate_destination_no_effect",
            )
    return _derive(
        state.objective,
        observation,
        revision=state.revision + 1,
        enumerator=enumerator,
        semantic_leaf_assessments=(),
    )


def install_aggregate_visual_leaf_assessments(
    state: AggregateObjectiveState,
    observation: WorldObservation,
    leaf: PredicateExpr,
    assessments: tuple[tuple[str, PredicateTruth], ...],
    *,
    evaluator_id: str,
    enumerator: ScopeEnumeratorPort | None = None,
) -> AggregateObjectiveState:
    """Install one visual-leaf batch and deterministically re-evaluate the aggregate."""

    leaf_digest = predicate_digest(leaf)
    submitted = tuple(assessments)
    current_ids = set(state.universe.entity_ids)
    if (
        observation.observation_id != state.universe.observation_epoch
        or not submitted
        or len({entity_id for entity_id, _ in submitted}) != len(submitted)
        or any(entity_id not in current_ids for entity_id, _ in submitted)
    ):
        raise ValueError("aggregate visual leaf evidence is not current and bounded")
    by_key = {
        (item.entity_id, item.predicate_digest): item
        for item in state.semantic_leaf_assessments
        if item.observation_epoch == state.universe.observation_epoch
    }
    for entity_id, truth in submitted:
        by_key[(entity_id, leaf_digest)] = PredicateAssessment(
            entity_id,
            leaf_digest,
            truth,
            PredicateAssurance.SEMANTIC_UNCALIBRATED,
            evaluator_id,
            observation.observation_id,
            (f"aggregate-visual-leaf:{observation.observation_id}:{leaf_digest[:12]}:{entity_id}",),
            None,
        )
    return _derive(
        state.objective,
        observation,
        revision=state.revision + 1,
        enumerator=enumerator,
        semantic_leaf_assessments=tuple(by_key.values()),
    )


def install_aggregate_destination_visual_leaf_assessments(
    state: AggregateObjectiveState,
    observation: WorldObservation,
    leaf: PredicateExpr,
    assessments: tuple[tuple[str, PredicateTruth], ...],
    *,
    evaluator_id: str,
    enumerator: ScopeEnumeratorPort | None = None,
) -> AggregateObjectiveState:
    """Install visual evidence for the destination selector using the same lifecycle."""

    if state.destination_resolution is None:
        raise ValueError("aggregate destination selector is unresolved")
    destination = install_selector_visual_leaf_assessments(
        state.destination_resolution,
        observation,
        leaf,
        assessments,
        evaluator_id=evaluator_id,
        enumerator=enumerator,
    )
    return _derive(
        state.objective,
        observation,
        revision=state.revision + 1,
        enumerator=enumerator,
        semantic_leaf_assessments=state.semantic_leaf_assessments,
        destination_leaf_assessments=destination.semantic_leaf_assessments,
    )


def aggregate_allowed_action_ids(
    state: AggregateObjectiveState,
    action_space: ActionSpace,
) -> frozenset[str]:
    if state.disposition is not AggregateDisposition.READY:
        return frozenset()
    return frozenset(
        option.action_id
        for option in action_space.options
        if option.target_id == state.destination_entity_id and option.semantic_action == state.objective.semantic_action
    )


def aggregate_objective_public_value(objective: AggregateObjective) -> dict[str, object]:
    return {
        "kind": "aggregate",
        "source_scope": objective.source_scope.extent.value,
        "source_entity_domain": objective.source_scope.entity_domain.value,
        "member_predicate": predicate_public_value(objective.member_predicate),
        "value_extractor": {
            "kind": objective.value_extractor.kind.value,
            "field_name": objective.value_extractor.field_name,
            "constant": objective.value_extractor.constant,
        },
        "operator": objective.operator.value,
        "destination_selector": predicate_public_value(objective.destination_selector),
        "semantic_action": objective.semantic_action,
        "parameter_name": objective.parameter_name,
        "output_format": objective.output_format.value,
    }


def aggregate_objective_digest(objective: AggregateObjective) -> str:
    encoded = json.dumps(
        aggregate_objective_public_value(objective),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _derive(
    objective: AggregateObjective,
    observation: WorldObservation,
    *,
    revision: int,
    enumerator: ScopeEnumeratorPort | None = None,
    semantic_leaf_assessments: tuple[PredicateAssessment, ...] = (),
    destination_leaf_assessments: tuple[PredicateAssessment, ...] = (),
) -> AggregateObjectiveState:
    universe = _universe(objective.source_scope, observation, enumerator)
    if len(universe.entity_ids) > MAX_AGGREGATE_MEMBERS:
        return AggregateObjectiveState(
            objective, universe, (), (), issue_code="aggregate_capacity_exceeded", revision=revision
        )
    fields = target_public_fields(observation)
    semantic_by_entity: dict[str, dict[str, PredicateTruth]] = {}
    for item in semantic_leaf_assessments:
        if item.observation_epoch == observation.observation_id:
            semantic_by_entity.setdefault(item.entity_id, {})[item.predicate_digest] = item.truth
    member_truth = tuple(
        (
            entity_id,
            evaluate_predicate(
                objective.member_predicate,
                fields.get(entity_id, {}),
                semantic_by_entity.get(entity_id),
            ),
        )
        for entity_id in universe.entity_ids
    )
    true_ids = tuple(entity_id for entity_id, truth in member_truth if truth is PredicateTruth.TRUE)
    values: list[AggregateValueEvidence] = []
    if objective.operator is not AggregateOperator.COUNT:
        for entity_id in true_ids:
            public = fields.get(entity_id, {})
            raw = (
                objective.value_extractor.constant
                if objective.value_extractor.kind is ValueExtractorKind.CONSTANT
                else public.get(objective.value_extractor.field_name)
            )
            if _numeric(raw):
                values.append(
                    AggregateValueEvidence(
                        entity_id,
                        raw,
                        observation.observation_id,
                        (f"aggregate-source:{observation.observation_id}:{entity_id}",),
                    )
                )
    destination_resolution = resolve_entity_selector(
        f"aggregate-destination:{objective.digest[:16]}",
        objective.destination_selector,
        observation,
        enumerator=enumerator,
        semantic_leaf_assessments=destination_leaf_assessments,
    )
    destination = destination_resolution.resolved_entity_id
    raw_result: int | float | None = None
    if universe.coverage is ScopeCoverage.COMPLETE and not any(
        truth is PredicateTruth.UNKNOWN for _, truth in member_truth
    ):
        if objective.operator is AggregateOperator.COUNT:
            raw_result = len(true_ids)
        elif objective.operator is AggregateOperator.SUM and not true_ids:
            raw_result = 0
        elif len(values) == len(true_ids) and values:
            numbers = [item.value for item in values]
            raw_result = {
                AggregateOperator.SUM: sum(numbers),
                AggregateOperator.MIN: min(numbers),
                AggregateOperator.MAX: max(numbers),
            }[objective.operator]
    derived = _format_result(raw_result, objective.output_format) if raw_result is not None else None
    provenance = ""
    if derived is not None:
        provenance = hashlib.sha256(
            json.dumps(
                {
                    "objective": objective.digest,
                    "epoch": observation.observation_id,
                    "members": true_ids,
                    "values": [(item.entity_id, item.value) for item in values],
                    "result": to_json_compatible(derived),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    issue = ""
    if destination_resolution.disposition is SelectorResolutionDisposition.AMBIGUOUS:
        issue = "aggregate_destination_ambiguous"
    return AggregateObjectiveState(
        objective,
        universe,
        member_truth,
        tuple(values),
        destination,
        derived,
        provenance,
        issue_code=issue,
        revision=revision,
        semantic_leaf_assessments=semantic_leaf_assessments,
        destination_resolution=destination_resolution,
    )


def _universe(
    scope: ScopeSpec,
    observation: WorldObservation,
    enumerator: ScopeEnumeratorPort | None,
) -> CandidateUniverse:
    enumeration = (enumerator or SnapshotScopeEnumerator()).enumerate(scope, observation)
    return CandidateUniverse(
        enumeration.scope_id,
        enumeration.observation_epoch,
        enumeration.entity_ids,
        enumeration.coverage,
        enumeration.evidence_refs,
    )


def _numeric(value: object) -> TypeGuard[int | float]:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def _format_result(value: int | float, output: AggregateOutputFormat) -> object:
    if output is AggregateOutputFormat.NUMBER:
        return value
    if output is AggregateOutputFormat.INTEGER_STRING:
        if float(value).is_integer():
            return str(int(value))
        raise ValueError("integer aggregate output is not integral")
    return format(float(value), ".12g")
