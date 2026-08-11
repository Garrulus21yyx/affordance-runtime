"""Coverage admission for policy conclusions that depend on unseen absence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.decisions import Abort, AbortCategory, AgentDecisionPackage, ProposeDone
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.observation_paging import ObservationTraversalStatus
from affordance_runtime.task.frontier_contracts import ProposeObjective, ReplaceObjective, TargetAbsent
from affordance_runtime.world.contracts import CoverageState, EntityInventoryStatus, WorldObservation


class NegativeClaimCoverageDisposition(StrEnum):
    ALLOW = "allow"
    ADVANCE = "advance"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NegativeClaimCoverageResult:
    disposition: NegativeClaimCoverageDisposition
    reason_code: str = ""
    next_cursor: str = ""


@dataclass(frozen=True)
class NegativeClaimCoverageGate:
    """Fail closed only for conclusions whose validity depends on search coverage."""

    def assess(
        self,
        package: AgentDecisionPackage,
        context: AgentContext,
        observation: WorldObservation,
    ) -> NegativeClaimCoverageResult:
        if not _requires_negative_coverage(package):
            return NegativeClaimCoverageResult(NegativeClaimCoverageDisposition.ALLOW)
        unavailable = _inventory_unavailable_reason(observation)
        if unavailable:
            return NegativeClaimCoverageResult(
                NegativeClaimCoverageDisposition.UNKNOWN,
                unavailable,
            )
        traversal = getattr(context.world, "traversal", None)
        if traversal is None:
            return NegativeClaimCoverageResult(NegativeClaimCoverageDisposition.ALLOW)
        if traversal.status is ObservationTraversalStatus.UNKNOWN:
            return NegativeClaimCoverageResult(
                NegativeClaimCoverageDisposition.UNKNOWN,
                traversal.reason_code,
            )
        return NegativeClaimCoverageResult(
            NegativeClaimCoverageDisposition.ADVANCE,
            "negative_claim_requires_observation_traversal",
            traversal.next_cursor,
        )


def _requires_negative_coverage(package: AgentDecisionPackage) -> bool:
    operation = package.objective_operation
    if isinstance(operation, ProposeObjective | ReplaceObjective) and isinstance(
        operation.predicate,
        TargetAbsent,
    ):
        return True
    decision = package.decision
    if isinstance(decision, Abort):
        return decision.category in {
            AbortCategory.NO_PROGRESS,
            AbortCategory.UNSUPPORTED,
        }
    return isinstance(decision, ProposeDone) and not decision.evidence_refs


def _inventory_unavailable_reason(observation: WorldObservation) -> str:
    if any(coverage is not CoverageState.COMPLETE for coverage in observation.coverage.values()):
        return "negative_claim_source_coverage_unavailable"
    if any(
        source.entity_inventory.status in {EntityInventoryStatus.PARTIAL, EntityInventoryStatus.UNAVAILABLE}
        for source in observation.sources
    ):
        return "negative_claim_inventory_incomplete"
    return ""
