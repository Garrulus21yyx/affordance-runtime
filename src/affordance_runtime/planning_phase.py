"""Pure task and step planning stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.choice_contracts import (
    ActionChoiceFailure,
    ActionSelection,
    AskUser,
    ChoicePlanningBudget,
    DeferChoice,
    ReportPlanIssue,
    SelectChoice,
)
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.observation_store import ObservationRef
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.planning import PlannerProposal
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import semantic_progress_fingerprint
from affordance_runtime.simplified_runtime_contracts import StepActivityStatus
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)
from affordance_runtime.step_choice_flow import (
    StepChoiceFlow,
    StepChoiceFlowKind,
    StepChoiceFlowResult,
    recent_choice_outcomes,
)
from affordance_runtime.task_plan_contracts import project_task_plan_views
from affordance_runtime.task_plan_flow import (
    TaskPlanCommitPreparation,
    TaskPlanCommitStateView,
    TaskPlanFlow,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime, TaskSkillRuntimeDecision
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.mechanical import VerificationReport


class PlanningBudgetView(TaskPlanBudgetLimits, Protocol):
    @property
    def max_replans(self) -> int: ...


@dataclass(frozen=True)
class PlanningStageInput:
    envelope: RunRequest
    capture: PerceptionCapture
    observation: UnifiedObservation
    observation_ref: ObservationRef
    state_view: RuntimeStateSnapshot
    budget: PlanningBudgetView
    latest_verification: VerificationReport | None = None
    remaining_budgets: RemainingRecoveryBudgets = field(default_factory=RemainingRecoveryBudgets)


@dataclass(frozen=True)
class PlanningOutput:
    skill_step_id: str = ""
    task_plan_changed: bool = False
    catalog: ActionChoiceCatalog | None = None
    selection: ActionSelection | None = None


@dataclass(frozen=True)
class PlanningStage:
    task_plan_flow: TaskPlanFlow | None = None
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None
    step_choice_flow: StepChoiceFlow = field(default_factory=lambda: StepChoiceFlow(None))

    def run(self, stage_input: PlanningStageInput) -> StageResult[PlanningOutput]:
        planned = self._prepare_task_plan(stage_input)
        if planned is not None:
            return planned
        choice_result = self._prepare_action_choice(stage_input)
        if choice_result is not None:
            return choice_result
        return self._failure(
            stage_input,
            FailurePhase.STEP_PLANNING,
            FailureClass.PLANNING,
            RuntimeErrorCode.PLANNER_FAILED,
            "strict planning produced neither a TaskPlan transition nor a closed action choice",
            recoverable=False,
        )

    def _prepare_action_choice(self, stage_input: PlanningStageInput) -> StageResult[PlanningOutput] | None:
        task_spec = stage_input.envelope.task_spec
        if task_spec is None:
            return None
        plan = stage_input.state_view.task_plan
        progress = stage_input.state_view.task_progress
        if plan is None or progress is None:
            return None
        task_plan_view, step_progress_view = project_task_plan_views(
            plan,
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            progress=progress,
        )
        if step_progress_view.activity_status != StepActivityStatus.ACTIVE or not step_progress_view.active_step_id:
            return None
        step = next(
            (item for item in task_plan_view.steps if item.step_id == step_progress_view.active_step_id),
            None,
        )
        if step is None:
            return None
        catalog_or_failure = self.step_choice_flow.build_catalog(
            task_spec=task_spec,
            plan_revision=getattr(plan, "plan_version", 1),
            state_version=stage_input.state_view.version,
            step=step,
            observation=stage_input.observation,
            capabilities=frozenset(stage_input.envelope.capabilities),
        )
        if isinstance(catalog_or_failure, ActionChoiceFailure):
            choice = None
            failure_reason = catalog_or_failure.reason_code
        else:
            catalog = catalog_or_failure
            try:
                skill_selection, skill_step_id, skill_events = self._task_skill_selection(
                    stage_input,
                    catalog,
                )
            except Exception as exc:
                return self._failure(
                    stage_input,
                    FailurePhase.SKILL_ACTIVATION,
                    FailureClass.PLANNING,
                    RuntimeErrorCode.PLANNER_FAILED,
                    f"{type(exc).__name__}: {exc}"[:500],
                    recoverable=False,
                )
            if skill_selection is not None:
                choice = StepChoiceFlowResult(
                    StepChoiceFlowKind.SELECTED,
                    catalog=catalog,
                    selection=skill_selection,
                    selection_source="accepted_task_skill",
                )
            else:
                choice = self.step_choice_flow.choose_from_catalog(
                    catalog,
                    recent_outcomes=recent_choice_outcomes(stage_input.state_view.recent_action_outcomes),
                    budget=ChoicePlanningBudget(
                        model_calls_remaining=max(
                            0,
                            stage_input.remaining_budgets.model_calls,
                        ),
                    ),
                )
            failure_reason = choice.failure_reason
        if choice is None or choice.kind == StepChoiceFlowKind.FAILED:
            events = tuple(skill_events) if not isinstance(catalog_or_failure, ActionChoiceFailure) else ()
            events += (
                _event(
                    "ActionChoiceCatalogRejected",
                    stage_input.state_view.phase,
                    reason_code=failure_reason,
                    authority_rejections=(
                        [
                            {
                                "target_id": item.target_id,
                                "action_kind": (
                                    item.action_kind.value
                                    if item.action_kind is not None
                                    else ""
                                ),
                                "status": item.status.value,
                                "reason_codes": list(item.reason_codes),
                            }
                            for item in catalog_or_failure.build_report.rejections
                        ]
                        if isinstance(catalog_or_failure, ActionChoiceFailure)
                        and catalog_or_failure.build_report is not None
                        else []
                    ),
                ),
            )
            return self._failure(
                stage_input,
                FailurePhase.STEP_PLANNING,
                FailureClass.PLANNING,
                RuntimeErrorCode.PLANNER_FAILED,
                failure_reason,
                events=events,
            )
        if choice.kind == StepChoiceFlowKind.ASK_USER:
            assert isinstance(choice.response, AskUser)
            result = {"clarification": choice.response.question}
            return StageResult(
                output=PlanningOutput(),
                transition=RuntimeTransition(
                    phase=RuntimeStep.WAITING_CLARIFICATION,
                    final_result=result,
                ),
                events=(
                    _event(
                        "ClarificationRequested",
                        RuntimeStep.WAITING_CLARIFICATION.value,
                        **result,
                    ),
                ),
                terminal=TerminalResult(
                    "",
                    "clarification_required",
                    RuntimeStep.WAITING_CLARIFICATION,
                ),
                directive=LoopDirective.WAIT_USER,
            )
        if choice.kind == StepChoiceFlowKind.DEFER:
            assert isinstance(choice.response, DeferChoice)
            return StageResult(
                output=PlanningOutput(),
                transition=RuntimeTransition(
                    phase=RuntimeStep.DEFERRED,
                    final_result={"deferred": True, "reason": choice.response.reason},
                ),
                events=(
                    _event(
                        "PlannerDeferred",
                        RuntimeStep.DEFERRED.value,
                        reason=choice.response.reason,
                    ),
                ),
                terminal=TerminalResult("", "choice_deferred", RuntimeStep.DEFERRED),
                directive=LoopDirective.TERMINAL,
            )
        if choice.kind == StepChoiceFlowKind.PLAN_ISSUE:
            assert isinstance(choice.response, ReportPlanIssue)
            return self._failure(
                stage_input,
                FailurePhase.TASK_PLANNING,
                FailureClass.PLANNING,
                RuntimeErrorCode.PLANNER_FAILED,
                choice.response.kind,
            )
        selected_catalog = choice.catalog
        selected_selection = choice.selection
        if selected_catalog is None or selected_selection is None:
            raise RuntimeError("selected choice flow result is incomplete")
        events = (
            *skill_events,
            _event(
                "ActionChoiceCatalogBuilt",
                stage_input.state_view.phase,
                catalog_id=selected_catalog.catalog_id,
                catalog_digest=selected_catalog.catalog_digest,
                total_choice_count=selected_catalog.count,
                admitted_choice_count=selected_catalog.build_report.admitted_choice_count,
            ),
            _event(
                "ActionChoiceSelected",
                stage_input.state_view.phase,
                choice_id=selected_selection.choice_id,
                selection_source=choice.selection_source,
                presented_choice_count=(len(choice.page.choices) if choice.page is not None else 0),
            ),
        )
        return StageResult(
            output=PlanningOutput(
                skill_step_id=skill_step_id,
                catalog=selected_catalog,
                selection=selected_selection,
            ),
            events=events,
        )

    def _task_skill_selection(
        self,
        stage_input: PlanningStageInput,
        catalog: ActionChoiceCatalog,
    ) -> tuple[ActionSelection | None, str, tuple[RuntimeEvent, ...]]:
        runtime = self.task_skill_runtime
        task_spec = stage_input.envelope.task_spec
        if runtime is None or task_spec is None:
            return None, "", ()
        decision = runtime.expose(
            task_spec,
            cast(Any, stage_input.state_view),
            stage_input.observation,
        )
        events = _task_skill_events(runtime, stage_input, decision)
        exposure = decision.exposure
        proposal = exposure.proposal if exposure is not None else None
        if not isinstance(proposal, PlannerProposal):
            return None, "", events
        assert exposure is not None
        matches = tuple(
            choice
            for choice in catalog.page(None, catalog.count).choices
            if choice.action_kind == proposal.action_kind
            and choice.target_id == proposal.target_affordance_id
            and choice.destination_id == proposal.destination_affordance_id
            and dict(choice.parameters) == dict(proposal.parameters)
        )
        if len(matches) != 1:
            reason = "accepted TaskSkill proposal does not name exactly one canonical choice"
            runtime.fallthrough(cast(Any, stage_input.state_view), reason)
            return (
                None,
                "",
                (
                    *events,
                    _event(
                        "TaskSkillFellThrough",
                        stage_input.state_view.phase,
                        reason=reason,
                        fallback="strict_step_choice",
                    ),
                ),
            )
        selection = self.step_choice_flow.selection_validator.validate(
            SelectChoice(matches[0].choice_id, "accepted_task_skill"),
            catalog,
            None,
        )
        return selection, exposure.step_id, events

    def _prepare_task_plan(self, stage_input: PlanningStageInput) -> StageResult[PlanningOutput] | None:
        task_spec = stage_input.envelope.task_spec
        if self.task_plan_flow is None or task_spec is None:
            return None
        result = self.task_plan_flow.prepare(
            task_spec,
            cast(Any, stage_input.state_view),
            stage_input.observation,
            stage_input.budget,
        )
        preparation = TaskPlanCommitPreparation(result)
        if not result.required:
            return None
        events: list[RuntimeEvent] = []
        before = preparation.pre_commit_projection(state_phase=stage_input.state_view.phase)
        if before is not None:
            events.append(RuntimeEvent(before.kind, before.payload))
        if preparation.failure is not None:
            rejected = preparation.failure_projection(state_phase=stage_input.state_view.phase)
            return self._failure(
                stage_input,
                FailurePhase.TASK_PLANNING,
                preparation.failure.failure_class,
                preparation.failure.error_code,
                preparation.failure.message,
                events=(*events, RuntimeEvent(rejected.kind, rejected.payload)),
            )
        if not preparation.accepted or preparation.transition is None:
            return None
        transition = preparation.transition
        plan = transition.plan
        completed = tuple(
            getattr(stage_input.state_view.task_progress, "completed_step_ids", ())
            if stage_input.state_view.task_progress is not None
            else ()
        )
        active = next(
            (
                item.step_id
                for item in plan.steps
                if item.step_id not in completed and set(item.depends_on).issubset(completed)
            ),
            "",
        )
        accepted = preparation.acceptance_projection(
            state_phase=stage_input.state_view.phase,
            committed=TaskPlanCommitStateView(active, completed),
        )
        events.append(RuntimeEvent(accepted.kind, accepted.payload))
        return StageResult(
            output=PlanningOutput(task_plan_changed=True),
            transition=RuntimeTransition(
                phase=RuntimeStep.OBSERVING,
                task_plan_transition=transition,
            ),
            events=tuple(events),
            directive=LoopDirective.NEXT_STAGE,
        )

    def _failure(
        self,
        stage_input: PlanningStageInput,
        phase: FailurePhase,
        failure_class: FailureClass,
        error_code: RuntimeErrorCode | str,
        message: str,
        *,
        events: tuple[RuntimeEvent, ...] = (),
        recoverable: bool = True,
    ) -> StageResult[PlanningOutput]:
        view = stage_input.state_view
        plan = view.task_plan
        failure = make_failure_envelope(
            run_id=stage_input.envelope.task_id,
            phase=phase,
            failure_class=failure_class,
            error_code=error_code,
            message=message,
            state_version=view.version,
            task_revision=(
                plan.task_revision
                if plan is not None
                else stage_input.envelope.task_spec.revision
                if stage_input.envelope.task_spec is not None
                else 1
            ),
            plan_version=plan.plan_version if plan is not None else 0,
            active_step_id=view.task_progress.active_step_id if view.task_progress is not None else "",
            observation_epoch_id=stage_input.observation.epoch_id,
            snapshot_id=stage_input.observation.epoch_id,
            expected_effect=stage_input.envelope.goal,
            remaining_budgets=stage_input.remaining_budgets,
            recoverable=recoverable,
            progress_fingerprint=semantic_progress_fingerprint(cast(Any, view)),
        )
        return StageResult(events=events, failure=failure)


def task_skill_progress(runtime: object | None, state: object) -> TaskSkillRunState | None:
    progress_for = getattr(runtime, "progress_for", None)
    progress = progress_for(state) if callable(progress_for) else None
    return progress if isinstance(progress, TaskSkillRunState) else None


def _task_skill_events(
    runtime: AcceptedTaskSkillRuntime,
    stage_input: PlanningStageInput,
    decision: TaskSkillRuntimeDecision,
) -> tuple[RuntimeEvent, ...]:
    events = [
        _event(
            "TaskSkillSelectionEvaluated",
            stage_input.state_view.phase,
            matched=decision.payload is not None,
            newly_activated=decision.newly_activated,
            attempted=decision.attempted,
            reason=decision.reason,
        )
    ]
    if decision.newly_activated and decision.payload is not None:
        events.append(
            _event(
                "TaskSkillActivated",
                stage_input.state_view.phase,
                skill_id=decision.payload.skill_id,
                version=decision.payload.version,
            )
        )
    if decision.exposure is not None and decision.exposure.proposal is not None and decision.payload is not None:
        events.append(
            _event(
                "TaskSkillStepExposed",
                stage_input.state_view.phase,
                skill_id=decision.payload.skill_id,
                step_id=decision.exposure.step_id,
            )
        )
    elif decision.attempted and decision.reason:
        progress = task_skill_progress(runtime, stage_input.state_view)
        events.append(
            _event(
                "TaskSkillFellThrough",
                stage_input.state_view.phase,
                reason=decision.reason,
                preserved_evidence=list(progress.evidence) if progress else [],
                fallback="system_2",
            )
        )
    return tuple(events)


def _event(kind: str, state: str, **payload: object) -> RuntimeEvent:
    return RuntimeEvent(kind, {"state": state, **payload})
