from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.task_projection import project_task
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.benchmarks.webarena_verified import (
    WA_W1_SMOKE_CASES,
    WebArenaVerifiedNativeEvaluator,
    open_webarena_verified_case,
)
from affordance_runtime.evaluation import (
    EvaluatedOutput,
    ProductionActionOutcomeProjector,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.mission import (
    AuditDelta,
    AuditDeltaStatus,
    AuditorRoleRequest,
    ManagerDecision,
    ManagerRoute,
    MissionOutcome,
    MissionRunResult,
    MissionState,
    MissionSupervisor,
    OutcomeProposal,
    PromoteFactProposal,
    SubtaskContract,
    SupervisorState,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.model.policy.grounded_tool_catalog import (
    GroundedToolPhase,
    compile_grounded_tool_catalog,
)
from affordance_runtime.world.acquisition import AcquisitionOrigin, ObservationRequestKind, WorldObservationRequest
from affordance_runtime.world.finalization import EnvironmentFinalization
from tests.support.observation_acquisition import acquired_acquisition
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
)
from tests.unit.mission.test_episode_lifecycle import ManagerScript, YieldPolicy


class YieldThenFinalPolicy:
    def __init__(self):
        self.contexts = []

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    @property
    def supports_final_response(self):
        return True

    async def decide(self, context):
        self.contexts.append(context)
        if "final_response" in context.runtime_controls:
            return FinalResponse(context.context_id, "Done")
        return await YieldPolicy([]).decide(context)


class PrematureFinalPolicy:
    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    @property
    def supports_final_response(self):
        return True

    async def decide(self, context):
        return FinalResponse(context.context_id, "too soon")


class UnknownEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.UNKNOWN, "unknown")


class CompleteEvaluator:
    async def evaluate(self, task, observation):
        ref = observation.facts[0].fact_id
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE,
            "complete",
            completion_evidence_refs=(ref,),
            outputs=(EvaluatedOutput("answer", "Done", (ref,)),),
        )


class PostStopCompleteEvaluator:
    def __init__(self, finalizing_environment):
        self.finalizing_environment = finalizing_environment
        self.calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        if not self.finalizing_environment.finalize_calls:
            return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.UNKNOWN, "pre-stop")
        ref = observation.facts[0].fact_id
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE,
            "post-stop complete",
            completion_evidence_refs=(ref,),
        )


class FinalAuditAuditor:
    def __init__(self, *, accept_final: bool):
        self.accept_final = accept_final
        self.requests: list[AuditorRoleRequest] = []

    async def audit(self, request):
        self.requests.append(request)
        record = next(item for item in request.audit_bundle.evidence_records if item.kind == "fact")
        if len(self.requests) == 1:
            return ModelInvocationResult(
                output=AuditDelta(
                    AuditDeltaStatus.AUDITED_SATISFIED,
                    0,
                    (OutcomeProposal("audit:first", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "answer"),),
                    (PromoteFactProposal("answer", record.evidence_ref, record.value, "answer"),),
                )
            )
        if not self.accept_final:
            return ModelInvocationResult(output=AuditDelta(AuditDeltaStatus.UNKNOWN, 1, missing_evidence=("readiness",)))
        return ModelInvocationResult(
            output=AuditDelta(
                AuditDeltaStatus.AUDITED_SATISFIED,
                1,
                (OutcomeProposal("audit:final", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "ready"),),
            )
        )


class EmptySatisfiedFinalAuditAuditor(FinalAuditAuditor):
    async def audit(self, request):
        self.requests.append(request)
        record = next(item for item in request.audit_bundle.evidence_records if item.kind == "fact")
        if len(self.requests) == 1:
            return ModelInvocationResult(
                output=AuditDelta(
                    AuditDeltaStatus.AUDITED_SATISFIED,
                    0,
                    (OutcomeProposal("audit:first", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "answer"),),
                )
            )
        return ModelInvocationResult(output=AuditDelta(AuditDeltaStatus.AUDITED_SATISFIED, 1))


