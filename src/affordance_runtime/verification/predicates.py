"""Pure recursive evaluation of canonical criterion expressions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from affordance_runtime.criteria import (
    MECHANICAL_BASELINE_OPERATORS,
    AllOf,
    AnyOf,
    CriterionExpr,
    LiteralValue,
    Not,
    OpenSemanticCriterion,
    PredicateExpr,
    PredicateOperator,
)
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionEvaluation,
    CriterionPolicy,
    CriterionStatus,
    EvidenceValidityMode,
    PredicateEvidence,
    PredicateEvidenceContext,
    SatisfactionMode,
)


class EvidenceProvider(Protocol):
    def evidence_for(
        self, predicate: PredicateExpr, context: PredicateEvidenceContext
    ) -> tuple[PredicateEvidence, ...]: ...


@dataclass(frozen=True)
class PredicateEvaluator:
    providers: tuple[EvidenceProvider, ...] = field(default_factory=lambda: _providers())

    def evaluate(self, expression: CriterionExpr, context: PredicateEvidenceContext) -> CriterionEvaluation:
        if isinstance(expression, PredicateExpr):
            return self._predicate(expression, context)
        if isinstance(expression, OpenSemanticCriterion):
            return CriterionEvaluation(
                expression.criterion_id,
                CriterionStatus.UNSUPPORTED,
                reason_code="open_semantic_requires_explicit_resolver",
            )
        if isinstance(expression, Not):
            child = self.evaluate(expression.child, context)
            status = {
                CriterionStatus.SATISFIED: CriterionStatus.UNSATISFIED,
                CriterionStatus.UNSATISFIED: CriterionStatus.SATISFIED,
            }.get(child.status, child.status)
            return _composite(expression.criterion_id, status, (child,), "not")
        children = tuple(self.evaluate(child, context) for child in expression.children)
        statuses = tuple(item.status for item in children)
        if isinstance(expression, AllOf):
            status = _all_status(statuses)
            return _composite(expression.criterion_id, status, children, "all_of")
        if isinstance(expression, AnyOf):
            status = _any_status(statuses)
            return _composite(expression.criterion_id, status, children, "any_of")
        raise TypeError(f"unsupported criterion expression: {type(expression).__name__}")

    def _predicate(self, predicate: PredicateExpr, context: PredicateEvidenceContext) -> CriterionEvaluation:
        if predicate.operator not in MECHANICAL_BASELINE_OPERATORS:
            return CriterionEvaluation(
                predicate.criterion_id,
                CriterionStatus.UNSUPPORTED,
                reason_code="registered_operator_has_no_mechanical_coverage",
            )
        provided = tuple(item for provider in self.providers for item in provider.evidence_for(predicate, context))
        causal = tuple(
            item
            for item in context.evidence
            if predicate.policy.satisfaction == SatisfactionMode.ACTION_CAUSED
            and predicate.criterion_id in item.effect_criterion_ids
        )
        evidence = tuple({item.evidence_ref: item for item in (*provided, *causal)}.values())
        allowed = tuple(item for item in evidence if _admitted(item, predicate, context))
        if any(item.conflict for item in evidence) or _material_value_conflict(allowed):
            return _evaluation(predicate, CriterionStatus.CONFLICT, allowed, "material_evidence_conflict")
        stale = tuple(item for item in evidence if _is_stale_current_evidence(item, predicate, context))
        if not allowed:
            return _evaluation(
                predicate,
                CriterionStatus.STALE if stale else CriterionStatus.UNKNOWN,
                evidence,
                "evidence_stale_or_policy_rejected" if stale else "no_admitted_evidence",
            )
        try:
            matches = tuple(_matches(predicate, item.observed_value) for item in allowed)
        except (TypeError, ValueError):
            return _evaluation(predicate, CriterionStatus.ERROR, allowed, "predicate_evaluation_error")
        status = (
            CriterionStatus.CONFLICT
            if len(set(matches)) > 1
            else CriterionStatus.SATISFIED
            if all(matches)
            else CriterionStatus.UNSATISFIED
        )
        return _evaluation(predicate, status, allowed, "mechanical_predicate_evaluated")


def _admitted(
    evidence: PredicateEvidence,
    predicate: PredicateExpr,
    context: PredicateEvidenceContext,
) -> bool:
    return evidence_admitted_by_policy(
        evidence,
        predicate.policy,
        context,
        criterion_id=predicate.criterion_id,
    )


def evidence_admitted_by_policy(
    evidence: PredicateEvidence,
    policy: CriterionPolicy,
    context: PredicateEvidenceContext,
    *,
    criterion_id: str,
) -> bool:
    """Shared evidence-policy gate for predicate and task-success evaluation."""

    if policy.allowed_source_kinds and evidence.source_kind not in policy.allowed_source_kinds:
        return False
    assurance_rank = {
        AssuranceLevel.WEAK: 0,
        AssuranceLevel.STRUCTURAL: 1,
        AssuranceLevel.AUTHORITATIVE: 2,
    }
    if assurance_rank[evidence.assurance] < assurance_rank[policy.minimum_assurance]:
        return False
    if policy.validity == EvidenceValidityMode.CURRENT_OBSERVATION:
        if not context.current_observation_ref or evidence.observation_ref != context.current_observation_ref:
            return False
    elif policy.validity == EvidenceValidityMode.RECENT_ACTION:
        if (
            evidence.evidence_ref not in context.recent_evidence_refs
            or evidence.contract_id not in context.recent_contract_ids
        ):
            return False
    elif policy.validity == EvidenceValidityMode.DURABLE:
        if not evidence.durable or evidence.evidence_ref not in context.durable_evidence_refs:
            return False
    elif policy.validity == EvidenceValidityMode.FINAL_RECHECK:
        if not (
            evidence.runtime_final_recheck
            and evidence.authoritative_final_recheck
            and evidence.observation_ref == context.current_observation_ref
            and context.latest_final_recheck_ref
            and evidence.final_recheck_ref == context.latest_final_recheck_ref
        ):
            return False
        versions = dict(context.current_resource_versions)
        if evidence.subject_ref in versions and (
            not evidence.resource_version or evidence.resource_version != versions[evidence.subject_ref]
        ):
            return False
    if policy.satisfaction == SatisfactionMode.ACTION_CAUSED:
        if not (
            evidence.runtime_causal_lineage
            and evidence.contract_id
            and (
                evidence.contract_id == context.current_contract_id
                or evidence.contract_id in context.recent_contract_ids
            )
            and evidence.receipt_ref
            and evidence.pre_observation_ref
            and evidence.post_observation_ref
            and criterion_id in evidence.effect_criterion_ids
            and (
                policy.validity == EvidenceValidityMode.RECENT_ACTION
                or evidence.post_observation_ref == context.current_observation_ref
            )
        ):
            return False
    return not evidence.error_code


def _is_stale_current_evidence(
    evidence: PredicateEvidence,
    predicate: PredicateExpr,
    context: PredicateEvidenceContext,
) -> bool:
    policy = predicate.policy
    assurance_rank = {
        AssuranceLevel.WEAK: 0,
        AssuranceLevel.STRUCTURAL: 1,
        AssuranceLevel.AUTHORITATIVE: 2,
    }
    return bool(
        policy.validity == EvidenceValidityMode.CURRENT_OBSERVATION
        and evidence.observation_ref
        and evidence.observation_ref != context.current_observation_ref
        and (not policy.allowed_source_kinds or evidence.source_kind in policy.allowed_source_kinds)
        and assurance_rank[evidence.assurance] >= assurance_rank[policy.minimum_assurance]
    )


def _matches(predicate: PredicateExpr, observed: object) -> bool:
    expected = predicate.value.value if isinstance(predicate.value, LiteralValue) else None
    operator = predicate.operator
    if operator == PredicateOperator.EXISTS:
        return observed is not None and observed is not False
    if operator == PredicateOperator.ABSENT:
        return observed is None or observed is False
    if operator == PredicateOperator.CHANGED:
        return bool(observed)
    if operator in {PredicateOperator.SELECTED, PredicateOperator.CHECKED}:
        return bool(observed) if expected is None else observed == expected
    if operator == PredicateOperator.EQUALS:
        return observed == expected
    if operator == PredicateOperator.CONTAINS:
        return expected in observed  # type: ignore[operator]
    if operator == PredicateOperator.STARTS_WITH:
        return str(observed).startswith(str(expected))
    if operator == PredicateOperator.ENDS_WITH:
        return str(observed).endswith(str(expected))
    if operator == PredicateOperator.BETWEEN:
        if not isinstance(expected, tuple) or len(expected) != 2:
            raise ValueError("between requires a two-value literal")
        return expected[0] <= observed <= expected[1]  # type: ignore[operator]
    raise ValueError("operator has no mechanical implementation")


def _material_value_conflict(evidence: tuple[PredicateEvidence, ...]) -> bool:
    values = {repr(item.observed_value) for item in evidence}
    return len(values) > 1


def _evaluation(
    predicate: PredicateExpr,
    status: CriterionStatus,
    evidence: tuple[PredicateEvidence, ...],
    reason: str,
) -> CriterionEvaluation:
    return CriterionEvaluation(
        predicate.criterion_id,
        status,
        observed_value=tuple(item.observed_value for item in evidence),
        evidence_refs=tuple(dict.fromkeys(item.evidence_ref for item in evidence)),
        evaluated_at_observation_ref=(evidence[0].observation_ref if evidence else ""),
        reason_code=reason,
        authoritative_final_recheck=any(item.authoritative_final_recheck for item in evidence),
    )


def _composite(
    criterion_id: str,
    status: CriterionStatus,
    children: tuple[CriterionEvaluation, ...],
    operator: str,
) -> CriterionEvaluation:
    return CriterionEvaluation(
        criterion_id,
        status,
        observed_value=tuple((item.criterion_id, item.status.value) for item in children),
        evidence_refs=tuple(dict.fromkeys(ref for item in children for ref in item.evidence_refs)),
        reason_code=f"composite_{operator}",
    )


def _all_status(statuses: tuple[CriterionStatus, ...]) -> CriterionStatus:
    if CriterionStatus.UNSATISFIED in statuses:
        return CriterionStatus.UNSATISFIED
    if all(item == CriterionStatus.SATISFIED for item in statuses):
        return CriterionStatus.SATISFIED
    return _inconclusive(statuses)


def _any_status(statuses: tuple[CriterionStatus, ...]) -> CriterionStatus:
    if CriterionStatus.SATISFIED in statuses:
        return CriterionStatus.SATISFIED
    if all(item == CriterionStatus.UNSATISFIED for item in statuses):
        return CriterionStatus.UNSATISFIED
    return _inconclusive(statuses)


def _inconclusive(statuses: tuple[CriterionStatus, ...]) -> CriterionStatus:
    for status in (
        CriterionStatus.CONFLICT,
        CriterionStatus.ERROR,
        CriterionStatus.STALE,
        CriterionStatus.UNSUPPORTED,
        CriterionStatus.UNKNOWN,
    ):
        if status in statuses:
            return status
    return CriterionStatus.UNKNOWN


def _providers() -> tuple[EvidenceProvider, ...]:
    from affordance_runtime.verification.providers import MECHANICAL_EVIDENCE_PROVIDERS

    return MECHANICAL_EVIDENCE_PROVIDERS
