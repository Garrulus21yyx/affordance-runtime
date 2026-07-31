import asyncio
import json
from dataclasses import dataclass, field
from typing import Sequence, TypeVar

import pytest
from pydantic import BaseModel

from affordance_runtime.intent_compiler import (
    INTENT_COMPILER_PROMPT_VERSION,
    INTENT_DRAFT_REPAIR_PROMPT_VERSION,
    IntentDraftRepairAttempt,
    LLMIntentCompiler,
    LLMIntentDraft,
    ParentSemanticProposalCompiler,
)
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    StructuredModelError,
    StructuredOutputError,
)
from affordance_runtime.task_intake import (
    CompilationPolicy,
    CompilationResult,
    CompilationStatus,
    GraphConstructionSource,
    IntentAmbiguity,
    IntentDraft,
    IntentDraftValidator,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    SemanticValueRelation,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskInteractionRelationKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskStructure,
    UserRequest,
)
from affordance_runtime.task_obligation_coverage import (
    TaskObligationCoverageDecision,
    TaskObligationCoverageReview,
    TaskObligationCoverageStatus,
)
from affordance_runtime.trace import TraceDag

T = TypeVar("T", bound=BaseModel)


@pytest.mark.parametrize(
    ("raw_text", "source", "destination"),
    (
        (
            "Drag the cobalt tile into the amber tray.",
            "cobalt tile",
            "amber tray",
        ),
        (
            "Move the renamed source completely inside the renamed destination.",
            "renamed source",
            "renamed destination",
        ),
    ),
)
def test_intent_compiler_canonicalizes_explicit_two_endpoint_drag_relation(
    raw_text: str,
    source: str,
    destination: str,
) -> None:
    model = FixedModel(
        IntentDraft(
            objective=raw_text,
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="provider generic drag target",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("The requested relation holds.",),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="relation-request", raw_text=raw_text)
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.subject == source
    assert obligation.interaction_relation is not None
    assert obligation.interaction_relation.kind == TaskInteractionRelationKind.DRAG_TO
    assert obligation.interaction_relation.destination == destination
    assert obligation.interaction_relation.relative_offset is None


def test_intent_compiler_canonicalizes_relative_position_without_guessing_endpoint() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Move Delta down by one position.",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="sortable list",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("Delta moved down one position.",),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="relative-relation-request",
                raw_text="Move Delta down by one position.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.subject == "Delta"
    assert obligation.interaction_relation is not None
    assert obligation.interaction_relation.kind == TaskInteractionRelationKind.RELATIVE_POSITION
    assert obligation.interaction_relation.destination == ""
    assert obligation.interaction_relation.relative_offset == 1


def test_intent_compiler_canonicalizes_absolute_position_as_an_ordinal() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Move Vanya to the 4th position.",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="provider position string",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("Vanya is fourth.",),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="absolute-relation-request",
                raw_text="Move Vanya to the 4th position.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.subject == "Vanya"
    assert obligation.interaction_relation is not None
    assert obligation.interaction_relation.kind == TaskInteractionRelationKind.ABSOLUTE_POSITION
    assert obligation.interaction_relation.destination == ""
    assert obligation.interaction_relation.destination_ordinal == 4


@pytest.mark.parametrize(
    "raw_text",
    (
        "Click the point at coordinate (2,-2).",
        "Activate the mark at coordinate (-4,3).",
    ),
)
def test_intent_compiler_marks_explicit_spatial_point_as_capability_bound(raw_text: str) -> None:
    model = FixedModel(
        IntentDraft(
            objective=raw_text,
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.NAVIGATION,
                    target="provider spatial target",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("The requested point is activated.",),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(UserRequest(request_id="spatial-request", raw_text=raw_text))
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.requested_capabilities == ("spatial.point.current_geometry",)
    obligation = result.task_spec.obligations[0]
    assert obligation.interaction_capability == "spatial.point.current_geometry"
    assert "coordinate" in obligation.subject.casefold()


def test_intent_compiler_marks_only_the_explicit_center_region_effect() -> None:
    raw_text = "Click the center of the renamed polygon, then press Confirm."
    model = FixedModel(
        IntentDraft(
            objective=raw_text,
            task_structure=TaskStructure.MULTI_STAGE,
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.NAVIGATION,
                    target="polygon_center",
                    source_ref="raw_text",
                ),
                RequestedEffect(
                    operation_class=OperationClass.NAVIGATION,
                    target="confirm_button",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("Polygon center activated.", "Confirm pressed."),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(UserRequest(request_id="region-request", raw_text=raw_text))
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    first, second = result.task_spec.obligations
    assert first.subject == "renamed polygon"
    assert first.interaction_capability == "spatial.point.current_geometry"
    assert second.interaction_capability == ""


def test_intent_draft_repair_attempt_claim_id_map_is_immutable_from_source_mapping() -> None:
    draft = IntentDraft(
        objective="Inspect report",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="report",
                source_ref="source:request:whole",
            ),
        ),
    )
    proposal_claim_ids = {"provider-read": "claim:canonical"}

    attempt = IntentDraftRepairAttempt(
        draft=draft,
        provider_issues=(),
        proposal_claim_ids=proposal_claim_ids,
        result=CompilationResult(
            status=CompilationStatus.READY,
            request_id="request-1",
            draft=draft,
        ),
        parent=None,
        succeeded=True,
    )
    proposal_claim_ids["provider-read"] = "claim:polluted"

    assert attempt.proposal_claim_ids["provider-read"] == "claim:canonical"
    with pytest.raises(TypeError):
        attempt.proposal_claim_ids["provider-read"] = "claim:polluted"


def _terminal_authority(
    source_ref: str,
    subject: str,
) -> tuple[tuple[SourcedTaskClaim, ...], tuple[TaskObligationSpec, ...]]:
    claim = SourcedTaskClaim(
        claim_id="claim-terminal",
        kind=TaskClaimKind.TERMINAL,
        statement=f"complete {subject}",
        source_ref=source_ref,
    )
    obligation = TaskObligationSpec(
        obligation_id="obligation-terminal",
        kind=TaskObligationKind.EFFECT,
        subject=subject,
        relation=TaskObligationRelation.IS_COMPLETED,
        claim_ids=(claim.claim_id,),
        evidence_requirements=(f"independent {subject} evidence",),
        terminal=True,
    )
    return (claim,), (obligation,)


@dataclass
class FixedModel:
    draft: IntentDraft
    provider: str = "fixed"
    model: str = "fixed-v1"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    messages: Sequence[ModelMessage] = ()
    message_batches: list[Sequence[ModelMessage]] = field(default_factory=list)

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        self.messages = messages
        self.message_batches.append(messages)
        if output_schema is LLMIntentDraft:
            assert config.prompt_version in {
                INTENT_COMPILER_PROMPT_VERSION,
                INTENT_DRAFT_REPAIR_PROMPT_VERSION,
            }
            return output_schema.model_validate(self.draft.model_dump())
        if output_schema is TaskObligationCoverageReview:
            reviewed_draft = json.loads(messages[-1].content)
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": [
                        item["claim_id"]
                        for item in reviewed_draft["source_claims"]
                        if item["required"]
                    ],
                }
            )
        raise AssertionError(f"unexpected schema: {output_schema.__name__}")


