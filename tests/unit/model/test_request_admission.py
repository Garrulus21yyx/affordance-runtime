from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field, replace

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent import Abort
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
from affordance_runtime.agent.context.world_region_index import WorldRegion, WorldRegionIndex
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_tool_catalog
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.grounded_tool_port_bridge import CompactJsonDecisionPort
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.pydantic_ai_bridge import (
    _intent_preservation_error,
    _repair_input_transcript,
    _representation_repair_allowed,
)
from affordance_runtime.model.policy.request_admission import ModelRequestBudget, estimate_model_request
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
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
        request, _catalog = await _request()
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
            region_index=WorldRegionIndex(
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

        admitted = binder.action_request(
            request,
            (tool,),
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )

        payload = json.loads(admitted.messages[1].content)
        observation = payload["observation"]
        assert "delivery=region_lens" in observation
        assert "recovery=inspect_world" in observation
        assert "recovery=none" not in observation
        assert "[E1]" in observation
        assert request.agent_context.actor_world == before_actor_world
        assert request.agent_context.private_fact_bindings == before_bindings
        assert admitted.breakdown.admission_action == "admitted"
        assert admitted.breakdown.delivery_projection == "region_lens"
        assert admitted.breakdown.prefit_estimated_total_tokens > admitted.breakdown.estimated_total_tokens

    asyncio.run(scenario())


def test_tool_schema_refs_do_not_expand_all_regions_and_direct_tools_match_delivery() -> None:
    async def scenario() -> None:
        request, _catalog = await _request()
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
            region_index=WorldRegionIndex(
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
                "properties": {"target": {"type": "string", "enum": [f"E{index}" for index in range(1, total + 1)]}},
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

        admitted = binder.action_request(
            request,
            (broad_tool,),
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )

        payload = json.loads(admitted.messages[1].content)
        observation = payload["observation"]
        delivered_refs = set(re.findall(r"\bE[1-9][0-9]*\b", observation))
        direct_refs = set(admitted.tools[0].input_schema["properties"]["target"]["enum"])
        assert admitted.breakdown.delivery_projection == "region_lens"
        assert admitted.breakdown.expanded_region_count < len(large_context.region_index.regions)
        assert direct_refs
        assert direct_refs <= delivered_refs
        assert len(direct_refs) < total
        assert admitted.breakdown.folded_region_count > 0

    asyncio.run(scenario())


def test_soft_target_keeps_full_projection_when_region_lens_is_larger() -> None:
    async def scenario() -> None:
        request, _catalog = await _request()
        context = replace(
            request.agent_context,
            region_index=WorldRegionIndex(
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

        admitted = binder.action_request(
            request,
            (tool,),
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )

        payload = json.loads(admitted.messages[1].content)
        assert "delivery=region_lens" not in payload["observation"]
        assert admitted.breakdown.delivery_projection == "full"
        assert admitted.breakdown.prefit_estimated_total_tokens == admitted.breakdown.estimated_total_tokens

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


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big")


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


def test_narrow_representation_repair_transcript_excludes_original_context() -> None:
    transcript = _repair_input_transcript(
        "Repair only this call. Allowed operation schema: {\"type\":\"object\"}."
    )
    encoded = json.dumps(transcript)

    assert "Repair only this call" in encoded
    assert "compact_world" not in encoded
    assert "recent_steps" not in encoded
    assert "goal_plan" not in encoded
    assert "image_url" not in encoded


def test_representation_repair_rejects_stale_grounding_and_changed_intent() -> None:
    assert not _representation_repair_allowed(
        GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    )
    assert not _representation_repair_allowed(
        GroundedToolResolutionError(GroundedToolResolutionCode.STALE_CATALOG)
    )
    assert not _representation_repair_allowed(
        GroundedToolResolutionError(GroundedToolResolutionCode.GROUNDING_GAP)
    )

    changed = _intent_preservation_error(
        ToolCall("activate", {"target": "E1", "expected_outcome": "open"}),
        ToolCall("activate", {"target": "E2", "expected_outcome": "open"}),
    )

    assert changed is not None
    assert changed.code is GroundedToolResolutionCode.REPAIR_CHANGED_INTENT
