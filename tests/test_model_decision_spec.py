import json

import pytest
from pydantic import ValidationError

from affordance_runtime.model_policy.spec import SCHEMA_VERSION, AgentDecisionPayload, decision_response_schema


def test_canonical_spec_has_exactly_seven_discriminated_variants() -> None:
    schema = decision_response_schema()
    discriminator = schema["discriminator"]

    assert SCHEMA_VERSION == "agent-decision.v1"
    assert discriminator["propertyName"] == "type"
    assert set(discriminator["mapping"]) == {
        "select_action",
        "request_observation",
        "request_action_page",
        "ask_user",
        "propose_done",
        "wait",
        "abort",
    }
    assert len(schema["oneOf"]) == 7
    assert AgentDecisionPayload.model_json_schema() == schema


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
