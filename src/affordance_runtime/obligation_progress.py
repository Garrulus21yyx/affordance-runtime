"""Typed, authority-free canonical obligation progress contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Mapping

from affordance_runtime.task_intake import (
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskSpec,
)


class ObligationExecutionRole(StrEnum):
    PRECONDITION = "precondition"
    PROGRESS_EFFECT = "progress_effect"
    TERMINAL_EFFECT = "terminal_effect"
    EVIDENCE_ONLY = "evidence_only"


class ObligationRoleDecisionStatus(StrEnum):
    ASSIGNED = "assigned"
    PENDING = "pending"


PROGRESS_ROLES = frozenset(
    {
        ObligationExecutionRole.PROGRESS_EFFECT,
        ObligationExecutionRole.TERMINAL_EFFECT,
    }
)


@dataclass(frozen=True)
class ObligationRoleDecision:
    obligation_id: str
    status: ObligationRoleDecisionStatus
    role: ObligationExecutionRole | None
    reason_code: str

    def __post_init__(self) -> None:
        _require_nonblank("obligation_id", self.obligation_id)
        _require_nonblank("reason_code", self.reason_code)
        if self.status == ObligationRoleDecisionStatus.ASSIGNED and self.role is None:
            raise ValueError("assigned role decision requires role")
        if self.status == ObligationRoleDecisionStatus.PENDING and self.role is not None:
            raise ValueError("pending role decision cannot include role")


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
class ObligationEvidenceLedgerEntry:
    obligation_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank("evidence obligation id", self.obligation_id)
        _require_unique_nonblank("evidence refs", self.evidence_refs)


@dataclass(frozen=True)
class ObligationAttemptCount:
    obligation_id: str
    attempt_count: int

    def __post_init__(self) -> None:
        _require_nonblank("attempt obligation id", self.obligation_id)
        if self.attempt_count < 0:
            raise ValueError("obligation attempt count cannot be negative")


@dataclass(frozen=True)
class ObligationProgressStateView:
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    known_obligation_ids: tuple[str, ...]
    satisfied_obligation_ids: tuple[str, ...] = ()
    failed_obligation_ids: tuple[str, ...] = ()
    evidence_by_obligation: tuple[ObligationEvidenceLedgerEntry, ...] = ()
    attempt_count_by_obligation: tuple[ObligationAttemptCount, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        _require_unique_nonblank("known obligation ids", self.known_obligation_ids)
        _require_unique_nonblank("satisfied obligation ids", self.satisfied_obligation_ids)
        _require_unique_nonblank("failed obligation ids", self.failed_obligation_ids)
        overlap = set(self.satisfied_obligation_ids) & set(self.failed_obligation_ids)
        if overlap:
            raise ValueError("obligation cannot be both satisfied and failed")
        evidence_ids = tuple(item.obligation_id for item in self.evidence_by_obligation)
        attempt_ids = tuple(item.obligation_id for item in self.attempt_count_by_obligation)
        _require_unique_nonblank("evidence obligation ids", evidence_ids)
        _require_unique_nonblank("attempt obligation ids", attempt_ids)
        known_ids = set(self.known_obligation_ids)
        supplied_ids = (
            set(self.satisfied_obligation_ids)
            | set(self.failed_obligation_ids)
            | set(evidence_ids)
            | set(attempt_ids)
        )
        unknown = sorted(supplied_ids - known_ids)
        if unknown:
            raise ValueError(f"unknown obligation progress id: {', '.join(unknown)}")


@dataclass
class ObligationProgressLedger:
    """Mutable StateKernel storage for canonical-obligation progress.

    This object is storage foundation only. It does not decide runtime finish,
    planner input, recovery, trace, or standard-path progress authority.
    """

    task_spec_identity: str
    task_revision: int
    known_obligation_ids: tuple[str, ...]
    satisfied_obligation_ids: list[str] = field(default_factory=list)
    failed_obligation_ids: list[str] = field(default_factory=list)
    evidence_by_obligation: dict[str, list[str]] = field(default_factory=dict)
    attempt_count_by_obligation: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        _require_unique_nonblank("known obligation ids", self.known_obligation_ids)
        if not self.known_obligation_ids:
            raise ValueError("known obligation ids cannot be empty")
        self._validate_storage()

    @classmethod
    def from_task_spec(cls, task_spec: TaskSpec) -> "ObligationProgressLedger":
        return cls(
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            known_obligation_ids=tuple(
                obligation.obligation_id for obligation in task_spec.obligations
            ),
        )

    def record_attempt(self, obligation_id: str) -> None:
        self._require_known_obligation(obligation_id)
        self.attempt_count_by_obligation[obligation_id] = (
            self.attempt_count_by_obligation.get(obligation_id, 0) + 1
        )
        self._validate_storage()

    def record_satisfaction(
        self,
        obligation_id: str,
        evidence_refs: tuple[str, ...],
    ) -> None:
        self._require_known_obligation(obligation_id)
        if not evidence_refs:
            raise ValueError("satisfaction evidence refs cannot be empty")
        _require_unique_nonblank("satisfaction evidence refs", _dedupe(evidence_refs))
        if obligation_id in self.failed_obligation_ids:
            raise ValueError("obligation is already failed")
        if obligation_id not in self.satisfied_obligation_ids:
            self.satisfied_obligation_ids.append(obligation_id)
        self._append_evidence(obligation_id, evidence_refs)
        self._validate_storage()

    def record_failure(
        self,
        obligation_id: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        self._require_known_obligation(obligation_id)
        if obligation_id in self.satisfied_obligation_ids:
            raise ValueError("obligation is already satisfied")
        if obligation_id not in self.failed_obligation_ids:
            self.failed_obligation_ids.append(obligation_id)
        if evidence_refs:
            self._append_evidence(obligation_id, evidence_refs)
        self._validate_storage()

    def to_view(
        self,
        *,
        evaluated_at_state_version: int,
    ) -> ObligationProgressStateView:
        self._validate_storage()
        return ObligationProgressStateView(
            task_spec_identity=self.task_spec_identity,
            task_revision=self.task_revision,
            evaluated_at_state_version=evaluated_at_state_version,
            known_obligation_ids=tuple(self.known_obligation_ids),
            satisfied_obligation_ids=tuple(self.satisfied_obligation_ids),
            failed_obligation_ids=tuple(self.failed_obligation_ids),
            evidence_by_obligation=tuple(
                ObligationEvidenceLedgerEntry(
                    obligation_id=obligation_id,
                    evidence_refs=tuple(self.evidence_by_obligation[obligation_id]),
                )
                for obligation_id in self.known_obligation_ids
                if obligation_id in self.evidence_by_obligation
            ),
            attempt_count_by_obligation=tuple(
                ObligationAttemptCount(
                    obligation_id=obligation_id,
                    attempt_count=self.attempt_count_by_obligation[obligation_id],
                )
                for obligation_id in self.known_obligation_ids
                if obligation_id in self.attempt_count_by_obligation
            ),
        )

    def _append_evidence(
        self,
        obligation_id: str,
        evidence_refs: tuple[str, ...],
    ) -> None:
        refs = self.evidence_by_obligation.setdefault(obligation_id, [])
        for evidence_ref in _dedupe(evidence_refs):
            if evidence_ref not in refs:
                refs.append(evidence_ref)

    def _require_known_obligation(self, obligation_id: str) -> None:
        _require_nonblank("obligation id", obligation_id)
        if obligation_id not in self.known_obligation_ids:
            raise ValueError(f"unknown obligation id: {obligation_id}")

    def _validate_storage(self) -> None:
        known_ids = set(self.known_obligation_ids)
        _require_unique_nonblank(
            "satisfied obligation ids",
            tuple(self.satisfied_obligation_ids),
        )
        _require_unique_nonblank(
            "failed obligation ids",
            tuple(self.failed_obligation_ids),
        )
        overlap = set(self.satisfied_obligation_ids) & set(self.failed_obligation_ids)
        if overlap:
            raise ValueError("obligation cannot be both satisfied and failed")
        supplied_ids = (
            set(self.satisfied_obligation_ids)
            | set(self.failed_obligation_ids)
            | set(self.evidence_by_obligation)
            | set(self.attempt_count_by_obligation)
        )
        unknown = sorted(supplied_ids - known_ids)
        if unknown:
            raise ValueError(f"unknown obligation id: {', '.join(unknown)}")
        for evidence_refs in self.evidence_by_obligation.values():
            _require_unique_nonblank("evidence refs", tuple(evidence_refs))
        for attempt_count in self.attempt_count_by_obligation.values():
            if attempt_count < 0:
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


@dataclass(frozen=True)
class ReadyObligationProjection:
    status: Literal[
        "ready",
        "role_pending",
        "stale_progress",
        "invalid_progress",
    ]
    ready_obligations: tuple[ReadyObligationView, ...]
    pending_role_obligation_ids: tuple[str, ...]
    reason: str = ""

    def __post_init__(self) -> None:
        _require_unique_nonblank(
            "pending role obligation ids",
            self.pending_role_obligation_ids,
        )
        if self.status == "ready" and self.pending_role_obligation_ids:
            raise ValueError("ready projection cannot include pending role ids")
        if self.status == "role_pending" and not self.pending_role_obligation_ids:
            raise ValueError("role_pending projection requires pending role ids")
        if self.status != "ready" and self.ready_obligations:
            raise ValueError("non-ready projection cannot include ready obligations")


def decide_obligation_execution_roles(
    task_spec: TaskSpec,
) -> tuple[ObligationRoleDecision, ...]:
    """Derive conservative execution-role decisions from canonical fields only."""

    return tuple(_decide_obligation_execution_role(obligation) for obligation in task_spec.obligations)


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


def project_ready_obligations(
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    role_decisions: tuple[ObligationRoleDecision, ...],
) -> ReadyObligationProjection:
    """Safely project ready obligations without throwing into shadow integration."""

    try:
        validate_obligation_progress_state(task_spec, progress)
    except ValueError as exc:
        reason = str(exc)
        if "task spec identity" in reason or "task revision" in reason:
            return ReadyObligationProjection(
                status="stale_progress",
                ready_obligations=(),
                pending_role_obligation_ids=(),
                reason=reason,
            )
        return ReadyObligationProjection(
            status="invalid_progress",
            ready_obligations=(),
            pending_role_obligation_ids=(),
            reason=reason,
        )

    try:
        decisions_by_id = _validated_role_decisions_by_id(task_spec, role_decisions)
    except ValueError as exc:
        return ReadyObligationProjection(
            status="invalid_progress",
            ready_obligations=(),
            pending_role_obligation_ids=(),
            reason=str(exc),
        )

    pending = tuple(
        obligation.obligation_id
        for obligation in task_spec.obligations
        if decisions_by_id[obligation.obligation_id].status
        == ObligationRoleDecisionStatus.PENDING
    )
    if pending:
        reasons = tuple(
            decisions_by_id[obligation_id].reason_code for obligation_id in pending
        )
        return ReadyObligationProjection(
            status="role_pending",
            ready_obligations=(),
            pending_role_obligation_ids=pending,
            reason=", ".join(_dedupe(reasons)),
        )

    execution_views_list: list[TaskObligationExecutionView] = []
    for obligation in task_spec.obligations:
        role = decisions_by_id[obligation.obligation_id].role
        if role is None:
            continue
        execution_views_list.append(
            TaskObligationExecutionView.from_obligation(
                obligation,
                role=role,
            )
        )
    execution_views = tuple(execution_views_list)
    return ReadyObligationProjection(
        status="ready",
        ready_obligations=ready_obligation_views(
            task_spec,
            progress,
            execution_views,
        ),
        pending_role_obligation_ids=(),
    )


def ready_obligation_ids(
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    execution_views: tuple[TaskObligationExecutionView, ...],
) -> tuple[str, ...]:
    """Return graph-ordered ready progress obligations from canonical state."""

    validate_obligation_progress_state(task_spec, progress)
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

    validate_obligation_progress_state(task_spec, progress)
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

    validate_obligation_progress_state(task_spec, progress)
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


def validate_obligation_progress_state(
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
) -> None:
    """Validate that progress belongs to exactly this canonical TaskSpec graph."""

    if progress.task_spec_identity != task_spec.identity:
        raise ValueError("task spec identity does not match obligation progress")
    if progress.task_revision != task_spec.revision:
        raise ValueError("task revision does not match obligation progress")
    expected_ids = tuple(obligation.obligation_id for obligation in task_spec.obligations)
    if progress.known_obligation_ids != expected_ids:
        raise ValueError("known obligation ids do not match canonical graph")
    known_ids = set(expected_ids)
    supplied_ids = (
        set(progress.satisfied_obligation_ids)
        | set(progress.failed_obligation_ids)
        | {item.obligation_id for item in progress.evidence_by_obligation}
        | {item.obligation_id for item in progress.attempt_count_by_obligation}
    )
    unknown = sorted(supplied_ids - known_ids)
    if unknown:
        raise ValueError(f"unknown obligation progress id: {', '.join(unknown)}")


def _decide_obligation_execution_role(
    obligation: TaskObligationSpec,
) -> ObligationRoleDecision:
    if obligation.kind == TaskObligationKind.EFFECT:
        if obligation.terminal:
            return ObligationRoleDecision(
                obligation_id=obligation.obligation_id,
                status=ObligationRoleDecisionStatus.ASSIGNED,
                role=ObligationExecutionRole.TERMINAL_EFFECT,
                reason_code="effect_terminal",
            )
        return ObligationRoleDecision(
            obligation_id=obligation.obligation_id,
            status=ObligationRoleDecisionStatus.ASSIGNED,
            role=ObligationExecutionRole.PROGRESS_EFFECT,
            reason_code="effect_nonterminal",
        )

    if obligation.relation in {
        TaskObligationRelation.IS_AVAILABLE,
        TaskObligationRelation.IS_VISIBLE,
    }:
        if not obligation.blocking and not obligation.terminal:
            return ObligationRoleDecision(
                obligation_id=obligation.obligation_id,
                status=ObligationRoleDecisionStatus.ASSIGNED,
                role=ObligationExecutionRole.PRECONDITION,
                reason_code="nonblocking_availability_predicate",
            )
        return ObligationRoleDecision(
            obligation_id=obligation.obligation_id,
            status=ObligationRoleDecisionStatus.PENDING,
            role=None,
            reason_code="blocking_availability_predicate_pending",
        )

    return ObligationRoleDecision(
        obligation_id=obligation.obligation_id,
        status=ObligationRoleDecisionStatus.PENDING,
        role=None,
        reason_code="predicate_role_pending",
    )


def _validated_role_decisions_by_id(
    task_spec: TaskSpec,
    role_decisions: tuple[ObligationRoleDecision, ...],
) -> dict[str, ObligationRoleDecision]:
    decisions_by_id = {item.obligation_id: item for item in role_decisions}
    if len(decisions_by_id) != len(role_decisions):
        raise ValueError("obligation role decision ids must be unique")
    expected_ids = {item.obligation_id for item in task_spec.obligations}
    supplied_ids = set(decisions_by_id)
    missing = sorted(expected_ids - supplied_ids)
    if missing:
        raise ValueError(f"missing obligation role decision: {', '.join(missing)}")
    extra = sorted(supplied_ids - expected_ids)
    if extra:
        raise ValueError(f"unknown obligation role decision: {', '.join(extra)}")
    return decisions_by_id


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


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)
