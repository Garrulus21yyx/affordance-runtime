from __future__ import annotations

import json

from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldDocumentView,
    ActorWorldNodeView,
    ActorWorldSnapshot,
    ActorWorldSourceView,
)
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.compact_world_renderer import render_compact_actor_world
from affordance_runtime.agent.context.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
)
from affordance_runtime.immutable import to_json_compatible


def test_compact_world_conserves_complete_groups_states_and_affordances() -> None:
    roots = tuple(_post(index) for index in range(1, 8)) + (
        ActorWorldNodeView("E22", "button", "Submit"),
    )
    snapshot = _snapshot(roots)
    grounding = _grounding()

    rendered = render_compact_actor_world(snapshot, grounding, include_images=False)

    assert rendered.count('StaticText "@nibh"') == 7
    assert rendered.count('clickable "like" active=false verbs=["activate"]') == 7
    assert '[E22] button "Submit" verbs=["activate"]' in rendered
    for index in range(1, 8):
        group_ref = f"E{(index - 1) * 3 + 1}"
        like_ref = f"E{(index - 1) * 3 + 3}"
        group = rendered.index(f'[{group_ref}] group "media"')
        author = rendered.index('StaticText "@nibh"', group)
        like = rendered.index(f'[{like_ref}] clickable "like"', author)
        assert group < author < like


def test_compact_world_drops_projection_scaffolding_but_not_public_semantics() -> None:
    snapshot = _snapshot((_post(1), ActorWorldNodeView("E22", "button", "Submit")))
    grounding = _grounding(post_count=1)

    rendered = render_compact_actor_world(snapshot, grounding, include_images=False)
    typed = json.dumps(to_json_compatible(snapshot), separators=(",", ":"))

    assert len(rendered.encode()) < len(typed.encode()) / 2
    assert "state_evidence" not in rendered
    assert "source_refs" not in rendered
    assert "semantic.dom.tag" not in rendered
    assert "appearance.color_family" not in rendered
    assert "N1" not in rendered
    assert "@nibh" in rendered
    assert "active=false" in rendered


def test_compact_world_discloses_partial_node_state() -> None:
    node = ActorWorldNodeView(
        "E1",
        "combobox",
        "Country",
        {"value": "China", "selected_options": ("China",)},
        state_total_count=5,
        state_truncated=True,
    )

    rendered = render_compact_actor_world(
        _snapshot((node,)),
        AgentGroundingIndexView(
            (AgentGroundingEntityView("E1", "combobox", "Country"),),
            {"target:country": "E1"},
        ),
        include_images=False,
    )

    assert 'value="China"' in rendered
    assert "state_coverage=2/5" in rendered


def _post(index: int) -> ActorWorldNodeView:
    base = (index - 1) * 3 + 1
    return ActorWorldNodeView(
        f"E{base}",
        "generic",
        "",
        {
            "appearance.color_family": "other",
            "semantic.dom.attribute.class_tokens": ("media",),
            "semantic.dom.tag": "div",
        },
        children=(
            ActorWorldNodeView("N1" if index == 1 else f"N{index}", "StaticText", "@nibh"),
            ActorWorldNodeView(f"E{base + 1}", "StaticText", f"Post {index}"),
            ActorWorldNodeView(
                f"E{base + 2}",
                "clickable",
                "",
                {
                    "active": False,
                    "appearance.color_family": "other",
                    "semantic.dom.attribute.class_tokens": ("like",),
                    "semantic.dom.tag": "span",
                    "viewport.visible": True,
                },
                {"active": f"F{index}"},
                source_refs=("S1",),
            ),
        ),
        source_refs=("S1",),
    )


def _snapshot(roots: tuple[ActorWorldNodeView, ...]) -> ActorWorldSnapshot:
    count = sum(1 for root in roots for _ in _walk(root))
    return ActorWorldSnapshot(
        (ActorWorldDocumentView("S1", "structural", roots, count, count, False),),
        (
            ActorWorldSourceView(
                "S1",
                "structural",
                "structural",
                "current",
                "complete",
                "complete",
                "current_screenshot_available",
            ),
        ),
        (),
        (),
        BoundedSection((), 0, False),
        (),
        (),
        (),
    )


def _grounding(post_count: int = 7) -> AgentGroundingIndexView:
    entities = []
    bindings = {}
    for index in range(1, post_count + 1):
        base = (index - 1) * 3 + 1
        for offset, role, label, verbs in (
            (0, "generic", "", ()),
            (1, "StaticText", f"Post {index}", ()),
            (2, "clickable", "", ("activate",)),
        ):
            ref = f"E{base + offset}"
            entities.append(AgentGroundingEntityView(ref, role, label, verbs=verbs))
            bindings[f"entity:{base + offset}"] = ref
    entities.append(AgentGroundingEntityView("E22", "button", "Submit", verbs=("activate",)))
    bindings["entity:22"] = "E22"
    return AgentGroundingIndexView(tuple(entities), bindings)


def _walk(node: ActorWorldNodeView):
    yield node
    for child in node.children:
        yield from _walk(child)
