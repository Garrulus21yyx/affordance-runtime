"""Mechanical milestone supervisor around the single CoreAgentLoop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.budgets import EpisodeBudget
from affordance_runtime.agent.context.contracts import AgentMilestoneContractView
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.agent.decisions import FinalResponse, YieldMilestone
from affordance_runtime.agent.episode_snapshot import EpisodeSnapshot, snapshot_episode
from affordance_runtime.agent.observability import NullRunTraceSink, RunTraceSink
from affordance_runtime.agent.run_state import EpisodeYieldReason, RunState, RunStatus
from affordance_runtime.evaluation.contracts import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.mission.boundary import EvidenceBoundary
from affordance_runtime.mission.contracts import (
    AuditorPort,
    AuditorRoleRequest,
    EvidenceAssessment,
    EvidenceBundle,
    ExecutionMode,
    Milestone,
    MissionOutcome,
    MissionState,
    PlannerPort,
    PlannerRecoveryView,
    PlannerRequestMode,
    PlannerRoleRequest,
    PlannerRoute,
    RecoveryKind,
    RecoverySignal,
    SupervisorPhase,
    SupervisorState,
    WorkingFactProposal,
    WorkingOutcomeProposal,
    WorkingStateProposal,
)
from affordance_runtime.mission.environment_projection import project_mission_environment
from affordance_runtime.mission.finalization import FinalResponseBoundary, FinalResponseRejection
from affordance_runtime.mission.goal_projection import milestone_goal_resolution
from affordance_runtime.mission.monitor import EpisodeMonitor
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import AcquisitionStatus
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.finalization import EnvironmentFinalization


@dataclass(frozen=True)
class MissionRunResult:
    state: RunState | None
    mission_state: MissionState
    supervisor_state: SupervisorState
    outcome: MissionOutcome = MissionOutcome.RUNNING
    planner_calls: int = 0
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
    terminal_evaluation: TaskEvaluation | None = None
    episode_snapshot: EpisodeSnapshot | None = None

    @property
    def status(self) -> RunStatus:
        return _run_status_for_mission_outcome(self.outcome, self.state, self.terminal_evaluation)

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
        if self.terminal_evaluation is not None:
            return self.terminal_evaluation.outcome
        return self.state.task_outcome if self.state is not None else None

    @property
    def sent_unknown_count(self) -> int:
        return self.state.sent_unknown_count if self.state is not None else 0


class _EpisodeRoute(StrEnum):
    FINAL_RESPONSE = "final_response"
    TASK_COMPLETE = "task_complete"
    TASK_BLOCKED = "task_blocked"
    WAITING_USER = "waiting_user"
    CANCELLED = "cancelled"
    OUTCOME_PROPOSED = "outcome_proposed"
    NEEDS_REPLAN = "needs_replan"
    OPERATIONAL_FAILURE = "operational_failure"
    UNHANDLED = "unhandled"


@dataclass(frozen=True)
class NullMissionLifecycleSink:
    def planner_started(self) -> None:
        return None

    def planner_returned(self) -> None:
        return None


@dataclass(frozen=True)
class MissionSupervisor:
    planner: PlannerPort
    auditor: AuditorPort | None = None
    boundary: EvidenceBoundary = EvidenceBoundary()
    final_response_boundary: FinalResponseBoundary = FinalResponseBoundary()
    max_rounds: int = 8
    trace_sink: RunTraceSink = NullRunTraceSink()
    official_outcome_sink: object | None = None
    lifecycle_sink: object = NullMissionLifecycleSink()

    async def run(self, runtime, environment: WorldEnvironment, task: TaskGoal) -> MissionRunResult:
        attempt_sink = getattr(self.trace_sink, "mission_role_provider_attempt", None)
        if callable(attempt_sink):
            for role in (self.planner, self.auditor):
                binder = getattr(role, "bind_attempt_sink", None)
                if callable(binder):
                    binder(attempt_sink)
        runtime = _with_episode_monitor(runtime)
        mission = MissionState.empty()
        state: RunState | None = None
        planner_calls = auditor_calls = boundary_rejections = 0
        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return _result(state, mission, None, MissionOutcome.TASK_BLOCKED, 0, 0, 0)
        current_world = acquisition.observation
        request = PlannerRoleRequest(
            PlannerRequestMode.START,
            task,
            mission,
            remaining_mission_budget=self.max_rounds,
            environment=project_mission_environment(current_world, ()),
        )
        planned = await self._plan(request)
        planner_calls += 1
        _record_role_invocation(
            self.trace_sink,
            "planner",
            planner_calls,
            request,
            planned,
            trigger_kind="task_start",
            milestone_id="",
            mission_version=mission.version,
        )
        if planned.failure is not None or planned.output is None:
            return _result(state, mission, None, MissionOutcome.PLANNER_FAILURE, planner_calls, 0, 0)
        terminal = _non_roadmap_result(planned.output, state, mission, None, planner_calls, 0, 0)
        if terminal is not None:
            return terminal
        roadmap = planned.output.roadmap
        assert roadmap is not None

        for round_index in range(self.max_rounds):
            active = roadmap.select_ready(mission)
            if active is None:
                return _result(
                    state,
                    mission,
                    roadmap,
                    MissionOutcome.FINALIZATION_NOT_READY,
                    planner_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            episode_start_world = current_world
            carry_keys = tuple(item.key for item in active.required_evidence)
            state = await runtime.initialize_from_world(
                task,
                current_world,
                milestone_goal_resolution(task, active, plan_version=roadmap.version),
                budget=EpisodeBudget.ordinary(),
                yield_on_budget_exhaustion=True,
                working_facts=mission.carry_working_facts(carry_keys),
                active_milestone=_action_policy_milestone_contract(active),
            )
            state = await runtime.continue_task(environment, task, state)
            current_world = state.current_world
            route = _episode_route(state)
            if route is _EpisodeRoute.FINAL_RESPONSE:
                decision = state.last_step.decision if state.last_step is not None else None
                assert isinstance(decision, FinalResponse)
                required_keys = {item.key for item in active.required_evidence}
                retained_keys = {item.key for item in state.working_facts}
                required_refs = {
                    item.record.evidence_ref
                    for item in state.working_facts
                    if item.key in required_keys
                }
                if required_keys and (
                    not required_keys.issubset(retained_keys)
                    or not required_refs.issubset(decision.evidence_refs)
                ):
                    return _result(
                        state,
                        mission,
                        roadmap,
                        MissionOutcome.FINALIZATION_NOT_READY,
                        planner_calls,
                        auditor_calls,
                        boundary_rejections,
                        final_response_boundary_rejection_count=1,
                        final_response_rejection_code=FinalResponseRejection.EVIDENCE_LINEAGE_INVALID.value,
                    )
                bundle = EvidenceBundle.from_world(current_world, state.working_facts)
                admitted = self.final_response_boundary.admit(
                    decision,
                    _public_final_response_schema(task),
                    bundle,
                    already_finalized=False,
                )
                _record_final_response_boundary(
                    self.trace_sink,
                    mission,
                    current_world.observation_id,
                    decision.evidence_refs,
                    admitted,
                )
                if not admitted.admitted or admitted.response is None:
                    return _result(
                        state,
                        mission,
                        roadmap,
                        MissionOutcome.FINALIZATION_NOT_READY,
                        planner_calls,
                        auditor_calls,
                        boundary_rejections,
                        final_response_boundary_rejection_count=1,
                        final_response_rejection_code=(
                            admitted.rejection_code.value
                            if admitted.rejection_code is not None
                            else FinalResponseRejection.FINAL_RESPONSE_INVALID.value
                        ),
                    )
                return await self._finalize(
                    runtime,
                    environment,
                    task,
                    state,
                    mission,
                    roadmap,
                    planner_calls,
                    auditor_calls,
                    boundary_rejections,
                    admitted.response,
                )
            if route is _EpisodeRoute.TASK_BLOCKED:
                return _result(state, mission, roadmap, MissionOutcome.TASK_BLOCKED, planner_calls, auditor_calls, boundary_rejections)
            if route is _EpisodeRoute.WAITING_USER:
                return _result(state, mission, roadmap, MissionOutcome.NEEDS_USER_INPUT, planner_calls, auditor_calls, boundary_rejections)
            if route is _EpisodeRoute.CANCELLED:
                return _result(state, mission, roadmap, MissionOutcome.CANCELLED, planner_calls, auditor_calls, boundary_rejections)
            if route is _EpisodeRoute.OPERATIONAL_FAILURE:
                return _result(state, mission, roadmap, MissionOutcome.OPERATIONAL_FAILURE, planner_calls, auditor_calls, boundary_rejections)
            if route is _EpisodeRoute.UNHANDLED:
                return _result(state, mission, roadmap, MissionOutcome.UNHANDLED_EPISODE_STATE, planner_calls, auditor_calls, boundary_rejections)
            if route in {_EpisodeRoute.OUTCOME_PROPOSED, _EpisodeRoute.TASK_COMPLETE}:
                summary = _outcome_summary(state, active)
                admission = self.boundary.evaluate_milestone(
                    mission,
                    active,
                    episode_start_world,
                    current_world,
                    state.working_facts,
                    summary,
                )
                proposal = admission.proposal
                if admission.assessment is EvidenceAssessment.UNKNOWN:
                    if self.auditor is None:
                        return _result(state, mission, roadmap, MissionOutcome.EVIDENCE_GAP, planner_calls, auditor_calls, boundary_rejections)
                    bundle = EvidenceBundle.from_world(current_world, state.working_facts)
                    audit_request = AuditorRoleRequest.from_authorities(
                        task,
                        active,
                        mission,
                        current_world,
                        state.working_facts,
                        "outcome_proposed",
                        state.recent_steps,
                        bundle,
                    )
                    audit = await self.auditor.audit(audit_request)
                    auditor_calls += 1
                    _record_role_invocation(
                        self.trace_sink,
                        "auditor",
                        auditor_calls,
                        audit_request,
                        audit,
                        trigger_kind="deterministic_admission_unknown",
                        milestone_id=active.id,
                        mission_version=mission.version,
                    )
                    if audit.failure is not None or audit.output is None:
                        return _result(state, mission, roadmap, MissionOutcome.AUDITOR_FAILURE, planner_calls, auditor_calls, boundary_rejections)
                    if audit.output.assessment is not EvidenceAssessment.SATISFIED:
                        return _result(state, mission, roadmap, MissionOutcome.EVIDENCE_GAP, planner_calls, auditor_calls, boundary_rejections)
                    proposal = _audited_proposal(mission, active, state, audit.output.evidence_refs, summary)
                assert proposal is not None
                accepted = self.boundary.accept(mission, proposal, EvidenceBundle.from_world(current_world, state.working_facts))
                if not accepted.accepted:
                    boundary_rejections += 1
                    return _result(state, mission, roadmap, MissionOutcome.BOUNDARY_REJECTED, planner_calls, auditor_calls, boundary_rejections)
                mission = accepted.mission_state
                if active.final:
                    return _result(state, mission, roadmap, MissionOutcome.FINALIZATION_NOT_READY, planner_calls, auditor_calls, boundary_rejections)
                continue

            assert route is _EpisodeRoute.NEEDS_REPLAN
            recovery = PlannerRecoveryView(
                "needs_replan",
                episode_start_world.observation_id != current_world.observation_id,
                active,
                state.recovery_signal or RecoverySignal(
                    RecoveryKind.MILESTONE_MISALIGNED,
                    f"milestone:{active.id}",
                    {"yield_reason": state.yield_reason.value if state.yield_reason is not None else "needs_replan"},
                ),
                outcome_proposal=_outcome_summary(state, active),
            )
            replan_request = PlannerRoleRequest(
                PlannerRequestMode.NEEDS_REPLAN,
                task,
                mission,
                roadmap,
                "needs_replan",
                self.max_rounds - round_index - 1,
                recovery,
                project_mission_environment(current_world, state.recent_steps),
                active.id,
            )
            replanned = await self._plan(replan_request)
            planner_calls += 1
            _record_role_invocation(
                self.trace_sink,
                "planner",
                planner_calls,
                replan_request,
                replanned,
                trigger_kind="needs_replan",
                milestone_id=active.id,
                mission_version=mission.version,
            )
            if replanned.failure is not None or replanned.output is None:
                return _result(state, mission, roadmap, MissionOutcome.PLANNER_FAILURE, planner_calls, auditor_calls, boundary_rejections)
            terminal = _non_roadmap_result(replanned.output, state, mission, roadmap, planner_calls, auditor_calls, boundary_rejections)
            if terminal is not None:
                return terminal
            assert replanned.output.roadmap is not None
            next_roadmap = replanned.output.roadmap
            if not _roadmap_revision_preserves_accepted_semantics(roadmap, next_roadmap, mission):
                return _result(
                    state,
                    mission,
                    roadmap,
                    MissionOutcome.PLANNER_FAILURE,
                    planner_calls,
                    auditor_calls,
                    boundary_rejections,
                )
            roadmap = next_roadmap

        return _result(state, mission, roadmap, MissionOutcome.ROUND_BUDGET_EXHAUSTED, planner_calls, auditor_calls, boundary_rejections)

    async def _plan(self, request: PlannerRoleRequest):
        self.lifecycle_sink.planner_started()
        try:
            return await self.planner.plan(request)
        finally:
            self.lifecycle_sink.planner_returned()

    async def _finalize(
        self,
        runtime,
        environment,
        task,
        state,
        mission,
        roadmap,
        planner_calls,
        auditor_calls,
        boundary_rejections,
        response,
    ) -> MissionRunResult:
        finalization = await environment.finalize(response.content)
        dispatch_status = finalization.result.dispatch_status
        delivered = dispatch_status is not DispatchStatus.NOT_SENT
        post = finalization.post_acquisition
        terminal_evaluation = None
        native_count = 0
        successful_post_capture = bool(
            delivered
            and post is not None
            and post.status is AcquisitionStatus.ACQUIRED
            and post.observation is not None
        )
        if successful_post_capture:
            assert post is not None and post.observation is not None
            terminal_evaluation = await runtime.task_evaluator.evaluate(task, post.observation)
            native_count = 1
            _record_native_evaluator_returned(self.trace_sink, self.official_outcome_sink, terminal_evaluation)
        _record_finalization_protocol(
            self.trace_sink,
            int(delivered),
            int(successful_post_capture),
            native_count,
            dispatch_status.value,
        )
        return _result(
            state,
            mission,
            roadmap,
            MissionOutcome.FINALIZED if delivered else MissionOutcome.FINALIZATION_NOT_READY,
            planner_calls,
            auditor_calls,
            boundary_rejections,
            final_response_boundary_admission_count=1,
            stop_send_count=int(delivered),
            post_stop_capture_count=int(successful_post_capture),
            native_evaluator_count=native_count,
            delivered=delivered,
            finalization=finalization,
            terminal_evaluation=terminal_evaluation,
        )


def _episode_route(state: RunState) -> _EpisodeRoute:
    if state.current_task_evaluation.status is TaskEvaluationStatus.BLOCKED:
        return _EpisodeRoute.TASK_BLOCKED
    if state.current_task_evaluation.status is TaskEvaluationStatus.COMPLETE:
        return _EpisodeRoute.TASK_COMPLETE
    if state.status in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}:
        return _EpisodeRoute.WAITING_USER
    if state.status is RunStatus.CANCELLED:
        return _EpisodeRoute.CANCELLED
    if state.status in {RunStatus.BLOCKED, RunStatus.FAILED}:
        return _EpisodeRoute.OPERATIONAL_FAILURE
    if state.last_step is not None and isinstance(state.last_step.decision, FinalResponse):
        return _EpisodeRoute.FINAL_RESPONSE
    if state.status is RunStatus.YIELDED:
        if state.yield_reason is EpisodeYieldReason.OUTCOME_PROPOSED:
            return _EpisodeRoute.OUTCOME_PROPOSED
        return _EpisodeRoute.NEEDS_REPLAN
    return _EpisodeRoute.UNHANDLED


def _roadmap_revision_preserves_accepted_semantics(before, after, mission: MissionState) -> bool:
    if after.version <= before.version:
        return False
    before_by_id = {item.id: item for item in before.milestones}
    after_by_id = {item.id: item for item in after.milestones}
    accepted_ids = {item.outcome_id for item in mission.working_outcomes}
    return all(
        milestone_id in after_by_id
        and before_by_id.get(milestone_id) == after_by_id[milestone_id]
        for milestone_id in accepted_ids
    )


def _non_roadmap_result(decision, state, mission, roadmap, planner_calls, auditor_calls, boundary_rejections):
    if decision.route is PlannerRoute.ASK_USER:
        return _result(
            state,
            mission,
            roadmap,
            MissionOutcome.NEEDS_USER_INPUT,
            planner_calls,
            auditor_calls,
            boundary_rejections,
            user_question=decision.question,
        )
    if decision.route is PlannerRoute.BLOCKED:
        return _result(state, mission, roadmap, MissionOutcome.BLOCKED, planner_calls, auditor_calls, boundary_rejections)
    return None


def _outcome_summary(state: RunState, milestone: Milestone) -> str:
    decision = state.last_step.decision if state.last_step is not None else None
    if isinstance(decision, YieldMilestone):
        return decision.reason
    return milestone.outcome


def _audited_proposal(mission, milestone, state, evidence_refs, summary):
    promoted = tuple(
        WorkingFactProposal(item.key, item.record.evidence_ref, item.purpose) for item in state.working_facts
    )
    return WorkingStateProposal(
        EvidenceAssessment.SATISFIED,
        mission.version,
        (
            WorkingOutcomeProposal(
                milestone.id,
                EvidenceAssessment.SATISFIED,
                evidence_refs,
                summary,
            ),
        ),
        promoted,
    )


def _action_policy_milestone_contract(milestone: Milestone) -> AgentMilestoneContractView:
    return AgentMilestoneContractView(
        milestone.id,
        milestone.outcome,
        milestone.done_when,
        tuple((item.key, item.description) for item in milestone.required_evidence),
        milestone.depends_on,
        milestone.final,
    )


def _public_final_response_schema(task: TaskGoal):
    value = task.inputs.get(PUBLIC_FINAL_RESPONSE_CONTRACT_KEY)
    if isinstance(value, Mapping):
        schema = value.get("json_schema")
        if isinstance(schema, Mapping):
            return schema
    return {"type": "string", "minLength": 1, "maxLength": 8_000}


def _result(
    state,
    mission,
    roadmap,
    outcome,
    planner_calls,
    auditor_calls,
    boundary_rejections,
    **details,
):
    terminal_evaluation = details.get("terminal_evaluation")
    control_status = _run_status_for_mission_outcome(outcome, state, terminal_evaluation)
    user_question = details.get("user_question", "")
    snapshot = snapshot_episode(
        state,
        control_status=control_status,
        mission_outcome=outcome,
        mission_last_ref=outcome.value,
        user_question=user_question,
        terminal_evaluation=terminal_evaluation,
    )
    delivered = details.pop("delivered", False)
    return MissionRunResult(
        state=state,
        mission_state=mission,
        supervisor_state=SupervisorState(
            phase=SupervisorPhase.WAITING_USER if outcome is MissionOutcome.NEEDS_USER_INPUT else SupervisorPhase.TERMINAL,
            roadmap=roadmap,
            last_typed_episode_exit=outcome.value,
            last_ref=outcome.value,
            final_response_delivered=delivered,
        ),
        outcome=outcome,
        planner_calls=planner_calls,
        auditor_calls=auditor_calls,
        boundary_rejections=boundary_rejections,
        episode_snapshot=snapshot,
        **details,
    )


def _status_for_terminal_evaluation(status: TaskEvaluationStatus) -> RunStatus:
    if status is TaskEvaluationStatus.COMPLETE:
        return RunStatus.DONE
    if status is TaskEvaluationStatus.BLOCKED:
        return RunStatus.BLOCKED
    return RunStatus.FAILED


def _run_status_for_mission_outcome(outcome, state, terminal_evaluation=None):
    if outcome is MissionOutcome.FINALIZED:
        return _status_for_terminal_evaluation(terminal_evaluation.status) if terminal_evaluation is not None else RunStatus.FAILED
    mapping = {
        MissionOutcome.RUNNING: RunStatus.RUNNING,
        MissionOutcome.NEEDS_USER_INPUT: RunStatus.WAITING_USER,
        MissionOutcome.BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.EVIDENCE_GAP: RunStatus.BLOCKED,
        MissionOutcome.CANCELLED: RunStatus.CANCELLED,
        MissionOutcome.TASK_COMPLETE: RunStatus.DONE,
        MissionOutcome.TASK_BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.ROUND_BUDGET_EXHAUSTED: RunStatus.BLOCKED,
    }
    return mapping.get(outcome, RunStatus.FAILED)


def _with_episode_monitor(runtime):
    if getattr(runtime, "episode_monitor", None) is not None:
        return runtime
    with_controls = getattr(runtime, "with_runtime_controls", None)
    if not callable(with_controls):
        return runtime
    return with_controls(tuple(getattr(runtime, "runtime_controls", ())), episode_monitor=EpisodeMonitor())


def _record_role_invocation(trace_sink, role, call_index, request, result, **metadata):
    recorder = getattr(trace_sink, "mission_role_invocation", None)
    if callable(recorder):
        recorder(role, call_index, request, result, execution_mode=ExecutionMode.MISSION.value, **metadata)


def _record_final_response_boundary(trace_sink, mission, observation_id, refs, result):
    recorder = getattr(trace_sink, "final_response_boundary_evaluated", None)
    if callable(recorder):
        recorder(
            mission_version=mission.version,
            review_world_observation_id=observation_id,
            schema_digest=result.schema_digest,
            cited_evidence_refs=refs,
            admitted=result.admitted,
            rejection_code=result.rejection_code.value if result.rejection_code is not None else "",
            response_digest=result.response_digest,
        )


def _record_finalization_protocol(trace_sink, stop_count, capture_count, evaluator_count, dispatch_status):
    recorder = getattr(trace_sink, "finalization_protocol", None)
    if callable(recorder):
        recorder(
            stop_send_count=stop_count,
            post_stop_capture_count=capture_count,
            native_evaluator_count=evaluator_count,
            dispatch_status=dispatch_status,
        )


def _record_native_evaluator_returned(trace_sink, official_outcome_sink, evaluation):
    recorder = getattr(official_outcome_sink, "native_evaluator_returned", None)
    if not callable(recorder):
        recorder = getattr(trace_sink, "native_evaluator_returned", None)
    if callable(recorder):
        recorder(evaluation)
