import pytest

from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget


def test_bounded_section_distinguishes_complete_empty_from_truncated() -> None:
    empty = BoundedSection((), total_count=0, truncated=False)
    truncated = BoundedSection(("one",), total_count=3, truncated=True)

    assert empty.items == () and not empty.truncated
    assert truncated.total_count > len(truncated.items) and truncated.truncated


@pytest.mark.parametrize(
    "section",
    [
        lambda: BoundedSection(("one",), total_count=0, truncated=False),
        lambda: BoundedSection(("one",), total_count=1, truncated=True),
        lambda: BoundedSection(("one",), total_count=2, truncated=False),
    ],
)
def test_bounded_section_rejects_untruthful_metadata(section) -> None:
    with pytest.raises(ValueError):
        section()


def test_projection_budget_defaults_are_fixed_and_bounded() -> None:
    budget = ContextProjectionBudget()

    assert budget.max_intent_excerpts == 6
    assert budget.max_targets == 64
    assert budget.max_facts == 128
    assert budget.max_action_options == 32
    assert budget.max_total_serialized_bytes == 64 * 1024
