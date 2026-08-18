from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime.agent import Abort, AskUser, YieldSubtask
from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.mission import (
    AuditDelta,
    AuditDeltaStatus,
    AuditorRoleRequest,
    ManagerDecision,
    ManagerRoleRequest,
    ManagerRoute,
    MissionSupervisor,
    OutcomeProposal,
    PromoteFactProposal,
    SubtaskContract,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
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


def test_unknown_missing_evidence_retry_success_counts_both_auditor_calls() -> None:
    fake, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript([ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract)], [])
    auditor = UnknownThenSatisfiedAuditor([])

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=1).run(runtime, env, task))

    assert len(auditor.requests) == 2
    assert result.auditor_calls == 2
    assert fake.capture_count == 2
    assert result.mission_state.version == 1


def test_accepted_carry_fact_enters_later_episode_without_becoming_fresh_world_fact() -> None:
    _, env, task = _env_task()
    policy = YieldPolicy([])
    runtime = _runtime(policy)
    contract = SubtaskContract("Read value", "Value is read", episode_turn_budget=1)
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, contract),
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
