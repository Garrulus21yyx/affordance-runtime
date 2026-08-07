"""Verifier-backed, scope-bounded route outcome calibration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import time

from affordance_runtime.grounding import GroundingSource
from affordance_runtime.verification.mechanical import VerificationReport, VerificationStatus


class RouteOutcomeStatus(StrEnum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_FAILURE = "verified_failure"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class RouteScope:
    """Calibration scope; observations never leak across action/environment/source."""

    environment_family: str
    action_kind: str
    source: GroundingSource
    executor: str
    verifier_kinds: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.environment_family or not self.action_kind or not self.executor:
            raise ValueError("route calibration scope fields must be non-empty")
        if not self.verifier_kinds:
            raise ValueError("route calibration requires an explicit verifier plan")
        object.__setattr__(self, "verifier_kinds", tuple(sorted(set(self.verifier_kinds))))


@dataclass(frozen=True)
class RouteOutcome:
    """One route label derived only from independent postcondition verification."""

    outcome_id: str
    scope: RouteScope
    semantic_target_id: str
    candidate_id: str
    contract_id: str
    status: RouteOutcomeStatus
    verification_status: VerificationStatus
    evidence_ids: tuple[str, ...]
    post_snapshot_id: str
    latency_ms: float = 0.0
    expected_cost: float = 0.0
    observed_at_s: float = field(default_factory=time)

    def __post_init__(self) -> None:
        if not all(
            (
                self.outcome_id,
                self.semantic_target_id,
                self.candidate_id,
                self.contract_id,
                self.post_snapshot_id,
            )
        ):
            raise ValueError("route outcome identity fields must be non-empty")
        if self.status != RouteOutcomeStatus.INCONCLUSIVE and not self.evidence_ids:
            raise ValueError("conclusive route outcomes require independent evidence")
        if self.latency_ms < 0 or self.expected_cost < 0:
            raise ValueError("route outcome latency and cost cannot be negative")

    @classmethod
    def from_verification(
        cls,
        *,
        outcome_id: str,
        scope: RouteScope,
        semantic_target_id: str,
        candidate_id: str,
        contract_id: str,
        report: VerificationReport,
        post_snapshot_id: str,
        latency_ms: float,
        expected_cost: float,
    ) -> "RouteOutcome":
        independent_evidence = tuple(
            item
            for item in report.evidence
            if item.source != "execution_receipt"
            and item.evidence_id
            and item.snapshot_id == post_snapshot_id
            and item.strength == "strong"
        )
        independent = tuple(item.evidence_id for item in independent_evidence)
        if not independent_evidence:
            status = RouteOutcomeStatus.INCONCLUSIVE
        elif report.status == VerificationStatus.PASSED and all(
            item.passed for item in independent_evidence
        ):
            status = RouteOutcomeStatus.VERIFIED_SUCCESS
        elif report.status == VerificationStatus.FAILED and any(
            not item.passed for item in independent_evidence
        ):
            status = RouteOutcomeStatus.VERIFIED_FAILURE
        else:
            status = RouteOutcomeStatus.INCONCLUSIVE
        return cls(
            outcome_id=outcome_id,
            scope=scope,
            semantic_target_id=semantic_target_id,
            candidate_id=candidate_id,
            contract_id=contract_id,
            status=status,
            verification_status=report.status,
            evidence_ids=independent,
            post_snapshot_id=post_snapshot_id,
            latency_ms=latency_ms,
            expected_cost=expected_cost,
        )


@dataclass
class RouteStatistics:
    verified_attempts: int = 0
    verified_successes: int = 0
    verified_failures: int = 0
    inconclusive: int = 0
    total_latency_ms: float = 0.0
    total_expected_cost: float = 0.0

    @property
    def reliability(self) -> float | None:
        if not self.verified_attempts:
            return None
        return self.verified_successes / self.verified_attempts


@dataclass
class RouteCalibrator:
    """Session-scoped statistics updated only by typed RouteOutcome values."""

    stats: dict[RouteScope, RouteStatistics] = field(default_factory=dict)
    outcomes: list[RouteOutcome] = field(default_factory=list)
    minimum_verified_attempts: int = 2
    seen_outcome_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.minimum_verified_attempts < 1:
            raise ValueError("route calibration needs at least one verified attempt")

    def record(self, outcome: RouteOutcome) -> None:
        if outcome.outcome_id in self.seen_outcome_ids:
            raise ValueError(f"route outcome was already recorded: {outcome.outcome_id}")
        self.seen_outcome_ids.add(outcome.outcome_id)
        current = self.stats.setdefault(outcome.scope, RouteStatistics())
        self.outcomes.append(outcome)
        if outcome.status == RouteOutcomeStatus.INCONCLUSIVE:
            current.inconclusive += 1
            return
        current.verified_attempts += 1
        current.verified_successes += int(
            outcome.status == RouteOutcomeStatus.VERIFIED_SUCCESS
        )
        current.verified_failures += int(
            outcome.status == RouteOutcomeStatus.VERIFIED_FAILURE
        )
        current.total_latency_ms += outcome.latency_ms
        current.total_expected_cost += outcome.expected_cost

    def get(self, scope: RouteScope) -> RouteStatistics:
        return self.stats.get(scope, RouteStatistics())

    def failure_component(self, scope: RouteScope) -> float | None:
        stats = self.get(scope)
        if stats.verified_attempts < self.minimum_verified_attempts:
            return None
        reliability = stats.reliability
        return None if reliability is None else 1.0 - reliability