@dataclass(frozen=True)
class FixedCoverageChecker:
    decision: TaskObligationCoverageDecision

    async def review(
        self,
        request: UserRequest,
        draft: IntentDraft,
    ) -> TaskObligationCoverageDecision:
        del request, draft
        return self.decision


@dataclass
class CountingCompleteCoverageChecker:
    calls: int = 0

    async def review(
        self,
        request: UserRequest,
        draft: IntentDraft,
    ) -> TaskObligationCoverageDecision:
        del request, draft
        self.calls += 1
        return TaskObligationCoverageDecision(status=TaskObligationCoverageStatus.COMPLETE)


@dataclass
class SequentialCoverageChecker:
    decisions: tuple[TaskObligationCoverageDecision, ...]
    calls: int = 0

    async def review(
        self,
        request: UserRequest,
        draft: IntentDraft,
    ) -> TaskObligationCoverageDecision:
        del request, draft
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision


@dataclass
class RepairingModel(FixedModel):
    repaired_draft: IntentDraft = field(default_factory=IntentDraft)
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        self.calls += 1
        self.messages = messages
        self.message_batches.append(messages)
        if output_schema is LLMIntentDraft:
            expected_prompt = (
                INTENT_COMPILER_PROMPT_VERSION
                if self.calls == 1
                else INTENT_DRAFT_REPAIR_PROMPT_VERSION
            )
            assert config.prompt_version == expected_prompt
            draft = self.draft if self.calls == 1 else self.repaired_draft
            return output_schema.model_validate(draft.model_dump())
        if output_schema is TaskObligationCoverageReview:
            reviewed_draft = json.loads(messages[-1].content)
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": [
                        item["claim_id"]
                        for item in reviewed_draft["source_claims"]
                        if item["required"]
                    ],
                }
            )
        raise AssertionError(f"unexpected schema: {output_schema.__name__}")


@dataclass
class ProviderSchemaRepairingModel(RepairingModel):
    """First provider draft has one malformed untrusted obligation node."""

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        self.calls += 1
        self.messages = messages
        self.message_batches.append(messages)
        if output_schema is LLMIntentDraft:
            expected_prompt = (
                INTENT_COMPILER_PROMPT_VERSION
                if self.calls == 1
                else INTENT_DRAFT_REPAIR_PROMPT_VERSION
            )
            assert config.prompt_version == expected_prompt
            payload = self.repaired_draft.model_dump(mode="json")
            if self.calls == 1:
                payload["candidate_obligations"][0]["evidence_requirements"] = []
            return output_schema.model_validate(payload)
        if output_schema is TaskObligationCoverageReview:
            reviewed_draft = json.loads(messages[-1].content)
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": [
                        item["claim_id"]
                        for item in reviewed_draft["source_claims"]
                        if item["required"]
                    ],
                }
            )
        raise AssertionError(f"unexpected schema: {output_schema.__name__}")


@dataclass
class FailingRepairModel(FixedModel):
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        self.calls += 1
        if self.calls == 2:
            assert config.prompt_version == INTENT_DRAFT_REPAIR_PROMPT_VERSION
            raise StructuredModelError("redacted repair decode failure")
        return await super().generate_structured(messages, output_schema, config)


@dataclass
class UnexpectedModelCall:
    provider: str = "unexpected"
    model: str = "unexpected-v1"
    endpoint_class: str = "test"
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, output_schema, config
        self.calls += 1
        raise AssertionError("source ledger rejection must not call the model")


@dataclass
class SchemaRetryModel(FixedModel):
    draft_attempts: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        if output_schema is LLMIntentDraft:
            self.draft_attempts += 1
            if self.draft_attempts == 1:
                raise StructuredOutputError("redacted invalid structured output")
        return await super().generate_structured(messages, output_schema, config)


def test_provider_schema_requires_deterministic_validator_prerequisites() -> None:
    schema = LLMIntentDraft.model_json_schema()

    assert set(schema["required"]) == {
        "objective",
        "requested_effects",
        "candidate_success_criteria",
    }
    assert schema["properties"]["objective"]["minLength"] == 1
    assert schema["properties"]["requested_effects"]["minItems"] == 1
    assert schema["properties"]["candidate_success_criteria"]["minItems"] == 1
    assert "candidate_semantic_value_constraints" in schema["properties"]
    assert "candidate_source_claims" in schema["properties"]
    assert "candidate_obligations" in schema["properties"]
    assert "candidate_source_claims" not in schema["required"]
    assert "candidate_obligations" not in schema["required"]