class ContradictoryFinalAuditAuditor(FinalAuditAuditor):
    async def audit(self, request):
        self.requests.append(request)
        record = next(item for item in request.audit_bundle.evidence_records if item.kind == "fact")
        if len(self.requests) == 1:
            return ModelInvocationResult(
                output=AuditDelta(
                    AuditDeltaStatus.AUDITED_SATISFIED,
                    0,
                    (OutcomeProposal("audit:first", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "answer"),),
                    (PromoteFactProposal("answer", record.evidence_ref, record.value, "answer"),),
                )
            )
        return ModelInvocationResult(
            output=AuditDelta(
                AuditDeltaStatus.AUDITED_SATISFIED,
                1,
                (OutcomeProposal("audit:final", AuditDeltaStatus.AUDITED_UNSATISFIED, (record.evidence_ref,), "not ready"),),
            )
        )


class UnsatisfiedFinalAuditAuditor(FinalAuditAuditor):
    async def audit(self, request):
        self.requests.append(request)
        record = next(item for item in request.audit_bundle.evidence_records if item.kind == "fact")
        if len(self.requests) == 1:
            return ModelInvocationResult(
                output=AuditDelta(
                    AuditDeltaStatus.AUDITED_SATISFIED,
                    0,
                    (OutcomeProposal("audit:first", AuditDeltaStatus.AUDITED_SATISFIED, (record.evidence_ref,), "answer"),),
                )
            )
        return ModelInvocationResult(
            output=AuditDelta(
                AuditDeltaStatus.AUDITED_UNSATISFIED,
                1,
                (OutcomeProposal("audit:final", AuditDeltaStatus.AUDITED_UNSATISFIED, (record.evidence_ref,), "not ready"),),
            )
        )


def _browsergym_env_task(*, fail_final=False):
    raw = raw_observation(
        ax_node("input", "textbox", "Answer", value="Done"),
        ax_node("button", "button", "Continue"),
        goal="Complete the long task.",
    )
    fake = FakeBrowserGym(raw, fail_final=fail_final)
    env, task = open_fake(fake)
    return fake, env, task


class SentUnknownWithPostWorldEnvironment:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.finalize_calls = 0
        self.final_messages: list[str] = []
        self.last_world = None

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    @property
    def supports_finalization(self):
        return True

    async def reset(self, task):
        acquisition = await self.wrapped.reset(task)
        self.last_world = acquisition.observation
        return acquisition

    async def capture(self, request):
        acquisition = await self.wrapped.capture(request)
        if acquisition.observation is not None:
            self.last_world = acquisition.observation
        return acquisition

    async def execute(self, request):
        return await self.wrapped.execute(request)

    def is_current(self, request):
        return self.wrapped.is_current(request)

    async def finalize(self, content):
        self.finalize_calls += 1
        self.final_messages.append(content)
        assert self.last_world is not None
        return EnvironmentFinalization(
            ActionResult(
                "final-response",
                DispatchStatus.SENT_UNKNOWN,
                "browsergym",
                False,
                ActionError.EXECUTION_FAILED,
                {"effectful_dispatch_count": 1},
            ),
            acquired_acquisition(
                self.last_world,
                AcquisitionOrigin.POST_ACTION,
                kind=ObservationRequestKind.POST_ACTION_FALLBACK,
                acquisition_id="test:post-final-response",
            ),
        )


