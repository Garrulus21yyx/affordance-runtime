"""Internal task-plan lifecycle collaborator for the serial Coordinator.

The lifecycle is deliberately stateless.  It prepares and validates plan
transitions while the Coordinator remains the sole control-flow authority and
``StateKernel`` remains the single mutable run state.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Awaitable, Mapping, Protocol, cast

from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.simplified_step_projection import (
    LegacyStepProjectionStatus,
    project_state_legacy_task_plan_to_step_view,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_contracts import (
    InitialTaskPlanRequest,
    PlanCandidate,
    TaskPlanAuthority,
    TaskPlanDecisionStatus,
    TaskPlanRevisionRequest,
    TaskPlanRevisionTrigger,
)
from affordance_runtime.task_planning import (
    CriteriaEvidenceLedgerEntry,
    PlanningAffordanceState,
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    SubgoalSpec,
    TaskPlan,
    TaskPlannerPort,
    TaskPlanningBudgetSummary,
    TaskPlanningContext,
    TaskPlanningFailureSummary,
    TaskPlanningRecoverySummary,
    TaskPlanValidationReport,
    TaskPlanValidator,
    task_plan_entry_feasibility_issue,
    task_plan_entry_state_issue,
    task_plan_entry_state_support_issue,
)


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


@dataclass(frozen=True)
class TaskPlanTransition:
    """A proposed immutable plan transition, before state mutation."""

    context: TaskPlanningContext
    plan: TaskPlan
    validation: TaskPlanValidationReport
    previous_plan: TaskPlan | None = None


class TaskPlanReplacementReason(StrEnum):
    SUBGOAL_ACTION_BUDGET_EXHAUSTED = "subgoal_action_budget_exhausted"
    ACTIVE_SUBGOAL_ACTION_FAMILY_UNAVAILABLE = "active_subgoal_action_family_unavailable"
    ACTIVE_SUBGOAL_OUTCOME_ALREADY_SATISFIED = (
        "active_subgoal_outcome_already_satisfied"
    )
    ACTIVE_SUBGOAL_OUTCOME_STATE_UNSUPPORTED = (
        "active_subgoal_outcome_state_unsupported"
    )


@dataclass(frozen=True)
class TaskPlanReplacementDecision:
    """Authority-free lifecycle decision consumed by the state committer."""

    reason: TaskPlanReplacementReason | None = None
    subgoal_id: str = ""
    unavailable_action_family: str = ""

    @property
    def required(self) -> bool:
        return self.reason is not None


@dataclass(frozen=True)
class TaskPlanLifecycle:
    """Prepare task-plan transitions without owning mutable run state."""

    planner: TaskPlannerPort
    validator: TaskPlanValidator = field(default_factory=TaskPlanValidator)
    authority: TaskPlanAuthority = field(default_factory=TaskPlanAuthority)

    def propose_initial(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        budget: TaskPlanBudgetLimits,
    ) -> TaskPlanTransition:
        context = self.build_context(task_spec, state, snapshot, budget, reason="initial")
        candidate_value = _initial_plan_candidate(self.planner, context)
        if candidate_value is None:
            plan = _legacy_initial_task_plan(self.planner, context)
        else:
            candidate = _resolve_plan_candidate(candidate_value)
            decision = self.authority.admit_initial(
                InitialTaskPlanRequest(
                    task_spec_identity=task_spec.identity,
                    task_revision=task_spec.revision,
                    evaluated_at_state_version=state.version,
                    objective=task_spec.objective,
                    operation_class=task_spec.operation_class,
                    observation_refs=(snapshot.observation.snapshot_id,),
                    remaining_budget_steps=budget.max_steps,
                    task_id=task_spec.task_id,
                ),
                candidate,
            )
            if decision.status != TaskPlanDecisionStatus.ACCEPTED or decision.plan is None:
                raise ValueError("initial TaskPlan candidate was not accepted")
            plan = decision.plan
        validation = self.validator.validate(
            plan,
            task_spec,
            state_version=state.version,
            planning_context=context,
        )
        return TaskPlanTransition(context=context, plan=plan, validation=validation)

    def propose_replacement(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        budget: TaskPlanBudgetLimits,
        *,
        reason: str,
    ) -> TaskPlanTransition:
        previous_plan = state.task_plan
        if previous_plan is None or state.plan_progress is None:
            raise ValueError("cannot replan without an active TaskPlan")
        context = self.build_context(task_spec, state, snapshot, budget, reason=reason)
        candidate_value = _initial_plan_candidate(self.planner, context)
        if candidate_value is None:
            plan = _resolve_task_plan(self.planner.plan(context))
        else:
            projection = project_state_legacy_task_plan_to_step_view(
                task_spec=task_spec,
                state=state,
            )
            if (
                projection.status != LegacyStepProjectionStatus.PROJECTED
                or projection.task_plan_view is None
                or projection.step_progress_view is None
            ):
                raise ValueError("cannot admit replacement without projected previous plan")
            candidate = _resolve_plan_candidate(candidate_value)
            decision = self.authority.admit_revision(
                TaskPlanRevisionRequest(
                    task_spec_identity=task_spec.identity,
                    task_revision=task_spec.revision,
                    evaluated_at_state_version=state.version,
                    previous_plan=projection.task_plan_view,
                    previous_progress=projection.step_progress_view,
                    trigger=TaskPlanRevisionTrigger(
                        kind=_revision_trigger_kind(reason),
                        reason_code=reason,
                        affected_step_id=state.plan_progress.active_subgoal_id,
                    ),
                    operation_class=task_spec.operation_class,
                    observation_refs=(snapshot.observation.snapshot_id,),
                    remaining_budget_steps=budget.max_steps,
                    task_id=task_spec.task_id,
                ),
                candidate,
            )
            if decision.status != TaskPlanDecisionStatus.ACCEPTED or decision.plan is None:
                raise ValueError("replacement TaskPlan candidate was not accepted")
            plan = decision.plan
        plan = _carry_forward_completed_subgoals(
            plan,
            previous_plan,
            tuple(state.plan_progress.completed_subgoal_ids),
        )
        validation = self.validator.validate(
            plan,
            task_spec,
            state_version=state.version,
            previous_plan=previous_plan,
            planning_context=context,
        )
        return TaskPlanTransition(
            context=context,
            plan=plan,
            validation=validation,
            previous_plan=previous_plan,
        )

    @staticmethod
    def should_replan(state: StateKernel) -> bool:
        return (
            state.task_plan is not None
            and state.plan_progress is not None
            and state.plan_progress.action_budget_exhausted(state.task_plan)
        )

    def evaluate_replacement(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        budget: TaskPlanBudgetLimits,
    ) -> TaskPlanReplacementDecision:
        """Decide whether the current plan needs replacement without mutation."""

        if state.task_plan is None or state.plan_progress is None:
            return TaskPlanReplacementDecision()
        if self.should_replan(state):
            return TaskPlanReplacementDecision(
                reason=TaskPlanReplacementReason.SUBGOAL_ACTION_BUDGET_EXHAUSTED,
                subgoal_id=state.plan_progress.active_subgoal_id,
            )
        context = self.build_context(
            task_spec,
            state,
            snapshot,
            budget,
            reason=TaskPlanReplacementReason.ACTIVE_SUBGOAL_ACTION_FAMILY_UNAVAILABLE.value,
        )
        state_issue = task_plan_entry_state_issue(state.task_plan, context)
        if state_issue is not None:
            return TaskPlanReplacementDecision(
                reason=TaskPlanReplacementReason.ACTIVE_SUBGOAL_OUTCOME_ALREADY_SATISFIED,
                subgoal_id=state_issue.detail,
            )
        support_issue = task_plan_entry_state_support_issue(state.task_plan, context)
        if support_issue is not None:
            return TaskPlanReplacementDecision(
                reason=TaskPlanReplacementReason.ACTIVE_SUBGOAL_OUTCOME_STATE_UNSUPPORTED,
                subgoal_id=support_issue.detail,
            )
        issue = task_plan_entry_feasibility_issue(state.task_plan, context)
        if issue is None:
            return TaskPlanReplacementDecision()
        return TaskPlanReplacementDecision(
            reason=TaskPlanReplacementReason.ACTIVE_SUBGOAL_ACTION_FAMILY_UNAVAILABLE,
            subgoal_id=issue.detail,
            unavailable_action_family=(issue.disallowed_values[0] if issue.disallowed_values else ""),
        )

    @staticmethod
    def completed(state: StateKernel) -> bool:
        if state.task_plan is None or state.plan_progress is None:
            return False
        completed = set(state.plan_progress.completed_subgoal_ids)
        return all(item.subgoal_id in completed for item in state.task_plan.subgoals)

    @staticmethod
    def active_subgoal_spec(state: StateKernel) -> SubgoalSpec | None:
        if state.task_plan is None or state.plan_progress is None:
            return None
        active_id = state.plan_progress.active_subgoal_id
        return next((item for item in state.task_plan.subgoals if item.subgoal_id == active_id), None)

    @classmethod
    def active_subgoal_for_perception(cls, state: StateKernel) -> SubgoalSpec | str | None:
        if state.task_plan is None or state.plan_progress is None:
            return state.subgoals[-1] if state.subgoals else None
        return cls.active_subgoal_spec(state)

    @staticmethod
    def build_context(
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        budget: TaskPlanBudgetLimits,
        *,
        reason: str,
    ) -> TaskPlanningContext:
        plan = state.task_plan
        progress = state.plan_progress
        source_affordances = {
            item.id: item for item in snapshot.affordance_model.affordances
        }
        if snapshot.unified_affordances:
            affordances = tuple(
                PlanningAffordanceSummary(
                    semantic_target_id=item.semantic_target_id,
                    role=item.role,
                    label=item.label,
                    supported_actions=tuple(item.supported_actions),
                    current_state=_planning_affordance_state(
                        next(
                            (
                                source_affordances[candidate.source_affordance_id].state
                                for candidate in item.grounding_candidates
                                if candidate.source_affordance_id in source_affordances
                            ),
                            {},
                        )
                    ),
                )
                for item in snapshot.unified_affordances[:64]
            )
        else:
            affordances = tuple(
                PlanningAffordanceSummary(
                    semantic_target_id=item.id,
                    role=item.role,
                    label=item.label,
                    supported_actions=(item.action,),
                    current_state=_planning_affordance_state(item.state),
                )
                for item in snapshot.affordance_model.affordances[:64]
            )
        failures: tuple[TaskPlanningFailureSummary, ...] = ()
        latest = state.latest_verification
        if latest is not None and not latest.passed:
            failures = (
                TaskPlanningFailureSummary(
                    phase=state.phase,
                    error_code=latest.status.value,
                    reason=latest.reason[:500],
                    subgoal_id=progress.active_subgoal_id if progress is not None else "",
                    environment_revision=snapshot.observation.environment_revision,
                ),
            )
        elif reason == "subgoal_action_budget_exhausted":
            failures = (
                TaskPlanningFailureSummary(
                    phase="task_planning",
                    error_code="subgoal_action_budget_exhausted",
                    reason="active subgoal exhausted its action budget without matched criteria evidence",
                    subgoal_id=progress.active_subgoal_id if progress is not None else "",
                    environment_revision=snapshot.observation.environment_revision,
                ),
            )
        failure = state.current_failure
        recovery_plan = state.current_recovery_plan
        recovery_summary = (
            TaskPlanningRecoverySummary(
                incident_id=failure.failure_id,
                root_error_code=failure.error_code,
                terminal_outcome=(
                    recovery_plan.commands[0].reentry_phase.value
                    if recovery_plan is not None
                    else ""
                ),
                findings=(failure.failure_class.value,),
                attempted_actions=(
                    (recovery_plan.commands[0].kind.value,)
                    if recovery_plan is not None
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
                environment_revision=snapshot.observation.environment_revision,
                snapshot_id=snapshot.observation.snapshot_id,
                page_revision=snapshot.observation.page_revision,
                url=snapshot.observation.url,
                affordances=affordances,
            ),
            active_subgoal_id=progress.active_subgoal_id if progress is not None else "",
            completed_subgoal_ids=tuple(progress.completed_subgoal_ids) if progress is not None else (),
            failed_subgoal_ids=tuple(progress.failed_subgoal_ids) if progress is not None else (),
            criteria_evidence_ledger=(
                tuple(
                    CriteriaEvidenceLedgerEntry(
                        subgoal_id=subgoal_id,
                        evidence_ids=tuple(evidence_ids),
                    )
                    for subgoal_id, evidence_ids in sorted(progress.evidence_by_subgoal.items())
                )
                if progress is not None
                else ()
            ),
            failures=failures,
            recovery_summary=recovery_summary,
            disproved_assumptions=tuple(state.disproved_assumptions[-16:]),
            remaining_budget=TaskPlanningBudgetSummary(
                steps_remaining=max(0, budget.max_steps - state.step_count),
                observations_remaining=max(0, budget.max_observations - state.observation_count),
                replans_remaining=max(
                    0,
                    budget.max_replans - (progress.task_replan_count if progress is not None else 0),
                ),
                recoveries_remaining=max(0, budget.max_recoveries - state.recovery_count),
                effectful_actions_remaining=max(
                    0,
                    budget.max_effectful_actions - state.effectful_action_count,
                ),
            ),
        )


def _resolve_task_plan(value: TaskPlan | Awaitable[TaskPlan]) -> TaskPlan:
    if not inspect.isawaitable(value):
        return value
    return cast(TaskPlan, resolve_awaitable(value))


def _legacy_initial_task_plan(
    planner: TaskPlannerPort,
    context: TaskPlanningContext,
) -> TaskPlan:
    return _resolve_task_plan(planner.plan(context))


def _initial_plan_candidate(
    planner: TaskPlannerPort,
    context: TaskPlanningContext,
) -> PlanCandidate | Awaitable[PlanCandidate] | None:
    generate_candidate = getattr(planner, "generate_candidate", None)
    if generate_candidate is not None:
        return generate_candidate(context)
    return None


def _resolve_plan_candidate(value: PlanCandidate | Awaitable[PlanCandidate]) -> PlanCandidate:
    if not inspect.isawaitable(value):
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


def _carry_forward_completed_subgoals(
    replacement: TaskPlan,
    previous: TaskPlan,
    completed_subgoal_ids: tuple[str, ...],
) -> TaskPlan:
    """Restore exact completed authority while retaining model-owned unfinished units."""

    if not completed_subgoal_ids:
        return replacement
    completed = set(completed_subgoal_ids)
    previous_by_id = {item.subgoal_id: item for item in previous.subgoals}
    missing_authority = completed - previous_by_id.keys()
    if missing_authority:
        raise ValueError("completed subgoal is missing from the previous TaskPlan")
    preserved = tuple(
        item for item in previous.subgoals if item.subgoal_id in completed
    )
    unfinished = tuple(
        item for item in replacement.subgoals if item.subgoal_id not in completed
    )
    return replacement.model_copy(update={"subgoals": (*preserved, *unfinished)})


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
    )
