from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from types import SimpleNamespace

from affordance_runtime.agent import (
    Abort,
    AskUser,
    LocalToolResult,
    ProtocolFeedback,
    ProtocolFeedbackKind,
    YieldSubtask,
)
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.core_loop import _world_fingerprint
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_state import EpisodeYieldReason, RunStatus
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.mission import (
    AuditDelta,
    AuditDeltaStatus,
    AuditorRoleRequest,
    ManagerDecision,
    ManagerRecoveryView,
    ManagerRoleRequest,
    ManagerRoute,
    MissionOutcome,
    MissionState,
    MissionSupervisor,
    OutcomeProposal,
    PromoteFactProposal,
    SubtaskContract,
)
from affordance_runtime.mission.supervisor import _episode_route, _EpisodeRoute, _repeats_failed_strategy
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.world.acquisition import ObservationRequestKind, WorldObservationRequest
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
)


class UnknownEvaluator:
    calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown")


class IncompleteEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.INCOMPLETE, "pre-stop incomplete")


class CompleteEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE,
            "terminal complete",
            completion_evidence_refs=(observation.facts[0].fact_id,),
        )


class BlockedEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.BLOCKED,
            "terminal blocked",
        )


@dataclass
class YieldPolicy:
    contexts: list[object]

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    async def decide(self, context):
        self.contexts.append(context)
        return YieldSubtask(context.context_id, "ready_for_audit", "ready")


@dataclass
class AskPolicy:
    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.ASK_USER})

    async def decide(self, context):
        return AskUser(context.context_id, "Need input")


@dataclass
class CancelPolicy:
    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.ABORT})

    async def decide(self, context):
        return Abort(context.context_id, "cancel", "user_request")


@dataclass
class PolicyFailurePolicy:
    contexts: list[object]

    @property
    def supported_decisions(self):
        return frozenset()

    async def decide(self, context):
        self.contexts.append(context)
        return PolicyFailure(ModelFailureKind.SCHEMA_ERROR, "invalid provider payload")


@dataclass
class RepeatedSearchPolicy:
    contexts: list[object]

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.REQUEST_EVIDENCE, DecisionCapability.YIELD_SUBTASK})

    async def decide(self, context):
        self.contexts.append(context)
        return LocalToolResult(
            context.context_id,
            "search_world",
            {"query": "2022"},
            {"kind": "Matches", "items": (), "total_count": 0},
        )


@dataclass
class RepeatedProtocolPolicy:
    contexts: list[object]

    @property
    def supported_decisions(self):
        return frozenset()

    async def decide(self, context):
        self.contexts.append(context)
        return ProtocolFeedback(
            context.context_id,
            ProtocolFeedbackKind.MULTIPLE_TOOL_CALLS,
            2,
            "multiple_tool_calls",
        )


@dataclass
class ManagerScript:
    decisions: list[ManagerDecision]
    requests: list[ManagerRoleRequest]

    async def decide(self, request):
        self.requests.append(request)
        return ModelInvocationResult(output=self.decisions.pop(0))


@dataclass
class AuditorScript:
    deltas: list[AuditDelta]
    requests: list[AuditorRoleRequest]

    async def audit(self, request):
        self.requests.append(request)
        if not self.deltas:
            failure = ModelFailure(ModelFailureKind.SCHEMA_ERROR, "no audit", False)
            return ModelInvocationResult(failure=failure)
        return ModelInvocationResult(output=self.deltas.pop(0))


