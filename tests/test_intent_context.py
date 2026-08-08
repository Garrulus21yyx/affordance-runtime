import pytest

from affordance_runtime.model_boundary.budgets import ContextProjectionBudget
from affordance_runtime.model_boundary.context_builder import project_intent_context
from affordance_runtime.task import IntentContext, IntentExcerpt, IntentSourceKind


def test_intent_context_is_context_only_and_bounded_for_model() -> None:
    intent = IntentContext(
        tuple(
            IntentExcerpt(
                text=f"excerpt {index} " + "x" * 300,
                source_kind=IntentSourceKind.USER,
                source_ref=f"request:{index}",
                digest=f"sha256:{index:064x}",
            )
            for index in range(8)
        )
    )

    view = project_intent_context(intent, ContextProjectionBudget(max_intent_excerpts=2, max_intent_chars=40))

    assert intent.authority == "context_only"
    assert len(view.excerpts.items) == 2
    assert view.excerpts.total_count == 8
    assert view.excerpts.truncated
    assert sum(len(item.text) for item in view.excerpts.items) <= 40
    assert "context_only" in repr(view)


def test_intent_excerpt_requires_stable_source_and_digest() -> None:
    with pytest.raises(ValueError):
        IntentExcerpt("text", IntentSourceKind.USER, "", "sha256:" + "a" * 64)
