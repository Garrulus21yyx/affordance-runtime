import json

from affordance_runtime.benchmarks.model_conformance.levels import (
    Level0Payload,
    Level1SelectActionPayload,
    minimal_union_context,
)
from affordance_runtime.model_policy.spec import AgentDecisionPayload


def test_level_zero_schema_is_minimal_and_closed() -> None:
    schema = Level0Payload.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["type"]["const"] == "select_action"
    assert schema["required"] == ["type"]


def test_level_one_requires_actual_select_action_contract() -> None:
    value = Level1SelectActionPayload.model_validate(
        {
            "type": "select_action",
            "context_id": "context:x",
            "action_id": "action:x",
            "parameters": {},
            "destination_id": "",
        }
    )
    assert value.action_id == "action:x"
    assert len(AgentDecisionPayload.model_json_schema()["oneOf"]) == 11


def test_level_two_context_is_minimal_but_uses_actual_ids() -> None:
    encoded = minimal_union_context(
        "context:actual",
        "action:actual",
        "activate",
        "target:actual",
        "Shared state",
        "",
    )
    value = json.loads(encoded)
    assert value["context_id"] == "context:actual"
    assert value["visible_actions"][0]["action_id"] == "action:actual"
    assert "world" not in value
