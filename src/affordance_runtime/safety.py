"""Capability and side-effect gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from affordance_runtime.contracts import ActionContract, ApprovalToken, RiskLevel, RuntimeErrorCode
from affordance_runtime.task_intake import TaskSpec


@dataclass
class CapabilityGate:
    granted_capabilities: set[str] = field(default_factory=set)
    approval_required_risks: set[RiskLevel] = field(default_factory=lambda: {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE})
    approval_required_capabilities: set[str] = field(default_factory=set)
    approval_tokens: dict[str, ApprovalToken] = field(default_factory=dict)
    # Compatibility-only debug approvals. Task-level coordination should use
    # bound, expiring ApprovalTokens.
    approved_contract_ids: set[str] = field(default_factory=set)

    def check(self, contract: ActionContract) -> RuntimeErrorCode | None:
        missing = [
            capability for capability in contract.required_capabilities if capability not in self.granted_capabilities
        ]
        if missing:
            return RuntimeErrorCode.CAPABILITY_DENIED
        requires_approval = contract.risk in self.approval_required_risks or bool(
            set(contract.required_capabilities) & self.approval_required_capabilities
        )
        if requires_approval:
            if contract.id in self.approved_contract_ids:
                return None
            if not any(token.matches(contract) for token in self.approval_tokens.values()):
                return RuntimeErrorCode.APPROVAL_REQUIRED
        return None

    def authorize(self, contract: ActionContract) -> RuntimeErrorCode | None:
        """Check policy and atomically consume a matching approval token."""

        error = self.check(contract)
        if error is not None:
            return error
        requires_approval = contract.risk in self.approval_required_risks or bool(
            set(contract.required_capabilities) & self.approval_required_capabilities
        )
        if requires_approval and contract.id not in self.approved_contract_ids:
            token = next(item for item in self.approval_tokens.values() if item.matches(contract))
            token.consume()
        return None


@dataclass(frozen=True)
class TaskConstraintPolicy:
    """Enforce task authority independently from planner/page suggestions."""

    def check(
        self,
        contract: ActionContract,
        constraints: dict[str, Any],
        task_spec: TaskSpec | None = None,
    ) -> RuntimeErrorCode | None:
        if task_spec is not None and contract.selected_choice_id:
            known_requirements = {item.requirement_id for item in task_spec.requirements}
            if not contract.requirement_refs or set(contract.requirement_refs) - known_requirements:
                return RuntimeErrorCode.POLICY_DENIED
            if set(contract.effect_authorization_refs) - set(task_spec.allowed_effect_refs):
                return RuntimeErrorCode.POLICY_DENIED
            if set(contract.effect_authorization_refs) - set(contract.requirement_refs):
                return RuntimeErrorCode.POLICY_DENIED
            if contract.effectful and not contract.effect_authorization_refs:
                return RuntimeErrorCode.POLICY_DENIED
        effectful = (
            bool(contract.required_capabilities)
            or contract.risk != RiskLevel.LOW
            or contract.action
            in {
                "download",
                "write_property",
                "invoke",
            }
        )
        if constraints.get("read_only") and effectful:
            return RuntimeErrorCode.POLICY_DENIED
        # Idempotency and compensation constrain recovery after an attempted
        # effect; their absence does not revoke authority for the first,
        # explicitly requested execution.  The SAR-8 recovery policy fails
        # closed rather than retrying a non-idempotent contract blindly.
        text = " ".join([contract.intent, contract.action, *contract.required_capabilities]).lower()
        forbidden = {
            "no_purchase": ("purchase", "payment", "checkout", "pay"),
            "no_delete": ("delete", "remove", "destroy"),
            "no_external_message": ("message", "email.send", "send_email", "post_message"),
        }
        for constraint, terms in forbidden.items():
            if constraints.get(constraint) and any(term in text for term in terms):
                return RuntimeErrorCode.POLICY_DENIED
        allowed_domains = constraints.get("allowed_domains")
        if allowed_domains:
            target_url = str(
                contract.parameters.get("url") or contract.locator.get("url") or contract.locator.get("href") or ""
            )
            hostname = urlsplit(target_url).hostname if target_url else None
            if hostname and hostname not in set(str(item) for item in allowed_domains):
                return RuntimeErrorCode.POLICY_DENIED
        return None
