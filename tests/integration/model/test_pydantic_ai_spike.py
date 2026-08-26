from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

pytest.importorskip("pydantic_ai")

from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.usage import RequestUsage

import affordance_runtime.model.policy.canonical_provider_envelope as canonical_envelope_module
import affordance_runtime.model.policy.pydantic_ai_bridge as pydantic_bridge
import affordance_runtime.model.policy.request_admission as request_admission_module
import affordance_runtime.model.policy.turn_packer as turn_packer_module
from affordance_runtime.actions import ActionSpace, ActionSpaceBuilder
from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.failures import ModelFailureKind, ProviderAttemptOrigin
from affordance_runtime.agent.context.observation_delivery import ObservationDeliveryStore
from affordance_runtime.agent.decisions import (
    FinalResponse,
    ReadRegionResult,
    SearchPageContentResult,
    SelectAction,
)
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    EvaluatedOutput,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.factory import model_policy_from_environment
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.provider_call_normalizer import (
    ToolCallReconciliationResult,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.pydantic_ai_bridge import (
    PydanticAIGroundedDecisionPort,
    zhipu_pydantic_ai_policy_from_environment,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBreakdown,
    ModelRequestCapacityError,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model.providers.port import StructuredOutputFailureKind
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.agent.core_loop_support import (
    SharedActionOutcomeProjector,
    SharedTaskEvaluator,
    shared_task,
    shared_world,
)
from tests.support.model.recording_pydantic_model import (
    RecordingPydanticModel,
    normalize_recorded_provider_input,
)

ScriptedModel = RecordingPydanticModel


def _progress_text(
    *,
    verified_facts: tuple[str, ...] = (),
    working_hypotheses: tuple[str, ...] = (),
    remaining_requirements: tuple[str, ...] = (),
    next_intent: str,
    avoid_repeating: tuple[str, ...] = (),
) -> str:
    return json.dumps(
        {
            "verified_facts": verified_facts,
            "working_hypotheses": working_hypotheses,
            "remaining_requirements": remaining_requirements,
            "next_intent": next_intent,
            "avoid_repeating": avoid_repeating,
        },
        sort_keys=True,
    )


def _policy(model) -> ModelBackedAgentPolicy:
    port = PydanticAIGroundedDecisionPort(
        model=model,
        provider_id="fixture",
        model_id="scripted",
        endpoint_host="fixture.invalid",
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
        transport_timeout_s=4.0,
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=5.0)


async def _bound_envelope_for_port(port: PydanticAIGroundedDecisionPort, request_id: str):
    task = shared_task()
    world = shared_world(request_id, False)
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        await SharedTaskEvaluator().evaluate(task, world),
    )
    profile = port.reasoning_policy.select(context, frozenset())
    return turn_packer_module.TurnPacker().pack(
        ModelDecisionRequest(f"request:{request_id}", context),
        binder=port.envelope_binder,
        identity=pydantic_bridge.CanonicalProviderIdentity(
            port.provider_id,
            port.model_id,
            port.endpoint_host,
            port.perception_profile.value,
        ),
        call_profile=profile,
        supports_multimodal=False,
        perception_profile=port.perception_profile,
    ).admitted_envelope.envelope


def _runtime(model) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(_policy(model)),
        SharedActionOutcomeProjector(),
        SharedTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
    )


def test_pydantic_ai_checkpoint_history_uses_official_message_adapter() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    history = (
        ModelRequest(parts=[UserPromptPart("current task")]),
        ModelResponse(
            parts=[ToolCallPart("activate", {"target": "E1"}, "call:checkpoint")]
        ),
        ModelRequest(
            parts=[ToolReturnPart("activate", {"status": "paused"}, "call:checkpoint")]
        ),
    )
    object.__setattr__(policy.port, "message_history", history)
    object.__setattr__(policy.port, "active_task_identity", ("task:checkpoint", 3))

    serialized = policy.export_checkpoint_history()

    assert serialized["format"] == "pydantic-ai.messages.v1"
    assert serialized["active_task_identity"] == ["task:checkpoint", 3]
    assert [message["kind"] for message in serialized["messages"]] == [
        "request",
        "response",
        "request",
    ]

    restored = _policy(ScriptedModel(["first_gui_action"]).build())
    restored.restore_checkpoint_history(
        serialized,
        task_id="task:checkpoint",
        task_revision=3,
    )
    assert restored.port.message_history == history
    assert restored.port.active_task_identity == ("task:checkpoint", 3)

    from affordance_runtime.immutable import freeze_json

    frozen = freeze_json(serialized)
    restored_from_checkpoint = _policy(ScriptedModel(["first_gui_action"]).build())
    restored_from_checkpoint.restore_checkpoint_history(
        frozen,
        task_id="task:checkpoint",
        task_revision=3,
    )
    assert restored_from_checkpoint.port.message_history == history


def test_pydantic_ai_checkpoint_history_uses_settled_step_persistence_reference(
    tmp_path,
) -> None:
    async def scenario() -> None:
        step_persistence = pytest.importorskip(
            "pydantic_ai_harness.step_persistence"
        )
        database = tmp_path / "model-steps.sqlite3"
        store = step_persistence.SqliteStepStore(database=database)
        policy = _policy(ScriptedModel(["first_gui_action"]).build())
        object.__setattr__(policy.port, "step_store", store)
        object.__setattr__(policy.port, "step_conversation_id", "session:checkpoint")
        history = (
            ModelRequest(parts=[UserPromptPart("current task")]),
            ModelResponse(
                parts=[ToolCallPart("activate", {"target": "E1"}, "call:settled")]
            ),
            ModelRequest(
                parts=[ToolReturnPart("activate", {"status": "paused"}, "call:settled")]
            ),
        )
        object.__setattr__(policy.port, "message_history", history)
        object.__setattr__(policy.port, "active_task_identity", ("task:checkpoint", 3))

        reference = await policy.persist_checkpoint_history()

        assert reference["format"] == "pydantic-ai.step-persistence.v1"
        assert reference["conversation_id"] == "session:checkpoint"
        assert "messages" not in reference
        snapshot = await store.latest_snapshot(run_id=reference["run_id"])
        assert snapshot is not None
        assert snapshot.state == "complete"
        assert snapshot.messages == list(history)

        restored = _policy(ScriptedModel(["first_gui_action"]).build())
        restarted_store = step_persistence.SqliteStepStore(database=database)
        object.__setattr__(restored.port, "step_store", restarted_store)
        object.__setattr__(
            restored.port,
            "step_conversation_id",
            "session:checkpoint",
        )
        await restored.restore_persisted_checkpoint_history(
            reference,
            task_id="task:checkpoint",
            task_revision=3,
        )
        assert restored.port.message_history == history

        tampered = {**reference, "message_digest": "f" * 64}
        with pytest.raises(ValueError, match="digest"):
            await restored.restore_persisted_checkpoint_history(
                tampered,
                task_id="task:checkpoint",
                task_revision=3,
            )

    asyncio.run(scenario())


def test_pydantic_ai_checkpoint_history_rejects_unclosed_tool_call() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    object.__setattr__(
        policy.port,
        "message_history",
        (
            ModelResponse(
                parts=[ToolCallPart("activate", {"target": "E1"}, "call:checkpoint")]
            ),
        ),
    )

    with pytest.raises(ValueError, match="unclosed tool call"):
        policy.export_checkpoint_history()


def test_pydantic_ai_checkpoint_history_rebinds_only_one_closed_revision() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    history = (
        ModelRequest(parts=[UserPromptPart("current task")]),
        ModelResponse(
            parts=[ToolCallPart("activate", {"target": "E1"}, "call:revision")]
        ),
        ModelRequest(
            parts=[ToolReturnPart("activate", {"status": "paused"}, "call:revision")]
        ),
    )
    object.__setattr__(policy.port, "message_history", history)
    object.__setattr__(policy.port, "active_task_identity", ("task:checkpoint", 3))

    policy.rebind_checkpoint_history(
        task_id="task:checkpoint",
        current_revision=3,
        revised_revision=4,
    )

    assert policy.port.message_history == history
    assert policy.export_checkpoint_history()["active_task_identity"] == [
        "task:checkpoint",
        4,
    ]
    with pytest.raises(ValueError, match="consecutive"):
        policy.rebind_checkpoint_history(
            task_id="task:checkpoint",
            current_revision=4,
            revised_revision=6,
        )


