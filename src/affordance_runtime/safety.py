"""Capability and side-effect gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from affordance_runtime.action_choice_authority import contract_matches_task_authority
from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.contracts import (
    ActionContract,
    ApprovalToken,
    RiskLevel,
    RuntimeErrorCode,
    risk_level_rank,
)
from affordance_runtime.effect_authority_contracts import ActionAuthorityProof, EffectClass
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation


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
        effective_risk = _effective_contract_risk(contract)
        requires_approval = effective_risk in self.approval_required_risks or bool(
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
        effective_risk = _effective_contract_risk(contract)
        requires_approval = effective_risk in self.approval_required_risks or bool(
            set(contract.required_capabilities) & self.approval_required_capabilities
        )
        if requires_approval and contract.id not in self.approved_contract_ids:
            token = next(item for item in self.approval_tokens.values() if item.matches(contract))
            token.consume()
        return None


def _effective_contract_risk(contract: ActionContract) -> RiskLevel:
    proof_risk = getattr(contract.action_authority_proof, "risk", contract.risk)
    if isinstance(proof_risk, RiskLevel) and risk_level_rank(proof_risk) > risk_level_rank(contract.risk):
        return proof_risk
    return contract.risk


@dataclass(frozen=True)
class TaskConstraintPolicy:
    """Enforce typed task authority independently from planner/page suggestions."""

    def check(
        self,
        contract: ActionContract,
        constraints: dict[str, Any],
        task_spec: TaskSpec | None = None,
        canonical_observation: UnifiedObservation | None = None,
    ) -> RuntimeErrorCode | None:
        if task_spec is not None and contract.selected_choice_id:
            proof = self.evaluate_authority(contract, task_spec, canonical_observation)
            if not proof.authorized:
                return RuntimeErrorCode.POLICY_DENIED
        signature = contract.runtime_effect_signature
        effectful = (
            signature.effect_class not in {EffectClass.READ, EffectClass.NAVIGATE, EffectClass.INTERACTION_ONLY}
            if signature is not None
            else bool(contract.required_capabilities)
            or contract.risk != RiskLevel.LOW
            or contract.action in {"download", "write_property", "invoke"}
        )
        if constraints.get("read_only") and effectful:
            return RuntimeErrorCode.POLICY_DENIED
        forbidden = {
            "no_purchase": frozenset({EffectClass.PAY}),
            "no_delete": frozenset({EffectClass.DELETE}),
            "no_external_message": frozenset({EffectClass.SEND, EffectClass.SHARE}),
        }
        for constraint, effect_classes in forbidden.items():
            if constraints.get(constraint) and signature is not None and signature.effect_class in effect_classes:
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

    def evaluate_authority(
        self,
        contract: ActionContract,
        task_spec: TaskSpec,
        canonical_observation: UnifiedObservation | None,
    ) -> ActionAuthorityProof:
        signature = contract.runtime_effect_signature
        if canonical_observation is not None and signature is not None:
            candidate = next(
                (
                    item
                    for item in canonical_observation.bindings
                    if contract.grounding_candidate is not None
                    and item.candidate_id == contract.grounding_candidate.candidate_id
                ),
                None,
            )
            destination_candidate = None
            if contract.gesture_binding is not None:
                destination_candidate = next(
                    (
                        item
                        for item in canonical_observation.bindings
                        if item.candidate_id == contract.gesture_binding.destination.candidate_id
                    ),
                    None,
                )
            signature = classify_action(
                canonical_observation,
                target_id=signature.target_ref,
                destination_id=signature.destination_ref or "",
                action_kind=signature.action_kind,
                parameters=signature.parameter_values,
                candidate=candidate,
                destination_candidate=destination_candidate,
            )
        return contract_matches_task_authority(
            task_spec=task_spec,
            runtime_signature=signature,
            sealed_proof=contract.action_authority_proof,
            requirement_refs=contract.requirement_refs,
            choice_role=contract.choice_role,
        )