@dataclass
class PromoteFirstAuditor:
    requests: list[AuditorRoleRequest]

    async def audit(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            record = next(item for item in request.audit_bundle.evidence_records if item.kind == "fact")
            return ModelInvocationResult(
                output=AuditDelta(
                    AuditDeltaStatus.AUDITED_SATISFIED,
                    0,
                    (
                        OutcomeProposal(
                            "audit:carry",
                            AuditDeltaStatus.AUDITED_SATISFIED,
                            (record.evidence_ref,),
                            "carried",
                        ),
                    ),
                    (PromoteFactProposal("answer", record.evidence_ref, record.value, "carry"),),
                )
            )
        return ModelInvocationResult(output=AuditDelta(AuditDeltaStatus.UNKNOWN, 1))


@dataclass
class UnknownThenSatisfiedAuditor:
    requests: list[AuditorRoleRequest]

    async def audit(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return ModelInvocationResult(output=AuditDelta(AuditDeltaStatus.UNKNOWN, 0, missing_evidence=("fresh_value",)))
        record = next(item for item in request.audit_bundle.evidence_records if item.kind == "fact")
        return ModelInvocationResult(
            output=AuditDelta(
                AuditDeltaStatus.AUDITED_SATISFIED,
                0,
                (OutcomeProposal("audit:recaptured", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "recaptured"),),
            )
        )


def _runtime(policy, evaluator=None):
    return compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        evaluator or UnknownEvaluator(),
        runtime_controls=("yield_subtask",),
    )


def _env_task():
    raw = raw_observation(
        ax_node("input", "textbox", "Answer", value="Done"),
        ax_node("button", "button", "Continue"),
        goal="Complete the long task.",
    )
    fake = FakeBrowserGym(raw)
    env, task = open_fake(fake)
    return fake, env, task


def test_yield_subtask_has_zero_browsergym_dispatch_and_only_yields_episode() -> None:
    fake, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)

    state = asyncio.run(runtime.run_task(env, task))

    assert state.status is RunStatus.YIELDED
    assert state.yield_reason.value == "ready_for_audit"
    assert fake.actions == []
    assert state.current_task_evaluation.status is TaskEvaluationStatus.UNKNOWN


def test_same_browsergym_adapter_spans_two_episodes_without_trajectory_leak() -> None:
    fake, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Do next thing", "Next thing is done", episode_turn_budget=1)
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.BLOCKED, reason="stop"),
        ],
        [],
    )
    auditor = AuditorScript([AuditDelta(AuditDeltaStatus.UNKNOWN, 0), AuditDelta(AuditDeltaStatus.UNKNOWN, 0)], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.state is not None
    assert result.state.status is RunStatus.YIELDED
    assert fake.reset_count == 1
    assert env.surface.logical_reset_calls == 1
    assert len(policy.contexts) == 2
    assert [len(context.recent_steps.items) for context in policy.contexts] == [0, 0]


def test_auditor_failure_terminates_without_reexecuting_same_gui_subtask() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is visible", episode_turn_budget=1)
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
        ],
        [],
    )
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.outcome is MissionOutcome.AUDITOR_SCHEMA_FAILURE
    assert result.status is RunStatus.FAILED
    assert len(manager.requests) == 1
    assert len(auditor.requests) == 1
    assert len(policy.contexts) == 1


def test_policy_failure_is_typed_operational_terminal_and_never_audited() -> None:
    _, env, task = _env_task()
    policy = PolicyFailurePolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Do next thing", "Next thing is done", episode_turn_budget=1)
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
        ],
        [],
    )
    auditor = AuditorScript([AuditDelta(AuditDeltaStatus.UNKNOWN, 0), AuditDelta(AuditDeltaStatus.UNKNOWN, 0)], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=4).run(runtime, env, task))

    assert result.state is not None
    assert result.outcome is MissionOutcome.OPERATIONAL_FAILURE
    assert result.state.status is RunStatus.FAILED
    assert result.state.failure_code is None
    assert result.supervisor_state.last_typed_episode_exit == "operational_failure"
    assert len(policy.contexts) == 1
    assert len(manager.requests) == 1
    assert len(auditor.requests) == 0


def test_pre_stop_incomplete_task_evaluation_does_not_become_subtask_unsatisfied() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy, IncompleteEvaluator())
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript([ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)], [])
    auditor = PromoteFirstAuditor([])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert len(auditor.requests) == 1
    assert result.mission_state.version == 1
    assert result.mission_state.audited_outcomes[0].status is AuditDeltaStatus.AUDITED_SATISFIED


def test_terminal_task_evaluation_ends_case_without_writing_subtask_mission_outcome() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy, CompleteEvaluator())
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript([ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)], [])
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert result.state is not None
    assert result.state.status is RunStatus.DONE
    assert result.mission_state.version == 0
    assert auditor.requests == []


def test_blocked_task_evaluation_ends_case_without_calling_auditor() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy, BlockedEvaluator())
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript([ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)], [])
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert result.state is not None
    assert result.state.status is RunStatus.BLOCKED
    assert result.outcome is MissionOutcome.TASK_BLOCKED
    assert result.mission_state.version == 0
    assert auditor.requests == []


def test_unknown_missing_evidence_returns_manager_guidance_after_one_auditor_call() -> None:
    fake, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript([ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)], [])
    auditor = UnknownThenSatisfiedAuditor([])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert len(auditor.requests) == 1
    assert result.auditor_calls == 1
    assert fake.capture_count == 1
    assert result.mission_state.version == 0