def test_provider_obligation_schema_keeps_graph_fields_while_deferring_semantic_validation() -> None:
    schema = LLMIntentDraft.model_json_schema()
    reference = schema["properties"]["candidate_obligations"]["items"]["$ref"]
    obligation_schema = schema["$defs"][reference.rsplit("/", 1)[-1]]

    assert {
        "obligation_id",
        "kind",
        "subject",
        "relation",
        "claim_ids",
        "depends_on",
        "evidence_requirements",
        "terminal",
    }.issubset(obligation_schema["properties"])
    assert {"obligation_id", "kind", "subject", "relation", "claim_ids"}.issubset(
        obligation_schema["required"]
    )


def test_parent_semantic_proposal_is_source_bound_and_receives_runtime_graph_ids() -> None:
    claims, obligations = _terminal_authority("parent-proposal", "pricing read")
    proposal = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="parent-proposal",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
        candidate_source_claims=claims,
        candidate_obligations=obligations,
    )
    trace = TraceDag("parent-proposal")

    result = ParentSemanticProposalCompiler().compile(
        UserRequest(request_id="parent-proposal", raw_text="Read pricing"),
        proposal,
        trace=trace,
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.source_claims[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    assert result.task_spec.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    assert result.task_spec.source_claims[0].claim_id != "claim-terminal"
    assert result.task_spec.obligations[0].obligation_id != "obligation-terminal"
    assert "ParentSemanticProposalNormalized" in [node.kind for node in trace.nodes]


def test_parent_flat_proposal_ignores_unknown_proposal_graph_unit() -> None:
    claims, obligations = _terminal_authority("unknown-source", "pricing read")
    proposal = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="parent-proposal",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
        candidate_source_claims=claims,
        candidate_obligations=obligations,
    )

    result = ParentSemanticProposalCompiler().compile(
        UserRequest(request_id="parent-proposal", raw_text="Read pricing"),
        proposal,
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER


def test_parent_flat_proposal_rejects_unknown_requested_effect_source_before_taskspec_creation() -> None:
    proposal = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="unknown-source",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
    )

    result = ParentSemanticProposalCompiler().compile(
        UserRequest(request_id="parent-proposal", raw_text="Read pricing"),
        proposal,
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[-1].code == "canonical_flat_graph_unavailable"


def test_model_complete_cannot_upgrade_deterministically_uncovered_source_clause() -> None:
    request = UserRequest(
        request_id="coverage-authority",
        raw_text="Read the code. Submit the result.",
    )
    first_clause_id = "coverage-authority:source:request:clause:0"
    claim = SourcedTaskClaim(
        claim_id="provider-claim",
        kind=TaskClaimKind.TERMINAL,
        statement="submit result",
        source_ref="raw_text",
        source_unit_ids=(first_clause_id,),
    )
    obligation = TaskObligationSpec(
        obligation_id="provider-obligation",
        kind=TaskObligationKind.EFFECT,
        subject="result",
        relation=TaskObligationRelation.IS_COMPLETED,
        claim_ids=(claim.claim_id,),
        evidence_requirements=("independent result evidence",),
        terminal=True,
    )
    model = FixedModel(
        IntentDraft(
            objective="Read and submit",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="result",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("result submitted",),
            candidate_source_claims=(claim,),
            candidate_obligations=(obligation,),
        )
    )
    checker = CountingCompleteCoverageChecker()

    result = asyncio.run(
        LLMIntentCompiler(model, coverage_checker=checker, max_draft_repairs=0).compile(request)
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER
    assert checker.calls == 1


def test_llm_compiler_preserves_explicit_prefix_without_inventing_completion() -> None:
    constraint = SemanticValueConstraint(
        relation=SemanticValueRelation.PREFIX,
        value="Com",
        target="item",
        source_ref="request-prefix",
    )
    claims, obligations = _terminal_authority("request-prefix", "matching item entry")
    model = FixedModel(
        IntentDraft(
            objective="Enter an item that starts with Com",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="item",
                    source_ref="request-prefix",
                ),
            ),
            candidate_success_criteria=("matching item entered",),
            candidate_semantic_value_constraints=(constraint,),
            candidate_source_claims=claims,
            candidate_obligations=obligations,
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="request-prefix",
                raw_text="Enter an item that starts with Com",
            )
        )
    )

    assert result.task_spec is not None
    assert result.task_spec.semantic_value_constraints == (
        constraint.model_copy(update={"source_ref": "request-prefix:source:request:whole"}),
    )
    assert any(
        "never invent a completion" in messages[0].content.casefold()
        for messages in model.message_batches
    )


