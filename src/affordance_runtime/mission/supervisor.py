"""Mechanical outer mission supervisor around the single CoreAgentLoop."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.agent.context.contracts import AgentSubtaskContractView
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.agent.decisions import FinalResponse, YieldSubtask
from affordance_runtime.agent.observability import NullRunTraceSink, RunTraceSink
from affordance_runtime.agent.run_state import EpisodeYieldReason, RunState, RunStatus
from affordance_runtime.agent.working_facts import is_public_scalar
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.boundary import EvidenceBoundary
from affordance_runtime.mission.contracts import (
    AuditorPort,
    AuditorRoleRequest,
    EvidenceBoundaryRejectionClass,
    EvidenceBundle,
    ManagerAssessment,
    ManagerDecision,
    ManagerPort,
    ManagerRecoveryView,
    ManagerRequestMode,
    ManagerRoleRequest,
    ManagerRoute,
    MissionOutcome,
    MissionState,
    RecoveryKind,
    RecoverySignal,
    SubtaskContract,
    SupervisorPhase,
    SupervisorState,
)
from affordance_runtime.mission.environment_projection import project_mission_environment
from affordance_runtime.mission.finalization import (
    FinalResponseBoundary,
    FinalResponseRejection,
)
from affordance_runtime.mission.goal_projection import subtask_goal_resolution
from affordance_runtime.mission.monitor import EpisodeMonitor
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.finalization import EnvironmentFinalization
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest


@dataclass(frozen=True)
class MissionRunResult:
    state: RunState | None
    mission_state: MissionState
    supervisor_state: SupervisorState
    outcome: MissionOutcome = MissionOutcome.RUNNING
    manager_calls: int = 0
    auditor_calls: int = 0
    final_response_boundary_admission_count: int = 0
    final_response_boundary_rejection_count: int = 0
    stop_send_count: int = 0
    post_stop_capture_count: int = 0
    native_evaluator_count: int = 0
    boundary_rejections: int = 0
    final_response_rejection_code: str = ""
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


class _EpisodeRoute(StrEnum):
    TASK_COMPLETE = "task_complete"
    TASK_BLOCKED = "task_blocked"
    RUNTIME_BLOCKED = "runtime_blocked"
    WAITING_USER = "waiting_user"
    CANCELLED = "cancelled"
    OUTCOME_PROPOSED = "outcome_proposed"
    NEEDS_REPLAN = "needs_replan"
    MANAGER_RECOVERY = "manager_recovery"
    OPERATIONAL_FAILURE = "operational_failure"
    UNHANDLED = "unhandled"


@dataclass(frozen=True)
class NullMissionLifecycleSink:
    def manager_started(self) -> None:
        return None

    def manager_returned(self) -> None:
        return None


@dataclass(frozen=True)
class MissionSupervisor:
    manager: ManagerPort
    auditor: AuditorPort | None = None
    boundary: EvidenceBoundary = EvidenceBoundary()
    final_response_boundary: FinalResponseBoundary = FinalResponseBoundary()
    max_rounds: int = 8
    strict_verification: bool = False
    trace_sink: RunTraceSink = NullRunTraceSink()
    official_outcome_sink: object | None = None
    lifecycle_sink: object = NullMissionLifecycleSink()

    async def run(
        self,
        runtime,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> MissionRunResult:
        runtime = _with_episode_monitor(runtime)
        mission = MissionState.empty()
        state: RunState | None = None
        manager_calls = auditor_calls = boundary_rejections = 0
        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return _result(
                state,
                mission,
                MissionOutcome.TASK_BLOCKED,
                manager_calls,
                auditor_calls,
                boundary_rejections,
            )
        current_world = acquisition.observation
        initial_request = ManagerRoleRequest(
            mode=ManagerRequestMode.INITIAL_PLAN,
            original_task=task,
            mission_state=mission,
            last_typed_exit="task_start",
            remaining_rounds=self.max_rounds,
            environment=project_mission_environment(current_world, ()),
        )
        self.lifecycle_sink.manager_started()
        try:
            initial = await self.manager.decide(initial_request)
        finally:
            self.lifecycle_sink.manager_returned()
        manager_calls += 1
        _record_role_invocation(
            self.trace_sink,
            "manager",
            manager_calls,
            initial_request,
            initial,
            trigger_kind="task_start",
            subtask_id="",
            mission_version=mission.version,
        )
        if initial.failure is not None or initial.output is None:
            return _result(
                state,
                mission,
                MissionOutcome.MANAGER_FAILURE,
                manager_calls,
                auditor_calls,
                boundary_rejections,
            )
        decision = initial.output
        terminal = _non_execution_manager_result(
            decision,
            state,
            mission,
            manager_calls,
            auditor_calls,
            boundary_rejections,
        )
        if terminal is not None:
            return terminal
        assert decision.subtask is not None
        active_subtask = decision.subtask
        pending_boundary_feedback = ""

        for round_index in range(self.max_rounds):
            episode_start_world = current_world
            state = await runtime.initialize_from_world(
                task,
                current_world,
                subtask_goal_resolution(task, active_subtask),
                max_turns=active_subtask.episode_turn_budget,
                yield_on_budget_exhaustion=True,
                working_facts=mission.carry_working_facts(active_subtask.relevant_fact_keys),
                active_subtask=_action_policy_subtask_contract(active_subtask),
            )
            state = await runtime.continue_task(environment, task, state)
            route = _episode_route(state)
            if route is _EpisodeRoute.TASK_COMPLETE:
                state.status = RunStatus.DONE
                return _result(
                    state,
                    mission,
                    MissionOutcome.TASK_COMPLETE,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            if route in {_EpisodeRoute.TASK_BLOCKED, _EpisodeRoute.RUNTIME_BLOCKED}:
                state.status = RunStatus.BLOCKED
                return _result(
                    state,
                    mission,
                    MissionOutcome.TASK_BLOCKED,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            if route is _EpisodeRoute.CANCELLED:
                return _result(
                    state,
                    mission,
                    MissionOutcome.CANCELLED,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            if route is _EpisodeRoute.WAITING_USER:
                return _result(
                    state,
                    mission,
                    MissionOutcome.NEEDS_USER_INPUT,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            if route is _EpisodeRoute.UNHANDLED:
                state.status = RunStatus.FAILED
                return _result(
                    state,
                    mission,
                    MissionOutcome.UNHANDLED_EPISODE_STATE,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )

            review_capture = await environment.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "fresh ManagerReview evidence",
                )
            )
            if (
                review_capture.status is not AcquisitionStatus.ACQUIRED
                or review_capture.observation is None
            ):
                state.status = RunStatus.FAILED
                return _result(
                    state,
                    mission,
                    MissionOutcome.OPERATIONAL_FAILURE,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            current_world = review_capture.observation
            state.current_world = current_world
            evidence = EvidenceBundle.from_world(current_world, state.working_facts)
            recovery = _review_recovery_view(
                route,
                state,
                active_subtask,
                episode_start_world,
                working_proposal_feedback=pending_boundary_feedback,
            )
            pending_boundary_feedback = ""
            review_request = ManagerRoleRequest(
                mode=ManagerRequestMode.REVIEW_AND_ROUTE,
                original_task=task,
                mission_state=mission,
                last_typed_exit=recovery.exit_kind,
                last_audit_or_failure_ref=_review_failure_ref(route, state),
                remaining_rounds=self.max_rounds - round_index,
                recovery=recovery,
                environment=project_mission_environment(current_world, state.recent_steps),
                active_subtask=active_subtask,
                review_world=current_world,
                evidence_bundle=evidence,
                final_response_schema=_public_final_response_schema(task),
                allowed_evidence_refs=_allowed_current_evidence_refs(evidence),
                episode_working_facts=state.working_facts,
                changed_evidence_refs=_new_or_changed_evidence_refs(
                    episode_start_world,
                    current_world,
                    evidence,
                ),
            )
            review = await self.manager.decide(review_request)
            manager_calls += 1
            _record_role_invocation(
                self.trace_sink,
                "manager",
                manager_calls,
                review_request,
                review,
                trigger_kind=_review_trigger(route, state),
                subtask_id=_subtask_id(active_subtask),
                mission_version=mission.version,
            )
            if review.failure is not None or review.output is None:
                return _result(
                    state,
                    mission,
                    MissionOutcome.MANAGER_FAILURE,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            decision = review.output
            repeated_strategy = bool(
                decision.route is ManagerRoute.EXECUTE_SUBTASK
                and _failed_or_stalled(route)
                and _repeats_failed_strategy(decision, recovery)
            )
            if repeated_strategy and route is _EpisodeRoute.NEEDS_REPLAN:
                assert recovery.recovery_signal is not None
                deliberate_recovery = replace(
                    recovery,
                    exit_kind="strategy_not_changed",
                    recovery_signal=RecoverySignal(
                        RecoveryKind.SUBTASK_MISALIGNED,
                        recovery.recovery_signal.stable_signature,
                        {
                            "reason": "Manager repeated the rejected subtask strategy",
                            "prior_reason": recovery.recovery_signal.observed_evidence,
                        },
                        prohibited_immediate_repeat=_subtask_id(active_subtask),
                        recovery_attempt=2,
                    ),
                )
                deliberate_request = replace(
                    review_request,
                    last_typed_exit="strategy_not_changed",
                    last_audit_or_failure_ref="subtask_misaligned",
                    recovery=deliberate_recovery,
                )
                deliberate = await self.manager.decide(deliberate_request)
                manager_calls += 1
                _record_role_invocation(
                    self.trace_sink,
                    "manager",
                    manager_calls,
                    deliberate_request,
                    deliberate,
                    trigger_kind="subtask_misaligned_deliberate_replan",
                    subtask_id=_subtask_id(active_subtask),
                    mission_version=mission.version,
                )
                if deliberate.failure is not None or deliberate.output is None:
                    return _result(
                        state,
                        mission,
                        MissionOutcome.MANAGER_FAILURE,
                        manager_calls,
                        auditor_calls,
                        boundary_rejections,
                    )
                decision = deliberate.output
                repeated_strategy = _repeats_failed_strategy(decision, deliberate_recovery)
            if repeated_strategy:
                state.status = RunStatus.BLOCKED
                return _result(
                    state,
                    mission,
                    MissionOutcome.STRATEGY_NOT_CHANGED,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )

            allowed_review_evidence = set(review_request.allowed_evidence_refs)
            cited_review_evidence = {
                *decision.evidence_refs,
                *decision.final_response_evidence_refs,
                *(
                    ref
                    for outcome in decision.working_outcomes
                    for ref in outcome.evidence_refs
                ),
                *(fact.evidence_ref for fact in decision.working_facts),
            }
            if not cited_review_evidence.issubset(allowed_review_evidence):
                boundary_rejections += 1
                return _result(
                    state,
                    mission,
                    MissionOutcome.BOUNDARY_REJECTED,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                )

            proposal = decision.state_proposal(mission.version)
            final_response = None
            if decision.route is ManagerRoute.REQUEST_FINALIZATION:
                if not getattr(environment, "supports_finalization", False):
                    return _result(
                        state,
                        mission,
                        MissionOutcome.FINALIZATION_NOT_READY,
                        manager_calls,
                        auditor_calls,
                        boundary_rejections,
                    )
                final_boundary = self.final_response_boundary.admit(
                    decision,
                    review_request,
                    mission,
                    already_finalized=False,
                )
                _record_final_response_boundary(
                    self.trace_sink,
                    review_request,
                    decision,
                    final_boundary,
                )
                if not final_boundary.admitted or final_boundary.response is None:
                    return _result(
                        state,
                        mission,
                        MissionOutcome.FINALIZATION_NOT_READY,
                        manager_calls,
                        auditor_calls,
                        boundary_rejections,
                        final_response_boundary_rejection_count=1,
                        final_response_rejection_code=(
                            final_boundary.rejection_code.value
                            if final_boundary.rejection_code is not None
                            else FinalResponseRejection.FINAL_RESPONSE_INVALID.value
                        ),
                    )
                final_response = final_boundary.response

            requires_strict_audit = bool(
                self.strict_verification
                and active_subtask.related_audit_ids
                and proposal is not None
                and proposal.working_outcomes
                and decision.route is not ManagerRoute.REQUEST_FINALIZATION
            )
            if requires_strict_audit:
                if auditor_calls:
                    return _result(
                        state,
                        mission,
                        MissionOutcome.AUDITOR_FAILURE,
                        manager_calls,
                        auditor_calls,
                        boundary_rejections,
                    )
                if self.auditor is None:
                    return _result(
                        state,
                        mission,
                        MissionOutcome.AUDITOR_FAILURE,
                        manager_calls,
                        auditor_calls,
                        boundary_rejections,
                    )
                audit_request = AuditorRoleRequest.from_authorities(
                    task,
                    active_subtask,
                    mission,
                    current_world,
                    state.working_facts,
                    "outcome_proposed",
                    (),
                    evidence,
                    active_subtask.related_audit_ids,
                )
                audit = await self.auditor.audit(audit_request)
                auditor_calls += 1
                _record_role_invocation(
                    self.trace_sink,
                    "auditor",
                    auditor_calls,
                    audit_request,
                    audit,
                    trigger_kind="strict_exceptional_claim",
                    subtask_id=_subtask_id(active_subtask),
                    mission_version=mission.version,
                )
                if (
                    audit.failure is not None
                    or audit.output is None
                    or audit.output.assessment is not ManagerAssessment.SATISFIED
                    or not audit.output.evidence_refs
                    or any(
                        ref not in _allowed_current_evidence_refs(evidence)
                        for ref in audit.output.evidence_refs
                    )
                ):
                    return _result(
                        state,
                        mission,
                        MissionOutcome.AUDITOR_FAILURE,
                        manager_calls,
                        auditor_calls,
                        boundary_rejections,
                    )

            if proposal is not None:
                admitted = self.boundary.accept(mission, proposal, evidence)
                if not admitted.accepted:
                    boundary_rejections += 1
                    if (
                        admitted.rejection_class
                        is EvidenceBoundaryRejectionClass.RECOVERABLE_SHAPE
                        and decision.route is ManagerRoute.EXECUTE_SUBTASK
                    ):
                        pending_boundary_feedback = (
                            f"working_proposal_rejected:{admitted.reason_code}"
                        )
                    else:
                        return _result(
                            state,
                            mission,
                            MissionOutcome.BOUNDARY_REJECTED,
                            manager_calls,
                            auditor_calls,
                            boundary_rejections,
                        )
                else:
                    mission = admitted.mission_state

            if decision.route is ManagerRoute.REQUEST_FINALIZATION:
                assert final_response is not None
                return await self._finalize(
                    runtime,
                    environment,
                    task,
                    state,
                    mission,
                    manager_calls,
                    auditor_calls,
                    boundary_rejections,
                    final_response,
                )

            terminal = _non_execution_manager_result(
                decision,
                state,
                mission,
                manager_calls,
                auditor_calls,
                boundary_rejections,
            )
            if terminal is not None:
                return terminal
            assert decision.subtask is not None
            active_subtask = decision.subtask

        state.status = RunStatus.BLOCKED
        return _result(
            state,
            mission,
            MissionOutcome.ROUND_BUDGET_EXHAUSTED,
            manager_calls,
            auditor_calls,
            boundary_rejections,
        )

    async def _finalize(
        self,
        runtime,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        mission: MissionState,
        manager_calls: int,
        auditor_calls: int,
        boundary_rejections: int,
        response: FinalResponse,
    ) -> MissionRunResult:
        finalization = await environment.finalize(response.content)
        delivered = finalization.result.dispatch_status is not DispatchStatus.NOT_SENT
        if not delivered or finalization.post_acquisition is None:
            state.status = RunStatus.FAILED
            _record_finalization_protocol(
                self.trace_sink,
                1,
                int(finalization.post_acquisition is not None),
                0,
                finalization.result.dispatch_status.value,
            )
            return _result(
                state,
                mission,
                MissionOutcome.FINALIZED,
                manager_calls,
                auditor_calls,
                boundary_rejections,
                final_response_boundary_admission_count=1,
                stop_send_count=1,
                post_stop_capture_count=int(finalization.post_acquisition is not None),
                delivered=delivered,
                finalization=finalization,
            )
        post = finalization.post_acquisition
        if post.status is not AcquisitionStatus.ACQUIRED or post.observation is None:
            state.status = RunStatus.FAILED
        else:
            state.current_world = post.observation
            state.current_task_evaluation = await runtime.task_evaluator.evaluate(
                task, post.observation
            )
            _record_native_evaluator_returned(
                self.trace_sink,
                self.official_outcome_sink,
                state.current_task_evaluation,
            )
            state.status = _status_for_terminal_evaluation(
                state.current_task_evaluation.status
            )
        _record_finalization_protocol(
            self.trace_sink,
            1,
            1,
            int(post.status is AcquisitionStatus.ACQUIRED and post.observation is not None),
            finalization.result.dispatch_status.value,
        )
        return _result(
            state,
            mission,
            MissionOutcome.FINALIZED,
            manager_calls,
            auditor_calls,
            boundary_rejections,
            final_response_boundary_admission_count=1,
            stop_send_count=1,
            post_stop_capture_count=1,
            native_evaluator_count=int(
                post.status is AcquisitionStatus.ACQUIRED
                and post.observation is not None
            ),
            delivered=delivered,
            finalization=finalization,
        )


def _result(
    state: RunState | None,
    mission: MissionState,
    outcome: MissionOutcome,
    manager_calls: int,
    auditor_calls: int,
    boundary_rejections: int,
    *,
    final_response_boundary_admission_count: int = 0,
    final_response_boundary_rejection_count: int = 0,
    stop_send_count: int = 0,
    post_stop_capture_count: int = 0,
    native_evaluator_count: int = 0,
    final_response_rejection_code: str = "",
    delivered: bool = False,
    finalization: EnvironmentFinalization | None = None,
    user_question: str = "",
) -> MissionRunResult:
    phase = SupervisorPhase.TERMINAL
    if outcome is MissionOutcome.NEEDS_USER_INPUT:
        phase = SupervisorPhase.WAITING_USER
    return MissionRunResult(
        state,
        mission,
        SupervisorState(
            phase,
            last_typed_episode_exit=outcome.value,
            last_ref=outcome.value,
            final_response_delivered=delivered,
        ),
        outcome,
        manager_calls,
        auditor_calls,
        final_response_boundary_admission_count,
        final_response_boundary_rejection_count,
        stop_send_count,
        post_stop_capture_count,
        native_evaluator_count,
        boundary_rejections,
        final_response_rejection_code,
        user_question,
        finalization,
    )


def _non_execution_manager_result(
    decision: ManagerDecision,
    state: RunState | None,
    mission: MissionState,
    manager_calls: int,
    auditor_calls: int,
    boundary_rejections: int,
) -> MissionRunResult | None:
    if decision.route is ManagerRoute.ASK_USER:
        return _result(
            state,
            mission,
            MissionOutcome.NEEDS_USER_INPUT,
            manager_calls,
            auditor_calls,
            boundary_rejections,
            user_question=decision.question,
        )
    if decision.route is ManagerRoute.BLOCKED:
        if state is not None:
            state.status = RunStatus.BLOCKED
        return _result(
            state,
            mission,
            MissionOutcome.BLOCKED,
            manager_calls,
            auditor_calls,
            boundary_rejections,
        )
    if decision.route is ManagerRoute.REQUEST_FINALIZATION:
        return _result(
            state,
            mission,
            MissionOutcome.FINALIZATION_NOT_READY,
            manager_calls,
            auditor_calls,
            boundary_rejections,
        )
    return None


def _episode_route(state: RunState) -> _EpisodeRoute:
    evaluation = state.current_task_evaluation.status
    if evaluation is TaskEvaluationStatus.COMPLETE:
        return _EpisodeRoute.TASK_COMPLETE
    if evaluation is TaskEvaluationStatus.BLOCKED:
        return _EpisodeRoute.TASK_BLOCKED
    if state.status in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}:
        return _EpisodeRoute.WAITING_USER
    if state.status is RunStatus.CANCELLED:
        return _EpisodeRoute.CANCELLED
    if state.status is RunStatus.BLOCKED:
        return _EpisodeRoute.RUNTIME_BLOCKED
    if state.status is RunStatus.FAILED:
        return _EpisodeRoute.OPERATIONAL_FAILURE
    if state.status is RunStatus.YIELDED:
        if state.yield_reason is EpisodeYieldReason.OUTCOME_PROPOSED:
            return _EpisodeRoute.OUTCOME_PROPOSED
        if state.yield_reason is EpisodeYieldReason.NEEDS_REPLAN:
            return _EpisodeRoute.NEEDS_REPLAN
        if state.yield_reason is not None:
            return _EpisodeRoute.MANAGER_RECOVERY
    return _EpisodeRoute.UNHANDLED


def _review_recovery_view(
    route: _EpisodeRoute,
    state: RunState,
    subtask: SubtaskContract,
    episode_start_world: WorldObservation,
    *,
    working_proposal_feedback: str = "",
) -> ManagerRecoveryView:
    exit_kind = (
        state.yield_reason.value
        if state.yield_reason is not None
        else route.value
    )
    replan_reason = (
        state.last_step.decision.reason
        if route is _EpisodeRoute.NEEDS_REPLAN
        and state.last_step is not None
        and isinstance(state.last_step.decision, YieldSubtask)
        else ""
    )
    recovery_signal = state.recovery_signal
    if route is _EpisodeRoute.NEEDS_REPLAN:
        recovery_signal = RecoverySignal(
            RecoveryKind.SUBTASK_MISALIGNED,
            _subtask_id(subtask),
            {"reason": replan_reason},
            prohibited_immediate_repeat=_subtask_id(subtask),
        )
    return ManagerRecoveryView(
        exit_kind,
        _world_changed(episode_start_world, state.current_world),
        subtask,
        recovery_signal=recovery_signal,
        attempted_modes=_episode_attempted_modes(state),
        outcome_proposal=(
            state.last_step.decision.reason
            if state.last_step is not None
            and isinstance(state.last_step.decision, YieldSubtask)
            and state.last_step.decision.kind == "outcome_proposed"
            else ""
        ),
        working_proposal_feedback=working_proposal_feedback,
    )


def _review_trigger(route: _EpisodeRoute, state: RunState) -> str:
    if route is _EpisodeRoute.OUTCOME_PROPOSED:
        return "outcome_proposed"
    if route is _EpisodeRoute.NEEDS_REPLAN:
        return "subtask_misaligned"
    if route is _EpisodeRoute.OPERATIONAL_FAILURE:
        return "failed_subtask"
    if state.yield_reason is EpisodeYieldReason.BUDGET:
        return "subtask_budget_exhausted"
    return "typed_stall_or_gap"


def _review_failure_ref(route: _EpisodeRoute, state: RunState) -> str:
    if route is _EpisodeRoute.OPERATIONAL_FAILURE:
        if state.runtime_failure is not None:
            return state.runtime_failure.code
        if state.policy_failure is not None:
            return state.policy_failure.kind.value
        if state.failure_code is not None:
            return state.failure_code.value
    return state.yield_reason.value if state.yield_reason is not None else route.value


def _failed_or_stalled(route: _EpisodeRoute) -> bool:
    return route in {
        _EpisodeRoute.MANAGER_RECOVERY,
        _EpisodeRoute.NEEDS_REPLAN,
        _EpisodeRoute.OPERATIONAL_FAILURE,
    }


_MONITOR_EVENT_NAMES = frozenset(
    {
        "state_changed",
        "no_observed_change",
        "repeated_action",
        "oscillation",
        "formal_criterion_changed",
        "provider_failure",
        "environment_failure",
        "capability_gap",
    }
)


def _episode_attempted_modes(state: RunState) -> tuple[str, ...]:
    modes = [
        item.semantic_action
        for item in state.recent_steps
        if item.semantic_action and item.semantic_action not in _MONITOR_EVENT_NAMES
    ]
    if state.recovery_signal is not None:
        modes.extend(
            item
            for item in state.recovery_signal.attempted_modes
            if item not in _MONITOR_EVENT_NAMES
        )
    return tuple(dict.fromkeys(modes))[:32]


def _world_changed(before: WorldObservation, after: WorldObservation) -> bool:
    return public_world_semantic_digest(before) != public_world_semantic_digest(after)


def _repeats_failed_strategy(
    decision: ManagerDecision,
    recovery: ManagerRecoveryView | None,
) -> bool:
    if (
        recovery is None
        or decision.route is not ManagerRoute.EXECUTE_SUBTASK
        or decision.subtask is None
    ):
        return False
    return _subtask_strategy(decision.subtask) == _subtask_strategy(
        recovery.prior_subtask
    )


def _subtask_strategy(subtask: SubtaskContract) -> tuple[object, ...]:
    return (
        subtask.objective,
        subtask.done_when,
        subtask.task_link,
        subtask.outcome_kind.value,
        tuple((item.key, item.description) for item in subtask.required_evidence),
    )


def _public_final_response_schema(task: TaskGoal) -> Mapping[str, object]:
    contract = task.inputs.get(PUBLIC_FINAL_RESPONSE_CONTRACT_KEY)
    if isinstance(contract, Mapping):
        schema = contract.get("json_schema")
        if isinstance(schema, Mapping) and schema:
            return schema
    return {}


def _allowed_current_evidence_refs(bundle: EvidenceBundle) -> tuple[str, ...]:
    sources = set(bundle.source_observation_ids)
    return tuple(
        record.evidence_ref
        for record in bundle.evidence_records
        if (
            record.kind == "fact"
            and is_public_scalar(record.value)
            and record.has_typed_source
            and (
                record.evidence_ref in bundle.pinned_evidence_refs
                or (
                    record.observation_id == bundle.observation_id
                    and record.source_observation_id in sources
                    and bundle.source_coverages.get(record.source_observation_id, "") != "stale"
                )
            )
        )
    )


def _new_or_changed_evidence_refs(
    before: WorldObservation,
    after: WorldObservation,
    bundle: EvidenceBundle,
) -> tuple[str, ...]:
    before_records = (
        *WorldEvidenceIndex.from_observation(before).records,
        *public_text_evidence_records(before),
    )
    before_signatures = {
        (item.kind, item.source_id, item.predicate, to_json_compatible(item.value))
        for item in before_records
        if item.kind == "fact" and is_public_scalar(item.value)
    }
    return tuple(
        item.evidence_ref
        for item in bundle.evidence_records
        if (
            item.observation_id == after.observation_id
            and item.kind == "fact"
            and is_public_scalar(item.value)
            and (item.kind, item.source_id, item.predicate, to_json_compatible(item.value))
            not in before_signatures
        )
    )[:32]


def _status_for_terminal_evaluation(status: TaskEvaluationStatus) -> RunStatus:
    if status is TaskEvaluationStatus.COMPLETE:
        return RunStatus.DONE
    if status is TaskEvaluationStatus.BLOCKED:
        return RunStatus.BLOCKED
    return RunStatus.FAILED


def _run_status_for_mission_outcome(
    outcome: MissionOutcome,
    state: RunState | None,
) -> RunStatus:
    if outcome is MissionOutcome.FINALIZED:
        return state.status if state is not None else RunStatus.FAILED
    mapping = {
        MissionOutcome.RUNNING: RunStatus.RUNNING,
        MissionOutcome.NEEDS_USER_INPUT: RunStatus.WAITING_USER,
        MissionOutcome.BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.BOUNDARY_REJECTED: RunStatus.FAILED,
        MissionOutcome.EVIDENCE_GAP: RunStatus.BLOCKED,
        MissionOutcome.FINALIZATION_NOT_READY: RunStatus.FAILED,
        MissionOutcome.CANCELLED: RunStatus.CANCELLED,
        MissionOutcome.TASK_COMPLETE: RunStatus.DONE,
        MissionOutcome.TASK_BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.STRATEGY_NOT_CHANGED: RunStatus.BLOCKED,
        MissionOutcome.ROUND_BUDGET_EXHAUSTED: RunStatus.BLOCKED,
    }
    return mapping.get(outcome, RunStatus.FAILED)


def _with_episode_monitor(runtime):
    if getattr(runtime, "episode_monitor", None) is not None:
        return runtime
    with_controls = getattr(runtime, "with_runtime_controls", None)
    if not callable(with_controls):
        return runtime
    return with_controls(
        tuple(getattr(runtime, "runtime_controls", ())),
        episode_monitor=EpisodeMonitor(),
    )


def _record_role_invocation(
    trace_sink: RunTraceSink,
    role: str,
    call_index: int,
    request: object,
    result: object,
    *,
    trigger_kind: str,
    subtask_id: str,
    mission_version: int,
) -> None:
    recorder = getattr(trace_sink, "mission_role_invocation", None)
    if callable(recorder):
        recorder(
            role,
            call_index,
            request,
            result,
            trigger_kind=trigger_kind,
            execution_mode="mission",
            subtask_id=subtask_id,
            mission_version=mission_version,
        )


def _record_finalization_protocol(
    trace_sink: RunTraceSink,
    stop_send_count: int,
    post_stop_capture_count: int,
    native_evaluator_count: int,
    dispatch_status: str,
) -> None:
    recorder = getattr(trace_sink, "finalization_protocol", None)
    if callable(recorder):
        recorder(
            stop_send_count=stop_send_count,
            post_stop_capture_count=post_stop_capture_count,
            native_evaluator_count=native_evaluator_count,
            dispatch_status=dispatch_status,
        )


def _record_native_evaluator_returned(
    trace_sink: RunTraceSink,
    official_outcome_sink: object | None,
    evaluation: object,
) -> None:
    recorder = getattr(official_outcome_sink, "native_evaluator_returned", None)
    if not callable(recorder):
        recorder = getattr(trace_sink, "native_evaluator_returned", None)
    if callable(recorder):
        recorder(evaluation)


def _record_final_response_boundary(
    trace_sink: RunTraceSink,
    review: ManagerRoleRequest,
    decision: ManagerDecision,
    result,
) -> None:
    recorder = getattr(trace_sink, "final_response_boundary_evaluated", None)
    if callable(recorder):
        recorder(
            mission_version=review.mission_state.version,
            review_world_observation_id=(
                review.review_world.observation_id
                if review.review_world is not None
                else ""
            ),
            schema_digest=result.schema_digest,
            cited_evidence_refs=decision.final_response_evidence_refs,
            admitted=result.admitted,
            rejection_code=(
                result.rejection_code.value
                if result.rejection_code is not None
                else ""
            ),
            response_digest=result.response_digest,
        )


def _subtask_id(subtask: SubtaskContract) -> str:
    payload = json.dumps(
        to_json_compatible(
            (
                subtask.objective,
                subtask.done_when,
                subtask.task_link,
                subtask.constraints,
                subtask.relevant_fact_keys,
                tuple((item.key, item.description) for item in subtask.required_evidence),
                subtask.outcome_kind.value,
            )
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"subtask:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def _action_policy_subtask_contract(subtask: SubtaskContract) -> AgentSubtaskContractView:
    return AgentSubtaskContractView(
        subtask.objective,
        subtask.done_when,
        subtask.task_link,
        subtask.outcome_kind.value,
        subtask.constraints,
        tuple((item.key, item.description) for item in subtask.required_evidence),
    )
