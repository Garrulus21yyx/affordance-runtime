from dataclasses import dataclass, replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

import affordance_runtime.actions.paging as action_paging
from affordance_runtime.actions import (
    ActionOption,
    ActionPager,
    ActionRelevanceRole,
    ActionRisk,
    ActionSpace,
)
from affordance_runtime.actions.paging import (
    PUBLIC_ACTION_LABEL_MAX_CHARS,
    ActionRecallSet,
    ActionReranker,
)
from affordance_runtime.schema_digest import schema_digest
from tests.support.action_contracts import verification_kwargs


@dataclass(frozen=True)
class _Objective:
    direct_target_ids: tuple[str, ...] = ()
    direct_effects: tuple[str, ...] = ()
    enabling_target_ids: tuple[str, ...] = ()
    enabling_action_hints: tuple[str, ...] = ()


def _option(index: int, *, action: str = "activate", effect: str = "changed") -> ActionOption:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    effects = () if action == "read" else (effect,)
    return ActionOption(
        f"action:{index:02}",
        "obs:1",
        action,
        f"target:{index:02}",
        "observation" if action == "read" else "local_reversible",
        schema,
        schema_digest(schema),
        (f"binding:{index:02}",),
        f"{action} public target {index:02}",
        effects,
        ActionRisk.LOW,
        **verification_kwargs(action, schema_digest(schema), effects),
    )


def test_action_page_is_bounded_truthful_and_tail_remains_retrievable() -> None:
    space = ActionSpace("obs:1", tuple(_option(index) for index in range(40)))
    pager = ActionPager(page_size=8)
    objective = _Objective(direct_target_ids=("target:00",))

    default = pager.page(space, objective)
    second = pager.page(space, objective, cursor=default.next_cursor)

    assert default.visible_action_ids[0] == "action:00"
    assert len(default.visible_action_ids) == 8
    assert default.total_count == 40 and default.has_more
    assert "action:39" not in default.visible_action_ids
    assert set(default.visible_action_ids).isdisjoint(second.visible_action_ids)
    assert second.page_id != default.page_id


def test_cursor_pager_traverses_every_action_without_overlap() -> None:
    space = ActionSpace("obs:1", tuple(_option(index) for index in range(20)))
    pager = ActionPager(page_size=6)
    pages = []
    cursor = ""

    while True:
        page = pager.page(space, cursor=cursor)
        pages.append(page)
        if not page.has_more:
            break
        cursor = page.next_cursor

    flattened = tuple(action_id for page in pages for action_id in page.visible_action_ids)
    assert flattened == tuple(option.action_id for option in space.options)
    assert len(flattened) == len(set(flattened))
    assert pages[-1].next_cursor == ""


def test_query_cursor_is_bound_to_its_exact_query() -> None:
    space = ActionSpace(
        "obs:1",
        tuple(_option(index, action="read", effect="") for index in range(12)),
    )
    pager = ActionPager(page_size=5)

    first = pager.page(space, query="read")
    second = pager.page(
        space,
        query="read",
        cursor=first.next_cursor,
    )

    assert first.visible_action_ids != second.visible_action_ids
    with pytest.raises(ValueError, match="cursor"):
        pager.page(space, query="different", cursor=first.next_cursor)


def test_private_description_size_does_not_change_page_membership() -> None:
    base = ActionSpace("obs:1", (_option(0), _option(1)))
    enlarged = ActionSpace("obs:1", (replace(_option(0), description="x" * 1_000), _option(1)))

    assert ActionPager().page(base).visible_action_ids == ActionPager().page(enlarged).visible_action_ids


def test_business_schema_size_does_not_change_route_page_membership() -> None:
    def typed(index: int, enum: tuple[str, ...]) -> ActionOption:
        schema = {
            "type": "object",
            "properties": {"text": {"type": "string", "enum": enum}},
            "required": ["text"],
            "additionalProperties": False,
        }
        return replace(
            _option(index),
            semantic_action="type_text",
            parameter_schema=schema,
            schema_digest=schema_digest(schema),
            **verification_kwargs("type_text", schema_digest(schema), ("changed",)),
        )

    small = ActionSpace("obs:1", (typed(0, ("a",)), _option(1)))
    large = ActionSpace("obs:1", (typed(0, tuple(f"value-{index}" for index in range(256))), _option(1)))

    assert ActionPager(page_size=1).page(small).visible_action_ids == (
        ActionPager(page_size=1).page(large).visible_action_ids
    )