def test_llm_compiler_canonicalizes_explicit_entry_value_as_write_obligation() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Enter 01/18/2019 as the date and hit submit.",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="date_field",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("The date field contains the value '01/18/2019'.",),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=CountingCompleteCoverageChecker(),
        ).compile(
            UserRequest(
                request_id="date-entry",
                raw_text="Enter 01/18/2019 as the date and hit submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.operation_class == OperationClass.REVERSIBLE_WRITE
    assert result.task_spec.semantic_value_constraints[0].value == "01/18/2019"
    assert result.task_spec.obligations[0].relation == TaskObligationRelation.EQUALS
    assert result.task_spec.obligations[0].expected_value == "01/18/2019"
    assert result.task_spec.obligations[0].construction_source == (
        GraphConstructionSource.CANONICAL_COMPILER
    )


def test_llm_compiler_binds_ordinal_entry_value_to_matching_effect() -> None:
    model = FixedModel(
        IntentDraft(
            objective='Check a radio control and enter "-7" into a text control.',
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="radio_button[3]",
                    source_ref="raw_text",
                ),
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="text_box[1]",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=(
                "The requested radio control is checked.",
                "The requested text control contains -7.",
            ),
            task_structure=TaskStructure.MULTI_STAGE,
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=CountingCompleteCoverageChecker(),
        ).compile(
            UserRequest(
                request_id="ordinal-entry",
                raw_text='Check the 4th radio button and enter the number "-7" into the 2nd textbox.',
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    first, second = result.task_spec.obligations
    assert first.subject == "radio_4"
    assert first.relation == TaskObligationRelation.HAS_CHANGED
    assert second.subject == "textbox_2"
    assert second.relation == TaskObligationRelation.EQUALS
    assert second.expected_value == "-7"
    assert second.depends_on == (first.obligation_id,)


def test_llm_compiler_builds_sourced_value_transfer_dependency() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Copy the value from Source field into Destination field.",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="Source field",
                    source_ref="raw_text",
                ),
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="Destination field",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("Destination field equals the source value.",),
            task_structure=TaskStructure.MULTI_STAGE,
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=CountingCompleteCoverageChecker(),
        ).compile(
            UserRequest(
                request_id="value-transfer",
                raw_text="Copy the value from Source field into Destination field.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    source, destination = result.task_spec.obligations
    assert source.value_source == TaskObligationValueSource.OBSERVATION
    assert destination.relation == TaskObligationRelation.EQUALS
    assert destination.value_source == TaskObligationValueSource.OBLIGATION_OUTPUT
    assert destination.value_obligation_id == source.obligation_id
    assert source.obligation_id in destination.depends_on


def test_llm_compiler_does_not_literalize_page_sourced_text_below() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Type the text below into the text field and press Submit.",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="text_field",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=(
                "Text field contains the text 'Type the text below into the text field and press Submit.'",
            ),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=CountingCompleteCoverageChecker(),
        ).compile(
            UserRequest(
                request_id="text-below",
                raw_text="Type the text below into the text field and press Submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.operation_class == OperationClass.REVERSIBLE_WRITE
    assert result.task_spec.semantic_value_constraints == ()
    assert result.task_spec.obligations[0].relation == TaskObligationRelation.HAS_CHANGED
    assert result.task_spec.obligations[0].expected_value == ""


def test_llm_compiler_repairs_reviewer_vetoed_unresolved_dependency_before_clarification() -> None:
    initial = IntentDraft(
        objective="Type the text below into the text field and press Submit.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="text_field",
                source_ref="raw_text",
            ),
        ),
        candidate_success_criteria=("Text field contains the text provided below.",),
    )
    repaired = IntentDraft(
        objective="Type the text below into the text field and press Submit.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="text_field",
                source_ref="raw_text",
            ),
        ),
        candidate_success_criteria=("Text field equals the text observed below after submit.",),
        task_structure=TaskStructure.FLAT,
        candidate_source_claims=(
            SourcedTaskClaim(
                claim_id="provider-observe-text",
                kind=TaskClaimKind.DEPENDENCY,
                statement="observe the text below",
                source_ref="raw_text",
            ),
            SourcedTaskClaim(
                claim_id="provider-enter-text",
                kind=TaskClaimKind.EFFECT,
                statement="text field equals the observed text after submit",
                source_ref="raw_text",
            ),
        ),
        candidate_obligations=(
            TaskObligationSpec(
                obligation_id="provider-observe-text-obligation",
                kind=TaskObligationKind.PREDICATE,
                subject="text below",
                relation=TaskObligationRelation.IS_AVAILABLE,
                value_source=TaskObligationValueSource.OBSERVATION,
                claim_ids=("provider-observe-text",),
                evidence_requirements=("provider-authored observation evidence",),
            ),
            TaskObligationSpec(
                obligation_id="provider-enter-text-obligation",
                kind=TaskObligationKind.EFFECT,
                subject="text_field",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.OBLIGATION_OUTPUT,
                value_obligation_id="provider-observe-text-obligation",
                claim_ids=("provider-enter-text",),
                depends_on=("provider-observe-text-obligation",),
                evidence_requirements=("provider-authored terminal evidence",),
                terminal=True,
            ),
        ),
    )
    model = RepairingModel(initial, repaired_draft=repaired)
    coverage = SequentialCoverageChecker(
        (
            TaskObligationCoverageDecision(
                status=TaskObligationCoverageStatus.NEEDS_CLARIFICATION,
                issue_code="unresolved_task_dependency",
                issue_detail="Type the text below into the text field and press Submit.",
            ),
            TaskObligationCoverageDecision(status=TaskObligationCoverageStatus.COMPLETE),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model, coverage_checker=coverage, max_model_calls=3).compile(
            UserRequest(
                request_id="coverage-veto-repair",
                raw_text="Type the text below into the text field and press Submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert model.calls == 2
    assert coverage.calls == 2
    assert result.task_spec.operation_class == OperationClass.REVERSIBLE_WRITE
    assert result.task_spec.task_structure == TaskStructure.MULTI_STAGE
    assert result.task_spec.obligations[1].relation == TaskObligationRelation.EQUALS
    assert result.task_spec.obligations[1].value_obligation_id == (
        result.task_spec.obligations[0].obligation_id
    )
    assert all(
        obligation.construction_source == GraphConstructionSource.MODEL_PROPOSAL
        for obligation in result.task_spec.obligations
    )
    assert all(
        "provider" not in obligation.obligation_id
        for obligation in result.task_spec.obligations
    )


def test_llm_compiler_repairs_missing_obligation_graph_within_three_call_budget() -> None:
    initial = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="repair-request",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
    )
    claims, obligations = _terminal_authority("repair-request", "pricing read")
    repaired = initial.model_copy(
        update={"candidate_source_claims": claims, "candidate_obligations": obligations}
    )
    model = RepairingModel(initial, repaired_draft=repaired)

    trace = TraceDag("repair-request")
    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="repair-request", raw_text="Read pricing"), trace=trace
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert model.calls == 2
    assert "IntentDraftRepairProduced" not in [node.kind for node in trace.nodes]


def test_llm_compiler_canonicalizes_multistage_requested_effects_when_provider_graph_is_incomplete() -> None:
    draft = IntentDraft(
        objective="Click button ONE, then click button TWO.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="button ONE",
                source_ref="button-sequence",
            ),
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="button TWO",
                source_ref="button-sequence",
            ),
        ),
        candidate_success_criteria=("Button ONE was clicked.", "Button TWO was clicked."),
        task_structure=TaskStructure.FLAT,
        candidate_source_claims=(
            SourcedTaskClaim(
                claim_id="provider-one",
                kind=TaskClaimKind.EFFECT,
                statement="Click button ONE",
                source_ref="button-sequence",
            ),
            SourcedTaskClaim(
                claim_id="provider-two",
                kind=TaskClaimKind.EFFECT,
                statement="Click button TWO",
                source_ref="button-sequence",
            ),
        ),
    )
    model = RepairingModel(draft, repaired_draft=draft)

    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=CountingCompleteCoverageChecker(),
            max_model_calls=1,
        ).compile(
            UserRequest(
                request_id="button-sequence",
                raw_text="Click button ONE, then click button TWO.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert model.calls == 1
    assert result.task_spec.task_structure == TaskStructure.MULTI_STAGE
    assert len(result.task_spec.obligations) == 2
    assert all(
        claim.construction_source == GraphConstructionSource.CANONICAL_COMPILER
        for claim in result.task_spec.source_claims
    )
    assert all(
        obligation.construction_source == GraphConstructionSource.CANONICAL_COMPILER
        for obligation in result.task_spec.obligations
    )
    assert all("provider" not in claim.claim_id for claim in result.task_spec.source_claims)
    assert all(
        "provider" not in obligation.obligation_id
        for obligation in result.task_spec.obligations
    )


def test_llm_compiler_canonicalizes_clicked_navigation_effects_as_completed_actions() -> None:
    draft = IntentDraft(
        objective="Click button Alpha, then click button Beta.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="button Alpha",
                source_ref="button-sequence",
            ),
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="button Beta",
                source_ref="button-sequence",
            ),
        ),
        candidate_success_criteria=("Button Alpha was clicked.", "Button Beta was clicked."),
        task_structure=TaskStructure.MULTI_STAGE,
    )
    model = FixedModel(draft)

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="button-sequence",
                raw_text="Click button Alpha, then click button Beta.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    alpha, beta = result.task_spec.obligations
    assert alpha.kind == TaskObligationKind.EFFECT
    assert beta.kind == TaskObligationKind.EFFECT
    assert alpha.relation == TaskObligationRelation.IS_COMPLETED
    assert beta.relation == TaskObligationRelation.IS_COMPLETED
    assert alpha.typed_evidence_requirements[0].relation == TaskObligationRelation.IS_COMPLETED
    assert beta.typed_evidence_requirements[0].relation == TaskObligationRelation.IS_COMPLETED
    assert not alpha.terminal
    assert beta.terminal
    assert beta.depends_on == (alpha.obligation_id,)


