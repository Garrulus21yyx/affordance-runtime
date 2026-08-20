from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace

import pytest

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.agent import FinalResponse, YieldSubtask
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.mission import (
    ManagerAssessment,
    ManagerDecision,
    ManagerRequestMode,
    ManagerRoute,
    MissionOutcome,
    MissionSupervisor,
    SubtaskContract,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    resolve_grounded_action_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolResolutionError
from affordance_runtime.model.policy.tool_contracts import ToolCall
from tests.support.model_delivery import delivery_for
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
)

FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "task_type": {"type": "string", "const": "RETRIEVE"},
        "status": {"type": "string", "enum": ["SUCCESS", "FAILURE"]},
        "retrieved_data": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "error_details": {"type": "null"},
    },
    "required": ["task_type", "status", "retrieved_data", "error_details"],
    "additionalProperties": False,
}
FINAL_VALUE = {
    "task_type": "RETRIEVE",
    "status": "SUCCESS",
    "retrieved_data": ["Done"],
    "error_details": None,
}


class UnknownEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.UNKNOWN,
            "pre-STOP",
        )


class PostStopEvaluator:
    def __init__(self, fake):
        self.fake = fake
        self.calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        status = (
            TaskEvaluationStatus.COMPLETE
            if self.fake.final_messages
            else TaskEvaluationStatus.UNKNOWN
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            "native",
            completion_evidence_refs=(observation.facts[0].fact_id,) if self.fake.final_messages else (),
        )


@dataclass
class YieldThenFinalPolicy:
    malformed: bool = False

    def __post_init__(self):
        self.contexts = []

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    async def decide(self, context):
        self.contexts.append(context)
        if context.runtime_controls == ("submit_final_response",):
            if self.malformed:
                return YieldSubtask(context.context_id, "outcome_proposed", "illegal fallback")
            return FinalResponse(
                context.context_id,
                json.dumps(FINAL_VALUE, separators=(",", ":")),
            )
        return YieldSubtask(context.context_id, "outcome_proposed", "candidate ready")


class SatisfiedManager:
    def __init__(self):
        self.requests = []

    async def decide(self, request):
        self.requests.append(request)
        if request.mode is ManagerRequestMode.INITIAL_PLAN:
            decision = ManagerDecision(
                ManagerAssessment.NOT_APPLICABLE,
                ManagerRoute.EXECUTE_SUBTASK,
                subtask=SubtaskContract("Read answer", "Answer is visible"),
            )
        else:
            record = next(
                item
                for item in request.evidence_bundle.evidence_records
                if item.kind == "fact" and item.value == "Done"
            )
            decision = ManagerDecision(
                ManagerAssessment.SATISFIED,
                ManagerRoute.REQUEST_FINALIZATION,
                (record.evidence_ref,),
                reason="Current evidence supports the response.",
            )
        return ModelInvocationResult(output=decision)


def _env_task(*, fail_final: bool = False):
    raw = raw_observation(
        ax_node("input", "textbox", "Answer", value="Done"),
        goal="Complete the long task.",
    )
    fake = FakeBrowserGym(raw, fail_final=fail_final)
    env, task = open_fake(fake)
    task = replace(
        task,
        inputs={
            PUBLIC_FINAL_RESPONSE_CONTRACT_KEY: {
                "format": "FinalAgentResponse",
                "json_schema": FINAL_SCHEMA,
            }
        },
    )
    return fake, env, task


def _context(runtime_controls):
    _, env, task = _env_task()
    world = asyncio.run(env.reset(task)).observation
    evaluation = asyncio.run(UnknownEvaluator().evaluate(task, world))
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        evaluation,
        observation_capabilities=env.observation_capabilities,
        runtime_controls=runtime_controls,
    )
    return context


def test_ordinary_executor_catalog_has_no_final_response_operation() -> None:
    context = _context(("yield_subtask",))
    catalog = compile_grounded_action_catalog(context, delivery_for(context))
    names = {item.spec.name for item in catalog.tools}

    assert "yield_subtask" in names
    assert "submit_final_response" not in names
    assert "final_response" not in names


def test_finalizing_catalog_contains_only_dynamic_submit_final_response() -> None:
    context = _context(("submit_final_response",))
    catalog = compile_grounded_action_catalog(context, delivery_for(context))

    assert [item.spec.name for item in catalog.tools] == ["submit_final_response"]
    assert catalog.specs[0].input_schema["properties"]["response"] == FINAL_SCHEMA