@pytest.mark.parametrize("destination_count", (16, 17, 512, 513))
def test_destination_routes_are_paged_without_truncation_or_overlap(destination_count: int) -> None:
    destinations = tuple(f"destination:{index:04}" for index in range(destination_count))
    base = _option(0)
    option = replace(
        base,
        semantic_action="drag_to",
        semantic_effects=("changed",),
        destination_required=True,
        eligible_destination_ids=destinations,
        **verification_kwargs("drag_to", base.schema_digest, ("changed",)),
    )

    pager = ActionPager()
    space = ActionSpace("obs:1", (option,))
    seen = []
    cursor = ""
    while True:
        page = pager.page(space, cursor=cursor)
        assert page.visible_action_ids == (option.action_id,)
        seen.extend(page.visible_destination_ids(option.action_id))
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert tuple(seen) == destinations
    assert len(seen) == len(set(seen))


def test_false_positive_query_returns_empty_without_hiding_unqueried_inventory() -> None:
    space = ActionSpace("obs:1", (_option(0),))
    page = ActionPager(page_size=1).page(
        space,
        query="definitely absent operation",
    )

    assert page.visible_action_ids == ()
    assert page.total_count == 0
    assert not page.has_more and not page.next_cursor
    assert ActionPager(page_size=1).page(space).visible_action_ids == ("action:00",)


def test_default_page_orders_explicit_relevance_without_changing_membership() -> None:
    options = (
        _option(0),
        _option(1),
        _option(2, action="read", effect=""),
        _option(3),
    )
    objective = _Objective(
        direct_target_ids=("target:00",),
        enabling_target_ids=("target:01",),
    )

    page = ActionPager(page_size=8).page(ActionSpace("obs:1", options), objective)

    assert page.visible_action_ids == ("action:00", "action:01", "action:02", "action:03")
    assert tuple(item.role for _, item in page.relevance) == (
        ActionRelevanceRole.DIRECT,
        ActionRelevanceRole.ENABLING,
        ActionRelevanceRole.INFORMATION,
        ActionRelevanceRole.OTHER,
    )


@pytest.mark.parametrize(
    "label",
    ("G", "Go", "保存", "!?!", "two   spaces", "x" * 119, "x" * 120, "x" * 121, "x" * 240),
)
def test_exact_public_labels_are_mandatory_query_inclusions(label: str) -> None:
    space = ActionSpace("obs:1", (_option(0), _option(1)))
    page = ActionPager(page_size=1).page(
        space,
        query=label,
        labels={"target:00": label, "target:01": "other"},
    )

    assert page.visible_action_ids == ("action:00",)


def test_query_pages_only_matching_duplicate_labels() -> None:
    space = ActionSpace("obs:1", tuple(_option(index) for index in range(3)))
    labels = {"target:00": "", "target:01": "Duplicate", "target:02": "Duplicate"}
    pager = ActionPager(page_size=1)
    pages = []
    cursor = ""
    while True:
        page = pager.page(space, query="Duplicate", labels=labels, cursor=cursor)
        pages.append(page)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert {action for page in pages for action in page.visible_action_ids} == {
        "action:01",
        "action:02",
    }
    assert ActionPager(page_size=3).page(space).visible_action_ids == (
        "action:00",
        "action:01",
        "action:02",
    )


@given(st.permutations(tuple(range(8))))
def test_prioritized_membership_and_leading_order_ignore_unrelated_permutation_and_page_limit(
    permutation: list[int],
) -> None:
    options = tuple(_option(index) for index in permutation)
    labels = {f"target:{index:02}": f"optional {index}" for index in range(8)}
    labels["target:06"] = "保存!"
    partition = ActionRecallSet().partition(options, labels=labels, query="请立即 保存! then continue")

    assert tuple(item.action_id for item in partition.prioritized) == ("action:06",)
    page = ActionPager(page_size=1).page(
        ActionSpace("obs:1", options),
        _Objective(direct_target_ids=("target:00",)),
        query="请立即 保存! then continue",
        labels=labels,
    )
    assert page.visible_action_ids == ("action:06",)


def test_focus_alone_does_not_turn_a_nonmatch_into_a_query_result() -> None:
    options = (_option(0), _option(1))
    partition = ActionRecallSet().partition(
        options,
        labels={"target:00": "", "target:01": "unrelated"},
        query="missing",
        focused_target_ids=frozenset({"target:00"}),
    )

    assert partition.prioritized == ()
    assert tuple(item.action_id for item in partition.remainder) == (
        "action:00",
        "action:01",
    )


def test_query_include_returns_matches_not_the_private_remainder() -> None:
    options = (_option(0), _option(1), _option(2))

    included = ActionRecallSet().include(
        options,
        labels={
            "target:00": "Open settings",
            "target:01": "Submit order",
            "target:02": "Cancel",
        },
        query="settings",
    )

    assert tuple(item.action_id for item in included) == ("action:00",)


