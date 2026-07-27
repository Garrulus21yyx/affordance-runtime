"""Neutral approval-source contracts for Runtime entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol
from uuid import uuid4

from affordance_runtime.contracts import ActionContract, ApprovalToken


class ApprovalProvider(Protocol):
    def approve(self, contract: ActionContract) -> ApprovalToken | None: ...


@dataclass(frozen=True)
class ConfiguredApprovalProvider:
    """Explicit entrypoint approval source; never derives authority from observations."""

    approver: str
    allowed_capabilities: set[str]
    ttl_s: float = 60.0

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
            page_revision=contract.page_revision,
            capability=capabilities[0],
            approver=self.approver,
            issued_at_s=issued_at,
            expires_at_s=issued_at + self.ttl_s,
        )
