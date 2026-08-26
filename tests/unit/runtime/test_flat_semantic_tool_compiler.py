from __future__ import annotations

import itertools
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.compact_world_renderer import DeliveryManifest
from affordance_runtime.agent.context.contracts import AgentActionOptionView, AgentDestinationView
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_compiler import GroundedToolCompiler, SelectorMode
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
    RegisteredGroundedTool,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from tests.support.model_delivery import resolve_catalog_call

_CONTEXT = "context:" + "a" * 64


def _empty_schema() -> dict[str, object]:
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def _text_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }


def _select_schema(*values: str) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"value": {"type": "string", "enum": list(values)}},
        "required": ["value"],
        "additionalProperties": False,
    }


def _destination(identity: str, ref: str, *, context_id: str = _CONTEXT) -> AgentDestinationView:
    return AgentDestinationView(
        identity,
        identity,
        ref,
        {"role": "dropzone", "label": identity},
        False,
        context_id,
    )


def _candidate(
    index: int,
    *,
    operation: str = "activate",
    schema: dict[str, object] | None = None,
    ref: str | None = None,
    state: dict[str, object] | None = None,
    context_id: str = _CONTEXT,
    mode: str = "forbidden",
    destinations: tuple[AgentDestinationView, ...] = (),
    subject_kind: str = "entity",
    target_role: str = "button",
) -> AgentActionOptionView:
    return AgentActionOptionView(
        action_id=f"action:{index}",
        semantic_action=operation,
        target_id=f"entity:{index}",
        target_label=f"Target {index}",
        destination_required=mode == "required",
        destinations=BoundedSection(destinations, len(destinations), False),
        parameter_schema=schema or _empty_schema(),
        description="current action",
        semantic_effects=("external_ui_interaction",),
        risk="low",
        observation_barrier=True,
        effect_category="interaction",
        operation=operation,
        target_ref=ref or f"E{index}",
        target_semantics={"role": target_role, "label": f"Target {index}", "state": state or {}},
        target_role=target_role,
        target_state=state or {},
        target_marked=False,
        destination_mode=mode,
        grounding_context_id=context_id,
        subject_kind=subject_kind,
    )


def _compile(*options: AgentActionOptionView):
    return GroundedToolCompiler().compile(tuple(options), context_id=_CONTEXT)


def _catalog(tool) -> GroundedToolCatalog:
    return GroundedToolCatalog(
        "grounded-catalog:" + "b" * 32,
        _CONTEXT,
        "delivery:" + "d" * 64,
        DeliveryManifest(tuple(f"E{index}" for index in range(1, 65))),
        WorldDeliveryIndex("world:test"),
        (RegisteredGroundedTool(tool.public_spec, tool),),
        1,
    )


def _branches(tool) -> tuple[dict[str, object], ...]:
    schema = tool.public_spec.input_schema
    return tuple(schema["oneOf"]) if "oneOf" in schema else (schema,)


def test_single_target_uses_stable_operation_and_explicit_target() -> None:
    tool = _compile(_candidate(1))[0]

    assert tool.public_spec.name == "activate"
    assert tool.selector_mode is SelectorMode.CURRENT_TARGET
    assert tool.public_spec.input_schema["required"] == ("target",)
    assert tool.public_spec.input_schema["properties"]["target"] == {
        "type": "string",
        "description": "current executable E-ref",
        "pattern": "^(E)([1-9][0-9]*)$",
    }


def test_unique_browser_context_operation_uses_business_parameters_without_grounding_ref() -> None:
    goto_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2048,
                "pattern": "^https?://.+",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }
    tool = _compile(
        _candidate(
            1,
            operation="goto",
            schema=goto_schema,
            subject_kind="browser_context",
            target_role="browser_context",
        )
    )[0]

    assert tool.selector_mode is SelectorMode.CURRENT_BROWSER_CONTEXT
    assert tool.selector_fields == ()
    assert tool.public_spec.input_schema["required"] == ("url",)
    assert "target" not in tool.public_spec.input_schema["properties"]
    outcome = resolve_catalog_call(
        _catalog(tool),
        ToolCall("goto", {"url": "https://example.test/docs"}),
        expected_context_id=_CONTEXT,
    )
    assert outcome.decision.action_id == "action:1"
    assert outcome.decision.parameters == {"url": "https://example.test/docs"}


