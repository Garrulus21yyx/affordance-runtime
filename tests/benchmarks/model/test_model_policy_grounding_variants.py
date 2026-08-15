import asyncio
import json

from affordance_runtime.benchmarks.model_conformance.grounding import (
    GroundingVariant,
    build_grounded_input,
    context_bound_schema,
)
from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.model.policy.spec import decision_response_schema


def test_grounding_variants_keep_current_ids_in_user_data() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    schema = decision_response_schema()
    baseline = build_grounded_input(scenario.serialized_context, schema, GroundingVariant.FORMAT_ONLY)
    compact = build_grounded_input(scenario.serialized_context, schema, GroundingVariant.COMPACT_CONTRACT)
    full = build_grounded_input(scenario.serialized_context, schema, GroundingVariant.FULL_SCHEMA_TEXT)
    assert baseline.user_message == scenario.serialized_context
    assert scenario.context.context_id in compact.user_message
    assert "decision_guide" in compact.user_message
    assert "decision_schema" in full.user_message
    assert scenario.context.context_id not in compact.system_message


def test_context_bound_schema_uses_current_const_and_visible_action_enum() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    action = scenario.context.actions.options[0].action_id
    schema = context_bound_schema(
        decision_response_schema(), scenario.context.context_id, (action,),
    )
    select = schema["$defs"]["SelectActionPayload"]["properties"]
    assert select["context_id"]["const"] == scenario.context.context_id
    assert select["action_id"]["enum"] == [action]
    assert json.dumps(schema) != json.dumps(decision_response_schema())