def test_pydantic_ai_decision_executes_one_action_then_runtime_auto_completes() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert state.execution_count == 1
        assert scripted.calls == 1
        # FunctionModel strips unsupported thinking while preserving the
        # transport-level single-call prohibition and output/sampling budget.
        assert scripted.model_settings == [
            {
                "max_tokens": 1024,
                "temperature": 0.0,
                "parallel_tool_calls": False,
                "timeout": 4.0,
            }
        ]
        assert dict(policy.port.last_admitted_envelopes[0].model_settings) == {
            "max_tokens": 1024,
            "temperature": 0.0,
            "parallel_tool_calls": False,
            "timeout": 4.0,
        }
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "recording-call:1"
        assert "ask_user" in scripted.offered_tools[0]
        assert "propose_done" not in scripted.offered_tools[0]
        attempt = policy.port.last_generation_attempts[0]
        assert attempt.phase == "ordinary"
        assert attempt.role == "action_policy"
        assert attempt.trigger == "ordinary"
        assert attempt.thinking_requested == "disabled"
        assert attempt.thinking_effective == "disabled"
        assert attempt.max_output_tokens == 1024
        assert attempt.final_tool_call_present is True
        assert attempt.final_content_tokens == attempt.completion_tokens
        assert attempt.transcript["llm.input_messages"][0]["parts"][0]["content"]
        assert attempt.transcript["llm.output_messages"][0]["parts"][0]["tool_name"]
        assert policy.last_metadata is not None
        assert policy.last_metadata.latency_ms >= attempt.latency_ms > 0

    asyncio.run(scenario())


def test_pydantic_ai_step_persistence_records_each_action_policy_run() -> None:
    async def scenario() -> None:
        step_persistence = pytest.importorskip(
            "pydantic_ai_harness.step_persistence"
        )
        store = step_persistence.InMemoryStepStore()
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        object.__setattr__(policy.port, "step_store", store)
        object.__setattr__(policy.port, "step_conversation_id", "session:steps")
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("step_persistence_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        runs = await store.list_runs(conversation_id="session:steps")
        assert len(runs) == 1
        assert runs[0].agent_name == "action-policy"
        events = await store.list_events(run_id=runs[0].run_id)
        assert [event.kind for event in events] == [
            "run_started",
            "model_request_started",
            "model_request_completed",
            "run_completed",
        ]
        assert policy.port.last_step_run_id == runs[0].run_id

    asyncio.run(scenario())


def test_pydantic_ai_action_policy_emits_native_open_telemetry_spans() -> None:
    async def scenario() -> None:
        trace_module = pytest.importorskip("opentelemetry.sdk.trace")
        export_module = pytest.importorskip("opentelemetry.sdk.trace.export")
        in_memory_module = pytest.importorskip(
            "opentelemetry.sdk.trace.export.in_memory_span_exporter"
        )
        exporter = in_memory_module.InMemorySpanExporter()
        tracer_provider = trace_module.TracerProvider()
        tracer_provider.add_span_processor(export_module.SimpleSpanProcessor(exporter))
        policy = _policy(ScriptedModel(["first_gui_action"]).build())
        object.__setattr__(policy.port, "tracer_provider", tracer_provider)
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("otel_test"),
        ).run_task(environment, shared_task())

        spans = exporter.get_finished_spans()
        assert {span.name for span in spans} == {
            "chat recording-scripted",
            "invoke_agent action-policy",
        }
        chat_span = next(span for span in spans if span.name == "chat recording-scripted")
        assert chat_span.attributes["gen_ai.agent.name"] == "action-policy"
        assert chat_span.attributes["gen_ai.operation.name"] == "chat"
        assert chat_span.attributes["gen_ai.usage.input_tokens"] > 0

    asyncio.run(scenario())


def test_multiple_provider_tool_calls_execute_first_and_preserve_every_proposal() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["multiple_gui_actions"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("multiple-calls", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:multiple-calls", context))

        assert result.failure is None
        assert result.output is not None
        decision = result.output.decision
        assert isinstance(decision, SelectAction)
        assert decision.tool_call_id == "recording-call:1"
        assert scripted.calls == 1
        assert [attempt.phase for attempt in result.attempts] == ["ordinary"]
        assert result.diagnostics["multiple_tool_call_attempt_count"] == 1
        assert result.diagnostics["discarded_protocol_call_count"] == 1
        assert len(policy.port.last_admitted_envelopes) == 1
        assert isinstance(policy.port.message_history[0], ModelRequest)
        assert any(
            isinstance(part, UserPromptPart)
            for part in policy.port.message_history[0].parts
        )
        retained = policy.port.message_history[1]
        assert isinstance(retained, ModelResponse)
        assert [part.tool_call_id for part in retained.parts if isinstance(part, ToolCallPart)] == [
            "recording-call:1",
            "recording-call:1:second",
        ]

    asyncio.run(scenario())


def test_text_only_output_uses_one_pydantic_retry_and_retains_only_the_accepted_exchange() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["zero_calls", "first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("text-only-output-retry", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(
            ModelDecisionRequest("request:text-only-output-retry", context)
        )

        assert result.failure is None and result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "ordinary_output_retry",
        ]
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert result.attempts[0].output_failure_kind is StructuredOutputFailureKind.NO_TOOL_CALL
        assert result.attempts[1].output_failure_kind is None
        assert result.diagnostics["policy_model_call_count"] == 2
        canonical_history = json.dumps(policy.port.message_history, default=str)
        assert "no tool call" not in canonical_history
        assert "Return one offered tool call" not in canonical_history
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_text_only_output_retry_exhaustion_is_typed_no_tool_call() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["zero_calls", "zero_calls"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("text-only-output-exhausted", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(
            ModelDecisionRequest("request:text-only-output-exhausted", context)
        )

        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INVALID_RESPONSE
        assert result.failure.reason == "no_tool_call"
        assert scripted.calls == 2
        assert [attempt.status for attempt in result.attempts] == ["invalid", "failed"]
        assert all(
            attempt.output_failure_kind is StructuredOutputFailureKind.NO_TOOL_CALL
            for attempt in result.attempts
        )
        assert result.diagnostics["policy_model_call_count"] == 2
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_text_only_length_exhaustion_is_typed_output_budget_failure() -> None:
    async def scenario() -> None:
        truncated = ModelResponse(
            parts=[TextPart("unfinished policy reasoning")],
            usage=RequestUsage(input_tokens=10, output_tokens=1024),
            finish_reason="length",
            provider_response_id="recording-truncated",
        )
        scripted = ScriptedModel([truncated, truncated])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("text-output-budget-exhausted", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(
            ModelDecisionRequest("request:text-output-budget-exhausted", context)
        )

        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INVALID_RESPONSE
        assert result.failure.reason == "output_budget_exhausted"
        assert scripted.calls == 2
        assert all(
            attempt.output_failure_kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED
            for attempt in result.attempts
        )

    asyncio.run(scenario())


def test_wholly_unparseable_tool_call_fails_without_representation_repair() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["malformed_tool_call"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("malformed-tool-call", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(
            ModelDecisionRequest("request:malformed-tool-call", context)
        )

        assert result.failure is not None
        assert scripted.calls == 1
        assert len(result.attempts) == 1
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_semantically_distinct_extra_call_is_not_a_fallback_but_remains_visible() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["multiple_distinct_gui_actions"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("multiple-call-reselection", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:multiple-reselection", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert result.output.decision.tool_call_id == "recording-call:1"
        assert scripted.calls == 1
        assert [attempt.phase for attempt in result.attempts] == ["ordinary"]
        assert result.diagnostics["multiple_tool_call_attempt_count"] == 1
        assert result.diagnostics["discarded_protocol_call_count"] == 1
        physical_history = json.dumps(policy.port.message_history, default=str)
        assert "recording-call:1:discarded" in physical_history

    asyncio.run(scenario())


def test_unexecuted_second_proposal_can_be_reissued_after_the_fresh_world() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("multiple-call-reissue", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        scripted = ScriptedModel(
            [
                [
                    ("list_regions", {}),
                    ("search_page_content", {"query": "scope"}),
                ],
                ("search_page_content", {"query": "scope"}),
            ]
        )
        policy = _policy(scripted.build())
        context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(
            ModelDecisionRequest("request:multiple-reissue:first", context)
        )

        assert first.failure is None and first.output is not None
        assert first.output.decision.tool_name == "list_regions"
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        fresh_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:multiple-reissue:second",
                fresh_context,
                last_step=step,
            )
        )

        assert second.failure is None and second.output is not None, json.dumps(
            second.diagnostics, default=str
        )
        assert second.output.decision.tool_name == "search_page_content"
        assert second.output.decision.arguments == {"query": "scope"}
        recorded = normalize_recorded_provider_input(scripted.records[1])
        proposal_ids = tuple(
            part["tool_call_id"]
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        )
        returns = tuple(
            part
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        )
        assert proposal_ids == (
            "recording-call:1",
            "recording-call:1:discarded:1",
        )
        assert tuple(item["tool_call_id"] for item in returns) == proposal_ids
        assert returns[1]["content"].startswith("Not executed:")

    asyncio.run(scenario())


def test_first_call_serialization_preserves_the_current_pending_tool_return_pair() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("multiple-call-with-pending-result", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                [
                    ("search_page_content", {"query": "scope"}),
                    ("list_regions", {}),
                ],
                (
                    "submit_final_response",
                    {"content": "Canonical pairs preserved.", "evidence_refs": []},
                ),
            ]
        )
        policy = _policy(scripted.build())
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(
            ModelDecisionRequest("request:pending-pair:first", first_context)
        )
        assert first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:pending-pair:second",
                second_context,
                last_step=first_step,
            )
        )

        assert second.failure is None and second.output is not None, json.dumps(
            second.diagnostics, default=str
        )
        assert second.output.decision.tool_call_id == "recording-call:2"
        assert [attempt.phase for attempt in second.attempts] == ["ordinary"]
        assert second.diagnostics["multiple_tool_call_attempt_count"] == 1
        assert second.diagnostics["discarded_protocol_call_count"] == 1
        assert len(policy.port.last_admitted_envelopes) == 1
        assert len(policy.port.message_history) == 4
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) == ToolCall(
            "search_page_content",
            {"query": "scope"},
            "recording-call:2",
        )

        second_step = StepResult(
            second.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        third_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=second_step,
        )
        final = await policy.port.generate(
            ModelDecisionRequest(
                "request:pending-pair:final",
                third_context,
                last_step=second_step,
            )
        )

        assert final.failure is None and final.output is not None
        assert isinstance(final.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[2])
        calls = [
            part
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        ]
        returns = [
            part
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        ]
        assert [(item["tool_name"], item["tool_call_id"]) for item in calls] == [
            ("list_regions", "recording-call:1"),
            ("search_page_content", "recording-call:2"),
            ("list_regions", "recording-call:2:discarded:1"),
        ]
        assert [(item["tool_name"], item["tool_call_id"]) for item in returns] == [
            ("list_regions", "recording-call:1"),
            ("search_page_content", "recording-call:2"),
            ("list_regions", "recording-call:2:discarded:1"),
        ]

    asyncio.run(scenario())


@given(call_count=st.integers(min_value=1, max_value=8))
@settings(max_examples=8, deadline=None)
def test_accepted_exchange_conserves_every_proposal_across_the_next_provider_turn(
    call_count: int,
) -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world(f"accepted-exchange-{call_count}", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        raw_calls = [
            ("list_regions", {}),
            *(
                ("search_page_content", {"query": f"discarded-{index}"})
                for index in range(1, call_count)
            ),
        ]
        scripts: list[object] = [raw_calls]
        scripts.append(
            (
                "submit_final_response",
                {"content": "Canonical exchange received.", "evidence_refs": []},
            )
        )
        scripted = ScriptedModel(scripts)
        policy = _policy(scripted.build())

        first = await policy.port.generate(
            ModelDecisionRequest("request:accepted-exchange:first", first_context)
        )

        assert first.failure is None and first.output is not None
        assert first.output.decision.tool_name == "list_regions"
        accepted_call_id = "recording-call:1"
        assert first.output.decision.tool_call_id == accepted_call_id
        history = policy.port.message_history
        assert len(history) == 2
        assert pydantic_bridge._pending_call_from_history(history) == ToolCall(
            "list_regions", {}, accepted_call_id
        )
        raw_response_parts = first.attempts[0].transcript["llm.output_messages"][0]["parts"]
        assert len(
            [part for part in raw_response_parts if part["part_kind"] == "tool-call"]
        ) == call_count

        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        assert step.decision is first.output.decision
        assert step.decision.tool_call_id == accepted_call_id
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:accepted-exchange:second",
                second_context,
                last_step=step,
            )
        )

        assert second.failure is None and second.output is not None, json.dumps(
            second.diagnostics, default=str
        )
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        assert recorded == policy.port.last_admitted_envelopes[0].model_boundary_projection()
        prior_calls = tuple(
            part
            for part in recorded["messages"][-2]["parts"]
            if part["part_kind"] == "tool-call"
        )
        paired_results = tuple(
            part
            for part in recorded["messages"][-1]["parts"]
            if part["part_kind"] == "tool-return"
        )
        assert prior_calls[0] == {
            "part_kind": "tool-call",
            "tool_name": "list_regions",
            "arguments": {},
            "tool_call_id": accepted_call_id,
        }
        assert len(prior_calls) == call_count
        assert len(paired_results) == call_count
        assert tuple(
            (item["tool_name"], item["tool_call_id"]) for item in paired_results
        ) == tuple((item["tool_name"], item["tool_call_id"]) for item in prior_calls)
        physical = json.dumps(recorded, sort_keys=True)
        if call_count > 1:
            assert all(
                f"discarded-{index}" in physical for index in range(1, call_count)
            )
            assert all(
                f"recording-call:1:discarded:{index}" in physical
                for index in range(1, call_count)
            )
            assert all(
                "Not executed" in item["content"] for item in paired_results[1:]
            )
        assert scripted.calls == 2

    asyncio.run(scenario())


def test_control_boundary_closes_pending_pydantic_history_before_another_model_turn() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("control-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        scripted = ScriptedModel(
            [
                "first_gui_action",
                (
                    "submit_final_response",
                    {"content": "Closed control boundary observed.", "evidence_refs": []},
                ),
            ]
        )
        policy = _policy(scripted.build())
        context = builder.build(task, world, actions, evaluation)
        first = await policy.port.generate(ModelDecisionRequest("request:control:first", context))
        assert first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="action_not_dispatched:control_pause_boundary_reached",
        )

        policy.close_deferred_call(step)

        assert len(policy.port.message_history) == 3
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) is None
        closed_request = policy.port.message_history[-1]
        assert isinstance(closed_request, ModelRequest)
        returned = tuple(part for part in closed_request.parts if isinstance(part, ToolReturnPart))
        assert len(returned) == 1
        assert returned[0].tool_call_id == first.output.decision.tool_call_id
        assert returned[0].content["completion"] == "not_dispatched"

        next_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:control:second", next_context, last_step=step)
        )

        assert second.failure is None and second.output is not None, json.dumps(
            second.diagnostics, default=str
        )
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        paired = tuple(
            part
            for message in recorded["messages"]
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        )
        assert len(paired) == 1
        assert paired[0]["content"]["completion"] == "not_dispatched"
        assert policy.port.message_history == ()

    asyncio.run(scenario())


