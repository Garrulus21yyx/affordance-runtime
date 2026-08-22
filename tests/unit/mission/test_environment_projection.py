from affordance_runtime.actions import ActionBinding
from affordance_runtime.mission.environment_projection import project_mission_environment
from affordance_runtime.world import SemanticTarget
from tests.support.world import fused_world


def test_planner_environment_is_a_ref_free_functional_region_summary() -> None:
    target = SemanticTarget("query", "textbox", "Route origin")
    binding = ActionBinding(
        binding_id="binding:query",
        world_observation_id="source:page",
        source_observation_id="source:page",
        source_revision="revision:source:page",
        target_fingerprint="fingerprint:query",
        target_id=target.target_id,
        source_target_id=target.target_id,
        surface="dom",
        executor_id="dom",
        semantic_action="type_text",
        primitive_action="type",
        effect_category="local_reversible",
        semantic_effects=("value_changed",),
        parameter_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        payload={"selector": "#query"},
    )
    world = fused_world("source:page", (target,), bindings=(binding,))
    projection = project_mission_environment(world)
    assert projection.functional_regions
    encoded = repr(projection)
    assert "binding:query" not in encoded
    assert "E1" not in encoded
    assert "selector" not in encoded
    assert all(region.label and region.purpose for region in projection.functional_regions)


def test_functional_region_summary_has_no_action_or_scope_authority() -> None:
    projection = project_mission_environment(fused_world("source:empty"))
    region = projection.functional_regions[0]
    assert set(vars(region)) == {"label", "purpose", "control_families", "coverage"}
