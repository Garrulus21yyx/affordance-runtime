from dataclasses import replace

from affordance_runtime.risk import RiskDecisionKind, RiskPolicy, semantic_subject_id
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ActionRisk, AdmittedActionSelection


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
        replace(original, semantic_action="set_value"),
        replace(original, target_id="target:other"),
        replace(original, parameters={"mode": "other"}),
        replace(original, semantic_effects=("other_effect",)),
        replace(original, risk=ActionRisk.HIGH),
    )
    assert all(semantic_subject_id(item, consequences=consequences) != baseline for item in variants)
    assert semantic_subject_id(original, destination_id="destination:other", consequences=consequences) != baseline
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
