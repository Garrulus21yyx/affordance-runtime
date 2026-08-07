"""Runtime loop lifecycle seam for Coordinator phase extraction.

This module owns loop-start and phase-entry lifecycle commits that are not
domain planning, execution, verification, progress, or recovery decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.execution_context import RunProvenanceManifest
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.stage_protocol import StageResult, TerminalResult
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class RuntimeLoopEvent:
    kind: str
    payload: dict[str, object]
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeLoopTransition:
    phase: RuntimeStep
    activate_next_step: bool = False


@dataclass(frozen=True)
class RuntimeLoopStartResult:
    state: StateKernel
    trace: TraceDag
    event: RuntimeLoopEvent


@dataclass(frozen=True)
class RuntimeLoopTerminalResult:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None
    transition: RuntimeLoopTransition
    event: RuntimeLoopEvent


class RuntimeBudgetView(Protocol):
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

    @property
    def max_active_perception_observations(self) -> int: ...


class RuntimeLoopPhase:
    """Prepare loop lifecycle transitions and events without committing them."""

    def start(
        self,
        *,
        envelope: RunRequest,
        upstream_trace: TraceDag | None,
        runtime_profile_digest: str,
        loaded_profile_artifact_ids: tuple[str, ...],
        provenance_manifest: RunProvenanceManifest,
    ) -> RuntimeLoopStartResult:
        state = StateKernel(
            task_id=envelope.task_id,
            goal=envelope.goal,
            constraints=dict(envelope.constraints),
        )
        if upstream_trace is not None and upstream_trace.run_id != envelope.task_id:
            raise ValueError("upstream trace run_id does not match task")
        trace = upstream_trace or TraceDag(run_id=envelope.task_id)
        upstream_parent = trace.nodes[-1] if trace.nodes else None
        event = RuntimeLoopEvent(
            kind="TaskCreated",
            payload={
                "state": RuntimeStep.CREATED.value,
                "goal": envelope.goal,
                "constraints": envelope.constraints,
                "task_spec_identity": (
                    envelope.task_spec.identity if envelope.task_spec is not None else ""
                ),
                "runtime_profile_digest": runtime_profile_digest,
                "loaded_profile_artifact_ids": list(loaded_profile_artifact_ids),
                "run_provenance_manifest_digest": provenance_manifest.digest,
            },
            parent_ids=(upstream_parent.id,) if upstream_parent else (),
        )
        return RuntimeLoopStartResult(state=state, trace=trace, event=event)

    def check_budget(
        self,
        *,
        state: StateKernel,
        budget: RuntimeBudgetView,
    ) -> RuntimeLoopTerminalResult | None:
        budget_error = _budget_error(state, budget)
        if budget_error is None:
            return None
        return RuntimeLoopTerminalResult(
            status=RuntimeStep.FAILED,
            error_code=budget_error,
            transition=RuntimeLoopTransition(RuntimeStep.FAILED),
            event=RuntimeLoopEvent(
                kind="TaskFailed",
                payload={
                    "state": RuntimeStep.FAILED.value,
                    "error_code": budget_error.value,
                    "reason": "runtime budget exhausted",
                },
            ),
        )

    def enter_planning(self, *, has_task_plan: bool) -> RuntimeLoopTransition:
        return RuntimeLoopTransition(
            RuntimeStep.PLANNING,
            activate_next_step=has_task_plan,
        )

    def enter_verifying(self) -> RuntimeLoopTransition:
        return RuntimeLoopTransition(RuntimeStep.VERIFYING)


@dataclass
class RuntimeCommitSession:
    """Run lifecycle orchestration around the typed RuntimeCommitter boundary."""

    committer: Any
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
        committer: Any,
        result_builder: Any,
        recovery_stage: Any,
        envelope: RunRequest,
        budget: RuntimeBudgetView,
        upstream_trace: TraceDag | None,
        provenance_manifest: RunProvenanceManifest,
    ) -> RuntimeCommitSession:
        started = RuntimeLoopPhase().start(
            envelope=envelope,
            upstream_trace=upstream_trace,
            runtime_profile_digest=recovery_stage.runtime_profile_digest,
            loaded_profile_artifact_ids=recovery_stage.loaded_profile_artifact_ids,
            provenance_manifest=provenance_manifest,
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
        from affordance_runtime.runtime_state_projection import perception_state_view

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

    def admit_dispatch(self, admission: Any, attempt: Any) -> Any:
        permit, self.parent = self.committer.admit_dispatch(
            self.state,
            self.trace,
            self.parent,
            admission,
            attempt,
        )
        return permit

    def enter_planning(self) -> None:
        self.committer.commit_loop_transition(
            self.state,
            RuntimeLoopPhase().enter_planning(
                has_task_plan=self.state.task_plan is not None
            ),
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
        from affordance_runtime.runtime_state_projection import runtime_state_snapshot

        result = self.recovery_stage.resolve_failure(
            RecoveryStageInput(
                failure=failure,
                state_view=runtime_state_snapshot(self.state),
                available_commands=commands,
                runtime_profile_digest=self.recovery_stage.runtime_profile_digest,
                loaded_profile_artifact_ids=(
                    self.recovery_stage.loaded_profile_artifact_ids
                ),
            ),
            preserve_terminal=preserve_terminal,
            terminate_all_handoffs=terminate_all_handoffs,
        )
        self.commit(result)
        return self.finish(result.terminal) if result.terminal is not None else None


def _budget_error(
    state: StateKernel,
    budget: RuntimeBudgetView,
) -> RuntimeErrorCode | None:
    if state.step_count >= budget.max_steps:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.observation_count >= budget.max_observations:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.replan_count >= budget.max_replans:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.recovery_count >= budget.max_recoveries:
        return RuntimeErrorCode.EXECUTION_FAILED
    if state.effectful_action_count >= budget.max_effectful_actions:
        return RuntimeErrorCode.UNSAFE_ACTION
    return None
