from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.attempt_signature import (
    public_attempt_signature,
    public_local_result_attempt_signature,
)
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldFusion,
)
from affordance_runtime.world.contracts import ObservationStructureNode, WorldObservation


def _world(
    observation_id: str,
    controls: tuple[tuple[str, dict[str, object]], ...],
    *,
    status_text: str = "",
) -> WorldObservation:
    targets = [
        SemanticTarget(
            f"document:{observation_id}",
            "document",
            "Repository",
            {"page.route": "https://example.test/repository/changes"},
        ),
        SemanticTarget(f"status:{observation_id}", "status", status_text),
        *(SemanticTarget(target_id, "button", "Commit", state) for target_id, state in controls),
    ]
    control_nodes = tuple(
        ObservationStructureNode(
            f"control-node:{index}:{observation_id}",
            "button",
            "Commit",
            state,
            parent_structure_id=f"root:{observation_id}",
            semantic_target_id=target_id,
        )
        for index, (target_id, state) in enumerate(controls)
    )
    structure = (
        ObservationStructureNode(
            f"root:{observation_id}",
            "document",
            "Repository",
            child_structure_ids=tuple(item.structure_id for item in control_nodes),
            semantic_target_id=f"document:{observation_id}",
        ),
        *control_nodes,
    )
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        tuple(targets),
        structure=structure,
        structure_total_count=len(structure),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


@given(
    before_status=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=40,
    ),
    after_status=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=40,
    ),
)
def test_unrelated_page_content_cannot_invalidate_exact_attempt_identity(
    before_status: str,
    after_status: str,
) -> None:
    before = _world("before", (("commit:before", {"enabled": True}),), status_text=before_status)
    after = _world("after", (("commit:after", {"enabled": True}),), status_text=after_status)

    assert public_attempt_signature("activate", "commit:before", "", {}, before) == (
        public_attempt_signature("activate", "commit:after", "", {}, after)
    )


def test_target_precondition_change_invalidates_exact_attempt_identity() -> None:
    before = _world("before", (("commit:before", {"enabled": True}),))
    after = _world("after", (("commit:after", {"enabled": False}),))

    assert public_attempt_signature("activate", "commit:before", "", {}, before) != (
        public_attempt_signature("activate", "commit:after", "", {}, after)
    )


def test_duplicate_controls_have_distinct_but_ref_free_stable_identity() -> None:
    before = _world(
        "before",
        (
            ("commit:first:before", {"enabled": True}),
            ("commit:second:before", {"enabled": True}),
        ),
    )
    after = _world(
        "after",
        (
            ("commit:first:after", {"enabled": True}),
            ("commit:second:after", {"enabled": True}),
        ),
    )

    before_first = public_attempt_signature("activate", "commit:first:before", "", {}, before)
    before_second = public_attempt_signature("activate", "commit:second:before", "", {}, before)
    after_first = public_attempt_signature("activate", "commit:first:after", "", {}, after)
    after_second = public_attempt_signature("activate", "commit:second:after", "", {}, after)

    assert before_first != before_second
    assert before_first == after_first
    assert before_second == after_second


def test_local_result_attempt_identity_is_stable_across_public_id_churn() -> None:
    before = _world("before", (("commit:before", {"enabled": True}),))
    after = _world("after", (("commit:after", {"enabled": True}),))
    arguments = {"region_ref": "R10"}
    result = {"kind": "Region", "items": ({"label": "review"},)}

    assert public_local_result_attempt_signature("read_region", arguments, result, before) == (
        public_local_result_attempt_signature("read_region", arguments, result, after)
    )


def test_local_result_attempt_identity_changes_with_world_or_result() -> None:
    before = _world("before", (("commit:before", {"enabled": True}),))
    changed_world = _world(
        "after",
        (("commit:after", {"enabled": True}),),
        status_text="new public content",
    )
    arguments = {"query": "reviews"}
    first_result = {"kind": "Matches", "items": ({"label": "first"},)}
    changed_result = {"kind": "Matches", "items": ({"label": "second"},)}
    original = public_local_result_attempt_signature(
        "search_page_content",
        arguments,
        first_result,
        before,
    )

    assert original != public_local_result_attempt_signature(
        "search_page_content",
        arguments,
        first_result,
        changed_world,
    )
    assert original != public_local_result_attempt_signature(
        "search_page_content",
        arguments,
        changed_result,
        before,
    )
