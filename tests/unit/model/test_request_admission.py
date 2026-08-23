from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.budgets import ModelRequestBudget
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.model.policy.canonical_provider_envelope import (
    CanonicalMediaRecord,
    CanonicalOutputContract,
    CanonicalProviderEnvelope,
    CanonicalProviderEnvelopeBinder,
    CanonicalProviderIdentity,
    _envelope_id,
)
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.model.policy.grounded_tool_contracts import RegisteredGroundedTool
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyCallProfile,
    ActionPolicyInvocationPhase,
    ActionPolicyInvocationTrigger,
)
from affordance_runtime.model.policy.request_admission import (
    AdmittedProviderEnvelope,
    RejectedProviderEnvelope,
    RequestAdmission,
    estimate_canonical_envelope,
)
from tests.support.agent.core_loop_support import SharedTaskEvaluator, _task, _world


class _EquivalentResolver:
    def resolve(self, arguments, context_id: str, tool_call_id: str):
        raise AssertionError((arguments, context_id, tool_call_id))


async def _bound_envelope() -> CanonicalProviderEnvelope:
    task = _task()
    world = _world("request-admission", False)
    evaluation = await SharedTaskEvaluator().evaluate(task, world)
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        evaluation,
    )
    request = ModelDecisionRequest("request:test", context)
    delivery = build_model_turn_delivery(context, include_images=False)
    catalog = compile_grounded_action_catalog(context, delivery)
    return CanonicalProviderEnvelopeBinder().bind(
        request,
        delivery,
        catalog,
        identity=CanonicalProviderIdentity("fixture", "recording", "fixture.invalid", "text_only"),
        call_profile=_profile(),
        output_token_reserve=4_096,
    )


def _profile(*, max_output_tokens: int = 1024) -> ActionPolicyCallProfile:
    return ActionPolicyCallProfile(
        ActionPolicyInvocationPhase.ORDINARY,
        ActionPolicyInvocationTrigger.ORDINARY,
        max_output_tokens,
        "disabled",
    )


def _replace_physical(envelope: CanonicalProviderEnvelope, **changes) -> CanonicalProviderEnvelope:
    values = {name: getattr(envelope, name) for name in envelope.__dataclass_fields__ if name != "envelope_id"}
    values.update(changes)
    provisional = CanonicalProviderEnvelope.__new__(CanonicalProviderEnvelope)
    for key, value in values.items():
        object.__setattr__(provisional, key, value)
    return CanonicalProviderEnvelope(envelope_id=_envelope_id(provisional.physical_content()), **values)


def _budget(limit: int) -> ModelRequestBudget:
    return ModelRequestBudget(
        soft_target_tokens=max(1, limit),
        model_context_window=max(1, limit + 10_000),
        max_output_tokens=0,
        protocol_reserve_tokens=0,
        safety_margin_tokens=0,
        admission_limit=max(1, limit),
    )


def _png(width: int = 20, height: int = 20, *, padding: int = 0) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00" * 8
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"x" * padding
    )


def _media(data: bytes) -> CanonicalMediaRecord:
    return CanonicalMediaRecord(
        data,
        "image/png",
        hashlib.sha256(data).hexdigest(),
        (20, 20),
        "raw",
        (),
        (),
        "viewport:private",
    )


def test_complete_envelope_count_is_deterministic_and_covers_every_physical_component() -> None:
    async def scenario() -> None:
        envelope = await _bound_envelope()
        first = estimate_canonical_envelope(envelope)
        second = estimate_canonical_envelope(envelope)

        assert first == second
        assert first.system_tokens > 0
        assert first.actor_world_tokens > 0
        assert first.tool_schema_tokens > 0
        assert first.model_settings_tokens > 0
        assert first.output_contract_tokens > 0
        assert first.image_estimated_tokens == 0
        assert first.output_reserve_tokens == envelope.output_token_reserve
        assert first.complete_request_tokens == first.estimated_total_tokens + first.output_reserve_tokens
        assert first.counting_method == envelope.counting_method

    asyncio.run(scenario())


