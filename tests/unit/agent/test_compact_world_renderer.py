from __future__ import annotations

import json

from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldDocumentView,
    ActorWorldNodeView,
    ActorWorldSnapshot,
    ActorWorldSourceView,
)
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.compact_world_renderer import (
    Matches,
    Opened,
    Page,
    inspect_actor_world,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex, WorldRegion
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import SemanticTarget
from tests.support.world import fused_world


def test_compact_world_conserves_complete_groups_states_and_inline_verbs() -> None:
    roots = tuple(_post(index) for index in range(1, 8)) + (ActorWorldNodeView("E22", "button", "Submit"),)
    snapshot = _snapshot(roots)
    grounding = _grounding()

    rendered = render_compact_actor_world(snapshot, grounding, include_images=False)

    assert rendered.count('StaticText "@nibh"') == 7
    assert rendered.count("clickable active[F") == 7
    assert '[E22] button "Submit" verbs=["activate"]' in rendered
    for index in range(1, 8):
        like_ref = f"E{(index - 1) * 3 + 3}"
        post = rendered.text.index(f'StaticText "Post {index}"')
        like = rendered.text.index(f"[{like_ref}] clickable", post)
        assert post < like


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
    assert '[N1] StaticText "@nibh" read_only=true' in rendered
    assert "@nibh" in rendered
    assert "active[F1]=false" in rendered


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


def test_executable_and_readonly_refs_render_with_separate_contracts() -> None:
    snapshot = _snapshot(
        (
            ActorWorldNodeView("N1", "link", "Bestsellers"),
            ActorWorldNodeView("E1", "tab", "Bestsellers"),
        )
    )
    grounding = AgentGroundingIndexView(
        (
            AgentGroundingEntityView("N1", "link", "Bestsellers"),
            AgentGroundingEntityView("E1", "tab", "Bestsellers", verbs=("activate", "press_key")),
        ),
        {
            "readonly:bestsellers": "N1",
            "action:bestsellers": "E1",
        },
    )

    rendered = render_compact_actor_world(snapshot, grounding, include_images=False)

    assert '[N1] link "Bestsellers" read_only=true' in rendered
    assert '[E1] tab "Bestsellers" verbs=["activate","press_key"]' in rendered


def test_region_delivery_folds_with_recoverable_directory() -> None:
    snapshot = _snapshot(tuple(_post(index) for index in range(1, 16)))
    grounding = _grounding(post_count=15, include_submit=False)
    observation = _observation(15)

    rendered = render_compact_actor_world(
        snapshot,
        grounding,
        include_images=False,
        region_index=_region_index(15, observation.observation_id),
        observation=observation,
        expanded_refs=frozenset({"E3"}),
        max_rendered_bytes=700,
    )

    assert "projection=page_map" in rendered
    assert "public_content=folded" in rendered
    assert "recovery=read_region/search_page_content/find_controls" in rendered
    assert "PageMap regions=15" in rendered
    assert "R1" in rendered.manifest.region_refs
    assert "Post 1" in rendered
    assert "R15" in rendered.manifest.region_refs


def test_inspect_actor_world_recovers_folded_regions_and_exact_find_results() -> None:
    snapshot = _snapshot(tuple(_post(index) for index in range(1, 6)))
    grounding = _grounding(post_count=5)
    observation = _observation(5)
    region_index = _region_index(5, observation.observation_id)

    opened = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        observation=observation,
        action="read_region",
        region_ref="R5",
    )
    found = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        observation=observation,
        action="find",
        query="Post 5",
    )
    all_regions = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        observation=observation,
        action="view_all",
    )

    assert isinstance(opened, Opened)
    assert any(item["label"] == "Post 5" for item in opened.items)
    assert isinstance(found, Matches)
    assert len(found.items) == 1
    assert found.items[0]["region_ref"] == "R5"
    assert found.items[0]["label"] == "Post 5"
    assert not {"actionable", "verbs", "action_refs"}.intersection(found.items[0])
    assert isinstance(all_regions, Page)
    assert len(all_regions.items) == 5


def _observation(post_count: int):
    targets = []
    for index in range(1, post_count + 1):
        base = (index - 1) * 3 + 1
        targets.extend(
            (
                SemanticTarget(f"entity:{base}", "generic", "media"),
                SemanticTarget(f"entity:{base + 1}", "StaticText", f"Post {index}"),
                SemanticTarget(f"entity:{base + 2}", "clickable", "like", {"active": False}),
            )
        )
    return fused_world("S1", tuple(targets), surface="dom")


def _region_index(post_count: int, observation_id: str = "world:test") -> WorldDeliveryIndex:
    return WorldDeliveryIndex(
        observation_id,
        tuple(
            WorldRegion(
                f"region:test:{index}",
                f"R{index}",
                "S1",
                f"post:{index}",
                tuple(f"entity:{(index - 1) * 3 + offset}" for offset in (1, 2, 3)),
                (),
                f"Post {index}",
                "generic",
                {"targets": 3, "facts": 0, "actions": 1},
                "complete",
            )
            for index in range(1, post_count + 1)
        ),
    )


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


def _grounding(post_count: int = 7, *, include_submit: bool = True) -> AgentGroundingIndexView:
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
    if include_submit:
        entities.append(AgentGroundingEntityView("E22", "button", "Submit", verbs=("activate",)))
        bindings["entity:22"] = "E22"
    return AgentGroundingIndexView(tuple(entities), bindings)


def _walk(node: ActorWorldNodeView):
    yield node
    for child in node.children:
        yield from _walk(child)
