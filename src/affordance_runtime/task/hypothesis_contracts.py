"""Non-authoritative bounded requirement-hypothesis proposal contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from affordance_runtime.task.frontier_contracts import (
    FactAvailable,
    TargetAbsent,
    TargetFieldEquals,
    TargetPresent,
    TaskOutcomeIs,
)

if TYPE_CHECKING:
    from affordance_runtime.task.contracts import TaskGoal
    from affordance_runtime.world.contracts import ActionSpace, WorldObservation

_PUBLIC_ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,239}")
_PREDICATES = (
    FactAvailable,
    TargetFieldEquals,
    TargetPresent,
    TargetAbsent,
    TaskOutcomeIs,
)
MAX_HYPOTHESES_PER_PROPOSAL = 8
MAX_CANDIDATE_ENTITIES_PER_HYPOTHESIS = 8
MAX_TRACKED_HYPOTHESES = 16
_HYPOTHESIS_ID = re.compile(r"hypothesis:[1-9][0-9]{0,9}")


class HypothesisProposalMode(StrEnum):
    INITIAL = "initial"
    AUGMENT = "augment"
    REPLACE = "replace"


class HypothesisSetCompleteness(StrEnum):
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RequirementHypothesisProposal:
    summary: str
    predicate: FactAvailable | TargetFieldEquals | TargetPresent | TargetAbsent | TaskOutcomeIs
    candidate_entity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.summary.strip() or len(self.summary) > 240:
            raise ValueError("requirement hypothesis summary must be bounded public text")
        if not isinstance(self.predicate, _PREDICATES):
            raise TypeError("requirement hypothesis requires a closed typed predicate")
        candidates = tuple(self.candidate_entity_ids)
        if (
            len(candidates) > MAX_CANDIDATE_ENTITIES_PER_HYPOTHESIS
            or len(set(candidates)) != len(candidates)
            or any(_PUBLIC_ID.fullmatch(item) is None for item in candidates)
        ):
            raise ValueError("requirement hypothesis candidate entities are invalid")
        object.__setattr__(self, "candidate_entity_ids", candidates)


@dataclass(frozen=True)
class RequirementHypothesisProposalBatch:
    mode: HypothesisProposalMode
    proposals: tuple[RequirementHypothesisProposal, ...]
    completeness: HypothesisSetCompleteness = field(
        default=HypothesisSetCompleteness.UNKNOWN,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, HypothesisProposalMode):
            raise TypeError("hypothesis proposal mode must be typed")
        proposals = tuple(self.proposals)
        if len(proposals) > MAX_HYPOTHESES_PER_PROPOSAL:
            raise ValueError("requirement hypothesis proposal batch exceeds its bound")
        object.__setattr__(self, "proposals", proposals)


class RequirementHypothesisFailureKind(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_RESPONSE = "invalid_response"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class RequirementHypothesisFailure:
    kind: RequirementHypothesisFailureKind
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RequirementHypothesisFailureKind):
            raise TypeError("requirement hypothesis failure kind must be typed")
        if not self.reason_code.strip() or len(self.reason_code) > 96:
            raise ValueError("requirement hypothesis failure reason must be bounded")


class RequirementHypothesisProposer(Protocol):
    async def propose(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        action_space: ActionSpace,
        *,
        mode: HypothesisProposalMode,
        observation_cursor: str = "",
    ) -> RequirementHypothesisProposalBatch | RequirementHypothesisFailure: ...


class TrackedHypothesisStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class HypothesisPredicateAssessment(StrEnum):
    SATISFIED = "satisfied"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrackedRequirementHypothesis:
    hypothesis_id: str
    summary: str
    predicate: FactAvailable | TargetFieldEquals | TargetPresent | TargetAbsent | TaskOutcomeIs
    candidate_entity_ids: tuple[str, ...]
    status: TrackedHypothesisStatus
    assessment: HypothesisPredicateAssessment = HypothesisPredicateAssessment.UNKNOWN
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if _HYPOTHESIS_ID.fullmatch(self.hypothesis_id) is None:
            raise ValueError("tracked hypothesis requires a Runtime-assigned ID")
        RequirementHypothesisProposal(
            self.summary,
            self.predicate,
            self.candidate_entity_ids,
        )
        if not isinstance(self.status, TrackedHypothesisStatus):
            raise TypeError("tracked hypothesis status must be typed")
        if not isinstance(self.assessment, HypothesisPredicateAssessment):
            raise TypeError("hypothesis predicate assessment must be typed")
        refs = tuple(self.evidence_refs)
        if len(refs) > 16 or len(set(refs)) != len(refs):
            raise ValueError("hypothesis assessment evidence must be bounded and unique")
        object.__setattr__(self, "candidate_entity_ids", tuple(self.candidate_entity_ids))
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True)
class RequirementHypothesisState:
    hypotheses: tuple[TrackedRequirementHypothesis, ...] = ()
    revision: int = 0
    next_sequence: int = 1
    completeness: HypothesisSetCompleteness = HypothesisSetCompleteness.UNKNOWN

    def __post_init__(self) -> None:
        values = tuple(self.hypotheses)
        if (
            len(values) > MAX_TRACKED_HYPOTHESES
            or len({item.hypothesis_id for item in values}) != len(values)
            or self.revision < 0
            or self.next_sequence <= 0
            or self.completeness is not HypothesisSetCompleteness.UNKNOWN
        ):
            raise ValueError("requirement hypothesis state is invalid")
        object.__setattr__(self, "hypotheses", values)

    @property
    def active(self) -> tuple[TrackedRequirementHypothesis, ...]:
        return tuple(
            item for item in self.hypotheses
            if item.status is TrackedHypothesisStatus.ACTIVE
        )
