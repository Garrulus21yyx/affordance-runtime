"""Independent bounded review of raw-request obligation coverage."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from pydantic import model_validator

from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.task_intake import IntentDraft, StrictModel, UserRequest

TASK_OBLIGATION_COVERAGE_PROMPT_VERSION = "task-obligation-coverage-v1"

_SYSTEM_PROMPT = """You independently review a proposed sourced task-claim ledger and
obligation graph against the supplied raw user request. You do not plan actions,
grant authority, repair the draft, infer page facts, or use benchmark/task
vocabulary. Compare every explicit imperative, requested value, ordering or
data dependency, terminal outcome, and constraint in raw_request with the
candidate claims and obligations.

Return complete only when every required candidate claim is covered by the graph
and no explicit request clause is absent or unresolved. For complete, list every
required claim id in covered_claim_ids and leave every issue field empty.
For needs_clarification, quote each exact ambiguous clause from raw_request in
unresolved_dependency_quotes. For unsupported, quote each exact uncovered or
unsupported clause from raw_request in uncovered_source_quotes and identify any
candidate claim ids that lack support. Quotes must be literal non-empty
substrings of raw_request. Do not invent quotations or claim ids."""


class TaskObligationCoverageStatus(StrEnum):
    COMPLETE = "complete"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class TaskObligationCoverageReview(StrictModel):
    """Structured output of one independent, non-mutating coverage review."""

    status: TaskObligationCoverageStatus
    covered_claim_ids: tuple[str, ...] = ()
    uncovered_source_quotes: tuple[str, ...] = ()
    unresolved_dependency_quotes: tuple[str, ...] = ()
    unsupported_claim_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_status_shape(self) -> "TaskObligationCoverageReview":
        fields = (
            self.covered_claim_ids,
            self.uncovered_source_quotes,
            self.unresolved_dependency_quotes,
            self.unsupported_claim_ids,
        )
        if any(len(value) != len(set(value)) for value in fields):
            raise ValueError("coverage review references must be unique")
        if any(not value.strip() for values in fields for value in values):
            raise ValueError("coverage review references cannot be blank")
        if self.status == TaskObligationCoverageStatus.COMPLETE and any(
            (
                self.uncovered_source_quotes,
                self.unresolved_dependency_quotes,
                self.unsupported_claim_ids,
            )
        ):
            raise ValueError("complete coverage review cannot contain issues")
        if self.status != TaskObligationCoverageStatus.COMPLETE and not any(
            (
                self.uncovered_source_quotes,
                self.unresolved_dependency_quotes,
                self.unsupported_claim_ids,
            )
        ):
            raise ValueError("incomplete coverage review requires a typed issue")
        return self


@dataclass(frozen=True)
class TaskObligationCoverageDecision:
    """Deterministically validated outcome consumed by intent compilation."""

    status: TaskObligationCoverageStatus
    issue_code: str = ""
    issue_detail: str = ""
    review: TaskObligationCoverageReview | None = None


class TaskObligationCoverageChecker(Protocol):
    async def review(
        self,
        request: UserRequest,
        draft: IntentDraft,
    ) -> TaskObligationCoverageDecision: ...


def task_obligation_coverage_model_config() -> ModelConfig:
    """Return the bounded, versioned independent-review decoding contract."""

    return ModelConfig(
        temperature=0.0,
        max_tokens=384,
        prompt_version=TASK_OBLIGATION_COVERAGE_PROMPT_VERSION,
    )


@dataclass
class ModelBackedTaskObligationCoverageChecker:
    """Run exactly one independent review and validate its references locally."""

    model: ModelPort
    config: ModelConfig = field(default_factory=task_obligation_coverage_model_config)

    async def review(
        self,
        request: UserRequest,
        draft: IntentDraft,
    ) -> TaskObligationCoverageDecision:
        review = await self.model.generate_structured(
            [
                ModelMessage(role="system", content=_SYSTEM_PROMPT),
                ModelMessage(role="user", content=json.dumps(_review_input(request, draft), sort_keys=True)),
            ],
            TaskObligationCoverageReview,
            self.config,
        )
        return validate_task_obligation_coverage_review(request, draft, review)


def validate_task_obligation_coverage_review(
    request: UserRequest,
    draft: IntentDraft,
    review: TaskObligationCoverageReview,
) -> TaskObligationCoverageDecision:
    """Fail closed unless the independent review is coherent and complete."""

    required_claim_ids = {
        item.claim_id for item in draft.candidate_source_claims if item.required
    }
    known_claim_ids = {item.claim_id for item in draft.candidate_source_claims}
    review_ids = set(review.covered_claim_ids)
    unsupported_ids = set(review.unsupported_claim_ids)
    if review_ids - known_claim_ids or unsupported_ids - known_claim_ids:
        return TaskObligationCoverageDecision(
            status=TaskObligationCoverageStatus.UNSUPPORTED,
            issue_code="coverage_review_unknown_claim",
            review=review,
        )
    quotes = (*review.uncovered_source_quotes, *review.unresolved_dependency_quotes)
    if any(quote not in request.raw_text for quote in quotes):
        return TaskObligationCoverageDecision(
            status=TaskObligationCoverageStatus.UNSUPPORTED,
            issue_code="coverage_review_invalid_quote",
            review=review,
        )
    if review.status == TaskObligationCoverageStatus.COMPLETE:
        if review_ids != required_claim_ids:
            return TaskObligationCoverageDecision(
                status=TaskObligationCoverageStatus.UNSUPPORTED,
                issue_code="coverage_review_incomplete_claim_set",
                review=review,
            )
        return TaskObligationCoverageDecision(
            status=TaskObligationCoverageStatus.COMPLETE,
            review=review,
        )
    if review.status == TaskObligationCoverageStatus.NEEDS_CLARIFICATION:
        return TaskObligationCoverageDecision(
            status=review.status,
            issue_code="unresolved_task_dependency",
            issue_detail="; ".join(review.unresolved_dependency_quotes),
            review=review,
        )
    return TaskObligationCoverageDecision(
        status=TaskObligationCoverageStatus.UNSUPPORTED,
        issue_code="uncovered_task_clause",
        issue_detail="; ".join((*review.uncovered_source_quotes, *review.unsupported_claim_ids)),
        review=review,
    )


def _review_input(request: UserRequest, draft: IntentDraft) -> dict[str, object]:
    return {
        "raw_request": request.raw_text,
        "request_id": request.request_id,
        "requested_effects": [item.model_dump(mode="json") for item in draft.requested_effects],
        "semantic_value_constraints": [
            item.model_dump(mode="json") for item in draft.candidate_semantic_value_constraints
        ],
        "source_claims": [item.model_dump(mode="json") for item in draft.candidate_source_claims],
        "obligations": [item.model_dump(mode="json") for item in draft.candidate_obligations],
    }
