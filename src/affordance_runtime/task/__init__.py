"""Stable lazy facade for target task contracts.

The package facade performs no eager imports.  This keeps canonical planning
contracts independent from target execution implementations while preserving
the public import surface.
"""

from __future__ import annotations

from importlib import import_module

_MODULE_EXPORTS = {
    "affordance_runtime.task.contracts": {
        "EvaluationSpec", "LoopBudget", "MaterialBinding", "RiskProfile", "TaskGoal",
    },
    "affordance_runtime.task.aggregate_objective": {
        "AggregateDisposition", "AggregateObjective", "AggregateObjectiveState", "AggregateOperator",
        "AggregateOutputFormat", "AggregateValueEvidence", "ValueExtractor", "ValueExtractorKind",
        "aggregate_allowed_action_ids", "aggregate_objective_public_value", "establish_aggregate_objective_state",
        "install_aggregate_destination_visual_leaf_assessments", "install_aggregate_visual_leaf_assessments",
        "refresh_aggregate_objective_state",
    },
    "affordance_runtime.task.hypothesis_contracts": {
        "HypothesisItemRejection", "HypothesisPredicateAssessment", "HypothesisProposalMode",
        "HypothesisRejectionCode", "HypothesisSetCompleteness", "RequirementHypothesisFailure",
        "RequirementHypothesisFailureKind", "RequirementHypothesisProposal", "RequirementHypothesisProposalBatch",
        "RequirementHypothesisProposer", "RequirementHypothesisState", "TrackedHypothesisStatus",
        "TrackedRequirementHypothesis",
    },
    "affordance_runtime.task.hypothesis_runtime": {
        "HypothesisAdmissionCode", "HypothesisAdmissionResult", "admit_requirement_hypotheses",
        "assess_requirement_hypotheses",
    },
    "affordance_runtime.task.intent_context": {"IntentContext", "IntentExcerpt", "IntentSourceKind"},
    "affordance_runtime.task.local_objective": {
        "LocalObjective", "LocalObjectiveState", "establish_local_objective",
        "local_objective_action_parameters", "local_objective_allowed_action_ids", "local_objective_authority_digest",
        "local_objective_complete", "local_objective_observation_id",
        "refresh_local_objective",
    },
    "affordance_runtime.task.selector_resolution": {
        "SelectorResolutionDisposition", "SelectorResolutionState", "install_selector_visual_leaf_assessments",
        "resolve_entity_selector",
    },
    "affordance_runtime.task.set_objective": {
        "ActionObligationStatus", "ActionTemplate", "And", "CandidateUniverse", "Compare", "CompareOperator",
        "FactEquals", "MemberOrdering", "Not", "Or", "PredicateAssessment", "PredicateAssurance",
        "PredicateTruth", "SchedulingMode", "SchedulingPolicy", "ScopeCoverage", "ScopeEntityDomain",
        "ScopeExtent", "ScopeSpec", "SetCompletionCertificate", "SetDisposition", "SetMemberObligation",
        "SetObjective", "SetObjectiveReduction", "SetQuantifier", "SpatialRelation", "StabilityStatus",
        "VisualAttribute", "VisualConcept", "evaluate_predicate", "predicate_digest", "predicate_public_value",
        "reduce_set_objective", "transition_obligation", "visual_predicate_leaves",
    },
    "affordance_runtime.task.set_objective_state": {
        "MAX_SET_MEMBERS", "SetEvidenceNeedKind", "SetEvidenceObligation", "SetObjectiveState",
        "SetObjectiveStateError", "SetObjectiveStateErrorCode", "establish_set_objective_state",
        "install_semantic_assessments", "refresh_set_objective_state", "set_allowed_action_ids",
        "set_evidence_obligations",
    },
    "affordance_runtime.task_plan_contracts": {"TaskPlan"},
}

_EXPORTS = {name: module for module, names in _MODULE_EXPORTS.items() for name in names}
__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value
