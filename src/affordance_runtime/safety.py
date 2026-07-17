"""Capability and side-effect gate."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.contracts import ActionContract, RiskLevel, RuntimeErrorCode


@dataclass
class CapabilityGate:
    granted_capabilities: set[str] = field(default_factory=set)
    approval_required_risks: set[RiskLevel] = field(default_factory=lambda: {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE})
    approved_contract_ids: set[str] = field(default_factory=set)

    def check(self, contract: ActionContract) -> RuntimeErrorCode | None:
        missing = [capability for capability in contract.required_capabilities if capability not in self.granted_capabilities]
        if missing:
            return RuntimeErrorCode.CAPABILITY_DENIED
        if contract.risk in self.approval_required_risks and contract.id not in self.approved_contract_ids:
            return RuntimeErrorCode.UNSAFE_ACTION
        return None

