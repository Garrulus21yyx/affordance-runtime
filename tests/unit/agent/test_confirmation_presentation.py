from affordance_runtime.actions import (
    ActionRisk,
    AdmittedActionSelection,
)
from affordance_runtime.confirmation import build_confirmation_request
from affordance_runtime.execution import ActionIntent
from affordance_runtime.risk import RiskPolicy
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.task import RiskProfile, TaskGoal
from tests.support.action_contracts import verification_kwargs

_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _selection() -> AdmittedActionSelection:
    return AdmittedActionSelection(
        "option:send",
        "observation:1",
        "drag_to",
        "message:quarterly",
        "external",
        ("message_sent",),
        schema_digest(_SCHEMA),
        ("binding:private",),
        ActionRisk.LOW,
        True,
        {
            "text": "Quarterly report attached",
            "api_token": "super-secret-value",
            "metadata": {"priority": "high", "nested": {"too": "deep"}},
        },
        "person:alice",
        True,
        ("person:alice",),
        **verification_kwargs("drag_to", schema_digest(_SCHEMA), ("message_sent",)),
    )


def _labels(target_label: str = "Quarterly report") -> dict[str, str]:
    return {"message:quarterly": target_label, "person:alice": "Alice"}


def _assessment(selection: AdmittedActionSelection):
    task = TaskGoal(
        "send",
        "Send report",
        allowed_effects=("message_sent",),
        risk_profile=RiskProfile.HIGH,
    )
    return RiskPolicy().assess(task, selection)


def test_confirmation_summary_presents_semantics_and_redacts_secret_like_parameters() -> None:
    selection = _selection()
    intent = ActionIntent(
        selection.semantic_action,
        selection.target_id,
        dict(selection.parameters),
        selection.destination_id,
    )
    request = build_confirmation_request(intent, _assessment(selection), _labels())

    assert "drag_to" in request.summary
    assert "Quarterly report (message:quarterly)" in request.summary
    assert "Alice (person:alice)" in request.summary
    assert "Quarterly report attached" in request.summary
    assert "[REDACTED]" in request.summary
    assert "super-secret-value" not in request.summary
    assert "super-secret-value" not in repr(request)
    assert "Risk: high" in request.summary
    assert "message_sent" in request.summary
    assert "affect an external system" in request.summary


def test_display_label_change_updates_summary_without_changing_subject() -> None:
    selection = _selection()
    assessment = _assessment(selection)
    intent = ActionIntent("drag_to", "message:quarterly", dict(selection.parameters), "person:alice")

    first = build_confirmation_request(intent, assessment, _labels("Quarterly report"))
    updated = build_confirmation_request(intent, assessment, _labels("Q3 report"))

    assert first.subject_id == updated.subject_id
    assert first.summary != updated.summary
    assert "Q3 report (message:quarterly)" in updated.summary
