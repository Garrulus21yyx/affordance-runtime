import asyncio

from affordance_runtime.benchmarks.model_conformance.runner import build_live_dom_scenario


def test_level_three_scenario_uses_real_dom_agent_context() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    assert scenario.context.context_id.startswith("context:")
    assert len(scenario.context.actions.options) == 1
    assert scenario.context.actions.options[0].semantic_action == "activate"
    assert scenario.complexity.actions == 1
