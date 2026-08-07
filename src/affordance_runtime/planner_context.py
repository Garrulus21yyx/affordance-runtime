"""One-way compatibility context projected only from immutable PlanningRequest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from affordance_runtime.planning_request import (
    PlanningRequest,
    thaw_request_mapping,
    thaw_request_value,
)


class AffordanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    surface: str
    role: str
    label: str
    action: str
    supported_actions: tuple[str, ...] = ()
    confidence: float
    state: dict[str, Any]


class PlannerContext(BaseModel):
    """Historical provider payload, never a Runtime authority object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_spec: dict[str, Any]
    active_subgoal: str
    active_subgoal_action_family: str = ""
    observed_text: str
    affordances: tuple[AffordanceSummary, ...]
    permitted_action_kinds: tuple[str, ...]
    selected_artifact_refs: tuple[str, ...]
    granted_capabilities: tuple[str, ...]
    approval_handling: str
    remaining_budgets: dict[str, int]
    pending_evidence_obligations: tuple[str, ...]
    latest_outcome: dict[str, Any]
    recent_proposals: tuple[dict[str, Any], ...]
    verified_effects: tuple[str, ...]
    satisfied_action_targets: dict[str, tuple[str, ...]]
    recovery_summary: dict[str, Any]
    accepted_knowledge: tuple[str, ...]
    task_revision: int
    state_version: int
    snapshot_id: str


@dataclass(frozen=True)
class PlannerLimits:
    max_steps: int = 20
    max_observations: int = 30
    max_recoveries: int = 3
    max_effectful_actions: int = 5
    max_affordances: int = 80
    max_artifact_refs: int = 3
    max_accepted_knowledge: int = 3


@dataclass(frozen=True)
class PlannerContextBuilder:
    """P5-expiring adapter for the historical provider profile."""

    limits: PlannerLimits = PlannerLimits()
    accepted_knowledge: tuple[str, ...] = ()
    allow_finish: bool = True

    def build(self, request: PlanningRequest) -> PlannerContext:
        latest_outcome = thaw_request_mapping(request.latest_outcome)
        recent_proposals = tuple(thaw_request_mapping(item) for item in request.recent_proposals)
        recovery_summary = (
            {
                "kind": request.recovery.kind,
                "reason_code": request.recovery.reason_code,
                "message": request.recovery.message,
                "attempted_changes": list(request.recovery.attempted_changes),
            }
            if request.recovery is not None
            else {}
        )
        active_subgoal = (
            request.step.active_step.objective
            if request.step.active_step is not None
            else request.step.compatibility_active_step_objective or request.task.objective
        )
        return PlannerContext(
            task_spec=_task_summary_from_request(request),
            active_subgoal=active_subgoal,
            active_subgoal_action_family=request.step.active_step_action_family,
            observed_text=request.observation.observed_text,
            affordances=tuple(
                AffordanceSummary(
                    id=item.target_id,
                    surface=item.surface,
                    role=item.role,
                    label=item.label,
                    action=next(
                        (action for action in item.supported_actions if action != "focus"),
                        item.supported_actions[0] if item.supported_actions else "",
                    ),
                    supported_actions=item.supported_actions,
                    confidence=item.confidence if item.confidence is not None else 0.0,
                    state={key: thaw_request_value(value) for key, value in item.state},
                )
                for item in request.observation.affordances
            ),
            permitted_action_kinds=request.permitted_action_kinds,
            selected_artifact_refs=request.observation.artifact_refs,
            granted_capabilities=request.task.capabilities,
            approval_handling="coordinator_managed",
            remaining_budgets={
                "steps": request.remaining_budget.steps,
                "observations": request.remaining_budget.observations,
                "recoveries": request.remaining_budget.recoveries,
                "effectful_actions": request.remaining_budget.effectful_actions,
            },
            pending_evidence_obligations=request.pending_evidence_obligations,
            latest_outcome=latest_outcome,
            recent_proposals=recent_proposals,
            verified_effects=request.verified_effects,
            satisfied_action_targets=dict(request.satisfied_action_targets),
            recovery_summary=recovery_summary,
            accepted_knowledge=self.accepted_knowledge[-self.limits.max_accepted_knowledge :],
            task_revision=request.identity.task_revision,
            state_version=request.identity.evaluated_at_state_version,
            snapshot_id=request.identity.snapshot_id,
        )


def _task_summary_from_request(request: PlanningRequest) -> dict[str, Any]:
    summary = thaw_request_mapping(request.task.task_summary)
    if summary:
        return summary
    return {
        "revision": request.task.task_revision,
        "objective": request.task.objective,
        "constraints": list(request.task.constraints),
        "requested_capabilities": list(request.task.capabilities),
    }
