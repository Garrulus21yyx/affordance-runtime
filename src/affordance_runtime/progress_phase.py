"""Pure post-observation and post-action progress stage."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, cast

from affordance_runtime.action_outcome_flow import record_contract_action_outcome_trace
from affordance_runtime.active_perception import ObservationContinuationPolicy
from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
)
from affordance_runtime.failure_envelope import RemainingRecoveryBudgets
from affordance_runtime.observation_store import (
    InMemoryObservationStore,
    ObservationCommit,
    ObservationRef,
)
from affordance_runtime.perception_session import PerceptionCapture, PerceptionSession
from affordance_runtime.progress_evaluation import (
    ActiveStepEvaluationStatus,
    PostActionEvaluation,
    ProgressEvaluationService,
    TaskCompletionEvaluationStatus,
)
from affordance_runtime.progress_observation import PostActionObservationService
from affordance_runtime.progress_skill import TaskSkillProgressService
from affordance_runtime.route_calibration import RouteCalibrator, RouteOutcome, RouteOutcomeStatus, RouteScope
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import (
    admit_observation_durable_evidence,
    observation_evidence_context_metadata,
    observation_predicate_evidence,
    verification_satisfies_effect,
)
from affordance_runtime.runtime_state_projection import project_working_phase
from affordance_runtime.simplified_runtime_contracts import ActionOutcome
from affordance_runtime.source_context import TaskSpecGap
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEventBuffer,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits, TaskPlanLifecycle
from affordance_runtime.task_plan_progress_flow import (
    commit_verified_task_progress,
)
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import (
    LoopEvaluation,
    TaskCompletionEvaluation,
)
from affordance_runtime.verification.loop_evaluator import LoopEvaluator
from affordance_runtime.verification.mechanical import VerificationReport, VerificationStatus
from affordance_runtime.verification.open_semantic import (
    OPEN_SEMANTIC_UNRESOLVED,
    unresolved_open_semantic_gaps,
)


@dataclass(frozen=True)
class ProgressActionInput:
    contract: ActionContract
    receipt: ExecutionReceipt
    execution_observation: Observation
    action_signature: str
    skill_step_id: str = ""


@dataclass(frozen=True)
class ProgressStageInput:
    envelope: RunRequest
    capture: PerceptionCapture
    observation: UnifiedObservation
    state_view: RuntimeStateSnapshot
    budget: TaskPlanBudgetLimits
    remaining_budgets: RemainingRecoveryBudgets
    action: ProgressActionInput | None = None


@dataclass(frozen=True)
class ProgressOutput:
    capture: PerceptionCapture
    observation: UnifiedObservation | None = None
    observation_ref: ObservationRef | None = None
    observation_commits: tuple[ObservationCommit, ...] = ()
    verification: VerificationReport | None = None
    verification_ref: ArtifactRef | None = None
    action_outcome: ActionOutcome | None = None
    completion_committed: bool = False
    evaluation: PostActionEvaluation | None = None
    task_completion: TaskCompletionEvaluation | None = None
    loop_evaluation: LoopEvaluation | None = None
    task_spec_gaps: tuple[TaskSpecGap, ...] = ()


@dataclass(frozen=True)
class ProgressStage:
    execution_loop: ContractExecutionLoop
    perception_session: PerceptionSession
    route_calibrator: RouteCalibrator
    loop_evaluator: LoopEvaluator = field(default_factory=LoopEvaluator)
    continuation_policy: ObservationContinuationPolicy = field(default_factory=ObservationContinuationPolicy)
    observation_builder: CanonicalObservationBuilder = CanonicalObservationBuilder()
    observation_store: InMemoryObservationStore = field(default_factory=InMemoryObservationStore)
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None
    evaluation_service: ProgressEvaluationService = field(default_factory=ProgressEvaluationService)
    artifacts: ArtifactStore | None = None
    structural_verification_enabled: bool = True
    recovery_enabled: bool = True
    task_planner_is_router: bool = True

    def run(self, stage_input: ProgressStageInput) -> StageResult[ProgressOutput]:
        state = cast(Any, stage_input.state_view.projection())
        events = RuntimeEventBuffer()
        parent = events.root()
        if stage_input.action is None:
            current_evidence = observation_predicate_evidence(stage_input.observation)
            latest_recheck, resource_versions = observation_evidence_context_metadata(stage_input.observation)
            if state.task_progress is not None:
                admit_observation_durable_evidence(stage_input.observation, state.task_progress.durable_evidence)
            task_completion = self.evaluation_service.evaluate_task_completion(
                task_spec=stage_input.envelope.task_spec,
                state=state,
                observation=stage_input.capture.observation,
                report=None,
                result=state.final_result,
            )
            if task_completion is not None:
                self.evaluation_service.record_task_completion(events, state, task_completion)
            if task_completion is not None and task_completion.completed:
                return self._result(
                    state,
                    events,
                    ProgressOutput(
                        stage_input.capture,
                        completion_committed=True,
                        task_completion=task_completion,
                    ),
                    terminal=TerminalResult("", "task_completed", RuntimeStep.DONE),
                    task_completion=task_completion,
                )
            active_step = TaskPlanLifecycle.active_step_spec(state)
            if active_step is None and state.task_plan is not None and state.task_progress is not None:
                ready = state.task_progress.ready_step_ids(state.task_plan)
                active_step = state.task_plan.step(ready[0]) if ready else None
                if active_step is not None:
                    state.task_progress.active_step_id = active_step.step_id
            step_completion = self.loop_evaluator.step_evaluator.evaluate(
                active_step,
                self.loop_evaluator.evidence_context(
                    observation=stage_input.observation,
                    current_evidence=current_evidence,
                    recent_action_outcomes=(
                        tuple(state.task_progress.recent_action_outcomes.records)
                        if state.task_progress is not None
                        else ()
                    ),
                    durable_evidence=(
                        tuple(state.task_progress.durable_evidence.records) if state.task_progress is not None else ()
                    ),
                    latest_final_recheck_ref=latest_recheck,
                    current_resource_versions=resource_versions,
                ),
            )
            gaps = unresolved_open_semantic_gaps(
                active_step.completion_criteria if active_step is not None else (),
                step_completion,
            )
            if gaps:
                return self._open_semantic_result(state, events, stage_input.capture, gaps)
            progress = commit_verified_task_progress(
                state=state,
                trace=cast(Any, events),
                parent=cast(Any, parent),
                step_completion=step_completion,
                task_planner_is_router=self.task_planner_is_router,
                task_spec=stage_input.envelope.task_spec,
                skill_complete=False,
            )
            return self._result(
                state,
                events,
                ProgressOutput(
                    stage_input.capture,
                    completion_committed=progress.step_completion_committed,
                    task_completion=task_completion,
                ),
                directive=(
                    LoopDirective.REPEAT_OBSERVATION if progress.step_completion_committed else LoopDirective.NEXT_STAGE
                ),
            )
        action = stage_input.action
        observation_service = PostActionObservationService(
            perception_session=self.perception_session,
            execution_loop=self.execution_loop,
            observation_builder=self.observation_builder,
            observation_store=self.observation_store,
            artifacts=self.artifacts,
        )
        observed = observation_service.capture(
            envelope=stage_input.envelope,
            state=state,
            state_view=stage_input.state_view,
            events=events,
        )
        post_snapshot = observed.capture
        canonical = observed.observation
        canonical_ref = observed.observation_ref
        observation_commits = observed.observation_commits
        report = self.execution_loop.verify(
            action.contract,
            action.receipt,
            post_snapshot.observation,
            structural_verification_enabled=self.structural_verification_enabled,
            disabled_reason="structural verification disabled by benchmark ablation",
        )
        if report.status == VerificationStatus.INCONCLUSIVE and self.structural_verification_enabled:
            repaired, report = observation_service.repair_verification(
                action=action,
                state=state,
                events=events,
                capture=post_snapshot,
                report=report,
            )
            post_snapshot = repaired.capture
            canonical = repaired.observation
            canonical_ref = repaired.observation_ref
            observation_commits = (
                *observation_commits,
                *repaired.observation_commits,
            )
        state.latest_verification = report
        outcome_commit = record_contract_action_outcome_trace(
            self.execution_loop,
            cast(Any, events),
            cast(Any, events.root()),
            action.contract,
            action.execution_observation,
            stage_input.state_view.version,
            action.receipt,
            report,
            post_snapshot.observation,
            action.skill_step_id or action.contract.affordance_id,
            state.phase,
        )
        if state.task_progress is not None:
            state.task_progress.record_action_outcome(outcome_commit.outcome)
            admit_observation_durable_evidence(canonical, state.task_progress.durable_evidence)
        current_evidence = observation_predicate_evidence(canonical)
        latest_recheck, resource_versions = observation_evidence_context_metadata(canonical)
        state.record_action_progress(
            action.action_signature,
            post_snapshot.observation.environment_revision,
            verification_passed=report.passed,
            effect_satisfied=verification_satisfies_effect(report),
            post_page_revision=post_snapshot.observation.page_revision,
        )
        verification_ref = self._write_verification(stage_input.envelope.task_id, state.step_count, report)
        if verification_ref is not None:
            events.artifact_index.append(verification_ref.path)
        self._record_route_outcome(events, action, report, post_snapshot)
        skill_result = TaskSkillProgressService(self.task_skill_runtime, self.evaluation_service).evaluate(
            action=action,
            task_spec=stage_input.envelope.task_spec,
            state=state,
            events=events,
            report=report,
            observation=post_snapshot.observation,
            verification_ref=verification_ref,
        )
        skill_complete = skill_result.complete
        skill_progress = skill_result.progress
        terminal = skill_result.terminal
        skill_task_completion = skill_result.task_completion
        task_completion = skill_task_completion or self.evaluation_service.evaluate_task_completion(
            task_spec=stage_input.envelope.task_spec,
            state=state,
            observation=post_snapshot.observation,
            report=report,
            result=state.final_result,
        )
        if task_completion is not None and skill_task_completion is None:
            self.evaluation_service.record_task_completion(events, state, task_completion)
        loop_evaluation = self.loop_evaluator.evaluate(
            receipt=action.receipt,
            report=report,
            observation=canonical,
            active_step=TaskPlanLifecycle.active_step_spec(state),
            task_completion=task_completion,
            recent_action_outcomes=(
                tuple(state.task_progress.recent_action_outcomes.records) if state.task_progress is not None else ()
            ),
            current_evidence=current_evidence,
            durable_evidence=(
                tuple(state.task_progress.durable_evidence.records) if state.task_progress is not None else ()
            ),
            latest_final_recheck_ref=latest_recheck,
            current_resource_versions=resource_versions,
        )
        loop_evaluation = replace(
            loop_evaluation,
            observation_continuation=self.continuation_policy.decide(canonical),
        )
        output = ProgressOutput(
            post_snapshot,
            canonical,
            canonical_ref,
            observation_commits,
            report,
            verification_ref,
            outcome_commit.outcome,
            task_completion=task_completion,
            loop_evaluation=loop_evaluation,
        )
        gaps = unresolved_open_semantic_gaps(
            TaskPlanLifecycle.active_step_spec(state).completion_criteria
            if TaskPlanLifecycle.active_step_spec(state) is not None
            else (),
            loop_evaluation.step_completion,
        )
        if gaps:
            return self._open_semantic_result(
                state,
                events,
                post_snapshot,
                gaps,
                output=replace(output, task_spec_gaps=gaps),
            )
        if terminal is not None:
            return self._result(
                state,
                events,
                output,
                terminal=terminal,
                task_completion=task_completion,
            )
        if report.passed:
            progress = commit_verified_task_progress(
                state=state,
                trace=cast(Any, events),
                parent=cast(Any, events.root()),
                step_completion=loop_evaluation.step_completion,
                task_planner_is_router=self.task_planner_is_router,
                task_spec=stage_input.envelope.task_spec,
                skill_complete=skill_complete,
                skill_progress=skill_progress,
            )
            if task_completion is not None and task_completion.completed:
                evaluation = self.evaluation_service.record_post_action(
                    events,
                    state,
                    report,
                    contract_id=action.contract.id,
                    active_step_status=(
                        ActiveStepEvaluationStatus.COMPLETED
                        if progress.step_completion_committed
                        else ActiveStepEvaluationStatus.INCOMPLETE
                    ),
                    task_completion_status=TaskCompletionEvaluationStatus.COMPLETED,
                    progress_committed=progress.step_completion_committed,
                    liveness_decision="terminal",
                )
                output = replace(output, evaluation=evaluation)
                return self._result(
                    state,
                    events,
                    output,
                    terminal=TerminalResult("", "task_completed", RuntimeStep.DONE),
                    task_completion=task_completion,
                )
            if progress.task_completion_requested:
                completion = task_completion
                if completion is None:
                    raise ValueError("task completion requires an admitted TaskSpec")
                evaluation = self.evaluation_service.record_post_action(
                    events,
                    state,
                    report,
                    contract_id=action.contract.id,
                    active_step_status=(
                        ActiveStepEvaluationStatus.COMPLETED
                        if progress.step_completion_committed
                        else ActiveStepEvaluationStatus.INCOMPLETE
                    ),
                    task_completion_status=(
                        TaskCompletionEvaluationStatus.COMPLETED
                        if completion.completed
                        else TaskCompletionEvaluationStatus.INCOMPLETE
                    ),
                    progress_committed=progress.step_completion_committed,
                    liveness_decision="terminal" if completion.completed else "replan",
                )
                output = replace(
                    output,
                    evaluation=evaluation,
                    task_completion=completion,
                )
                if completion.completed:
                    return self._result(
                        state,
                        events,
                        output,
                        terminal=TerminalResult("", "task_completed", RuntimeStep.DONE),
                        task_completion=completion,
                    )
                state.replan_count += 1
                project_working_phase(state, RuntimeStep.OBSERVING)
                return self._result(
                    state,
                    events,
                    output,
                    directive=LoopDirective.REPEAT_OBSERVATION,
                )
            evaluation = self.evaluation_service.record_post_action(
                events,
                state,
                report,
                contract_id=action.contract.id,
                active_step_status=(
                    ActiveStepEvaluationStatus.COMPLETED
                    if progress.step_completion_committed
                    else ActiveStepEvaluationStatus.INCOMPLETE
                ),
                task_completion_status=(
                    TaskCompletionEvaluationStatus.INCOMPLETE
                    if task_completion is not None
                    else TaskCompletionEvaluationStatus.NOT_EVALUATED
                ),
                progress_committed=progress.step_completion_committed,
                liveness_decision=("advance_step" if progress.step_completion_committed else "reconcile_active_step"),
            )
            output = replace(output, evaluation=evaluation)
            state.replan_count += 1
            project_working_phase(state, RuntimeStep.OBSERVING)
            return self._result(state, events, output, directive=LoopDirective.REPEAT_OBSERVATION)
        evaluation = self.evaluation_service.record_post_action(
            events,
            state,
            report,
            contract_id=action.contract.id,
            active_step_status=ActiveStepEvaluationStatus.NOT_EVALUATED,
            task_completion_status=(
                TaskCompletionEvaluationStatus.INCOMPLETE
                if task_completion is not None
                else TaskCompletionEvaluationStatus.NOT_EVALUATED
            ),
            progress_committed=False,
            liveness_decision="verification_failure",
        )
        output = replace(output, evaluation=evaluation)
        failure = self.evaluation_service.verification_failure(
            run_id=stage_input.envelope.task_id,
            task_spec=stage_input.envelope.task_spec,
            state=state,
            action=action,
            report=report,
            verification_ref=verification_ref,
            remaining_budgets=stage_input.remaining_budgets,
        )
        if not self.recovery_enabled:
            project_working_phase(state, RuntimeStep.FAILED)
            return self._result(
                state,
                events,
                output,
                terminal=TerminalResult(
                    failure.failure_id,
                    "verification_failed",
                    RuntimeStep.FAILED,
                    RuntimeErrorCode.VERIFICATION_FAILED,
                ),
            )
        return self._result(state, events, output, failure=failure)

    def _record_route_outcome(
        self,
        events: RuntimeEventBuffer,
        action: ProgressActionInput,
        report: VerificationReport,
        snapshot: PerceptionCapture,
    ) -> None:
        contract = action.contract
        candidate, plan = contract.grounding_candidate, contract.route_plan
        if candidate is None or plan is None or not plan.verifier_kinds:
            return
        scope = RouteScope(
            plan.environment_scope,
            plan.action_kind or contract.action,
            candidate.source,
            candidate.compatible_executor,
            plan.verifier_kinds,
        )
        outcome = RouteOutcome.from_verification(
            outcome_id=f"route-outcome:{contract.id}:{snapshot.observation.snapshot_id}",
            scope=scope,
            semantic_target_id=candidate.semantic_target_id,
            candidate_id=candidate.candidate_id,
            contract_id=contract.id,
            report=report,
            post_snapshot_id=snapshot.observation.snapshot_id,
            latency_ms=action.receipt.latency_ms,
            expected_cost=candidate.expected_cost,
        )
        self.route_calibrator.record(outcome)
        events.add(
            "RouteOutcomeRecorded",
            {
                "state": RuntimeStep.VERIFYING.value,
                "outcome_id": outcome.outcome_id,
                "status": outcome.status.value,
                "verification_status": outcome.verification_status.value,
                "trainable": outcome.status != RouteOutcomeStatus.INCONCLUSIVE,
                "semantic_target_id": outcome.semantic_target_id,
                "candidate_id": outcome.candidate_id,
                "contract_id": outcome.contract_id,
                "post_snapshot_id": outcome.post_snapshot_id,
                "evidence_ids": list(outcome.evidence_ids),
                "scope": {
                    "environment_family": scope.environment_family,
                    "action_kind": scope.action_kind,
                    "source": scope.source.value,
                    "executor": scope.executor,
                    "verifier_kinds": list(scope.verifier_kinds),
                },
                "latency_ms": outcome.latency_ms,
                "expected_cost": outcome.expected_cost,
            },
        )

    def _open_semantic_result(
        self,
        state: Any,
        events: RuntimeEventBuffer,
        capture: PerceptionCapture,
        gaps: tuple[TaskSpecGap, ...],
        *,
        output: ProgressOutput | None = None,
    ) -> StageResult[ProgressOutput]:
        state.final_result = {
            "clarification": gaps[0].clarification,
            "task_spec_gaps": [gap.model_dump(mode="json") for gap in gaps],
        }
        events.add(
            "OpenSemanticUnresolved",
            {
                "state": state.phase,
                "reason_code": OPEN_SEMANTIC_UNRESOLVED,
                "gap_ids": [gap.gap_id for gap in gaps],
            },
        )
        return self._result(
            state,
            events,
            output or ProgressOutput(capture, task_spec_gaps=gaps),
            terminal=TerminalResult(
                "",
                OPEN_SEMANTIC_UNRESOLVED,
                RuntimeStep.WAITING_CLARIFICATION,
            ),
        )

    @staticmethod
    def _result(
        state: Any,
        events: RuntimeEventBuffer,
        output: ProgressOutput,
        *,
        directive: LoopDirective = LoopDirective.NEXT_STAGE,
        failure: Any = None,
        terminal: TerminalResult | None = None,
        task_completion: TaskCompletionEvaluation | None = None,
    ) -> StageResult[ProgressOutput]:
        return StageResult(
            output=output,
            transition=RuntimeTransition(
                state_updates=state.changes(),
                artifact_refs=tuple(dict.fromkeys(events.artifact_index)),
                observation_commits=output.observation_commits,
                task_completion=task_completion,
            ),
            events=tuple(events.events),
            failure=failure,
            terminal=terminal,
            directive=(LoopDirective.TERMINAL if terminal is not None else directive),
        )

    def _write_verification(self, run_id: str, sequence: int, report: VerificationReport) -> ArtifactRef | None:
        return self.artifacts.write_verification(run_id, sequence, report) if self.artifacts else None
