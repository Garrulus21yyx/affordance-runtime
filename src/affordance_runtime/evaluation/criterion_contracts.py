"""Runtime-only normalized criterion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.source_profile import ObservationAssurance


class CriterionAdjudicator(StrEnum):
    MECHANICAL = "mechanical"
    SEMANTIC = "semantic"
    USER_ACCEPTANCE = "user_acceptance"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class NormalizedCriterionSpec:
    criterion_id: str
    adjudicator: CriterionAdjudicator
    kind: str
    subject_id: str = ""
    predicate: str = ""
    expected_value: object = None
    state_key: str = ""
    rubric: str = ""
    evidence_scope_target_ids: tuple[str, ...] = ()
    evidence_scope_output_ids: tuple[str, ...] = ()
    required_assurance: str = ""
    output_id: str = ""

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.kind.strip():
            raise ValueError("normalized criterion requires identity and kind")
        if self.required_assurance:
            ObservationAssurance(self.required_assurance)
        if len(self.rubric) > 2_000 or len(self.evidence_scope_target_ids) > 64 or len(self.evidence_scope_output_ids) > 64:
            raise ValueError("normalized criterion exceeds bounded semantic fields")
        if any(
            not item.strip() or len(item) > 240
            for item in (*self.evidence_scope_target_ids, *self.evidence_scope_output_ids)
        ):
            raise ValueError("criterion evidence scope is invalid")
        object.__setattr__(self, "expected_value", freeze_json(self.expected_value))
        object.__setattr__(self, "evidence_scope_target_ids", tuple(self.evidence_scope_target_ids))
        object.__setattr__(self, "evidence_scope_output_ids", tuple(self.evidence_scope_output_ids))
