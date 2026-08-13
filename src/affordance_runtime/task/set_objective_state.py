"""Runtime-owned lifecycle for one admitted quantified objective."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.evaluation.contracts import ActionEvaluationStatus
from affordance_runtime.task.set_objective import (
    ActionObligationStatus,
    ActionTemplate,
    CandidateUniverse,
    PredicateAssessment,
    PredicateAssurance,
    PredicateExpr,
    PredicateTruth,
    SchedulingPolicy,
    ScopeCoverage,
    ScopeExtent,
    ScopeSpec,
    SetCompletionCertificate,
    SetDisposition,
    SetMemberObligation,
    SetObjective,
    SetObjectiveReduction,
    SetQuantifier,
    StabilityStatus,
    evaluate_predicate,
    predicate_public_value,
    reduce_set_objective,
)
from affordance_runtime.world.contracts import (
    ActionSpace,
    CoverageState,
    WorldObservation,
)

MAX_SET_MEMBERS = 256


class SetEvidenceNeedKind(StrEnum):
    ENUMERATE_SCOPE = "enumerate_scope"
    CLASSIFY_PREDICATE = "classify_predicate"
    RESOLVE_UNKNOWN = "resolve_unknown"
    VERIFY_ITEM_EFFECT = "verify_item_effect"
    REFRESH_STABILITY = "refresh_stability"
    RESOLVE_ACTIONABILITY = "resolve_actionability"


class SetObjectiveStateErrorCode(StrEnum):
    EMPTY_CANDIDATE_DOMAIN = "empty_candidate_domain"
    SET_CAPACITY_EXCEEDED = "set_capacity_exceeded"
    UNKNOWN_CANDIDATE = "unknown_candidate"
    MIXED_CANDIDATE_ROLE = "mixed_candidate_role"


class SetObjectiveStateError(ValueError):
    def __init__(self, code: SetObjectiveStateErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True)
class SetEvidenceObligation:
    kind: SetEvidenceNeedKind
    entity_ids: tuple[str, ...]
    predicate_digest: str
    reason_code: str

    def __post_init__(self) -> None:
        values = tuple(self.entity_ids)
        if (
            len(values) != len(set(values))
            or any(not item.strip() for item in values)
            or (self.predicate_digest and len(self.predicate_digest) != 64)
            or not self.reason_code.strip()
        ):
            raise ValueError("set evidence obligation is invalid")
        object.__setattr__(self, "entity_ids", values)


@dataclass(frozen=True)
class SetObjectiveState:
    """Authoritative membership/effect state independent of model history."""

    objective: SetObjective
    candidate_role: str
    candidate_entity_ids: tuple[str, ...]
    universe: CandidateUniverse
    assessments: tuple[PredicateAssessment, ...]
    obligations: tuple[SetMemberObligation, ...]
    stability_status: StabilityStatus = StabilityStatus.PENDING
    certificate: SetCompletionCertificate | None = None
    revision: int = 1
    issue_code: str = ""

    def __post_init__(self) -> None:
        candidates = tuple(self.candidate_entity_ids)
        if (
            not self.candidate_role.strip()
            or len(self.candidate_role) > 120
            or not 1 <= self.revision
            or len(candidates) > MAX_SET_MEMBERS
            or len(candidates) != len(set(candidates))
            or any(not item.strip() for item in candidates)
        ):
            raise ValueError("set objective state candidate domain is invalid")
        if self.universe.scope_id != self.objective.scope.scope_id:
            raise ValueError("set objective state scope identity mismatch")
        object.__setattr__(self, "candidate_entity_ids", candidates)
        object.__setattr__(self, "assessments", tuple(self.assessments))
        object.__setattr__(self, "obligations", tuple(self.obligations))

    @property
    def reduction(self) -> SetObjectiveReduction:
        if self.issue_code:
            return SetObjectiveReduction(SetDisposition.BLOCKED, self.issue_code)
        return reduce_set_objective(
            self.objective,
            self.universe,
            self.assessments,
            self.obligations,
            stability_status=self.stability_status,
        )


def establish_set_objective_state(
    *,
    predicate: PredicateExpr,
    quantifier: SetQuantifier,
    semantic_action: str,
    candidate_entity_ids: tuple[str, ...],
    observation: WorldObservation,
) -> SetObjectiveState:
    """Install one admitted objective against a full Runtime observation."""

    candidates = tuple(dict.fromkeys(candidate_entity_ids))
    if not candidates:
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.EMPTY_CANDIDATE_DOMAIN)
    if len(candidates) > MAX_SET_MEMBERS:
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.SET_CAPACITY_EXCEEDED)
    visible = {item.target_id for item in observation.targets}
    if any(item not in visible for item in candidates):
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.UNKNOWN_CANDIDATE)
    targets = {item.target_id: item for item in observation.targets}
    roles = {targets[item].role.casefold().strip() for item in candidates}
    if len(roles) != 1 or not next(iter(roles)):
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.MIXED_CANDIDATE_ROLE)
    candidate_role = next(iter(roles))
    digest = _objective_digest(predicate, quantifier, semantic_action, candidates)
    scope = ScopeSpec(
        f"scope:{digest[:24]}",
        "current-viewport",
        ScopeExtent.CURRENT_VIEWPORT,
    )
    objective = SetObjective(
        f"set-objective:{digest[:24]}",
        scope,
        predicate,
        quantifier,
        ActionTemplate(semantic_action),
        SchedulingPolicy(),
    )
    universe = _universe(scope, candidates, observation)
    assessments = _assess(objective, universe, observation)
    obligations = _merge_obligations((), assessments, observation.observation_id)
    return SetObjectiveState(
        objective,
        candidate_role,
        candidates,
        universe,
        assessments,
        obligations,
    )


def refresh_set_objective_state(
    state: SetObjectiveState,
    observation: WorldObservation,
    *,
    acted_entity_id: str = "",
    action_status: ActionEvaluationStatus | None = None,
    effect_evidence_refs: tuple[str, ...] = (),
) -> SetObjectiveState:
    """Advance membership/effects on a fresh observation without reading history."""

    current_targets = {item.target_id for item in observation.targets}
    historical = tuple(item for item in state.obligations if item.entity_id not in current_targets)
    current_candidates = tuple(
        item.target_id
        for item in observation.targets
        if item.role.casefold().strip() == state.candidate_role
    )
    if len(current_candidates) > MAX_SET_MEMBERS:
        return replace(state, issue_code="set_capacity_exceeded", revision=state.revision + 1)
    universe = _universe(state.objective.scope, current_candidates, observation)
    assessments = _assess(state.objective, universe, observation)
    obligations = _apply_effect(
        state.obligations,
        acted_entity_id,
        action_status,
        observation.observation_id,
        effect_evidence_refs,
    )
    obligations = _merge_obligations(obligations, assessments, observation.observation_id)
    obligations = tuple(dict((item.entity_id, item) for item in (*historical, *obligations)).values())
    provisional = SetObjectiveState(
        state.objective,
        state.candidate_role,
        current_candidates,
        universe,
        assessments,
        obligations,
        StabilityStatus.PENDING,
        revision=state.revision + 1,
    )
    stable = (
        universe.coverage is ScopeCoverage.COMPLETE
        and all(item.truth is not PredicateTruth.UNKNOWN for item in assessments)
        and not any(
            item.action_status in {
                ActionObligationStatus.UNACTED,
                ActionObligationStatus.ACTION_IN_FLIGHT,
                ActionObligationStatus.NO_EFFECT_CONFIRMED,
                ActionObligationStatus.EFFECT_UNKNOWN,
                ActionObligationStatus.BLOCKED,
            }
            for item in obligations
        )
        and observation.observation_id != state.universe.observation_epoch
    )
    if not stable:
        return provisional
    settled = replace(provisional, stability_status=StabilityStatus.PASSED)
    final = settled.reduction
    return replace(
        settled,
        certificate=final.certificate,
    ) if final.certificate is not None else settled


def set_allowed_action_ids(
    state: SetObjectiveState,
    action_space: ActionSpace,
) -> frozenset[str]:
    """Map the reducer's stable entity identity to current private action IDs."""

    reduction = state.reduction
    if reduction.next_entity_id:
        admitted = {reduction.next_entity_id}
    else:
        admitted = set(reduction.true_entity_ids)
    return frozenset(
        option.action_id
        for option in action_space.options
        if option.target_id in admitted
        and option.semantic_action == state.objective.action_template.semantic_action
    )


