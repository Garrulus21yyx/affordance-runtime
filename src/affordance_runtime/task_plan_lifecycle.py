"""Internal task-plan lifecycle collaborator for the serial Coordinator.

The lifecycle is deliberately stateless.  It prepares and validates plan
transitions while the Coordinator remains the sole control-flow authority and
``StateKernel`` remains the single mutable run state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Awaitable, Mapping, Protocol, cast

from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.simplified_runtime_contracts import (
    StepActivityStatus,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_contracts import (
    InitialTaskPlanRequest,
    PlanCandidate,
    TaskPlan,
    TaskPlanAuthority,
    TaskPlanDecision,
    TaskPlanDecisionStatus,
    TaskPlanRevisionRequest,
    TaskPlanRevisionTrigger,
)
from affordance_runtime.task_planner import (
    CriteriaEvidenceLedgerEntry,
    PlanningAffordanceState,
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    TaskPlanningBudgetSummary,
    TaskPlanningContext,
    TaskPlanningFailureSummary,
    TaskPlanningRecoverySummary,
)
from affordance_runtime.unified_observation import UnifiedObservation


class TaskPlanBudgetLimits(Protocol):
    """Structural view of the run limits used in planning context."""

    @property
    def max_steps(self) -> int: ...

    @property
    def max_observations(self) -> int: ...

    @property
    def max_replans(self) -> int: ...

    @property
    def max_recoveries(self) -> int: ...

    @property
    def max_effectful_actions(self) -> int: ...


class TaskPlannerPort(Protocol):
    def generate_candidate(
        self, context: TaskPlanningContext
    ) -> PlanCandidate | Awaitable[PlanCandidate]: ...


@dataclass(frozen=True)
class TaskPlanTransition:
    """A proposed immutable plan transition, before state mutation."""

    context: TaskPlanningContext
    plan: TaskPlan
    decision: TaskPlanDecision
    previous_plan: TaskPlan | None = None


class TaskPlanReplacementReason(StrEnum):
    STEP_ACTION_BUDGET_EXHAUSTED = "step_action_budget_exhausted"
    ACTIVE_STEP_ACTION_FAMILY_UNAVAILABLE = "active_step_action_family_unavailable"
    ACTIVE_STEP_OUTCOME_ALREADY_SATISFIED = (
        "active_step_outcome_already_satisfied"
    )
    ACTIVE_STEP_OUTCOME_STATE_UNSUPPORTED = (
        "active_step_outcome_state_unsupported"
    )


@dataclass(frozen=True)
class TaskPlanReplacementDecision:
    """Authority-free lifecycle decision consumed by the state committer."""

    reason: TaskPlanReplacementReason | None = None
    step_id: str = ""
    unavailable_action_family: str = ""

    @property
    def required(self) -> bool:
        return self.reason is not None


@dataclass(frozen=True)
class TaskPlanLifecycle:
    """Prepare task-plan transitions without owning mutable run state."""

    planner: TaskPlannerPort
    authority: TaskPlanAuthority = field(default_factory=TaskPlanAuthority)

    def propose_initial(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
    ) -> TaskPlanTransition:
        context = self.build_context(task_spec, state, snapshot, budget, reason="initial")
        candidate = _resolve_plan_candidate(self.planner.generate_candidate(context))
        decision = self.authority.admit_initial(
                InitialTaskPlanRequest(
                    task_spec_identity=task_spec.identity,
                    task_revision=task_spec.revision,
                    evaluated_at_state_version=state.version,
                    objective=task_spec.objective,
                    operation_class=task_spec.operation_class,
                    observation_refs=(snapshot.epoch_id,),
                    remaining_budget_steps=budget.max_steps,
                    allowed_requirement_ids=tuple(
                        item.requirement_id for item in task_spec.requirements
                    ),
                    allowed_effect_ids=task_spec.allowed_effect_refs,
                    task_id=task_spec.task_id,
                ),
                candidate,
            )
        if decision.status != TaskPlanDecisionStatus.ACCEPTED or decision.plan is None:
            raise ValueError("initial TaskPlan candidate was not accepted")
        plan = decision.plan
        return TaskPlanTransition(context=context, plan=plan, decision=decision)

    def propose_replacement(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
        *,
        reason: str,
    ) -> TaskPlanTransition:
        previous_plan = state.task_plan
        if previous_plan is None or state.task_progress is None:
            raise ValueError("cannot replan without an active TaskPlan")
        context = self.build_context(task_spec, state, snapshot, budget, reason=reason)
        candidate = _resolve_plan_candidate(self.planner.generate_candidate(context))
        decision = self.authority.admit_revision(
                TaskPlanRevisionRequest(
                    task_spec_identity=task_spec.identity,
                    task_revision=task_spec.revision,
                    evaluated_at_state_version=state.version,
                    previous_plan=_plan_view(previous_plan, task_spec, state),
                    previous_progress=_progress_view(previous_plan, state),
                    trigger=TaskPlanRevisionTrigger(
                        kind=_revision_trigger_kind(reason),
                        reason_code=reason,
                        affected_step_id=state.task_progress.active_step_id,
                    ),
                    operation_class=task_spec.operation_class,
                    observation_refs=(snapshot.epoch_id,),
                    remaining_budget_steps=budget.max_steps,
                    allowed_requirement_ids=tuple(
                        item.requirement_id for item in task_spec.requirements
                    ),
                    allowed_effect_ids=task_spec.allowed_effect_refs,
                    task_id=task_spec.task_id,
                ),
                candidate,
            )
        if decision.status != TaskPlanDecisionStatus.ACCEPTED or decision.plan is None:
            raise ValueError("replacement TaskPlan candidate was not accepted")
        plan = decision.plan
        return TaskPlanTransition(
            context=context,
            plan=plan,
            decision=decision,
            previous_plan=previous_plan,
        )

    @staticmethod
    def should_replan(state: StateKernel) -> bool:
        return (
            state.task_plan is not None
            and state.task_progress is not None
            and state.task_progress.action_budget_exhausted(state.task_plan)
        )

    def evaluate_replacement(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
    ) -> TaskPlanReplacementDecision:
        """Decide whether the current plan needs replacement without mutation."""

        if state.task_plan is None or state.task_progress is None:
            return TaskPlanReplacementDecision()
        if self.should_replan(state):
            return TaskPlanReplacementDecision(
                reason=TaskPlanReplacementReason.STEP_ACTION_BUDGET_EXHAUSTED,
                step_id=state.task_progress.active_step_id,
            )
        return TaskPlanReplacementDecision()

    @staticmethod
    def completed(state: StateKernel) -> bool:
        if state.task_plan is None or state.task_progress is None:
            return False
        completed = set(state.task_progress.completed_step_ids)
        return all(item.step_id in completed for item in state.task_plan.steps)

    @staticmethod
    def active_step_spec(state: StateKernel) -> StepSpec | None:
        if state.task_plan is None or state.task_progress is None:
            return None
        active_id = state.task_progress.active_step_id
        return state.task_plan.step(active_id)

    @classmethod
    def active_step_for_perception(cls, state: StateKernel) -> StepSpec | str | None:
        if state.task_plan is None or state.task_progress is None:
            return None
        return cls.active_step_spec(state)

    @staticmethod
    def build_context(
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
        *,
        reason: str,
    ) -> TaskPlanningContext:
        plan = state.task_plan
        progress = state.task_progress
        affordances = tuple(
            PlanningAffordanceSummary(
                semantic_target_id=item.target_id,
                role=item.role,
                label=item.label,
                supported_actions=item.supported_actions,
                current_state=_planning_affordance_state(item.state),
            )
            for item in snapshot.targets[:64]
        )
        failures: tuple[TaskPlanningFailureSummary, ...] = ()
        latest = state.latest_verification
        if latest is not None and not latest.passed:
            failures = (
                TaskPlanningFailureSummary(
                    phase=state.phase,
                    error_code=latest.status.value,
                    reason=latest.reason[:500],
                    step_id=progress.active_step_id if progress is not None else "",
                    environment_revision=snapshot.environment_revision,
                ),
            )
        elif reason == "step_action_budget_exhausted":
            failures = (
                TaskPlanningFailureSummary(
                    phase="task_planning",
                    error_code="step_action_budget_exhausted",
                    reason="active step exhausted its action budget without matched criteria evidence",
                    step_id=progress.active_step_id if progress is not None else "",
                    environment_revision=snapshot.environment_revision,
                ),
            )
        failure = state.current_failure
        recovery_decision = state.current_recovery_decision
        recovery_summary = (
            TaskPlanningRecoverySummary(
                incident_id=failure.failure_id,
                root_error_code=failure.error_code,
                terminal_outcome=(
                    recovery_decision.reentry_phase.value
                    if recovery_decision is not None
                    else ""
                ),
                findings=(failure.failure_class.value,),
                attempted_actions=(
                    (recovery_decision.kind.value,)
                    if recovery_decision is not None
                    else ()
                ),
            )
            if failure is not None
            else None
        )
        return TaskPlanningContext(
            task_spec=task_spec,
            state_version=state.version,
            reason=reason,
            current_plan_id=plan.plan_id if plan is not None else "",
            current_plan_version=plan.plan_version if plan is not None else 0,
            environment=PlanningEnvironmentSummary(
                environment_revision=snapshot.environment_revision,
                snapshot_id=snapshot.epoch_id,
                page_revision=snapshot.page_revision,
                url=str(snapshot.metadata.get("url") or ""),
                affordances=affordances,
            ),
            active_step_id=progress.active_step_id if progress is not None else "",
            completed_step_ids=tuple(progress.completed_step_ids) if progress is not None else (),
            failed_step_ids=tuple(progress.failed_step_ids) if progress is not None else (),
            criteria_evidence_ledger=(
                tuple(
                    CriteriaEvidenceLedgerEntry(
                        step_id=record.step_id,
                        evidence_ids=record.evidence_refs,
                    )
                    for record in progress.verified_steps
                )
                if progress is not None
                else ()
            ),
            failures=failures,
            recovery_summary=recovery_summary,
            disproved_assumptions=((state.current_disproved_assumption,) if state.current_disproved_assumption else ()),
            remaining_budget=TaskPlanningBudgetSummary(
                steps_remaining=max(0, budget.max_steps - state.step_count),
                observations_remaining=max(0, budget.max_observations - state.observation_count),
                replans_remaining=max(
                    0,
                    budget.max_replans - (progress.replan_count if progress is not None else 0),
                ),
                recoveries_remaining=max(0, budget.max_recoveries - state.recovery_count),
                effectful_actions_remaining=max(
                    0,
                    budget.max_effectful_actions - state.effectful_action_count,
                ),
            ),
        )


def _resolve_plan_candidate(value: PlanCandidate | Awaitable[PlanCandidate]) -> PlanCandidate:
    if not hasattr(value, "__await__"):
        return value
    return cast(PlanCandidate, resolve_awaitable(value))


def _revision_trigger_kind(reason: str) -> str:
    if "budget" in reason:
        return "action_budget_exhausted"
    if "verif" in reason:
        return "criterion_unverifiable"
    if "assumption" in reason:
        return "plan_assumption_invalid"
    if "requirement" in reason:
        return "task_requirements_changed"
    return "step_unexecutable"


def _plan_view(plan: TaskPlan, task_spec: TaskSpec, state: StateKernel) -> TaskPlanView:
    active = state.task_progress.active_step_id if state.task_progress is not None else None
    return TaskPlanView(
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        steps=plan.steps,
        active_step_id=active or None,
    )


def _progress_view(plan: TaskPlan, state: StateKernel) -> StepProgressView:
    progress = state.task_progress
    if progress is None:
        raise ValueError("replacement requires task progress")
    completed = tuple(progress.completed_step_ids)
    failed = tuple(progress.failed_step_ids)
    ready = tuple(progress.ready_step_ids(plan))
    activity = (
        StepActivityStatus.ACTIVE
        if progress.active_step_id
        else StepActivityStatus.READY_NOT_ACTIVATED
        if ready
        else StepActivityStatus.COMPLETED
    )
    return StepProgressView(
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        active_step_id=progress.active_step_id or None,
        activity_status=activity,
        completed_step_ids=completed,
        failed_step_ids=failed,
        ready_step_ids=ready,
        evidence_by_step_id=tuple(
            (step_id, progress.evidence_for_step(step_id))
            for step_id in completed
        ),
    )


def _planning_affordance_state(
    state: Mapping[str, object],
) -> PlanningAffordanceState:
    """Project only bounded predicate state; never expose handles or passwords."""

    def boolean(name: str) -> bool | None:
        value = state.get(name)
        return value if isinstance(value, bool) else None

    input_type = str(state.get("input_type") or "").casefold()
    raw_value = state.get("control_value")
    control_value = (
        raw_value[:240]
        if isinstance(raw_value, str) and input_type != "password"
        else None
    )
    raw_options = state.get("selected_options")
    selected_options = (
        tuple(item[:160] for item in raw_options[:20] if isinstance(item, str))
        if isinstance(raw_options, (list, tuple))
        else ()
    )
    selected = boolean("selected")
    if selected is None:
        aria_selected = state.get("aria_selected")
        if isinstance(aria_selected, str) and aria_selected.casefold() in {
            "true",
            "false",
        }:
            selected = aria_selected.casefold() == "true"
    return PlanningAffordanceState(
        visible=boolean("visible"),
        enabled=boolean("enabled"),
        control_value=control_value,
        checked=boolean("checked"),
        selected=selected,
        selected_options=selected_options,
        expanded=boolean("expanded"),
        element_tag=str(state.get("element_tag") or "")[:40],
    )