def test_query_does_not_match_short_substrings_inside_unrelated_labels() -> None:
    options = (_option(0), _option(1))
    partition = ActionRecallSet().partition(
        options,
        labels={
            "target:00": "ION",
            "target:01": "Browser navigation",
        },
        roles={
            "target:00": "link",
            "target:01": "browser_context",
        },
        query="address bar URL navigation",
    )

    assert tuple(item.action_id for item in partition.prioritized) == ("action:01",)
    assert tuple(item.action_id for item in partition.remainder) == ("action:00",)


def test_target_terms_outweigh_role_and_operation_terms_in_explicit_control_query() -> None:
    options = (
        _option(0),
        _option(1),
        _option(2),
    )
    partition = ActionRecallSet().partition(
        options,
        labels={
            "target:00": "Africa",
            "target:01": "Portland (Maine)",
            "target:02": "Portland (Maine)",
        },
        roles={
            "target:00": "link",
            "target:01": "link",
            "target:02": "textbox",
        },
        query="Portland (Maine) link activate",
    )

    assert tuple(item.action_id for item in partition.prioritized) == ("action:01",)
    assert {item.action_id for item in partition.remainder} == {"action:00", "action:02"}


def test_exact_label_token_is_not_stolen_by_another_options_operation_facet() -> None:
    options = (
        _option(0, action="activate"),
        _option(1, action="go_back"),
    )

    partition = ActionRecallSet().partition(
        options,
        labels={
            "target:00": "Go",
            "target:01": "Browser navigation",
        },
        roles={
            "target:00": "button",
            "target:01": "browser_context",
        },
        query="Go button",
    )

    assert tuple(item.action_id for item in partition.prioritized) == ("action:00",)
    assert tuple(item.action_id for item in partition.remainder) == ("action:01",)


def test_explicit_control_query_returns_empty_when_only_role_matches() -> None:
    options = (_option(0), _option(1))
    partition = ActionRecallSet().partition(
        options,
        labels={"target:00": "Africa", "target:01": "Agriculture"},
        roles={"target:00": "link", "target:01": "link"},
        query="Portland (Maine) link",
    )

    assert partition.prioritized == ()
    assert {item.action_id for item in partition.remainder} == {"action:00", "action:01"}


def test_explicit_control_query_orders_all_matches_by_target_term_coverage() -> None:
    options = (_option(0), _option(1))
    partition = ActionRecallSet().partition(
        options,
        labels={"target:00": "Wikipedia", "target:01": "Search Wikipedia"},
        roles={"target:00": "link", "target:01": "textbox"},
        query="search wikipedia input",
    )

    assert tuple(item.action_id for item in partition.prioritized) == (
        "action:01",
        "action:00",
    )
    assert partition.remainder == ()


@given(st.permutations(tuple(range(8))))
def test_role_heavy_unrelated_controls_cannot_displace_best_target_match(
    permutation: list[int],
) -> None:
    options = tuple(_option(index) for index in permutation)
    labels = {f"target:{index:02}": f"Unrelated link {index}" for index in range(8)}
    labels["target:06"] = "Portland (Maine)"
    roles = {f"target:{index:02}": "link" for index in range(8)}

    partition = ActionRecallSet().partition(
        options,
        labels=labels,
        roles=roles,
        query="Portland (Maine) link activate",
    )

    assert tuple(item.action_id for item in partition.prioritized) == ("action:06",)


def test_query_bound_plus_one_fails_typed_without_slicing() -> None:
    with pytest.raises(ValueError, match="bound"):
        ActionPager().page(
            ActionSpace("obs:1", (_option(0),)),
            query="x" * (PUBLIC_ACTION_LABEL_MAX_CHARS + 1),
        )


def test_action_reranker_reuses_fuzzy_scores_for_repeated_public_tokens(monkeypatch) -> None:
    options = tuple(_option(index) for index in range(100))
    labels = {option.target_id: "Portland" for option in options}
    calls = 0
    original = action_paging.SequenceMatcher

    def counting_sequence_matcher(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(action_paging, "SequenceMatcher", counting_sequence_matcher)

    ranked = ActionReranker().rank(
        options,
        labels=labels,
        query="Portlnd",
    )

    assert len(ranked) == len(options)
    assert 0 < calls < 10


def test_action_reranker_does_not_fuzzy_match_a_full_task_instruction(monkeypatch) -> None:
    options = tuple(_option(index) for index in range(100))
    labels = {option.target_id: f"Control {index}" for index, option in enumerate(options)}

    def unexpected_sequence_matcher(*_args, **_kwargs):
        raise AssertionError("automatic candidate ranking must not invoke fuzzy search")

    monkeypatch.setattr(action_paging, "SequenceMatcher", unexpected_sequence_matcher)

    ranked = ActionReranker().rank(
        options,
        labels=labels,
        instruction="Open the relevant control and complete the task",
    )

    assert len(ranked) == len(options)
