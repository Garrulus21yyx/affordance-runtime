from __future__ import annotations

import pytest

from affordance_runtime.planning import PlannerActionKind


def _choices():
    from affordance_runtime.choice_contracts import ActionChoice

    return tuple(
        ActionChoice(
            choice_id=f"choice:{index}",
            task_revision=3,
            state_version=7,
            snapshot_id="observation:7",
            active_step_id="step:current",
            action_kind=PlannerActionKind.ACTIVATE,
            target_id=f"target:{index}",
            criterion_ids=("criterion:done",),
        )
        for index in range(4)
    )


@pytest.mark.parametrize("realization", ["eager", "lazy", "indexed"])
@pytest.mark.parametrize("page_size", [1, 2, 10])
def test_catalog_semantics_are_invariant_to_realization_and_presentation(
    realization: str,
    page_size: int,
) -> None:
    """Failure: model/materialization budgets used to own Runtime membership.

    Owner: ActionChoiceCatalog. Existing builder tests only covered eager tuples
    and could not detect a digest/order change caused by page policy. This test
    retires when Catalog has a stronger shared conformance suite.
    """
    from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
    from affordance_runtime.choice_presentation import ChoicePresentationProjector

    catalog = ActionChoiceCatalog.from_choices(
        task_revision=3,
        plan_revision=2,
        state_version=7,
        observation_ref="observation:7",
        active_step_id="step:current",
        choices=_choices(),
        realization=realization,
    )
    page = ChoicePresentationProjector(page_size=page_size).project(catalog)

    assert catalog.count == 4
    assert tuple(choice.choice_id for choice in catalog.page(None, 10).choices) == (
        "choice:0",
        "choice:1",
        "choice:2",
        "choice:3",
    )
    assert (
        catalog.catalog_digest
        == ActionChoiceCatalog.from_choices(
            task_revision=3,
            plan_revision=2,
            state_version=7,
            observation_ref="observation:7",
            active_step_id="step:current",
            choices=_choices(),
            realization="eager",
        ).catalog_digest
    )
    assert page.total_choice_count == 4
    assert page.included_choice_count == min(page_size, 4)


def test_selection_rejects_catalog_member_not_presented_on_current_page() -> None:
    """Failure: a guessed hidden catalog ID could previously be dispatched.

    Owner: ActionSelectionValidator. Existing validation only checked full-set
    membership, so it could not distinguish unknown from unpresented IDs. The
    test retires only if this invariant moves into a shared selection suite.
    """
    from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
    from affordance_runtime.action_selection import (
        ActionSelectionError,
        ActionSelectionValidator,
        SelectionRejectionCode,
    )
    from affordance_runtime.choice_contracts import SelectChoice
    from affordance_runtime.choice_presentation import ChoicePresentationProjector

    catalog = ActionChoiceCatalog.from_choices(
        task_revision=3,
        plan_revision=2,
        state_version=7,
        observation_ref="observation:7",
        active_step_id="step:current",
        choices=_choices(),
    )
    page = ChoicePresentationProjector(page_size=1).project(catalog)

    with pytest.raises(ActionSelectionError) as exc_info:
        ActionSelectionValidator().validate(
            SelectChoice("choice:3", "guessed hidden id"),
            catalog,
            page,
        )

    assert exc_info.value.code == SelectionRejectionCode.UNPRESENTED_CHOICE_ID


def test_choice_serializer_projects_only_the_displayed_page_without_runtime_handles() -> None:
    from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
    from affordance_runtime.choice_contracts import ChoicePlanningRequest
    from affordance_runtime.choice_presentation import ChoicePresentationProjector
    from affordance_runtime.planning_request_serializer import (
        serialize_choice_planning_request,
    )

    catalog = ActionChoiceCatalog.from_choices(
        task_revision=3,
        plan_revision=2,
        state_version=7,
        observation_ref="observation:7",
        active_step_id="step:current",
        choices=_choices(),
    )
    page = ChoicePresentationProjector(page_size=2).project(catalog)
    payload = serialize_choice_planning_request(ChoicePlanningRequest(3, 2, "step:current", catalog.ref, page))

    assert [item["choice_id"] for item in payload["choices"]] == [
        "choice:0",
        "choice:1",
    ]
    encoded = repr(payload).casefold()
    for forbidden in ("selector", "coordinate", "backend", "locator", "approval"):
        assert forbidden not in encoded
