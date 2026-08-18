"""Thin mission supervisor around the existing CoreAgentLoop episode."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.mission.boundary import AuditBoundary
from affordance_runtime.mission.contracts import (
    AuditBundle,
    AuditDelta,
    AuditDeltaStatus,
    AuditorPort,
    AuditorRoleRequest,
    ManagerPort,
    ManagerRoleRequest,
    ManagerRoute,
    MissionState,
    OutcomeProposal,
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
    manager_calls: int = 0
    auditor_calls: int = 0
    finalization: EnvironmentFinalization | None = None


@dataclass(frozen=True)
class MissionSupervisor:
    manager: ManagerPort
    auditor: AuditorPort
    boundary: AuditBoundary = AuditBoundary()
    max_rounds: int = 8

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
        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return MissionRunResult(None, mission, supervisor, manager_calls, auditor_calls)
        current_world = acquisition.observation
        last_exit = "task_start"
        last_ref = ""
        for round_index in range(self.max_rounds):
            decision_result = await self.manager.decide(
                ManagerRoleRequest(task, mission, last_exit, last_ref, self.max_rounds - round_index)
            )
            manager_calls += 1
            if decision_result.failure is not None:
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit="manager_failure",
                    last_ref="manager_failure",
                    mission_round_budget=self.max_rounds - round_index,
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(state, mission, supervisor, manager_calls, auditor_calls)
            decision = decision_result.output
            assert decision is not None
            if decision.route is ManagerRoute.ASK_USER:
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit="manager_ask_user",
                    last_ref="manager_ask_user",
                    mission_round_budget=self.max_rounds - round_index,
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(state, mission, supervisor, manager_calls, auditor_calls)
            if decision.route is ManagerRoute.BLOCKED:
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit="manager_blocked",
                    last_ref="manager_blocked",
                    mission_round_budget=self.max_rounds - round_index,
                    opened_environment_ref=_environment_ref(environment),
                )
                return MissionRunResult(state, mission, supervisor, manager_calls, auditor_calls)
            if decision.route is ManagerRoute.REQUEST_FINAL_AUDIT:
                final = await self._finalize_if_ready(runtime, environment, task, state, mission)
                supervisor = SupervisorState(
                    SupervisorPhase.TERMINAL,
                    last_typed_episode_exit="finalized",
                    last_ref="final_response",
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
                    manager_calls,
                    auditor_calls + final.auditor_calls,
                    final.finalization,
                )
            assert decision.subtask is not None
            state = await runtime.initialize_from_world(
                task,
                current_world,
                subtask_goal_resolution(task, decision.subtask),
                max_turns=decision.subtask.episode_turn_budget,
                yield_on_budget_exhaustion=True,
                working_facts=mission.carry_working_facts(),
            )
            state = await runtime.continue_task(environment, task, state)
            if state.status is RunStatus.CANCELLED:
                return MissionRunResult(state, mission, SupervisorState(SupervisorPhase.TERMINAL), manager_calls, auditor_calls)
            if state.status in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}:
                return MissionRunResult(state, mission, SupervisorState(SupervisorPhase.EXECUTING, decision.subtask), manager_calls, auditor_calls)
            current_world = state.current_world
            audit_result = await self._audit_episode(
                environment,
                task,
                decision.subtask,
                mission,
                state,
            )
            auditor_calls += audit_result.auditor_calls
            mission = audit_result.mission_state
            current_world = audit_result.state.current_world if audit_result.state is not None else current_world
            last_exit = f"episode:{state.status.value}:{state.yield_reason.value if state.yield_reason else ''}"
            last_ref = audit_result.supervisor_state.last_ref
        return MissionRunResult(state, mission, SupervisorState(SupervisorPhase.TERMINAL), manager_calls, auditor_calls)

    async def _audit_episode(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        subtask: SubtaskContract,
        mission: MissionState,
        state: RunState,
    ) -> MissionRunResult:
        deterministic = state.current_task_evaluation
        if deterministic.status is not TaskEvaluationStatus.UNKNOWN:
            delta = _delta_from_task_evaluation(mission, deterministic.status, deterministic.completion_evidence_refs)
            bundle = AuditBundle.from_world(state.current_world)
            accepted = self.boundary.accept(mission, delta, bundle)
            return MissionRunResult(
                state,
                accepted.mission_state,
                SupervisorState(SupervisorPhase.MANAGER, last_ref=accepted.reason_code or "deterministic_audit"),
            )
        acquisition = await environment.capture(WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "fresh audit capture"))
        if acquisition.status is AcquisitionStatus.ACQUIRED and acquisition.observation is not None:
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
        if result.failure is not None:
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref="auditor_failure"),
                auditor_calls=1,
            )
        delta = result.output
        assert delta is not None
        if delta.status is AuditDeltaStatus.UNKNOWN and delta.missing_evidence:
            recaptured = await environment.capture(WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "fresh audit recapture"))
            if recaptured.status is AcquisitionStatus.ACQUIRED and recaptured.observation is not None:
                state.current_world = recaptured.observation
            bundle = AuditBundle.from_world(state.current_world)
            retry = await self.auditor.audit(
                AuditorRoleRequest(
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
            )
            if retry.failure is not None:
                return MissionRunResult(state, mission, SupervisorState(SupervisorPhase.MANAGER, last_ref="auditor_failure"), auditor_calls=2)
            delta = retry.output
            assert delta is not None
            if delta.status is AuditDeltaStatus.UNKNOWN:
                return MissionRunResult(state, mission, SupervisorState(SupervisorPhase.MANAGER, last_ref="evidence_gap"), auditor_calls=2)
        accepted = self.boundary.accept(mission, delta, bundle)
        return MissionRunResult(
            state,
            accepted.mission_state,
            SupervisorState(SupervisorPhase.MANAGER, last_ref=accepted.reason_code or "audit_accepted"),
            auditor_calls=1,
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
            return MissionRunResult(state, mission, SupervisorState(SupervisorPhase.TERMINAL))
        bundle = AuditBundle.from_world(state.current_world)
        final_contract = SubtaskContract(
            "Audit whether the mission is ready for the single final response.",
            "Accepted mission state and current public evidence support sending the final response.",
            candidate_output_keys=("final_response",),
        )
        audit = await self.auditor.audit(
            AuditorRoleRequest(
                task,
                final_contract,
                mission,
                state.current_world,
                state.working_facts,
                "request_final_audit",
                (),
                bundle,
            )
        )
        if audit.failure is not None or audit.output is None:
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref="final_audit_failed"),
                auditor_calls=1,
            )
        accepted = self.boundary.accept(mission, audit.output, bundle)
        if (
            not accepted.accepted
            or audit.output.status is not AuditDeltaStatus.AUDITED_SATISFIED
        ):
            return MissionRunResult(
                state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref=accepted.reason_code or "final_audit_not_ready"),
                auditor_calls=1,
            )
        mission = accepted.mission_state
        finalizing_runtime = runtime.with_runtime_controls(("final_response",), episode_monitor=None)
        final_state = await finalizing_runtime.initialize_from_world(
            task,
            state.current_world,
            subtask_goal_resolution(task, final_contract),
            max_turns=1,
            yield_on_budget_exhaustion=False,
            working_facts=mission.carry_working_facts(),
        )
        final_state = await finalizing_runtime.continue_task(environment, task, final_state)
        if not isinstance(final_state.last_step.decision if final_state.last_step is not None else None, FinalResponse):
            return MissionRunResult(
                final_state,
                mission,
                SupervisorState(SupervisorPhase.MANAGER, last_ref="final_response_not_produced"),
                auditor_calls=1,
            )
        response = final_state.last_step.decision
        finalization = await environment.finalize(response.content)
        if finalization.result.dispatch_status is not DispatchStatus.SENT or finalization.post_acquisition is None:
            return MissionRunResult(
                final_state,
                mission,
                SupervisorState(SupervisorPhase.TERMINAL),
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
            auditor_calls=1,
            finalization=finalization,
        )


def _delta_from_task_evaluation(mission: MissionState, status: TaskEvaluationStatus, refs: tuple[str, ...]) -> AuditDelta:
    if status is TaskEvaluationStatus.COMPLETE:
        delta_status = AuditDeltaStatus.AUDITED_SATISFIED
    else:
        delta_status = AuditDeltaStatus.AUDITED_UNSATISFIED
    return AuditDelta(
        delta_status,
        mission.version,
        (OutcomeProposal(f"audit:{mission.version + 1}", delta_status, refs, status.value),),
    )


def _status_for_terminal_evaluation(status: TaskEvaluationStatus) -> RunStatus:
    if status is TaskEvaluationStatus.COMPLETE:
        return RunStatus.DONE
    if status is TaskEvaluationStatus.BLOCKED:
        return RunStatus.BLOCKED
    return RunStatus.RUNNING


def _environment_ref(environment: object) -> str:
    return str(getattr(environment, "physical_environment_id", "") or id(environment))
