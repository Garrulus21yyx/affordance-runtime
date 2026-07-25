import asyncio
from dataclasses import dataclass, field
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.intent_compiler import (
    INTENT_COMPILER_PROMPT_VERSION,
    INTENT_DRAFT_REPAIR_PROMPT_VERSION,
    LLMIntentCompiler,
    LLMIntentDraft,
)
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.task_intake import (
    CompilationPolicy,
    CompilationStatus,
    IntentAmbiguity,
    IntentDraft,
    IntentDraftValidator,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    SemanticValueRelation,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    UserRequest,
)
from affordance_runtime.task_obligation_coverage import (
    TaskObligationCoverageDecision,
    TaskObligationCoverageReview,
    TaskObligationCoverageStatus,
)
from affordance_runtime.trace import TraceDag

T = TypeVar("T", bound=BaseModel)


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
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": [
                        item.claim_id
                        for item in self.draft.candidate_source_claims
                        if item.required
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
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": [
                        item.claim_id for item in self.repaired_draft.candidate_source_claims if item.required
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
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": [
                        item.claim_id for item in self.repaired_draft.candidate_source_claims if item.required
                    ],
                }
            )
        raise AssertionError(f"unexpected schema: {output_schema.__name__}")


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
    assert result.task_spec.semantic_value_constraints == (constraint,)
    assert any(
        "never invent a completion" in messages[0].content.casefold()
        for messages in model.message_batches
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
    assert model.calls == 3
    repair = next(node.payload for node in trace.nodes if node.kind == "IntentDraftRepairProduced")
    assert repair["prompt_version"] == INTENT_DRAFT_REPAIR_PROMPT_VERSION
    assert repair["decoding_config"]["prompt_version"] == INTENT_DRAFT_REPAIR_PROMPT_VERSION


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
    assert model.calls == 3
    assert "invalid_provider_obligation" in model.message_batches[1][-1].content


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

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert model.calls == 2


def test_llm_compiler_stops_when_repair_consumes_intake_budget() -> None:
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

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.issues[0].code == "coverage_review_unavailable"
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
        "request-prefix"
    )
    assert result.task_spec.source_claims[0].source_ref == "request-prefix"
    assert result.task_spec.obligations[0].claim_ids == ("claim-effect",)
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
        "IntentDraftProduced",
        "TaskObligationCoverageReviewed",
        "TaskSpecCreated",
    ]
    assert "private wording" not in str(trace.to_dict())
    assert trace.nodes[-1].parents == [trace.nodes[-2].id]


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

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert [item.code for item in result.issues] == [
        "missing_source_claims",
        "missing_task_obligations",
    ]


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

    assert result.status == CompilationStatus.UNSUPPORTED
    assert result.task_spec is None
    assert result.issues[-1].code == "invalid_task_obligation_graph"


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
