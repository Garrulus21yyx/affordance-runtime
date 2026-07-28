"""Authority-free ODG shadow comparison between TaskPlan and obligation progress.

The comparator produces diagnostic payloads only. It does not mutate
``StateKernel``, write trace events, invoke planners, inspect benchmarks, or
decide task completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from affordance_runtime.obligation_progress import ReadyObligationProjection


class ObligationProgressShadowClassification(StrEnum):
    ALIGNED = "aligned"
    LEGACY_ACTIVE_NON_PROGRESS_PREDICATE = "legacy_active_non_progress_predicate"
    OBLIGATION_READY_WITHOUT_SUBGOAL = "obligation_ready_without_subgoal"
    SUBGOAL_WITHOUT_OBLIGATION = "subgoal_without_obligation"
    DEPENDENCY_DIVERGENCE = "dependency_divergence"
    ROLE_PENDING = "role_pending"
    INVALID_PROGRESS = "invalid_progress"
    STALE_PROGRESS = "stale_progress"


@dataclass(frozen=True)
class TaskPlanShadowProjection:
    active_subgoal_id: str
    ready_subgoal_ids: tuple[str, ...]
    completed_subgoal_ids: tuple[str, ...]
    subgoal_obligation_ids: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_unique_nonblank("ready subgoal ids", self.ready_subgoal_ids)
        _require_unique_nonblank("completed subgoal ids", self.completed_subgoal_ids)
        subgoal_ids: list[str] = []
        for subgoal_id, obligation_id in self.subgoal_obligation_ids:
            _require_nonblank("subgoal id", subgoal_id)
            _require_nonblank("obligation id", obligation_id)
            subgoal_ids.append(subgoal_id)
        _require_unique("subgoal obligation subgoal ids", tuple(subgoal_ids))


@dataclass(frozen=True)
class ObligationProgressShadowComparison:
    classification: ObligationProgressShadowClassification
    active_subgoal_id: str
    active_subgoal_obligation_id: str
    ready_subgoal_ids: tuple[str, ...]
    completed_subgoal_ids: tuple[str, ...]
    ready_obligation_ids: tuple[str, ...]
    satisfied_obligation_ids: tuple[str, ...]
    pending_role_obligation_ids: tuple[str, ...] = ()
    divergent_subgoal_ids: tuple[str, ...] = ()
    divergent_obligation_ids: tuple[str, ...] = ()
    reason: str = ""

    def to_trace_payload(self) -> dict[str, object]:
        return {
            "classification": self.classification.value,
            "legacy": {
                "active_subgoal_id": self.active_subgoal_id,
                "ready_subgoal_ids": list(self.ready_subgoal_ids),
                "completed_subgoal_ids": list(self.completed_subgoal_ids),
            },
            "obligation": {
                "active_subgoal_obligation_id": self.active_subgoal_obligation_id,
                "ready_obligation_ids": list(self.ready_obligation_ids),
                "satisfied_obligation_ids": list(self.satisfied_obligation_ids),
                "pending_role_obligation_ids": list(self.pending_role_obligation_ids),
            },
            "divergent_subgoal_ids": list(self.divergent_subgoal_ids),
            "divergent_obligation_ids": list(self.divergent_obligation_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ObligationProgressShadowTraceProjection:
    schema_version: str = "1.0"
    task_spec_identity: str = ""
    task_revision: int = 0
    evaluated_at_state_version: int = 0
    snapshot_id: str = ""
    page_revision: str = ""
    environment_revision: str = ""
    task_plan_id: str = ""
    task_plan_version: int = 0
    obligation_progress_source: Literal[
        "legacy_verified_projection",
        "statekernel_shadow_ledger",
    ] = "legacy_verified_projection"
    comparison: ObligationProgressShadowComparison | None = None

    def __post_init__(self) -> None:
        _require_nonblank("schema version", self.schema_version)
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        _require_nonblank("snapshot id", self.snapshot_id)
        _require_nonblank("page revision", self.page_revision)
        _require_nonblank("environment revision", self.environment_revision)
        _require_nonblank("task plan id", self.task_plan_id)
        if self.task_plan_version < 1:
            raise ValueError("task plan version must be positive")
        if self.comparison is None:
            raise ValueError("shadow trace projection requires comparison")

    def to_trace_payload(self) -> dict[str, object]:
        assert self.comparison is not None
        return {
            "schema_version": self.schema_version,
            "task_spec_identity": self.task_spec_identity,
            "task_revision": self.task_revision,
            "evaluated_at_state_version": self.evaluated_at_state_version,
            "snapshot": {
                "snapshot_id": self.snapshot_id,
                "page_revision": self.page_revision,
                "environment_revision": self.environment_revision,
            },
            "task_plan": {
                "plan_id": self.task_plan_id,
                "plan_version": self.task_plan_version,
            },
            "obligation_progress_source": self.obligation_progress_source,
            "comparison": self.comparison.to_trace_payload(),
        }


def compare_obligation_progress_shadow(
    *,
    legacy: TaskPlanShadowProjection,
    obligation_projection: ReadyObligationProjection,
    satisfied_obligation_ids: tuple[str, ...],
) -> ObligationProgressShadowComparison:
    """Compare legacy TaskPlan progress to canonical obligation projection."""

    ready_obligation_ids = tuple(
        item.obligation_id for item in obligation_projection.ready_obligations
    )
    subgoal_to_obligation = dict(legacy.subgoal_obligation_ids)
    active_obligation_id = subgoal_to_obligation.get(legacy.active_subgoal_id, "")

    if obligation_projection.status == "stale_progress":
        return _comparison(
            ObligationProgressShadowClassification.STALE_PROGRESS,
            legacy,
            active_obligation_id,
            ready_obligation_ids,
            satisfied_obligation_ids,
            pending_role_obligation_ids=obligation_projection.pending_role_obligation_ids,
            reason=obligation_projection.reason,
        )
    if obligation_projection.status == "invalid_progress":
        return _comparison(
            ObligationProgressShadowClassification.INVALID_PROGRESS,
            legacy,
            active_obligation_id,
            ready_obligation_ids,
            satisfied_obligation_ids,
            pending_role_obligation_ids=obligation_projection.pending_role_obligation_ids,
            reason=obligation_projection.reason,
        )

    if not active_obligation_id and legacy.active_subgoal_id:
        return _comparison(
            ObligationProgressShadowClassification.SUBGOAL_WITHOUT_OBLIGATION,
            legacy,
            active_obligation_id,
            ready_obligation_ids,
            satisfied_obligation_ids,
            pending_role_obligation_ids=obligation_projection.pending_role_obligation_ids,
            divergent_subgoal_ids=(legacy.active_subgoal_id,),
            reason="active subgoal has no canonical obligation mapping",
        )

    if obligation_projection.status == "role_pending":
        classification = (
            ObligationProgressShadowClassification.LEGACY_ACTIVE_NON_PROGRESS_PREDICATE
            if active_obligation_id
            in set(obligation_projection.pending_role_obligation_ids)
            else ObligationProgressShadowClassification.ROLE_PENDING
        )
        return _comparison(
            classification,
            legacy,
            active_obligation_id,
            ready_obligation_ids,
            satisfied_obligation_ids,
            pending_role_obligation_ids=obligation_projection.pending_role_obligation_ids,
            reason=obligation_projection.reason,
        )

    known_obligation_ids = {item[1] for item in legacy.subgoal_obligation_ids}
    missing_from_taskplan = tuple(
        item for item in ready_obligation_ids if item not in known_obligation_ids
    )
    if missing_from_taskplan:
        return _comparison(
            ObligationProgressShadowClassification.OBLIGATION_READY_WITHOUT_SUBGOAL,
            legacy,
            active_obligation_id,
            ready_obligation_ids,
            satisfied_obligation_ids,
            divergent_obligation_ids=missing_from_taskplan,
            reason="ready obligation has no legacy TaskPlan subgoal",
        )

    if (
        active_obligation_id
        and ready_obligation_ids
        and active_obligation_id not in set(ready_obligation_ids)
    ):
        return _comparison(
            ObligationProgressShadowClassification.DEPENDENCY_DIVERGENCE,
            legacy,
            active_obligation_id,
            ready_obligation_ids,
            satisfied_obligation_ids,
            divergent_subgoal_ids=(legacy.active_subgoal_id,),
            divergent_obligation_ids=ready_obligation_ids,
            reason="legacy active subgoal is not ready in canonical graph",
        )

    return _comparison(
        ObligationProgressShadowClassification.ALIGNED,
        legacy,
        active_obligation_id,
        ready_obligation_ids,
        satisfied_obligation_ids,
    )


def _comparison(
    classification: ObligationProgressShadowClassification,
    legacy: TaskPlanShadowProjection,
    active_obligation_id: str,
    ready_obligation_ids: tuple[str, ...],
    satisfied_obligation_ids: tuple[str, ...],
    *,
    pending_role_obligation_ids: tuple[str, ...] = (),
    divergent_subgoal_ids: tuple[str, ...] = (),
    divergent_obligation_ids: tuple[str, ...] = (),
    reason: str = "",
) -> ObligationProgressShadowComparison:
    return ObligationProgressShadowComparison(
        classification=classification,
        active_subgoal_id=legacy.active_subgoal_id,
        active_subgoal_obligation_id=active_obligation_id,
        ready_subgoal_ids=legacy.ready_subgoal_ids,
        completed_subgoal_ids=legacy.completed_subgoal_ids,
        ready_obligation_ids=ready_obligation_ids,
        satisfied_obligation_ids=satisfied_obligation_ids,
        pending_role_obligation_ids=pending_role_obligation_ids,
        divergent_subgoal_ids=divergent_subgoal_ids,
        divergent_obligation_ids=divergent_obligation_ids,
        reason=reason,
    )


def _require_nonblank(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be nonblank")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    for value in values:
        _require_nonblank(name, value)
    _require_unique(name, values)


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
