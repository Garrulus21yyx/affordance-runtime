from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent import Abort
from affordance_runtime.agent.context import ContextBuilder, ModelFailureKind
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_tool_catalog
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolPhase
from affordance_runtime.model.policy.grounded_tool_port_bridge import CompactJsonDecisionPort
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.request_admission import ModelRequestBudget
from affordance_runtime.model.providers.port import (
    ModelConfig,
    StructuredOutputError,
    StructuredOutputViolation,
)
from tests.support.agent.core_loop_support import SharedTaskEvaluator, _task, _world


async def _request():
    task = _task()
    world = _world("request-admission", False)
    evaluation = await SharedTaskEvaluator().evaluate(task, world)
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        evaluation,
    )
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    return ModelDecisionRequest("request:test", context), catalog


def test_complete_request_breakdown_covers_rendered_sections_and_is_deterministic() -> None:
    async def scenario() -> None:
        request, catalog = await _request()
        binder = GroundedPolicyContextBinder()

        first = binder.action_request(
            request,
            catalog.specs,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        ).breakdown
        second = binder.action_request(
            request,
            catalog.specs,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        ).breakdown

        assert first == second
        assert first.system_tokens > 0
        assert first.task_plan_tokens > 0
        assert first.actor_world_tokens > 0
        assert first.history_tokens > 0
        assert first.tool_schema_tokens > 0
        assert first.image_estimated_tokens == 0
        assert first.estimated_total_tokens == (
            first.system_tokens
            + first.task_plan_tokens
            + first.actor_world_tokens
            + first.history_tokens
            + first.working_set_tokens
            + first.tool_schema_tokens
            + first.image_estimated_tokens
            + first.repair_tokens
            + first.provider_envelope_tokens
        )

    asyncio.run(scenario())


@dataclass
class _FakeCompactPort:
    scripted: list[object] = field(default_factory=list)
    calls: int = 0
    provider: str = "zhipu"
    model: str = "glm-4.1v-thinking-flashx"
    endpoint_class: str = "fixture"
    last_call: object | None = None
    last_transcript: object | None = None

    @property
    def supports_multimodal(self) -> bool:
        return False

    async def generate_structured(self, messages, output_schema, config):
        del messages, config
        self.calls += 1
        item = self.scripted.pop(0)
        if isinstance(item, BaseException):
            raise item
        name, arguments = item
        return output_schema(name=name, arguments=arguments)


def test_irreducible_over_budget_returns_context_capacity_without_provider_attempt() -> None:
    async def scenario() -> None:
        request, _catalog = await _request()
        port = _FakeCompactPort()
        adapter = CompactJsonDecisionPort(
            port,
            ModelConfig(rate_limit_retries=0, transient_retries=0),
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            context_binder=GroundedPolicyContextBinder(
                request_budget=ModelRequestBudget(admission_limit=1)
            ),
        )

        result = await adapter.generate(request)

        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.CONTEXT_CAPACITY
        assert port.calls == 0
        assert result.diagnostics["policy_model_call_count"] == 0
        assert result.diagnostics["admission_action"] == "context_capacity"
        assert result.diagnostics["estimated_total_tokens"] > result.diagnostics["admission_limit"]

    asyncio.run(scenario())


def test_repair_request_has_separate_admission_and_bounded_repair_tokens() -> None:
    async def scenario() -> None:
        request, _catalog = await _request()
        port = _FakeCompactPort(
            [
                StructuredOutputError(
                    "invalid",
                    violations=(StructuredOutputViolation("$.name", "missing"),),
                ),
                ("abort", {"reason": "stop", "category": "policy"}),
            ]
        )
        adapter = CompactJsonDecisionPort(
            port,
            ModelConfig(rate_limit_retries=0, transient_retries=0),
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
        )

        result = await adapter.generate(request)

        assert result.output is not None
        assert isinstance(result.output.decision, Abort)
        assert port.calls == 2
        breakdowns = result.diagnostics["request_breakdowns"]
        assert [item["phase"] for item in breakdowns] == ["initial", "structured_output_repair"]
        assert breakdowns[0]["repair_tokens"] == 0
        assert breakdowns[1]["repair_tokens"] > 0

    asyncio.run(scenario())
