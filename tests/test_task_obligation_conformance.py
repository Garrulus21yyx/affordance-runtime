import asyncio
from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

import pytest
from pydantic import BaseModel

from affordance_runtime.intent_compiler import LLMIntentCompiler, LLMIntentDraft
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.task_intake import (
    AmbiguityRisk,
    CompilationStatus,
    IntentAmbiguity,
    IntentDraft,
    OperationClass,
    RequestedEffect,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskStructure,
    UserRequest,
)
from affordance_runtime.task_obligation_coverage import (
    TaskObligationCoverageReview,
    TaskObligationCoverageStatus,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class ScriptedRawIntentModel:
    draft: IntentDraft
    review: TaskObligationCoverageReview
    provider: str = "conformance"
    model: str = "scripted-independent-review"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        self.calls += 1
        if output_schema is LLMIntentDraft:
            return output_schema.model_validate(self.draft.model_dump())
        if output_schema is TaskObligationCoverageReview:
            return output_schema.model_validate(self.review.model_dump())
        raise AssertionError(f"unexpected schema: {output_schema.__name__}")


def _complete_review(draft: IntentDraft) -> TaskObligationCoverageReview:
    return TaskObligationCoverageReview(
        status=TaskObligationCoverageStatus.COMPLETE,
        covered_claim_ids=tuple(
            item.claim_id for item in draft.candidate_source_claims if item.required
        ),
    )


def _direct_form_draft(source_ref: str) -> IntentDraft:
    claim = SourcedTaskClaim(
        claim_id="claim-theme",
        kind=TaskClaimKind.TERMINAL,
        statement="set theme to dark",
        source_ref=source_ref,
    )
    obligation = TaskObligationSpec(
        obligation_id="obligation-theme",
        kind=TaskObligationKind.EFFECT,
        subject="theme",
        relation=TaskObligationRelation.IS_COMPLETED,
        claim_ids=(claim.claim_id,),
        evidence_requirements=("fresh settings confirmation",),
        terminal=True,
    )
    return IntentDraft(
        objective="Set the theme to dark",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="theme",
                source_ref=source_ref,
            ),
        ),
        candidate_success_criteria=("theme is dark",),
        candidate_source_claims=(claim,),
        candidate_obligations=(obligation,),
    )


def _derived_submit_draft(source_ref: str) -> IntentDraft:
    read_claim = SourcedTaskClaim(
        claim_id="claim-read-code",
        kind=TaskClaimKind.DEPENDENCY,
        statement="read the current code",
        source_ref=source_ref,
    )
    write_claim = SourcedTaskClaim(
        claim_id="claim-write-code",
        kind=TaskClaimKind.EFFECT,
        statement="enter the current code in the destination",
        source_ref=source_ref,
    )
    submit_claim = SourcedTaskClaim(
        claim_id="claim-submit-code",
        kind=TaskClaimKind.TERMINAL,
        statement="submit the destination code",
        source_ref=source_ref,
    )
    return IntentDraft(
        objective="Read the current code, enter it in the destination, then submit",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="destination code",
                source_ref=source_ref,
            ),
        ),
        candidate_success_criteria=("destination code submitted",),
        task_structure=TaskStructure.MULTI_STAGE,
        candidate_source_claims=(read_claim, write_claim, submit_claim),
        candidate_obligations=(
            TaskObligationSpec(
                obligation_id="obligation-read-code",
                kind=TaskObligationKind.PREDICATE,
                subject="current code",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source=TaskObligationValueSource.OBSERVATION,
                claim_ids=(read_claim.claim_id,),
                evidence_requirements=("fresh code observation",),
            ),
            TaskObligationSpec(
                obligation_id="obligation-write-code",
                kind=TaskObligationKind.PREDICATE,
                subject="destination code",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.OBLIGATION_OUTPUT,
                value_obligation_id="obligation-read-code",
                claim_ids=(write_claim.claim_id,),
                depends_on=("obligation-read-code",),
                evidence_requirements=("fresh destination observation",),
            ),
            TaskObligationSpec(
                obligation_id="obligation-submit-code",
                kind=TaskObligationKind.EFFECT,
                subject="destination code submission",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=(submit_claim.claim_id,),
                depends_on=("obligation-write-code",),
                evidence_requirements=("fresh submission confirmation",),
                terminal=True,
            ),
        ),
    )