def test_browser_context_operation_rejects_ambiguous_current_owner() -> None:
    with pytest.raises(GroundedToolResolutionError) as failure:
        _compile(
            _candidate(
                1,
                operation="go_back",
                subject_kind="browser_context",
                target_role="browser_context",
            ),
            _candidate(
                2,
                operation="go_back",
                subject_kind="browser_context",
                target_role="browser_context",
            ),
        )

    assert failure.value.code is GroundedToolResolutionCode.CATALOG_INVALID


def test_one_stable_tool_contains_all_current_targets() -> None:
    tools = _compile(_candidate(1), _candidate(2), _candidate(3))

    assert len(tools) == 1
    assert tools[0].public_spec.name == "activate"
    assert "enum" not in tools[0].public_spec.input_schema["properties"]["target"]
    assert {
        item.selector_values["target"] for item in tools[0].private_resolutions
    } == {"E1", "E2", "E3"}
    assert len(tools[0].private_resolutions) == 3


@given(st.integers(min_value=1, max_value=64))
def test_unary_selector_schema_is_stable_while_private_resolution_is_closed(count: int) -> None:
    tool = _compile(*(_candidate(index) for index in range(1, count + 1)))[0]
    catalog = _catalog(tool)
    offered = tuple(item.selector_values["target"] for item in tool.private_resolutions)

    assert validate_value(
        {"target": "E10000"},
        tool.public_spec.input_schema,
        path="command",
    ) is None
    assert len(set(offered)) == len(offered)
    for resolution in tool.private_resolutions:
        target = resolution.selector_values["target"]
        outcome = resolve_catalog_call(
            catalog,
            ToolCall("activate", {"target": target}),
            expected_context_id=_CONTEXT,
        )
        assert outcome.decision.action_id == resolution.action_id


def test_tool_name_and_shape_do_not_depend_on_state_or_candidate_order() -> None:
    candidates = (
        _candidate(1, state={"color": "blue", "selected": False}),
        _candidate(2, state={"color": "red", "selected": True}),
        _candidate(3, state={"semantic_grid_coordinate": (-1, 2)}),
    )
    signatures = set()
    for permutation in itertools.permutations(candidates):
        tool = _compile(*permutation)[0]
        signatures.add(
            (
                tool.public_spec.name,
                json.dumps(to_json_compatible(tool.public_spec.input_schema), sort_keys=True),
            )
        )

    assert len(signatures) == 1


def test_multiple_operations_are_registry_names_without_suffixes() -> None:
    tools = _compile(
        _candidate(1),
        _candidate(2, operation="type_text", schema=_text_schema()),
    )

    assert tuple(tool.public_spec.name for tool in tools) == ("activate", "type_text")
    assert tuple(tools[1].public_spec.input_schema["properties"]) == ("target", "text")


def test_business_enums_merge_publicly_but_remain_exact_per_target() -> None:
    tool = _compile(
        _candidate(1, operation="select_option", schema=_select_schema("A", "B")),
        _candidate(2, operation="select_option", schema=_select_schema("B", "C")),
    )[0]
    catalog = _catalog(tool)

    assert tool.public_spec.input_schema["properties"]["value"] == {"type": "string"}
    accepted = resolve_catalog_call(
        catalog,
        ToolCall("select_option", {"target": "E2", "value": "C"}),
        expected_context_id=_CONTEXT,
    )
    assert isinstance(accepted, GroundedActionResolution)
    assert accepted.decision.action_id == "action:2"
    assert accepted.decision.parameters == {"value": "C"}
    assert accepted.decision.expected_outcome == ""
    with pytest.raises(GroundedToolResolutionError) as failure:
        resolve_catalog_call(
            catalog,
            ToolCall("select_option", {"target": "E1", "value": "C"}),
            expected_context_id=_CONTEXT,
        )
    assert failure.value.code is GroundedToolResolutionCode.INVALID_ARGUMENTS


def test_required_destination_uses_source_and_destination_and_resolves_exact_pair() -> None:
    left = _destination("left", "E8")
    right = _destination("right", "E9")
    tool = _compile(
        _candidate(1, operation="drag_to", mode="required", destinations=(left,)),
        _candidate(2, operation="drag_to", mode="required", destinations=(right,)),
    )[0]
    catalog = _catalog(tool)

    assert tool.selector_mode is SelectorMode.CURRENT_ENDPOINTS
    pairs = {
        (
            item.selector_values["source"],
            item.selector_values["destination"],
        )
        for item in tool.private_resolutions
    }
    assert pairs == {("E1", "E8"), ("E2", "E9")}
    assert tuple(tool.public_spec.input_schema["required"]) == ("source", "destination")
    outcome = resolve_catalog_call(
        catalog,
        ToolCall("drag_to", {"source": "E2", "destination": "E9"}),
        expected_context_id=_CONTEXT,
    )
    assert outcome.decision.action_id == "action:2"
    assert outcome.decision.destination_id == "right"
    with pytest.raises(GroundedToolResolutionError):
        resolve_catalog_call(
            catalog,
            ToolCall("drag_to", {"source": "E1", "destination": "E9"}),
            expected_context_id=_CONTEXT,
        )