def test_llm_compiler_preserves_quoted_entry_value_in_multistage_graph() -> None:
    draft = IntentDraft(
        objective='Enter "Myron" into the text field and press Submit.',
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="text_field",
                source_ref="enter-text",
            ),
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="submit_button",
                source_ref="enter-text",
            ),
        ),
        candidate_success_criteria=(
            'The text field contains the string "Myron".',
            "The form is submitted.",
        ),
        task_structure=TaskStructure.MULTI_STAGE,
    )
    model = FixedModel(draft)

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="enter-text",
                raw_text='Enter "Myron" into the text field and press Submit.',
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    text_obligation, submit_obligation = result.task_spec.obligations
    assert text_obligation.subject == "text_field"
    assert text_obligation.relation == TaskObligationRelation.EQUALS
    assert text_obligation.value_source == TaskObligationValueSource.LITERAL
    assert text_obligation.expected_value == "Myron"
    assert text_obligation.typed_evidence_requirements[0].value_ref == "Myron"
    assert submit_obligation.depends_on == (text_obligation.obligation_id,)


def test_llm_compiler_normalizes_select_from_list_value_in_multistage_graph() -> None:
    draft = IntentDraft(
        objective="Select Ertha from the list and click Submit.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                target="Select Ertha from the list and click Submit.",
                source_ref="choose-list",
            ),
        ),
        candidate_success_criteria=("The user has selected Ertha from the list and clicked Submit.",),
        task_structure=TaskStructure.FLAT,
    )
    model = FixedModel(draft)

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="choose-list",
                raw_text="Select Ertha from the list and click Submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.subject == "list"
    assert obligation.relation == TaskObligationRelation.IS_SELECTED
    assert obligation.value_source == TaskObligationValueSource.LITERAL
    assert obligation.expected_value == "Ertha"
    assert obligation.typed_evidence_requirements[0].value_ref == "Ertha"


