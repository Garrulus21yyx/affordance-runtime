"""Single commit boundary for immutable stage results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any, TypeVar

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.dispatch_lifecycle import (
    DispatchAdmissionRejected,
    DispatchPermit,
    FinalDispatchAdmission,
)
from affordance_runtime.execution_context import digest_payload
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.simplified_runtime_contracts import ExecutionAttempt
from affordance_runtime.stage_protocol import (
    RuntimeEvent,
    StageResult,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.contracts import TaskCompletionEvaluation

T = TypeVar("T")
_DISPATCH_LINEARIZATION_LOCK = RLock()


@dataclass(frozen=True)
class RuntimeCommitter:
    def admit_dispatch(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        admission: FinalDispatchAdmission,
        attempt: ExecutionAttempt,
    ) -> tuple[DispatchPermit, TraceNode]:
        """Consume owner-issued admission and commit intent at one linearization point."""

        with _DISPATCH_LINEARIZATION_LOCK, admission.gate.linearized_authority():
            if (
                state.task_id != admission.run_id
                or attempt.contract_id != admission.contract.id
                or attempt.contract_hash != admission.contract_hash
                or attempt.issued_at_state_version != admission.expected_state_version
                or attempt.pre_observation.snapshot_id != admission.observation.snapshot_id
                or attempt.pre_observation.page_revision != admission.observation.page_revision
                or attempt.pre_observation.environment_revision != admission.observation.environment_revision
            ):
                raise DispatchAdmissionRejected(
                    RuntimeErrorCode.STALE_OBSERVATION
                )
            error = admission.consume_if_current(state_version=state.version)
            if error is not None:
                raise DispatchAdmissionRejected(error)
            state.current_contract = admission.contract
            state.current_execution_attempt = attempt
            state.step_count += 1
            if admission.contract.effectful:
                state.effectful_action_count += 1
            state.version += 1
            committed_version = state.version
            attempt_node = trace.add(
                "ExecutionAttemptCommitted",
                {
                    "admission_id": admission.admission_id,
                    "attempt_id": attempt.attempt_id,
                    "contract_hash": admission.contract.contract_hash,
                    "state_version": committed_version,
                },
                parents=[parent.id],
            )
            node = trace.add(
                "DispatchIntentCommitted",
                {
                    "admission_id": admission.admission_id,
                    "attempt_id": attempt.attempt_id,
                    "contract_hash": admission.contract.contract_hash,
                    "state_version": committed_version,
                },
                parents=[attempt_node.id],
            )
            issued = time()
            surface = admission.contract.live_surface_binding
            if surface is None:
                raise DispatchAdmissionRejected(RuntimeErrorCode.STALE_OBSERVATION)
            permit = DispatchPermit(
                permit_id="dispatch-permit:"
                + digest_payload((admission.admission_id, attempt.attempt_id, committed_version, issued)).split(":", 1)[1],
                admission_id=admission.admission_id,
                contract=admission.contract,
                observation=admission.observation,
                attempt=attempt,
                committed_state_version=committed_version,
                issued_at_s=issued,
                expires_at_s=min(admission.expires_at_s, surface.lease.expires_at_s),
                contract_hash=admission.contract_hash,
                run_id=admission.run_id,
                session_generation=admission.session_generation,
                surface_id=admission.surface_id,
                surface_check=admission.surface_check,
                coordinate_check=admission.coordinate_check,
                fence_lock=admission.fence_lock,
            )
            return permit, node

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
        if transition is not None and transition.phase == RuntimeStep.DONE and transition.task_completion is None:
            raise ValueError("terminal success state and result require typed task completion")
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
            if transition.execution_attempt is not None:
                state.current_execution_attempt = transition.execution_attempt
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
            trace.artifact_index.extend(path for path in transition.artifact_refs if path)
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
            {
                "state": state.phase,
                "result": {
                    "content_digest": digest_payload(state.final_result),
                    "keys": tuple(sorted(state.final_result)),
                    "redacted": True,
                    "access_policy_ref": "task-owner@v1",
                    "retention_policy_ref": "run-scoped@v1",
                },
            },
            parents=[parent.id],
        )

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
        if (
            state.phase
            in {
                RuntimeStep.ACTING.value,
                RuntimeStep.VERIFYING.value,
            }
            and target == RuntimeStep.ABORTED
        ):
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
