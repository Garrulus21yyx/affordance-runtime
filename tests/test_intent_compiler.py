import asyncio
from dataclasses import dataclass
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.intent_compiler import (
    INTENT_COMPILER_PROMPT_VERSION,
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
    UserRequest,
)
from affordance_runtime.trace import TraceDag

T = TypeVar("T", bound=BaseModel)


@dataclass
class FixedModel:
    draft: IntentDraft
    provider: str = "fixed"
    model: str = "fixed-v1"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    messages: Sequence[ModelMessage] = ()

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        self.messages = messages
        assert output_schema is LLMIntentDraft
        assert config.prompt_version == INTENT_COMPILER_PROMPT_VERSION
        return output_schema.model_validate(self.draft.model_dump())


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


def test_compiler_trace_records_redacted_lineage_and_model_boundary() -> None:
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
        "TaskSpecCreated",
    ]
    assert "private wording" not in str(trace.to_dict())
    assert trace.nodes[-1].parents == [trace.nodes[-2].id]
