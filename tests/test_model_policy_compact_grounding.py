import asyncio
import json

from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.model_policy.grounding import (
    MAX_COMPACT_GUIDE_BYTES,
    build_compact_decision_guide,
    serialize_compact_decision_guide,
)


def test_compact_guide_uses_actual_ids_and_is_deterministic_and_bounded() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    guide = build_compact_decision_guide(scenario.serialized_context)
    encoded = serialize_compact_decision_guide(guide)
    option = scenario.context.actions.options[0]
    assert guide.current_context_id == scenario.context.context_id
    assert guide.visible_actions[0].action_id == option.action_id
    assert guide.select_action_example["action_id"] == option.action_id
    assert encoded == serialize_compact_decision_guide(guide)
    assert len(encoded.encode()) <= MAX_COMPACT_GUIDE_BYTES
    assert len(encoded.encode()) < 1_024


def test_compact_guide_contains_no_private_route_fields() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    encoded = serialize_compact_decision_guide(
        build_compact_decision_guide(scenario.serialized_context)
    ).casefold()
    for private in (
        "selector", "coordinate", "bbox", "point", "href", "method", "backend",
        "executor", "credential", "authorization", "/home/yang", "backend_private",
    ):
        assert private not in encoded
    assert json.loads(encoded)["current_context_id"] == scenario.context.context_id
