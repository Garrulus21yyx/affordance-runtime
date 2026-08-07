"""Neutral approval-source contracts for Runtime entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol
from uuid import uuid4

from affordance_runtime.contracts import ActionContract, ApprovalToken
from affordance_runtime.immutable import FrozenDict


@dataclass(frozen=True)
class ApprovalPresentation:
    contract_hash: str
    operation_ref: str
    resource_ref: str
    destination_ref: str
    material_parameters: FrozenDict
    effect_class: str
    externality: str
    reversibility: str
    backend: str
    source_refs: tuple[str, ...]
    source_assurance: str
    runtime_risk: str
    uncertainty_codes: tuple[str, ...]


def present_approval(contract: ActionContract) -> ApprovalPresentation:
    signature = contract.runtime_effect_signature
    proof = contract.action_authority_proof
    if signature is None or proof is None or not proof.authorized:
        raise ValueError("approval presentation requires an ALLOW typed authority proof")
    return ApprovalPresentation(
        contract_hash=contract.contract_hash,
        operation_ref=signature.operation_ref or "unproven",
        resource_ref=signature.resource_ref or "unproven",
        destination_ref=signature.destination_ref or "",
        # The exact contract hash already seals the provider-ready route.  Show
        # that same finalized parameter object so approval never describes a
        # narrower payload than the executor will receive.
        material_parameters=FrozenDict(contract.parameters),
        effect_class=signature.effect_class.value if signature.effect_class else "unknown",
        externality=signature.externality.value if signature.externality else "unknown",
        reversibility=signature.reversibility.value if signature.reversibility else "unknown",
        backend=contract.backend,
        source_refs=signature.source_refs,
        source_assurance=signature.assurance.value,
        runtime_risk=signature.runtime_risk.value,
        uncertainty_codes=tuple(
            code for code in proof.reason_codes if "UNPROVEN" in code or "UNKNOWN" in code
        ),
    )


class ApprovalProvider(Protocol):
    def approve(self, contract: ActionContract) -> ApprovalToken | None: ...


@dataclass(frozen=True)
class ConfiguredApprovalProvider:
    """Explicit entrypoint approval source; never derives authority from observations."""

    approver: str
    allowed_capabilities: set[str]
    ttl_s: float = 60.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_capabilities", frozenset(self.allowed_capabilities))

    def approve(self, contract: ActionContract) -> ApprovalToken | None:
        capabilities = [
            item
            for item in contract.required_capabilities
            if item in self.allowed_capabilities
        ]
        if not capabilities:
            return None
        issued_at = time()
        return ApprovalToken(
            token_id=f"approval-{uuid4().hex}",
            run_id=contract.run_id,
            contract_hash=contract.contract_hash,
            snapshot_id=contract.snapshot_id,
            page_revision=contract.page_revision,
            environment_revision=contract.environment_revision,
            capability=capabilities[0],
            approver=self.approver,
            issued_at_s=issued_at,
            expires_at_s=issued_at + self.ttl_s,
        )