def test_exact_model_reasoning_and_calls_survive_into_the_next_turn() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("progress-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        progress = _progress_text(
            verified_facts=("Verified names: Dibbins and Anglebert Dinkherhump",),
            next_intent="Submit the supported final answer",
        )
        discarded_id = "recording-call:progress:discarded"
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ThinkingPart("private deliberation " * 400),
                        TextPart(progress),
                        ToolCallPart("list_regions", {}, "recording-call:progress"),
                        ToolCallPart(
                            "search_page_content",
                            {"query": "unneeded recheck"},
                            discarded_id,
                        ),
                    ],
                    provider_response_id="recording-response:progress",
                ),
                (
                    "submit_final_response",
                    {"content": "Dibbins; Anglebert Dinkherhump", "evidence_refs": []},
                ),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(
            ModelDecisionRequest("request:progress:first", first_context)
        )

        assert first.failure is None and first.output is not None
        assert first.output.decision.tool_call_id == "recording-call:progress"
        retained = policy.port.message_history[1]
        assert isinstance(retained, ModelResponse)
        assert [type(part) for part in retained.parts] == [
            ThinkingPart,
            TextPart,
            ToolCallPart,
            ToolCallPart,
        ]
        assert retained.parts[1].content == progress
        raw_parts = first.attempts[0].transcript["llm.output_messages"][0]["parts"]
        assert any(
            part["part_kind"] == "thinking" and "private deliberation" in part["content"]
            for part in raw_parts
        )

        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:progress:second", second_context, last_step=step)
        )

        assert second.failure is None and second.output is not None, json.dumps(
            second.diagnostics, default=str
        )
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        prior_response = next(
            message for message in recorded["messages"] if message["kind"] == "response"
        )
        assert prior_response["parts"] == (
            {
                "part_kind": "thinking",
                "content": retained.parts[0].content,
            },
            {
                "part_kind": "text",
                "content": retained.parts[1].content,
            },
            {
                "part_kind": "tool-call",
                "tool_name": "list_regions",
                "arguments": {},
                "tool_call_id": "recording-call:progress",
            },
            {
                "part_kind": "tool-call",
                "tool_name": "search_page_content",
                "arguments": {"query": "unneeded recheck"},
                "tool_call_id": discarded_id,
            },
        )
        physical = json.dumps(recorded, sort_keys=True)
        assert "private deliberation" in physical
        assert discarded_id in physical
        assert "Not executed" in physical
        assert "Do not emit a separate memory" in str(scripted.records[0].instructions)
        assert "Return exactly one offered tool call" in str(scripted.records[0].instructions)

    asyncio.run(scenario())


