"""Canonical TaskSpec and TaskPlan preparation for the target AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.semantic_audit import SemanticAudit, SemanticAuditStatus
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task_intake import CompilationStatus, UserRequest
from affordance_runtime.task_plan_contracts import (
    InitialTaskPlanRequest,
    TaskPlan,
    TaskPlanAuthority,
    TaskPlanDecisionStatus,
    project_task_requirements,
)
from affordance_runtime.task_planner import (
    PlanningAffordanceState,
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    StrictTaskPlanner,
    TaskPlanningBudgetSummary,
    TaskPlanningRequest,
)
from affordance_runtime.task_spec_authority import AdmittedTaskSpec, TaskSpecAuthority
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class PreparedAgentTask:
    admitted_task: AdmittedTaskSpec
    plan: TaskPlan


class AgentTaskPlanPreparerPort(Protocol):
    async def prepare(self, task: TaskGoal, observation: WorldObservation) -> PreparedAgentTask: ...


@dataclass
class CanonicalAgentTaskPlanPreparer:
    intent_compiler: LLMIntentCompiler
    task_planner: StrictTaskPlanner
    source_builder: SourceEnvelopeBuilder = field(default_factory=SourceEnvelopeBuilder)
    semantic_audit: SemanticAudit = field(default_factory=SemanticAudit)
    task_spec_authority: TaskSpecAuthority = field(default_factory=TaskSpecAuthority)
    task_plan_authority: TaskPlanAuthority = field(default_factory=TaskPlanAuthority)

    async def prepare(self, task: TaskGoal, observation: WorldObservation) -> PreparedAgentTask:
        request = UserRequest(
            request_id=task.task_id,
            raw_text=task.instruction,
            channel="target-agent-loop",
        )
        envelope = self.source_builder.build(request)
        proposal = await self.intent_compiler.propose(request, envelope)
        audit = self.semantic_audit.evaluate(envelope, proposal)
        if audit.status is not SemanticAuditStatus.PASS:
            raise ValueError("target AgentLoop semantic audit rejected the intent proposal")
        admission = self.task_spec_authority.admit(request, envelope, proposal, task_id=task.task_id)
        if admission.status is not CompilationStatus.READY or admission.admitted_task is None:
            raise ValueError("target AgentLoop TaskSpec admission failed")
        task_spec = admission.admitted_task.task_spec
        planning_request = TaskPlanningRequest(
            task_spec=task_spec,
            state_version=0,
            reason="initial",
            environment=PlanningEnvironmentSummary(
                environment_revision=observation.observation_id,
                snapshot_id=observation.observation_id,
                page_revision=observation.observation_id,
                affordances=tuple(
                    PlanningAffordanceSummary(
                        semantic_target_id=item.target_id,
                        role=item.role,
                        label=item.label,
                        supported_actions=tuple(
                            sorted(
                                {
                                    binding.semantic_action
                                    for binding in observation.bindings
                                    if binding.target_id == item.target_id
                                }
                            )
                        ),
                        current_state=_planning_state(item.state),
                    )
                    for item in observation.targets[:64]
                ),
            ),
            remaining_budget=TaskPlanningBudgetSummary(
                steps_remaining=task.loop_budget.max_turns,
                observations_remaining=task.loop_budget.max_observations,
                replans_remaining=0,
                recoveries_remaining=0,
                effectful_actions_remaining=task.loop_budget.max_turns,
            ),
        )
        plan_proposal = await self.task_planner.propose(planning_request)
        decision = self.task_plan_authority.admit_initial(
            InitialTaskPlanRequest(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                evaluated_at_state_version=0,
                objective=task_spec.objective,
                observation_refs=(observation.observation_id,),
                remaining_budget_steps=task.loop_budget.max_turns,
                allowed_requirement_ids=tuple(item.requirement_id for item in task_spec.requirements),
                allowed_effect_ids=task_spec.allowed_effect_refs,
                operation_class=task_spec.operation_class,
                task_id=task_spec.task_id,
                requirement_projections=project_task_requirements(task_spec),
            ),
            plan_proposal,
        )
        if decision.status is not TaskPlanDecisionStatus.ACCEPTED or decision.plan is None:
            raise ValueError("target AgentLoop TaskPlan admission failed")
        if not all(step.execution is not None for step in decision.plan.steps):
            raise ValueError("target AgentLoop TaskPlan omitted executable step semantics")
        return PreparedAgentTask(admission.admitted_task, decision.plan)


def _planning_state(state) -> PlanningAffordanceState:
    return PlanningAffordanceState(
        visible=_optional_bool(state.get("visible")),
        enabled=_optional_bool(state.get("enabled")),
        control_value=_optional_string(state.get("value")),
        checked=_optional_bool(state.get("checked")),
        selected=_optional_bool(state.get("selected")),
        selected_options=tuple(str(item) for item in state.get("selected_options", ())[:20])
        if isinstance(state.get("selected_options"), tuple | list)
        else (),
        expanded=_optional_bool(state.get("expanded")),
        element_tag=_optional_string(state.get("element_tag"), limit=40) or "",
    )


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_string(value: object, *, limit: int = 240) -> str | None:
    return value[:limit] if isinstance(value, str) else None