def set_evidence_obligations(
    state: SetObjectiveState,
) -> tuple[SetEvidenceObligation, ...]:
    """Mechanically project missing evidence from the authoritative reducer."""

    reduction = state.reduction
    kind = {
        SetDisposition.NEED_SCOPE_CLOSURE: SetEvidenceNeedKind.ENUMERATE_SCOPE,
        SetDisposition.NEED_CLASSIFICATION: SetEvidenceNeedKind.CLASSIFY_PREDICATE,
        SetDisposition.NEED_UNKNOWN_RESOLUTION: SetEvidenceNeedKind.RESOLVE_UNKNOWN,
        SetDisposition.NEED_EFFECT_RESOLUTION: SetEvidenceNeedKind.VERIFY_ITEM_EFFECT,
        SetDisposition.NEED_STABILITY_CHECK: SetEvidenceNeedKind.REFRESH_STABILITY,
    }.get(reduction.disposition)
    if kind is None:
        return ()
    if kind in {SetEvidenceNeedKind.CLASSIFY_PREDICATE, SetEvidenceNeedKind.RESOLVE_UNKNOWN}:
        entities = tuple(
            item.entity_id
            for item in state.assessments
            if item.truth is PredicateTruth.UNKNOWN
        )
    else:
        entities = reduction.true_entity_ids
    return (SetEvidenceObligation(
        kind,
        entities,
        state.objective.predicate_digest,
        reduction.reason_code,
    ),)


