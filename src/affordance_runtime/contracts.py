"""Core contracts for planner-neutral GUI execution.

This module is the cleaned-up successor of the Modular Action System contracts.
It keeps the old repository's typed affordance idea, then adds environment
revision, lease, verifier, risk, and evidence fields needed by the new runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from typing import Any


class Surface(StrEnum):
    DOM = "dom"
    VISUAL = "visual"
    ACCESSIBILITY = "accessibility"
    WOT = "wot"
    API = "api"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


class RuntimeErrorCode(StrEnum):
    STALE_OBSERVATION = "stale_observation"
    PRECONDITION_FAILED = "precondition_failed"
    CAPABILITY_DENIED = "capability_denied"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    UNSAFE_ACTION = "unsafe_action"


@dataclass(frozen=True)
class Condition:
    predicate: str
    description: str = ""
    required: bool = True


@dataclass(frozen=True)
class Observation:
    environment_revision: str
    url: str = ""
    dom_hash: str = ""
    screenshot_ref: str = ""
    accessibility_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AffordanceLease:
    """Validity boundary for an affordance snapshot."""

    environment_revision: str
    issued_at_s: float
    ttl_ms: int = 2_000
    provenance: list[str] = field(default_factory=list)
    confidence: float = 1.0

    @classmethod
    def issue(
        cls,
        *,
        environment_revision: str,
        ttl_ms: int = 2_000,
        provenance: list[str] | None = None,
        confidence: float = 1.0,
    ) -> "AffordanceLease":
        return cls(
            environment_revision=environment_revision,
            issued_at_s=time(),
            ttl_ms=ttl_ms,
            provenance=provenance or [],
            confidence=confidence,
        )

    def is_current(self, observation: Observation, *, now_s: float | None = None) -> bool:
        current_time = time() if now_s is None else now_s
        age_ms = (current_time - self.issued_at_s) * 1000
        return self.environment_revision == observation.environment_revision and age_ms <= self.ttl_ms


@dataclass(frozen=True)
class Affordance:
    id: str
    surface: Surface
    role: str
    label: str
    action: str
    locator: dict[str, Any]
    lease: AffordanceLease
    confidence: float = 1.0
    state: dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VerifierSpec:
    kind: str
    target: str
    expected: Any = True
    strict: bool = True
    evidence_key: str = ""


@dataclass(frozen=True)
class ActionContract:
    """Executable action with explicit state, safety, and verification bounds."""

    id: str
    intent: str
    affordance_id: str
    action: str
    backend: str
    environment_revision: str
    locator: dict[str, Any]
    preconditions: list[Condition] = field(default_factory=list)
    expected_effects: list[Condition] = field(default_factory=list)
    verifier_plan: list[VerifierSpec] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW
    idempotency_key: str = ""
    compensation: str | None = None
    timeout_ms: int = 5_000
    fallback_backends: list[str] = field(default_factory=list)

    @classmethod
    def from_affordance(
        cls,
        affordance: Affordance,
        *,
        intent: str,
        backend: str,
        expected_effects: list[Condition] | None = None,
        verifier_plan: list[VerifierSpec] | None = None,
        required_capabilities: list[str] | None = None,
    ) -> "ActionContract":
        return cls(
            id=f"contract_{affordance.id}",
            intent=intent,
            affordance_id=affordance.id,
            action=affordance.action,
            backend=backend,
            environment_revision=affordance.lease.environment_revision,
            locator=dict(affordance.locator),
            expected_effects=expected_effects or [],
            verifier_plan=verifier_plan or [],
            required_capabilities=required_capabilities or [],
            risk=affordance.risk,
        )


@dataclass(frozen=True)
class ExecutionReceipt:
    contract_id: str
    backend: str
    success: bool
    started_revision: str
    ended_revision: str
    latency_ms: float
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: RuntimeErrorCode | None = None
    message: str = ""

