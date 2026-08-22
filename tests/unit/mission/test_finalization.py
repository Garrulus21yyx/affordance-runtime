import asyncio

import pytest

from affordance_runtime.agent import EpisodeYieldReason, FinalResponse, RunState, RunStatus, StepResult
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.mission import (
    EvidenceBundle,
    EvidenceRequirement,
    FinalResponseBoundary,
    FinalResponseRejection,
    Milestone,
    MilestoneRoadmap,
    MissionOutcome,
    MissionSupervisor,
    PlannerDecision,
    PlannerRoute,
)
from affordance_runtime.mission.supervisor import _public_final_response_schema
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import AcquisitionOrigin, SemanticTarget, StateFact
from affordance_runtime.world.finalization import EnvironmentFinalization
from tests.support.observation_acquisition import acquired_acquisition
from tests.support.world import fused_world


def _bundle():
    world = fused_world(
        "source:result",
        targets=(SemanticTarget("answer", "status", "Answer"),),
        facts=(StateFact("result", "answer", "value", "ready", "source:result"),),
    )
    bundle = EvidenceBundle.from_world(world)
    assert bundle.evidence_records
    return bundle


def test_mechanical_final_response_admits_current_evidence_without_an_llm_finalizer() -> None:
    bundle = _bundle()
    evidence_ref = bundle.evidence_records[0].evidence_ref
    result = FinalResponseBoundary().admit(
        FinalResponse("context:1", "ready", (evidence_ref,)),
        {"type": "string", "const": "ready"},
        bundle,
        already_finalized=False,
    )
    assert result.admitted


def test_final_response_rejects_repeated_send_before_stop_dispatch() -> None:
    bundle = _bundle()
    evidence_ref = bundle.evidence_records[0].evidence_ref
    result = FinalResponseBoundary().admit(
        FinalResponse("context:1", "ready", (evidence_ref,)),
        {"type": "string"},
        bundle,
        already_finalized=True,
    )
    assert result.rejection_code is FinalResponseRejection.ALREADY_FINALIZED


@pytest.mark.parametrize(
    "schema",
    [
        {"allOf": ({"type": "string", "const": "ready"},)},
        {"type": "object", "properties": {}, "const": {}},
        {"type": "array", "items": {"type": "string"}, "properties": {}},
        {"type": "boolean", "const": 1},
        {"type": "boolean", "enum": [1]},
        {"type": "integer", "const": True},
        {"type": "integer", "enum": [True]},
        {"type": "number", "const": float("nan")},
        {"type": "number", "minimum": float("nan")},
        {"type": "number", "maximum": float("inf")},
    ],
)
def test_final_response_rejects_unsupported_public_json_schema_shapes(schema) -> None:
    bundle = _bundle()
    evidence_ref = bundle.evidence_records[0].evidence_ref
    result = FinalResponseBoundary().admit(
        FinalResponse("context:1", '"wrong"', (evidence_ref,)),
        schema,
        bundle,
        already_finalized=False,
    )

    assert result.rejection_code is FinalResponseRejection.FINAL_RESPONSE_INVALID


def test_final_response_rejects_an_overflowed_non_finite_json_number() -> None:
    bundle = _bundle()
    evidence_ref = bundle.evidence_records[0].evidence_ref
    result = FinalResponseBoundary().admit(
        FinalResponse("context:1", "1e999", (evidence_ref,)),
        {"type": "number"},
        bundle,
        already_finalized=False,
    )

    assert result.rejection_code is FinalResponseRejection.FINAL_RESPONSE_INVALID


def test_supervisor_uses_the_webarena_json_schema_contract_key() -> None:
    schema = {"type": "object", "required": ["retrieved_data"]}
    task = TaskGoal(
        "task:json-final",
        "Return structured data",
        inputs={PUBLIC_FINAL_RESPONSE_CONTRACT_KEY: {"json_schema": schema}},
    )
    assert _public_final_response_schema(task) == schema


class _Planner:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, request):
        del request
        self.calls += 1
        roadmap = MilestoneRoadmap(
            1,
            (Milestone("answer", "Return the supported answer", "The answer is visible", final=True),),
        )
        return ModelInvocationResult(output=PlannerDecision(PlannerRoute.ROADMAP, roadmap))


class _RequiredEvidencePlanner(_Planner):
    async def plan(self, request):
        del request
        self.calls += 1
        roadmap = MilestoneRoadmap(
            1,
            (
                Milestone(
                    "answer",
                    "Return the supported answer",
                    "The answer is visible",
                    (EvidenceRequirement("required_answer", "Exact supported answer"),),
                    final=True,
                ),
            ),
        )
        return ModelInvocationResult(output=PlannerDecision(PlannerRoute.ROADMAP, roadmap))


class _Evaluator:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        evidence_ref = EvidenceBundle.from_world(observation).evidence_records[0].evidence_ref
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE,
            "native success",
            completion_evidence_refs=(evidence_ref,),
        )


