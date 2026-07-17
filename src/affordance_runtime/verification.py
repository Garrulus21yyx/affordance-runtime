"""Verifier ladder and preflight checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
    VerifierSpec,
)


class Verifier(Protocol):
    kind: str

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        ...


@dataclass
class EvidenceVerifier:
    kind: str = "evidence"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        value = receipt.evidence.get(spec.target)
        return value == spec.expected if spec.strict else bool(value)


@dataclass
class ObservationMetadataVerifier:
    kind: str = "observation_metadata"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        value = observation.metadata.get(spec.target)
        return value == spec.expected if spec.strict else bool(value)


@dataclass
class VerifierLadder:
    """Prefer structural receipts before model or human judgment."""

    verifiers: list[Verifier] = field(default_factory=lambda: [EvidenceVerifier(), ObservationMetadataVerifier()])

    def verify(self, specs: list[VerifierSpec], receipt: ExecutionReceipt, observation: Observation) -> bool:
        if not specs:
            return receipt.success
        for spec in specs:
            verifier = next((item for item in self.verifiers if item.kind == spec.kind), None)
            if verifier is None:
                if spec.strict:
                    return False
                continue
            if not verifier.verify(spec, receipt, observation):
                return False
        return True


def preflight(contract: ActionContract, observation: Observation) -> RuntimeErrorCode | None:
    if contract.environment_revision != observation.environment_revision:
        return RuntimeErrorCode.STALE_OBSERVATION
    for condition in contract.preconditions:
        if condition.required and condition.predicate == "false":
            return RuntimeErrorCode.PRECONDITION_FAILED
    return None


def evaluate_conditions(conditions: list[Any], facts: dict[str, Any]) -> bool:
    """Minimal condition evaluator for benchmark fixtures.

    Conditions are intentionally simple in the skeleton: a predicate passes when
    it names a truthy fact. Real adapters can replace this with DOM/API oracles.
    """

    for condition in conditions:
        predicate = getattr(condition, "predicate", str(condition))
        if predicate and not facts.get(predicate, False):
            return False
    return True

