from dataclasses import replace

from affordance_runtime.model_boundary.context import ContextIdentity
from affordance_runtime.world import ActionOption, ActionSpace


def test_context_identity_is_deterministic_and_revision_sensitive() -> None:
    identity = ContextIdentity(1, "obs:1", "space:1", "page:1", 0, 0)

    assert identity.context_id == ContextIdentity(1, "obs:1", "space:1", "page:1", 0, 0).context_id
    assert replace(identity, observation_id="obs:2").context_id != identity.context_id
    assert replace(identity, action_space_id="space:2").context_id != identity.context_id
    assert replace(identity, action_page_id="page:2").context_id != identity.context_id
    assert replace(identity, progress_revision=1).context_id != identity.context_id
    assert replace(identity, pending_revision=1).context_id != identity.context_id


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
