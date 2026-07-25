import asyncio
from dataclasses import dataclass
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.benchmarks.intent_compilation import (
    IntentCompilationCase,
    controlled_intent_cases,
    run_intent_compilation_suite,
)
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.task_intake import (
    CompilationStatus,
    IntentAmbiguity,
    IntentDraft,
    OperationClass,
    RequestedEffect,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class FixedModel:
    draft: IntentDraft
    provider: str = "fixed"
    model: str = "fixed-v1"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        if output_schema.__name__ == "TaskObligationCoverageReview":
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
        return output_schema.model_validate(self.draft.model_dump())


def test_controlled_intent_suite_has_thirty_balanced_cases() -> None:
    cases = controlled_intent_cases()

    assert len(cases) == 30
    assert {case.expected_operation for case in cases} == set(OperationClass)
    assert sum(case.expected_status == CompilationStatus.NEEDS_CLARIFICATION for case in cases) == 5


def test_intent_compilation_report_attributes_semantic_and_safety_results() -> None:
    compiler = LLMIntentCompiler(
        FixedModel(
            IntentDraft(
                objective="Send report",
                requested_effects=(
                    RequestedEffect(
                        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
                        target="report",
                        capability="report.send",
                        source_ref="case-1",
                    ),
                ),
                candidate_success_criteria=("report sent",),
                ambiguities=(
                    IntentAmbiguity(
                        field="recipient",
                        reason="missing recipient",
                        blocking=True,
                        risk="high",
                    ),
                ),
            )
        )
    )
    report = asyncio.run(
        run_intent_compilation_suite(
            compiler,
            (
                IntentCompilationCase(
                    case_id="case-1",
                    raw_text="Send the report",
                    expected_status=CompilationStatus.NEEDS_CLARIFICATION,
                    expected_operation=OperationClass.EXTERNAL_SIDE_EFFECT,
                    target_terms=("report",),
                ),
            ),
        )
    ).to_dict()

    assert report["schema_valid_rate"] == 1.0
    assert report["status_accuracy"] == 1.0
    assert report["safe_stop_rate"] == 1.0
    assert report["compiler_failure_count"] == 0
