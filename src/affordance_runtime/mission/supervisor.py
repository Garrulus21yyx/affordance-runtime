"""Thin mission supervisor around the existing CoreAgentLoop episode."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.observability import NullRunTraceSink, RunTraceSink
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.mission.boundary import AuditBoundary
from affordance_runtime.mission.contracts import (
    AuditBundle,
    AuditDeltaStatus,
    AuditorPort,
    AuditorRoleRequest,
    ManagerPort,
    ManagerRoleRequest,
    ManagerRoute,
    MissionOutcome,
    MissionState,
    SubtaskContract,
    SupervisorPhase,
    SupervisorState,
)
from affordance_runtime.mission.goal_projection import subtask_goal_resolution
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.finalization import EnvironmentFinalization


@dataclass(frozen=True)
class MissionRunResult:
    state: RunState | None
    mission_state: MissionState
    supervisor_state: SupervisorState
    outcome: MissionOutcome = MissionOutcome.RUNNING
    manager_calls: int = 0
    auditor_calls: int = 0
    boundary_rejections: int = 0
    user_question: str = ""
    finalization: EnvironmentFinalization | None = None

    @property
    def status(self) -> RunStatus:
        return _run_status_for_mission_outcome(self.outcome, self.state)

    @property
    def observation_count(self) -> int:
        return self.state.observation_count if self.state is not None else 0

    @property
    def execution_count(self) -> int:
        return self.state.execution_count if self.state is not None else 0

    @property
    def step_count(self) -> int:
        return self.state.step_count if self.state is not None else 0

    @property
    def last_step(self):
        return self.state.last_step if self.state is not None else None

    @property
    def policy_failure(self):
        return self.state.policy_failure if self.state is not None else None

    @property
    def failure_code(self):
        return self.state.failure_code if self.state is not None else None

    @property
    def runtime_failure(self):
        return self.state.runtime_failure if self.state is not None else None

    @property
    def task_outcome(self):
        return self.state.task_outcome if self.state is not None else None

    @property
    def sent_unknown_count(self) -> int:
        return self.state.sent_unknown_count if self.state is not None else 0


@dataclass(frozen=True)
class MissionSupervisor:
    manager: ManagerPort
    auditor: AuditorPort
    boundary: AuditBoundary = AuditBoundary()
    max_rounds: int = 8
    trace_sink: RunTraceSink = NullRunTraceSink()

    async def run(
        self,
        runtime,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> MissionRunResult:
        mission = MissionState.empty()
        supervisor = SupervisorState(
            SupervisorPhase.MANAGER,
            mission_round_budget=self.max_rounds,
            opened_environment_ref=_environment_ref(environment),
        )
        state: RunState | None = None
        manager_calls = 0
        auditor_calls = 0
        boundary_rejections = 0
        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return MissionRunResult(
                None,
                mission,
                supervisor,
                MissionOutcome.TASK_BLOCKED,
                manager_calls=manager_calls,
                auditor_calls=auditor_calls,
            )
        current_world = acquisition.observation
        last_exit = "task_start"
        last_ref = ""
        for round_index in range(self.max_rounds):
            remaining_budget = self.max_rounds - round_index
            manager_request = ManagerRoleRequest(task, mission, last_exit, last_ref, remaining_budget)
            decision_result = await self.manager.decide(
                manager_request
            )
            _record_role_invocation(self.trace_sink, "manager", manager_calls + 1, manager_request, decision_result)
            manager_calls += 1
            if decision_result.failure is not None:
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit="manager_failure",
                    last_ref="manager_failure",
                    mission_round_budget=self.max_rounds - round_index,
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(
                    state,
                    mission,
                    supervisor,
                    MissionOutcome.MANAGER_FAILURE,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                )
            decision = decision_result.output
            assert decision is not None
            if decision.route is ManagerRoute.ASK_USER:
                supervisor = SupervisorState(
                    SupervisorPhase.WAITING_USER,
                    last_typed_episode_exit="manager_ask_user",
                    last_ref="manager_ask_user",
                    mission_round_budget=self.max_rounds - round_index,
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(
                    state,
                    mission,
                    supervisor,
                    MissionOutcome.NEEDS_USER_INPUT,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                    user_question=decision.question,
                )
            if decision.route is ManagerRoute.BLOCKED:
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit="manager_blocked",
                    last_ref="manager_blocked",
                    mission_round_budget=self.max_rounds - round_index,
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(
                    state,
                    mission,
                    supervisor,
                    MissionOutcome.BLOCKED,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                )
            if decision.route is ManagerRoute.REQUEST_FINAL_AUDIT:
                final = await self._finalize_if_ready(runtime, environment, task, state, mission)
                auditor_calls += final.auditor_calls
                boundary_rejections += final.boundary_rejections
                if final.outcome is MissionOutcome.FINAL_AUDIT_NOT_READY and remaining_budget > 1:
                    mission = final.mission_state
                    if final.state is not None:
                        state = final.state
                        current_world = final.state.current_world
                    last_exit = "final_audit:not_ready"
                    last_ref = final.supervisor_state.last_ref
                    continue
                final_outcome = (
                    MissionOutcome.ROUND_BUDGET_EXHAUSTED
                    if final.outcome is MissionOutcome.FINAL_AUDIT_NOT_READY
                    else final.outcome
                )
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit=final_outcome.value,
                    last_ref=final.supervisor_state.last_ref or "final_response",
                    mission_round_budget=self.max_rounds - round_index,
                    final_response_delivered=(
                        final.finalization is not None
                        and final.finalization.result.dispatch_status is not DispatchStatus.NOT_SENT
                    ),
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(
                    final.state,
                    final.mission_state,
                    supervisor,
                    final_outcome,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                    finalization=final.finalization,
                )
            assert decision.subtask is not None
            state = await runtime.initialize_from_world(
                task,
                current_world,
                subtask_goal_resolution(task, decision.subtask),
                max_turns=decision.subtask.episode_turn_budget,
                yield_on_budget_exhaustion=True,
                working_facts=mission.carry_working_facts(decision.subtask.relevant_fact_keys),
            )
            state = await runtime.continue_task(environment, task, state)
            if state.status is RunStatus.CANCELLED:
                return MissionRunResult(
                    state,
                    mission,
                    SupervisorState(SupervisorPhase.TERMINAL),
                    MissionOutcome.CANCELLED,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                )
            if state.status in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}:
                return MissionRunResult(
                    state,
                    mission,
                    SupervisorState(SupervisorPhase.EXECUTING, decision.subtask),
                    MissionOutcome.NEEDS_USER_INPUT,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                )
            current_world = state.current_world
            audit_result = await self._audit_episode(
                environment,
                task,
                decision.subtask,
                mission,
                state,
            )
            auditor_calls += audit_result.auditor_calls
            boundary_rejections += audit_result.boundary_rejections
            if audit_result.outcome in {MissionOutcome.TASK_COMPLETE, MissionOutcome.TASK_BLOCKED}:
                return MissionRunResult(
                    audit_result.state,
                    mission,
                    audit_result.supervisor_state,
                    audit_result.outcome,
                    manager_calls=manager_calls,
                    auditor_calls=auditor_calls,
                    boundary_rejections=boundary_rejections,
                )
            mission = audit_result.mission_state
            current_world = audit_result.state.current_world if audit_result.state is not None else current_world
            last_exit = _audit_manager_signal(audit_result, state)
            last_ref = audit_result.supervisor_state.last_ref
        return MissionRunResult(
            state,
            mission,
            SupervisorState(SupervisorPhase.TERMINAL),
            MissionOutcome.ROUND_BUDGET_EXHAUSTED,
            manager_calls=manager_calls,
            auditor_calls=auditor_calls,
            boundary_rejections=boundary_rejections,
        )

    async def _audit_episode(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        subtask: SubtaskContract,
        mission: MissionState,
        state: RunState,
    ) -> MissionRunResult:
        deterministic = state.current_task_evaluation
        if deterministic.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
            state.status = _status_for_terminal_evaluation(deterministic.status)
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.TERMINAL, last_ref=f"task_evaluator:{deterministic.status.value}"),
                (
                    MissionOutcome.TASK_COMPLETE
                    if deterministic.status is TaskEvaluationStatus.COMPLETE
                    else MissionOutcome.TASK_BLOCKED
                ),
            )
        acquisition = await environment.capture(WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "fresh audit capture"))
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref=f"audit_capture:{acquisition.status.value}"),
                _audit_capture_failure_outcome(acquisition.status),
            )
        state.current_world = acquisition.observation
        bundle = AuditBundle.from_world(state.current_world)
        request = AuditorRoleRequest(
            task,
            subtask,
            mission,
            state.current_world,
            state.working_facts,
            state.yield_reason.value if state.yield_reason else "unknown",
            state.recent_steps,
            bundle,
            subtask.related_audit_ids,
        )
        result = await self.auditor.audit(request)
        _record_role_invocation(self.trace_sink, "auditor", 1, request, result)
        if result.failure is not None:
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref="auditor_failure"),
                MissionOutcome.AUDITOR_FAILURE,
                auditor_calls=1,
            )
        delta = result.output
        assert delta is not None
        calls = 1
        if delta.status is AuditDeltaStatus.UNKNOWN and delta.missing_evidence:
            recaptured = await environment.capture(WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "fresh audit recapture"))
            if recaptured.status is not AcquisitionStatus.ACQUIRED or recaptured.observation is None:
                return MissionRunResult(
                    state,
                    mission,
                    SupervisorState(SupervisorPhase.MANAGER, last_ref=f"audit_recapture:{recaptured.status.value}"),
                    _audit_capture_failure_outcome(recaptured.status),
                    auditor_calls=1,
                )
            state.current_world = recaptured.observation
            bundle = AuditBundle.from_world(state.current_world)
            retry_request = AuditorRoleRequest(
                task,
                subtask,
                mission,
                state.current_world,
                state.working_facts,
                state.yield_reason.value if state.yield_reason else "unknown",
                state.recent_steps,
                bundle,
                subtask.related_audit_ids,
            )
            retry = await self.auditor.audit(retry_request)
            _record_role_invocation(self.trace_sink, "auditor", 2, retry_request, retry)
            calls = 2
            if retry.failure is not None:
                return MissionRunResult(
                    state,
                    mission,
                    SupervisorState(SupervisorPhase.MANAGER, last_ref="auditor_failure"),
                    MissionOutcome.AUDITOR_FAILURE,
                    auditor_calls=2,
                )
            delta = retry.output
            assert delta is not None
            if delta.status is AuditDeltaStatus.UNKNOWN:
                return MissionRunResult(
                    state,
                    mission,
                    SupervisorState(SupervisorPhase.MANAGER, last_ref="evidence_gap"),
                    MissionOutcome.EVIDENCE_GAP,
                    auditor_calls=2,
                )
        accepted = self.boundary.accept(mission, delta, bundle)
        return MissionRunResult(
            state,
            accepted.mission_state,
            SupervisorState(SupervisorPhase.MANAGER, last_ref=accepted.reason_code or "audit_accepted"),
            MissionOutcome.BOUNDARY_REJECTED if not accepted.accepted else MissionOutcome.RUNNING,
            auditor_calls=calls,
            boundary_rejections=int(not accepted.accepted),
        )

    async def _finalize_if_ready(
        self,
        runtime,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState | None,
        mission: MissionState,
    ) -> MissionRunResult:
        if state is None or not getattr(environment, "supports_finalization", False):
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.TERMINAL),
                MissionOutcome.FINAL_AUDIT_NOT_READY,
            )
        bundle = AuditBundle.from_world(state.current_world)
        final_contract = SubtaskContract(
            "Audit whether the mission is ready for the single final response.",
            "Accepted mission state and current public evidence support sending the final response.",
            relevant_fact_keys=tuple(item.key for item in mission.accepted_facts),
            candidate_output_keys=("final_response",),
        )
        audit_request = AuditorRoleRequest(
            task,
            final_contract,
            mission,
            state.current_world,
            state.working_facts,
            "request_final_audit",
            (),
            bundle,
        )
        audit = await self.auditor.audit(audit_request)
        _record_role_invocation(self.trace_sink, "auditor", 1, audit_request, audit)
        if audit.failure is not None or audit.output is None:
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref="final_audit_failed"),
                MissionOutcome.AUDITOR_FAILURE,
                auditor_calls=1,
            )
        accepted = self.boundary.accept(mission, audit.output, bundle)
        if (
            not accepted.accepted
            or audit.output.status is not AuditDeltaStatus.AUDITED_SATISFIED
        ):
            return MissionRunResult(
                state,
                accepted.mission_state,
                SupervisorState(SupervisorPhase.MANAGER, last_ref=accepted.reason_code or "final_audit_not_ready"),
                MissionOutcome.FINAL_AUDIT_NOT_READY,
                auditor_calls=1,
                boundary_rejections=int(not accepted.accepted),
            )
        mission = accepted.mission_state
        finalizing_runtime = runtime.with_runtime_controls(("final_response",), episode_monitor=None)
        final_state = await finalizing_runtime.initialize_from_world(
            task,
            state.current_world,
            subtask_goal_resolution(task, final_contract),
            max_turns=1,
            yield_on_budget_exhaustion=False,
            working_facts=mission.carry_working_facts(final_contract.relevant_fact_keys),
        )
        final_state = await finalizing_runtime.continue_task(environment, task, final_state)
        if not isinstance(final_state.last_step.decision if final_state.last_step is not None else None, FinalResponse):
            return MissionRunResult(
                final_state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref="final_response_not_produced"),
                MissionOutcome.FINAL_AUDIT_NOT_READY,
                auditor_calls=1,
            )
        response = final_state.last_step.decision
        finalization = await environment.finalize(response.content)
        if finalization.result.dispatch_status is not DispatchStatus.SENT or finalization.post_acquisition is None:
            return MissionRunResult(
                final_state,
                mission,
                SupervisorState(SupervisorPhase.TERMINAL),
                MissionOutcome.FINALIZED,
                auditor_calls=1,
                finalization=finalization,
            )
        post = finalization.post_acquisition
        if post.status is AcquisitionStatus.ACQUIRED and post.observation is not None:
            final_state.current_world = post.observation
            final_state.current_task_evaluation = await runtime.task_evaluator.evaluate(task, post.observation)
            final_state.status = _status_for_terminal_evaluation(final_state.current_task_evaluation.status)
        return MissionRunResult(
            final_state,
            mission,
            SupervisorState(SupervisorPhase.TERMINAL),
            MissionOutcome.FINALIZED,
            auditor_calls=1,
            finalization=finalization,
        )


def _status_for_terminal_evaluation(status: TaskEvaluationStatus) -> RunStatus:
    if status is TaskEvaluationStatus.COMPLETE:
        return RunStatus.DONE
    if status is TaskEvaluationStatus.BLOCKED:
        return RunStatus.BLOCKED
    return RunStatus.RUNNING


def _run_status_for_mission_outcome(outcome: MissionOutcome, state: RunState | None) -> RunStatus:
    if outcome is MissionOutcome.FINALIZED:
        evaluation = state.current_task_evaluation if state is not None else None
        if evaluation is None:
            return RunStatus.FAILED
        if evaluation.status is TaskEvaluationStatus.COMPLETE:
            return RunStatus.DONE
        if evaluation.status is TaskEvaluationStatus.BLOCKED:
            return RunStatus.BLOCKED
        return RunStatus.FAILED
    mapping = {
        MissionOutcome.RUNNING: RunStatus.RUNNING,
        MissionOutcome.NEEDS_USER_INPUT: RunStatus.WAITING_USER,
        MissionOutcome.BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.MANAGER_FAILURE: RunStatus.FAILED,
        MissionOutcome.AUDITOR_FAILURE: RunStatus.FAILED,
        MissionOutcome.BOUNDARY_REJECTED: RunStatus.RUNNING,
        MissionOutcome.EVIDENCE_GAP: RunStatus.BLOCKED,
        MissionOutcome.FINAL_AUDIT_NOT_READY: RunStatus.RUNNING,
        MissionOutcome.CANCELLED: RunStatus.CANCELLED,
        MissionOutcome.TASK_COMPLETE: RunStatus.DONE,
        MissionOutcome.TASK_BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.ROUND_BUDGET_EXHAUSTED: RunStatus.BLOCKED,
    }
    return mapping[outcome]


def _audit_manager_signal(result: MissionRunResult, state: RunState) -> str:
    if result.outcome is MissionOutcome.BOUNDARY_REJECTED:
        return "audit:rejected"
    if result.outcome is MissionOutcome.EVIDENCE_GAP:
        return "audit:evidence_gap"
    if result.outcome is MissionOutcome.AUDITOR_FAILURE:
        return "audit:auditor_failure"
    return f"episode:{state.status.value}:{state.yield_reason.value if state.yield_reason else ''}"


def _audit_capture_failure_outcome(status: AcquisitionStatus) -> MissionOutcome:
    if status is AcquisitionStatus.CANCELLED:
        return MissionOutcome.CANCELLED
    return MissionOutcome.EVIDENCE_GAP


def _record_role_invocation(
    trace_sink: RunTraceSink,
    role: str,
    call_index: int,
    request: object,
    result: object,
) -> None:
    recorder = getattr(trace_sink, "mission_role_invocation", None)
    if callable(recorder):
        recorder(role, call_index, request, result)


def _environment_ref(environment: object) -> str:
    return str(getattr(environment, "physical_environment_id", "") or id(environment))
