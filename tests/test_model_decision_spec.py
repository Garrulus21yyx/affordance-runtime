import json

import pytest
from pydantic import ValidationError

from affordance_runtime.agent.decisions import EstablishLocalObjective
from affordance_runtime.model_policy.spec import (
    SCHEMA_VERSION,
    AgentDecisionPackagePayload,
    AgentDecisionPayload,
    decision_response_schema,
    payload_to_decision,
)


def test_canonical_package_has_four_objective_operations_and_typed_decisions() -> None:
    schema = decision_response_schema()
    objective = schema["properties"]["objective_operation"]
    decision = schema["properties"]["decision"]

    assert SCHEMA_VERSION == "agent-decision-package.v2"
    assert objective["discriminator"]["propertyName"] == "kind"
    assert set(objective["discriminator"]["mapping"]) == {
        "none",
        "propose",
        "retain",
        "replace",
    }
    assert decision["discriminator"]["propertyName"] == "type"
    assert set(decision["discriminator"]["mapping"]) == {
        "select_action",
        "establish_local_objective",
        "request_observation",
        "request_action_page",
        "ask_user",
        "propose_done",
        "wait",
        "abort",
    }
    assert len(objective["oneOf"]) == 4
    assert len(decision["oneOf"]) == 8
    assert AgentDecisionPackagePayload.model_json_schema() == schema


def test_provider_schema_encodes_runtime_enums_and_forbids_extra_fields() -> None:
    encoded = json.dumps(decision_response_schema(), sort_keys=True)

    for value in (
        "structural",
        "visual",
        "environment_state",
        "weak",
        "authoritative",
        "direct",
        "enabling",
        "information",
        "other",
        "safety",
        "unsupported",
        "no_progress",
        "user_request",
    ):
        assert f'"{value}"' in encoded
    assert '"additionalProperties": false' in encoded


def test_propose_done_summary_uses_canonical_1024_character_budget() -> None:
    schema = decision_response_schema()
    summary = schema["$defs"]["ProposeDonePayload"]["properties"]["result_summary"]

    assert summary["minLength"] == 1
    assert summary["maxLength"] == 1_024


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_canonical_payload_rejects_non_finite_python_parameter_values(value: float) -> None:
    with pytest.raises(ValidationError):
        AgentDecisionPayload.model_validate(
            {
                "type": "select_action",
                "context_id": "context:1",
                "action_id": "action:1",
                "parameters": {"value": value},
                "destination_id": "",
            }
        )


def test_direct_decision_boundary_rejects_non_json_sequence_coercion() -> None:
    with pytest.raises(TypeError, match="JSON lists"):
        AgentDecisionPayload.model_validate(
            {
                "type": "ask_user",
                "context_id": "context:1",
                "question": "Which value?",
                "requested_fields": ("value",),
            }
        )
    with pytest.raises(TypeError, match="JSON lists"):
        AgentDecisionPayload.model_validate(
            {
                "type": "select_action",
                "context_id": "context:1",
                "action_id": "action:1",
                "parameters": {"indices": range(2)},
                "destination_id": "",
            }
        )


def test_local_objective_payload_uses_semantics_instead_of_runtime_target_identity() -> None:
    payload = AgentDecisionPayload.model_validate(
        {
            "type": "establish_local_objective",
            "context_id": "context:1",
            "objective": {
                "kind": "set",
                "predicate": {
                    "kind": "fact_equals",
                    "field_name": "grid_coordinate",
                    "expected": {"x": 1, "y": -2},
                },
                "quantifier": "exactly_one",
                "semantic_action": "activate",
            },
        }
    )
    decision = payload_to_decision(payload, "context:1")

    assert isinstance(decision, EstablishLocalObjective)
    assert decision.objective.objective_id.startswith("set-objective:")
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
    assert "target_id" not in encoded and "action_id" not in encoded and "binding_id" not in encoded
    objective_schema = AgentDecisionPayload.model_json_schema()["$defs"]["SetLocalObjectivePayload"]
    assert not set(objective_schema["properties"]).intersection(
        {"objective_id", "scope_id", "scope_root", "target_id", "action_id", "binding_id"}
    )