class _FinalResponseRuntime:
    def __init__(self, *, final_status=RunStatus.YIELDED) -> None:
        self.episode_monitor = object()
        self.task_evaluator = _Evaluator()
        self.final_status = final_status

    async def initialize_from_world(
        self,
        task,
        initial,
        goal_resolution,
        *,
        budget,
        yield_on_budget_exhaustion,
        working_facts,
        active_milestone,
    ):
        del goal_resolution, yield_on_budget_exhaustion, working_facts, active_milestone
        return RunState(
            initial,
            TaskEvaluation(task.task_id, initial.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
            budget.turns,
            yield_on_budget_exhaustion=True,
        )

    async def continue_task(self, environment, task, state):
        del environment
        evidence_ref = EvidenceBundle.from_world(state.current_world).evidence_records[0].evidence_ref
        decision = FinalResponse("context:final", "ready", (evidence_ref,))
        state.apply(
            StepResult(
                decision,
                state.current_world,
                state.current_world,
                TaskEvaluation(task.task_id, state.current_world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
                self.final_status,
                feedback="final_response_submitted",
                yield_reason=(
                    EpisodeYieldReason.FINAL_RESPONSE
                    if self.final_status is RunStatus.YIELDED
                    else None
                ),
            )
        )
        return state


class _FinalizingEnvironment:
    def __init__(self, before, after, dispatch_status=DispatchStatus.SENT_UNKNOWN) -> None:
        from affordance_runtime.benchmarks.support import ScriptedEnvironment

        self.delegate = ScriptedEnvironment(initial_observation=before)
        self.after = after
        self.dispatch_status = dispatch_status
        self.finalize_calls = 0

    async def reset(self, task):
        return await self.delegate.reset(task)

    async def finalize(self, content):
        assert content == "ready"
        self.finalize_calls += 1
        return EnvironmentFinalization(
            ActionResult(
                "stop:1",
                self.dispatch_status,
                "browsergym",
                False,
                ActionError.EXECUTION_FAILED,
            ),
            acquired_acquisition(self.after, AcquisitionOrigin.POST_ACTION, acquisition_id="post-stop:1"),
        )


def test_sent_unknown_stop_is_not_replayed_and_post_world_is_evaluated_once() -> None:
    before = fused_world(
        "source:pre-stop",
        targets=(SemanticTarget("answer", "status", "Answer"),),
        facts=(StateFact("result", "answer", "value", "ready", "source:pre-stop"),),
    )
    after = fused_world(
        "source:post-stop",
        targets=(SemanticTarget("answer", "status", "Answer"),),
        facts=(StateFact("result", "answer", "value", "ready", "source:post-stop"),),
    )
    environment = _FinalizingEnvironment(before, after)
    planner = _Planner()
    runtime = _FinalResponseRuntime()

    result = asyncio.run(MissionSupervisor(planner).run(runtime, environment, TaskGoal("task:final", "Return answer")))

    assert result.outcome is MissionOutcome.FINALIZED
    assert result.status is RunStatus.DONE
    assert result.supervisor_state.final_response_delivered
    assert result.stop_send_count == environment.finalize_calls == 1
    assert result.post_stop_capture_count == 1
    assert result.native_evaluator_count == runtime.task_evaluator.calls == 1


def test_not_sent_stop_cannot_turn_an_inconsistent_post_capture_into_official_success() -> None:
    before = fused_world(
        "source:not-sent-pre",
        targets=(SemanticTarget("answer", "status", "Answer"),),
        facts=(StateFact("result", "answer", "value", "ready", "source:not-sent-pre"),),
    )
    after = fused_world(
        "source:not-sent-post",
        targets=(SemanticTarget("answer", "status", "Answer"),),
        facts=(StateFact("result", "answer", "value", "ready", "source:not-sent-post"),),
    )
    environment = _FinalizingEnvironment(before, after, DispatchStatus.NOT_SENT)
    runtime = _FinalResponseRuntime()

    result = asyncio.run(
        MissionSupervisor(_Planner()).run(runtime, environment, TaskGoal("task:not-sent", "Return answer"))
    )

    assert result.outcome is MissionOutcome.FINALIZATION_NOT_READY
    assert result.status is RunStatus.FAILED
    assert not result.supervisor_state.final_response_delivered
    assert result.stop_send_count == 0
    assert result.post_stop_capture_count == 0
    assert result.native_evaluator_count == runtime.task_evaluator.calls == 0
    assert result.terminal_evaluation is None


def test_failed_final_response_step_cannot_be_reinterpreted_as_permission_to_send_stop() -> None:
    before = fused_world(
        "source:failed-final",
        targets=(SemanticTarget("answer", "status", "Answer"),),
        facts=(StateFact("result", "answer", "value", "ready", "source:failed-final"),),
    )
    environment = _FinalizingEnvironment(before, before)
    runtime = _FinalResponseRuntime(final_status=RunStatus.FAILED)

    result = asyncio.run(
        MissionSupervisor(_Planner()).run(runtime, environment, TaskGoal("task:failed-final", "Return answer"))
    )

    assert result.outcome is MissionOutcome.OPERATIONAL_FAILURE
    assert environment.finalize_calls == result.stop_send_count == 0
    assert runtime.task_evaluator.calls == 0


def test_final_milestone_cannot_vacuously_bypass_a_missing_required_working_fact() -> None:
    world = fused_world(
        "source:missing-required-final",
        targets=(SemanticTarget("unrelated", "status", "Unrelated"),),
        facts=(StateFact("result", "unrelated", "value", "ready", "source:missing-required-final"),),
    )
    environment = _FinalizingEnvironment(world, world)
    runtime = _FinalResponseRuntime()

    result = asyncio.run(
        MissionSupervisor(_RequiredEvidencePlanner()).run(
            runtime,
            environment,
            TaskGoal("task:missing-required-final", "Return answer"),
        )
    )

    assert result.outcome is MissionOutcome.FINALIZATION_NOT_READY
    assert result.final_response_boundary_rejection_count == 1
    assert result.stop_send_count == environment.finalize_calls == 0
    assert result.native_evaluator_count == runtime.task_evaluator.calls == 0
