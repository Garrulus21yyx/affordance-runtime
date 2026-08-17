from dataclasses import replace

import pytest

from affordance_runtime.actions import (
    ActionOption,
    ActionSpace,
)
from affordance_runtime.agent.context.context import ContextIdentity


def test_context_identity_is_deterministic_and_revision_sensitive() -> None:
    identity = ContextIdentity(
        1,
        "obs:1",
        "space:1",
        "page:1",
        1,
        "ready",
        3,
        "a" * 64,
        "c" * 64,
    )

    assert identity.context_id == replace(identity).context_id
    assert replace(identity, observation_id="obs:2").context_id != identity.context_id
    assert replace(identity, action_space_id="space:2").context_id != identity.context_id
    assert replace(identity, action_page_id="page:2").context_id != identity.context_id
    assert replace(identity, context_generation=2).context_id != identity.context_id
    assert replace(identity, goal_plan_version=4).context_id != identity.context_id
    assert replace(identity, goal_plan_digest="b" * 64).context_id != identity.context_id
    assert replace(identity, tool_catalog_digest="d" * 64).context_id != identity.context_id


def test_context_identity_empty_goal_dispositions_cannot_forge_plan_identity() -> None:
    with pytest.raises(ValueError, match="cannot invent"):
        ContextIdentity(
            1,
            "obs:1",
            "space:1",
            "page:1",
            goal_plan_disposition="not_required",
            goal_plan_digest="a" * 64,
        )


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
