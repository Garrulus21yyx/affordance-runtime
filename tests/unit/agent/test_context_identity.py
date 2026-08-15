from dataclasses import replace

from affordance_runtime.actions import (
    ActionOption,
    ActionSpace,
)
from affordance_runtime.agent.context.context import ContextIdentity


def test_context_identity_is_deterministic_and_revision_sensitive() -> None:
    identity = ContextIdentity(1, "obs:1", "space:1", "page:1", 1)

    assert identity.context_id == ContextIdentity(1, "obs:1", "space:1", "page:1", 1).context_id
    assert replace(identity, observation_id="obs:2").context_id != identity.context_id
    assert replace(identity, action_space_id="space:2").context_id != identity.context_id
    assert replace(identity, action_page_id="page:2").context_id != identity.context_id
    assert replace(identity, context_generation=2).context_id != identity.context_id


def test_action_space_identity_binds_exact_semantic_membership() -> None:
    option = ActionOption(
        "action:one",
        "obs:1",
        "read",
        "target:1",
        "observation",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:1",
        ("binding:private",),
        "read target",
    )
    first = ActionSpace("obs:1", (option,))
    same = ActionSpace("obs:1", (option,))
    changed = ActionSpace("obs:1", (replace(option, description="inspect target"),))

    assert first.action_space_id == same.action_space_id
    assert first.action_space_id != changed.action_space_id
