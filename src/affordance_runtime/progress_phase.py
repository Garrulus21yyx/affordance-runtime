"""Pure post-observation and post-action progress stage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from time import time
from typing import Any, cast

from affordance_runtime.action_outcome_flow import record_contract_action_outcome_trace
from affordance_runtime.active_perception import ActivePerceptionRequest, ProbeReceipt
from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.observation_store import (
    InMemoryObservationStore,
    ObservationCommit,
    ObservationRef,
)
from affordance_runtime.perception_session import (
    PerceptionCapture,
    PerceptionCaptureRequest,
    PerceptionSession,
)
from affordance_runtime.route_calibration import RouteCalibrator, RouteOutcome, RouteOutcomeStatus, RouteScope
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_committer import project_working_phase
from affordance_runtime.runtime_evidence import semantic_progress_fingerprint, verification_satisfies_effect
from affordance_runtime.simplified_runtime_contracts import ActionOutcome
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEventBuffer,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits
from affordance_runtime.task_plan_progress_flow import (
    commit_current_state_completion,
    commit_task_skill_terminal_progress,
    commit_verified_task_progress,
)
from affordance_runtime.task_planning import SubgoalVerifierPort
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import TaskCompletionEvaluation
from affordance_runtime.verification.mechanical import VerificationReport, VerificationStatus
from affordance_runtime.verification.task_completion import TaskCompletionEvaluator
from affordance_runtime.verification_report_adapter import (
    admit_completion_evidence,
    output_source_bindings,
)


@dataclass(frozen=True)
class ProgressActionInput:
    contract: ActionContract
    receipt: ExecutionReceipt
    execution_observation: Observation
    action_signature: str
    skill_step_id: str = ""


class ActionEffectEvaluationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


class ActiveStepEvaluationStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    NOT_EVALUATED = "not_evaluated"


class TaskCompletionEvaluationStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class PostActionEvaluation:
    contract_id: str
    action_effect: ActionEffectEvaluationStatus
    active_step: ActiveStepEvaluationStatus
    task_completion: TaskCompletionEvaluationStatus
    criterion_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    progress_committed: bool = False
    liveness_decision: str = ""


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


@dataclass(frozen=True)
class ProgressStage:
    execution_loop: ContractExecutionLoop
    perception_session: PerceptionSession
    subgoal_verifier: SubgoalVerifierPort
    route_calibrator: RouteCalibrator
    observation_builder: CanonicalObservationBuilder = CanonicalObservationBuilder()
    observation_store: InMemoryObservationStore = field(default_factory=InMemoryObservationStore)
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None
    artifacts: ArtifactStore | None = None
    structural_verification_enabled: bool = True
    recovery_enabled: bool = True
    task_planner_is_router: bool = True

    def run(self, stage_input: ProgressStageInput) -> StageResult[ProgressOutput]:
        state = cast(Any, stage_input.state_view.projection())
        events = RuntimeEventBuffer()
        parent = events.root()
        if stage_input.action is None:
            task_completion = self._evaluate_task_completion(
                task_spec=stage_input.envelope.task_spec,
                state=state,
                observation=stage_input.capture.observation,
                report=None,
                result=state.final_result,
            )
            if task_completion is not None:
                self._record_task_completion_evaluation(events, state, task_completion)
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
            committed = commit_current_state_completion(
                stage_input.envelope.task_spec,
                state,
                stage_input.observation,
                stage_input.budget,
                cast(Any, events),
                cast(Any, parent),
            )
            return self._result(
                state,
                events,
                ProgressOutput(
                    stage_input.capture,
                    completion_committed=committed is not None,
                    task_completion=task_completion,
                ),
                directive=(LoopDirective.REPEAT_OBSERVATION if committed is not None else LoopDirective.NEXT_STAGE),
            )
        action = stage_input.action
        post_snapshot, canonical, canonical_ref, observation_refs, observation_commits = self._capture(
            stage_input, state, events, parent
        )
        report = self.execution_loop.verify(
            action.contract,
            action.receipt,
            post_snapshot.observation,
            structural_verification_enabled=self.structural_verification_enabled,
            disabled_reason="structural verification disabled by benchmark ablation",
        )
        if report.status == VerificationStatus.INCONCLUSIVE and self.structural_verification_enabled:
            post_snapshot, canonical, canonical_ref, report, repair_commit = self._repair_verification(
                stage_input, state, events, post_snapshot, report
            )
            if repair_commit is not None:
                observation_commits = (*observation_commits, repair_commit)
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
        skill_complete, skill_progress, terminal, skill_task_completion = self._commit_task_skill(
            stage_input, state, events, report, post_snapshot, verification_ref
        )
        task_completion = skill_task_completion or self._evaluate_task_completion(
            task_spec=stage_input.envelope.task_spec,
            state=state,
            observation=post_snapshot.observation,
            report=report,
            result=state.final_result,
        )
        if task_completion is not None and skill_task_completion is None:
            self._record_task_completion_evaluation(events, state, task_completion)
        output = ProgressOutput(
            post_snapshot,
            canonical,
            canonical_ref,
            observation_commits,
            report,
            verification_ref,
            outcome_commit.outcome,
            task_completion=task_completion,
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
                subgoal_verifier=self.subgoal_verifier,
                verification=report,
                observation=post_snapshot.observation,
                task_planner_is_router=self.task_planner_is_router,
                skill_complete=skill_complete,
                skill_progress=skill_progress,
            )
            if task_completion is not None and task_completion.completed:
                evaluation = self._record_post_action_evaluation(
                    events,
                    state,
                    report,
                    contract_id=action.contract.id,
                    active_step_status=(
                        ActiveStepEvaluationStatus.COMPLETED
                        if progress.subgoal_completion_committed
                        else ActiveStepEvaluationStatus.INCOMPLETE
                    ),
                    task_completion_status=TaskCompletionEvaluationStatus.COMPLETED,
                    progress_committed=progress.subgoal_completion_committed,
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
                evaluation = self._record_post_action_evaluation(
                    events,
                    state,
                    report,
                    contract_id=action.contract.id,
                    active_step_status=(
                        ActiveStepEvaluationStatus.COMPLETED
                        if progress.subgoal_completion_committed
                        else ActiveStepEvaluationStatus.INCOMPLETE
                    ),
                    task_completion_status=(
                        TaskCompletionEvaluationStatus.COMPLETED
                        if completion.completed
                        else TaskCompletionEvaluationStatus.INCOMPLETE
                    ),
                    progress_committed=progress.subgoal_completion_committed,
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
            evaluation = self._record_post_action_evaluation(
                events,
                state,
                report,
                contract_id=action.contract.id,
                active_step_status=(
                    ActiveStepEvaluationStatus.COMPLETED
                    if progress.subgoal_completion_committed
                    else ActiveStepEvaluationStatus.INCOMPLETE
                ),
                task_completion_status=(
                    TaskCompletionEvaluationStatus.INCOMPLETE
                    if task_completion is not None
                    else TaskCompletionEvaluationStatus.NOT_EVALUATED
                ),
                progress_committed=progress.subgoal_completion_committed,
                liveness_decision=(
                    "advance_step"
                    if progress.subgoal_completion_committed
                    else "reconcile_active_step"
                ),
            )
            output = replace(output, evaluation=evaluation)
            state.replan_count += 1
            project_working_phase(state, RuntimeStep.OBSERVING)
            return self._result(state, events, output, directive=LoopDirective.REPEAT_OBSERVATION)
        evaluation = self._record_post_action_evaluation(
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
        failure = self._verification_failure(stage_input, state, action, report, verification_ref)
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

    def _capture(
        self,
        stage_input: ProgressStageInput,
        state: Any,
        events: RuntimeEventBuffer,
        parent: object,
    ) -> tuple[
        PerceptionCapture,
        UnifiedObservation,
        ObservationRef,
        tuple[str, ...],
        tuple[ObservationCommit, ...],
    ]:
        snapshot = self.perception_session.capture(
            PerceptionCaptureRequest(
                envelope=stage_input.envelope,
                sequence=state.observation_count + 1,
                active_subgoal="",
                failed_sources=_failed_sources(stage_input.state_view),
            )
        )
        canonical, canonical_ref, commit = self._canonicalize(snapshot)
        ref = self._write_observation(stage_input.envelope.task_id, state.observation_count, snapshot)
        refs = tuple(dict.fromkeys((*( [ref.path] if ref else []), *snapshot.observation.artifact_refs)))
        events.artifact_index.extend(refs)
        events.add(
            "PostActionObservationCaptured",
            {
                "state": state.phase,
                "snapshot_id": snapshot.observation.snapshot_id,
                "page_revision": snapshot.observation.page_revision,
                "artifact_refs": list(refs),
            },
        )
        del parent
        return snapshot, canonical, canonical_ref, refs, (commit,)

    def _repair_verification(
        self,
        stage_input: ProgressStageInput,
        state: Any,
        events: RuntimeEventBuffer,
        snapshot: PerceptionCapture,
        report: VerificationReport,
    ) -> tuple[
        PerceptionCapture,
        UnifiedObservation,
        ObservationRef,
        VerificationReport,
        ObservationCommit | None,
    ]:
        action = cast(ProgressActionInput, stage_input.action)
        sources = tuple(
            dict.fromkeys(
                item.source
                for item in snapshot.source_observations
                if item.source in {GroundingSource.DOM, GroundingSource.ACCESSIBILITY, GroundingSource.API}
            )
        ) or (GroundingSource.DOM, GroundingSource.ACCESSIBILITY)
        request = ActivePerceptionRequest(
            entity_key=action.contract.affordance_id,
            property_key="verification",
            requested_sources=sources,
            reason="verifier is inconclusive and requires fresh independent structural evidence",
            max_observations=1,
        )
        events.add("VerificationEvidenceRepairRequested", {"state": state.phase, "contract_id": action.contract.id, "verification_status": report.status.value})
        events.add(
            "ActivePerceptionPlanned",
            {
                "state": state.phase,
                "reason": request.reason,
                "requested_sources": [item.value for item in request.requested_sources],
            },
        )
        events.add(
            "ProbeStarted",
            {"state": state.phase, "entity_key": request.entity_key, "property_key": request.property_key},
        )
        try:
            repaired = self.perception_session.capture_targeted((request,))
        except Exception:
            events.add("ProbeCompleted", {"state": state.phase, "success": False})
            canonical, ref, _commit = self._canonicalize(snapshot)
            return snapshot, canonical, ref, report, None
        if repaired.observation.snapshot_id == snapshot.observation.snapshot_id:
            canonical, ref, _commit = self._canonicalize(snapshot)
            return snapshot, canonical, ref, report, None
        canonical, canonical_ref, commit = self._canonicalize(repaired)
        now = time()
        state.latest_probe_receipt = ProbeReceipt(
                command_id=f"verification-probe:{action.contract.id}",
                started_at_s=now,
                completed_at_s=now,
                observation_epoch_id=repaired.observation.snapshot_id,
                source=request.requested_sources[0],
                success=True,
                artifact_refs=tuple(repaired.observation.artifact_refs),
        )
        state.active_perception_count += 1
        events.add(
            "TargetedPerceptionCaptured",
            {"state": state.phase, "snapshot_id": repaired.observation.snapshot_id},
        )
        events.add("ProbeCompleted", {"state": state.phase, "success": True})
        repaired_report = self.execution_loop.verify(
            action.contract,
            action.receipt,
            repaired.observation,
            structural_verification_enabled=True,
            disabled_reason="",
        )
        events.add("VerificationEvidenceReevaluated", {"state": state.phase, "contract_id": action.contract.id, "verification_status": repaired_report.status.value, "snapshot_id": repaired.observation.snapshot_id})
        return repaired, canonical, canonical_ref, repaired_report, commit

    def _commit_task_skill(
        self,
        stage_input: ProgressStageInput,
        state: Any,
        events: RuntimeEventBuffer,
        report: VerificationReport,
        snapshot: PerceptionCapture,
        verification_ref: ArtifactRef | None,
    ) -> tuple[
        bool,
        TaskSkillRunState | None,
        TerminalResult | None,
        TaskCompletionEvaluation | None,
    ]:
        action = cast(ProgressActionInput, stage_input.action)
        runtime = self.task_skill_runtime
        if not action.skill_step_id or runtime is None:
            return False, None, None, None
        if report.passed:
            skill_report = runtime.verify_active_step(
                state,
                step_id=action.skill_step_id,
                verification=report,
                observation=snapshot.observation,
            )
            if not skill_report.passed:
                runtime.fallthrough(state, skill_report.match.reason)
                events.add("TaskSkillStepEvidenceRejected", {"state": state.phase, "skill_id": skill_report.skill_id, "version": skill_report.skill_version, "step_id": skill_report.step_id, "criteria_match": asdict(skill_report.match)})
                self._trace_skill_fallthrough(events, state, runtime, skill_report.match.reason, action.skill_step_id)
                return False, _skill_progress(runtime, state), None, None
            complete = runtime.checkpoint_verified(
                state,
                report=skill_report,
                artifact_refs=((verification_ref.path,) if verification_ref else ()),
            )
            progress = _skill_progress(runtime, state)
            events.add("TaskSkillStepCompleted", {"state": state.phase, "skill_id": progress.skill_id if progress else "", "version": progress.version if progress else "", "step_id": action.skill_step_id, "completed_step_ids": list(progress.completed_step_ids) if progress else [], "evidence": list(progress.evidence) if progress else [], "criterion_evidence_links": [asdict(item) for item in skill_report.match.links]})
            if complete and state.task_plan is None:
                if action.contract.grounding_candidate is not None:
                    state.complete_grounding_recovery(action.contract.grounding_candidate.semantic_target_id)
                commit = commit_task_skill_terminal_progress(state=state, progress=progress, trace=cast(Any, events), parent=cast(Any, events.root()))
                completion = self._evaluate_task_completion(
                    task_spec=stage_input.envelope.task_spec,
                    state=state,
                    observation=snapshot.observation,
                    report=report,
                    result=commit.result_payload(),
                )
                if completion is None:
                    raise ValueError("task completion requires an admitted TaskSpec")
                self._record_task_completion_evaluation(events, state, completion)
                self._record_post_action_evaluation(
                    events,
                    state,
                    report,
                    contract_id=action.contract.id,
                    active_step_status=ActiveStepEvaluationStatus.COMPLETED,
                    task_completion_status=(
                        TaskCompletionEvaluationStatus.COMPLETED
                        if completion.completed
                        else TaskCompletionEvaluationStatus.INCOMPLETE
                    ),
                    progress_committed=True,
                    liveness_decision="terminal" if completion.completed else "replan",
                )
                if completion.completed:
                    return (
                        complete,
                        progress,
                        TerminalResult("", "task_completed", RuntimeStep.DONE),
                        completion,
                    )
                return complete, progress, None, completion
            return complete, progress, None, None
        reason = f"TaskSkill step verification {report.status.value}"
        runtime.fallthrough(state, reason)
        progress = _skill_progress(runtime, state)
        events.add("TaskSkillStepFailed", {"state": state.phase, "skill_id": progress.skill_id if progress else "", "step_id": action.skill_step_id, "verification": report.status.value})
        self._trace_skill_fallthrough(events, state, runtime, reason, action.skill_step_id)
        return False, progress, None, None

    @staticmethod
    def _trace_skill_fallthrough(events: RuntimeEventBuffer, state: Any, runtime: object, reason: str, step_id: str) -> None:
        progress = _skill_progress(runtime, state)
        events.add("TaskSkillFellThrough", {"state": state.phase, "skill_id": progress.skill_id if progress else "", "version": progress.version if progress else "", "step_id": step_id, "reason": reason, "preserved_completed_step_ids": list(progress.completed_step_ids) if progress else [], "preserved_evidence": list(progress.evidence) if progress else [], "fallback": "system_2"})

    def _record_route_outcome(self, events: RuntimeEventBuffer, action: ProgressActionInput, report: VerificationReport, snapshot: PerceptionCapture) -> None:
        contract = action.contract
        candidate, plan = contract.grounding_candidate, contract.route_plan
        if candidate is None or plan is None or not plan.verifier_kinds:
            return
        scope = RouteScope(plan.environment_scope, plan.action_kind or contract.action, candidate.source, candidate.compatible_executor, plan.verifier_kinds)
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
        events.add("RouteOutcomeRecorded", {"state": RuntimeStep.VERIFYING.value, "outcome_id": outcome.outcome_id, "status": outcome.status.value, "verification_status": outcome.verification_status.value, "trainable": outcome.status != RouteOutcomeStatus.INCONCLUSIVE, "semantic_target_id": outcome.semantic_target_id, "candidate_id": outcome.candidate_id, "contract_id": outcome.contract_id, "post_snapshot_id": outcome.post_snapshot_id, "evidence_ids": list(outcome.evidence_ids), "scope": {"environment_family": scope.environment_family, "action_kind": scope.action_kind, "source": scope.source.value, "executor": scope.executor, "verifier_kinds": list(scope.verifier_kinds)}, "latency_ms": outcome.latency_ms, "expected_cost": outcome.expected_cost})

    def _verification_failure(self, stage_input: ProgressStageInput, state: Any, action: ProgressActionInput, report: VerificationReport, verification_ref: ArtifactRef | None):
        plan = state.task_plan
        return make_failure_envelope(
            run_id=stage_input.envelope.task_id,
            phase=FailurePhase.VERIFICATION,
            failure_class=FailureClass.VERIFICATION,
            error_code=RuntimeErrorCode.VERIFICATION_FAILED,
            message=report.reason or RuntimeErrorCode.VERIFICATION_FAILED.value,
            state_version=state.version,
            task_revision=plan.task_revision if plan is not None else stage_input.envelope.task_spec.revision if stage_input.envelope.task_spec is not None else 1,
            plan_version=plan.plan_version if plan is not None else 0,
            active_subgoal_id=state.task_progress.active_subgoal_id if state.task_progress is not None else "",
            observation_epoch_id=state.current_snapshot_id,
            snapshot_id=state.current_snapshot_id,
            contract=action.contract,
            receipt=action.receipt,
            expected_effect=action.contract.intent,
            evidence_refs=((verification_ref.path,) if verification_ref else ()),
            verification_ref=verification_ref.path if verification_ref else "",
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=((state.current_disproved_assumption,) if state.current_disproved_assumption else ()),
            remaining_budgets=stage_input.remaining_budgets,
            progress_fingerprint=semantic_progress_fingerprint(state),
        )

    @staticmethod
    def _record_post_action_evaluation(
        events: RuntimeEventBuffer,
        state: Any,
        report: VerificationReport,
        *,
        contract_id: str,
        active_step_status: ActiveStepEvaluationStatus,
        task_completion_status: TaskCompletionEvaluationStatus,
        progress_committed: bool,
        liveness_decision: str,
    ) -> PostActionEvaluation:
        criterion_ids = tuple(
            dict.fromkeys(
                criterion_id
                for evidence in report.evidence
                for criterion_id in evidence.criterion_ids
            )
        )
        requirement_ids = tuple(
            dict.fromkeys(
                requirement_id
                for evidence in report.evidence
                for requirement_id in evidence.requirement_ids
            )
        )
        evidence_refs = tuple(
            dict.fromkeys(
                evidence.evidence_id
                for evidence in report.evidence
                if evidence.evidence_id
            )
        )
        evaluation = PostActionEvaluation(
            contract_id=contract_id,
            action_effect=(
                ActionEffectEvaluationStatus.PASSED
                if report.passed
                else ActionEffectEvaluationStatus(report.status.value)
            ),
            active_step=active_step_status,
            task_completion=task_completion_status,
            criterion_ids=criterion_ids,
            requirement_ids=requirement_ids,
            evidence_refs=evidence_refs,
            progress_committed=progress_committed,
            liveness_decision=liveness_decision,
        )
        events.add(
            "PostActionEvaluated",
            {
                "state": state.phase,
                "contract_id": evaluation.contract_id,
                "action_effect_status": evaluation.action_effect.value,
                "active_step_status": evaluation.active_step.value,
                "task_completion_status": evaluation.task_completion.value,
                "criterion_ids": list(evaluation.criterion_ids),
                "requirement_ids": list(evaluation.requirement_ids),
                "evidence_refs": list(evaluation.evidence_refs),
                "evidence": [asdict(item) for item in report.evidence],
                "progress_committed": progress_committed,
                "liveness_decision": liveness_decision,
            },
        )
        return evaluation

    @staticmethod
    def _evaluate_task_completion(
        *,
        task_spec: object | None,
        state: Any,
        observation: Observation,
        report: VerificationReport | None,
        result: dict[str, object],
    ) -> TaskCompletionEvaluation | None:
        if task_spec is None:
            return None
        typed_task_spec = cast(Any, task_spec)
        admitted = admit_completion_evidence(
            observation=observation,
            report=report,
        )
        retained = getattr(state, "completion_criterion_evaluations", {})
        relevant_ids = TaskCompletionEvaluator.criterion_ids(typed_task_spec)
        final_recheck_ids = frozenset(typed_task_spec.final_recheck_criterion_ids)
        for evaluation in admitted:
            if (
                evaluation.criterion_id in relevant_ids
                and evaluation.criterion_id not in final_recheck_ids
            ):
                retained[evaluation.criterion_id] = evaluation
        current_index = {item.criterion_id: item for item in admitted}
        criterion_results = tuple(
            current_index.get(criterion_id, evaluation)
            for criterion_id, evaluation in retained.items()
        ) + tuple(
            evaluation
            for criterion_id, evaluation in current_index.items()
            if criterion_id not in retained
        )
        return TaskCompletionEvaluator().evaluate(
            task_spec=typed_task_spec,
            criterion_results=criterion_results,
            result_payload=result,
            output_source_bindings=output_source_bindings(observation),
            uncertain_external_effects=tuple(
                str(item)
                for item in getattr(state, "uncertain_external_effects", ())
                if str(item)
            ),
        )

    @staticmethod
    def _record_task_completion_evaluation(
        events: RuntimeEventBuffer,
        state: Any,
        evaluation: TaskCompletionEvaluation,
    ) -> None:
        events.add(
            "TaskCompletionEvaluated",
            {
                "state": state.phase,
                "status": evaluation.status.value,
                "root_criterion_id": evaluation.root_criterion_id,
                "missing_required_outputs": list(evaluation.missing_required_outputs),
                "missing_rechecks": list(evaluation.missing_rechecks),
                "constraint_violations": list(evaluation.constraint_violations),
                "uncertain_external_effects": list(evaluation.uncertain_external_effects),
            },
        )

    @staticmethod
    def _result(state: Any, events: RuntimeEventBuffer, output: ProgressOutput, *, directive: LoopDirective = LoopDirective.NEXT_STAGE, failure: Any = None, terminal: TerminalResult | None = None, task_completion: TaskCompletionEvaluation | None = None) -> StageResult[ProgressOutput]:
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

    def _canonicalize(
        self, capture: PerceptionCapture
    ) -> tuple[UnifiedObservation, ObservationRef, ObservationCommit]:
        canonical = self.observation_builder.build(capture)
        ref = self.observation_store.put(canonical)
        return (
            canonical,
            ref,
            ObservationCommit(
                ref,
                canonical.environment_revision,
                canonical.page_revision,
            ),
        )

    def _write_observation(self, run_id: str, sequence: int, snapshot: PerceptionCapture) -> ArtifactRef | None:
        return self.artifacts.write_observation(run_id, sequence, snapshot.observation) if self.artifacts else None

    def _write_verification(self, run_id: str, sequence: int, report: VerificationReport) -> ArtifactRef | None:
        return self.artifacts.write_verification(run_id, sequence, report) if self.artifacts else None


def _skill_progress(runtime: object | None, state: object) -> TaskSkillRunState | None:
    progress_for = getattr(runtime, "progress_for", None)
    progress = progress_for(state) if callable(progress_for) else None
    return progress if isinstance(progress, TaskSkillRunState) else None


def _failed_sources(view: RuntimeStateSnapshot) -> frozenset[GroundingSource]:
    result: set[GroundingSource] = set()
    for lineage in view.current_grounding_fallback.values():
        try:
            result.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            pass
    return frozenset(result)