def test_all_mission_outcomes_have_closed_non_yielded_run_status() -> None:
    statuses = {
        outcome: MissionRunResult(None, MissionState.empty(), SupervisorState(), outcome).status
        for outcome in MissionOutcome
    }

    assert statuses == {
        MissionOutcome.RUNNING: RunStatus.RUNNING,
        MissionOutcome.NEEDS_USER_INPUT: RunStatus.WAITING_USER,
        MissionOutcome.BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.MANAGER_FAILURE: RunStatus.FAILED,
        MissionOutcome.AUDITOR_FAILURE: RunStatus.FAILED,
        MissionOutcome.BOUNDARY_REJECTED: RunStatus.RUNNING,
        MissionOutcome.EVIDENCE_GAP: RunStatus.BLOCKED,
        MissionOutcome.FINAL_AUDIT_NOT_READY: RunStatus.RUNNING,
        MissionOutcome.FINALIZED: RunStatus.FAILED,
        MissionOutcome.CANCELLED: RunStatus.CANCELLED,
        MissionOutcome.TASK_COMPLETE: RunStatus.DONE,
        MissionOutcome.TASK_BLOCKED: RunStatus.BLOCKED,
        MissionOutcome.ROUND_BUDGET_EXHAUSTED: RunStatus.BLOCKED,
    }


def test_ordinary_episode_catalog_exposes_yield_but_not_final_response_or_stop() -> None:
    _, env, task = _browsergym_env_task()
    world = asyncio.run(env.reset(task)).observation
    assert world is not None
    evaluation = asyncio.run(UnknownEvaluator().evaluate(task, world))
    action_space = ActionSpaceBuilder().build(task, world)
    context = ContextBuilder().build(
        task,
        world,
        action_space,
        evaluation,
        observation_capabilities=env.observation_capabilities,
        runtime_controls=("yield_subtask",),
    )

    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    names = {tool.spec.name for tool in catalog.tools}

    assert "yield_subtask" in names
    assert "final_response" not in names
    assert "STOP" not in names


def test_unaccepted_global_final_audit_cannot_send_stop() -> None:
    fake, env, task = _browsergym_env_task()
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
        ],
        [],
    )
    auditor = FinalAuditAuditor(accept_final=False)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.finalization is None
    assert fake.final_messages == []


def test_empty_satisfied_global_final_audit_cannot_send_stop() -> None:
    fake, env, task = _browsergym_env_task()
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
        ],
        [],
    )
    auditor = EmptySatisfiedFinalAuditAuditor(accept_final=True)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.outcome is MissionOutcome.ROUND_BUDGET_EXHAUSTED
    assert result.status is RunStatus.BLOCKED
    assert result.boundary_rejections == 1
    assert result.finalization is None
    assert fake.final_messages == []


def test_contradictory_satisfied_final_audit_cannot_send_stop() -> None:
    fake, env, task = _browsergym_env_task()
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
        ],
        [],
    )
    auditor = ContradictoryFinalAuditAuditor(accept_final=True)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.outcome is MissionOutcome.ROUND_BUDGET_EXHAUSTED
    assert result.boundary_rejections == 1
    assert result.finalization is None
    assert fake.final_messages == []
    assert result.mission_state.audited_outcomes[-1].audit_id == "audit:first"


def test_final_audit_requires_fresh_capture_before_auditor_or_stop() -> None:
    fake, env, task = _browsergym_env_task()
    fake.supports_capture_current = False
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
            ManagerDecision(ManagerRoute.BLOCKED, reason="fresh evidence missing"),
        ],
        [],
    )
    auditor = FinalAuditAuditor(accept_final=True)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.outcome is MissionOutcome.BLOCKED
    assert auditor.requests == []
    assert result.finalization is None
    assert fake.final_messages == []
    assert len(manager.requests) == 3
    assert manager.requests[1].last_typed_exit == "audit:evidence_gap"
    assert manager.requests[2].last_typed_exit == "final_audit:not_ready"
    assert manager.requests[2].last_audit_or_failure_ref == "final_audit_capture:capability_unavailable"


def test_final_audit_not_ready_returns_to_manager_when_budget_remains() -> None:
    fake, env, task = _browsergym_env_task()
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
            ManagerDecision(ManagerRoute.BLOCKED, reason="repair needed"),
        ],
        [],
    )
    auditor = FinalAuditAuditor(accept_final=False)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.outcome is MissionOutcome.BLOCKED
    assert result.finalization is None
    assert fake.final_messages == []
    assert len(manager.requests) == 3
    assert manager.requests[2].last_typed_exit == "final_audit:not_ready"
    assert manager.requests[2].last_audit_or_failure_ref == "audit_status_not_promotable"


