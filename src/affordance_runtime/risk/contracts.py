"""Immutable semantic risk assessment contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.space_contracts import (
    ActionRisk,
    AdmittedActionSelection,
)
from affordance_runtime.immutable import freeze_json, to_json_compatible


class RiskDecisionKind(StrEnum):
    ALLOW = "allow"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCK = "block"


@dataclass(frozen=True)
class ConfirmationSubject:
    semantic_action: str
    target_id: str
    destination_id: str
    parameters: Mapping[str, object]
    selection_effects: tuple[str, ...]
    assessed_effects: tuple[str, ...]
    risk: ActionRisk
    consequences: tuple[str, ...]
    effect_category: str

    def __post_init__(self) -> None:
        if not self.semantic_action or not self.target_id or not self.effect_category:
            raise ValueError("confirmation subject requires material semantic identity")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        object.__setattr__(self, "selection_effects", tuple(sorted(self.selection_effects)))
        object.__setattr__(self, "assessed_effects", tuple(sorted(self.assessed_effects)))
        object.__setattr__(self, "consequences", tuple(sorted(self.consequences)))

    @property
    def subject_id(self) -> str:
        canonical = {
            "semantic_action": self.semantic_action,
            "target_id": self.target_id,
            "destination_id": self.destination_id,
            "parameters": to_json_compatible(self.parameters),
            "selection_effects": self.selection_effects,
            "assessed_effects": self.assessed_effects,
            "risk": self.risk.value,
            "consequences": self.consequences,
            "effect_category": self.effect_category,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"semantic-subject:sha256:{digest}"

    @classmethod
    def from_selection(
        cls,
        selection: AdmittedActionSelection,
        *,
        assessed_effects: tuple[str, ...],
        consequences: tuple[str, ...],
        effective_risk: ActionRisk,
    ) -> ConfirmationSubject:
        return cls(
            selection.semantic_action,
            selection.target_id,
            selection.destination_id,
            dict(selection.parameters),
            tuple(selection.semantic_effects),
            assessed_effects,
            effective_risk,
            consequences,
            selection.effect_category,
        )


@dataclass(frozen=True)
class RiskAssessment:
    decision: RiskDecisionKind
    risk: ActionRisk
    semantic_effects: tuple[str, ...]
    consequences: tuple[str, ...]
    subject_id: str
    reason: str
    subject: ConfirmationSubject

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RiskDecisionKind):
            raise TypeError("decision must be a RiskDecisionKind")
        if not isinstance(self.risk, ActionRisk):
            raise TypeError("risk must be an ActionRisk")
        if not self.subject_id.strip() or not self.reason.strip():
            raise ValueError("risk assessment requires subject identity and reason")
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "consequences", tuple(self.consequences))
        if not isinstance(self.subject, ConfirmationSubject):
            raise TypeError("risk assessment requires a canonical confirmation subject")
        if self.subject_id != self.subject.subject_id:
            raise ValueError("risk assessment subject_id does not match canonical semantics")
        if self.risk is not self.subject.risk:
            raise ValueError("risk assessment risk does not match canonical semantics")
        if tuple(sorted(self.semantic_effects)) != self.subject.assessed_effects:
            raise ValueError("risk assessment effects do not match canonical semantics")
        if tuple(sorted(self.consequences)) != self.subject.consequences:
            raise ValueError("risk assessment consequences do not match canonical semantics")


def semantic_subject_id(
    selection: AdmittedActionSelection,
    *,
    consequences: tuple[str, ...],
    effective_risk: ActionRisk | None = None,
) -> str:
    return ConfirmationSubject.from_selection(
        selection,
        assessed_effects=tuple(selection.semantic_effects),
        consequences=consequences,
        effective_risk=effective_risk or selection.risk,
    ).subject_id
