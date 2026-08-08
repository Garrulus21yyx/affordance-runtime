"""Evidence-bound semantic criterion proposals; never task completion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus
from affordance_runtime.model_boundary.evaluator_views import SemanticJudgeRequest
from affordance_runtime.model_boundary.failures import ModelFailure


@dataclass(frozen=True)
class SemanticCriterionProposal:
    criterion_id: str
    status: CriterionEvaluationStatus
    evidence_refs: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.reason.strip() or len(self.reason) > 500:
            raise ValueError("semantic proposal requires bounded criterion identity and reason")
        if self.status == CriterionEvaluationStatus.BLOCKED:
            raise ValueError("semantic judge cannot declare a criterion blocked")
        refs = tuple(self.evidence_refs)
        if len(refs) > 32 or len(set(refs)) != len(refs) or any(not ref.strip() or len(ref) > 512 for ref in refs):
            raise ValueError("semantic proposal evidence refs are invalid")
        if self.status != CriterionEvaluationStatus.UNKNOWN and not refs:
            raise ValueError("resolved semantic proposal requires evidence")
        object.__setattr__(self, "evidence_refs", refs)


SemanticJudgeOutcome: TypeAlias = tuple[SemanticCriterionProposal, ...] | ModelFailure


class SemanticCriterionJudge(Protocol):
    async def evaluate(self, request: SemanticJudgeRequest) -> SemanticJudgeOutcome: ...
