"""Canonical strict semantic criterion proposal response."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus
from affordance_runtime.evaluation.semantic_contracts import SemanticCriterionProposal
from affordance_runtime.model_policy.strict_json import strict_json_loads

Id240 = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Ref512 = Annotated[str, StringConstraints(min_length=1, max_length=512)]
Reason500 = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class SemanticProposalPayload(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    criterion_id: Id240
    status: Literal["satisfied", "unsatisfied", "unknown"]
    evidence_refs: Annotated[list[Ref512], Field(max_length=32)]
    reason: Reason500


class SemanticProposalResponse(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    proposals: Annotated[list[SemanticProposalPayload], Field(max_length=32)]

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs):
        del kwargs
        raw = bytes(json_data).decode() if isinstance(json_data, bytes | bytearray) else json_data
        return cls.model_validate(strict_json_loads(raw))

    def to_proposals(self) -> tuple[SemanticCriterionProposal, ...]:
        return tuple(
            SemanticCriterionProposal(
                item.criterion_id,
                CriterionEvaluationStatus(item.status),
                tuple(item.evidence_refs),
                item.reason,
            )
            for item in self.proposals
        )