@given(
    st.lists(
        st.sets(st.integers(min_value=20, max_value=24), min_size=1, max_size=5),
        min_size=1,
        max_size=5,
    )
)
def test_factorized_sparse_relation_matches_rows_and_unique_resolver(
    adjacency: list[set[int]],
) -> None:
    options = tuple(
        _candidate(
            source,
            operation="drag_to",
            mode="required",
            destinations=tuple(
                _destination(f"destination:{destination}", f"E{destination}")
                for destination in sorted(destinations)
            ),
        )
        for source, destinations in enumerate(adjacency, 1)
    )
    tool = _compile(*options)[0]
    catalog = _catalog(tool)
    expected = {
        (f"E{source}", f"E{destination}")
        for source, destinations in enumerate(adjacency, 1)
        for destination in destinations
    }
    accepted: set[tuple[str, str]] = set()
    for source in range(1, len(adjacency) + 1):
        for destination in range(20, 25):
            arguments = {"source": f"E{source}", "destination": f"E{destination}"}
            schema_accepts = True
            try:
                validate_value(arguments, tool.public_spec.input_schema, path="command")
            except ValueError:
                schema_accepts = False
            resolves = True
            try:
                resolve_catalog_call(
                    catalog,
                    ToolCall("drag_to", arguments),
                    expected_context_id=_CONTEXT,
                )
            except GroundedToolResolutionError:
                resolves = False
            assert schema_accepts
            assert resolves == ((f"E{source}", f"E{destination}") in expected)
            if resolves:
                accepted.add((f"E{source}", f"E{destination}"))
    assert accepted == expected


def test_invalid_or_stale_reference_never_resolves() -> None:
    tool = _compile(_candidate(1), _candidate(2))[0]
    catalog = _catalog(tool)
    with pytest.raises(GroundedToolResolutionError) as invalid:
        resolve_catalog_call(
            catalog,
            ToolCall("activate", {"target": "E99"}),
            expected_context_id=_CONTEXT,
        )
    assert invalid.value.code is GroundedToolResolutionCode.GROUNDING_GAP
    with pytest.raises(GroundedToolResolutionError) as stale:
        resolve_catalog_call(
            catalog,
            ToolCall("activate", {"target": "E1"}),
            expected_context_id="context:" + "d" * 64,
        )
    assert stale.value.code is GroundedToolResolutionCode.STALE_CATALOG


def test_public_refs_need_current_context_not_visual_marking() -> None:
    assert _compile(_candidate(1))[0].public_spec.name == "activate"
    with pytest.raises(GroundedToolResolutionError) as failure:
        _compile(_candidate(1, context_id="context:" + "c" * 64))
    assert failure.value.code is GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE


def test_duplicate_public_binding_fails_closed() -> None:
    with pytest.raises(GroundedToolResolutionError) as failure:
        _compile(_candidate(1, ref="E1"), _candidate(2, ref="E1"))
    assert failure.value.code is GroundedToolResolutionCode.CATALOG_INVALID


def test_optional_and_empty_required_destination_fail_closed() -> None:
    with pytest.raises(GroundedToolResolutionError) as optional:
        _compile(_candidate(1, operation="drag_to", mode="optional"))
    assert optional.value.code is GroundedToolResolutionCode.UNSUPPORTED_DESTINATION_MODE
    with pytest.raises(GroundedToolResolutionError) as unavailable:
        _compile(_candidate(1, operation="drag_to", mode="required"))
    assert unavailable.value.code is GroundedToolResolutionCode.DESTINATION_UNAVAILABLE


def test_business_parameter_cannot_claim_public_target_owner() -> None:
    schema = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
        "additionalProperties": False,
    }
    with pytest.raises(GroundedToolResolutionError) as failure:
        _compile(_candidate(1, schema=schema))
    assert failure.value.code is GroundedToolResolutionCode.CATALOG_INVALID
