from __future__ import annotations

import pytest

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.contracts import AgentActionOptionView, AgentDestinationView
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_catalog import resolve_grounded_tool_call
from affordance_runtime.model.policy.grounded_tool_compiler import (
    GroundedToolCompiler,
    SelectorMode,
    recursive_common_semantic_skeleton,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.providers.tool_transport_contracts import ToolCall

_CONTEXT = "context:" + "a" * 64


def _destination(
    identity: str,
    ref: str,
    semantics: dict[str, object],
    *,
    rendered: bool = True,
    context_id: str = _CONTEXT,
) -> AgentDestinationView:
    return AgentDestinationView(identity, str(semantics.get("label", "")), ref, semantics, rendered, context_id)


def _candidate(
    index: int,
    semantics: dict[str, object],
    *,
    operation: str = "activate",
    schema: dict[str, object] | None = None,
    ref: str | None = None,
    rendered: bool = True,
    context_id: str = _CONTEXT,
    mode: str = "forbidden",
    destinations: tuple[AgentDestinationView, ...] = (),
) -> AgentActionOptionView:
    schema = schema or {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    return AgentActionOptionView(
        action_id=f"action:{index}",
        semantic_action=operation,
        target_id=f"entity:{index}",
        target_label=str(semantics.get("label", "")),
        destination_required=mode == "required",
        destinations=BoundedSection(destinations, len(destinations), False),
        parameter_schema=schema,
        description="current action",
        semantic_effects=("external_ui_interaction",),
        risk="low",
        observation_barrier=True,
        effect_category="interaction",
        operation=operation,
        target_ref=ref or f"E{index}",
        target_semantics=semantics,
        target_role=str(semantics["role"]),
        target_state=semantics.get("state", {}),
        target_marked=rendered,
        destination_mode=mode,
        grounding_context_id=context_id,
    )


def _compile(*options: AgentActionOptionView):
    return GroundedToolCompiler().compile(tuple(options), context_id=_CONTEXT)


def _catalog(tool) -> GroundedToolCatalog:
    return GroundedToolCatalog("grounded-catalog:" + "b" * 32, _CONTEXT, (tool.public_spec,), (tool,), 1)


def test_singleton_emits_no_target_selector() -> None:
    tool = _compile(_candidate(1, {"role": "button", "label": "Save"}))[0]
    assert tool.selector_mode is SelectorMode.CONSTANT_TARGET
    assert tool.public_spec.name == "activate"
    assert tool.public_spec.input_schema["properties"] == {}


def test_identical_buttons_compress_to_within_label() -> None:
    tools = _compile(
        _candidate(1, {"role": "button", "label": "加入购物车", "within": {"role": "product", "label": "MacBook Air"}}),
        _candidate(2, {"role": "button", "label": "加入购物车", "within": {"role": "product", "label": "MacBook Pro"}}),
    )
    schema = tools[0].public_spec.input_schema
    assert schema["required"] == ("within_label",)
    assert schema["properties"]["within_label"]["enum"] == ("MacBook Air", "MacBook Pro")


def test_semantic_grid_coordinate_never_exposes_eref() -> None:
    tool = _compile(
        _candidate(1, {"role": "cell", "label": "point", "state": {"semantic_grid_coordinate": (-1, 1)}}, ref="E31"),
        _candidate(2, {"role": "cell", "label": "point", "state": {"semantic_grid_coordinate": (1, -2)}}, ref="E38"),
    )[0]
    public = str(to_json_compatible(tool.public_spec.input_schema))
    assert tool.public_spec.input_schema["properties"]["semantic_grid_coordinate"]["enum"] == ("(-1,1)", "(1,-2)")
    assert "E31" not in public and "E38" not in public


def test_minimal_facet_tie_break_is_deterministic() -> None:
    first = _candidate(1, {"role": "button", "label": "Same", "state": {"alpha": "A", "beta": "A"}})
    second = _candidate(2, {"role": "button", "label": "Same", "state": {"alpha": "B", "beta": "B"}})
    expected = _compile(first, second)[0].public_spec.input_schema
    assert tuple(expected["properties"]) == ("alpha",)
    assert _compile(second, first)[0].public_spec.input_schema == expected


def test_recursive_intersection_distinguishes_absent_null_list_and_relation() -> None:
    common = recursive_common_semantic_skeleton((
        {"role": "item", "nullable": None, "tags": ["a", "b"], "relations": {"member_of": "list"}, "only_first": None},
        {"role": "item", "nullable": None, "tags": ["a", "b"], "relations": {"member_of": "list"}},
    ))
    assert common == {
        "nullable": None,
        "relations": {"member_of": "list"},
        "role": "item",
        "tags": ["a", "b"],
    }


def test_multi_field_cartesian_emits_independent_fields() -> None:
    options = tuple(
        _candidate(index, {"role": "button", "label": "Choose", "state": {"color": color, "size": size}})
        for index, (color, size) in enumerate((("blue", "S"), ("blue", "L"), ("red", "S"), ("red", "L")), 1)
    )
    tool = _compile(*options)[0]
    assert tool.selector_mode is SelectorMode.SEMANTIC_FIELDS
    assert set(tool.public_spec.input_schema["properties"]) == {"color", "size"}


def test_multi_field_non_cartesian_emits_atomic_real_tuple_choice() -> None:
    options = tuple(
        _candidate(index, {"role": "button", "label": "Choose", "state": {"color": color, "size": size}})
        for index, (color, size) in enumerate((("blue", "S"), ("blue", "L"), ("red", "L")), 1)
    )
    tool = _compile(*options)[0]
    assert tool.selector_mode is SelectorMode.ATOMIC_SEMANTIC_CHOICE
    assert tuple(tool.public_spec.input_schema["properties"]) == ("choice",)
    assert len(tool.public_spec.input_schema["properties"]["choice"]["enum"]) == 3


def test_required_destination_rows_and_constant_elision() -> None:
    destination = _destination("entity:d1", "E8", {"role": "dropzone", "label": "Done"})
    tool = _compile(_candidate(1, {"role": "item", "label": "Card"}, mode="required", destinations=(destination,)))[0]
    assert tool.public_spec.input_schema["properties"] == {}
    assert tool.private_resolutions[0].destination_id == "entity:d1"


def test_one_source_many_destinations_emits_only_destination_difference() -> None:
    destinations = (
        _destination("entity:d1", "E8", {"role": "dropzone", "label": "Left"}),
        _destination("entity:d2", "E9", {"role": "dropzone", "label": "Right"}),
    )
    tool = _compile(_candidate(1, {"role": "item", "label": "Card"}, mode="required", destinations=destinations))[0]
    assert tuple(tool.public_spec.input_schema["properties"]) == ("destination_label",)


def test_many_sources_one_destination_emits_only_source_difference() -> None:
    destination = _destination("entity:d1", "E8", {"role": "dropzone", "label": "Done"})
    tool = _compile(
        _candidate(1, {"role": "item", "label": "Card", "state": {"ordinal": 1}}, mode="required", destinations=(destination,)),
        _candidate(2, {"role": "item", "label": "Card", "state": {"ordinal": 2}}, mode="required", destinations=(destination,)),
    )[0]
    assert tuple(tool.public_spec.input_schema["properties"]) == ("source_ordinal",)


def test_sparse_source_destination_pairs_are_atomic() -> None:
    d1 = _destination("entity:d1", "E7", {"role": "dropzone", "label": "One"})
    d2 = _destination("entity:d2", "E8", {"role": "dropzone", "label": "Two"})
    d3 = _destination("entity:d3", "E9", {"role": "dropzone", "label": "Three"})
    tool = _compile(
        _candidate(1, {"role": "item", "label": "Card", "state": {"ordinal": 1}}, mode="required", destinations=(d1, d2)),
        _candidate(2, {"role": "item", "label": "Card", "state": {"ordinal": 2}}, mode="required", destinations=(d2, d3)),
    )[0]
    assert tool.selector_mode is SelectorMode.ATOMIC_SEMANTIC_CHOICE
    assert tuple(tool.public_spec.input_schema["properties"]) == ("choice",)


def test_complete_source_destination_product_emits_independent_semantic_fields() -> None:
    destinations = (
        _destination("entity:d1", "E8", {"role": "dropzone", "label": "Left"}),
        _destination("entity:d2", "E9", {"role": "dropzone", "label": "Right"}),
    )
    tool = _compile(
        _candidate(1, {"role": "item", "label": "Card", "state": {"ordinal": 1}}, mode="required", destinations=destinations),
        _candidate(2, {"role": "item", "label": "Card", "state": {"ordinal": 2}}, mode="required", destinations=destinations),
    )[0]
    assert tool.selector_mode is SelectorMode.SEMANTIC_FIELDS
    assert set(tool.public_spec.input_schema["properties"]) == {"source_ordinal", "destination_label"}


def test_complete_grounding_product_is_independent_but_sparse_pairs_are_atomic() -> None:
    d1 = _destination("entity:d1", "E7", {"role": "dropzone", "label": "Same"})
    d2 = _destination("entity:d2", "E8", {"role": "dropzone", "label": "Same"})
    d3 = _destination("entity:d3", "E9", {"role": "dropzone", "label": "Same"})
    complete = _compile(
        _candidate(1, {"role": "item", "label": "Same"}, mode="required", destinations=(d1, d2)),
        _candidate(2, {"role": "item", "label": "Same"}, mode="required", destinations=(d1, d2)),
    )[0]
    assert complete.selector_mode is SelectorMode.GROUNDING_FALLBACK
    assert set(complete.public_spec.input_schema["properties"]) == {
        "source_grounding_ref",
        "destination_grounding_ref",
    }

    sparse = _compile(
        _candidate(1, {"role": "item", "label": "Same"}, mode="required", destinations=(d1, d2)),
        _candidate(2, {"role": "item", "label": "Same"}, mode="required", destinations=(d2, d3)),
    )[0]
    assert sparse.selector_mode is SelectorMode.GROUNDING_FALLBACK
    assert tuple(sparse.public_spec.input_schema["properties"]) == ("grounding_pair",)
    assert len(sparse.public_spec.input_schema["properties"]["grounding_pair"]["enum"]) == 4


def test_optional_and_empty_required_destination_fail_closed() -> None:
    with pytest.raises(GroundedToolResolutionError) as optional:
        _compile(_candidate(1, {"role": "item"}, mode="optional"))
    assert optional.value.code is GroundedToolResolutionCode.UNSUPPORTED_DESTINATION_MODE
    with pytest.raises(GroundedToolResolutionError) as unavailable:
        _compile(_candidate(1, {"role": "item"}, mode="required"))
    assert unavailable.value.code is GroundedToolResolutionCode.DESTINATION_UNAVAILABLE


def test_complete_grounding_fallback_is_exact() -> None:
    tool = _compile(
        _candidate(1, {"role": "button", "label": "Same"}, ref="E1"),
        _candidate(2, {"role": "button", "label": "Same"}, ref="E2"),
    )[0]
    assert tool.selector_mode is SelectorMode.GROUNDING_FALLBACK
    assert tool.public_spec.input_schema["properties"]["grounding_ref"]["enum"] == ("E1", "E2")


@pytest.mark.parametrize(
    ("second_ref", "second_context", "second_rendered"),
    (("E1", _CONTEXT, True), ("E2", "context:" + "c" * 64, True), ("E2", _CONTEXT, False)),
)
def test_grounding_fallback_duplicate_stale_and_unrendered_fail(
    second_ref: str,
    second_context: str,
    second_rendered: bool,
) -> None:
    with pytest.raises(GroundedToolResolutionError) as failure:
        _compile(
            _candidate(1, {"role": "button", "label": "Same"}, ref="E1"),
            _candidate(2, {"role": "button", "label": "Same"}, ref=second_ref, context_id=second_context, rendered=second_rendered),
        )
    assert failure.value.code is GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE


def test_generic_business_parameter_round_trip_and_invalid_choice() -> None:
    schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "enum": ["A", "B"]},
            "count": {"type": "integer", "minimum": 1, "maximum": 3},
        },
        "required": ["text", "count"],
        "additionalProperties": False,
    }
    tool = _compile(
        _candidate(1, {"role": "textbox", "label": "Same", "state": {"ordinal": 1}}, operation="type_text", schema=schema),
        _candidate(2, {"role": "textbox", "label": "Same", "state": {"ordinal": 2}}, operation="type_text", schema=schema),
    )[0]
    catalog = _catalog(tool)
    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall(tool.public_spec.name, {"ordinal": 2, "text": "B", "count": 3}),
        expected_context_id=_CONTEXT,
    )
    assert isinstance(outcome, GroundedActionResolution)
    assert outcome.decision.parameters == {"text": "B", "count": 3}
    with pytest.raises(GroundedToolResolutionError) as invalid:
        resolve_grounded_tool_call(
            catalog,
            ToolCall(tool.public_spec.name, {"ordinal": 99, "text": "B", "count": 3}),
            expected_context_id=_CONTEXT,
        )
    assert invalid.value.code is GroundedToolResolutionCode.INVALID_ARGUMENTS


def test_selector_and_business_parameter_name_collision_fails_closed() -> None:
    schema = {
        "type": "object",
        "properties": {"within_label": {"type": "string"}},
        "required": ["within_label"],
        "additionalProperties": False,
    }
    with pytest.raises(GroundedToolResolutionError) as failure:
        _compile(
            _candidate(1, {"role": "button", "label": "Add", "within": {"label": "One"}}, schema=schema),
            _candidate(2, {"role": "button", "label": "Add", "within": {"label": "Two"}}, schema=schema),
        )
    assert failure.value.code is GroundedToolResolutionCode.CATALOG_INVALID


def test_stale_catalog_fails_before_resolution() -> None:
    tool = _compile(_candidate(1, {"role": "button", "label": "Save"}))[0]
    with pytest.raises(GroundedToolResolutionError) as failure:
        resolve_grounded_tool_call(
            _catalog(tool),
            ToolCall("activate", {}),
            expected_context_id="context:" + "d" * 64,
        )
    assert failure.value.code is GroundedToolResolutionCode.STALE_CATALOG
