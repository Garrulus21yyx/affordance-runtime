"""Single commit boundary for immutable stage results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeVar

from affordance_runtime.perception_phase import (
    _source_arbitration_events,
)
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.stage_protocol import (
    OwnerHandoff,
    RuntimeEvent,
    StageResult,
    StepPlannerHandoff,
    TaskPlannerHandoff,
    TerminalResult,
    UserInputRequest,
    build_failure_owner_handoff,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.contracts import TaskCompletionEvaluation

T = TypeVar("T")


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
        if (
            transition is not None
            and transition.phase == RuntimeStep.DONE
            and transition.task_completion is None
        ):
            raise ValueError(
                "terminal success state and result require typed task completion"
            )
        if transition is not None:
            if transition.state_updates is not None:
                for name, value in transition.state_updates.items():
                    setattr(state, name, deepcopy(value))
            for intermediate in transition.intermediate_phases:
                if state.phase != intermediate.value:
                    self._commit_phase(state, intermediate)
            if transition.phase is not None and state.phase != transition.phase.value:
                self._commit_phase(state, transition.phase)
            for observation in transition.observation_commits:
                state.remember_observation_commit(observation)
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
                state.record_step_action()
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
        parent = self.commit_events(trace, parent, result.events)
        if transition is not None and transition.task_completion is not None:
            parent = self.commit_task_completion(
                state,
                trace,
                parent,
                transition.task_completion,
            )
        return parent

    @staticmethod
    def commit_task_completion(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        completion: TaskCompletionEvaluation,
    ) -> TraceNode:
        """Commit one already-evaluated typed completion transition/event."""

        if not completion.completed:
            raise ValueError("task completion evaluation is not satisfied")
        state.final_result = dict(completion.result_payload)
        if state.phase != RuntimeStep.DONE.value:
            state.transition(RuntimeStep.DONE.value)
        return trace.add(
            "TaskCompleted",
            {"state": state.phase, "result": state.final_result},
            parents=[parent.id],
        )

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
            if event.kind == "TaskCompleted":
                raise ValueError("TaskCompleted may only be emitted from typed completion commit")
            parent = trace.add(event.kind, dict(event.payload), parents=[parent.id])
        return parent

    def commit_source_arbitration(
        self,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: PerceptionCapture,
        state_label: str,
    ) -> TraceNode:
        return self.commit_events(
            trace,
            parent,
            _source_arbitration_events(snapshot, state_label),
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