def test_action_narration_and_fresh_world_prompts_remain_in_official_history() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("progress-carry-forward", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        progress = _progress_text(
            verified_facts=("Portland coordinates: 43.6600,-70.2550",),
            remaining_requirements=("Acadia coordinates", "OSRM distance"),
            next_intent="Resolve the Acadia location and route distance",
        )
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        TextPart(progress),
                        ToolCallPart("list_regions", {}, "call:progress:first"),
                    ]
                ),
                ModelResponse(
                    parts=[
                        ThinkingPart("hidden tool-only deliberation"),
                        TextPart("I will switch back to the Portland tab now."),
                        ToolCallPart(
                            "search_page_content",
                            {"query": "coordinates"},
                            "call:progress:second",
                        ),
                    ]
                ),
            ]
        )
        policy = _policy(scripted.build())
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(
            ModelDecisionRequest("request:progress-carry:first", first_context)
        )
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:progress-carry:second",
                second_context,
                last_step=first_step,
            )
        )

        assert second.failure is None and second.output is not None
        history = policy.port.message_history
        assert len(history) == 4
        assert isinstance(history[0], ModelRequest)
        assert isinstance(history[1], ModelResponse)
        assert [part.content for part in history[1].parts if isinstance(part, TextPart)] == [
            progress
        ]
        assert isinstance(history[2], ModelRequest)
        assert sum(
            isinstance(part, UserPromptPart)
            for message in history
            if isinstance(message, ModelRequest)
            for part in message.parts
        ) == 2
        assert isinstance(history[-1], ModelResponse)
        assert [part.content for part in history[-1].parts if isinstance(part, TextPart)] == [
            "I will switch back to the Portland tab now."
        ]
        assert sum(
            isinstance(part, TextPart)
            for message in history
            if isinstance(message, ModelResponse)
            for part in message.parts
        ) == 2
        assert "hidden tool-only deliberation" in json.dumps(history, default=str)
        assert "switch back to the Portland tab" in json.dumps(history, default=str)
        assert "switch back to the Portland tab" in json.dumps(
            second.attempts[0].transcript["llm.output_messages"],
            default=str,
        )

    asyncio.run(scenario())


def test_recording_model_can_consume_search_region_in_the_next_turn() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("search-follow-up-recording", False)
        action_space = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, action_space, evaluation)
        region = first_context.region_index.region_for_target("shared-toggle")
        assert region is not None
        region_ref = first_context.canonical_world.region_refs[region.key]
        scripted = ScriptedModel(
            [
                ("search_page_content", {"query": "false"}),
                ("read_region", {"region_ref": region_ref}),
                (
                    "submit_final_response",
                    {"content": "Observed the complete current result.", "evidence_refs": []},
                ),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:search", first_context))
        assert first.failure is None
        assert first.output is not None
        assert isinstance(first.output.decision, SearchPageContentResult)
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            action_space,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:read", second_context, last_step=step)
        )

        assert second.failure is None
        assert second.output is not None
        assert isinstance(second.output.decision, ReadRegionResult)
        assert second.output.decision.arguments == {"region_ref": region_ref}
        assert second.output.decision.result["kind"] == "Opened"
        second_step = StepResult(
            second.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        third_context = builder.build(
            task,
            world,
            action_space,
            evaluation,
            last_step=second_step,
        )
        third = await policy.port.generate(
            ModelDecisionRequest("request:answer", third_context, last_step=second_step)
        )

        assert third.failure is None
        assert third.output is not None
        assert isinstance(third.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[2])
        history_parts = tuple(
            part
            for message in recorded["messages"]
            for part in message["parts"]
            if part["part_kind"] in {"tool-call", "tool-return"}
        )
        assert tuple(part["part_kind"] for part in history_parts) == (
            "tool-call",
            "tool-return",
            "tool-call",
            "tool-return",
        )
        assert tuple(part["tool_call_id"] for part in history_parts) == (
            "recording-call:1",
            "recording-call:1",
            "recording-call:2",
            "recording-call:2",
        )
        assert history_parts[1]["content"] == first.output.decision.result
        assert history_parts[3]["content"] == second.output.decision.result
        assert sum(
            part["part_kind"] == "user-prompt"
            for message in recorded["messages"]
            for part in message["parts"]
        ) == 3
        current_prompt_part = next(
            part
            for part in recorded["messages"][-1]["parts"]
            if part["part_kind"] == "user-prompt"
        )
        user_text = current_prompt_part["content"][0]["content"]
        payload = json.loads(user_text)
        assert "latest_public_results" not in payload
        assert scripted.calls == 3
        assert policy.port.message_history == ()

    asyncio.run(scenario())


def _official_history_with_pending_actions(turns: int) -> tuple[object, ...]:
    messages: list[object] = [
        ModelRequest(parts=[UserPromptPart("World 0: Portland task not started")]),
    ]
    for index in range(turns):
        messages.append(
            ModelResponse(
                parts=[
                    ThinkingPart(f"step {index}: inspect the fresh World"),
                    TextPart(f"conclusion {index}: continue toward Acadia"),
                    ToolCallPart("activate", {"target": f"E{index}"}, f"call:{index}"),
                ]
            )
        )
        if index + 1 < turns:
            messages.append(
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            "activate",
                            {"status": "stable", "page": index + 1},
                            f"call:{index}",
                        ),
                        UserPromptPart(
                            f"World {index + 1}: fresh observation after action {index}"
                        ),
                    ]
                )
            )
    return tuple(messages)


def test_harness_summarizes_only_a_pressured_expired_trajectory_prefix() -> None:
    history = _official_history_with_pending_actions(7)
    scripted = ScriptedModel(
        [ModelResponse(parts=[TextPart("Verified Portland facts; next open Acadia.")])]
    )
    model = scripted.build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.attempted is True
    assert run.error == ""
    assert len(scripted.records) == 1
    assert isinstance(run.messages[0], ModelRequest)
    assert isinstance(run.messages[0].parts[0], SystemPromptPart)
    assert "Verified Portland facts" in run.messages[0].parts[0].content
    preserved_count = len(run.messages) - 1
    assert 0 < preserved_count < len(history)
    assert run.messages[1:] == history[-preserved_count:]
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall(
        "activate", {"target": "E6"}, "call:6"
    )
    summary_input = normalize_recorded_provider_input(scripted.records[0])
    serialized_input = json.dumps(summary_input, sort_keys=True)
    assert "World 0" in serialized_input
    assert "stable" in serialized_input
    assert "inspect the fresh World" in serialized_input
    assert "continue toward Acadia" in serialized_input
    canonical_envelope_module._project_pydantic_history(run.messages)


def test_harness_summary_contract_keeps_conclusions_without_action_narration() -> None:
    prompt = pydantic_bridge._HISTORY_COMPACTION_SUMMARY_PROMPT

    assert "## Task progress" in prompt
    assert "At most three completed user-requirement outcomes" in prompt
    assert "## Verified facts" in prompt
    assert "At most eight exact facts" in prompt
    assert "## Remaining questions" in prompt
    assert "## Next intent" in prompt
    assert "Exactly one semantic next intent" in prompt
    assert "## Failed strategies" in prompt
    assert "At most two terse strategy-level failures" in prompt
    assert "## Action outcomes" not in prompt
    assert "Never enumerate attempted URLs" in prompt
    assert pydantic_bridge._HISTORY_COMPACTION_KEEP_TOKENS_RATIO == 0.12
    assert pydantic_bridge._HISTORY_COMPACTION_MAX_OUTPUT_TOKENS == 1024


def test_harness_summary_sees_complete_bounded_tool_result_past_upstream_clip() -> None:
    coordinate = "43°39′36″N 70°15′18″W"
    long_result = {
        "kind": "Opened",
        "source_coverage": "partial",
        "has_more": True,
        "items": [
            {"kind": "complete_item", "text": "prefix-" + "x" * 700},
            {"kind": "complete_item", "text": f"Coordinates: {coordinate}"},
        ],
    }
    history = (
        ModelRequest(parts=[UserPromptPart("Find Portland's official coordinates")]),
        ModelResponse(
            parts=[
                ToolCallPart("read_region", {"region_ref": "R264"}, "call:read"),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart("read_region", long_result, "call:read"),
                UserPromptPart("Fresh World after the completed local read"),
            ]
        ),
        ModelResponse(
            parts=[
                ThinkingPart(f"The completed coordinate row confirms {coordinate}."),
                TextPart(f"Portland's official coordinates are {coordinate}."),
                ToolCallPart("wait", {"reason": "fixture"}, "call:pending"),
            ]
        ),
    )
    scripted = ScriptedModel(
        [ModelResponse(parts=[TextPart(f"Verified Portland coordinates: {coordinate}.")])]
    )

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=scripted.build(),
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.error == ""
    summary_input = json.dumps(
        normalize_recorded_provider_input(scripted.records[0]),
        ensure_ascii=False,
        sort_keys=True,
    )
    assert coordinate in summary_input
    assert "Completed tool result [read_region] call_id=call:read" in summary_input
    assert "Coverage or pagination metadata limits the result's scope" in summary_input
    assert run.messages[1:] == history[-(len(run.messages) - 1) :]
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall(
        "wait", {"reason": "fixture"}, "call:pending"
    )


def test_harness_does_not_call_a_model_below_real_history_pressure() -> None:
    history = _official_history_with_pending_actions(3)
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("must not be used")])])
    model = scripted.build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=100_000,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is False
    assert run.error == ""
    assert scripted.records == []


