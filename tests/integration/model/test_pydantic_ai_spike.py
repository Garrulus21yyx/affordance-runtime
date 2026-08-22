from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import pytest

pytest.importorskip("pydantic_ai")

from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel

import affordance_runtime.model.policy.pydantic_ai_bridge as pydantic_bridge
from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import EvaluatedOutput
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
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from tests.support.agent.core_loop_support import (
    SharedActionOutcomeProjector,
    SharedTaskEvaluator,
    shared_task,
    shared_world,
)

DecisionScript = list[tuple[str, dict[str, object]] | str | Exception]


@dataclass
class ScriptedModel:
    decisions: DecisionScript
    calls: int = 0
    messages: list[object] = field(default_factory=list)
    offered_tools: list[tuple[str, ...]] = field(default_factory=list)
    model_settings: list[object] = field(default_factory=list)
    last_gui_call: tuple[str, dict[str, object]] | None = None

    def build(self) -> FunctionModel:
        async def respond(messages, info: AgentInfo) -> ModelResponse:
            self.calls += 1
            self.messages.append(messages)
            self.offered_tools.append(tuple(tool.name for tool in info.function_tools))
            self.model_settings.append(info.model_settings)
            scripted = self.decisions.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            if isinstance(scripted, str) and scripted in {"final_response", "zero_calls"}:
                return ModelResponse(
                    parts=[TextPart("Shared state is enabled." if scripted == "final_response" else "no tool call")],
                    provider_response_id=f"pydantic-response:{self.calls}",
                )
            if scripted == "malformed_tool_call":
                name = info.function_tools[0].name
                return ModelResponse(
                    parts=[ToolCallPart(name, "{not-json", tool_call_id=f"pydantic-call:{self.calls}")],
                    provider_response_id=f"pydantic-response:{self.calls}",
                )
            if isinstance(scripted, str) and scripted in {
                "first_gui_action",
                "first_gui_action_invalid_extra",
                "multiple_gui_actions",
            }:
                controls = {
                    "ask_user",
                    "wait",
                    "abort",
                    "find_controls",
                    "request_evidence",
                }
                name = next(tool.name for tool in info.function_tools if tool.name not in controls)
                selected = next(tool for tool in info.function_tools if tool.name == name)
                target_schema = selected.parameters_json_schema["properties"].get("target", {})
                public = json.loads(messages[-1].parts[0].content)
                match = re.search(
                    rf"\[(E[1-9][0-9]{{0,2}})\][^\n]*verbs=[^\n]*\b{re.escape(name)}\b",
                    public["observation"],
                )
                assert match is not None
                target = match.group(1)
                arguments: dict[str, object] = {"target": target} if target_schema else {}
                self.last_gui_call = (name, dict(arguments))
                if scripted == "first_gui_action_invalid_extra":
                    arguments["unexpected"] = "remove-me"
            elif scripted == "repeat_last_gui_call":
                assert self.last_gui_call is not None
                name, remembered_arguments = self.last_gui_call
                arguments = dict(remembered_arguments)
            else:
                assert isinstance(scripted, tuple)
                name, arguments = scripted
            parts = [
                ToolCallPart(
                    name,
                    arguments,
                    tool_call_id=f"pydantic-call:{self.calls}",
                )
            ]
            if scripted == "multiple_gui_actions":
                parts.append(
                    ToolCallPart(
                        name,
                        arguments,
                        tool_call_id=f"pydantic-call:{self.calls}:second",
                    )
                )
            return ModelResponse(
                parts=parts,
                provider_response_id=f"pydantic-response:{self.calls}",
            )

        return FunctionModel(respond, model_name="scripted")


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


def _runtime(model) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(_policy(model)),
        SharedActionOutcomeProjector(),
        SharedTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
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
        assert scripted.model_settings == [{"max_tokens": 1024, "temperature": 0.0, "parallel_tool_calls": False}]
        assert pydantic_bridge._action_model_settings(policy.port.last_call_profile) == {
            "thinking": False,
            "max_tokens": 1024,
            "temperature": 0.0,
            "parallel_tool_calls": False,
        }
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "pydantic-call:1"
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


def test_multiple_provider_tool_calls_execute_neither_and_use_one_same_turn_repair() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["multiple_gui_actions", "repeat_last_gui_call"])
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
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == ["ordinary", "representation_repair"]

    asyncio.run(scenario())


@pytest.mark.parametrize("scripted_output", ["zero_calls", "malformed_tool_call"])
def test_zero_or_wholly_unparseable_output_fails_without_representation_repair(
    scripted_output: str,
) -> None:
    async def scenario() -> None:
        scripted = ScriptedModel([scripted_output])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world(f"invalid-envelope:{scripted_output}", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(
            ModelDecisionRequest(f"request:{scripted_output}", context)
        )

        assert result.failure is not None
        assert scripted.calls == 1
        assert len(result.attempts) == 1
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_multiple_call_repair_cannot_reselect_operation_or_target() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            ["multiple_gui_actions", ("ask_user", {"question": "Which value should be used?"})]
        )
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

        assert result.output is None
        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INVALID_TOOL_ARGUMENTS
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == ["ordinary", "representation_repair"]

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
        second = await policy.port.generate(ModelDecisionRequest("request:deliberate-2", context))

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
    set_form_fields = ToolSpec(
        "set_form_fields",
        "fixture",
        {
            "type": "object",
            "properties": {
                "form_ref": {"type": "string"},
                "fields": {
                    "type": "array",
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
                "set_form_fields",
                {"form_ref": "N1", "fields": [{"target": "E1", "value": "old"}]},
            ),
        ),
        ToolCall(
            "set_form_fields",
            {"form_ref": "N1", "fields": [{"target": "E1", "value": "new"}]},
        ),
        (set_form_fields,),
    )
    assert preserves(
        invalid,
        (ToolCall("type_text", {"target": "E1", "text": "same", "unexpected": True}),),
        ToolCall("type_text", {"target": "E1", "text": "same"}),
        (type_text,),
    )


def test_representation_repair_cannot_delete_legal_optional_operands() -> None:
    spec = ToolSpec(
        "ask_user",
        "fixture",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "requested_fields": {"type": "array", "items": {"type": "string"}},
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

        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", cancelled_backoff)
        with pytest.raises(asyncio.CancelledError):
            await port._run_provider_call(
                provider_call,
                phase="initial",
                specs=(),
                input_messages=(),
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

        with pytest.raises(asyncio.CancelledError):
            await port._run_provider_call(
                provider_call,
                phase="initial_provider_retry",
                specs=(),
                input_messages=({"role": "user", "content": "fixture"},),
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
        lambda _catalog, call, **_kwargs: captured.setdefault("resolution", SimpleNamespace(decision=call)),
    )
    output = DeferredToolRequests(calls=[ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1")])

    decision, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
    )

    assert decision == normalized
    assert error is None
    assert parsed == (normalized,)
    assert captured["resolution"].decision == normalized


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
    assert policy.port.max_provider_retry_delay_s == 0.5
    prepared, _ = policy.port.model.prepare_request(
        pydantic_bridge._action_model_settings(policy.port.reasoning_policy.repair()),
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
    assert selected.port.reasoning_policy.repair_max_tokens == 512

    with pytest.raises(ValueError, match="WIRE_CAPABILITY"):
        model_policy_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "deepseek",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "LLM_ACTION_POLICY_WIRE_CAPABILITY": "json_single_command",
            },
            call_timeout_s=5.0,
        )
