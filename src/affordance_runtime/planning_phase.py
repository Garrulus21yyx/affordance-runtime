"""Pure task and step planning stage."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, cast

from affordance_runtime.action_choice_catalog import (
    ActionChoiceCatalog,
    ActionChoiceCatalogBuilder,
)
from affordance_runtime.action_selection import ActionSelectionValidator
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.choice_contracts import (
    ActionChoiceFailure,
    ActionSelection,
    AskUser,
    ChoicePlanningRequest,
    SelectChoice,
)
from affordance_runtime.choice_presentation import ChoicePresentationProjector
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.model_port import ProviderFailureKind, ProviderModelError
from affordance_runtime.observation_store import ObservationRef
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.planning import (
    PlannerProposalValidator,
    ProposalRejected,
    proposal_error_code,
)
from affordance_runtime.planning_contracts import (
    PlannerClarificationResponse,
    PlannerDoneResponse,
    PlannerPort,
    PlannerProposalResponse,
    PlannerResponse,
    PlannerUnsupportedResponse,
)
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy
from affordance_runtime.recovery_protocol import classify_failure
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import semantic_progress_fingerprint, semantic_target_descriptor
from affordance_runtime.simplified_runtime_contracts import StepActivityStatus
from affordance_runtime.simplified_step_projection import (
    LegacyStepProjectionStatus,
    project_state_legacy_task_plan_to_step_view,
)
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)
from affordance_runtime.task_plan_flow import (
    TaskPlanCommitPreparation,
    TaskPlanCommitStateView,
    TaskPlanFlow,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits, TaskPlanLifecycle
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime, TaskSkillRuntimeDecision
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.mechanical import VerificationReport


class PlanningBudgetView(TaskPlanBudgetLimits, Protocol):
    @property
    def max_replans(self) -> int: ...


class _SkillActivationFailure(RuntimeError):
    pass


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
    response: PlannerResponse | None = None
    skill_step_id: str = ""
    task_plan_changed: bool = False
    catalog: ActionChoiceCatalog | None = None
    selection: ActionSelection | None = None


@dataclass(frozen=True)
class PlanningStage:
    planner: PlannerPort
    task_plan_flow: TaskPlanFlow | None = None
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None
    proposal_validator: PlannerProposalValidator = field(default_factory=PlannerProposalValidator)
    proposal_recovery_policy: ProposalRejectionRecoveryPolicy = field(
        default_factory=ProposalRejectionRecoveryPolicy
    )
    request_builder: PlanningRequestBuilder = field(default_factory=PlanningRequestBuilder)
    catalog_builder: ActionChoiceCatalogBuilder = field(default_factory=ActionChoiceCatalogBuilder)
    presentation_projector: ChoicePresentationProjector = field(
        default_factory=ChoicePresentationProjector
    )
    selection_validator: ActionSelectionValidator = field(default_factory=ActionSelectionValidator)
    runtime_profile_digest: str = ""

    def run(self, stage_input: PlanningStageInput) -> StageResult[PlanningOutput]:
        planned = self._prepare_task_plan(stage_input)
        if planned is not None:
            return planned
        choice_result = self._prepare_action_choice(stage_input)
        if choice_result is not None:
            return choice_result
        try:
            response, skill_step_id, events = self._select_response(stage_input)
        except ProviderModelError as exc:
            return self._provider_failure(stage_input, exc)
        except _SkillActivationFailure as exc:
            return self._failure(
                stage_input,
                FailurePhase.SKILL_ACTIVATION,
                FailureClass.PLANNING,
                RuntimeErrorCode.PLANNER_FAILED,
                str(exc),
                events=(
                    _event(
                        "TaskSkillFellThrough",
                        stage_input.state_view.phase,
                        reason=str(exc),
                        fallback="system_2",
                    ),
                ),
            )
        except Exception as exc:
            return self._failure(
                stage_input,
                FailurePhase.STEP_PLANNING,
                FailureClass.PLANNING,
                RuntimeErrorCode.PLANNER_FAILED,
                f"{type(exc).__name__}: {exc}"[:500],
                events=(
                    _event(
                        "PlannerProposalRejected",
                        stage_input.state_view.phase,
                        error_code=RuntimeErrorCode.PLANNER_FAILED.value,
                        reason=f"{type(exc).__name__}: {exc}"[:500],
                    ),
                ),
            )
        return self._validate_response(stage_input, response, skill_step_id, events)

    def _prepare_action_choice(
        self, stage_input: PlanningStageInput
    ) -> StageResult[PlanningOutput] | None:
        task_spec = stage_input.envelope.task_spec
        if task_spec is None:
            return None
        projection = project_state_legacy_task_plan_to_step_view(
            task_spec=task_spec,
            state=cast(Any, stage_input.state_view),
        )
        if (
            projection.status != LegacyStepProjectionStatus.PROJECTED
            or projection.task_plan_view is None
            or projection.step_progress_view is None
            or projection.step_progress_view.activity_status != StepActivityStatus.ACTIVE
            or not projection.step_progress_view.active_step_id
        ):
            return None
        step = next(
            (
                item
                for item in projection.task_plan_view.steps
                if item.step_id == projection.step_progress_view.active_step_id
            ),
            None,
        )
        if step is None:
            return None
        scope = ActiveStepScope.from_active_step(
            task_revision=task_spec.revision,
            evaluated_at_state_version=stage_input.state_view.version,
            snapshot_id=stage_input.observation.epoch_id,
            step=step,
            activity_status=StepActivityStatus.ACTIVE,
        )
        plan = stage_input.state_view.task_plan
        catalog_or_failure = self.catalog_builder.build(
            task_revision=task_spec.revision,
            task_spec=task_spec,
            plan_revision=getattr(plan, "plan_version", 1),
            state_version=stage_input.state_view.version,
            step=step,
            scope=scope,
            observation=stage_input.observation,
            capabilities=frozenset(stage_input.envelope.capabilities),
        )
        if isinstance(catalog_or_failure, ActionChoiceFailure):
            return self._failure(
                stage_input,
                FailurePhase.STEP_PLANNING,
                FailureClass.GROUNDING,
                RuntimeErrorCode.PLANNER_FAILED,
                catalog_or_failure.reason_code,
                events=(
                    _event(
                        "ActionChoiceCatalogRejected",
                        stage_input.state_view.phase,
                        reason_code=catalog_or_failure.reason_code,
                    ),
                ),
            )
        catalog = catalog_or_failure
        page = None
        if catalog.count == 1:
            selection = self.selection_validator.select_unique(catalog)
            source = "runtime_unique_choice"
        else:
            page = self.presentation_projector.project(catalog)
            selector = getattr(self.planner, "select", None)
            if not callable(selector):
                return self._failure(
                    stage_input,
                    FailurePhase.STEP_PLANNING,
                    FailureClass.PLANNING,
                    RuntimeErrorCode.PLANNER_FAILED,
                    "step choice planner does not implement select(ChoicePlanningRequest)",
                )
            request = ChoicePlanningRequest(
                task_spec.revision,
                catalog.plan_revision,
                step.step_id,
                catalog.ref,
                page,
            )
            value = selector(request)
            proposal = resolve_awaitable(value) if inspect.isawaitable(value) else value
            if isinstance(proposal, AskUser):
                result = {"clarification": proposal.question}
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
            if isinstance(proposal, ActionSelection):
                proposal = SelectChoice(proposal.choice_id, proposal.reason_summary)
            if not isinstance(proposal, SelectChoice):
                return self._failure(
                    stage_input,
                    FailurePhase.STEP_PLANNING,
                    FailureClass.VALIDATION,
                    RuntimeErrorCode.PLANNER_FAILED,
                    "step choice planner returned a non-selection control response",
                )
            selection = self.selection_validator.validate(proposal, catalog, page)
            source = "step_choice_planner"
        events = (
            _event(
                "ActionChoiceCatalogBuilt",
                stage_input.state_view.phase,
                catalog_id=catalog.catalog_id,
                catalog_digest=catalog.catalog_digest,
                total_choice_count=catalog.count,
                admitted_choice_count=catalog.build_report.admitted_choice_count,
            ),
            _event(
                "ActionChoiceSelected",
                stage_input.state_view.phase,
                choice_id=selection.choice_id,
                selection_source=source,
                presented_choice_count=len(page.choices) if page is not None else 0,
            ),
        )
        return StageResult(
            output=PlanningOutput(catalog=catalog, selection=selection),
            events=events,
        )

    def _prepare_task_plan(
        self, stage_input: PlanningStageInput
    ) -> StageResult[PlanningOutput] | None:
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
            getattr(stage_input.state_view.task_progress, "completed_subgoal_ids", ())
            if stage_input.state_view.task_progress is not None
            else ()
        )
        active = next(
            (
                item.subgoal_id
                for item in plan.subgoals
                if item.subgoal_id not in completed and set(item.depends_on).issubset(completed)
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

    def _select_response(
        self, stage_input: PlanningStageInput
    ) -> tuple[PlannerResponse, str, tuple[RuntimeEvent, ...]]:
        runtime = self.task_skill_runtime
        task_spec = stage_input.envelope.task_spec
        skill_events: tuple[RuntimeEvent, ...] = ()
        if runtime is not None and task_spec is not None:
            try:
                skill = runtime.expose(
                    task_spec,
                    cast(Any, stage_input.state_view),
                    stage_input.observation,
                )
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"[:500]
                runtime.fallthrough(cast(Any, stage_input.state_view), reason)
                raise _SkillActivationFailure(reason) from exc
            skill_response = _task_skill_response(runtime, stage_input, skill)
            events = _task_skill_events(runtime, stage_input, skill)
            skill_events = events
            if skill_response is not None:
                return skill_response, skill.exposure.step_id if skill.exposure else "", events
        request = self.request_builder.build(
            stage_input.envelope,
            cast(Any, stage_input.state_view),
            stage_input.observation,
        )
        propose_canonical = getattr(self.planner, "propose_canonical", None)
        value = (
            propose_canonical(request, stage_input.observation)
            if callable(propose_canonical)
            else self.planner.propose(request)
        )
        response = resolve_awaitable(value) if inspect.isawaitable(value) else value
        return cast(PlannerResponse, response), "", skill_events

    def _validate_response(
        self,
        stage_input: PlanningStageInput,
        response: PlannerResponse,
        skill_step_id: str,
        prefix_events: tuple[RuntimeEvent, ...],
    ) -> StageResult[PlanningOutput]:
        diagnostics = response.diagnostics
        events = [
            *prefix_events,
            _event(
                "PlanningTurnEvaluated",
                stage_input.state_view.phase,
                model_stage=diagnostics.model_stage,
                grounded_target_count=diagnostics.grounded_target_count,
                action_choice_count=diagnostics.action_choice_count,
                selection_source=diagnostics.selection_source,
                response_status=response.status.value,
            ),
            _event("PlanProposed", stage_input.state_view.phase, response=type(response).__name__),
        ]
        if isinstance(response, PlannerClarificationResponse):
            result = {"clarification": response.question}
            events.append(_event("ClarificationRequested", RuntimeStep.WAITING_CLARIFICATION.value, **result))
            return StageResult(
                output=PlanningOutput(response, skill_step_id),
                transition=RuntimeTransition(phase=RuntimeStep.WAITING_CLARIFICATION, final_result=result),
                events=tuple(events),
                terminal=TerminalResult("", "clarification_required", RuntimeStep.WAITING_CLARIFICATION),
                directive=LoopDirective.WAIT_USER,
            )
        if isinstance(response, PlannerUnsupportedResponse):
            return self._failure(
                stage_input,
                FailurePhase.STEP_PLANNING,
                FailureClass.VALIDATION,
                response.reason_code,
                response.message or response.reason_code,
                events=tuple(events),
            )
        if isinstance(response, PlannerDoneResponse):
            return self._done(stage_input, response, skill_step_id, events)
        if not isinstance(response, PlannerProposalResponse):
            raise TypeError(f"unsupported planner response: {type(response).__name__}")
        proposal = response.proposal
        if proposal.requires_clarification:
            return self._validate_response(
                stage_input,
                PlannerClarificationResponse(proposal.subgoal or proposal.reason or response.reason),
                skill_step_id,
                tuple(events),
            )
        if proposal.done:
            return self._done(
                stage_input,
                PlannerDoneResponse(result=dict(proposal.result), reason=response.reason),
                skill_step_id,
                events,
            )
        try:
            if stage_input.envelope.task_spec is None:
                raise ValueError("semantic proposal requires a validated TaskSpec")
            self.proposal_validator.validate(
                proposal,
                response.proposal_provenance,
                stage_input.envelope.task_spec,
                cast(Any, stage_input.state_view),
                stage_input.observation,
            )
        except ProposalRejected as exc:
            policy = self.proposal_recovery_policy.decide(
                exc.code, exc.detail, exc.reason_code, proposal.target_affordance_id
            )
            error = proposal_error_code(exc.code)
            events.append(
                _event(
                    "PlannerProposalRejected",
                    stage_input.state_view.phase,
                    proposal_id=proposal.proposal_id,
                    error_code=error.value,
                    rejection_code=exc.code.value,
                    rejection_reason_code=exc.reason_code,
                    reason=exc.detail,
                    provenance=(
                        response.proposal_provenance.model_dump(mode="json")
                        if response.proposal_provenance is not None
                        else None
                    ),
                )
            )
            return self._failure(
                stage_input,
                FailurePhase.PROPOSAL_VALIDATION,
                FailureClass.VALIDATION,
                error,
                policy.planner_feedback,
                events=tuple(events),
                recoverable=policy.recoverable,
            )
        provenance = response.proposal_provenance
        if provenance is None:
            raise RuntimeError("validated proposal is missing provenance")
        events.extend(
            (
                _event(
                    "PlannerProposalValidated",
                    stage_input.state_view.phase,
                    proposal_id=proposal.proposal_id,
                    source=provenance.source.value,
                    provenance=provenance.model_dump(mode="json"),
                ),
                _event(
                    "PlannerProposalProduced",
                    stage_input.state_view.phase,
                    proposal_id=proposal.proposal_id,
                    semantic_target=semantic_target_descriptor(stage_input.observation, proposal.target_affordance_id),
                    semantic_destination=semantic_target_descriptor(stage_input.observation, proposal.destination_affordance_id),
                    proposal=proposal.model_dump(mode="json"),
                    provenance=provenance.model_dump(mode="json"),
                ),
            )
        )
        return StageResult(
            output=PlanningOutput(response, skill_step_id),
            events=tuple(events),
        )

    def _done(
        self,
        stage_input: PlanningStageInput,
        response: PlannerDoneResponse,
        skill_step_id: str,
        events: list[RuntimeEvent],
    ) -> StageResult[PlanningOutput]:
        view = stage_input.state_view
        if view.task_plan is not None and not TaskPlanLifecycle.completed(cast(Any, view)):
            status = str(response.result.get("status") or "").casefold()
            safe_stop = status in {"blocked", "incomplete", "inconclusive", "unsupported"} and view.last_receipt is None and view.effectful_action_count == 0
            if not safe_stop:
                return self._failure(
                    stage_input,
                    FailurePhase.PROPOSAL_VALIDATION,
                    FailureClass.VALIDATION,
                    RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                    "planner cannot finish before verifier-backed subgoal completion",
                    events=tuple(events),
                    recoverable=False,
                )
        events.append(
            _event(
                "FinalVerificationRequested",
                view.phase,
                reason=response.reason,
            )
        )
        return StageResult(
            output=PlanningOutput(response, skill_step_id),
            transition=RuntimeTransition(
                phase=RuntimeStep.OBSERVING,
                final_result=dict(response.result),
            ),
            events=tuple(events),
            directive=LoopDirective.REPEAT_OBSERVATION,
        )

    def _provider_failure(
        self, stage_input: PlanningStageInput, exc: ProviderModelError
    ) -> StageResult[PlanningOutput]:
        error = RuntimeErrorCode(exc.kind.value)
        result = {
            "deferred": True,
            "provider_failure": exc.kind.value,
            "retry_after_s": exc.retry_after_s,
            "resumable": exc.resumable,
        }
        failed = self._failure(
            stage_input,
            FailurePhase.PROVIDER_CONTEXT,
            FailureClass.PROVIDER,
            error,
            f"provider failure: {exc.kind.value}",
        )
        if exc.kind != ProviderFailureKind.QUOTA_EXHAUSTED:
            return failed
        assert failed.failure is not None
        owner = classify_failure(failed.failure).owner
        return replace(
            failed,
            transition=RuntimeTransition(
                phase=RuntimeStep.DEFERRED,
                final_result=result,
            ),
            events=(
                RuntimeEvent(
                    "FailureDetected",
                    {
                        "state": stage_input.state_view.phase,
                        "failure": failed.failure.model_dump(mode="json"),
                    },
                ),
                _event(
                    "FailureOwnerRouted",
                    stage_input.state_view.phase,
                    failure_id=failed.failure.failure_id,
                    owner=owner.value,
                    reason_code="provider_unavailable",
                    handoff_type="TerminalResult",
                ),
                _event(
                    "PlannerDeferred",
                    stage_input.state_view.phase,
                    error_code=error.value,
                    retry_after_s=exc.retry_after_s,
                    circuit_open=exc.circuit_open,
                    resumable=exc.resumable,
                ),
            ),
            terminal=TerminalResult(
                "",
                "provider_deferred",
                RuntimeStep.DEFERRED,
                error,
            ),
            directive=LoopDirective.TERMINAL,
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
            task_revision=plan.task_revision if plan is not None else stage_input.envelope.task_spec.revision if stage_input.envelope.task_spec is not None else 1,
            plan_version=plan.plan_version if plan is not None else 0,
            active_subgoal_id=view.task_progress.active_subgoal_id if view.task_progress is not None else "",
            observation_epoch_id=stage_input.observation.epoch_id,
            snapshot_id=stage_input.observation.epoch_id,
            expected_effect=stage_input.envelope.goal,
            remaining_budgets=stage_input.remaining_budgets,
            recoverable=recoverable,
            progress_fingerprint=semantic_progress_fingerprint(cast(Any, view)),
        )
        return StageResult(events=events, failure=failure)


def task_skill_progress(
    runtime: object | None, state: object
) -> TaskSkillRunState | None:
    progress_for = getattr(runtime, "progress_for", None)
    progress = progress_for(state) if callable(progress_for) else None
    return progress if isinstance(progress, TaskSkillRunState) else None


def _task_skill_response(
    runtime: AcceptedTaskSkillRuntime,
    stage_input: PlanningStageInput,
    decision: TaskSkillRuntimeDecision,
) -> PlannerProposalResponse | None:
    exposure = decision.exposure
    if exposure is None or exposure.proposal is None or decision.payload is None:
        return None
    progress = task_skill_progress(runtime, stage_input.state_view)
    from affordance_runtime.planning import PlannerProposalProvenance, PlannerProposalSource

    return PlannerProposalResponse(
        proposal=exposure.proposal,
        proposal_provenance=PlannerProposalProvenance(
            source=PlannerProposalSource.ACCEPTED_SKILL,
            producer_id=decision.payload.skill_id,
            version=decision.payload.version,
            evidence_refs=tuple(progress.evidence) if progress else (),
        ),
        reason="accepted TaskSkill exposed one semantic step",
    )


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
        events.append(_event("TaskSkillActivated", stage_input.state_view.phase, skill_id=decision.payload.skill_id, version=decision.payload.version))
    if decision.exposure is not None and decision.exposure.proposal is not None and decision.payload is not None:
        events.append(_event("TaskSkillStepExposed", stage_input.state_view.phase, skill_id=decision.payload.skill_id, step_id=decision.exposure.step_id))
    elif decision.attempted and decision.reason:
        progress = task_skill_progress(runtime, stage_input.state_view)
        events.append(_event("TaskSkillFellThrough", stage_input.state_view.phase, reason=decision.reason, preserved_evidence=list(progress.evidence) if progress else [], fallback="system_2"))
    return tuple(events)


def _event(kind: str, state: str, **payload: object) -> RuntimeEvent:
    return RuntimeEvent(kind, {"state": state, **payload})
