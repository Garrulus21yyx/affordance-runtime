"""Generic task-to-set projection consumed by the grounded tool catalog.

This module may interpret public task language and evidence.  It cannot create
actions: returned target IDs are intersected with the current ActionSpace by
the catalog, whose private bindings remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.task.set_objective import (
    ActionObligationStatus,
    ActionTemplate,
    CandidateUniverse,
    FactEquals,
    PredicateAssessment,
    PredicateAssurance,
    PredicateTruth,
    SchedulingPolicy,
    ScopeCoverage,
    ScopeExtent,
    ScopeSpec,
    SetDisposition,
    SetMemberObligation,
    SetObjective,
    SetObjectiveReduction,
    SetQuantifier,
    StabilityStatus,
    reduce_set_objective,
)
from affordance_runtime.task.set_objective_compiler import (
    CompiledPublicPredicate,
    PublicCandidateEvidence,
    compile_public_task_predicate,
)


@dataclass(frozen=True)
class CatalogSetProjection:
    objective: SetObjective
    universe: CandidateUniverse
    reduction: SetObjectiveReduction

    @property
    def admitted_target_ids(self) -> tuple[str, ...]:
        if self.reduction.disposition in {
            SetDisposition.READY_FOR_NEXT_MEMBER,
            SetDisposition.AGENT_SELECT_NEXT,
        }:
            return (self.reduction.next_entity_id,) if self.reduction.next_entity_id else self.reduction.true_entity_ids
        return ()

    @property
    def completed_member_ids(self) -> tuple[str, ...]:
        if self.reduction.disposition is not SetDisposition.CERTIFIED:
            return ()
        if isinstance(self.objective.predicate, FactEquals) and self.objective.predicate.field_name == "task_predicate_truth":
            return self.reduction.true_entity_ids
        return self.universe.entity_ids


def project_catalog_set_objective(context: AgentContext) -> CatalogSetProjection | None:
    """Compile only mechanically grounded predicates; ambiguous language stays with the agent."""

    actionable = {item.target_id: item for item in context.actions.options}
    entities_by_target = {
        target_id: next((item for item in context.grounding.entities if item.ref == ref), None)
        for target_id, ref in context.grounding.target_refs.items()
        if target_id in actionable
    }
    entities_by_target = {key: value for key, value in entities_by_target.items() if value is not None}
    public_fields = _public_fields(context, entities_by_target)
    compiled = _compiled_visual_predicate(context.task.instruction, public_fields) or compile_public_task_predicate(
        context.task.instruction,
        tuple(PublicCandidateEvidence(target_id, fields) for target_id, fields in public_fields.items()),
    )
    if compiled is None:
        return None
    field_name, expected = compiled.field_name, compiled.expected
    candidate_ids = tuple(
        target_id for target_id in actionable
        if target_id in public_fields and field_name in public_fields[target_id]
    )
    if not candidate_ids:
        return None
    quantifier = compiled.quantifier
    semantic_actions = {actionable[item].semantic_action for item in candidate_ids}
    if len(semantic_actions) != 1:
        return None
    predicate = FactEquals(field_name, expected)
    digest_basis = json.dumps(
        {"predicate": to_json_compatible(predicate), "quantifier": quantifier.value},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    digest = hashlib.sha256(digest_basis.encode()).hexdigest()
    scope = ScopeSpec(
        f"scope:{digest[:24]}",
        "current-document",
        ScopeExtent.CURRENT_VIEWPORT,
    )
    objective = SetObjective(
        f"set-objective:{digest[:24]}",
        scope,
        predicate,
        quantifier,
        ActionTemplate(next(iter(semantic_actions))),
        SchedulingPolicy(),
    )
    coverage, basis = _scope_coverage(context)
    universe = CandidateUniverse(
        scope.scope_id,
        context.context_id,
        candidate_ids,
        coverage,
        basis,
    )
    visual_classification = field_name == "task_predicate_truth"
    assessments = tuple(
        PredicateAssessment(
            target_id,
            objective.predicate_digest,
            (
                PredicateTruth(str(public_fields[target_id][field_name]))
                if visual_classification
                else PredicateTruth.TRUE if public_fields[target_id][field_name] == expected else PredicateTruth.FALSE
            ),
            PredicateAssurance.SEMANTIC if visual_classification else PredicateAssurance.STRUCTURAL,
            "visual-predicate-classifier" if visual_classification else f"public-fact:{field_name}",
            context.context_id,
            (f"observation:{field_name}:{target_id}",),
        )
        for target_id in candidate_ids
    )
    true_ids = tuple(item.entity_id for item in assessments if item.truth is PredicateTruth.TRUE)
    settled = _confirmed_effect_targets(context, next(iter(semantic_actions)))
    obligations = tuple(
        SetMemberObligation(
            target_id,
            context.context_id,
            PredicateTruth.TRUE,
            (
                ActionObligationStatus.EFFECT_CONFIRMED
                if target_id in settled else ActionObligationStatus.UNACTED
            ),
            ((f"history:effect-confirmed:{target_id}",) if target_id in settled else ()),
            context.context_id if target_id in settled else "",
        )
        for target_id in true_ids
    )
    all_settled = bool(obligations) and all(
        item.action_status is ActionObligationStatus.EFFECT_CONFIRMED for item in obligations
    )
    reduction = reduce_set_objective(
        objective,
        universe,
        assessments,
        obligations,
        stability_status=(StabilityStatus.PASSED if all_settled else StabilityStatus.PENDING),
    )
    return CatalogSetProjection(objective, universe, reduction)


def _public_fields(context: AgentContext, entities: Mapping[str, object]) -> dict[str, dict[str, object]]:
    values = {target_id: dict(entity.state) for target_id, entity in entities.items()}
    for fact in context.world.facts.items:
        if fact.subject_id in values:
            values[fact.subject_id][fact.predicate] = fact.value
    return values


def _compiled_visual_predicate(
    instruction: str,
    public_fields: Mapping[str, Mapping[str, object]],
) -> CompiledPublicPredicate | None:
    instruction_digest = hashlib.sha256(instruction.encode()).hexdigest()
    classified = tuple(
        fields for fields in public_fields.values()
        if fields.get("task_predicate_digest") == instruction_digest
        and fields.get("task_predicate_truth") in {item.value for item in PredicateTruth}
    )
    if not classified:
        return None
    return CompiledPublicPredicate(
        "task_predicate_truth", "true", SetQuantifier.ALL_IN_CLOSED_SCOPE,
    )


def _scope_coverage(context: AgentContext) -> tuple[ScopeCoverage, tuple[str, ...]]:
    if context.world.targets.truncated or context.actions.truncated or context.actions.has_more:
        return ScopeCoverage.PARTIAL, ()
    owners = tuple(
        f"source:{item.modality}:entity-inventory"
        for item in context.world.sources
        if item.projection_coverage == "complete" and item.entity_inventory.status == "complete"
    )
    if owners:
        return ScopeCoverage.COMPLETE, owners
    return ScopeCoverage.UNKNOWN, ()


def _confirmed_effect_targets(context: AgentContext, semantic_action: str) -> frozenset[str]:
    return frozenset(
        item.target_id for item in context.history.items
        if item.semantic_action == semantic_action
        and item.dispatch_status == "sent"
        and item.action_evaluation_status == "effect_confirmed"
    )