def test_accepted_unsatisfied_final_audit_is_carried_back_to_manager() -> None:
    fake, env, task = _browsergym_env_task()
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
            ManagerDecision(ManagerRoute.BLOCKED, reason="repair needed"),
        ],
        [],
    )
    auditor = UnsatisfiedFinalAuditAuditor(accept_final=False)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=3).run(runtime, env, task))

    assert result.outcome is MissionOutcome.BLOCKED
    assert fake.final_messages == []
    assert [item.audit_id for item in result.mission_state.audited_outcomes] == ["audit:first", "audit:final"]
    assert result.mission_state.audited_outcomes[-1].status is AuditDeltaStatus.AUDITED_UNSATISFIED
    assert manager.requests[2].mission_state.version == 2


def test_sent_unknown_final_response_reads_acquired_post_world_once() -> None:
    fake, base_env, task = _browsergym_env_task()
    env = SentUnknownWithPostWorldEnvironment(base_env)
    policy = YieldThenFinalPolicy()
    evaluator = PostStopCompleteEvaluator(env)
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        evaluator,
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
        ],
        [],
    )
    auditor = FinalAuditAuditor(accept_final=True)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))

    assert result.finalization is not None
    assert result.finalization.result.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert result.finalization.post_acquisition is not None
    assert result.finalization.post_acquisition.observation is not None
    assert env.finalize_calls == 1
    assert env.final_messages == ["Done"]
    assert fake.final_messages == []
    assert evaluator.calls == 3
    assert result.state is not None
    assert result.state.current_task_evaluation.status is TaskEvaluationStatus.COMPLETE
    assert result.status is RunStatus.DONE


def test_accepted_final_audit_sends_stop_once() -> None:
    fake, env, task = _browsergym_env_task()
    policy = YieldThenFinalPolicy()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )
    manager = ManagerScript(
        [
            ManagerDecision(ManagerRoute.EXECUTE_SUBTASK, SubtaskContract("Read", "Read", episode_turn_budget=1)),
            ManagerDecision(ManagerRoute.REQUEST_FINAL_AUDIT, reason="ready"),
        ],
        [],
    )
    auditor = FinalAuditAuditor(accept_final=True)

    result = asyncio.run(MissionSupervisor(manager, auditor, max_rounds=2).run(runtime, env, task))
    second = asyncio.run(env.finalize("again"))

    assert result.finalization is not None
    assert result.finalization.result.dispatch_status is DispatchStatus.SENT
    assert second.result.dispatch_status is DispatchStatus.NOT_SENT
    assert fake.final_messages == ["Done"]
    assert [context.runtime_controls for context in policy.contexts] == [
        ("yield_subtask",),
        ("final_response",),
    ]


def test_premature_final_response_is_rejected_in_ordinary_episode() -> None:
    fake, env, task = _browsergym_env_task()
    runtime = compose_target_runtime(
        PrematureFinalPolicy(),
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )

    state = asyncio.run(runtime.run_task(env, task))

    assert state.status is RunStatus.FAILED
    assert state.last_step is not None
    assert state.last_step.feedback == "final_response_not_available"
    assert fake.final_messages == []


def test_completed_ordinary_long_horizon_episode_still_rejects_final_response() -> None:
    fake, env, task = _browsergym_env_task()
    task = replace(task, requested_outputs=("answer",))
    runtime = compose_target_runtime(
        PrematureFinalPolicy(),
        ProductionActionOutcomeProjector(),
        CompleteEvaluator(),
        required_decisions=frozenset({DecisionCapability.YIELD_SUBTASK}),
        runtime_controls=("yield_subtask",),
    )

    state = asyncio.run(runtime.run_task(env, task))

    assert state.status is RunStatus.FAILED
    assert state.last_step is not None
    assert state.last_step.feedback == "final_response_not_available"
    assert fake.final_messages == []


