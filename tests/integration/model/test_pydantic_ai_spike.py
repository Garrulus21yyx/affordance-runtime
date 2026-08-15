from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import pytest

pytest.importorskip("pydantic_ai")

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import affordance_runtime.model.policy.pydantic_ai_bridge as pydantic_bridge
from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import EvaluatedOutput
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.model.policy.factory import model_policy_from_environment
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
from affordance_runtime.model.policy.tool_contracts import ToolCall
from tests.support.agent.core_loop_support import (
    SharedActionEvaluator,
    SharedTaskEvaluator,
    shared_task,
    shared_world,
)

DecisionScript = list[tuple[str, dict[str, object]] | str]


@dataclass
class ScriptedModel:
    decisions: DecisionScript
    calls: int = 0
    messages: list[object] = field(default_factory=list)
    offered_tools: list[tuple[str, ...]] = field(default_factory=list)

    def build(self) -> FunctionModel:
        async def respond(messages, info: AgentInfo) -> ModelResponse:
            self.calls += 1
            self.messages.append(messages)
            self.offered_tools.append(tuple(tool.name for tool in info.function_tools))
            scripted = self.decisions.pop(0)
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
                    "next_actions",
                    "request_evidence",
                }
                name = next(tool.name for tool in info.function_tools if tool.name not in controls)
                arguments: dict[str, object] = {}
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
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
        transport_timeout_s=4.0,
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=5.0)


def _runtime(model) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(_policy(model)),
        SharedActionEvaluator(),
        SharedTaskEvaluator(),
    )


def test_pydantic_ai_decision_executes_one_action_then_runtime_auto_completes() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await _runtime(scripted.build()).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert state.execution_count == 1
        assert scripted.calls == 1
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "pydantic-call:1"
        assert "ask_user" in scripted.offered_tools[0]
        assert "propose_done" not in scripted.offered_tools[0]

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
            SharedActionEvaluator(),
            OutputTaskEvaluator(),
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


def test_pydantic_ai_returns_invalid_arguments_for_one_bounded_repair() -> None:
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
        assert "Re-emit exactly one call" in repr(scripted.messages[-1])

    asyncio.run(scenario())


def test_pydantic_ai_resolves_the_normalizer_call_not_the_raw_call(monkeypatch) -> None:
    normalized = ToolCall("activate_selector", {"grounding_ref": "E5"}, "call:1")
    monkeypatch.setattr(
        pydantic_bridge.ProviderCallNormalizer,
        "normalize",
        lambda *_args: ToolCallReconciliationResult(
            ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT,
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

    decision = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(catalog_id="grounded-catalog:test"),
        "context:test",
    )

    assert decision == normalized
    assert captured["resolution"].decision == normalized


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
