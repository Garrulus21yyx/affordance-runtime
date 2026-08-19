from __future__ import annotations

import asyncio
import json
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
from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import EvaluatedOutput
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.model.policy.factory import model_policy_from_environment
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolCatalog,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
    RegisteredGroundedTool,
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

    def build(self) -> FunctionModel:
        async def respond(messages, info: AgentInfo) -> ModelResponse:
            self.calls += 1
            self.messages.append(messages)
            self.offered_tools.append(tuple(tool.name for tool in info.function_tools))
            self.model_settings.append(info.model_settings)
            scripted = self.decisions.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            if scripted == "final_response":
                return ModelResponse(
                    parts=[TextPart("Shared state is enabled.")],
                    provider_response_id=f"pydantic-response:{self.calls}",
                )
            if scripted == "first_gui_action":
                controls = {
                    "ask_user",
                    "wait",
                    "abort",
                    "find_actions",
                    "request_evidence",
                }
                name = next(tool.name for tool in info.function_tools if tool.name not in controls)
                selected = next(tool for tool in info.function_tools if tool.name == name)
                target_schema = selected.parameters_json_schema["properties"].get("target", {})
                public = json.loads(messages[-1].parts[0].content)
                target = next(
                    item["ref"]
                    for item in public["affordances"]
                    if name in item["verbs"]
                )
                arguments: dict[str, object] = {"target": target} if target_schema else {}
            else:
                assert isinstance(scripted, tuple)
                name, arguments = scripted
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        name,
                        arguments,
                        tool_call_id=f"pydantic-call:{self.calls}",
                    )
                ],
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
        # FunctionModel strips unsupported thinking, while preserving the
        # cross-model output/sampling budget. ZaiModel translates the same
        # unified False value to extra_body.thinking.type=disabled.
        assert scripted.model_settings == [{"max_tokens": 1024, "temperature": 0.0}]
        assert pydantic_bridge._ACTION_MODEL_SETTINGS == {
            "thinking": False,
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "pydantic-call:1"
        assert "ask_user" in scripted.offered_tools[0]
        assert "propose_done" not in scripted.offered_tools[0]
        attempt = policy.port.last_generation_attempts[0]
        assert attempt.phase == "initial"
        assert attempt.transcript["llm.input_messages"][0]["parts"][0]["content"]
        assert attempt.transcript["llm.output_messages"][0]["parts"][0]["tool_name"]
        assert policy.last_metadata is not None
        assert policy.last_metadata.latency_ms >= attempt.latency_ms > 0

    asyncio.run(scenario())


def test_pydantic_ai_emits_native_final_response_only_after_verified_outputs() -> None:
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
        scripted = ScriptedModel(["final_response"])
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
        assert state.step_count == 1
        assert state.last_step is not None
        assert isinstance(state.last_step.decision, FinalResponse)
        assert state.last_step.decision.content == "Shared state is enabled."
        assert scripted.offered_tools == [()]

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


def test_pydantic_ai_returns_invalid_arguments_feedback_without_repicking_in_repair() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("ask_user", {}),
                ("ask_user", {"question": "Which value?", "requested_fields": ["value"]}),
            ]
        )
        environment = ScriptedEnvironment(initial_observation=shared_world("before", False))

        state = await _runtime(scripted.build()).run_task(environment, shared_task())

        assert state.status is RunStatus.WAITING_USER
        assert scripted.calls == 2
        assert "Re-emit exactly one call" not in repr(scripted.messages)
        assert state.recent_steps[0].semantic_action == "tool_rejected"
        assert state.recent_steps[0].semantic_summary["result"]["failure_kind"] == "invalid_tool_arguments"

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
        assert [item.phase for item in attempts] == ["initial", "initial_provider_retry"]
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
    output = DeferredToolRequests(
        calls=[ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1")]
    )

    decision, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(catalog_id="grounded-catalog:test"),
        "context:test",
    )

    assert decision == normalized
    assert error is None
    assert parsed == normalized
    assert captured["resolution"].decision == normalized


def test_pydantic_ai_repair_message_preserves_runtime_rejection_reason() -> None:
    class RejectingBinding:
        def resolve(self, arguments, context_id: str, tool_call_id: str):
            del arguments, context_id, tool_call_id
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS,
                "visual property requests require exactly one evidence property",
            )

    catalog = GroundedToolCatalog(
        "grounded-catalog:test",
        "context:test",
        (
            RegisteredGroundedTool(
                ToolSpec(
                    "request_evidence",
                    "Request evidence.",
                    {
                        "type": "object",
                        "properties": {
                            "purpose": {"type": "string", "enum": ["target_disambiguation"]},
                            "subject": {"type": "string", "enum": ["current_world"]},
                        },
                        "required": ["purpose", "subject"],
                        "additionalProperties": False,
                    },
                ),
                RejectingBinding(),
            ),
        ),
        1,
    )
    output = DeferredToolRequests(
        calls=[
            ToolCallPart(
                "request_evidence",
                {"purpose": "target_disambiguation", "subject": "current_world"},
                "call:1",
            )
        ]
    )

    message = pydantic_bridge._repair_message(
        output,
        catalog,
        DeferredToolRequests,
        "context:test",
    )

    assert "Runtime rejection" in message
    assert "visual property requests require exactly one evidence property" in message


def test_zhipu_pydantic_ai_factory_is_explicit_about_model_compatibility() -> None:
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
        pydantic_bridge._ACTION_MODEL_SETTINGS,
        ModelRequestParameters(),
    )
    assert prepared["extra_body"]["thinking"]["type"] == "disabled"
    assert prepared["max_tokens"] == 1024
    assert prepared["temperature"] == 0.0

    with pytest.raises(ValueError, match="LLM_MODEL_ADAPTER=compact-json"):
        zhipu_pydantic_ai_policy_from_environment(
            {**base, "LLM_ZHIPU_MODEL": "glm-4.1v-thinking-flashx"},
            call_timeout_s=5.0,
        )

    selected = model_policy_from_environment(
        {**base, "LLM_MODEL_ADAPTER": "pydantic-ai"},
        call_timeout_s=5.0,
    )
    assert isinstance(selected.port, PydanticAIGroundedDecisionPort)


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