def test_sent_unknown_final_response_is_not_retried() -> None:
    fake, env, _task = _browsergym_env_task(fail_final=True)

    first = asyncio.run(env.finalize("answer"))
    second = asyncio.run(env.finalize("answer"))

    assert first.result.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert second.result.dispatch_status is DispatchStatus.NOT_SENT
    assert fake.final_messages == ["answer"]


def test_webarena_native_evaluator_is_incomplete_before_stop_and_authoritative_after_stop() -> None:
    raw = raw_observation(ax_node("button", "button", "Continue"), goal="Official public instruction")
    fake = FakeBrowserGym(raw)
    env, task, evaluator = open_webarena_verified_case(
        WA_W1_SMOKE_CASES[0],
        gym_factory=lambda *_args, **_kwargs: fake,
    )
    initial = asyncio.run(env.reset(task)).observation
    assert initial is not None

    before = asyncio.run(evaluator.evaluate(task, initial))
    finalization = asyncio.run(env.finalize("answer"))
    assert finalization.post_acquisition is not None
    after_world = finalization.post_acquisition.observation
    assert after_world is not None
    after = asyncio.run(evaluator.evaluate(task, after_world))

    assert before.status is TaskEvaluationStatus.INCOMPLETE
    assert after.status is TaskEvaluationStatus.COMPLETE
    assert isinstance(evaluator, WebArenaVerifiedNativeEvaluator)


def test_webarena_native_success_is_stop_gated_even_if_probe_reports_done() -> None:
    raw = raw_observation(ax_node("button", "button", "Continue"), goal="Official public instruction")
    fake = FakeBrowserGym(raw)
    fake.probe_task = {
        "ready": True,
        "done": True,
        "raw_reward": 1,
        "episode": "0",
    }
    env, task, evaluator = open_webarena_verified_case(
        WA_W1_SMOKE_CASES[0],
        gym_factory=lambda *_args, **_kwargs: fake,
    )
    initial = asyncio.run(env.reset(task)).observation
    assert initial is not None
    capture = asyncio.run(env.capture(WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "probe")))
    assert capture.observation is not None

    evaluation = asyncio.run(evaluator.evaluate(task, capture.observation))

    assert evaluation.status is TaskEvaluationStatus.INCOMPLETE
    assert evaluation.outcome is not None
    assert evaluation.outcome.code == "stop_not_confirmed"


def test_webarena_public_intake_does_not_project_hidden_expected_or_evaluator_data() -> None:
    raw = raw_observation(
        ax_node("button", "button", "Continue"),
        goal=(
            "Official public instruction\n\n---\nFinal response format: "
            "use send_msg_to_user with STOP schema"
        ),
    )
    fake = FakeBrowserGym(raw)
    env, task, _evaluator = open_webarena_verified_case(
        WA_W1_SMOKE_CASES[0],
        gym_factory=lambda *_args, **_kwargs: fake,
    )

    serialized = str(task).casefold()
    projected = project_task(task)
    projected_serialized = str(projected).casefold()
    assert "expected_answer" not in serialized
    assert "hidden" not in serialized
    assert "reward" not in serialized
    assert "evaluator" not in serialized
    assert task.instruction == "Official public instruction"
    assert task.task_id == "task:webarena_verified"
    assert task.inputs == {}
    for leaked in ("browsergym/webarena_verified", "shopping_admin", "smoke", "send_msg_to_user", "stop"):
        assert leaked not in projected_serialized
    assert task.requested_outputs == ("webarena_final_response",)
    asyncio.run(env.close())


def test_offline_eval_tasks_helper_is_not_wired_into_formal_runner() -> None:
    import affordance_runtime.benchmarks.target_loop.runner as runner

    source = inspect.getsource(runner)
    assert "eval-tasks" not in source
    assert "evaluate_webarena_verified_manifest" not in source
