from dataclasses import replace

import pytest

from affordance_runtime.actions import (
    ActionRisk,
    AdmittedActionSelection,
)
from affordance_runtime.confirmation import build_confirmation_request
from affordance_runtime.execution import ActionIntent
from affordance_runtime.risk import RiskAssessment, RiskDecisionKind, RiskPolicy, semantic_subject_id
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    AgentTargetView,
    AgentWorldView,
)


@pytest.mark.parametrize(
    ("decision", "risk"),
    (("unexpected", ActionRisk.MEDIUM), (RiskDecisionKind.ALLOW, "medium")),
)
def test_risk_assessment_rejects_non_enum_values(decision, risk) -> None:
    with pytest.raises(TypeError):
        RiskAssessment(decision, risk, (), (), "subject:1", "bounded")


def _selection(**changes) -> AdmittedActionSelection:
    selection = AdmittedActionSelection(
        "option:old-observation",
        "observation:old",
        "activate",
        "target:shared",
        "local_reversible",
        ("shared_state_enabled",),
        "sha256:schema",
        ("binding:selector:#old",),
        ActionRisk.MEDIUM,
        True,
        {"mode": "normal"},
    )
    if {
        "semantic_action",
        "semantic_effects",
        "schema_digest",
        "observation_barrier",
    }.intersection(changes):
        changes.setdefault("verification_contract_digest", "")
    return replace(selection, **changes)


def _task(**changes) -> TaskGoal:
    task = TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )
    return replace(task, **changes)


def test_semantic_subject_ignores_observation_option_and_binding_identity() -> None:
    assessment = RiskPolicy().assess(_task(), _selection())
    rebound = _selection(
        action_id="option:new-observation",
        observation_id="observation:new",
        eligible_binding_ids=("binding:selector:#new",),
    )

    assert RiskPolicy().assess(_task(), rebound).subject_id == assessment.subject_id


def test_semantic_subject_changes_for_each_confirmed_semantic_field() -> None:
    original = _selection()
    consequences = ("change local state",)
    baseline = semantic_subject_id(original, consequences=consequences)

    variants = (
        replace(
            original,
            semantic_action="set_value",
            verification_contract_digest="",
        ),
        replace(original, target_id="target:other"),
        replace(original, parameters={"mode": "other"}),
        replace(
            original,
            semantic_effects=("other_effect",),
            verification_contract_digest="",
        ),
        replace(original, risk=ActionRisk.HIGH),
    )
    assert all(semantic_subject_id(item, consequences=consequences) != baseline for item in variants)
    assert semantic_subject_id(
        replace(
            original,
            destination_id="destination:other",
            eligible_destination_ids=("destination:other",),
        ),
        consequences=consequences,
    ) != baseline
    assert semantic_subject_id(original, consequences=("affect an external system",)) != baseline


def test_risk_policy_enforces_runtime_floor_and_forbidden_effects() -> None:
    policy = RiskPolicy()

    assert policy.assess(_task(), _selection()).decision == RiskDecisionKind.NEEDS_CONFIRMATION
    assert (
        policy.assess(
            _task(risk_profile=RiskProfile.HIGH),
            _selection(risk=ActionRisk.LOW),
        ).decision
        == RiskDecisionKind.NEEDS_CONFIRMATION
    )
    blocked = policy.assess(
        _task(forbidden_effects=("shared_state_enabled",)),
        _selection(),
    )
    assert blocked.decision == RiskDecisionKind.BLOCK


@pytest.mark.parametrize(
    ("task_risk", "option_risk", "effective_risk"),
    (
        (RiskProfile.MEDIUM, ActionRisk.LOW, ActionRisk.MEDIUM),
        (RiskProfile.HIGH, ActionRisk.LOW, ActionRisk.HIGH),
        (RiskProfile.LOW, ActionRisk.HIGH, ActionRisk.HIGH),
        (RiskProfile.HIGH, ActionRisk.IRREVERSIBLE, ActionRisk.IRREVERSIBLE),
    ),
)
def test_risk_assessment_uses_one_effective_risk(
    task_risk: RiskProfile,
    option_risk: ActionRisk,
    effective_risk: ActionRisk,
) -> None:
    selection = _selection(risk=option_risk)
    assessment = RiskPolicy().assess(_task(risk_profile=task_risk), selection)
    request = build_confirmation_request(
        ActionIntent(selection.semantic_action, selection.target_id, dict(selection.parameters)),
        assessment,
        AgentWorldView(
            "observation:display",
            (AgentTargetView(selection.target_id, "button", "Shared state"),),
            (),
            {"fixture": "complete"},
        ),
    )

    assert assessment.decision == RiskDecisionKind.NEEDS_CONFIRMATION
    assert assessment.risk == effective_risk
    assert request.risk == effective_risk
    assert f"Risk: {effective_risk.value}" in request.summary


def test_task_risk_floor_participates_in_semantic_subject() -> None:
    selection = _selection(risk=ActionRisk.LOW)
    low = RiskPolicy().assess(_task(risk_profile=RiskProfile.LOW), selection)
    high = RiskPolicy().assess(_task(risk_profile=RiskProfile.HIGH), selection)

    assert low.risk == ActionRisk.LOW
    assert high.risk == ActionRisk.HIGH
    assert low.subject_id != high.subject_id


def test_low_read_and_low_allowed_effect_are_allowed() -> None:
    policy = RiskPolicy()
    read_task = TaskGoal("read", "Read state")
    read = _selection(
        semantic_action="read",
        effect_category="observation",
        semantic_effects=(),
        risk=ActionRisk.LOW,
        parameters={},
    )
    low_effect = _selection(risk=ActionRisk.LOW)

    assert policy.assess(read_task, read).decision == RiskDecisionKind.ALLOW
    assert policy.assess(_task(), low_effect).decision == RiskDecisionKind.ALLOW


def test_read_only_risk_policy_allows_only_effect_free_low_risk_interaction() -> None:
    policy = RiskPolicy()
    task = TaskGoal("read", "Reveal local details")
    interaction = _selection(
        effect_category="interaction",
        semantic_effects=(),
        risk=ActionRisk.LOW,
        parameters={},
    )

    assert policy.assess(task, interaction).decision == RiskDecisionKind.ALLOW
    assert policy.assess(
        task,
        replace(
            interaction,
            semantic_effects=("update",),
            verification_contract_digest="",
        ),
    ).decision == RiskDecisionKind.BLOCK
