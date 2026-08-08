from affordance_runtime.confirmation import build_confirmation_request
from affordance_runtime.execution import ActionIntent
from affordance_runtime.risk import RiskPolicy
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ActionRisk, AdmittedActionSelection, AgentTargetView, AgentWorldView


def _selection() -> AdmittedActionSelection:
    return AdmittedActionSelection(
        "option:send",
        "observation:1",
        "send",
        "message:quarterly",
        "external",
        ("message_sent",),
        "sha256:schema",
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
    )


def _world(target_label: str = "Quarterly report") -> AgentWorldView:
    return AgentWorldView(
        "observation:1",
        (
            AgentTargetView("message:quarterly", "message", target_label),
            AgentTargetView("person:alice", "person", "Alice"),
        ),
        (),
        {"dom": "complete"},
    )


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
    request = build_confirmation_request(intent, _assessment(selection), _world())

    assert "send" in request.summary
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
    intent = ActionIntent("send", "message:quarterly", dict(selection.parameters), "person:alice")

    first = build_confirmation_request(intent, assessment, _world("Quarterly report"))
    updated = build_confirmation_request(intent, assessment, _world("Q3 report"))

    assert first.subject_id == updated.subject_id
    assert first.summary != updated.summary
    assert "Q3 report (message:quarterly)" in updated.summary
