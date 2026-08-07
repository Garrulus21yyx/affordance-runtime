from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime import approval_contracts
from affordance_runtime.approval_contracts import ConfiguredApprovalProvider
from affordance_runtime.contracts import ActionContract, RiskLevel


def _contract(*, required_capabilities: list[str]) -> ActionContract:
    return ActionContract(
        id="export",
        run_id="run-1",
        intent="export report",
        affordance_id="export-button",
        action="click",
        backend="dom",
        environment_revision="environment-1",
        page_revision="page-1",
        locator={"selector": "#export"},
        required_capabilities=required_capabilities,
        risk=RiskLevel.HIGH,
    )


def test_configured_approval_provider_binds_token_to_contract_and_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(approval_contracts, "time", lambda: 1_000.0)
    contract = _contract(required_capabilities=["report.export"])

    token = ConfiguredApprovalProvider(
        approver="operator-1",
        allowed_capabilities={"report.export"},
        ttl_s=45.0,
    ).approve(contract)

    assert token is not None
    assert token.run_id == contract.run_id
    assert token.contract_hash == contract.contract_hash
    assert token.snapshot_id == contract.snapshot_id
    assert token.page_revision == contract.page_revision
    assert token.environment_revision == contract.environment_revision
    assert token.capability == "report.export"
    assert token.approver == "operator-1"
    assert token.issued_at_s == 1_000.0
    assert token.expires_at_s == 1_045.0
    assert token.matches(contract, now_s=1_045.0)
    assert not token.matches(contract, now_s=1_045.001)
    assert not token.matches(
        replace(contract, snapshot_id="snapshot:next", contract_hash=""), now_s=1_001.0
    )
    assert not token.matches(
        replace(contract, environment_revision="environment-2", contract_hash=""), now_s=1_001.0
    )


@pytest.mark.parametrize(
    ("required_capabilities", "allowed_capabilities"),
    [
        (["report.export"], set()),
        (["report.export"], {"settings.write"}),
        ([], {"report.export"}),
    ],
)
def test_configured_approval_provider_returns_none_without_allowed_required_capability(
    required_capabilities: list[str],
    allowed_capabilities: set[str],
) -> None:
    provider = ConfiguredApprovalProvider(
        approver="operator-1",
        allowed_capabilities=allowed_capabilities,
    )

    assert provider.approve(_contract(required_capabilities=required_capabilities)) is None


def test_configured_approval_provider_allowed_capabilities_are_immutable_from_source_set() -> None:
    allowed_capabilities: set[str] = set()
    provider = ConfiguredApprovalProvider(
        approver="operator-1",
        allowed_capabilities=allowed_capabilities,
    )

    allowed_capabilities.add("report.export")

    assert provider.approve(_contract(required_capabilities=["report.export"])) is None
    with pytest.raises(AttributeError):
        provider.allowed_capabilities.add("report.export")  # type: ignore[attr-defined]


def test_configured_approval_provider_selects_first_allowed_capability_in_contract_order() -> None:
    contract = _contract(required_capabilities=["capability.a", "capability.b", "capability.c"])
    provider = ConfiguredApprovalProvider(
        approver="operator-1",
        allowed_capabilities={"capability.c", "capability.b"},
    )

    token = provider.approve(contract)

    assert token is not None
    assert token.capability == "capability.b"
