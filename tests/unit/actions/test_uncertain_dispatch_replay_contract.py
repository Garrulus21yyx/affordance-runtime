from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY


def test_uncertain_dispatch_replay_is_closed_and_excludes_generic_activation() -> None:
    replay_safe = {
        definition.semantic_action
        for definition in INTERACTION_CAPABILITY_REGISTRY.definitions
        if definition.replay_safe_after_uncertain_dispatch
    }

    assert replay_safe == {"type_text", "select_option", "set_value"}
    assert INTERACTION_CAPABILITY_REGISTRY.require(
        "activate"
    ).replay_safe_after_uncertain_dispatch is False