def test_history_pressure_excludes_current_prompt_tools_and_provider_usage_anchor() -> None:
    history = _official_history_with_pending_actions(2)
    history = (
        *history[:-1],
        replace(history[-1], usage=RequestUsage(input_tokens=50_000, output_tokens=1_000)),
    )
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("must not be used")])])

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=scripted.build(),
            max_estimated_tokens=8_000,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is False
    assert scripted.records == []


def test_history_compaction_pressure_uses_complete_request_admission_accounting() -> None:
    below_pressure = ModelRequestBreakdown(
        "ordinary",
        history_tokens=35_000,
        estimated_input_tokens=49_000,
        effective_input_limit=62_904,
    )
    over_capacity = ModelRequestBreakdown(
        "ordinary",
        history_tokens=53_712,
        estimated_input_tokens=67_022,
        effective_input_limit=62_904,
        admission_action="context_capacity",
    )

    assert not pydantic_bridge._history_compaction_required(
        below_pressure,
        has_history=True,
    )
    assert pydantic_bridge._history_compaction_required(
        over_capacity,
        has_history=True,
    )
    assert pydantic_bridge._available_history_tokens(over_capacity) == 49_594


def test_action_envelope_recomputes_timeout_after_actual_compaction_elapsed(monkeypatch) -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("dynamic-deadline", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                (
                    "submit_final_response",
                    {"content": "Deadline propagated.", "evidence_refs": []},
                ),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="fixture",
            model_id="scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=42.25,
            policy_timeout_s=90.0,
            max_provider_retry_delay_s=5.0,
            history_compaction_timeout_s=42.25,
        )

        first = await port.generate(ModelDecisionRequest("request:deadline-first", first_context))
        assert first.failure is None and first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )

        async def preserve_history(messages, **_kwargs):
            return pydantic_bridge._HistoryCompactionRun(messages)

        timeouts = iter((42.25, 30.75))
        observed: list[float] = []

        def remaining_timeout(**_kwargs):
            timeout = next(timeouts)
            observed.append(timeout)
            return timeout

        monkeypatch.setattr(pydantic_bridge, "_history_compaction_required", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(pydantic_bridge, "_compact_pydantic_history", preserve_history)
        monkeypatch.setattr(pydantic_bridge, "_remaining_action_attempt_timeout", remaining_timeout)

        second = await port.generate(
            ModelDecisionRequest("request:deadline-second", second_context, last_step=step)
        )

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, FinalResponse)
        assert observed == [42.25, 30.75]
        assert scripted.model_settings[-1]["timeout"] == 30.75
        assert dict(port.last_admitted_envelopes[-1].model_settings)["timeout"] == 30.75

    asyncio.run(scenario())


def test_harness_summary_failure_keeps_the_exact_raw_history() -> None:
    history = _official_history_with_pending_actions(7)
    scripted = ScriptedModel([RuntimeError("summary provider unavailable")])
    model = scripted.build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is True
    assert "summary provider unavailable" in run.error
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall(
        "activate", {"target": "E6"}, "call:6"
    )


@given(turns=st.integers(min_value=5, max_value=12))
@settings(max_examples=12)
def test_harness_compaction_keeps_an_exact_pair_safe_suffix_and_pending_call(
    turns: int,
) -> None:
    history = _official_history_with_pending_actions(turns)
    model = ScriptedModel(
        [ModelResponse(parts=[TextPart(f"summary for {turns} turns")])]
    ).build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.error == ""
    preserved_count = len(run.messages) - 1
    assert 0 < preserved_count < len(history)
    assert run.messages[1:] == history[-preserved_count:]
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall(
        "activate",
        {"target": f"E{turns - 1}"},
        f"call:{turns - 1}",
    )
    canonical_envelope_module._project_pydantic_history(run.messages)


def test_recording_model_receives_same_tool_cursor_page_as_direct_same_call_result() -> None:
    async def scenario() -> None:
        source_id = "source:long-reviews"
        targets = tuple(
            SemanticTarget(
                f"review:{index}",
                "listitem",
                f"Reviewer {index}: " + "深🙂" * 500,
            )
            for index in range(25)
        )
        fused = WorldFusion().fuse(
            (
                SurfaceObservation(
                    source_id,
                    "dom",
                    "revision:long-reviews",
                    ObservationSourceProfile.dom(),
                    targets,
                    (),
                ),
            )
        )
        assert fused.observation is not None
        world = fused.observation
        task = TaskGoal("read-long-reviews", "Inspect every review")
        evaluation = TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "more review pages remain",
        )
        builder = ContextBuilder()
        first_context = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            evaluation,
        )
        assert first_context.region_index.regions
        region = first_context.region_index.regions[0]
        region_ref = first_context.canonical_world.region_refs[region.key]
        scripted = ScriptedModel([("read_region", {"region_ref": region_ref})])
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:long-page-1", first_context))

        assert first.failure is None and first.output is not None
        assert isinstance(first.output.decision, ReadRegionResult)
        cursor = str(first.output.decision.result["next_cursor"])
        assert cursor
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        first_transition = ObservationDeliveryStore().reduce(first_step, step_index=1)
        assert not hasattr(first_transition.next_store, "public_result_inventory")
        scripted.decisions.extend(
            [
                ("read_region", {"region_ref": region_ref, "cursor": cursor}),
                (
                    "submit_final_response",
                    {"content": "Review pages inspected.", "evidence_refs": []},
                ),
            ]
        )
        second_context = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            evaluation,
            last_step=first_step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:long-page-2", second_context, last_step=first_step)
        )

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, ReadRegionResult)
        assert second.output.decision.arguments == {"region_ref": region_ref, "cursor": cursor}
        assert second.output.decision.result["items"]
        assert second.output.decision.result["items"] != first.output.decision.result["items"]
        second_step = StepResult(
            second.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_transition = first_transition.next_store.reduce(second_step, step_index=2)
        assert len(second_transition.next_store.local_deliveries) == 2
        assert all(not hasattr(item, "records") for item in second_transition.next_store.local_deliveries)
        third_context = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            evaluation,
            last_step=second_step,
        )
        third = await policy.port.generate(
            ModelDecisionRequest("request:long-finish", third_context, last_step=second_step)
        )

        assert third.failure is None and third.output is not None
        assert isinstance(third.output.decision, FinalResponse)
        assert policy.port.last_history_compaction_status == "not_triggered"
        recorded = normalize_recorded_provider_input(scripted.records[2])
        call = recorded["messages"][-2]["parts"][0]
        returned = recorded["messages"][-1]["parts"][0]
        assert call["part_kind"] == "tool-call"
        assert returned["part_kind"] == "tool-return"
        assert returned["tool_call_id"] == call["tool_call_id"]
        assert tuple(returned["content"]["items"]) == tuple(second.output.decision.result["items"])
        assert scripted.calls == 3

    asyncio.run(scenario())


def test_list_regions_returns_standard_call_correlated_tool_result() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("list-regions-tool-return", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                (
                    "submit_final_response",
                    {"content": "Region inventory received.", "evidence_refs": []},
                ),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:list-regions", first_context))
        assert first.failure is None and first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:list-regions-answer", second_context, last_step=step)
        )

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        call_part = recorded["messages"][-2]["parts"][0]
        return_part = recorded["messages"][-1]["parts"][0]
        assert call_part["tool_name"] == "list_regions"
        assert return_part["tool_call_id"] == call_part["tool_call_id"]
        assert return_part["content"]["kind"] == "Page"
        current_prompt = recorded["messages"][-1]["parts"][1]["content"][0]["content"]
        assert "latest_public_results" not in json.loads(current_prompt)
        physical = json.dumps(policy.port.envelope_history[1].physical_content(), default=str)
        assert "result_lineage" not in physical
        assert "record_digests" not in physical
        assert "origin_context_id" not in physical

    asyncio.run(scenario())


