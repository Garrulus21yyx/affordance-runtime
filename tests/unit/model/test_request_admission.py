from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field, replace

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent.context import ContextBuilder, ModelFailureKind
from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldDocumentView,
    ActorWorldNodeView,
    ActorWorldSnapshot,
    ActorWorldSourceView,
)
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
    AgentImageInput,
)
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex, WorldRegion
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_tool_catalog
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolPhase,
)
from affordance_runtime.model.policy.grounded_tool_port_bridge import CompactJsonDecisionPort
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.request_admission import ModelRequestBudget, estimate_model_request
from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ModelMessage,
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
    delivery = build_model_turn_delivery(context, include_images=False)
    catalog = compile_grounded_tool_catalog(
        context,
        GroundedToolPhase.ACTION_SELECTION,
        delivery,
    )
    return ModelDecisionRequest("request:test", context), catalog, delivery


def test_complete_request_breakdown_covers_rendered_sections_and_is_deterministic() -> None:
    async def scenario() -> None:
        request, catalog, delivery = await _request()
        binder = GroundedPolicyContextBinder()

        first = binder.action_request(
            request,
            catalog.specs,
            delivery,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        ).breakdown
        second = binder.action_request(
            request,
            catalog.specs,
            delivery,
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
            + first.evidence_tokens
            + first.tool_schema_tokens
            + first.image_estimated_tokens
            + first.repair_tokens
            + first.provider_envelope_tokens
        )

    asyncio.run(scenario())


def test_image_tokens_are_dimension_based_not_compressed_byte_based() -> None:
    small_png = _png(1280, 720)
    padded_png = small_png + (b"x" * (250 * 1024))
    first = AgentImageInput(
        "artifact:image:small",
        "image/png",
        small_png,
        hashlib.sha256(small_png).hexdigest(),
    )
    second = AgentImageInput(
        "artifact:image:padded",
        "image/png",
        padded_png,
        hashlib.sha256(padded_png).hexdigest(),
    )

    small = estimate_model_request(
        messages=(ModelMessage(role="user", content="see image"),),
        tools=(),
        image_inputs=(first,),
    )
    padded = estimate_model_request(
        messages=(ModelMessage(role="user", content="see image"),),
        tools=(),
        image_inputs=(second,),
    )

    assert small.image_estimated_tokens == padded.image_estimated_tokens
    assert padded.image_estimated_tokens < 5_000


def test_soft_target_uses_recoverable_region_projection_without_mutating_context() -> None:
    async def scenario() -> None:
        request, _catalog, _delivery = await _request()
        roots = tuple(
            ActorWorldNodeView(f"E{index}", "button", f"Button {index}", {"enabled": True}, source_refs=("S1",))
            for index in range(1, 240)
        )
        large_context = replace(
            request.agent_context,
            actor_world=ActorWorldSnapshot(
                (ActorWorldDocumentView("S1", "structural", roots, len(roots), len(roots), False),),
                (
                    ActorWorldSourceView(
                        "S1",
                        "structural",
                        "structural",
                        "current",
                        "complete",
                        "complete",
                        "not_available",
                    ),
                ),
                (),
                (),
                BoundedSection((), 0, False),
                (),
                (),
                (),
            ),
            grounding=AgentGroundingIndexView(
                tuple(
                    AgentGroundingEntityView(f"E{index}", "button", f"Button {index}", verbs=("activate",))
                    for index in range(1, 240)
                ),
                {f"target:{index}": f"E{index}" for index in range(1, 240)},
            ),
            region_index=WorldDeliveryIndex(
                request.agent_context.current_observation.observation_id,
                tuple(
                    WorldRegion(
                        f"region:test:{index + 1}-{min(index + 32, 239)}",
                        f"R{index // 32 + 1}",
                        "S1",
                        f"targets:{index + 1}-{min(index + 32, 239)}",
                        tuple(f"target:{target}" for target in range(index + 1, min(index + 33, 240))),
                        (),
                        f"button items {index + 1}-{min(index + 32, 239)}",
                        "button",
                        {"targets": min(32, 239 - index), "facts": 0, "actions": min(32, 239 - index)},
                        "complete",
                    )
                    for index in range(0, 239, 32)
                ),
            ),
        )
        request = ModelDecisionRequest(request.request_id, large_context)
        tool = ToolSpec(
            "activate_target",
            "Activate one current target.",
            {
                "type": "object",
                "properties": {"target": {"type": "string", "enum": ["E1"]}},
                "required": ["target"],
            },
        )
        binder = GroundedPolicyContextBinder(
            request_budget=ModelRequestBudget(
                soft_target_tokens=10,
                model_context_window=200_000,
                max_output_tokens=1,
                protocol_reserve_tokens=1,
                safety_margin_tokens=1,
                admission_limit=100_000,
            )
        )
        before_actor_world = request.agent_context.actor_world
        before_bindings = request.agent_context.private_fact_bindings
        delivery = build_model_turn_delivery(request.agent_context, include_images=False)

        admitted = binder.action_request(
            request,
            (tool,),
            delivery,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )

        payload = json.loads(admitted.messages[1].content)
        observation = payload["observation"]
        assert "projection=page_map" in observation
        assert "recovery=open_region/find_content/find_actions" in observation
        assert "recovery=none" not in observation
        assert "[E1]" in observation
        assert request.agent_context.actor_world == before_actor_world
        assert request.agent_context.private_fact_bindings == before_bindings
        assert admitted.breakdown.admission_action == "admitted"
        assert admitted.breakdown.delivery_projection == "page_map"
        assert admitted.breakdown.prefit_estimated_total_tokens == admitted.breakdown.estimated_total_tokens

    asyncio.run(scenario())


