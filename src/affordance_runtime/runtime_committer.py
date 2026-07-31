"""Single commit boundary for immutable stage results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, TypeVar

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureEnvelope, RemainingRecoveryBudgets
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.perception_phase import (
    PerceptionStage,
    PerceptionStageInput,
    PerceptionStateView,
    _source_arbitration_events,
)
from affordance_runtime.perception_session import PerceptionCaptureRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.runtime_evidence import semantic_progress_fingerprint
from affordance_runtime.stage_protocol import (
    OwnerHandoff,
    ProgressHandoff,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    StepPlannerHandoff,
    TaskPlannerHandoff,
    TerminalResult,
    UserInputRequest,
    build_failure_owner_handoff,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


class RuntimeBudgetView(Protocol):
    @property
    def max_steps(self) -> int: ...

    @property
    def max_observations(self) -> int: ...

    @property
    def max_recoveries(self) -> int: ...

    @property
    def max_replans(self) -> int: ...

    @property
    def max_effectful_actions(self) -> int: ...

    @property
    def max_active_perception_observations(self) -> int: ...


T = TypeVar("T")


@dataclass
class RuntimeCommitSession:
    """Run-scoped handle for the sole StateKernel/TraceDag writer."""

    committer: RuntimeCommitter
    result_builder: Any
    recovery_stage: Any
    envelope: RunRequest
    budget: RuntimeBudgetView
    state: StateKernel
    trace: TraceDag
    parent: TraceNode
    latest_verification: VerificationReport | None = None

    @classmethod
    def start(
        cls,
        committer: RuntimeCommitter,
        result_builder: Any,
        recovery_stage: Any,
        envelope: RunRequest,
        budget: RuntimeBudgetView,
        upstream_trace: TraceDag | None,
    ) -> RuntimeCommitSession:
        from affordance_runtime.runtime_loop_phase import RuntimeLoopPhase

        started = RuntimeLoopPhase().start(
            envelope=envelope,
            upstream_trace=upstream_trace,
            runtime_profile_digest=recovery_stage.runtime_profile_digest,
            loaded_profile_artifact_ids=recovery_stage.loaded_profile_artifact_ids,
        )
        return cls(
            committer,
            result_builder,
            recovery_stage,
            envelope,
            budget,
            started.state,
            started.trace,
            committer.commit_loop_event(started.trace, started.event),
        )

    @property
    def remaining_budgets(self) -> Any:
        return perception_state_view(
            self.envelope, self.state, self.budget
        ).remaining_budgets

    def finish(self, terminal: TerminalResult) -> Any:
        from affordance_runtime.runtime_result_phase import finish_phase_terminal

        return finish_phase_terminal(
            self.result_builder,
            self.envelope,
            self.state,
            self.trace,
            terminal,
            self.parent,
            self.latest_verification,
        )

    def check_budget(self) -> Any | None:
        from affordance_runtime.runtime_loop_phase import RuntimeLoopPhase

        result = RuntimeLoopPhase().check_budget(state=self.state, budget=self.budget)
        if result is None:
            return None
        self.committer.commit_loop_transition(self.state, result.transition)
        self.parent = self.committer.commit_loop_event(
            self.trace, result.event, self.parent
        )
        return self.result_builder.finish(
            self.envelope,
            self.state,
            self.trace,
            result.status,
            self.parent,
            result.error_code,
            self.latest_verification,
        )

    def commit(self, result: StageResult[Any]) -> None:
        self.parent = self.committer.commit(
            self.state, self.trace, self.parent, result
        )

    def enter_planning(self) -> None:
        from affordance_runtime.runtime_loop_phase import RuntimeLoopPhase

        self.committer.commit_loop_transition(
            self.state,
            RuntimeLoopPhase().enter_planning(
                has_task_plan=self.state.task_plan is not None
            ),
        )

    def fail_observation(self, failure: FailureEnvelope) -> Any:
        self.commit(
            StageResult(transition=RuntimeTransition(phase=RuntimeStep.FAILED))
        )
        return self.finish(
            TerminalResult(
                failure.failure_id,
                "observation_failed",
                RuntimeStep.FAILED,
                RuntimeErrorCode.PRECONDITION_FAILED,
            )
        )

    def recover(
        self,
        failure: FailureEnvelope,
        commands: frozenset[Any],
        *,
        preserve_terminal: bool = False,
        terminate_all_handoffs: bool = False,
    ) -> Any | None:
        from affordance_runtime.recovery_phase import RecoveryStageInput
        from affordance_runtime.recovery_protocol import (
            FailureOwner,
            RecoveryKind,
            classify_failure,
        )

        classification = classify_failure(failure)
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            handoff, self.parent = self.committer.commit_failure_owner(
                self.state, self.trace, self.parent, failure, classification
            )
        else:
            result = self.recovery_stage.run(
                RecoveryStageInput(
                    failure=failure,
                    state_view=runtime_state_snapshot(self.state),
                    available_commands=commands,
                    runtime_profile_digest=self.recovery_stage.runtime_profile_digest,
                    loaded_profile_artifact_ids=(
                        self.recovery_stage.loaded_profile_artifact_ids
                    ),
                )
            )
            self.commit(result)
            if result.terminal is not None:
                handoff = result.terminal
            elif result.output is not None:
                handoff = result.output.recovery_kind
            else:
                raise RuntimeError(
                    "recovery stage returned neither output nor terminal"
                )
        if isinstance(handoff, RecoveryKind):
            return None
        if (
            isinstance(handoff, ProgressHandoff)
            and handoff.reason_code == "progress_credit_invariant"
        ):
            return self.finish(
                TerminalResult(
                    handoff.failure_id,
                    handoff.reason_code,
                    RuntimeStep.FAILED,
                    RuntimeErrorCode.PROGRESS_CREDIT_INVARIANT,
                )
            )
        if not terminate_all_handoffs and not isinstance(
            handoff, (TerminalResult, UserInputRequest)
        ):
            return None
        if preserve_terminal and isinstance(handoff, TerminalResult):
            return self.finish(handoff)
        try:
            error = RuntimeErrorCode(failure.error_code)
        except ValueError:
            error = {
                "perception": RuntimeErrorCode.PRECONDITION_FAILED,
                "planning": RuntimeErrorCode.PLANNER_FAILED,
                "verification": RuntimeErrorCode.VERIFICATION_FAILED,
            }.get(failure.phase.value, RuntimeErrorCode.EXECUTION_FAILED)
        return self.finish(
            TerminalResult(
                handoff.failure_id,
                handoff.reason_code,
                RuntimeStep(self.state.phase),
                error,
            )
        )

    def abort_pending_recovery(self, failure: FailureEnvelope) -> Any:
        """Commit terminal exhaustion after a recovery action fails."""

        self.commit(
            StageResult(
                transition=RuntimeTransition(
                    phase=RuntimeStep.ABORTED,
                    clear_recovery_decision=True,
                ),
                events=(
                    RuntimeEvent(
                        "FailureOwnerRouted",
                        {
                            "state": RuntimeStep.RECOVERING.value,
                            "failure_id": failure.failure_id,
                            "owner": "terminal",
                            "handoff_type": "TerminalResult",
                            "reason_code": "runtime_recovery_failed",
                        },
                    ),
                ),
            )
        )
        return self.finish(
            TerminalResult(
                failure.failure_id,
                failure.error_code,
                RuntimeStep.ABORTED,
                RuntimeErrorCode(failure.error_code),
            )
        )


@dataclass(frozen=True)
class RuntimeCommitter:
    def commit_loop_transition(self, state: StateKernel, transition: Any) -> None:
        state.transition(transition.phase.value)
        if transition.activate_next_step:
            state.activate_next_step()

    def commit_loop_event(
        self,
        trace: TraceDag,
        event: Any,
        parent: TraceNode | None = None,
    ) -> TraceNode:
        parent_ids = event.parent_ids
        if not parent_ids and parent is not None:
            parent_ids = (parent.id,)
        return trace.add(
            event.kind,
            event.payload,
            parents=list(parent_ids) if parent_ids else None,
        )

    def commit_failure_owner(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        failure: Any,
        classification: Any,
    ) -> tuple[OwnerHandoff, TraceNode]:
        handoff = build_failure_owner_handoff(
            failure, classification.owner, classification.reason_code
        )
        failed_assumption = f"{failure.phase.value}:{failure.error_code}:{failure.message}"
        if (
            isinstance(handoff, (StepPlannerHandoff, TaskPlannerHandoff))
            and failed_assumption == state.current_disproved_assumption
        ):
            handoff = TerminalResult(
                failure.failure_id,
                f"{handoff.reason_code}_owner_handoff_exhausted",
            )
        state.current_failure = failure
        state.current_recovery_decision = None
        state.current_recovery_outcome = None
        parent = trace.add(
            "FailureDetected",
            {"state": state.phase, "failure": failure.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "FailureOwnerRouted",
            {
                "state": state.phase,
                "failure_id": failure.failure_id,
                "owner": handoff.owner.value,
                "reason_code": handoff.reason_code,
                "handoff_type": type(handoff).__name__,
            },
            parents=[parent.id],
        )
        if isinstance(handoff, (StepPlannerHandoff, TaskPlannerHandoff)):
            state.replan_count += 1
            state.record_disproved_assumption(failed_assumption)
            if state.phase != RuntimeStep.OBSERVING.value:
                state.transition(RuntimeStep.OBSERVING.value)
        elif isinstance(handoff, UserInputRequest):
            state.transition(RuntimeStep.WAITING_CLARIFICATION.value)
        elif isinstance(handoff, TerminalResult):
            state.transition(handoff.status.value)
        return handoff, parent

    def commit(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        result: StageResult[T],
    ) -> TraceNode:
        if result.failure is not None:
            state.current_failure = result.failure
        transition = result.transition
        if transition is not None:
            if transition.state_updates is not None:
                for name, value in transition.state_updates.items():
                    setattr(state, name, deepcopy(value))
            for intermediate in transition.intermediate_phases:
                if state.phase != intermediate.value:
                    self._commit_phase(state, intermediate)
            if transition.phase is not None and state.phase != transition.phase.value:
                self._commit_phase(state, transition.phase)
            for observation in transition.observations:
                state.remember_observation(observation)
            if transition.perception_update:
                state.evidence_gaps = transition.evidence_gaps
                state.active_probe_plan = transition.active_probe_plan
                if transition.probe_receipts:
                    state.latest_probe_receipt = transition.probe_receipts[-1]
                state.perception_resolution = transition.perception_resolution
                state.active_perception_count += transition.active_perception_count_delta
            if transition.latest_verification is not None:
                state.latest_verification = transition.latest_verification
            if transition.task_plan_transition is not None:
                plan_transition = transition.task_plan_transition
                if plan_transition.previous_plan is None:
                    state.install_task_plan(plan_transition.plan)
                else:
                    state.replace_task_plan(plan_transition.plan)
                state.activate_next_step()
            if transition.planner_proposal is not None:
                state.record_planner_proposal(dict(transition.planner_proposal))
            if transition.current_contract is not None:
                state.current_contract = transition.current_contract
            if transition.receipt is not None:
                state.record_receipt(transition.receipt)
            state.step_count += transition.step_count_delta
            for _ in range(transition.subgoal_action_count_delta):
                state.record_subgoal_action()
            state.effectful_action_count += transition.effectful_action_count_delta
            state.replan_count += transition.replan_count_delta
            state.version += transition.version_delta
            if transition.progress_guard is not None:
                reason, signature = transition.progress_guard
                from affordance_runtime.state_kernel import ProgressGuardReason

                state.record_progress_guard(ProgressGuardReason(reason), signature)
            if transition.clear_recovery_decision:
                state.current_recovery_decision = None
            if transition.final_result is not None:
                state.final_result = dict(transition.final_result)
            trace.artifact_index.extend(
                path for path in transition.artifact_refs if path
            )
        return self.commit_events(trace, parent, result.events)

    def commit_action(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        result: StageResult[Any],
    ) -> tuple[TraceNode, bool]:
        """Commit one ActionStage result and settle any pending mechanical recovery."""

        from affordance_runtime.recovery_protocol import RecoveryKind

        pending_recovery_failed = False
        output = result.output
        decision = state.current_recovery_decision
        if (
            result.failure is not None
            and result.failure.phase.value == "grounding_binding"
            and decision is not None
            and decision.kind in {RecoveryKind.REGROUND, RecoveryKind.REROUTE}
        ):
            parent = self._fail_pending_recovery(state, trace, parent, result.failure.error_code)
            pending_recovery_failed = True
        elif (
            output is not None
            and decision is not None
            and decision.kind in {RecoveryKind.REGROUND, RecoveryKind.REROUTE}
        ):
            parent, pending_recovery_failed = self._complete_pending_binding(
                state, trace, parent, output.contract
            )
        if result.failure is not None and output is not None and decision is not None:
            parent = self._complete_pending_execution(
                state, trace, parent, output.contract, output.receipt,
                output.execution_snapshot.observation,
            )
            pending_recovery_failed = bool(
                state.current_recovery_outcome is not None
                and not state.current_recovery_outcome.success
            )
        return self.commit(state, trace, parent, result), pending_recovery_failed

    @staticmethod
    def _fail_pending_recovery(
        state: StateKernel, trace: TraceDag, parent: TraceNode, error_code: str
    ) -> TraceNode:
        from affordance_runtime.recovery_protocol import RecoveryOutcome, RuntimePhase

        decision, failure = state.current_recovery_decision, state.current_failure
        if decision is None or failure is None or state.current_recovery_outcome is not None:
            return parent
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=False,
            changed_dimensions=decision.changed_dimensions,
            next_phase=RuntimePhase.ABORTED,
            error_code=error_code,
        )
        return _commit_recovery_outcome(trace, parent, state)

    @staticmethod
    def _complete_pending_binding(
        state: StateKernel, trace: TraceDag, parent: TraceNode, contract: Any
    ) -> tuple[TraceNode, bool]:
        from affordance_runtime.recovery_protocol import RecoveryKind, RecoveryOutcome

        decision, failure = state.current_recovery_decision, state.current_failure
        if (
            decision is None or failure is None or state.current_recovery_outcome is not None
            or decision.kind not in {RecoveryKind.REGROUND, RecoveryKind.REROUTE}
        ):
            return parent, False
        candidate_id = contract.grounding_candidate.candidate_id if contract.grounding_candidate else ""
        route_matches = bool(
            decision.kind == RecoveryKind.REGROUND
            or (decision.candidate_id and candidate_id == decision.candidate_id)
            or (decision.route_ref and contract.backend == decision.route_ref)
        )
        if not contract.snapshot_id or contract.snapshot_id == failure.snapshot_id or not route_matches:
            return RuntimeCommitter._fail_pending_recovery(
                state, trace, parent, "planner_proposal_rejected"
            ), True
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            artifact_refs=tuple(item for item in (candidate_id, contract.id) if item),
        )
        parent = _commit_recovery_outcome(trace, parent, state)
        return trace.add("RecoveryReenteredPhase", {"state": state.phase, "reentry_phase": decision.reentry_phase.value}, parents=[parent.id]), False

    @staticmethod
    def _complete_pending_execution(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: Any,
        receipt: Any,
        observation: Any,
    ) -> TraceNode:
        from affordance_runtime.recovery_protocol import RecoveryKind, RecoveryOutcome

        decision, failure = state.current_recovery_decision, state.current_failure
        if (
            decision is None or failure is None or state.current_recovery_outcome is not None
            or decision.kind != RecoveryKind.RETRY_IDEMPOTENT
        ):
            return parent
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=receipt.success,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            artifact_refs=tuple(item for item in receipt.evidence.values() if isinstance(item, str)),
            observation_refs=(observation.snapshot_id,) if observation.snapshot_id else (),
            error_code="" if receipt.success else (receipt.error_code.value if receipt.error_code else "execution_failed"),
        )
        return _commit_recovery_outcome(trace, parent, state)

    def commit_recovery_observation(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        execution_loop: Any,
        task_skill_progress: object | None = None,
    ) -> tuple[Any | None, TerminalResult | None, TraceNode]:
        from affordance_runtime.recovery_protocol import RecoveryKind, RecoveryOutcome, RuntimePhase
        from affordance_runtime.runtime_evidence import verification_confirms_effect_absent

        decision, failure = state.current_recovery_decision, state.current_failure
        if decision is None or failure is None or state.current_recovery_outcome is not None:
            return None, None, parent
        verification = None
        failed = False
        if decision.kind == RecoveryKind.INSPECT_POST_STATE:
            contract = state.current_contract
            receipt = state.last_receipt
            if contract is None or receipt is None:
                raise ValueError("post-state recovery inspection requires contract and receipt lineage")
            verification = execution_loop.verify(contract, receipt, snapshot.observation, structural_verification_enabled=True, disabled_reason="")
            state.latest_verification = verification
            parent = trace.add("RecoveryStateInspected", {"state": state.phase, "verification": verification.status.value, "snapshot_id": snapshot.observation.snapshot_id, "artifact_refs": snapshot.observation.artifact_refs}, parents=[parent.id])
            skill_fallthrough = bool(verification_confirms_effect_absent(verification) and task_skill_progress is not None and not getattr(task_skill_progress, "active", True))
            failed = not verification.passed and not skill_fallthrough
        if decision.kind not in {RecoveryKind.REOBSERVE, RecoveryKind.INSPECT_POST_STATE}:
            return verification, None, parent
        if failed:
            state.current_recovery_outcome = RecoveryOutcome(decision_id=decision.decision_id, failure_id=failure.failure_id, success=False, changed_dimensions=decision.changed_dimensions, next_phase=RuntimePhase.ABORTED, error_code="verification_failed")
            parent = _commit_recovery_outcome(trace, parent, state)
            parent = trace.add("RecoveryAborted", {"state": state.phase, "reason": "post-state inspection did not establish a safe changed effect status"}, parents=[parent.id])
            state.transition(RuntimeStep.ABORTED.value)
            return verification, TerminalResult(failure.failure_id, "post_state_inspection_failed", error_code=RuntimeErrorCode.PRECONDITION_FAILED), parent
        state.current_recovery_outcome = RecoveryOutcome(decision_id=decision.decision_id, failure_id=failure.failure_id, success=True, changed_dimensions=decision.changed_dimensions, next_phase=decision.reentry_phase, artifact_refs=tuple(snapshot.observation.artifact_refs), observation_refs=(snapshot.observation.snapshot_id,))
        parent = _commit_recovery_outcome(trace, parent, state)
        return verification, None, trace.add("RecoveryReenteredPhase", {"state": state.phase, "reentry_phase": decision.reentry_phase.value}, parents=[parent.id])

    @staticmethod
    def _commit_phase(state: StateKernel, target: RuntimeStep) -> None:
        """Commit the canonical in-stage action path through valid Runtime states."""

        if state.phase == RuntimeStep.PLANNING.value and target in {
            RuntimeStep.ACTING,
            RuntimeStep.VERIFYING,
        }:
            state.transition(RuntimeStep.PREFLIGHT.value)
        if state.phase == RuntimeStep.PREFLIGHT.value and target == RuntimeStep.VERIFYING:
            state.transition(RuntimeStep.ACTING.value)
        if state.phase in {
            RuntimeStep.ACTING.value,
            RuntimeStep.VERIFYING.value,
        } and target == RuntimeStep.ABORTED:
            state.transition(RuntimeStep.RECOVERING.value)
        if state.phase != target.value:
            state.transition(target.value)

    @staticmethod
    def commit_events(
        trace: TraceDag,
        parent: TraceNode,
        events: tuple[RuntimeEvent, ...],
    ) -> TraceNode:
        for event in events:
            parent = trace.add(event.kind, dict(event.payload), parents=[parent.id])
        return parent

    def commit_source_arbitration(
        self,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        state_label: str,
    ) -> TraceNode:
        return self.commit_events(
            trace,
            parent,
            _source_arbitration_events(snapshot, state_label),
        )


def perception_state_view(
    envelope: RunRequest,
    state: StateKernel,
    budget: RuntimeBudgetView,
) -> PerceptionStateView:
    task_plan = state.task_plan
    failed_sources: set[GroundingSource] = set()
    for lineage in state.current_grounding_fallback.values():
        try:
            failed_sources.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            continue
    return PerceptionStateView(
        phase=RuntimeStep(state.phase),
        state_version=state.version,
        observation_count=state.observation_count,
        active_perception_count=state.active_perception_count,
        task_revision=(
            task_plan.task_revision
            if task_plan is not None
            else envelope.task_spec.revision
            if envelope.task_spec is not None
            else 1
        ),
        plan_version=task_plan.plan_version if task_plan is not None else 0,
        active_subgoal_id=(
            state.task_progress.active_subgoal_id
            if state.task_progress is not None
            else ""
        ),
        active_subgoal=TaskPlanLifecycle.active_subgoal_for_perception(state) or "",
        attempted_probe_fingerprints=frozenset(state.attempted_probe_fingerprints),
        failed_sources=frozenset(failed_sources),
        effectful_action=(
            envelope.task_spec is not None
            and envelope.task_spec.operation_class
            not in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
        ),
        has_receipts=state.last_receipt is not None,
        max_active_perception_observations=budget.max_active_perception_observations,
        max_observations=budget.max_observations,
        remaining_budgets=RemainingRecoveryBudgets(
            recoveries=max(0, budget.max_recoveries - state.recovery_count),
            observations=max(0, budget.max_observations - state.observation_count),
            replans=max(0, budget.max_replans - state.replan_count),
            provider_switches=1,
            user_escalations=1,
            timeout_ms=120_000,
            model_calls=max(0, budget.max_replans - state.replan_count),
            estimated_cost=10.0,
        ),
        progress_fingerprint=semantic_progress_fingerprint(state),
    )


def runtime_state_snapshot(state: StateKernel) -> RuntimeStateSnapshot:
    """Detach mutable Runtime state before handing it to a pure stage."""

    return RuntimeStateSnapshot(
        MappingProxyType(deepcopy(vars(state))),
        deepcopy(state),
    )


def project_working_observation(state: StateKernel, observation: Any) -> None:
    """Apply an observation to a detached stage working copy."""

    state.remember_observation(observation)


def project_working_phase(state: StateKernel, phase: RuntimeStep) -> None:
    """Apply a phase transition to a detached stage working copy."""

    state.transition(phase.value)


def perception_capture_request(
    envelope: RunRequest,
    state: StateKernel,
    sequence: int,
) -> PerceptionCaptureRequest:
    failed_sources: set[GroundingSource] = set()
    for lineage in state.current_grounding_fallback.values():
        try:
            failed_sources.add(GroundingSource(lineage.get("failed_source", "")))
        except ValueError:
            continue
    return PerceptionCaptureRequest(
        envelope=envelope,
        sequence=sequence,
        active_subgoal=TaskPlanLifecycle.active_subgoal_for_perception(state) or "",
        failed_sources=frozenset(failed_sources),
    )


def commit_targeted_perception(
    envelope: RunRequest,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    snapshot: BrowserSnapshot,
    *,
    stage: PerceptionStage,
    committer: RuntimeCommitter,
    budget: RuntimeBudgetView,
) -> tuple[BrowserSnapshot, TraceNode]:
    result = stage.run(
        PerceptionStageInput(
            envelope=envelope,
            state_view=perception_state_view(envelope, state, budget),
            initial_snapshot=snapshot,
        )
    )
    parent = committer.commit(state, trace, parent, result)
    return (
        result.output.snapshot if result.output is not None else snapshot,
        parent,
    )


def _commit_recovery_outcome(
    trace: TraceDag, parent: TraceNode, state: StateKernel
) -> TraceNode:
    outcome = state.current_recovery_outcome
    if outcome is None:
        return parent
    return trace.add(
        "RecoveryOutcomeRecorded",
        {
            "state": state.phase,
            "outcome": {
                "decision_id": outcome.decision_id,
                "failure_id": outcome.failure_id,
                "success": outcome.success,
                "changed_dimensions": [item.value for item in outcome.changed_dimensions],
                "next_phase": outcome.next_phase.value,
                "artifact_refs": list(outcome.artifact_refs),
                "observation_refs": list(outcome.observation_refs),
                "error_code": outcome.error_code,
            },
        },
        parents=[parent.id],
    )
