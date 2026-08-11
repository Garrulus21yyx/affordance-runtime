import asyncio
import json
from dataclasses import dataclass, field

import pytest

from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.model_policy.contracts import ModelDecisionRequest
from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_policy.spec import (
    SCHEMA_VERSION,
    AgentDecisionPayload,
    decision_response_schema,
)
from affordance_runtime.model_port import ModelConfig, ModelMessage


@dataclass
class CapturingPort:
    provider: str = "fixture"
    model: str = "fixture"
    endpoint_class: str = "local"
    last_call: object = None
    messages: tuple[ModelMessage, ...] = field(default=())

    async def generate_structured(self, messages, output_schema, config):
        self.messages = tuple(messages)
        context = json.loads(self.messages[1].content)["agent_context"]
        option = context["actions"]["options"][0]
        return AgentDecisionPayload.model_validate({
            "type": "select_action", "context_id": context["context_id"],
            "action_id": option["action_id"], "parameters": {}, "destination_id": "",
        })


def test_compact_bridge_keeps_ids_out_of_system_message() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    port = CapturingPort()
    adapter = ModelPortDecisionAdapter(
        port, ModelConfig(rate_limit_retries=0, transient_retries=0),
        grounding_variant="compact-contract",
    )
    request = ModelDecisionRequest(
        "request:test", scenario.serialized_context, SCHEMA_VERSION, "instructions",
        decision_response_schema(),
    )
    outcome = asyncio.run(adapter.generate(request))
    assert scenario.context.context_id not in port.messages[0].content
    assert scenario.context.context_id in port.messages[1].content
    assert getattr(outcome, "raw_payload", "")


def test_compact_v2_bridge_records_distinct_guide_identity() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    port = CapturingPort()
    adapter = ModelPortDecisionAdapter(
        port, ModelConfig(rate_limit_retries=0, transient_retries=0),
        grounding_variant="compact-contract-v2",
    )
    request = ModelDecisionRequest(
        "request:v2", scenario.serialized_context, SCHEMA_VERSION, "instructions",
        decision_response_schema(),
    )
    outcome = asyncio.run(adapter.generate(request))
    message = json.loads(port.messages[1].content)
    assert message["decision_guide"]["profile_version"] == "compact-contract.v2"
    assert scenario.context.context_id not in port.messages[0].content
    assert outcome.metadata.grounding_variant == "compact-contract-v2"
    assert outcome.metadata.grounding_profile_version == "compact-contract.v2"
    assert outcome.metadata.grounding_guide_schema_version == "compact-contract.v2"
    assert outcome.metadata.grounding_guide_digest.startswith("sha256:")


def test_already_satisfied_repair_constrains_provider_objective_schema() -> None:
    class RepairPort:
        provider = "fixture"
        model = "fixture"
        endpoint_class = "local"
        last_call = None
        output_schema = None

        async def generate_structured(self, messages, output_schema, config):
            del messages, config
            self.output_schema = output_schema
            return output_schema.model_validate({
                "objective_operation": {"kind": "none"},
                "decision": {
                    "type": "abort",
                    "context_id": "context:repair",
                    "reason": "fixture complete",
                    "category": "policy",
                },
            })

    repairs = [
        {"kind": "none"},
        {
            "kind": "propose",
            "intended_requirement_ids": ["requirement:task_outcome"],
            "predicate": {"kind": "task_outcome_is", "status": "complete"},
        },
    ]
    context = json.dumps({
        "context_id": "context:repair",
        "control_feedback": {
            "code": "objective_already_satisfied",
            "recovery": {"admissible_objective_operations": repairs},
        },
    })
    port = RepairPort()
    adapter = ModelPortDecisionAdapter(
        port, ModelConfig(rate_limit_retries=0, transient_retries=0),
    )
    outcome = asyncio.run(adapter.generate(ModelDecisionRequest(
        "request:repair", context, SCHEMA_VERSION, "instructions",
        decision_response_schema(),
    )))

    schema = port.output_schema.model_json_schema()
    assert schema["properties"]["objective_operation"] == {"enum": repairs}
    assert json.loads(outcome.raw_payload)["objective_operation"] == {"kind": "none"}
    with pytest.raises(ValueError, match="outside projected repair alternatives"):
        port.output_schema.model_validate({
            "objective_operation": {
                "kind": "propose",
                "intended_requirement_ids": ["requirement:task_outcome"],
                "predicate": {"kind": "target_present", "target_id": "target:old"},
            },
            "decision": {
                "type": "abort",
                "context_id": "context:repair",
                "reason": "invalid fixture",
                "category": "policy",
            },
        })