def _navigation_draft(source_ref: str) -> IntentDraft:
    claim = SourcedTaskClaim(
        claim_id="claim-open-help",
        kind=TaskClaimKind.TERMINAL,
        statement="open help center",
        source_ref=source_ref,
    )
    return IntentDraft(
        objective="Open the help center",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="help center",
                source_ref=source_ref,
            ),
        ),
        candidate_success_criteria=("help center is visible",),
        candidate_source_claims=(claim,),
        candidate_obligations=(
            TaskObligationSpec(
                obligation_id="obligation-open-help",
                kind=TaskObligationKind.PREDICATE,
                subject="help center",
                relation=TaskObligationRelation.IS_VISIBLE,
                claim_ids=(claim.claim_id,),
                evidence_requirements=("fresh help-center observation",),
                terminal=True,
            ),
        ),
    )


def _send_draft(source_ref: str) -> IntentDraft:
    claim = SourcedTaskClaim(
        claim_id="claim-send-report",
        kind=TaskClaimKind.TERMINAL,
        statement="send the report to the specified recipient",
        source_ref=source_ref,
    )
    return IntentDraft(
        objective="Send the report to Pat",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                target="report to Pat",
                source_ref=source_ref,
            ),
        ),
        candidate_success_criteria=("Pat receives the report",),
        candidate_source_claims=(claim,),
        candidate_obligations=(
            TaskObligationSpec(
                obligation_id="obligation-send-report",
                kind=TaskObligationKind.EFFECT,
                subject="report delivery to Pat",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=(claim.claim_id,),
                evidence_requirements=("independent delivery confirmation",),
                terminal=True,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("raw_text", "draft_factory"),
    (
        ("Set the theme to dark", _direct_form_draft),
        ("Read the current code, enter it in the destination, then submit", _derived_submit_draft),
        ("Open the help center", _navigation_draft),
        ("Send the report to Pat", _send_draft),
    ),
)
def test_non_browsergym_raw_intake_conformance_accepts_typed_authority(
    raw_text: str,
    draft_factory: Callable[[str], IntentDraft],
) -> None:
    request_id = "conformance-request"
    draft = draft_factory(request_id)
    model = ScriptedRawIntentModel(draft=draft, review=_complete_review(draft))

    result = asyncio.run(
        LLMIntentCompiler(model).compile(UserRequest(request_id=request_id, raw_text=raw_text))
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.obligations == draft.candidate_obligations
    assert model.calls == 2


def test_non_browsergym_raw_intake_conformance_preserves_ambiguity_stop() -> None:
    request_id = "conformance-ambiguity"
    draft = IntentDraft(
        objective="Send a report",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                target="report",
                source_ref=request_id,
            ),
        ),
        candidate_success_criteria=("report sent",),
        ambiguities=(
            IntentAmbiguity(
                field="recipient",
                reason="recipient is missing",
                blocking=True,
                risk=AmbiguityRisk.HIGH,
            ),
        ),
    )
    model = ScriptedRawIntentModel(
        draft=draft,
        review=TaskObligationCoverageReview(
            status=TaskObligationCoverageStatus.UNSUPPORTED,
            uncovered_source_quotes=("Send a report",),
        ),
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(UserRequest(request_id=request_id, raw_text="Send a report"))
    )

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert model.calls == 1


def test_non_browsergym_raw_intake_conformance_rejects_stale_lineage() -> None:
    draft = _direct_form_draft("stale-request")
    model = ScriptedRawIntentModel(draft=draft, review=_complete_review(draft))

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="conformance-current", raw_text="Set the theme to dark")
        )
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[0].code == "unsourced_requested_effect"
    assert model.calls == 1
