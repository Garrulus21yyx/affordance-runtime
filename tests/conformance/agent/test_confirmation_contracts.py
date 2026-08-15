import pytest

from affordance_runtime.actions import (
    ActionRisk,
    AdmittedActionSelection,
)
from affordance_runtime.confirmation import (
    ConfirmationDecision,
    ConfirmationDecisionKind,
    build_confirmation_request,
)
from affordance_runtime.execution import ActionIntent
from affordance_runtime.risk import RiskPolicy
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    AgentTargetView,
    AgentWorldView,
)


def test_confirmation_decision_rejects_non_enum_kind() -> None:
    with pytest.raises(TypeError, match="ConfirmationDecisionKind"):
        ConfirmationDecision("confirmation:1", "subject:1", "not-a-decision")  # type: ignore[arg-type]


def _selection() -> AdmittedActionSelection:
    return AdmittedActionSelection(
        "option:private-selector:#old",
        "observation:screenshot-digest",
        "activate",
        "target:shared",
        "local_reversible",
        ("shared_state_enabled",),
        "sha256:schema",
        ("binding:https://private.example/action",),
        ActionRisk.MEDIUM,
        True,
        {},
    )


def _request():
    selection = _selection()
    task = TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.MEDIUM,
    )
    assessment = RiskPolicy().assess(task, selection)
    intent = ActionIntent(selection.semantic_action, selection.target_id, dict(selection.parameters))
    world = AgentWorldView(
        "observation:display",
        (AgentTargetView(selection.target_id, "button", "Shared state"),),
        (),
        {"dom": "complete"},
    )
    return build_confirmation_request(intent, assessment, world)


def test_confirmation_request_contains_only_semantic_confirmation_subject() -> None:
    request = _request()
    representation = repr(request)

    assert request.subject_id.startswith("semantic-subject:sha256:")
    assert request.intent.semantic_action == "activate"
    assert request.risk == ActionRisk.MEDIUM
    for private in ("selector", "coordinate", "bbox", "href", "method", "backend", "credential", "screenshot"):
        assert private not in representation.lower()


def test_confirmation_decision_binds_confirmation_and_subject_identity() -> None:
    request = _request()
    decision = ConfirmationDecision(
        request.confirmation_id,
        request.subject_id,
        ConfirmationDecisionKind.CONFIRM,
    )

    assert decision.matches(request)
    assert not ConfirmationDecision(
        "confirmation:other",
        request.subject_id,
        ConfirmationDecisionKind.CONFIRM,
    ).matches(request)
    assert not ConfirmationDecision(
        request.confirmation_id,
        "semantic-subject:sha256:other",
        ConfirmationDecisionKind.CONFIRM,
    ).matches(request)
