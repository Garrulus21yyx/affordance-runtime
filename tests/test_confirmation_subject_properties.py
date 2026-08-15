from __future__ import annotations

from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions import (
    ActionRisk,
)
from affordance_runtime.risk.contracts import ConfirmationSubject


def _subject() -> ConfirmationSubject:
    return ConfirmationSubject(
        "activate", "target:one", "destination:one", {"value": "one"},
        ("selection_effect",), ("assessed_effect",), ActionRisk.MEDIUM,
        ("change local state",), "local_reversible",
    )


@given(st.sampled_from((
    "semantic_action", "target_id", "destination_id", "parameters",
    "selection_effects", "assessed_effects", "risk", "consequences", "effect_category",
)))
def test_any_material_subject_change_invalidates_old_authorization(field: str) -> None:
    original = _subject()
    changes = {
        "semantic_action": "fill", "target_id": "target:two",
        "destination_id": "destination:two", "parameters": {"value": "two"},
        "selection_effects": ("other_selection",), "assessed_effects": ("other_assessed",),
        "risk": ActionRisk.HIGH, "consequences": ("external consequence",),
        "effect_category": "external",
    }
    assert replace(original, **{field: changes[field]}).subject_id != original.subject_id


def test_private_rebinding_is_not_authorization_material() -> None:
    assert not hasattr(_subject(), "binding_id")
    assert not hasattr(_subject(), "selector")
