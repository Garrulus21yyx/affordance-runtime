"""Single commit boundary for immutable stage results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeVar

from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.stage_protocol import (
    RuntimeEvent,
    StageResult,
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