def test_tool_schema_refs_do_not_expand_all_regions_and_direct_tools_match_delivery() -> None:
    async def scenario() -> None:
        request, _catalog, _delivery = await _request()
        total = 240
        roots = tuple(
            ActorWorldNodeView(f"E{index}", "button", f"Button {index}", {"enabled": True}, source_refs=("S1",))
            for index in range(1, total + 1)
        )
        large_context = replace(
            request.agent_context,
            actor_world=ActorWorldSnapshot(
                (ActorWorldDocumentView("S1", "structural", roots, len(roots), len(roots), False),),
                (
                    ActorWorldSourceView(
                        "S1",
                        "structural",
                        "structural",
                        "current",
                        "complete",
                        "complete",
                        "not_available",
                    ),
                ),
                (),
                (),
                BoundedSection((), 0, False),
                (),
                (),
                (),
            ),
            grounding=AgentGroundingIndexView(
                tuple(
                    AgentGroundingEntityView(f"E{index}", "button", f"Button {index}", verbs=("activate",))
                    for index in range(1, total + 1)
                ),
                {f"target:{index}": f"E{index}" for index in range(1, total + 1)},
            ),
            region_index=WorldDeliveryIndex(
                request.agent_context.current_observation.observation_id,
                tuple(
                    WorldRegion(
                        f"region:many:{index + 1}-{index + 12}",
                        f"R{index // 12 + 1}",
                        "S1",
                        f"targets:{index + 1}-{index + 12}",
                        tuple(f"target:{target}" for target in range(index + 1, index + 13)),
                        (),
                        f"button items {index + 1}-{index + 12}",
                        "region",
                        {"targets": 12, "facts": 0, "actions": 12},
                        "complete",
                    )
                    for index in range(0, total, 12)
                ),
            ),
        )
        request = ModelDecisionRequest(request.request_id, large_context)
        broad_tool = ToolSpec(
            "activate",
            "Activate one current target.",
            {
                "type": "object",
                "properties": {"target": {"type": "string", "pattern": r"^E[1-9][0-9]{0,2}$"}},
                "required": ["target"],
            },
        )
        binder = GroundedPolicyContextBinder(
            request_budget=ModelRequestBudget(
                soft_target_tokens=16_000,
                model_context_window=200_000,
                max_output_tokens=1,
                protocol_reserve_tokens=1,
                safety_margin_tokens=1,
                admission_limit=100_000,
            )
        )
        delivery = build_model_turn_delivery(request.agent_context, include_images=False)

        admitted = binder.action_request(
            request,
            (broad_tool,),
            delivery,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )

        payload = json.loads(admitted.messages[1].content)
        observation = payload["observation"]
        delivered_refs = set(re.findall(r"\bE[1-9][0-9]*\b", observation))
        target_schema = admitted.tools[0].input_schema["properties"]["target"]
        assert admitted.breakdown.delivery_projection == "page_map"
        assert admitted.breakdown.expanded_region_count < len(large_context.region_index.regions)
        assert target_schema["pattern"] == r"^E[1-9][0-9]{0,2}$"
        assert 0 < len(delivered_refs) < total
        assert admitted.breakdown.folded_region_count > 0

    asyncio.run(scenario())


def test_page_map_remains_default_when_full_projection_is_smaller() -> None:
    async def scenario() -> None:
        request, _catalog, _delivery = await _request()
        context = replace(
            request.agent_context,
            region_index=WorldDeliveryIndex(
                request.agent_context.current_observation.observation_id,
                tuple(
                    WorldRegion(
                        f"region:oversized:{index}",
                        f"R{index}",
                        "S1",
                        f"synthetic:{index}",
                        ("shared-toggle",) if index == 1 else (),
                        (),
                        "oversized directory entry " + ("x" * 240),
                        "region",
                        {"targets": 1 if index == 1 else 0, "facts": 0, "actions": 1 if index == 1 else 0},
                        "complete",
                    )
                    for index in range(1, 90)
                ),
            ),
        )
        request = ModelDecisionRequest(request.request_id, context)
        tool = ToolSpec(
            "activate_target",
            "Activate one current target.",
            {
                "type": "object",
                "properties": {"target": {"type": "string", "enum": ["E1"]}},
                "required": ["target"],
            },
        )
        binder = GroundedPolicyContextBinder(
            request_budget=ModelRequestBudget(
                soft_target_tokens=1,
                model_context_window=200_000,
                max_output_tokens=1,
                protocol_reserve_tokens=1,
                safety_margin_tokens=1,
                admission_limit=100_000,
            )
        )
        delivery = build_model_turn_delivery(request.agent_context, include_images=False)

        admitted = binder.action_request(
            request,
            (tool,),
            delivery,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )

        payload = json.loads(admitted.messages[1].content)
        assert "projection=page_map" in payload["observation"]
        assert admitted.breakdown.delivery_projection == "page_map"
        assert admitted.breakdown.full_candidate_tokens == 0
        assert admitted.breakdown.lens_candidate_tokens == admitted.breakdown.estimated_total_tokens

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
        request, _catalog, _delivery = await _request()
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


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big")


def test_schema_error_has_no_second_action_policy_request() -> None:
    async def scenario() -> None:
        request, _catalog, _delivery = await _request()
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

        assert result.failure is None
        assert result.output is not None
        assert port.calls == 1
        breakdowns = result.diagnostics["request_breakdowns"]
        assert [item["phase"] for item in breakdowns] == ["initial"]
        assert breakdowns[0]["repair_tokens"] == 0

    asyncio.run(scenario())