def install_semantic_assessments(
    state: SetObjectiveState,
    assessments: tuple[tuple[str, PredicateTruth, float], ...],
    *,
    evaluator_id: str = "model-policy-semantic-classifier",
) -> SetObjectiveState:
    """Install a complete model assessment only for currently unknown members."""

    unknown_ids = {
        item.entity_id
        for item in state.assessments
        if item.truth is PredicateTruth.UNKNOWN
    }
    submitted = tuple(assessments)
    if (
        not unknown_ids
        or {item[0] for item in submitted} != unknown_ids
        or len(submitted) != len(unknown_ids)
        or any(not 0 <= confidence <= 1 for _, _, confidence in submitted)
    ):
        raise ValueError("semantic assessment batch must cover every unknown member exactly once")
    replacements = {
        entity_id: PredicateAssessment(
            entity_id,
            state.objective.predicate_digest,
            truth,
            PredicateAssurance.SEMANTIC,
            evaluator_id,
            state.universe.observation_epoch,
            (f"semantic-assessment:{state.universe.observation_epoch}:{entity_id}",),
            confidence,
        )
        for entity_id, truth, confidence in submitted
    }
    merged = tuple(replacements.get(item.entity_id, item) for item in state.assessments)
    obligations = _merge_obligations(
        state.obligations,
        merged,
        state.universe.observation_epoch,
    )
    return replace(
        state,
        assessments=merged,
        obligations=obligations,
        stability_status=StabilityStatus.PENDING,
        certificate=None,
        revision=state.revision + 1,
    )


def _universe(
    scope: ScopeSpec,
    candidates: tuple[str, ...],
    observation: WorldObservation,
) -> CandidateUniverse:
    complete_sources = tuple(
        f"source:{name}:coverage"
        for name, coverage in observation.coverage.items()
        if coverage is CoverageState.COMPLETE
    )
    complete = bool(observation.coverage) and len(complete_sources) == len(observation.coverage)
    return CandidateUniverse(
        scope.scope_id,
        observation.observation_id,
        candidates,
        ScopeCoverage.COMPLETE if complete else ScopeCoverage.PARTIAL,
        complete_sources if complete else (),
    )


def _assess(
    objective: SetObjective,
    universe: CandidateUniverse,
    observation: WorldObservation,
) -> tuple[PredicateAssessment, ...]:
    targets = {item.target_id: dict(item.state) for item in observation.targets}
    for fact in observation.facts:
        if fact.subject_id in targets:
            targets[fact.subject_id][fact.predicate] = fact.value
    return tuple(
        PredicateAssessment(
            entity_id,
            objective.predicate_digest,
            evaluate_predicate(objective.predicate, targets.get(entity_id, {})),
            PredicateAssurance.STRUCTURAL,
            "runtime-predicate-evaluator",
            observation.observation_id,
            (f"observation:{observation.observation_id}:{entity_id}",),
        )
        for entity_id in universe.entity_ids
    )


def _merge_obligations(
    previous: tuple[SetMemberObligation, ...],
    assessments: tuple[PredicateAssessment, ...],
    observation_epoch: str,
) -> tuple[SetMemberObligation, ...]:
    by_id = {item.entity_id: item for item in previous}
    for assessment in assessments:
        existing = by_id.get(assessment.entity_id)
        if existing is None and assessment.truth is PredicateTruth.TRUE:
            by_id[assessment.entity_id] = SetMemberObligation(
                assessment.entity_id,
                observation_epoch,
                PredicateTruth.TRUE,
                ActionObligationStatus.UNACTED,
            )
        elif existing is not None:
            by_id[assessment.entity_id] = replace(
                existing,
                membership_status=assessment.truth,
            )
    return tuple(by_id.values())


def _apply_effect(
    obligations: tuple[SetMemberObligation, ...],
    entity_id: str,
    status: ActionEvaluationStatus | None,
    observation_epoch: str,
    evidence_refs: tuple[str, ...],
) -> tuple[SetMemberObligation, ...]:
    if not entity_id or status is None:
        return obligations
    projected = {
        ActionEvaluationStatus.EFFECT_CONFIRMED: ActionObligationStatus.EFFECT_CONFIRMED,
        ActionEvaluationStatus.NO_EFFECT_CONFIRMED: ActionObligationStatus.NO_EFFECT_CONFIRMED,
        ActionEvaluationStatus.UNKNOWN: ActionObligationStatus.EFFECT_UNKNOWN,
        ActionEvaluationStatus.REJECTED: ActionObligationStatus.UNACTED,
    }[status]
    return tuple(
        replace(
            item,
            action_status=projected,
            effect_evidence_refs=(
                evidence_refs
                if projected is ActionObligationStatus.EFFECT_CONFIRMED
                else ()
            ),
            effect_epoch=(
                observation_epoch
                if projected is ActionObligationStatus.EFFECT_CONFIRMED
                else ""
            ),
        )
        if item.entity_id == entity_id
        else item
        for item in obligations
    )


def _objective_digest(
    predicate: PredicateExpr,
    quantifier: SetQuantifier,
    semantic_action: str,
    candidates: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "predicate": predicate_public_value(predicate),
            "quantifier": quantifier.value,
            "semantic_action": semantic_action,
            "candidates": candidates,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
