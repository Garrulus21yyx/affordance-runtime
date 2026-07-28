"""Authority-free current-observation obligation satisfaction.

This module prepares satisfaction for canonical obligations that can be proven
from the current observation alone. It does not mutate ``StateKernel``, write
trace events, invoke planners, inspect TaskPlan, or decide task finish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from affordance_runtime.obligation_attribution import (
    CurrentObservationSatisfactionSource,
    EvidenceStrength,
    ObligationSatisfactionPreparation,
)
from affordance_runtime.obligation_progress import (
    PROGRESS_ROLES,
    ObligationProgressStateView,
    TaskObligationExecutionView,
    validate_obligation_progress_state,
)
from affordance_runtime.task_intake import EvidenceKind, TaskObligationRelation, TaskSpec


@dataclass(frozen=True)
class CurrentObservationAffordanceFact:
    """A current observation fact that carries no obligation authority."""

    snapshot_id: str
    page_revision: str
    environment_revision: str
    semantic_target_id: str
    subject: str
    relation: TaskObligationRelation
    visible: bool | None
    enabled: bool | None
    evidence_kind: EvidenceKind
    strength: EvidenceStrength
    source_ref: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        _require_nonblank("subject", self.subject)
        _require_nonblank("source_ref", self.source_ref)
        if not self.evidence_refs:
            raise ValueError("current observation evidence refs cannot be empty")
        _require_unique_nonblank("current observation evidence refs", self.evidence_refs)


@dataclass(frozen=True)
class CurrentObservationSatisfactionResult:
    status: Literal[
        "none",
        "satisfied",
        "multiple_satisfied",
        "ambiguous_target",
        "stale",
        "invalid",
        "weak_evidence",
    ]
    preparations: tuple[ObligationSatisfactionPreparation, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == "satisfied" and len(self.preparations) != 1:
            raise ValueError("satisfied current-observation result requires one preparation")
        if self.status == "multiple_satisfied" and len(self.preparations) < 2:
            raise ValueError(
                "multiple_satisfied current-observation result requires multiple preparations"
            )
        if self.status not in {"satisfied", "multiple_satisfied"} and self.preparations:
            raise ValueError("non-satisfied current-observation result cannot include preparations")


class CurrentObservationObligationSatisfactionEvaluator:
    """Prepare one uniquely proven current-observation obligation satisfaction."""

    _SUPPORTED_RELATIONS = {
        TaskObligationRelation.IS_AVAILABLE,
        TaskObligationRelation.IS_VISIBLE,
    }

    def evaluate(
        self,
        *,
        task_spec: TaskSpec,
        progress: ObligationProgressStateView,
        execution_views: tuple[TaskObligationExecutionView, ...],
        facts: tuple[CurrentObservationAffordanceFact, ...],
        snapshot_id: str,
        page_revision: str,
        environment_revision: str,
    ) -> CurrentObservationSatisfactionResult:
        if not _observation_identity_is_nonblank(
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            environment_revision=environment_revision,
        ):
            return CurrentObservationSatisfactionResult(
                status="stale",
                reason="observation identity is incomplete",
            )
        try:
            validate_obligation_progress_state(task_spec, progress)
            views_by_id = _validated_views_by_id(task_spec, execution_views)
        except ValueError:
            return CurrentObservationSatisfactionResult(status="stale")

        satisfied = set(progress.satisfied_obligation_ids)
        failed = set(progress.failed_obligation_ids)
        preparations: list[ObligationSatisfactionPreparation] = []
        saw_ambiguous_target = False
        saw_stale_observation = False
        saw_weak_evidence = False
        for obligation in task_spec.obligations:
            view = views_by_id[obligation.obligation_id]
            if view.role not in PROGRESS_ROLES:
                continue
            if view.relation not in self._SUPPORTED_RELATIONS:
                continue
            if view.obligation_id in satisfied or view.obligation_id in failed:
                continue
            if not set(view.dependency_ids).issubset(satisfied):
                continue
            matches = tuple(
                fact
                for fact in facts
                if _fact_matches_view(
                    fact,
                    view,
                    snapshot_id=snapshot_id,
                    page_revision=page_revision,
                    environment_revision=environment_revision,
                )
            )
            stale_matches = tuple(
                fact
                for fact in facts
                if fact.subject == view.subject
                and fact.relation == view.relation
                and _relation_satisfied(view.relation, fact)
                and (
                    fact.snapshot_id != snapshot_id
                    or fact.page_revision != page_revision
                    or fact.environment_revision != environment_revision
                )
            )
            if stale_matches:
                saw_stale_observation = True
            if len(matches) > 1:
                saw_ambiguous_target = True
                continue
            if not matches:
                continue
            fact = matches[0]
            if not _evidence_satisfies_requirement(fact, obligation):
                saw_weak_evidence = True
                continue
            preparations.append(
                ObligationSatisfactionPreparation(
                    task_spec_identity=task_spec.identity,
                    task_revision=task_spec.revision,
                    evaluated_at_state_version=progress.evaluated_at_state_version,
                    obligation_id=view.obligation_id,
                    evidence_refs=fact.evidence_refs,
                    source=CurrentObservationSatisfactionSource(
                        snapshot_id=snapshot_id,
                        page_revision=page_revision,
                        environment_revision=environment_revision,
                    ),
                )
            )

        if preparations:
            if len(preparations) == 1:
                return CurrentObservationSatisfactionResult(
                    status="satisfied",
                    preparations=tuple(preparations),
                )
            return CurrentObservationSatisfactionResult(
                status="multiple_satisfied",
                preparations=tuple(preparations),
            )
        if saw_ambiguous_target:
            return CurrentObservationSatisfactionResult(status="ambiguous_target")
        if saw_stale_observation:
            return CurrentObservationSatisfactionResult(status="stale")
        if saw_weak_evidence:
            return CurrentObservationSatisfactionResult(status="weak_evidence")
        return CurrentObservationSatisfactionResult(status="none")


def _fact_matches_view(
    fact: CurrentObservationAffordanceFact,
    view: TaskObligationExecutionView,
    *,
    snapshot_id: str,
    page_revision: str,
    environment_revision: str,
) -> bool:
    return (
        fact.snapshot_id == snapshot_id
        and fact.page_revision == page_revision
        and fact.environment_revision == environment_revision
        and fact.subject == view.subject
        and fact.relation == view.relation
        and _relation_satisfied(view.relation, fact)
    )


def _evidence_satisfies_requirement(
    fact: CurrentObservationAffordanceFact,
    obligation: object,
) -> bool:
    typed_requirements = getattr(obligation, "typed_evidence_requirements", ())
    return any(
        requirement.subject == fact.subject
        and requirement.relation == fact.relation
        and requirement.kind == fact.evidence_kind
        and fact.source_ref in requirement.source_constraints
        and _strength_rank(fact.strength.value) >= _strength_rank(requirement.minimum_strength)
        for requirement in typed_requirements
    )


def _strength_rank(value: str) -> int:
    ranks = {
        EvidenceStrength.WEAK.value: 0,
        EvidenceStrength.INDEPENDENT.value: 1,
        EvidenceStrength.AUTHORITATIVE.value: 2,
    }
    return ranks.get(value, -1)


def _relation_satisfied(
    relation: TaskObligationRelation,
    fact: CurrentObservationAffordanceFact,
) -> bool:
    if relation == TaskObligationRelation.IS_VISIBLE:
        return fact.visible is True
    if relation == TaskObligationRelation.IS_AVAILABLE:
        return fact.visible is True and fact.enabled is True
    return False


def _validated_views_by_id(
    task_spec: TaskSpec,
    execution_views: tuple[TaskObligationExecutionView, ...],
) -> dict[str, TaskObligationExecutionView]:
    views_by_id = {item.obligation_id: item for item in execution_views}
    if len(views_by_id) != len(execution_views):
        raise ValueError("obligation execution role ids must be unique")
    expected_ids = {item.obligation_id for item in task_spec.obligations}
    supplied_ids = set(views_by_id)
    missing = sorted(expected_ids - supplied_ids)
    if missing:
        raise ValueError(f"missing obligation execution role: {', '.join(missing)}")
    extra = sorted(supplied_ids - expected_ids)
    if extra:
        raise ValueError(f"unknown obligation execution role: {', '.join(extra)}")
    return views_by_id


def _observation_identity_is_nonblank(
    *,
    snapshot_id: str,
    page_revision: str,
    environment_revision: str,
) -> bool:
    return all(
        value.strip()
        for value in (snapshot_id, page_revision, environment_revision)
    )


def _require_nonblank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_unique_nonblank(field_name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")
    if any(not item.strip() for item in values):
        raise ValueError(f"{field_name} cannot contain blank values")