def test_llm_compiler_normalizes_navigation_misclassification_for_explicit_selection() -> None:
    draft = IntentDraft(
        objective="Select Ertha from the list.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="Select Ertha from the list.",
                source_ref="choose-list-navigation",
            ),
        ),
        candidate_success_criteria=("Ertha is selected from the list.",),
        task_structure=TaskStructure.FLAT,
    )

    result = asyncio.run(
        LLMIntentCompiler(FixedModel(draft)).compile(
            UserRequest(
                request_id="choose-list-navigation",
                raw_text="Select Ertha from the list.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.subject == "list"
    assert obligation.relation == TaskObligationRelation.IS_SELECTED
    assert obligation.expected_value == "Ertha"


def test_llm_compiler_preserves_multiword_explicit_selection_value() -> None:
    draft = IntentDraft(
        objective="Select Norfolk Island from the list.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="Norfolk Island",
                source_ref="choose-list-multiword",
            ),
        ),
        candidate_success_criteria=("Norfolk Island is selected in the list.",),
        task_structure=TaskStructure.FLAT,
    )

    result = asyncio.run(
        LLMIntentCompiler(FixedModel(draft)).compile(
            UserRequest(
                request_id="choose-list-multiword",
                raw_text="Select Norfolk Island from the list.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.subject == "list"
    assert obligation.relation == TaskObligationRelation.IS_SELECTED
    assert obligation.expected_value == "Norfolk Island"


def test_llm_compiler_normalizes_explicit_click_misclassified_as_read_only() -> None:
    draft = IntentDraft(
        objective="Close the dialog box by clicking the 'x'.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="dialog_box_close_button",
                source_ref="click-dialog-read-only",
            ),
        ),
        candidate_success_criteria=("The dialog box is closed by clicking the 'x'.",),
        task_structure=TaskStructure.FLAT,
    )

    result = asyncio.run(
        LLMIntentCompiler(FixedModel(draft)).compile(
            UserRequest(
                request_id="click-dialog-read-only",
                raw_text="Close the dialog box by clicking the 'x'.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    obligation = result.task_spec.obligations[0]
    assert obligation.kind == TaskObligationKind.EFFECT
    assert obligation.relation == TaskObligationRelation.IS_COMPLETED


def test_llm_compiler_restores_explicit_submit_effect_omitted_from_draft() -> None:
    draft = IntentDraft(
        objective="Select Ertha from the list and click Submit.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="Ertha",
                source_ref="choose-list-submit",
            ),
        ),
        candidate_success_criteria=("Ertha is selected from the list.",),
        task_structure=TaskStructure.FLAT,
    )

    result = asyncio.run(
        LLMIntentCompiler(FixedModel(draft)).compile(
            UserRequest(
                request_id="choose-list-submit",
                raw_text="Select Ertha from the list and click Submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    selection, submit = result.task_spec.obligations
    assert selection.relation == TaskObligationRelation.IS_SELECTED
    assert submit.subject == "submit_button"
    assert submit.relation == TaskObligationRelation.IS_COMPLETED
    assert submit.depends_on == (selection.obligation_id,)


def test_llm_compiler_preserves_multiple_collection_members_as_typed_values() -> None:
    draft = IntentDraft(
        objective="Select Lumen, Vela from the results list and click Submit.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="results list",
                source_ref="multi-select",
            ),
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="results list selection",
                source_ref="multi-select",
            ),
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="Submit button",
                source_ref="multi-select",
            ),
        ),
        candidate_success_criteria=(
            "Lumen and Vela are selected in the results list.",
            "The Submit button is clicked.",
        ),
        task_structure=TaskStructure.MULTI_STAGE,
    )

    result = asyncio.run(
        LLMIntentCompiler(FixedModel(draft)).compile(
            UserRequest(
                request_id="multi-select",
                raw_text="Select Lumen, Vela from the results list and click Submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    selection, submit = result.task_spec.obligations
    assert selection.subject == "results list"
    assert selection.relation == TaskObligationRelation.IS_SELECTED
    assert selection.interaction_values == ("Lumen", "Vela")
    assert submit.depends_on == (selection.obligation_id,)


def test_llm_compiler_preserves_slider_numeric_value_in_multistage_graph() -> None:
    draft = IntentDraft(
        objective="Select 7 with the slider, click the 3rd checkbox, then hit Submit.",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="slider",
                source_ref="form-sequence",
            ),
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="3rd checkbox",
                source_ref="form-sequence",
            ),
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="Submit button",
                source_ref="form-sequence",
            ),
        ),
        candidate_success_criteria=("Slider value is 7.", "The 3rd checkbox is checked.", "Form submitted."),
        task_structure=TaskStructure.MULTI_STAGE,
    )
    model = FixedModel(draft)

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="form-sequence",
                raw_text="Select 7 with the slider, click the 3rd checkbox, then hit Submit.",
            )
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    slider_obligation = result.task_spec.obligations[0]
    assert slider_obligation.subject == "slider"
    assert slider_obligation.relation == TaskObligationRelation.EQUALS
    assert slider_obligation.value_source == TaskObligationValueSource.LITERAL
    assert slider_obligation.expected_value == "7"
    assert slider_obligation.typed_evidence_requirements[0].value_ref == "7"


def test_llm_compiler_repairs_a_provider_malformed_obligation_without_trusting_it() -> None:
    claims, obligations = _terminal_authority("provider-schema", "pricing read")
    repaired = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="provider-schema",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
        candidate_source_claims=claims,
        candidate_obligations=obligations,
    )
    model = ProviderSchemaRepairingModel(repaired, repaired_draft=repaired)

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="provider-schema", raw_text="Read pricing")
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert model.calls == 2


def test_llm_compiler_repair_remains_fail_closed_when_repair_introduces_ambiguity() -> None:
    initial = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="repair-unsafe",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
    )
    claims, obligations = _terminal_authority("repair-unsafe", "pricing read")
    repaired = initial.model_copy(
        update={
            "candidate_source_claims": claims,
            "candidate_obligations": obligations,
            "ambiguities": (
                IntentAmbiguity(
                    field="pricing scope",
                    reason="scope is unresolved",
                    blocking=True,
                    risk="high",
                ),
            ),
        }
    )
    model = RepairingModel(initial, repaired_draft=repaired)

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="repair-unsafe", raw_text="Read pricing")
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert model.calls == 2