def test_unexpected_value_error_is_internal_not_invalid_tool_arguments() -> None:
    async def scenario() -> None:
        policy = _policy(ScriptedModel([ValueError("unexpected local invariant")]).build())
        task = shared_task()
        world = shared_world("unexpected-value-error", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:unexpected-value-error", context))

        assert result.output is None
        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INTERNAL_ERROR

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "fault_stage",
    (
        "delivery",
        "catalog",
        "envelope_bind",
        "schema_bind",
        "token_count",
        "admission",
        "provider_bind",
        "trace_record",
    ),
)
def test_pre_provider_ordinary_faults_are_total_and_never_attempt_provider(monkeypatch, fault_stage) -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world(f"pre-provider-{fault_stage}", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        def fail(*_args, **_kwargs):
            raise RuntimeError(f"synthetic {fault_stage} fault")

        if fault_stage == "delivery":
            monkeypatch.setattr(turn_packer_module, "build_model_turn_delivery", fail)
        elif fault_stage == "catalog":
            monkeypatch.setattr(turn_packer_module, "compile_grounded_action_catalog", fail)
        elif fault_stage == "envelope_bind":
            monkeypatch.setattr(canonical_envelope_module.CanonicalProviderEnvelopeBinder, "bind", fail)
        elif fault_stage == "schema_bind":
            monkeypatch.setattr(canonical_envelope_module, "CanonicalFunctionTool", fail)
        elif fault_stage == "token_count":
            monkeypatch.setattr(request_admission_module, "estimate_canonical_envelope", fail)
        elif fault_stage == "admission":
            monkeypatch.setattr(pydantic_bridge.RequestAdmission, "admit", fail)
        elif fault_stage == "provider_bind":
            monkeypatch.setattr(pydantic_bridge, "_pydantic_model_boundary_codec", fail)
        else:
            monkeypatch.setattr(pydantic_bridge.PydanticAIGroundedDecisionPort, "_record_attempt_started", fail)

        result = await policy.port.generate(ModelDecisionRequest(f"request:{fault_stage}", context))

        assert result.output is None
        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INTERNAL_ERROR
        assert result.failure.attempt_origin is ProviderAttemptOrigin.LOCAL_RUNTIME
        assert result.attempts == ()
        assert result.diagnostics["pre_provider_failure"]["phase"] == "local_runtime"
        assert result.diagnostics["policy_model_call_count"] == 0
        assert policy.port.last_model_call_count == 0
        assert scripted.calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("fault_stage", "fault", "expected_kind"),
    (
        (
            "catalog",
            GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID),
            ModelFailureKind.SCHEMA_ERROR,
        ),
        (
            "admission",
            ModelRequestCapacityError(
                ModelRequestBreakdown(
                    "initial",
                    admission_action="context_capacity",
                    effective_input_limit=1,
                )
            ),
            ModelFailureKind.CONTEXT_CAPACITY,
        ),
    ),
)
def test_pre_provider_typed_schema_and_capacity_faults_remain_local(
    monkeypatch,
    fault_stage,
    fault,
    expected_kind,
) -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world(f"typed-pre-provider-{fault_stage}", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        def fail(*_args, **_kwargs):
            raise fault

        if fault_stage == "catalog":
            monkeypatch.setattr(turn_packer_module, "compile_grounded_action_catalog", fail)
        else:
            monkeypatch.setattr(pydantic_bridge.RequestAdmission, "admit", fail)

        result = await policy.port.generate(ModelDecisionRequest(f"request:typed-{fault_stage}", context))

        assert result.failure is not None
        assert result.failure.kind is expected_kind
        assert result.failure.attempt_origin is ProviderAttemptOrigin.LOCAL_RUNTIME
        assert policy.port.last_model_call_count == 0
        assert scripted.calls == 0

    asyncio.run(scenario())


def test_pending_official_exchange_survives_pre_provider_capacity_rejection(monkeypatch) -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("pending-capacity", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        scripted = ScriptedModel([("list_regions", {})])
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:pending-first", first_context))
        assert first.failure is None and first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        history_before = policy.port.message_history

        def reject(*_args, **_kwargs):
            raise ModelRequestCapacityError(
                ModelRequestBreakdown(
                    "initial",
                    admission_action="context_capacity",
                    effective_input_limit=1,
                )
            )

        monkeypatch.setattr(pydantic_bridge.RequestAdmission, "admit", reject)
        second = await policy.port.generate(
            ModelDecisionRequest("request:pending-rejected", second_context, last_step=step)
        )

        assert second.output is None
        assert second.failure is not None
        assert second.failure.kind is ModelFailureKind.CONTEXT_CAPACITY
        assert second.attempts == ()
        assert policy.port.last_model_call_count == 0
        assert scripted.calls == 1
        assert policy.port.message_history is history_before
        assert policy.port.message_history == history_before

    asyncio.run(scenario())


def test_native_action_policy_uses_one_deliberate_call_per_recovery_event() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action", "first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("recovery", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "grounding_stall",
                "stable_signature": "generic:recovery:1",
                "recovery_attempt": 1,
            },
        )

        first = await policy.port.generate(ModelDecisionRequest("request:deliberate-1", context))
        assert first.output is not None
        committed = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="provider_free_committed_action",
        )
        next_context = replace(context, last_step=committed)
        second = await policy.port.generate(
            ModelDecisionRequest("request:deliberate-2", next_context, last_step=committed)
        )

        assert first.attempts[0].phase == "deliberate"
        assert first.attempts[0].trigger == "grounding_gap"
        assert first.attempts[0].thinking_requested == "enabled"
        assert first.attempts[0].max_output_tokens == 2048
        assert second.attempts[0].phase == "ordinary"
        assert second.attempts[0].trigger == "ordinary"
        assert second.attempts[0].thinking_requested == "disabled"
        assert second.attempts[0].max_output_tokens == 1024
        assert [settings["max_tokens"] for settings in scripted.model_settings] == [2048, 1024]

    asyncio.run(scenario())


def test_standalone_native_path_does_not_invent_a_context_only_final_response_turn() -> None:
    class OutputTaskEvaluator(SharedTaskEvaluator):
        async def evaluate(self, task, observation):
            evaluation = await super().evaluate(task, observation)
            if evaluation.status.value != "complete":
                return evaluation
            return replace(
                evaluation,
                outputs=(
                    EvaluatedOutput(
                        "answer",
                        "enabled",
                        (observation.facts[0].fact_id,),
                    ),
                ),
            )

    async def scenario() -> None:
        scripted = ScriptedModel([])
        policy = _policy(scripted.build())
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            OutputTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
        )
        task = replace(shared_task(), requested_outputs=("answer",))
        environment = ScriptedEnvironment(initial_observation=shared_world("complete", True))

        state = await runtime.run_task(environment, task)

        assert state.status is RunStatus.DONE
        assert state.execution_count == 0
        assert state.step_count == 0
        assert state.last_step is None
        assert scripted.offered_tools == []

    asyncio.run(scenario())


def test_pydantic_ai_ask_user_preserves_question_and_runtime_resume() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("ask_user", {"question": "Which value should I enter?", "requested_fields": ["value"]}),
                ("abort", {"reason": "resume observed", "category": "user_request"}),
            ]
        )
        runtime = _runtime(scripted.build())
        environment = ScriptedEnvironment(initial_observation=shared_world("before", False))
        task = shared_task()

        paused = await runtime.run_task(environment, task)

        assert paused.status is RunStatus.WAITING_USER
        assert paused.last_step is not None
        assert paused.last_step.decision.question == "Which value should I enter?"
        assert paused.last_step.decision.requested_fields == ("value",)

        resumed = await runtime.resume_user(
            environment,
            replace(task, inputs={"value": "provided"}, revision=2),
            paused,
        )

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.task_revision == 2
        assert scripted.calls == 2
        assert "provided" in repr(scripted.messages[-1])

    asyncio.run(scenario())


def test_pydantic_ai_rejects_repair_that_invents_missing_semantic_content() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("ask_user", {}),
                ("ask_user", {"question": "Which value?", "requested_fields": ["value"]}),
            ]
        )
        environment = ScriptedEnvironment(initial_observation=shared_world("before", False))

        state = await _runtime(scripted.build()).run_task(environment, shared_task())

        assert state.status is RunStatus.FAILED
        assert scripted.calls == 2
        assert "representation-only repaired tool call" in repr(scripted.messages)
        assert state.workspace.recent_steps == ()

    asyncio.run(scenario())


def test_pydantic_ai_repairs_invalid_representation_without_changing_target() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action_invalid_extra", "repeat_last_gui_call"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("invalid-extra", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:invalid-extra", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == ["ordinary", "representation_repair"]

    asyncio.run(scenario())


def test_representation_repair_cannot_change_effect_bearing_leaf_values() -> None:
    preserves = pydantic_bridge._repair_preserves_rejected_semantics
    invalid = GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    type_text = ToolSpec(
        "type_text",
        "fixture",
        {
            "type": "object",
            "properties": {"target": {"type": "string"}, "text": {"type": "string"}},
            "required": ["target", "text"],
            "additionalProperties": False,
        },
    )
    update_profile = ToolSpec(
        "update_profile",
        "fixture",
        {
            "type": "object",
            "properties": {
                "form_ref": {"type": "string"},
                "fields": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["target", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["form_ref", "fields"],
            "additionalProperties": False,
        },
    )

    assert not preserves(
        invalid,
        (ToolCall("type_text", {"target": "E1", "text": "original", "unexpected": True}),),
        ToolCall("type_text", {"target": "E1", "text": "CHANGED"}),
        (type_text,),
    )
    assert not preserves(
        invalid,
        (
            ToolCall(
                "update_profile",
                {"form_ref": "N1", "fields": [{"target": "E1", "value": "old"}]},
            ),
        ),
        ToolCall(
            "update_profile",
            {"form_ref": "N1", "fields": [{"target": "E1", "value": "new"}]},
        ),
        (update_profile,),
    )
    assert preserves(
        invalid,
        (ToolCall("type_text", {"target": "E1", "text": "same", "unexpected": True}),),
        ToolCall("type_text", {"target": "E1", "text": "same"}),
        (type_text,),
    )


def test_representation_repair_cannot_select_among_multiple_semantic_calls() -> None:
    first = ToolCall("read_region", {"region_ref": "R1"})
    second = ToolCall("search_page_content", {"query": "different operation"})
    specs = (
        ToolSpec(
            "read_region",
            "fixture",
            {
                "type": "object",
                "properties": {"region_ref": {"type": "string"}},
                "required": ["region_ref"],
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            "search_page_content",
            "fixture",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
    )

    assert not pydantic_bridge._repair_preserves_rejected_semantics(
        GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS),
        (first, second),
        second,
        specs,
    )


def test_representation_repair_cannot_delete_legal_optional_operands() -> None:
    spec = ToolSpec(
        "ask_user",
        "fixture",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                    "requested_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 32,
                    },
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    )
    rejected = ToolCall(
        "ask_user",
        {
            "question": "Which value?",
            "requested_fields": ["account"],
            "unexpected": "x",
        },
    )

    assert not pydantic_bridge._repair_preserves_rejected_semantics(
        GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS),
        (rejected,),
        ToolCall("ask_user", {"question": "Which value?"}),
        (spec,),
    )
    assert pydantic_bridge._repair_preserves_rejected_semantics(
        GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS),
        (rejected,),
        ToolCall(
            "ask_user",
            {"question": "Which value?", "requested_fields": ["account"]},
        ),
        (spec,),
    )


