from __future__ import annotations

import json

from affordance_runtime.actions.capabilities import InteractionSubjectKind
from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldDocumentView,
    ActorWorldFactView,
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
from affordance_runtime.agent.context.world_region_index import (
    DeliveryLimits,
    WorldDeliveryIndex,
    WorldRegion,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import SemanticTarget
from tests.support.canonical_world import canonical_world_with_regions
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


def test_hidden_duplicate_node_does_not_register_undelivered_fact_refs() -> None:
    snapshot = _snapshot(
        (
            ActorWorldNodeView(
                "N1",
                "group",
                "Repeated label",
                children=(
                    ActorWorldNodeView(
                        "N2",
                        "StaticText",
                        "Repeated label",
                        facts=(ActorWorldFactView("F1", "value", "hidden"),),
                    ),
                ),
            ),
        )
    )
    grounding = AgentGroundingIndexView(
        (
            AgentGroundingEntityView("N1", "group", "Repeated label"),
            AgentGroundingEntityView("N2", "StaticText", "Repeated label"),
        ),
        {"parent": "N1", "duplicate": "N2"},
    )

    rendered = render_compact_actor_world(snapshot, grounding, include_images=False)

    assert "[N2]" not in rendered.view.text
    assert "F1" not in rendered.manifest.fact_refs
    assert "F1" not in rendered.view.text


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
    region_index = _region_index(15, observation.observation_id)
    projection = canonical_world_with_regions(
        _canonical_world(observation), observation, region_index
    )

    rendered = render_compact_actor_world(
        snapshot,
        grounding,
        include_images=False,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
        expanded_refs=frozenset({"E3"}),
    )

    assert "projection=page_map" in rendered
    assert "public_content=folded" in rendered
    assert "recovery=read_region/search_page_content/find_controls" in rendered
    assert "PageMap regions=15" in rendered
    assert "R1" in rendered.manifest.region_refs
    assert "Post 1" in rendered
    assert "R15" in rendered.manifest.region_refs


def test_page_map_keeps_every_current_non_entity_action_subject() -> None:
    subject_kinds = tuple(
        kind for kind in InteractionSubjectKind if kind is not InteractionSubjectKind.ENTITY
    )
    snapshot = _snapshot(
        tuple(
            ActorWorldNodeView(
                f"N{index}",
                kind.value,
                f"Current {kind.value}",
                {"subject.kind": kind.value, "current_marker": kind.value},
            )
            for index, kind in enumerate(subject_kinds, start=1)
        )
    )
    observation = _observation(1)
    region_index = _region_index(1, observation.observation_id)
    projection = canonical_world_with_regions(
        _canonical_world(observation), observation, region_index
    )

    rendered = render_compact_actor_world(
        snapshot,
        _grounding(post_count=1, include_submit=False),
        include_images=False,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
    )

    assert rendered.view.text.count("CurrentActionSubjects") == 1
    for kind in subject_kinds:
        assert rendered.view.text.count(f"  {kind.value} label=") == 1
        assert f'"current_marker":"{kind.value}"' in rendered.view.text


def test_page_map_tells_action_policy_when_active_layer_blocks_background() -> None:
    state = {
        "active_layer": True,
        "blocks_background": True,
        "blocked_control_count": 3,
        "modal": False,
    }
    observation = fused_world(
        "S1",
        (SemanticTarget("layer:current", "region", "Visible overlay", state),),
        surface="dom",
    )
    index = WorldDeliveryIndex(
        observation.observation_id,
        (
            WorldRegion(
                key="region:active-layer",
                source_id="S1",
                root_structure_id="layer:root",
                member_target_ids=("layer:current",),
                heading="Visible overlay",
                role="region",
                counts={"targets": 1, "facts": 4, "actions": 0},
                state_badges=state,
                coverage="complete",
            ),
        ),
    )
    projection = canonical_world_with_regions(
        _canonical_world(observation), observation, index
    )
    snapshot = _snapshot((ActorWorldNodeView("N1", "region", "Visible overlay", state),))
    grounding = AgentGroundingIndexView(
        (AgentGroundingEntityView("N1", "region", "Visible overlay", state),),
        {"layer:current": "N1"},
    )

    rendered = render_compact_actor_world(
        snapshot,
        grounding,
        include_images=False,
        region_index=index,
        canonical_world=projection,
        observation=observation,
    )

    assert '"active_layer":true' in rendered.view.text
    assert '"blocks_background":true' in rendered.view.text
    assert '"blocked_control_count":3' in rendered.view.text


def test_large_page_map_is_bounded_without_shrinking_recoverable_region_index() -> None:
    count = 40
    snapshot = _snapshot(tuple(_post(index) for index in range(1, count + 1)))
    grounding = _grounding(post_count=count, include_submit=False)
    observation = _observation(count)
    region_index = _region_index(count, observation.observation_id)
    projection = canonical_world_with_regions(
        _canonical_world(observation), observation, region_index
    )
    limits = DeliveryLimits(page_map_tokens=160)

    rendered = render_compact_actor_world(
        snapshot,
        grounding,
        include_images=False,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
        limits=limits,
    )

    descriptor_lines = tuple(
        line for line in rendered.view.text.splitlines() if line.startswith("  [R")
    )
    descriptor_tokens = sum((len((line + "\n").encode("utf-8")) + 3) // 4 for line in descriptor_lines)
    assert descriptor_tokens <= limits.page_map_tokens
    assert rendered.coverage["page_map"] == "partial"
    assert rendered.coverage["page_map_regions"] != f"{count}/{count}"
    assert "recovery=list_regions/search_page_content" in rendered.view.text

    recovered = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
        action="view_all",
        page_size=count,
    )
    assert isinstance(recovered, Page)
    assert len(recovered.items) == count
    assert len(region_index.regions) == count


def test_page_map_keeps_every_region_ref_when_optional_descriptor_text_is_oversized() -> None:
    snapshot = _snapshot((_post(1),))
    grounding = _grounding(post_count=1, include_submit=False)
    observation = _observation(1)
    region_index = WorldDeliveryIndex(
        observation.observation_id,
        (
            WorldRegion(
                key="region:oversized",
                source_id="S1",
                root_structure_id="post:1",
                member_target_ids=("entity:1", "entity:2", "entity:3"),
                heading="Review form " + "oversized " * 2_000,
                role="form",
                counts={"targets": 3, "facts": 0, "actions": 1},
                coverage="complete",
            ),
        ),
    )
    projection = canonical_world_with_regions(
        _canonical_world(observation), observation, region_index
    )

    rendered = render_compact_actor_world(
        snapshot,
        grounding,
        include_images=False,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
    )

    assert rendered.manifest.region_refs == ("R1",)
    assert "[R1] kind=\"form\"" in rendered.view.text
    assert "recovery=read_region" in rendered.view.text
    assert all(f"[{ref}]" in rendered.view.text for ref in rendered.manifest.region_refs)


def test_inspect_actor_world_recovers_folded_regions_and_exact_find_results() -> None:
    snapshot = _snapshot(tuple(_post(index) for index in range(1, 6)))
    grounding = _grounding(post_count=5)
    observation = _observation(5)
    region_index = _region_index(5, observation.observation_id)
    projection = canonical_world_with_regions(
        _canonical_world(observation), observation, region_index
    )

    opened = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
        action="read_region",
        region_ref="R5",
    )
    found = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        canonical_world=projection,
        observation=observation,
        action="find",
        query="Post 5",
    )
    all_regions = inspect_actor_world(
        snapshot,
        grounding,
        region_index=region_index,
        canonical_world=projection,
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
                key=f"region:test:{index}",
                source_id="S1",
                root_structure_id=f"post:{index}",
                member_target_ids=tuple(
                    f"entity:{(index - 1) * 3 + offset}" for offset in (1, 2, 3)
                ),
                heading=f"Post {index}",
                role="generic",
                counts={"targets": 3, "facts": 0, "actions": 1},
                coverage="complete",
            )
            for index in range(1, post_count + 1)
        ),
    )


def _canonical_world(observation):
    from tests.support.canonical_world import canonical_world

    return canonical_world(observation)


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
