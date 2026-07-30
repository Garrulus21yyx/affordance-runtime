"""Typed contracts for post-verification obligation progress attribution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, cast

from affordance_runtime.obligation_progress import (
    PROGRESS_ROLES,
    ObligationProgressStateView,
    ReadyObligationProjection,
    ReadyObligationView,
    validate_obligation_progress_state,
)
from affordance_runtime.semantics import EvidenceSourceKind, EvidenceStrength
from affordance_runtime.task_intake import (
    TaskObligationRelation,
    TaskObligationSpec,
    TaskSpec,
)

FrozenEvidenceValue = str | bool | int | float | None


@dataclass(frozen=True)
class CurrentObservationSatisfactionSource:
    snapshot_id: str
    page_revision: str
    environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)


@dataclass(frozen=True)
class PostVerificationSatisfactionSource:
    contract_id: str
    post_snapshot_id: str
    post_page_revision: str
    post_environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("post_snapshot_id", self.post_snapshot_id)
        _require_nonblank("post_page_revision", self.post_page_revision)
        _require_nonblank("post_environment_revision", self.post_environment_revision)


@dataclass(frozen=True)
class PostVerificationContext:
    """Causal identity for one post-action verification pass."""

    contract_id: str
    contract_hash: str
    pre_snapshot_id: str
    post_snapshot_id: str
    post_page_revision: str
    post_environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("post_snapshot_id", self.post_snapshot_id)
        _require_nonblank("post_page_revision", self.post_page_revision)
        _require_nonblank("post_environment_revision", self.post_environment_revision)


@dataclass(frozen=True)
class AttributionTargetView:
    """Runtime-grounded target binding for attribution candidate matching."""

    semantic_target_id: str
    canonical_subject_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        if not self.canonical_subject_ids:
            raise ValueError("canonical subject ids cannot be empty")
        _require_unique_nonblank("canonical subject ids", self.canonical_subject_ids)


@dataclass(frozen=True)
class AttributionActionView:
    """Authority-free accepted-action identity for pre-action ticketing."""

    contract_id: str
    contract_hash: str
    task_spec_identity: str
    task_revision: int
    issued_at_state_version: int
    target: AttributionTargetView
    action_kind: str
    pre_snapshot_id: str
    pre_page_revision: str
    pre_environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.issued_at_state_version < 0:
            raise ValueError("issued state version cannot be negative")
        _require_nonblank("action_kind", self.action_kind)
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("pre_page_revision", self.pre_page_revision)
        _require_nonblank("pre_environment_revision", self.pre_environment_revision)


@dataclass(frozen=True)
class ProgressAttributionTicket:
    """Pre-action candidate scope for later verifier-owned attribution."""

    ticket_id: str
    task_spec_identity: str
    task_revision: int
    issued_at_state_version: int
    contract_id: str
    contract_hash: str
    semantic_target_id: str
    action_kind: str
    candidate_obligation_ids: tuple[str, ...]
    pre_snapshot_id: str
    pre_page_revision: str
    pre_environment_revision: str
    compatibility_plan_id: str = ""
    compatibility_plan_version: int = 0

    def __post_init__(self) -> None:
        _require_nonblank("ticket_id", self.ticket_id)
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.issued_at_state_version < 0:
            raise ValueError("issued state version cannot be negative")
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        _require_nonblank("action_kind", self.action_kind)
        if not self.candidate_obligation_ids:
            raise ValueError("candidate obligation ids cannot be empty")
        _require_unique_nonblank(
            "candidate obligation ids",
            self.candidate_obligation_ids,
        )
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("pre_page_revision", self.pre_page_revision)
        _require_nonblank("pre_environment_revision", self.pre_environment_revision)
        if self.compatibility_plan_version < 0:
            raise ValueError("compatibility plan version cannot be negative")


@dataclass(frozen=True)
class ProgressAttributionTicketResolution:
    status: Literal[
        "ticket_created",
        "no_candidate",
        "role_pending",
        "stale",
        "invalid",
    ]
    ticket: ProgressAttributionTicket | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == "ticket_created" and self.ticket is None:
            raise ValueError("ticket_created resolution requires ticket")
        if self.status != "ticket_created" and self.ticket is not None:
            raise ValueError("non-ticket resolution cannot include ticket")


class ProgressAttributionTicketResolver:
    """Resolve candidate obligation scope before an action is executed."""

    def resolve(
        self,
        *,
        task_spec: TaskSpec,
        progress: ObligationProgressStateView,
        ready_projection: ReadyObligationProjection,
        action: AttributionActionView,
    ) -> ProgressAttributionTicketResolution:
        if ready_projection.status == "role_pending":
            return ProgressAttributionTicketResolution(
                status="role_pending",
                reason=ready_projection.reason,
            )
        if ready_projection.status == "stale_progress":
            return ProgressAttributionTicketResolution(
                status="stale",
                reason=ready_projection.reason,
            )
        if ready_projection.status == "invalid_progress":
            return ProgressAttributionTicketResolution(
                status="invalid",
                reason=ready_projection.reason,
            )
        if ready_projection.status != "ready":
            return ProgressAttributionTicketResolution(status="invalid")
        if (
            action.task_spec_identity != task_spec.identity
            or action.task_revision != task_spec.revision
            or action.issued_at_state_version != progress.evaluated_at_state_version
        ):
            return ProgressAttributionTicketResolution(status="stale")
        progress_validation = _validate_progress_for_ticket(
            task_spec=task_spec,
            progress=progress,
        )
        if progress_validation is not None:
            return progress_validation

        canonical_by_id = {item.obligation_id: item for item in task_spec.obligations}
        satisfied = set(progress.satisfied_obligation_ids)
        failed = set(progress.failed_obligation_ids)
        candidate_ids: list[str] = []
        for view in ready_projection.ready_obligations:
            obligation = canonical_by_id.get(view.obligation_id)
            if obligation is None:
                return ProgressAttributionTicketResolution(
                    status="invalid",
                    reason=f"unknown ready obligation: {view.obligation_id}",
                )
            if not _ready_view_matches_obligation(view=view, obligation=obligation):
                return ProgressAttributionTicketResolution(
                    status="invalid",
                    reason=f"ready view drifted from canonical obligation: {view.obligation_id}",
                )
            if view.role not in PROGRESS_ROLES:
                continue
            if view.obligation_id in satisfied or view.obligation_id in failed:
                continue
            if not set(view.dependency_ids).issubset(satisfied):
                continue
            if view.subject not in action.target.canonical_subject_ids:
                continue
            if not _action_relation_compatible(action.action_kind, view.relation):
                continue
            candidate_ids.append(view.obligation_id)

        if not candidate_ids:
            return ProgressAttributionTicketResolution(status="no_candidate")
        candidates = tuple(candidate_ids)
        return ProgressAttributionTicketResolution(
            status="ticket_created",
            ticket=ProgressAttributionTicket(
                ticket_id=_ticket_id(action=action, candidate_obligation_ids=candidates),
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                issued_at_state_version=action.issued_at_state_version,
                contract_id=action.contract_id,
                contract_hash=action.contract_hash,
                semantic_target_id=action.target.semantic_target_id,
                action_kind=action.action_kind,
                candidate_obligation_ids=candidates,
                pre_snapshot_id=action.pre_snapshot_id,
                pre_page_revision=action.pre_page_revision,
                pre_environment_revision=action.pre_environment_revision,
            ),
        )


@dataclass(frozen=True)
class PostActionEvidenceFact:
    """Verifier/observation fact that deliberately carries no obligation id."""

    contract_id: str
    contract_hash: str
    pre_snapshot_id: str
    post_snapshot_id: str
    post_page_revision: str
    post_environment_revision: str
    action_semantic_target_id: str
    evidence_subject_id: str
    relation: TaskObligationRelation
    before_value: FrozenEvidenceValue
    after_value: FrozenEvidenceValue
    expected_value: FrozenEvidenceValue
    verifier_kind: str
    source_kind: EvidenceSourceKind
    strength: EvidenceStrength
    passed: bool
    evidence_refs: tuple[str, ...]
    criterion_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("post_snapshot_id", self.post_snapshot_id)
        _require_nonblank("post_page_revision", self.post_page_revision)
        _require_nonblank("post_environment_revision", self.post_environment_revision)
        _require_nonblank("action_semantic_target_id", self.action_semantic_target_id)
        _require_nonblank("evidence_subject_id", self.evidence_subject_id)
        _require_nonblank("verifier_kind", self.verifier_kind)
        _require_unique_nonblank("evidence refs", self.evidence_refs)
        _require_unique_nonblank("criterion ids", self.criterion_ids)
        _require_unique_nonblank("requirement ids", self.requirement_ids)


@dataclass(frozen=True)
class VerificationEvidenceView:
    """Immutable ODG-facing projection of verifier evidence."""

    verifier_kind: str
    target: str
    passed: bool
    source: str
    observed: FrozenEvidenceValue
    expected: FrozenEvidenceValue
    evidence_id: str
    semantic_evidence_key: str
    criterion_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    snapshot_id: str
    environment_revision: str
    observed_at_s: float
    reported_strength: str

    def __post_init__(self) -> None:
        _require_nonblank("verifier_kind", self.verifier_kind)
        _require_nonblank("target", self.target)
        _require_nonblank("source", self.source)
        object.__setattr__(
            self,
            "observed",
            _frozen_evidence_value("observed", self.observed),
        )
        object.__setattr__(
            self,
            "expected",
            _frozen_evidence_value("expected", self.expected),
        )
        _require_nonblank("evidence_id", self.evidence_id)
        _require_nonblank("semantic_evidence_key", self.semantic_evidence_key)
        object.__setattr__(self, "criterion_ids", tuple(self.criterion_ids))
        object.__setattr__(self, "requirement_ids", tuple(self.requirement_ids))
        _require_unique_nonblank("criterion ids", self.criterion_ids)
        _require_unique_nonblank("requirement ids", self.requirement_ids)
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("environment_revision", self.environment_revision)
        if self.observed_at_s < 0:
            raise ValueError("observed_at_s cannot be negative")
        _require_nonblank("reported_strength", self.reported_strength)


@dataclass(frozen=True)
class VerificationReportView:
    """Immutable ODG-facing projection of a verification report."""

    status: str
    evidence: tuple[VerificationEvidenceView, ...]
    reason: str = ""

    def __post_init__(self) -> None:
        _require_nonblank("verification report status", self.status)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for evidence in self.evidence:
            _require_nonblank("verification evidence id", evidence.evidence_id)


@dataclass(frozen=True)
class VerifierSemanticEvidenceDeclaration:
    """Runtime-owned semantic meaning for one verifier evidence item."""

    semantic_evidence_key: str
    evidence_subject_id: str
    relation: TaskObligationRelation
    before_value: FrozenEvidenceValue
    expected_value: FrozenEvidenceValue
    minimum_strength: EvidenceStrength
    allowed_source_kinds: tuple[EvidenceSourceKind, ...]

    def __post_init__(self) -> None:
        _require_nonblank("semantic evidence key", self.semantic_evidence_key)
        _require_nonblank("evidence subject id", self.evidence_subject_id)
        object.__setattr__(
            self,
            "before_value",
            _frozen_evidence_value("before", self.before_value),
        )
        object.__setattr__(
            self,
            "expected_value",
            _frozen_evidence_value("expected", self.expected_value),
        )
        if not self.allowed_source_kinds:
            raise ValueError("allowed source kinds cannot be empty")
        if len(self.allowed_source_kinds) != len(set(self.allowed_source_kinds)):
            raise ValueError("allowed source kinds must be unique")


@dataclass(frozen=True)
class PostActionEvidenceNormalizationResult:
    status: Literal[
        "normalized",
        "no_eligible_evidence",
        "report_not_passed",
        "stale",
        "invalid",
        "unsupported_observed_shape",
    ]
    facts: tuple[PostActionEvidenceFact, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == "normalized" and not self.facts:
            raise ValueError("normalized result requires facts")
        if self.status != "normalized" and self.facts:
            raise ValueError("non-normalized result cannot include facts")


class PostActionEvidenceNormalizer:
    """Normalize verifier evidence into identity-bound post-action facts."""

    def normalize(
        self,
        *,
        ticket: ProgressAttributionTicket,
        report: VerificationReportView,
        declarations: tuple[VerifierSemanticEvidenceDeclaration, ...],
        context: PostVerificationContext,
    ) -> PostActionEvidenceNormalizationResult:
        if (
            context.contract_id != ticket.contract_id
            or context.contract_hash != ticket.contract_hash
            or context.pre_snapshot_id != ticket.pre_snapshot_id
        ):
            return PostActionEvidenceNormalizationResult(
                status="stale",
                reason="post-verification context does not match ticket",
            )
        if report.status != "passed":
            return PostActionEvidenceNormalizationResult(status="report_not_passed")
        declarations_by_key = {item.semantic_evidence_key: item for item in declarations}
        if not declarations or len(declarations_by_key) != len(declarations):
            return PostActionEvidenceNormalizationResult(
                status="invalid",
                reason="semantic evidence declarations must be unique and non-empty",
            )
        evidence_by_id = {item.evidence_id: item for item in report.evidence}
        if len(evidence_by_id) != len(report.evidence):
            return PostActionEvidenceNormalizationResult(
                status="invalid",
                reason="verification evidence ids must be unique",
            )

        facts: list[PostActionEvidenceFact] = []
        unsupported_shape = False
        for evidence in report.evidence:
            declaration = declarations_by_key.get(evidence.semantic_evidence_key)
            if declaration is None:
                continue
            if not evidence.passed:
                continue
            if (
                evidence.snapshot_id != context.post_snapshot_id
                or evidence.environment_revision != context.post_environment_revision
            ):
                return PostActionEvidenceNormalizationResult(status="stale")
            source = _source_kind_and_strength(evidence.source)
            if source is None:
                continue
            reported_strength = _reported_strength(evidence.reported_strength)
            if reported_strength is None:
                return PostActionEvidenceNormalizationResult(
                    status="invalid",
                    reason=f"unknown reported evidence strength: {evidence.reported_strength}",
                )
            source_kind, source_strength = source
            strength = _minimum_strength(source_strength, reported_strength)
            if source_kind not in declaration.allowed_source_kinds:
                continue
            if _strength_rank(strength) < _strength_rank(declaration.minimum_strength):
                continue
            if declaration.expected_value != evidence.expected:
                return PostActionEvidenceNormalizationResult(
                    status="invalid",
                    reason="semantic declaration expected value does not match evidence",
                )
            if not _evidence_shape_supported(
                relation=declaration.relation,
                before_value=declaration.before_value,
                after_value=evidence.observed,
            ):
                unsupported_shape = True
                continue
            facts.append(
                PostActionEvidenceFact(
                    contract_id=ticket.contract_id,
                    contract_hash=ticket.contract_hash,
                    pre_snapshot_id=ticket.pre_snapshot_id,
                    post_snapshot_id=context.post_snapshot_id,
                    post_page_revision=context.post_page_revision,
                    post_environment_revision=context.post_environment_revision,
                    action_semantic_target_id=ticket.semantic_target_id,
                    evidence_subject_id=declaration.evidence_subject_id,
                    relation=declaration.relation,
                    before_value=declaration.before_value,
                    after_value=evidence.observed,
                    expected_value=declaration.expected_value,
                    verifier_kind=evidence.verifier_kind,
                    source_kind=source_kind,
                    strength=strength,
                    passed=evidence.passed,
                    evidence_refs=(evidence.evidence_id,),
                    criterion_ids=evidence.criterion_ids,
                    requirement_ids=evidence.requirement_ids,
                )
            )
        if facts:
            return PostActionEvidenceNormalizationResult(
                status="normalized",
                facts=tuple(facts),
            )
        if unsupported_shape:
            return PostActionEvidenceNormalizationResult(status="unsupported_observed_shape")
        return PostActionEvidenceNormalizationResult(status="no_eligible_evidence")


@dataclass(frozen=True)
class ObligationAttributionResult:
    status: Literal[
        "satisfied",
        "no_match",
        "ambiguous",
        "weak_evidence",
        "stale",
        "invalid",
        "dependency_blocked",
    ]
    preparation: "ObligationSatisfactionPreparation | None" = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == "satisfied" and self.preparation is None:
            raise ValueError("satisfied attribution requires preparation")
        if self.status != "satisfied" and self.preparation is not None:
            raise ValueError("non-satisfied attribution cannot include preparation")


class PostVerificationObligationAttributor:
    """Attribute post-action facts to exactly one candidate obligation."""

    def attribute(
        self,
        *,
        task_spec: TaskSpec,
        progress: ObligationProgressStateView,
        ticket: ProgressAttributionTicket,
        facts: tuple[PostActionEvidenceFact, ...],
    ) -> ObligationAttributionResult:
        identity_error = _validate_attribution_identity(
            task_spec=task_spec,
            progress=progress,
            ticket=ticket,
            facts=facts,
        )
        if identity_error is not None:
            return identity_error
        progress_validation = _validate_progress_for_ticket(
            task_spec=task_spec,
            progress=progress,
        )
        if progress_validation is not None:
            return ObligationAttributionResult(
                status="stale"
                if progress_validation.status == "stale"
                else "no_match",
                reason=progress_validation.reason,
            )

        obligations_by_id = {item.obligation_id: item for item in task_spec.obligations}
        satisfied_ids = set(progress.satisfied_obligation_ids)
        failed_ids = set(progress.failed_obligation_ids)
        eligible: list[TaskObligationSpec] = []
        dependency_blocked = False
        for candidate_id in ticket.candidate_obligation_ids:
            obligation = obligations_by_id[candidate_id]
            if candidate_id in satisfied_ids or candidate_id in failed_ids:
                continue
            if not set(obligation.depends_on).issubset(satisfied_ids):
                dependency_blocked = True
                continue
            eligible.append(obligation)
        if not eligible:
            return ObligationAttributionResult(
                status="dependency_blocked" if dependency_blocked else "no_match",
            )

        strong_matches: list[tuple[TaskObligationSpec, tuple[str, ...]]] = []
        weak_match_seen = False
        for obligation in eligible:
            proof = _prove_obligation_with_facts(obligation=obligation, facts=facts)
            if proof.status == "strong":
                strong_matches.append((obligation, proof.evidence_refs))
            elif proof.status == "weak":
                weak_match_seen = True

        if len(strong_matches) > 1:
            return ObligationAttributionResult(status="ambiguous")
        if not strong_matches:
            return ObligationAttributionResult(
                status="weak_evidence" if weak_match_seen else "no_match",
            )

        obligation, evidence_refs = strong_matches[0]
        post_snapshot_id, post_page_revision, post_environment_revision = _single_post_identity(
            facts
        )
        return ObligationAttributionResult(
            status="satisfied",
            preparation=ObligationSatisfactionPreparation(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                evaluated_at_state_version=progress.evaluated_at_state_version,
                obligation_id=obligation.obligation_id,
                evidence_refs=evidence_refs,
                source=PostVerificationSatisfactionSource(
                    contract_id=ticket.contract_id,
                    post_snapshot_id=post_snapshot_id,
                    post_page_revision=post_page_revision,
                    post_environment_revision=post_environment_revision,
                ),
            ),
        )


@dataclass(frozen=True)
class ObligationSatisfactionPreparation:
    """Coordinator-owned command payload for committing obligation progress."""

    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    obligation_id: str
    evidence_refs: tuple[str, ...]
    source: CurrentObservationSatisfactionSource | PostVerificationSatisfactionSource

    def __post_init__(self) -> None:
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        _require_nonblank("obligation_id", self.obligation_id)
        if not self.evidence_refs:
            raise ValueError("satisfaction evidence refs cannot be empty")
        _require_unique_nonblank("satisfaction evidence refs", self.evidence_refs)


def _require_nonblank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_unique_nonblank(field_name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")
    if any(not item.strip() for item in values):
        raise ValueError(f"{field_name} cannot contain blank values")


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


@dataclass(frozen=True)
class _ObligationProof:
    status: Literal["none", "weak", "strong"]
    evidence_refs: tuple[str, ...] = ()


def _validate_attribution_identity(
    *,
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    ticket: ProgressAttributionTicket,
    facts: tuple[PostActionEvidenceFact, ...],
) -> ObligationAttributionResult | None:
    if (
        ticket.task_spec_identity != task_spec.identity
        or ticket.task_revision != task_spec.revision
        or progress.task_spec_identity != task_spec.identity
        or progress.task_revision != task_spec.revision
    ):
        return ObligationAttributionResult(status="stale")
    if not facts:
        return ObligationAttributionResult(status="no_match")
    if len({ref for fact in facts for ref in fact.evidence_refs}) != sum(
        len(fact.evidence_refs) for fact in facts
    ):
        return ObligationAttributionResult(
            status="no_match",
            reason="duplicate evidence ref",
        )
    for fact in facts:
        if (
            fact.contract_id != ticket.contract_id
            or fact.contract_hash != ticket.contract_hash
            or fact.pre_snapshot_id != ticket.pre_snapshot_id
        ):
            return ObligationAttributionResult(status="stale")
    post_identities = {
        (
            fact.post_snapshot_id,
            fact.post_page_revision,
            fact.post_environment_revision,
        )
        for fact in facts
    }
    if len(post_identities) != 1:
        return ObligationAttributionResult(
            status="stale",
            reason="mixed post-verification identities",
        )
    known_ids = {item.obligation_id for item in task_spec.obligations}
    if any(candidate not in known_ids for candidate in ticket.candidate_obligation_ids):
        return ObligationAttributionResult(status="invalid")
    return None


def _single_post_identity(
    facts: tuple[PostActionEvidenceFact, ...],
) -> tuple[str, str, str]:
    fact = facts[0]
    return (
        fact.post_snapshot_id,
        fact.post_page_revision,
        fact.post_environment_revision,
    )


def _prove_obligation_with_facts(
    *,
    obligation: TaskObligationSpec,
    facts: tuple[PostActionEvidenceFact, ...],
) -> _ObligationProof:
    if not obligation.typed_evidence_requirements:
        return _ObligationProof(status="none")
    covered_refs: list[str] = []
    weak_candidate = False
    for requirement in obligation.typed_evidence_requirements:
        proof = _cover_evidence_requirement(obligation=obligation, requirement=requirement, facts=facts)
        if proof.status == "none":
            return _ObligationProof(status="weak" if weak_candidate else "none")
        if proof.status == "weak":
            weak_candidate = True
        covered_refs.extend(proof.evidence_refs)
    if weak_candidate:
        return _ObligationProof(status="weak")
    return _ObligationProof(status="strong", evidence_refs=_dedupe(tuple(covered_refs)))


def _cover_evidence_requirement(
    *,
    obligation: TaskObligationSpec,
    requirement: object,
    facts: tuple[PostActionEvidenceFact, ...],
) -> _ObligationProof:
    subject = getattr(requirement, "subject", obligation.subject)
    relation = getattr(requirement, "relation", obligation.relation)
    minimum_strength = _required_strength(getattr(requirement, "minimum_strength", "independent"))
    allowed_sources = _allowed_source_kinds(getattr(requirement, "source_constraints", ()))
    matching_facts = tuple(
        fact
        for fact in facts
        if fact.evidence_subject_id == subject
        and fact.relation == relation
        and _fact_proves_relation(fact=fact, obligation=obligation, relation=relation)
    )
    if not matching_facts:
        return _ObligationProof(status="none")
    strong = tuple(
        fact
        for fact in matching_facts
        if (not allowed_sources or fact.source_kind in allowed_sources)
        and _strength_rank(fact.strength) >= _strength_rank(minimum_strength)
        and fact.strength != EvidenceStrength.WEAK
    )
    source_mismatched_or_weak = tuple(
        fact
        for fact in matching_facts
        if _strength_rank(fact.strength) >= _strength_rank(minimum_strength)
        or fact.strength == EvidenceStrength.WEAK
        or (allowed_sources and fact.source_kind not in allowed_sources)
    )
    if not strong:
        return _ObligationProof(status="weak" if source_mismatched_or_weak else "none")
    return _ObligationProof(
        status="strong",
        evidence_refs=_dedupe(
            tuple(ref for fact in strong for ref in fact.evidence_refs)
        ),
    )


def _required_strength(value: str) -> EvidenceStrength:
    normalized = value.casefold()
    if normalized == EvidenceStrength.WEAK.value:
        return EvidenceStrength.WEAK
    if normalized == EvidenceStrength.AUTHORITATIVE.value:
        return EvidenceStrength.AUTHORITATIVE
    return EvidenceStrength.INDEPENDENT


def _allowed_source_kinds(source_constraints: tuple[str, ...]) -> frozenset[EvidenceSourceKind]:
    result: set[EvidenceSourceKind] = set()
    for constraint in source_constraints:
        normalized = constraint.casefold()
        if "independent_api" in normalized or "http" in normalized or "api" in normalized:
            result.add(EvidenceSourceKind.INDEPENDENT_API)
        elif "execution_receipt" in normalized or "receipt" in normalized:
            result.add(EvidenceSourceKind.EXECUTION_RECEIPT)
        elif "external_evaluator" in normalized or "reward" in normalized:
            result.add(EvidenceSourceKind.EXTERNAL_EVALUATOR)
        elif "post_action_observation" in normalized or "dom" in normalized or "source:" in normalized:
            result.add(EvidenceSourceKind.POST_ACTION_OBSERVATION)
    return frozenset(result)


def _fact_proves_relation(
    *,
    fact: PostActionEvidenceFact,
    obligation: TaskObligationSpec,
    relation: TaskObligationRelation,
) -> bool:
    expected = _expected_value_for_proof(obligation)
    if relation == TaskObligationRelation.EQUALS:
        return fact.after_value == expected and fact.expected_value == expected
    if relation == TaskObligationRelation.CONTAINS:
        return (
            isinstance(fact.after_value, str)
            and str(expected) in fact.after_value
            and fact.expected_value == expected
        )
    if relation == TaskObligationRelation.MATCHES:
        return fact.after_value == expected and fact.expected_value == expected
    if relation == TaskObligationRelation.HAS_CHANGED:
        changed = (
            fact.before_value is not None
            and fact.after_value is not None
            and fact.before_value != fact.after_value
        )
        return changed and (expected in {"", None} or fact.after_value == expected)
    if relation == TaskObligationRelation.IS_CHECKED:
        return fact.after_value is True
    if relation == TaskObligationRelation.IS_SELECTED:
        return fact.after_value == expected
    if relation == TaskObligationRelation.IS_COMPLETED:
        return fact.after_value is True or (
            fact.after_value is not None and fact.after_value == expected
        )
    return False


def _expected_value_for_proof(obligation: TaskObligationSpec) -> FrozenEvidenceValue:
    if obligation.expected_value.casefold() == "true":
        return True
    if obligation.expected_value.casefold() == "false":
        return False
    return obligation.expected_value


def _frozen_evidence_value(
    field_name: str,
    value: object,
) -> FrozenEvidenceValue:
    if value is None or type(value) in {str, bool, int, float}:
        return cast(FrozenEvidenceValue, value)
    raise ValueError(f"unsupported {field_name} evidence value")


def _source_kind_and_strength(
    source: str,
) -> tuple[EvidenceSourceKind, EvidenceStrength] | None:
    normalized = source.casefold()
    if normalized == "post_action_observation":
        return EvidenceSourceKind.POST_ACTION_OBSERVATION, EvidenceStrength.INDEPENDENT
    if normalized == "independent_http_json":
        return EvidenceSourceKind.INDEPENDENT_API, EvidenceStrength.AUTHORITATIVE
    if normalized == "execution_receipt":
        return EvidenceSourceKind.EXECUTION_RECEIPT, EvidenceStrength.WEAK
    if normalized == "external_evaluator":
        return EvidenceSourceKind.EXTERNAL_EVALUATOR, EvidenceStrength.WEAK
    return None


def _reported_strength(reported: str) -> EvidenceStrength | None:
    normalized = reported.casefold()
    if normalized == "weak":
        return EvidenceStrength.WEAK
    if normalized == "strong":
        return EvidenceStrength.AUTHORITATIVE
    if normalized == EvidenceStrength.INDEPENDENT.value:
        return EvidenceStrength.INDEPENDENT
    if normalized == EvidenceStrength.AUTHORITATIVE.value:
        return EvidenceStrength.AUTHORITATIVE
    return None


def _minimum_strength(
    left: EvidenceStrength,
    right: EvidenceStrength,
) -> EvidenceStrength:
    return left if _strength_rank(left) <= _strength_rank(right) else right


def _strength_rank(strength: EvidenceStrength) -> int:
    return {
        EvidenceStrength.WEAK: 0,
        EvidenceStrength.INDEPENDENT: 1,
        EvidenceStrength.AUTHORITATIVE: 2,
    }[strength]


def _evidence_shape_supported(
    *,
    relation: TaskObligationRelation,
    before_value: FrozenEvidenceValue,
    after_value: FrozenEvidenceValue,
) -> bool:
    if relation in {
        TaskObligationRelation.EQUALS,
        TaskObligationRelation.CONTAINS,
        TaskObligationRelation.MATCHES,
    }:
        return after_value is not None and not isinstance(after_value, bool)
    if relation == TaskObligationRelation.HAS_CHANGED:
        return (
            before_value is not None
            and after_value is not None
            and before_value != after_value
        )
    if relation == TaskObligationRelation.IS_CHECKED:
        return after_value is True
    if relation == TaskObligationRelation.IS_SELECTED:
        return after_value is not None and not isinstance(after_value, bool)
    if relation == TaskObligationRelation.IS_COMPLETED:
        return after_value is True or (
            after_value is not None and not isinstance(after_value, bool)
        )
    return False


def _action_relation_compatible(
    action_kind: str,
    relation: TaskObligationRelation,
) -> bool:
    normalized = action_kind.casefold()
    if normalized in {"type_text", "enter_text", "input_text", "fill"}:
        return relation in {
            TaskObligationRelation.CONTAINS,
            TaskObligationRelation.EQUALS,
            TaskObligationRelation.HAS_CHANGED,
            TaskObligationRelation.MATCHES,
        }
    if normalized in {"press_key", "set_value", "drag", "select_option"}:
        return relation in {
            TaskObligationRelation.CONTAINS,
            TaskObligationRelation.EQUALS,
            TaskObligationRelation.HAS_CHANGED,
            TaskObligationRelation.IS_CHECKED,
            TaskObligationRelation.IS_SELECTED,
        }
    if normalized in {"activate", "click", "submit"}:
        return relation in {
            TaskObligationRelation.HAS_CHANGED,
            TaskObligationRelation.IS_CHECKED,
            TaskObligationRelation.IS_COMPLETED,
            TaskObligationRelation.IS_SELECTED,
        }
    return False


def _validate_progress_for_ticket(
    *,
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
) -> ProgressAttributionTicketResolution | None:
    if (
        progress.task_spec_identity != task_spec.identity
        or progress.task_revision != task_spec.revision
        or progress.known_obligation_ids
        != tuple(obligation.obligation_id for obligation in task_spec.obligations)
    ):
        return ProgressAttributionTicketResolution(status="stale")
    try:
        validate_obligation_progress_state(task_spec, progress)
    except ValueError as exc:
        return ProgressAttributionTicketResolution(
            status="invalid",
            reason=str(exc),
        )
    return None


def _ready_view_matches_obligation(
    *,
    view: ReadyObligationView,
    obligation: TaskObligationSpec,
) -> bool:
    return (
        view.subject == obligation.subject
        and view.relation == obligation.relation
        and view.expected_value == obligation.expected_value
        and view.evidence_requirements == obligation.evidence_requirements
        and view.dependency_ids == obligation.depends_on
        and view.terminal == obligation.terminal
    )


def _ticket_id(
    *,
    action: AttributionActionView,
    candidate_obligation_ids: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "action_kind": action.action_kind,
            "candidate_obligation_ids": candidate_obligation_ids,
            "canonical_subject_ids": action.target.canonical_subject_ids,
            "contract_hash": action.contract_hash,
            "contract_id": action.contract_id,
            "issued_at_state_version": action.issued_at_state_version,
            "pre_environment_revision": action.pre_environment_revision,
            "pre_page_revision": action.pre_page_revision,
            "pre_snapshot_id": action.pre_snapshot_id,
            "semantic_target_id": action.target.semantic_target_id,
            "task_revision": action.task_revision,
            "task_spec_identity": action.task_spec_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ticket:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
