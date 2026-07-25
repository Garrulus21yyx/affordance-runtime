"""Code-owned, generic canonical obligation construction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import Field

from affordance_runtime.source_ledger import SourceLedger
from affordance_runtime.task_intake import (
    EvidenceRequirement,
    GraphConstructionSource,
    OperationClass,
    SourcedTaskClaim,
    StrictModel,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
)


class CanonicalEffectInput(StrictModel):
    operation_class: OperationClass
    target: str = Field(min_length=1, max_length=480)
    source_unit_ids: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[EvidenceRequirement, ...] = Field(min_length=1)


class CanonicalObligationGraph(StrictModel):
    compiler_version: str
    claims: tuple[SourcedTaskClaim, ...]
    obligations: tuple[TaskObligationSpec, ...]


@dataclass(frozen=True)
class CanonicalObligationCompiler:
    """Compile source-bound typed effect inputs without provider graph ids."""

    compiler_version: str = "canonical-obligation-v1"

    def compile(
        self,
        source_ledger: SourceLedger,
        effects: tuple[CanonicalEffectInput, ...],
    ) -> CanonicalObligationGraph:
        if not effects:
            raise ValueError("canonical obligation compilation requires effects")
        known_units = {unit.source_unit_id for unit in source_ledger.units}
        claims: list[SourcedTaskClaim] = []
        obligations: list[TaskObligationSpec] = []
        for effect in effects:
            if set(effect.source_unit_ids) - known_units:
                raise ValueError("canonical effect references unknown source unit")
            if any(set(item.source_constraints) - known_units for item in effect.evidence):
                raise ValueError("canonical evidence references unknown source unit")
            identity = _identity(effect)
            claim_id = f"claim:{identity}"
            obligation_id = f"obligation:{identity}"
            read = effect.operation_class in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
            relation = TaskObligationRelation.IS_AVAILABLE if read else TaskObligationRelation.IS_COMPLETED
            claims.append(SourcedTaskClaim(
                claim_id=claim_id,
                kind=TaskClaimKind.EFFECT,
                statement=f"{effect.operation_class.value}:{effect.target}",
                source_ref=effect.source_unit_ids[0],
                source_unit_ids=effect.source_unit_ids,
                construction_source=GraphConstructionSource.CANONICAL_COMPILER,
            ))
            obligations.append(TaskObligationSpec(
                obligation_id=obligation_id,
                kind=TaskObligationKind.PREDICATE if read else TaskObligationKind.EFFECT,
                subject=effect.target,
                relation=relation,
                claim_ids=(claim_id,),
                evidence_requirements=tuple(f"{item.kind.value}:{item.subject}" for item in effect.evidence),
                typed_evidence_requirements=effect.evidence,
                terminal=True,
                construction_source=GraphConstructionSource.CANONICAL_COMPILER,
            ))
        return CanonicalObligationGraph(
            compiler_version=self.compiler_version,
            claims=tuple(claims),
            obligations=tuple(obligations),
        )


def _identity(effect: CanonicalEffectInput) -> str:
    payload = json.dumps(effect.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
