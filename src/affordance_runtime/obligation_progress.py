"""Typed, authority-free canonical obligation progress contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

from affordance_runtime.task_intake import (
    TaskObligationRelation,
    TaskObligationSpec,
    TaskSpec,
)


class ObligationExecutionRole(StrEnum):
    PRECONDITION = "precondition"
    PROGRESS_EFFECT = "progress_effect"
    TERMINAL_EFFECT = "terminal_effect"
    EVIDENCE_ONLY = "evidence_only"


PROGRESS_ROLES = frozenset(
    {
        ObligationExecutionRole.PROGRESS_EFFECT,
        ObligationExecutionRole.TERMINAL_EFFECT,
    }
)


@dataclass(frozen=True)
class TaskObligationExecutionView:
    obligation_id: str
    role: ObligationExecutionRole
    subject: str
    relation: TaskObligationRelation
    expected_value: str
    evidence_requirements: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    terminal: bool
    blocking: bool

    def __post_init__(self) -> None:
        _require_nonblank("obligation_id", self.obligation_id)
        _require_nonblank("subject", self.subject)
        _require_unique_nonblank("dependency_ids", self.dependency_ids)
        _require_unique_nonblank("evidence_requirements", self.evidence_requirements)

    @classmethod
    def from_obligation(
        cls,
        obligation: TaskObligationSpec,
        *,
        role: ObligationExecutionRole,
    ) -> "TaskObligationExecutionView":
        return cls(
            obligation_id=obligation.obligation_id,
            role=role,
            subject=obligation.subject,
            relation=obligation.relation,
            expected_value=obligation.expected_value,
            evidence_requirements=obligation.evidence_requirements,
            dependency_ids=obligation.depends_on,
            terminal=obligation.terminal,
            blocking=obligation.blocking,
        )


@dataclass(frozen=True)
class ObligationProgressStateView:
    task_revision: int
    evaluated_at_state_version: int
    satisfied_obligation_ids: tuple[str, ...] = ()
    failed_obligation_ids: tuple[str, ...] = ()
    evidence_by_obligation: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    attempt_count_by_obligation: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        _require_unique_nonblank("satisfied obligation ids", self.satisfied_obligation_ids)
        _require_unique_nonblank("failed obligation ids", self.failed_obligation_ids)
        overlap = set(self.satisfied_obligation_ids) & set(self.failed_obligation_ids)
        if overlap:
            raise ValueError("obligation cannot be both satisfied and failed")
        for obligation_id, evidence_refs in self.evidence_by_obligation.items():
            _require_nonblank("evidence obligation id", obligation_id)
            _require_unique_nonblank("evidence refs", evidence_refs)
        for obligation_id, count in self.attempt_count_by_obligation.items():
            _require_nonblank("attempt obligation id", obligation_id)
            if count < 0:
                raise ValueError("obligation attempt count cannot be negative")


@dataclass(frozen=True)
class ReadyObligationView:
    obligation_id: str
    role: ObligationExecutionRole
    subject: str
    relation: TaskObligationRelation
    expected_value: str
    evidence_requirements: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    terminal: bool


def task_obligation_execution_views(
    task_spec: TaskSpec,
    roles_by_obligation_id: Mapping[str, ObligationExecutionRole],
) -> tuple[TaskObligationExecutionView, ...]:
    """Project explicit role decisions onto the canonical obligation graph."""

    expected_ids = {item.obligation_id for item in task_spec.obligations}
    supplied_ids = set(roles_by_obligation_id)
    missing = sorted(expected_ids - supplied_ids)
    if missing:
        raise ValueError(f"missing obligation execution role: {', '.join(missing)}")
    extra = sorted(supplied_ids - expected_ids)
    if extra:
        raise ValueError(f"unknown obligation execution role: {', '.join(extra)}")
    return tuple(
        TaskObligationExecutionView.from_obligation(
            obligation,
            role=roles_by_obligation_id[obligation.obligation_id],
        )
        for obligation in task_spec.obligations
    )


def ready_obligation_ids(
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    execution_views: tuple[TaskObligationExecutionView, ...],
) -> tuple[str, ...]:
    """Return graph-ordered ready progress obligations from canonical state."""

    views_by_id = _validated_views_by_id(task_spec, execution_views)
    satisfied = set(progress.satisfied_obligation_ids)
    failed = set(progress.failed_obligation_ids)
    return tuple(
        obligation.obligation_id
        for obligation in task_spec.obligations
        if (view := views_by_id[obligation.obligation_id]).role in PROGRESS_ROLES
        and obligation.obligation_id not in satisfied
        and obligation.obligation_id not in failed
        and set(view.dependency_ids).issubset(satisfied)
    )


def ready_obligation_views(
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    execution_views: tuple[TaskObligationExecutionView, ...],
) -> tuple[ReadyObligationView, ...]:
    """Return immutable Planner-facing views for ready obligations."""

    views_by_id = _validated_views_by_id(task_spec, execution_views)
    ready_ids = set(ready_obligation_ids(task_spec, progress, execution_views))
    return tuple(
        ReadyObligationView(
            obligation_id=view.obligation_id,
            role=view.role,
            subject=view.subject,
            relation=view.relation,
            expected_value=view.expected_value,
            evidence_requirements=view.evidence_requirements,
            dependency_ids=view.dependency_ids,
            terminal=view.terminal,
        )
        for obligation in task_spec.obligations
        if (view := views_by_id[obligation.obligation_id]).obligation_id in ready_ids
    )


def task_obligations_completed(
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    execution_views: tuple[TaskObligationExecutionView, ...],
) -> bool:
    """Evaluate task completion from blocking progress obligations only."""

    views_by_id = _validated_views_by_id(task_spec, execution_views)
    blocking_progress = tuple(
        views_by_id[obligation.obligation_id]
        for obligation in task_spec.obligations
        if views_by_id[obligation.obligation_id].role in PROGRESS_ROLES
        and views_by_id[obligation.obligation_id].blocking
    )
    if not blocking_progress:
        return False
    satisfied = set(progress.satisfied_obligation_ids)
    return all(item.obligation_id in satisfied for item in blocking_progress) and any(
        item.role == ObligationExecutionRole.TERMINAL_EFFECT
        and item.obligation_id in satisfied
        for item in blocking_progress
    )


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


def _require_nonblank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_unique_nonblank(field_name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")
    if any(not item.strip() for item in values):
        raise ValueError(f"{field_name} cannot contain blank values")
