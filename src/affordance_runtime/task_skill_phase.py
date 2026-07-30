"""Coordinator-facing TaskSkill selection seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable

from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.model_port import ProviderModelError as ProviderModelError
from affordance_runtime.planner_compatibility import (
    PlannerCompatibilityPort,
)
from affordance_runtime.planner_compatibility import (
    propose_with_runtime_projection as _propose,
)
from affordance_runtime.planning import (
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime, TaskSkillRuntimeDecision
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class TaskSkillPhaseFailure:
    reason: str


@dataclass(frozen=True)
class TaskSkillPhaseResult:
    parent: TraceNode
    decision: PlannerDecision | None = None
    skill_step_id: str = ""
    failure: TaskSkillPhaseFailure | None = None


class TaskSkillPhase:
    """Select a TaskSkill proposal or delegate to the standard planner."""

    def select(
        self,
        *,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        planner: PlannerCompatibilityPort,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        trace: TraceDag,
        parent: TraceNode,
        runtime_profile_digest: str,
    ) -> TaskSkillPhaseResult:
        if task_skill_runtime is None or envelope.task_spec is None:
            return TaskSkillPhaseResult(
                parent=parent,
                decision=resolve_planner_decision(
                    _propose(planner, envelope=envelope, state=state, snapshot=snapshot)
                ),
            )

        try:
            skill_decision = task_skill_runtime.expose(
                envelope.task_spec,
                state,
                snapshot,
            )
        except Exception as exc:
            reason = f"TaskSkill runtime error: {type(exc).__name__}: {exc}"[:500]
            task_skill_runtime.fallthrough(state, reason)
            skill_decision = TaskSkillRuntimeDecision(
                attempted=True,
                reason=reason,
            )

        parent = trace.add(
            "TaskSkillSelectionEvaluated",
            {
                "state": state.phase,
                "matched": skill_decision.payload is not None,
                "newly_activated": skill_decision.newly_activated,
                "attempted": skill_decision.attempted,
                "reason": skill_decision.reason,
                "profile_digest": runtime_profile_digest,
            },
            parents=[parent.id],
        )
        skill_progress = task_skill_progress(task_skill_runtime, state)
        if (
            skill_decision.attempted
            and skill_decision.reason.startswith("TaskSkill runtime error:")
        ):
            return TaskSkillPhaseResult(
                parent=parent,
                failure=TaskSkillPhaseFailure(skill_decision.reason),
            )

        if skill_decision.newly_activated and skill_decision.payload is not None:
            parent = trace.add(
                "TaskSkillActivated",
                {
                    "state": state.phase,
                    "skill_id": skill_decision.payload.skill_id,
                    "version": skill_decision.payload.version,
                    "trigger": skill_decision.payload.trigger.task_family,
                },
                parents=[parent.id],
            )

        exposure = skill_decision.exposure
        if exposure is not None and exposure.proposal is not None:
            skill_payload = skill_decision.payload
            if skill_payload is None:
                raise ValueError("TaskSkill exposure is missing its payload")
            skill_step_id = exposure.step_id
            decision = PlannerDecision(
                proposal=exposure.proposal,
                proposal_provenance=PlannerProposalProvenance(
                    source=PlannerProposalSource.ACCEPTED_SKILL,
                    producer_id=skill_payload.skill_id,
                    version=skill_payload.version,
                    evidence_refs=tuple(skill_progress.evidence)
                    if skill_progress
                    else (),
                ),
                reason="accepted TaskSkill exposed one semantic step",
            )
            parent = trace.add(
                "TaskSkillStepExposed",
                {
                    "state": state.phase,
                    "skill_id": skill_payload.skill_id,
                    "version": skill_payload.version,
                    "step_id": skill_step_id,
                    "action_kind": exposure.proposal.action_kind.value,
                    "semantic_target_id": exposure.proposal.target_affordance_id,
                    "semantic_destination_id": (
                        exposure.proposal.destination_affordance_id
                    ),
                },
                parents=[parent.id],
            )
            return TaskSkillPhaseResult(
                parent=parent,
                decision=decision,
                skill_step_id=skill_step_id,
            )

        if skill_decision.attempted and skill_decision.reason:
            parent = trace_task_skill_fallthrough(
                trace,
                parent,
                state,
                skill_decision.reason,
                progress=skill_progress,
            )
        return TaskSkillPhaseResult(
            parent=parent,
            decision=resolve_planner_decision(
                _propose(planner, envelope=envelope, state=state, snapshot=snapshot)
            ),
        )


def task_skill_progress(
    runtime: object | None,
    state: StateKernel,
) -> TaskSkillRunState | None:
    progress_for = getattr(runtime, "progress_for", None)
    if not callable(progress_for):
        return None
    progress = progress_for(state)
    return progress if isinstance(progress, TaskSkillRunState) else None


def trace_task_skill_fallthrough(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
    reason: str,
    *,
    progress: TaskSkillRunState | None = None,
    step_id: str = "",
) -> TraceNode:
    return trace.add(
        "TaskSkillFellThrough",
        {
            "state": state.phase,
            "skill_id": progress.skill_id if progress else "",
            "version": progress.version if progress else "",
            "step_id": step_id,
            "reason": reason,
            "preserved_completed_step_ids": (
                list(progress.completed_step_ids) if progress else []
            ),
            "preserved_evidence": list(progress.evidence) if progress else [],
            "fallback": "system_2",
        },
        parents=[parent.id],
    )


def resolve_planner_decision(
    value: PlannerDecision | Awaitable[PlannerDecision],
) -> PlannerDecision:
    if isinstance(value, PlannerDecision):
        return value
    return resolve_awaitable(_await_planner_decision(value))


async def _await_planner_decision(
    value: Awaitable[PlannerDecision],
) -> PlannerDecision:
    return await value