def test_json_and_native_envelopes_resolve_through_same_catalog_to_same_final_response() -> None:
    context = _context(("submit_final_response",))
    delivery = delivery_for(context)
    catalog = compile_grounded_action_catalog(context, delivery)
    calls = (
        ToolCall("submit_final_response", {"response": FINAL_VALUE}, "json-call"),
        ToolCall("submit_final_response", {"response": FINAL_VALUE}, "native-call"),
    )

    decisions = [
        resolve_grounded_action_call(
            catalog,
            call,
            expected_context_id=context.context_id,
            expected_delivery_id=delivery.delivery_id,
            expected_catalog_id=catalog.catalog_id,
        ).decision
        for call in calls
    ]

    assert all(isinstance(item, FinalResponse) for item in decisions)
    assert [json.loads(item.content) for item in decisions] == [FINAL_VALUE, FINAL_VALUE]


def test_malformed_final_response_is_typed_failure_and_cannot_fall_back_to_read_tools() -> None:
    context = _context(("submit_final_response",))
    delivery = delivery_for(context)
    catalog = compile_grounded_action_catalog(context, delivery)

    with pytest.raises(GroundedToolResolutionError):
        resolve_grounded_action_call(
            catalog,
            ToolCall("submit_final_response", {"response": {"status": "SUCCESS"}}),
            expected_context_id=context.context_id,
            expected_delivery_id=delivery.delivery_id,
        )

    assert {item.spec.name for item in catalog.tools}.isdisjoint(
        {"read_region", "search_world", "search_actions"}
    )


def test_normal_mission_has_two_manager_zero_auditor_one_finalizer_one_stop_one_native_evaluation() -> None:
    fake, env, task = _env_task()
    policy = YieldThenFinalPolicy()
    evaluator = PostStopEvaluator(fake)
    trace = RunTraceRecorder()
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        evaluator,
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(
        MissionSupervisor(
            SatisfiedManager(), None, max_rounds=2, trace_sink=trace
        ).run(runtime, env, task)
    )

    assert result.outcome is MissionOutcome.FINALIZED
    assert (result.manager_calls, result.auditor_calls, result.finalizer_calls) == (2, 0, 1)
    assert (
        result.stop_send_calls,
        result.post_stop_capture_calls,
        result.native_evaluator_calls,
    ) == (1, 1, 1)
    assert fake.final_messages == [json.dumps(FINAL_VALUE, separators=(",", ":"))]
    assert evaluator.calls == 3  # episode init, finalizing init, one post-STOP native evaluation
    assert [context.runtime_controls for context in policy.contexts] == [
        ("yield_subtask",),
        ("submit_final_response",),
    ]
    assert [fact.value for fact in policy.contexts[1].working_facts] == ["Done"]
    assert all(
        fact.record.observation_id
        == policy.contexts[1].current_observation.observation_id
        for fact in policy.contexts[1].working_facts
    )
    manager_events = [
        item
        for item in trace.events
        if item["event"] == "mission_role_invocation" and item["role"] == "manager"
    ]
    assert [item["manager_request_mode"] for item in manager_events] == [
        "initial_plan",
        "review_and_route",
    ]
    assert manager_events[1]["assessment"] == "satisfied"
    assert manager_events[1]["route"] == "request_finalization"
    protocol = next(item for item in trace.events if item["event"] == "finalization_protocol")
    assert (
        protocol["stop_send_count"],
        protocol["post_stop_capture_count"],
        protocol["native_evaluator_count"],
    ) == (1, 1, 1)


def test_malformed_finalizing_turn_does_not_reopen_executor_or_send_stop() -> None:
    fake, env, task = _env_task()
    policy = YieldThenFinalPolicy(malformed=True)
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(MissionSupervisor(SatisfiedManager(), None, max_rounds=2).run(runtime, env, task))

    assert result.outcome is MissionOutcome.FINALIZATION_NOT_READY
    assert result.finalizer_calls == 1
    assert fake.final_messages == []
    assert len(policy.contexts) == 2


def test_sent_unknown_does_not_retry_stop_and_still_runs_one_native_evaluation() -> None:
    fake, env, task = _env_task(fail_final=True)
    policy = YieldThenFinalPolicy()
    evaluator = PostStopEvaluator(fake)
    runtime = compose_target_runtime(
        policy,
        ProductionActionOutcomeProjector(),
        evaluator,
        runtime_controls=("yield_subtask",),
    )

    result = asyncio.run(
        MissionSupervisor(SatisfiedManager(), None, max_rounds=2).run(
            runtime, env, task
        )
    )

    assert len(fake.final_messages) == 1
    assert result.stop_send_calls == 1
    assert result.post_stop_capture_calls == 1
    assert result.native_evaluator_calls == 1
