"""One-way admission from current provider reports into typed criterion results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from affordance_runtime.contracts import Observation
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionEvaluation,
    CriterionPolicy,
    CriterionStatus,
    EvidenceSourceKind,
    PredicateEvidence,
    PredicateEvidenceContext,
    SuccessExpression,
    criterion_policy_digest,
)
from affordance_runtime.verification.mechanical import VerificationReport
from affordance_runtime.verification.predicates import evidence_admitted_by_policy


def admit_completion_evidence(
    *,
    task_spec: TaskSpec,
    observation: Observation,
    evidence_context: PredicateEvidenceContext,
    report: VerificationReport | None = None,
) -> tuple[CriterionEvaluation, ...]:
    admitted: dict[str, CriterionEvaluation] = {}
    policies = _success_policies(task_spec.success)
    if evidence_context.current_observation_ref != observation.snapshot_id:
        raise ValueError("completion evidence context must match the current observation")
    context = evidence_context
    declared = observation.metadata.get("criterion_evaluations")
    if isinstance(declared, Mapping):
        for criterion_id, raw_status in declared.items():
            criterion_id = str(criterion_id)
            provider = "current_observation_provider"
            evidence_refs: tuple[str, ...] = ()
            authoritative_final_recheck = False
            if isinstance(raw_status, Mapping):
                provider = str(raw_status.get("provider") or provider)
                evidence_refs = tuple(str(item) for item in raw_status.get("evidence_refs", ()) if str(item))
                authoritative_final_recheck = provider in {
                    "external_evaluator",
                    "independent_http_json",
                    "api_state",
                }
                status_value = raw_status.get("status", CriterionStatus.ERROR.value)
            else:
                status_value = raw_status
            try:
                status = CriterionStatus(str(status_value))
            except ValueError:
                status = CriterionStatus.ERROR
            policy = policies.get(criterion_id)
            policy_digest = ""
            if policy is not None:
                evidence = _declared_policy_evidence(criterion_id, raw_status, observation)
                candidates = (
                    *((evidence,) if evidence is not None else ()),
                    *(item for item in context.evidence if criterion_id in item.effect_criterion_ids),
                )
                if not any(
                    evidence_admitted_by_policy(item, policy, context, criterion_id=criterion_id) for item in candidates
                ):
                    status = CriterionStatus.UNKNOWN
                    provider = "success_evidence_rejected_by_policy"
                    evidence_refs = ()
                    authoritative_final_recheck = False
                policy_digest = criterion_policy_digest(criterion_id, policy)
            admitted[criterion_id] = CriterionEvaluation(
                criterion_id,
                status,
                evidence_refs=evidence_refs,
                evaluated_at_observation_ref=observation.snapshot_id,
                reason_code=provider,
                authoritative_final_recheck=authoritative_final_recheck,
                policy_digest=policy_digest,
            )

    if report is None:
        return _admit_context_only_success(policies, context, admitted)
    by_criterion: dict[str, list[Any]] = {}
    for evidence in report.evidence:
        for criterion_id in evidence.criterion_ids:
            by_criterion.setdefault(criterion_id, []).append(evidence)
    for criterion_id, evidence_items in by_criterion.items():
        current = tuple(
            item
            for item in evidence_items
            if item.snapshot_id == observation.snapshot_id
            and item.environment_revision == observation.environment_revision
        )
        if not current:
            admitted[criterion_id] = CriterionEvaluation(
                criterion_id,
                CriterionStatus.STALE,
                reason_code="evidence_not_from_current_observation",
            )
            continue
        strong = tuple(
            item
            for item in current
            if item.strength in {"strong", "authoritative"} and item.source not in {"receipt", "execution_receipt"}
        )
        if not strong:
            admitted[criterion_id] = CriterionEvaluation(
                criterion_id,
                CriterionStatus.UNKNOWN,
                evidence_refs=tuple(item.evidence_id for item in current if item.evidence_id),
                evaluated_at_observation_ref=observation.snapshot_id,
                reason_code="no_independent_strong_evidence",
            )
            continue
        passed = {item.passed for item in strong}
        status = (
            CriterionStatus.CONFLICT
            if len(passed) > 1
            else CriterionStatus.SATISFIED
            if True in passed
            else CriterionStatus.UNSATISFIED
        )
        policy = policies.get(criterion_id)
        policy_digest = ""
        if policy is not None:
            policy_evidence = tuple(
                item
                for item in (
                    _report_policy_evidence(criterion_id, evidence, observation, context) for evidence in strong
                )
                if item is not None
            )
            if not any(
                evidence_admitted_by_policy(item, policy, context, criterion_id=criterion_id)
                for item in (*policy_evidence, *context.evidence)
                if not item.effect_criterion_ids or criterion_id in item.effect_criterion_ids
            ):
                status = CriterionStatus.UNKNOWN
            policy_digest = criterion_policy_digest(criterion_id, policy)
        admitted[criterion_id] = CriterionEvaluation(
            criterion_id,
            status,
            observed_value=tuple(item.observed for item in strong),
            evidence_refs=tuple(item.evidence_id for item in strong if item.evidence_id),
            evaluated_at_observation_ref=observation.snapshot_id,
            reason_code="independent_typed_evidence",
            authoritative_final_recheck=any(
                item.source in {"external_evaluator", "independent_http_json", "api_state"}
                and item.strength == "authoritative"
                for item in strong
            ),
            policy_digest=policy_digest,
        )
    return _admit_context_only_success(policies, context, admitted)


def _admit_context_only_success(
    policies: Mapping[str, CriterionPolicy],
    context: PredicateEvidenceContext,
    admitted: dict[str, CriterionEvaluation],
) -> tuple[CriterionEvaluation, ...]:
    for criterion_id, policy in policies.items():
        if criterion_id in admitted:
            continue
        candidates = tuple(item for item in context.evidence if criterion_id in item.effect_criterion_ids)
        accepted = tuple(
            item for item in candidates if evidence_admitted_by_policy(item, policy, context, criterion_id=criterion_id)
        )
        if not accepted:
            continue
        statuses: set[CriterionStatus] = set()
        for item in accepted:
            try:
                statuses.add(CriterionStatus(str(item.observed_value)))
            except ValueError:
                statuses.add(CriterionStatus.SATISFIED)
        status = statuses.pop() if len(statuses) == 1 else CriterionStatus.CONFLICT
        admitted[criterion_id] = CriterionEvaluation(
            criterion_id,
            status,
            evidence_refs=tuple(item.evidence_ref for item in accepted),
            evaluated_at_observation_ref=context.current_observation_ref,
            reason_code="runtime_evidence_context",
            authoritative_final_recheck=policy.validity.value == "final_recheck",
            policy_digest=criterion_policy_digest(criterion_id, policy),
        )
    return tuple(admitted.values())


def _success_policies(expression: SuccessExpression) -> dict[str, CriterionPolicy]:
    if expression.operator == "criterion":
        assert expression.policy is not None
        return {expression.criterion_id: expression.policy}
    policies: dict[str, CriterionPolicy] = {}
    for child in expression.children:
        policies.update(_success_policies(child))
    return policies


def _declared_policy_evidence(
    criterion_id: str,
    raw: object,
    observation: Observation,
) -> PredicateEvidence | None:
    if not isinstance(raw, Mapping):
        return None
    provider = str(raw.get("provider") or "current_observation_provider")
    inferred_source = {
        "current_observation_provider": EvidenceSourceKind.DOM_STATE,
        "external_evaluator": EvidenceSourceKind.API_STATE,
        "independent_http_json": EvidenceSourceKind.API_STATE,
        "api_state": EvidenceSourceKind.API_STATE,
    }.get(provider)
    inferred_assurance = (
        AssuranceLevel.AUTHORITATIVE if inferred_source == EvidenceSourceKind.API_STATE else AssuranceLevel.STRUCTURAL
    )
    try:
        return PredicateEvidence(
            evidence_ref=str(next(iter(raw.get("evidence_refs", ())), "")),
            subject_ref=str(raw.get("subject_ref") or criterion_id),
            observed_value=raw.get("status"),
            source_kind=EvidenceSourceKind(str(raw.get("source_kind") or inferred_source or "")),
            assurance=AssuranceLevel(str(raw.get("assurance") or inferred_assurance)),
            observation_ref=str(raw.get("observation_ref") or observation.snapshot_id),
            contract_id=str(raw.get("contract_id") or ""),
            receipt_ref=str(raw.get("receipt_ref") or ""),
            pre_observation_ref=str(raw.get("pre_observation_ref") or ""),
            post_observation_ref=str(raw.get("post_observation_ref") or ""),
            effect_criterion_ids=tuple(str(item) for item in raw.get("effect_criterion_ids", (criterion_id,))),
            durable=bool(raw.get("durable", False)),
            authoritative_final_recheck=bool(raw.get("authoritative_final_recheck", False)),
            final_recheck_ref=str(raw.get("final_recheck_ref") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _report_policy_evidence(
    criterion_id: str,
    evidence: object,
    observation: Observation,
    context: PredicateEvidenceContext,
) -> PredicateEvidence | None:
    source = str(getattr(evidence, "source", ""))
    source_kind = {
        "external_evaluator": EvidenceSourceKind.API_STATE,
        "independent_http_json": EvidenceSourceKind.API_STATE,
        "api_state": EvidenceSourceKind.API_STATE,
        "post_action_observation": EvidenceSourceKind.DOM_STATE,
        "dom": EvidenceSourceKind.DOM_STATE,
        "accessibility": EvidenceSourceKind.ACCESSIBILITY_STATE,
        "visual": EvidenceSourceKind.VISUAL_STATE,
    }.get(source)
    if source_kind is None:
        return None
    strength = str(getattr(evidence, "strength", "weak"))
    assurance = {
        "weak": AssuranceLevel.WEAK,
        "strong": AssuranceLevel.STRUCTURAL,
        "authoritative": AssuranceLevel.AUTHORITATIVE,
    }.get(strength, AssuranceLevel.WEAK)
    return PredicateEvidence(
        evidence_ref=str(getattr(evidence, "evidence_id", "")),
        subject_ref=str(getattr(evidence, "target", "") or criterion_id),
        observed_value=getattr(evidence, "observed", None),
        source_kind=source_kind,
        assurance=assurance,
        observation_ref=observation.snapshot_id,
        authoritative_final_recheck=(
            source_kind == EvidenceSourceKind.API_STATE and assurance == AssuranceLevel.AUTHORITATIVE
        ),
        final_recheck_ref=context.latest_final_recheck_ref,
        resource_version=dict(context.current_resource_versions).get(
            str(getattr(evidence, "target", "") or criterion_id), ""
        ),
        runtime_final_recheck=(
            source_kind == EvidenceSourceKind.API_STATE and assurance == AssuranceLevel.AUTHORITATIVE
        ),
    )


def output_source_bindings(observation: Observation) -> dict[str, tuple[str, ...]]:
    raw = observation.metadata.get("output_source_bindings")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(output_id): tuple(str(item) for item in refs if str(item))
        for output_id, refs in raw.items()
        if isinstance(refs, (tuple, list))
    }
