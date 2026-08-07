"""Verified TaskPlan progress facts independent of plan ownership."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.runtime_evidence import (
    DurableEvidenceStore,
    RecentActionOutcomeEvidence,
    RecentActionOutcomeEvidenceIndex,
)
from affordance_runtime.task_plan_contracts import TaskPlan


@dataclass(frozen=True)
class VerifiedStepRecord:
    plan_id: str
    step_id: str
    step_digest: str
    verified_criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    completed_at_state_version: int


@dataclass
class TaskProgress:
    """Verified execution facts that survive replacement independently of a plan graph."""

    active_step_id: str = ""
    verified_steps: list[VerifiedStepRecord] = field(default_factory=list)
    failed_step_ids: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)
    bindings: dict[str, object] = field(default_factory=dict)
    recent_action_outcomes: RecentActionOutcomeEvidenceIndex = field(
        default_factory=RecentActionOutcomeEvidenceIndex
    )
    durable_evidence: DurableEvidenceStore = field(default_factory=DurableEvidenceStore)
    action_count_by_step: dict[str, int] = field(default_factory=dict)
    replan_count: int = 0

    def record_action_outcome(self, outcome: object) -> None:
        self.recent_action_outcomes.append(
            RecentActionOutcomeEvidence.from_action_outcome(outcome)
        )

    @property
    def completed_step_ids(self) -> tuple[str, ...]:
        return tuple(record.step_id for record in self.verified_steps)

    def evidence_for_step(self, step_id: str) -> tuple[str, ...]:
        record = next(
            (item for item in reversed(self.verified_steps) if item.step_id == step_id),
            None,
        )
        return record.evidence_refs if record is not None else ()

    def ready_step_ids(self, plan: TaskPlan) -> tuple[str, ...]:
        completed = set(self.completed_step_ids)
        unavailable = completed | set(self.failed_step_ids)
        return tuple(
            step.step_id
            for step in plan.steps
            if step.step_id not in unavailable
            and set(step.depends_on).issubset(completed)
        )

    def activate_next(self, plan: TaskPlan) -> str:
        if self.active_step_id:
            return self.active_step_id
        ready = self.ready_step_ids(plan)
        self.active_step_id = ready[0] if ready else ""
        return self.active_step_id

    def complete(
        self,
        *,
        plan: TaskPlan,
        step_id: str,
        criterion_ids: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        state_version: int,
    ) -> None:
        import hashlib

        step = plan.step(step_id)
        if step is None:
            raise ValueError("unknown TaskPlan step")
        digest = "sha256:" + hashlib.sha256(repr(step).encode()).hexdigest()
        self.verified_steps = [item for item in self.verified_steps if item.step_id != step_id]
        self.verified_steps.append(
            VerifiedStepRecord(
                plan_id=plan.plan_id,
                step_id=step_id,
                step_digest=digest,
                verified_criterion_ids=criterion_ids,
                evidence_refs=tuple(dict.fromkeys(evidence_refs)),
                completed_at_state_version=state_version,
            )
        )
        if self.active_step_id == step_id:
            self.active_step_id = ""

    def record_action(self, step_id: str) -> None:
        self.action_count_by_step[step_id] = self.action_count_by_step.get(step_id, 0) + 1

    def action_budget_exhausted(self, plan: TaskPlan) -> bool:
        step = plan.step(self.active_step_id)
        return step is not None and self.action_count_by_step.get(step.step_id, 0) >= step.max_actions
