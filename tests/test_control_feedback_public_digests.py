from __future__ import annotations

from dataclasses import replace

from test_agent_loop import _task, _world

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.world import ActionSpaceBuilder
from affordance_runtime.world.public_semantic_digest import (
    action_page_request_digest,
    issue_digest,
    public_action_page_digest,
    public_world_semantic_digest,
    semantic_scope_digest,
    task_progress_fingerprint,
)


def test_observation_action_space_page_and_private_identity_churn_do_not_change_scope() -> None:
    first = _world("obs:one", False)
    second = _world("obs:two", False)
    task = _task()
    first_space = ActionSpaceBuilder().build(task, first)
    second_space = ActionSpaceBuilder().build(task, second)
    first_page = ContextBuilder().page(first_space, AgentLoopState(first))
    second_page = ContextBuilder().page(second_space, AgentLoopState(second))

    assert public_world_semantic_digest(first) == public_world_semantic_digest(second)
    assert public_action_page_digest(first, first_space, first_page) == public_action_page_digest(
        second, second_space, second_page,
    )
    assert semantic_scope_digest(
        1,
        public_world_semantic_digest(first),
        public_action_page_digest(first, first_space, first_page),
        task_progress_fingerprint(None),
    ) == semantic_scope_digest(
        1,
        public_world_semantic_digest(second),
        public_action_page_digest(second, second_space, second_page),
        task_progress_fingerprint(None),
    )


def test_public_digest_changes_for_semantic_state_and_task_progress() -> None:
    disabled = _world("obs:one", False)
    enabled = _world("obs:two", True)

    assert public_world_semantic_digest(disabled) != public_world_semantic_digest(enabled)


def test_invalid_value_and_reason_text_cannot_expand_issue_budget() -> None:
    world = _world("obs:one", False)
    request_one = action_page_request_digest(
        world, query="same", target_id="shared-toggle", relevance_role="direct", semantic_offset=0,
    )
    request_two = action_page_request_digest(
        world, query="same", target_id="shared-toggle", relevance_role="direct", semantic_offset=0,
    )
    common = {
        "scope_digest": "a" * 64,
        "kind": "repairable_rejection",
        "source": "action_admission",
        "code": "invalid_action_parameters",
        "subject_semantics": ("button", "Enable shared state"),
        "public_field_paths": ("parameters",),
    }

    assert request_one == request_two
    assert issue_digest(**common) == issue_digest(**common)


def test_private_binding_payload_is_excluded_from_public_world_digest() -> None:
    world = _world("obs:one", False)
    binding = replace(world.bindings[0], payload={"selector": "#different-private-route"})
    source = replace(world.sources[0], bindings=(binding,))
    changed = replace(world, bindings=(binding,), sources=(source,))

    assert public_world_semantic_digest(world) == public_world_semantic_digest(changed)


def test_target_action_and_page_id_churn_with_same_semantics_is_ignored() -> None:
    first = _world("obs:one", False)
    target = replace(first.targets[0], target_id="replacement-public-id")
    fact = replace(
        first.facts[0],
        fact_id="fact:replacement",
        subject_id=target.target_id,
        source_id="source:replacement",
    )
    binding = replace(
        first.bindings[0],
        binding_id="binding:replacement",
        target_id=target.target_id,
        source_target_id=target.target_id,
        target_fingerprint="private:fingerprint:replacement",
        payload={"selector": "#replacement"},
    )
    source = replace(first.sources[0], targets=(target,), facts=(fact,), bindings=(binding,))
    second = replace(first, targets=(target,), facts=(fact,), bindings=(binding,), sources=(source,))
    first_space = ActionSpaceBuilder().build(_task(), first)
    second_space = ActionSpaceBuilder().build(_task(), second)
    first_page = ContextBuilder().page(first_space, AgentLoopState(first))
    second_page = ContextBuilder().page(second_space, AgentLoopState(second))

    assert public_world_semantic_digest(first) == public_world_semantic_digest(second)
    assert public_action_page_digest(first, first_space, first_page) == public_action_page_digest(
        second, second_space, second_page,
    )