def test_llm_compiler_traces_failed_repair_without_crediting_it_as_success() -> None:
    initial = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="repair-failure",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
        task_structure=TaskStructure.MULTI_STAGE,
    )
    model = FailingRepairModel(initial)
    trace = TraceDag("repair-failure")

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="repair-failure", raw_text="Read pricing"), trace=trace
        )
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert model.calls == 2
    failed = next(node.payload for node in trace.nodes if node.kind == "IntentDraftRepairFailed")
    assert failed["prompt_version"] == INTENT_DRAFT_REPAIR_PROMPT_VERSION
    assert failed["error_type"] == "StructuredModelError"


def test_llm_compiler_fails_closed_before_model_call_when_source_ledger_is_bounded() -> None:
    model = UnexpectedModelCall()
    trace = TraceDag("ledger-bound")
    raw_text = " ".join(f"Clause {index}." for index in range(33))

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="ledger-bound", raw_text=raw_text),
            trace=trace,
        )
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.issues[0].code == "source_ledger_unavailable"
    assert model.calls == 0
    assert [node.kind for node in trace.nodes] == [
        "UserRequestReceived",
        "IntentCompilationRejected",
    ]


def test_llm_compiler_allows_deterministic_ready_when_optional_audit_budget_is_exhausted() -> None:
    initial = IntentDraft(
        objective="Read pricing",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.READ_ONLY,
                target="pricing",
                source_ref="repair-budget",
            ),
        ),
        candidate_success_criteria=("pricing returned",),
    )
    claims, obligations = _terminal_authority("repair-budget", "pricing read")
    repaired = initial.model_copy(
        update={"candidate_source_claims": claims, "candidate_obligations": obligations}
    )
    model = RepairingModel(initial, repaired_draft=repaired)
    compiler = LLMIntentCompiler(model, max_model_calls=2)

    result = asyncio.run(
        compiler.compile(UserRequest(request_id="repair-budget", raw_text="Read pricing"))
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert model.calls == 2
    assert compiler.model_call_count == 2


def test_compiler_binds_only_raw_text_alias_to_current_request_lineage() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Enter an item that starts with Com",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    target="item",
                    source_ref="raw_text",
                ),
            ),
            candidate_success_criteria=("matching item entered",),
            candidate_semantic_value_constraints=(
                SemanticValueConstraint(
                    relation=SemanticValueRelation.PREFIX,
                    value="Com",
                    source_ref="raw_text",
                ),
            ),
            candidate_source_claims=(
                SourcedTaskClaim(
                    claim_id="claim-effect",
                    kind=TaskClaimKind.EFFECT,
                    statement="matching item entered",
                    source_ref="raw_text",
                ),
            ),
            candidate_obligations=(
                TaskObligationSpec(
                    obligation_id="obligation-effect",
                    kind=TaskObligationKind.EFFECT,
                    subject="matching item",
                    relation=TaskObligationRelation.IS_COMPLETED,
                    claim_ids=("claim-effect",),
                    evidence_requirements=("matching item is independently observed",),
                    terminal=True,
                ),
            ),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(
                request_id="request-prefix",
                raw_text="Enter an item that starts with Com",
            )
        )
    )

    assert result.task_spec is not None
    assert result.task_spec.semantic_value_constraints[0].source_ref == (
            "request-prefix:source:request:whole"
    )
    assert result.task_spec.source_claims[0].source_ref == "request-prefix:source:request:whole"
    assert result.task_spec.obligations[0].claim_ids == (
        result.task_spec.source_claims[0].claim_id,
    )
    assert result.task_spec.source_claims[0].claim_id != "claim-effect"
    assert result.task_spec.obligations[0].obligation_id != "obligation-effect"
    assert result.task_spec.targets == ("item",)


def test_llm_compiler_produces_draft_but_deterministic_policy_decides() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Send the report",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                    target="report",
                    capability="external.send",
                    source_ref="request-send",
                ),
            ),
            candidate_success_criteria=("recipient receives report",),
        )
    )
    compiler = LLMIntentCompiler(
        model,
        validator=IntentDraftValidator(
            CompilationPolicy(allowed_requested_capabilities=frozenset({"report.read"}))
        ),
    )

    result = asyncio.run(
        compiler.compile(UserRequest(request_id="request-send", raw_text="Send the report"))
    )

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert result.task_spec is None
    assert result.issues[0].code == "capability_not_allowed"
    assert "Send the report" in model.messages[1].content
    assert len(model.message_batches) == 1


def test_llm_compiler_cannot_override_blocking_ambiguity() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Send the report",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                    target="report",
                    source_ref="request-send",
                ),
            ),
            candidate_success_criteria=("report sent",),
            ambiguities=(
                IntentAmbiguity(
                    field="recipient",
                    reason="recipient is missing",
                    blocking=True,
                    risk="high",
                ),
            ),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="request-send", raw_text="Send the report")
        )
    )

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert len(model.message_batches) == 1


def test_compiler_trace_records_redacted_lineage_and_model_boundary() -> None:
    claims, obligations = _terminal_authority("request-read", "pricing read")
    model = FixedModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="request-read",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
            candidate_source_claims=claims,
            candidate_obligations=obligations,
        )
    )
    trace = TraceDag("request-read")

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="request-read", raw_text="Read pricing with private wording"),
            trace=trace,
        )
    )

    assert result.status == CompilationStatus.READY
    assert [node.kind for node in trace.nodes] == [
        "UserRequestReceived",
        "SourceLedgerBuilt",
        "IntentDraftProduced",
        "TaskObligationCoverageReviewed",
        "TaskSpecCreated",
    ]
    assert "private wording" not in str(trace.to_dict())
    source_ledger = trace.nodes[1].payload
    assert source_ledger["redaction"]["source_content"] == "sha256_and_length_only"
    assert source_ledger["source_units"][0]["source_unit_id"] == (
        "request-read:source:request:whole"
    )
    assert trace.nodes[-1].parents == [trace.nodes[-2].id]


