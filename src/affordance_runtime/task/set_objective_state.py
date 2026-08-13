"""Runtime-owned lifecycle for one admitted quantified objective."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.evaluation.contracts import ActionEvaluationStatus
from affordance_runtime.task.scope_enumerator import ScopeEnumeratorPort, SnapshotScopeEnumerator
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
    ScopeEntityDomain,
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
    predicate_digest,
    predicate_public_value,
    reduce_set_objective,
    visual_predicate_leaves,
)
from affordance_runtime.world.contracts import (
    ActionSpace,
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
    semantic_leaf_assessments: tuple[PredicateAssessment, ...] = ()

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
        object.__setattr__(self, "semantic_leaf_assessments", tuple(self.semantic_leaf_assessments))

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
    parameters: dict[str, object] | None = None,
    scope: ScopeSpec | None = None,
    enumerator: ScopeEnumeratorPort | None = None,
) -> SetObjectiveState:
    """Install one admitted objective against a full Runtime observation."""

    candidates = tuple(dict.fromkeys(candidate_entity_ids))
    if len(candidates) > MAX_SET_MEMBERS:
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.SET_CAPACITY_EXCEEDED)
    visible = {item.target_id for item in observation.targets}
    if any(item not in visible for item in candidates):
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.UNKNOWN_CANDIDATE)
    candidate_role = "*"
    digest = _objective_digest(predicate, quantifier, semantic_action, candidates)
    scope = scope or ScopeSpec(
        f"scope:{digest[:24]}",
        "current-viewport",
        ScopeExtent.CURRENT_VIEWPORT,
        entity_domain=(
            ScopeEntityDomain.ALL_VISIBLE if visual_predicate_leaves(predicate) else ScopeEntityDomain.STRUCTURED
        ),
    )
    objective = SetObjective(
        f"set-objective:{digest[:24]}",
        scope,
        predicate,
        quantifier,
        ActionTemplate(semantic_action, parameters=parameters or {}),
        SchedulingPolicy(),
    )
    enumeration = (enumerator or SnapshotScopeEnumerator()).enumerate(scope, observation)
    candidates = _action_candidate_ids(
        enumeration.entity_ids,
        semantic_action,
        observation,
    )
    if not candidates and quantifier is not SetQuantifier.ALL_IN_CLOSED_SCOPE:
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.EMPTY_CANDIDATE_DOMAIN)
    if len(candidates) > MAX_SET_MEMBERS:
        raise SetObjectiveStateError(SetObjectiveStateErrorCode.SET_CAPACITY_EXCEEDED)
    universe = CandidateUniverse(
        enumeration.scope_id,
        enumeration.observation_epoch,
        candidates,
        enumeration.coverage,
        enumeration.evidence_refs,
    )
    assessments = _assess(objective, universe, observation, ())
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
    enumerator: ScopeEnumeratorPort | None = None,
) -> SetObjectiveState:
    """Advance membership/effects on a fresh observation without reading history."""

    current_targets = {item.target_id for item in observation.targets}
    historical = tuple(item for item in state.obligations if item.entity_id not in current_targets)
    current_candidates = _action_candidate_ids(
        tuple(item.target_id for item in observation.targets),
        state.objective.action_template.semantic_action,
        observation,
    )
    if len(current_candidates) > MAX_SET_MEMBERS:
        return replace(state, issue_code="set_capacity_exceeded", revision=state.revision + 1)
    universe = _universe(
        state.objective.scope,
        current_candidates,
        state.objective.action_template.semantic_action,
        observation,
        enumerator,
    )
    leaf_assessments = tuple(
        item for item in state.semantic_leaf_assessments if item.observation_epoch == observation.observation_id
    )
    assessments = _assess(state.objective, universe, observation, leaf_assessments)
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
        semantic_leaf_assessments=leaf_assessments,
    )
    stable = (
        universe.coverage is ScopeCoverage.COMPLETE
        and all(item.truth is not PredicateTruth.UNKNOWN for item in assessments)
        and not any(
            item.action_status
            in {
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
    return (
        replace(
            settled,
            certificate=final.certificate,
        )
        if final.certificate is not None
        else settled
    )


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
        if option.target_id in admitted and option.semantic_action == state.objective.action_template.semantic_action
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
        entities = tuple(item.entity_id for item in state.assessments if item.truth is PredicateTruth.UNKNOWN)
    else:
        entities = reduction.true_entity_ids
    return (
        SetEvidenceObligation(
            kind,
            entities,
            state.objective.predicate_digest,
            reduction.reason_code,
        ),
    )


def install_semantic_assessments(
    state: SetObjectiveState,
    assessments: tuple[tuple[str, PredicateTruth, float | None], ...],
    *,
    evaluator_id: str = "model-policy-semantic-classifier",
) -> SetObjectiveState:
    """Install a complete model assessment only for currently unknown members."""

    unknown_ids = {item.entity_id for item in state.assessments if item.truth is PredicateTruth.UNKNOWN}
    submitted = tuple(assessments)
    if (
        not unknown_ids
        or {item[0] for item in submitted} != unknown_ids
        or len(submitted) != len(unknown_ids)
        or any(confidence is not None and not 0 <= confidence <= 1 for _, _, confidence in submitted)
    ):
        raise ValueError("semantic assessment batch must cover every unknown member exactly once")
    replacements = {
        entity_id: PredicateAssessment(
            entity_id,
            state.objective.predicate_digest,
            truth,
            PredicateAssurance.SEMANTIC_UNCALIBRATED,
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


def install_visual_leaf_assessments(
    state: SetObjectiveState,
    observation: WorldObservation,
    leaf: PredicateExpr,
    assessments: tuple[tuple[str, PredicateTruth], ...],
    *,
    evaluator_id: str,
) -> SetObjectiveState:
    """Install evidence for one visual leaf, then let Runtime recompute the compound AST."""

    leaf_digest = predicate_digest(leaf)
    current_ids = set(state.universe.entity_ids)
    submitted = tuple(assessments)
    if (
        observation.observation_id != state.universe.observation_epoch
        or not submitted
        or len({item[0] for item in submitted}) != len(submitted)
        or any(entity_id not in current_ids for entity_id, _ in submitted)
    ):
        raise ValueError("visual leaf assessment batch is not current and bounded")
    replacements = {
        (entity_id, leaf_digest): PredicateAssessment(
            entity_id,
            leaf_digest,
            truth,
            PredicateAssurance.SEMANTIC_UNCALIBRATED,
            evaluator_id,
            state.universe.observation_epoch,
            (f"visual-leaf:{state.universe.observation_epoch}:{leaf_digest[:12]}:{entity_id}",),
            None,
        )
        for entity_id, truth in submitted
    }
    by_key = {
        (item.entity_id, item.predicate_digest): item
        for item in state.semantic_leaf_assessments
        if item.observation_epoch == state.universe.observation_epoch
    }
    by_key.update(replacements)
    leaf_assessments = tuple(by_key.values())
    recomputed = _assess(state.objective, state.universe, observation, leaf_assessments)
    obligations = _merge_obligations(
        state.obligations,
        recomputed,
        state.universe.observation_epoch,
    )
    return replace(
        state,
        assessments=recomputed,
        obligations=obligations,
        stability_status=StabilityStatus.PENDING,
        certificate=None,
        revision=state.revision + 1,
        semantic_leaf_assessments=leaf_assessments,
    )


def _universe(
    scope: ScopeSpec,
    candidates: tuple[str, ...],
    semantic_action: str,
    observation: WorldObservation,
    enumerator: ScopeEnumeratorPort | None,
) -> CandidateUniverse:
    enumeration = (enumerator or SnapshotScopeEnumerator()).enumerate(scope, observation)
    entity_ids = _action_candidate_ids(
        enumeration.entity_ids,
        semantic_action,
        observation,
    )
    if len(entity_ids) > MAX_SET_MEMBERS:
        entity_ids = candidates
    return CandidateUniverse(
        enumeration.scope_id,
        enumeration.observation_epoch,
        entity_ids,
        enumeration.coverage,
        enumeration.evidence_refs,
    )


def _action_candidate_ids(
    scoped_entity_ids: tuple[str, ...],
    semantic_action: str,
    observation: WorldObservation,
) -> tuple[str, ...]:
    """Separate action-member domain from the wider observation scope."""

    actionable = {
        binding.target_id
        for binding in observation.bindings
        if binding.semantic_action == semantic_action
    }
    visual_only = {
        entity_id
        for source in observation.sources
        for entity_id in source.visual_only_target_ids
    }
    admitted = actionable | visual_only
    # Synthetic/unit observations may intentionally omit private bindings and
    # pass an already bounded candidate domain.  A real observation with any
    # route data must never fall back to its wider informational inventory.
    if not observation.bindings and not visual_only:
        return scoped_entity_ids
    return tuple(entity_id for entity_id in scoped_entity_ids if entity_id in admitted)


def _assess(
    objective: SetObjective,
    universe: CandidateUniverse,
    observation: WorldObservation,
    semantic_leaf_assessments: tuple[PredicateAssessment, ...],
) -> tuple[PredicateAssessment, ...]:
    targets = target_public_fields(observation)
    semantic_by_entity: dict[str, dict[str, PredicateTruth]] = {}
    for item in semantic_leaf_assessments:
        if item.observation_epoch == universe.observation_epoch:
            semantic_by_entity.setdefault(item.entity_id, {})[item.predicate_digest] = item.truth
    return tuple(
        PredicateAssessment(
            entity_id,
            objective.predicate_digest,
            evaluate_predicate(
                objective.predicate,
                targets.get(entity_id, {}),
                semantic_by_entity.get(entity_id),
            ),
            PredicateAssurance.STRUCTURAL,
            "runtime-predicate-evaluator",
            observation.observation_id,
            (f"observation:{observation.observation_id}:{entity_id}",),
        )
        for entity_id in universe.entity_ids
    )


def target_public_fields(
    observation: WorldObservation,
) -> dict[str, dict[str, object]]:
    """Project the canonical public facts used by all Runtime selectors."""

    targets = {
        item.target_id: {
            **dict(item.state),
            "identity.entity_id": item.target_id,
            "identity.label": item.label,
            "identity.role": item.role,
            **{f"relation.{key}": value for key, value in item.relations.items()},
        }
        for item in observation.targets
    }
    for fact in observation.facts:
        if fact.subject_id in targets:
            targets[fact.subject_id][fact.predicate] = fact.value
    return targets


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
            effect_evidence_refs=(evidence_refs if projected is ActionObligationStatus.EFFECT_CONFIRMED else ()),
            effect_epoch=(observation_epoch if projected is ActionObligationStatus.EFFECT_CONFIRMED else ""),
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