def test_admission_exact_fit_returns_the_same_immutable_envelope_and_one_unit_over_rejects() -> None:
    async def scenario() -> None:
        envelope = await _bound_envelope()
        total = estimate_canonical_envelope(envelope, budget=_budget(1_000_000)).complete_request_tokens

        admitted = RequestAdmission().admit(envelope, budget=_budget(total))
        rejected = RequestAdmission().admit(envelope, budget=_budget(total - 1))

        assert isinstance(admitted, AdmittedProviderEnvelope)
        assert admitted.envelope is envelope
        assert admitted.token_breakdown.complete_request_tokens == total
        assert isinstance(rejected, RejectedProviderEnvelope)
        assert rejected.reason == "context_capacity"
        assert rejected.token_breakdown.complete_request_tokens == total
        assert rejected.counting_method == envelope.counting_method

    asyncio.run(scenario())


def test_schema_media_settings_and_output_reserve_monotonically_change_complete_cost() -> None:
    async def scenario() -> None:
        base = await _bound_envelope()
        base_cost = estimate_canonical_envelope(base).complete_request_tokens

        first = base.function_tools[0]
        larger_tool = replace(
            first,
            parameters_json_schema={
                **dict(first.parameters_json_schema),
                "description": "schema expansion " + "x" * 900,
            },
        )
        with_tool = _replace_physical(base, function_tools=(larger_tool, *base.function_tools[1:]))
        with_media = _replace_physical(base, media=(_media(_png(padding=64 * 1024)),))
        with_settings = _replace_physical(
            base,
            model_settings={**dict(base.model_settings), "seed": 123456789},
        )
        with_reserve = _replace_physical(base, output_token_reserve=base.output_token_reserve + 17)

        assert estimate_canonical_envelope(with_tool).complete_request_tokens > base_cost
        assert estimate_canonical_envelope(with_media).complete_request_tokens > base_cost
        assert estimate_canonical_envelope(with_settings).complete_request_tokens > base_cost
        assert estimate_canonical_envelope(with_reserve).complete_request_tokens == base_cost + 17

    asyncio.run(scenario())


def test_media_byte_growth_changes_cost_even_when_dimensions_are_equal() -> None:
    async def scenario() -> None:
        base = await _bound_envelope()
        small = _replace_physical(base, media=(_media(_png(padding=1)),))
        large = _replace_physical(base, media=(_media(_png(padding=128 * 1024)),))

        small_cost = estimate_canonical_envelope(small)
        large_cost = estimate_canonical_envelope(large)
        assert large_cost.image_estimated_tokens > small_cost.image_estimated_tokens
        assert large_cost.media_bytes > small_cost.media_bytes

    asyncio.run(scenario())


def test_media_bytes_mime_digest_dimensions_and_marks_each_participate_in_identity() -> None:
    async def scenario() -> None:
        base = await _bound_envelope()
        data = _png()
        record = _media(data)
        physical = dict(base.physical_content())
        message = {
            "kind": "request",
            "parts": (
                {"part_kind": "user-prompt", "content": base.user_text},
                {
                    "part_kind": "binary",
                    "mime_type": record.mime_type,
                    "digest": record.digest,
                    "dimensions": record.dimensions,
                    "variant": record.variant,
                    "marks": record.marks,
                    "operand_roles": record.operand_roles,
                },
            ),
        }
        original = {**physical, "messages": (message,)}
        binary = message["parts"][1]
        variants = (
            {**binary, "digest": "f" * 64},
            {**binary, "mime_type": "image/jpeg"},
            {**binary, "dimensions": (21, 20)},
            {**binary, "marks": (("E1", (1, 2, 3, 4)),)},
        )

        assert all(
            _envelope_id(
                {
                    **physical,
                    "messages": ({**message, "parts": (message["parts"][0], variant)},),
                }
            )
            != _envelope_id(original)
            for variant in variants
        )

    asyncio.run(scenario())


