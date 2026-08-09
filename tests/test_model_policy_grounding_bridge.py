import asyncio
import json
from dataclasses import dataclass, field

from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.model_policy.contracts import ModelDecisionRequest
from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_policy.spec import SCHEMA_VERSION, AgentDecisionPayload, decision_response_schema
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