def test_provider_repair_dropping_legal_optional_operand_is_rejected() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                (
                    "ask_user",
                    {
                        "question": "Which value?",
                        "requested_fields": ["account"],
                        "unexpected": "x",
                    },
                ),
                ("ask_user", {"question": "Which value?"}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("optional-operand-pruning", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:optional-pruning", context))

        assert result.failure is not None
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "representation_repair",
        ]

    asyncio.run(scenario())


def test_pydantic_ai_records_rate_limit_then_retries_once(monkeypatch) -> None:
    async def scenario() -> None:
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", fake_sleep)
        scripted = ScriptedModel(
            [
                ModelHTTPError(
                    429,
                    "scripted",
                    {"error": "redacted fixture body"},
                    headers={"Retry-After": "9"},
                ),
                "first_gui_action",
            ]
        )
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert scripted.calls == 2
        assert delays == [5.0]
        assert policy.port.last_model_call_count == 2
        assert policy.port.last_provider_retry_count == 1
        assert policy.last_metadata is not None
        assert policy.last_metadata.rate_limit_retry_count == 1
        assert policy.last_metadata.transient_retry_count == 0
        attempts = policy.port.last_generation_attempts
        assert [item.phase for item in attempts] == ["ordinary", "ordinary_provider_retry"]
        assert all(item.role == "action_policy" for item in attempts)
        assert all(item.trigger == "ordinary" for item in attempts)
        assert all(item.thinking_requested == "disabled" for item in attempts)
        assert all(item.max_output_tokens == 1024 for item in attempts)
        assert [item.status for item in attempts] == ["failed", "accepted"]
        assert attempts[0].exception_class == "ModelHTTPError"
        assert attempts[0].transcript["error.code"] == "rate_limited"
        assert attempts[0].transcript["error.http_status"] == 429
        assert attempts[0].transcript["error.retry_after_s"] == 9.0
        assert "redacted fixture body" not in repr(attempts[0].transcript)

    asyncio.run(scenario())


def test_pydantic_ai_provider_classification_keeps_nonretryable_failures_typed() -> None:
    auth = pydantic_bridge._classify_provider_failure(ModelHTTPError(401, "scripted"))
    invalid = pydantic_bridge._classify_provider_failure(ModelHTTPError(422, "scripted"))
    unavailable = pydantic_bridge._classify_provider_failure(ModelHTTPError(503, "scripted"))

    assert (auth.code.value, auth.retryable) == ("authentication", False)
    assert (invalid.code.value, invalid.retryable) == ("invalid_request", False)
    assert (unavailable.code.value, unavailable.retryable) == ("unavailable", True)


def test_pydantic_ai_does_not_count_retry_cancelled_during_backoff(monkeypatch) -> None:
    async def scenario() -> None:
        port = PydanticAIGroundedDecisionPort(
            model=object(),
            provider_id="fixture",
            model_id="scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=2.0,
        )

        async def provider_call():
            raise ModelHTTPError(503, "scripted")

        async def cancelled_backoff(_delay: float) -> None:
            raise asyncio.CancelledError

        envelope = await _bound_envelope_for_port(port, "retry-backoff-envelope")
        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", cancelled_backoff)
        with pytest.raises(asyncio.CancelledError):
            await port._run_provider_call(
                provider_call,
                phase="initial",
                envelope=envelope,
                provider_error_type=ModelHTTPError,
            )

        assert port.last_model_call_count == 1
        assert port.last_provider_retry_count == 0
        assert len(port.last_generation_attempts) == 1

    asyncio.run(scenario())


def test_pydantic_ai_records_inflight_provider_cancellation() -> None:
    async def scenario() -> None:
        port = PydanticAIGroundedDecisionPort(
            model=object(),
            provider_id="fixture",
            model_id="scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=2.0,
        )

        async def provider_call():
            raise asyncio.CancelledError

        envelope = await _bound_envelope_for_port(port, "inflight-cancellation")
        with pytest.raises(asyncio.CancelledError):
            await port._run_provider_call(
                provider_call,
                phase="initial_provider_retry",
                envelope=envelope,
                provider_error_type=ModelHTTPError,
            )

        assert port.last_model_call_count == 1
        attempt = port.last_generation_attempts[0]
        assert attempt.phase == "initial_provider_retry"
        assert attempt.status == "cancelled"
        assert attempt.exception_class == "CancelledError"
        assert attempt.transcript["network_dispatched"] is True
        assert attempt.transcript["error.code"] == "cancelled"

    asyncio.run(scenario())


def test_pydantic_ai_resolves_the_normalizer_call_not_the_raw_call(monkeypatch) -> None:
    normalized = ToolCall("activate_selector", {"grounding_ref": "E5"}, "call:1")
    resolved_decision = SearchPageContentResult(
        "context:test",
        normalized.name,
        normalized.arguments,
        {"kind": "Matches", "items": []},
        normalized.call_id,
    )
    monkeypatch.setattr(
        pydantic_bridge.ProviderCallNormalizer,
        "normalize",
        lambda *_args: ToolCallReconciliationResult(
            ToolCallReconciliationStatus.EXACT,
            exact_call=normalized,
        ),
    )
    captured = {}
    monkeypatch.setattr(
        pydantic_bridge,
        "resolve_grounded_action_call",
        lambda _catalog, call, **_kwargs: captured.setdefault(
            "resolution", SimpleNamespace(decision=resolved_decision)
        ),
    )
    output = DeferredToolRequests(calls=[ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1")])

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
    )

    assert exchange is not None
    assert exchange.call == normalized
    assert exchange.decision is resolved_decision
    assert len(exchange.response.parts) == 1
    assert error is None
    assert parsed == ()
    assert captured["resolution"].decision is resolved_decision


def test_multiple_deferred_calls_resolve_only_the_first_and_record_discarded_count(monkeypatch) -> None:
    normalized = ToolCall("read_region", {"region_ref": "R1"}, "call:1")
    resolved_decision = SearchPageContentResult(
        "context:test",
        normalized.name,
        normalized.arguments,
        {"kind": "Matches", "items": []},
        normalized.call_id,
    )
    normalized_calls = []
    resolved_calls = []

    def normalize(_self, call, _catalog):
        normalized_calls.append(call)
        return ToolCallReconciliationResult(
            ToolCallReconciliationStatus.EXACT,
            exact_call=normalized,
        )

    def resolve(_catalog, call, **_kwargs):
        resolved_calls.append(call)
        return SimpleNamespace(decision=resolved_decision)

    monkeypatch.setattr(pydantic_bridge.ProviderCallNormalizer, "normalize", normalize)
    monkeypatch.setattr(pydantic_bridge, "resolve_grounded_action_call", resolve)
    output = DeferredToolRequests(
        calls=[
            ToolCallPart("read_region", {"region_ref": "R1"}, "call:1"),
            ToolCallPart("search_page_content", {"query": "scope"}, "call:2"),
        ]
    )

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
    )

    assert exchange is not None
    assert exchange.call == normalized
    assert exchange.decision is resolved_decision
    assert exchange.discarded_call_count == 1
    assert [
        (part.tool_name, part.tool_call_id)
        for part in exchange.response.parts
        if isinstance(part, ToolCallPart)
    ] == [
        ("read_region", "call:1"),
        ("search_page_content", "call:2"),
    ]
    assert error is None
    assert parsed == ()
    assert normalized_calls == [ToolCall("read_region", {"region_ref": "R1"}, "call:1")]
    assert resolved_calls == [normalized]


def test_invalid_first_deferred_call_never_falls_through_to_a_later_call(monkeypatch) -> None:
    normalized_calls = []

    def normalize(_self, call, _catalog):
        normalized_calls.append(call)
        return SimpleNamespace(
            status=ToolCallReconciliationStatus.REPAIR_REQUIRED,
            issue_code="invalid_argument",
            field_paths=("parameters.region_ref",),
            argument_code="invalid_value",
        )

    monkeypatch.setattr(pydantic_bridge.ProviderCallNormalizer, "normalize", normalize)
    monkeypatch.setattr(
        pydantic_bridge,
        "resolve_grounded_action_call",
        lambda *_args, **_kwargs: pytest.fail("an invalid first call must not resolve or fall through"),
    )
    output = DeferredToolRequests(
        calls=[
            ToolCallPart("read_region", {"region_ref": "invalid"}, "call:1"),
            ToolCallPart("search_page_content", {"query": "scope"}, "call:2"),
        ]
    )

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(catalog_id="grounded-catalog:test", delivery_id="delivery:" + "d" * 64),
        "context:test",
    )

    assert exchange is None
    assert error is not None
    assert error.code is GroundedToolResolutionCode.INVALID_ARGUMENTS
    assert parsed == (ToolCall("read_region", {"region_ref": "invalid"}, "call:1"),)
    assert normalized_calls == [ToolCall("read_region", {"region_ref": "invalid"}, "call:1")]