def test_envelope_identity_covers_every_model_visible_field_and_excludes_runtime_lineage() -> None:
    async def scenario() -> None:
        base = await _bound_envelope()
        physical = dict(base.physical_content())

        variants = []
        variants.append({**physical, "instructions": (base.instructions[0] + " changed",)})
        messages = list(physical["messages"])
        messages[-1] = {
            **messages[-1],
            "parts": ({"part_kind": "user-prompt", "content": base.user_text + " changed"},),
        }
        variants.append({**physical, "messages": tuple(messages)})
        tools = list(physical["tools"])
        tools[0] = {**tools[0], "parameters_json_schema": {"type": "object", "properties": {}}}
        variants.append({**physical, "tools": tuple(tools)})
        tools[0] = {**physical["tools"][0], "strict": False}
        variants.append({**physical, "tools": tuple(tools)})
        variants.append({**physical, "tools": tuple(reversed(physical["tools"]))})
        variants.append({**physical, "model_settings": {**physical["model_settings"], "temperature": 0.25}})
        variants.append(
            {
                **physical,
                "output_contract": {**physical["output_contract"], "allow_text_output": False},
            }
        )
        variants.append({**physical, "output_token_reserve": base.output_token_reserve + 1})
        variants.append(
            {
                **physical,
                "messages": (*physical["messages"], {"kind": "request", "parts": ({"part_kind": "binary", "mime_type": "image/png", "digest": "a" * 64},)}),
            }
        )

        assert all(_envelope_id(item) != base.envelope_id for item in variants)
        assert "context_id" not in physical
        assert "delivery_id" not in physical
        assert "attempt_phase" not in physical
        assert "catalog" not in physical

        replacement_tools = tuple(
            RegisteredGroundedTool(item.spec, _EquivalentResolver()) for item in base.catalog.tools
        )
        replacement_catalog = replace(base.catalog, tools=replacement_tools)
        rebound = _replace_physical(base, catalog=replacement_catalog, attempt_phase="trace-only-change")
        assert rebound.envelope_id == base.envelope_id

    asyncio.run(scenario())


def test_tool_order_schema_strictness_and_output_contract_are_closed_in_envelope() -> None:
    async def scenario() -> None:
        envelope = await _bound_envelope()

        assert tuple(item.name for item in envelope.function_tools) == tuple(
            item.spec.name for item in envelope.catalog.tools
        )
        assert all(item.strict is True for item in envelope.function_tools)
        assert all(
            item.parameters_json_schema == catalog_item.spec.input_schema
            for item, catalog_item in zip(envelope.function_tools, envelope.catalog.tools, strict=True)
        )
        assert envelope.output_contract == CanonicalOutputContract()
        assert envelope.model_settings["parallel_tool_calls"] is False
        assert envelope.media == ()

    asyncio.run(scenario())


def test_private_resolver_value_and_length_do_not_change_public_cost_or_identity() -> None:
    async def scenario() -> None:
        base = await _bound_envelope()
        replacement_catalog = replace(
            base.catalog,
            tools=tuple(RegisteredGroundedTool(item.spec, _EquivalentResolver()) for item in base.catalog.tools),
        )
        replacement = _replace_physical(base, catalog=replacement_catalog)

        assert replacement.envelope_id == base.envelope_id
        assert estimate_canonical_envelope(replacement) == estimate_canonical_envelope(base)

    asyncio.run(scenario())


def test_multiple_media_and_large_history_are_counted_without_provider_access() -> None:
    async def scenario() -> None:
        base = await _bound_envelope()
        expanded = _replace_physical(
            base,
            history_messages=tuple({"kind": "request", "content": "history " + "x" * 1000} for _ in range(8)),
            media=(_media(_png(padding=100)), _media(_png(padding=200))),
        )

        breakdown = estimate_canonical_envelope(expanded)
        assert breakdown.history_tokens > 0
        assert breakdown.image_estimated_tokens > 0
        assert breakdown.media_bytes == sum(len(item.data) for item in expanded.media)

    asyncio.run(scenario())