def test_accepted_carry_fact_enters_later_episode_without_becoming_fresh_world_fact() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    followup = SubtaskContract(
        "Use carried value",
        "Carried value is used",
        relevant_fact_keys=("answer",),
        episode_turn_budget=1,
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, followup),
            ManagerDecision(ManagerRoute.BLOCKED, reason="stop"),
        ],
        [],
    )
    auditor = PromoteFirstAuditor([])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.mission_state.accepted_facts
    assert len(policy.contexts) == 2
    assert policy.contexts[1].working_facts
    carried = policy.contexts[1].working_facts[0]
    current_source_refs = {source.source_ref for source in policy.contexts[1].actor_world.sources}
    assert carried.record.source_observation_id not in current_source_refs


def test_irrelevant_carry_facts_do_not_enter_later_episode() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    first = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    second = SubtaskContract(
        "Continue without carry",
        "No carry fact is needed",
        relevant_fact_keys=("missing",),
        episode_turn_budget=1,
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, first),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, second),
            ManagerDecision(ManagerRoute.BLOCKED, reason="stop"),
        ],
        [],
    )
    auditor = PromoteFirstAuditor([])

    asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert len(policy.contexts) == 2
    assert policy.contexts[1].working_facts == ()


def test_fresh_audit_capture_failure_does_not_audit_or_write_old_world() -> None:
    fake, env, task = _env_task()
    fake.supports_capture_current = False
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.BLOCKED, reason="stop"),
        ],
        [],
    )
    auditor = PromoteFirstAuditor([])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.outcome is MissionOutcome.BLOCKED
    assert result.mission_state.version == 0
    assert auditor.requests == []
    assert manager.requests[1].last_typed_exit == "audit:evidence_gap"
    assert manager.requests[1].last_audit_or_failure_ref == "audit_capture:capability_unavailable"


def test_world_fingerprint_uses_stable_public_semantics_not_observation_id() -> None:
    fake, env, task = _env_task()
    first = asyncio.run(env.reset(task)).observation
    second = asyncio.run(env.capture(WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "same public page"))).observation

    assert first is not None
    assert second is not None
    assert first.observation_id != second.observation_id
    assert _world_fingerprint(first) == _world_fingerprint(second)


def test_mission_role_invocations_enter_trace_sink() -> None:
    _, env, task = _env_task()
    task = replace(
        task,
        inputs={
            "public_final_response_contract": {"json_schema": {"secret_final": "hidden"}},
            "hidden_benchmark_reward": 1,
        },
    )
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript([ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)], [])
    auditor = PromoteFirstAuditor([])
    trace = RunTraceRecorder()

    asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1, trace_sink=trace).run(runtime, env, task))

    events = [item for item in trace.events if item["event"] == "mission_role_invocation"]
    assert [item["role"] for item in events] == ["manager", "auditor"]
    assert events[0]["role_request"]["remaining_rounds"] == 1
    assert events[1]["role_request"]["yield_reason"] == "ready_for_audit"
    assert "inputs" not in events[1]["role_request"]["task"]
    assert "secret_final" not in repr(events[1]["role_request"])
    assert "hidden_benchmark_reward" not in repr(events[1]["role_request"])
    assert events[1]["model_invocation"]["output"]["status"] == "audited_satisfied"


