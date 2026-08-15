from __future__ import annotations

import asyncio
import json

import pytest
from test_agent_loop import SharedTaskEvaluator, _task, _world

from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import RequestActionPage, RequestObservation, SelectAction
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.context import ContextBuilder
from affordance_runtime.model.policy.serialization import serialize_agent_context
from affordance_runtime.model.policy.tool_catalog import compile_tool_catalog, resolve_tool_call
from affordance_runtime.model.policy.tool_contracts import (
    ToolCall,
    ToolResolutionCode,
    ToolResolutionError,
)


def _context():
    observation = _world("before", False)
    task = _task()
    state = AgentLoopState(observation)
    actions = ActionSpaceBuilder().build(task, observation)
    evaluation = asyncio.run(SharedTaskEvaluator().evaluate(task, observation))
    return ContextBuilder().build(task, state, actions, evaluation)


def test_action_tools_hide_runtime_identity_and_resolve_to_typed_decision() -> None:
    context = _context()
    catalog = compile_tool_catalog(serialize_agent_context(context))
    action = next(spec for spec in catalog.specs if spec.name.startswith("act_"))

    serialized_schema = json.dumps(to_json_compatible(action.input_schema))
    assert context.context_id not in serialized_schema
    assert "action:" not in serialized_schema
    assert "entity:" not in action.description
    assert "target:" not in action.description
    decision = resolve_tool_call(
        catalog,
        ToolCall(action.name, {}),
        expected_context_id=context.context_id,
    )

    assert isinstance(decision, SelectAction)
    assert decision.context_id == context.context_id
    assert decision.action_id.startswith("action:")


def test_unknown_invalid_and_stale_calls_are_typed_before_runtime_admission() -> None:
    context = _context()
    catalog = compile_tool_catalog(serialize_agent_context(context))
    action = next(spec for spec in catalog.specs if spec.name.startswith("act_"))

    with pytest.raises(ToolResolutionError) as unknown:
        resolve_tool_call(catalog, ToolCall("unknown_tool", {}), expected_context_id=context.context_id)
    assert unknown.value.code is ToolResolutionCode.UNKNOWN_TOOL

    with pytest.raises(ToolResolutionError) as invalid:
        resolve_tool_call(
            catalog,
            ToolCall(action.name, {"unexpected": True}),
            expected_context_id=context.context_id,
        )
    assert invalid.value.code is ToolResolutionCode.INVALID_ARGUMENTS

    with pytest.raises(ToolResolutionError) as stale:
        resolve_tool_call(catalog, ToolCall(action.name, {}), expected_context_id="context:other")
    assert stale.value.code is ToolResolutionCode.STALE_CATALOG


def test_destination_refs_do_not_expand_action_tool_count() -> None:
    raw = json.loads(serialize_agent_context(_context()))
    option = raw["actions"]["options"][0]
    option["destination_required"] = True
    option["destinations"] = {
        "items": [
            {"destination_id": "entity:one", "label": "One"},
            {"destination_id": "entity:two", "label": "Two"},
        ],
        "total_count": 2,
        "truncated": False,
    }
    catalog = compile_tool_catalog(json.dumps(raw))
    action_specs = tuple(spec for spec in catalog.specs if spec.name.startswith("act_"))

    assert len(action_specs) == len(raw["actions"]["options"])
    assert action_specs[0].input_schema["properties"]["destination_ref"]["enum"] == (
        "dest_01",
        "dest_02",
    )
    decision = resolve_tool_call(
        catalog,
        ToolCall(action_specs[0].name, {"destination_ref": "dest_02"}),
        expected_context_id=raw["context_id"],
    )
    assert decision.destination_id == "entity:two"


def test_paging_controls_are_distinct_and_restore_existing_decisions() -> None:
    raw = json.loads(serialize_agent_context(_context()))
    raw["actions"].update({"has_more": True, "truncated": True, "total_count": 3, "next_cursor": "cursor:actions"})
    raw["world"]["traversal"] = {
        "snapshot_id": "observation:1",
        "status": "partial",
        "next_cursor": "cursor:observation",
        "traversed_count": 1,
        "reason_code": "",
    }
    catalog = compile_tool_catalog(json.dumps(raw))

    action_page = resolve_tool_call(
        catalog,
        ToolCall("next_action_page", {}),
        expected_context_id=raw["context_id"],
    )
    observation_page = resolve_tool_call(
        catalog,
        ToolCall("next_observation_page", {}),
        expected_context_id=raw["context_id"],
    )

    assert isinstance(action_page, RequestActionPage)
    assert action_page.cursor == "cursor:actions"
    assert isinstance(observation_page, RequestObservation)
    assert observation_page.cursor == "cursor:observation"
