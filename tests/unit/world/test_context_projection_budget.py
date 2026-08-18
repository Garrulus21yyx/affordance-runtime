import pytest

from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget


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


def test_projection_budget_defaults_are_byte_bounded_without_early_target_cap() -> None:
    budget = ContextProjectionBudget()

    assert budget.max_intent_excerpts == 6
    assert budget.max_targets is None
    assert budget.max_facts == 128
    assert budget.max_action_options == 128
    assert budget.max_total_serialized_bytes == 384 * 1024