def test_waiting_user_preserves_episode_and_does_not_call_auditor_or_replan() -> None:
    _, env, task = _env_task()
    runtime = _runtime(AskPolicy())
    manager = ManagerScript(
        [ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Ask", "Asked"))],
        [],
    )
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert result.state is not None
    assert result.state.status is RunStatus.WAITING_USER
    assert len(manager.requests) == 1
    assert auditor.requests == []


def test_cancellation_does_not_audit_retry_or_write_mission_state() -> None:
    _, env, task = _env_task()
    runtime = _runtime(CancelPolicy())
    manager = ManagerScript(
        [ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Cancel", "Cancelled"))],
        [],
    )
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert result.state is not None
    assert result.state.status is RunStatus.CANCELLED
    assert auditor.requests == []
    assert result.mission_state.version == 0


def test_control_stall_routes_directly_to_manager_and_blocks_unchanged_strategy() -> None:
    _, env, task = _env_task()
    policy = RepeatedSearchPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract(
        "Find the 2022 result",
        "The 2022 result is visible",
        episode_turn_budget=6,
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
        ],
        [],
    )
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.outcome is MissionOutcome.STRATEGY_NOT_CHANGED
    assert result.status is RunStatus.BLOCKED
    assert result.supervisor_state.last_ref == "strategy_not_changed"
    assert auditor.requests == []
    assert len(manager.requests) == 3
    recovery = manager.requests[1].recovery
    assert recovery is not None
    assert recovery.exit_kind == "control_stall"
    assert recovery.world_changed is False
    assert recovery.attempted_modes == ("search_world",)
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.observed_evidence["arguments"] == {"query": "2022"}
    assert recovery.recovery_signal.observed_evidence["item_count"] == 0
    assert recovery.recovery_signal.observed_evidence["same_result_count"] == 3
    assert manager.requests[2].recovery is not None
    assert manager.requests[2].recovery.strategy_revision_required is True


def test_repeated_multiple_calls_yield_protocol_stall_to_manager_without_auditor() -> None:
    _, env, task = _env_task()
    policy = RepeatedProtocolPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract(
        "Enter the remaining values one field at a time",
        "Both fields contain the requested values",
        episode_turn_budget=6,
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.BLOCKED, reason="protocol recovery exhausted"),
        ],
        [],
    )
    auditor = AuditorScript([], [])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.outcome is MissionOutcome.BLOCKED
    assert result.execution_count == 0
    assert len(policy.contexts) == 3
    assert auditor.requests == []
    assert len(manager.requests) == 2
    recovery = manager.requests[1].recovery
    assert recovery is not None
    assert recovery.exit_kind == EpisodeYieldReason.PROTOCOL_STALL.value
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.kind.value == "protocol_stall"
    assert manager.requests[1].environment.surface == "browser"
    assert "read_current_world" in manager.requests[1].environment.available_capabilities
    assert manager.requests[1].environment.unavailable_capabilities == ("public_web_search",)


def test_strategy_convergence_guard_does_not_block_after_world_change() -> None:
    contract = SubtaskContract("Continue collection", "Collection is complete")
    recovery = ManagerRecoveryView(
        "control_stall",
        True,
        contract,
        attempted_modes=("search_world",),
    )

    assert _repeats_failed_strategy(
        ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
        recovery,
    ) is False


def test_only_recovery_exits_bypass_auditor() -> None:
    direct = {
        reason
        for reason in EpisodeYieldReason
        if _episode_route(
            SimpleNamespace(
                status=RunStatus.YIELDED,
                yield_reason=reason,
                current_task_evaluation=SimpleNamespace(status=TaskEvaluationStatus.UNKNOWN),
            )
        )
        is _EpisodeRoute.MANAGER_RECOVERY
    }

    assert direct == set(EpisodeYieldReason) - {EpisodeYieldReason.READY_FOR_AUDIT}


def test_unknown_audit_guidance_reaches_only_the_next_manager_request() -> None:
    _, env, task = _env_task()
    runtime = _runtime(YieldPolicy([]))
    contract = SubtaskContract("Read the report", "The filtered ranking is visible")
    changed_contract = SubtaskContract(
        "Open a report with date controls",
        "A date-filtered report is visible",
        constraints=("Do not reuse the dashboard summary.",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, changed_contract),
            ManagerDecision(ManagerRoute.BLOCKED, reason="no supported route"),
        ],
        [],
    )
    auditor = AuditorScript(
        [
            AuditDelta(
                AuditDeltaStatus.UNKNOWN,
                0,
                missing_evidence=("a report filtered to 2022",),
                recovery_hint="Navigate to a report view exposing date controls.",
            ),
            AuditDelta(
                AuditDeltaStatus.UNKNOWN,
                0,
                missing_evidence=("ranking derived from that report",),
                recovery_hint="Do not use the dashboard summary as year-specific evidence.",
            ),
            AuditDelta(AuditDeltaStatus.UNKNOWN, 0),
        ],
        [],
    )

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.outcome is MissionOutcome.BLOCKED
    assert len(auditor.requests) == 2
    assert len(manager.requests) == 3
    recovery = manager.requests[1].recovery
    assert recovery is not None
    assert recovery.exit_kind == "audit:evidence_gap"
    assert recovery.audit_guidance is not None
    assert recovery.audit_guidance.missing_evidence == ("a report filtered to 2022",)
    assert "date controls" in recovery.audit_guidance.recovery_hint
    second_recovery = manager.requests[2].recovery
    assert second_recovery is not None
    assert second_recovery.audit_guidance is not None
    assert second_recovery.audit_guidance.missing_evidence == ("ranking derived from that report",)
    assert "dashboard summary" in second_recovery.audit_guidance.recovery_hint
    assert result.mission_state == MissionState.empty()
