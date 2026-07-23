from time import time

from affordance_runtime.contracts import ActionContract, ApprovalToken, RiskLevel, RuntimeErrorCode
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy


def _high_risk_contract() -> ActionContract:
    return ActionContract(
        id="export",
        run_id="run-1",
        intent="export report",
        affordance_id="export-button",
        action="click",
        backend="dom",
        environment_revision="rev-1",
        page_revision="rev-1",
        locator={"selector": "#export"},
        required_capabilities=["report.export"],
        risk=RiskLevel.HIGH,
    )


def test_approval_is_bound_and_single_use() -> None:
    contract = _high_risk_contract()
    token = ApprovalToken(
        token_id="approval-1",
        run_id=contract.run_id,
        contract_hash=contract.contract_hash,
        page_revision=contract.page_revision,
        capability="report.export",
        approver="user-1",
        issued_at_s=time(),
        expires_at_s=time() + 30,
    )
    gate = CapabilityGate(
        granted_capabilities={"report.export"},
        approval_tokens={token.token_id: token},
    )

    assert gate.authorize(contract) is None
    assert token.consumed
    assert gate.check(contract) == RuntimeErrorCode.APPROVAL_REQUIRED


def test_approval_fails_when_environment_binding_changes() -> None:
    contract = _high_risk_contract()
    token = ApprovalToken(
        token_id="approval-1",
        run_id=contract.run_id,
        contract_hash=contract.contract_hash,
        page_revision="other-revision",
        capability="report.export",
        approver="user-1",
        issued_at_s=time(),
        expires_at_s=time() + 30,
    )
    gate = CapabilityGate(granted_capabilities={"report.export"}, approval_tokens={token.token_id: token})

    assert gate.check(contract) == RuntimeErrorCode.APPROVAL_REQUIRED


def test_task_constraints_deny_effects_and_forbidden_domains() -> None:
    contract = _high_risk_contract()
    policy = TaskConstraintPolicy()

    assert policy.check(contract, {"read_only": True}) == RuntimeErrorCode.POLICY_DENIED
    external = ActionContract(
        id="navigate",
        intent="navigate",
        affordance_id="link",
        action="navigate",
        backend="dom",
        environment_revision="rev-1",
        locator={"url": "https://outside.example/path"},
    )
    assert policy.check(external, {"allowed_domains": ["fixture.example"]}) == RuntimeErrorCode.POLICY_DENIED


def test_task_constraint_can_require_approval_for_medium_risk_capability() -> None:
    contract = ActionContract(
        id="settings",
        run_id="run-1",
        intent="write settings",
        affordance_id="save",
        action="click",
        backend="dom",
        environment_revision="rev-1",
        locator={"selector": "#save"},
        required_capabilities=["settings.write.reversible"],
        risk=RiskLevel.MEDIUM,
    )
    gate = CapabilityGate(
        granted_capabilities={"settings.write.reversible"},
        approval_required_capabilities={"settings.write.reversible"},
    )

    assert gate.check(contract) == RuntimeErrorCode.APPROVAL_REQUIRED


def test_first_requested_effect_does_not_require_a_retry_mechanism() -> None:
    contract = ActionContract(
        id="activate",
        intent="activate target",
        affordance_id="target",
        action="click",
        backend="dom",
        environment_revision="rev-1",
        locator={"selector": "#target"},
        risk=RiskLevel.MEDIUM,
    )

    assert TaskConstraintPolicy().check(contract, {}) is None
