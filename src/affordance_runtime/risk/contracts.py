"""Immutable semantic risk assessment contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import ActionRisk, AdmittedActionSelection


class RiskDecisionKind(StrEnum):
    ALLOW = "allow"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCK = "block"


@dataclass(frozen=True)
class RiskAssessment:
    decision: RiskDecisionKind
    risk: ActionRisk
    semantic_effects: tuple[str, ...]
    consequences: tuple[str, ...]
    subject_id: str
    reason: str

    def __post_init__(self) -> None:
        if not self.subject_id.strip() or not self.reason.strip():
            raise ValueError("risk assessment requires subject identity and reason")
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "consequences", tuple(self.consequences))


def semantic_subject_id(
    selection: AdmittedActionSelection,
    *,
    destination_id: str = "",
    consequences: tuple[str, ...],
) -> str:
    canonical = {
        "semantic_action": selection.semantic_action,
        "semantic_target_id": selection.target_id,
        "destination_id": destination_id,
        "parameters": to_json_compatible(selection.parameters),
        "semantic_effects": sorted(selection.semantic_effects),
        "risk": selection.risk.value,
        "consequences": sorted(consequences),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"semantic-subject:sha256:{digest}"