def test_accepted_response_preserves_exact_reasoning_prose_and_calls(monkeypatch) -> None:
    normalized = ToolCall("activate_selector", {"grounding_ref": "E5"}, "call:1")
    resolved_decision = SearchPageContentResult(
        "context:test",
        normalized.name,
        normalized.arguments,
        {"kind": "Matches", "items": []},
        normalized.call_id,
    )
    monkeypatch.setattr(
        pydantic_bridge.ProviderCallNormalizer,
        "normalize",
        lambda *_args: ToolCallReconciliationResult(
            ToolCallReconciliationStatus.EXACT,
            exact_call=normalized,
        ),
    )
    monkeypatch.setattr(
        pydantic_bridge,
        "resolve_grounded_action_call",
        lambda *_args, **_kwargs: SimpleNamespace(decision=resolved_decision),
    )
    narration = "I will click the next visible control now."
    source = ModelResponse(
        parts=[
            ThinkingPart("hidden chain " * 1_000),
            TextPart(narration),
            ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1"),
            ToolCallPart("discarded", {}, "call:discarded"),
        ]
    )
    output = DeferredToolRequests(
        calls=[
            ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1"),
            ToolCallPart("discarded", {}, "call:discarded"),
        ]
    )

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
        source_response=source,
    )

    assert exchange is not None
    assert error is None
    assert parsed == ()
    assert exchange.response is source
    assert [type(part) for part in exchange.response.parts] == [
        ThinkingPart,
        TextPart,
        ToolCallPart,
        ToolCallPart,
    ]
    assert narration in repr(exchange.response)
    assert exchange.response.parts[2].tool_call_id == normalized.call_id


def test_zhipu_pydantic_ai_factory_is_selected_by_wire_capability() -> None:
    base = {
        "LLM_ACTIVE_PROFILE": "zhipu",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
        "LLM_ZHIPU_BASE_URL": "https://example.invalid/v1",
        "LLM_ZHIPU_API_KEY": "fixture-secret",
        "LLM_ZHIPU_MODEL": "glm-4.7-flash",
        "LLM_DECISION_PERCEPTION": "text-only.v1",
    }

    policy = zhipu_pydantic_ai_policy_from_environment(base, call_timeout_s=5.0)

    assert policy.port.provider_id == "zhipu"
    assert policy.port.model_id == "glm-4.7-flash"
    assert policy.port.supports_multimodal is False
    assert type(policy.port.model).__name__ == "ZaiModel"
    assert policy.port.transport_timeout_s == 2.0
    assert policy.port.policy_timeout_s == 5.0
    assert policy.port.max_provider_retry_delay_s == 0.5
    assert policy.port.history_compaction_timeout_s == 2.0
    assert policy.port.model._provider.client.timeout == 2.0
    prepared, _ = policy.port.model.prepare_request(
        {
            "thinking": False,
            "max_tokens": policy.port.reasoning_policy.repair().max_output_tokens,
            "temperature": 0.0,
            "parallel_tool_calls": False,
        },
        ModelRequestParameters(),
    )
    assert prepared["extra_body"]["thinking"]["type"] == "disabled"
    assert prepared["max_tokens"] == 512
    assert prepared["temperature"] == 0.0
    assert prepared["parallel_tool_calls"] is False

    selected = model_policy_from_environment(
        {**base, "LLM_ACTION_POLICY_WIRE_CAPABILITY": "native_single_tool"},
        call_timeout_s=5.0,
    )
    assert isinstance(selected.port, PydanticAIGroundedDecisionPort)

    with pytest.raises(ValueError, match="WIRE_CAPABILITY"):
        model_policy_from_environment(
            {**base, "LLM_ACTION_POLICY_WIRE_CAPABILITY": "json_single_command"},
            call_timeout_s=5.0,
        )


def test_compaction_and_provider_recovery_fit_one_policy_deadline() -> None:
    compaction, retry, transport = pydantic_bridge._provider_time_budgets(90.0)

    assert (compaction, retry, transport) == (42.25, 5.0, 42.25)
    assert retry + (2 * transport) + 0.5 == 90.0
    assert pydantic_bridge._remaining_action_attempt_timeout(
        deadline_s=89.5,
        now_s=0.0,
        retry_delay_reserve_s=retry,
        maximum_timeout_s=transport,
    ) == 42.25
    # run25's final compactor used 23 seconds. The old static partition still
    # limited each action attempt to 21.125 seconds; deadline propagation gives
    # both remaining attempts 30.75 seconds without exceeding the same total.
    assert pydantic_bridge._remaining_action_attempt_timeout(
        deadline_s=89.5,
        now_s=23.0,
        retry_delay_reserve_s=retry,
        maximum_timeout_s=transport,
    ) == 30.75


def test_pydantic_ai_factory_selects_separate_aliyun_profile() -> None:
    policy = zhipu_pydantic_ai_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "aliyun",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            "LLM_ALIYUN_BASE_URL": "https://aliyun.invalid/compatible-mode/v1",
            "LLM_ALIYUN_API_KEY": "fixture-secret",
            "LLM_ALIYUN_MODEL": "glm-5.2",
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=5.0,
    )

    assert policy.port.provider_id == "aliyun"
    assert policy.port.model_id == "glm-5.2"
    assert policy.port.endpoint_host == "aliyun.invalid"
    assert policy.port.supports_multimodal is False
    assert type(policy.port.model).__name__ == "ZaiModel"


@pytest.mark.parametrize(
    ("profile", "prefix", "base_url", "model_id"),
    (
        ("mistral", "LLM_MISTRAL", "https://mistral.invalid/v1", "mistral-small"),
        ("gemini", "LLM_GEMINI", "https://gemini.invalid/v1beta/openai", "gemini-flash"),
    ),
)
def test_openai_compatible_profiles_use_the_single_pydantic_ai_policy(
    profile: str,
    prefix: str,
    base_url: str,
    model_id: str,
) -> None:
    policy = model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": profile,
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            f"{prefix}_BASE_URL": base_url,
            f"{prefix}_API_KEY": "fixture-secret",
            f"{prefix}_MODEL": model_id,
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=5.0,
    )

    assert isinstance(policy.port, PydanticAIGroundedDecisionPort)
    assert policy.port.provider_id == profile
    assert policy.port.model_id == model_id


def test_local_openai_compatible_profile_uses_the_single_pydantic_ai_policy() -> None:
    policy = model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "local",
            "LLM_LOCAL_PROVIDER": "openai_compatible",
            "LLM_LOCAL_BASE_URL": "http://127.0.0.1:11434/v1",
            "LLM_LOCAL_MODEL": "qwen-test",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
        },
        call_timeout_s=5.0,
    )

    assert isinstance(policy.port, PydanticAIGroundedDecisionPort)
    assert policy.port.provider_id == "local"
    assert policy.port.model_id == "qwen-test"


def test_factory_selects_deepseek_pydantic_ai_profile_by_default() -> None:
    selected = model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "deepseek",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY": "fixture-secret",
            "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=5.0,
    )

    assert isinstance(selected.port, PydanticAIGroundedDecisionPort)
    assert selected.port.provider_id == "deepseek"
    assert selected.port.model_id == "deepseek-v4-flash"
    assert selected.port.supports_multimodal is False
    assert selected.port.transport_timeout_s == 2.0
    assert selected.port.policy_timeout_s == 5.0
    assert selected.port.reasoning_policy.repair_max_tokens == 512
    assert selected.port.history_compaction_timeout_s == 2.0
    assert selected.port.model._provider.client.timeout == 2.0
    assert selected.port.model.settings == {
        "max_tokens": 1024,
        "temperature": 0.0,
        "thinking": False,
    }
    assert selected.port.model.profile["openai_chat_supports_max_completion_tokens"] is False
    with pytest.raises(ValueError, match="WIRE_CAPABILITY"):
        model_policy_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "deepseek",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "LLM_ACTION_POLICY_WIRE_CAPABILITY": "json_single_command",
            },
            call_timeout_s=5.0,
        )