def test_llm_compiler_retries_one_typed_structured_output_failure() -> None:
    claims, obligations = _terminal_authority("schema-retry", "pricing read")
    model = SchemaRetryModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="schema-retry",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
            candidate_source_claims=claims,
            candidate_obligations=obligations,
        )
    )
    trace = TraceDag("schema-retry")

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="schema-retry", raw_text="Read pricing"),
            trace=trace,
        )
    )

    assert result.status == CompilationStatus.READY
    assert model.draft_attempts == 2
    retry = next(node for node in trace.nodes if node.kind == "IntentDraftSchemaRetry")
    assert retry.payload == {
        "attempt": 1,
        "error_type": "StructuredOutputError",
        "maximum": 1,
        "prompt_version": INTENT_COMPILER_PROMPT_VERSION,
    }


def test_llm_compiler_does_not_retry_untyped_model_boundary_failure() -> None:
    class BudgetFailureModel(FixedModel):
        calls = 0

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, output_schema, config
            self.calls += 1
            raise StructuredModelError("intake model call budget exhausted")

    model = BudgetFailureModel(IntentDraft())

    with pytest.raises(StructuredModelError, match="budget exhausted"):
        asyncio.run(
            LLMIntentCompiler(model).compile(
                UserRequest(request_id="budget-failure", raw_text="Read pricing")
            )
        )

    assert model.calls == 1


def test_raw_language_compiler_rejects_missing_obligation_authority() -> None:
    model = FixedModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="request-read",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="request-read", raw_text="Read pricing")
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER


def test_raw_language_compiler_projects_invalid_graph_to_typed_rejection() -> None:
    claims, obligations = _terminal_authority("request-read", "pricing read")
    prerequisite = TaskObligationSpec(
        obligation_id="obligation-prerequisite",
        kind=TaskObligationKind.PREDICATE,
        subject="pricing",
        relation=TaskObligationRelation.IS_VISIBLE,
        claim_ids=(claims[0].claim_id,),
        depends_on=(obligations[0].obligation_id,),
        evidence_requirements=("fresh pricing evidence",),
    )
    cyclic_obligation = obligations[0].model_copy(
        update={"depends_on": (prerequisite.obligation_id,)}
    )
    model = FixedModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="request-read",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
            candidate_source_claims=claims,
            candidate_obligations=(prerequisite, cyclic_obligation),
        )
    )

    result = asyncio.run(
        LLMIntentCompiler(model).compile(
            UserRequest(request_id="request-read", raw_text="Read pricing")
        )
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.obligations[0].construction_source == GraphConstructionSource.CANONICAL_COMPILER


def test_independent_coverage_rejection_cannot_create_taskspec() -> None:
    claims, obligations = _terminal_authority("request-read", "pricing read")
    model = FixedModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="request-read",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
            candidate_source_claims=claims,
            candidate_obligations=obligations,
        )
    )
    review = TaskObligationCoverageReview(
        status=TaskObligationCoverageStatus.UNSUPPORTED,
        uncovered_source_quotes=("Read pricing",),
    )
    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=FixedCoverageChecker(
                TaskObligationCoverageDecision(
                    status=TaskObligationCoverageStatus.UNSUPPORTED,
                    issue_code="uncovered_task_clause",
                    issue_detail="Read pricing",
                    review=review,
                )
            ),
        ).compile(UserRequest(request_id="request-read", raw_text="Read pricing"))
    )

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[0].code == "uncovered_task_clause"


def test_invalid_coverage_audit_quote_cannot_veto_deterministic_ready() -> None:
    claims, obligations = _terminal_authority("request-read", "pricing read")
    model = FixedModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="request-read",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
            candidate_source_claims=claims,
            candidate_obligations=obligations,
        )
    )
    invalid_review = TaskObligationCoverageReview(
        status=TaskObligationCoverageStatus.UNSUPPORTED,
        uncovered_source_quotes=("invented clause",),
    )
    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=FixedCoverageChecker(
                TaskObligationCoverageDecision(
                    status=TaskObligationCoverageStatus.UNSUPPORTED,
                    issue_code="coverage_review_invalid_quote",
                    review=invalid_review,
                )
            ),
        ).compile(UserRequest(request_id="request-read", raw_text="Read pricing"))
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert not result.issues


def test_independent_coverage_ambiguity_becomes_clarification() -> None:
    claims, obligations = _terminal_authority("request-read", "pricing read")
    model = FixedModel(
        IntentDraft(
            objective="Read pricing",
            requested_effects=(
                RequestedEffect(
                    operation_class=OperationClass.READ_ONLY,
                    target="pricing",
                    source_ref="request-read",
                ),
            ),
            candidate_success_criteria=("pricing returned",),
            candidate_source_claims=claims,
            candidate_obligations=obligations,
        )
    )
    result = asyncio.run(
        LLMIntentCompiler(
            model,
            coverage_checker=FixedCoverageChecker(
                TaskObligationCoverageDecision(
                    status=TaskObligationCoverageStatus.NEEDS_CLARIFICATION,
                    issue_code="unresolved_task_dependency",
                    issue_detail="pricing",
                )
            ),
        ).compile(UserRequest(request_id="request-read", raw_text="Read pricing"))
    )

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert result.issues[0].code == "unresolved_task_dependency"
