from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

from affordance_runtime.model.providers.port import (
    StructuredOutputError,
    StructuredOutputViolation,
)
from affordance_runtime.model.task_revision_compiler import (
    ModelBackedTaskRevisionCompiler,
    RevisedTaskGoalModel,
    RevisionLoopBudgetModel,
    TaskRevisionCompilerModelResponse,
)
from affordance_runtime.task import (
    RevisionNeedsInput,
    RevisionNoChange,
    RevisionReady,
    TaskGoal,
    TaskRevisionRequest,
)


@dataclass
class ScriptedModelPort:
    outcomes: list[object]
    provider: str = "zhipu"
    model: str = "glm-test"
    endpoint_class: str = "fixture"
    last_call: object | None = None
    last_transcript: object | None = None
    messages: list[tuple[object, ...]] = field(default_factory=list)

    @property
    def supports_multimodal(self) -> bool:
        return False

    async def generate_structured(self, messages, output_schema, config):
        index = len(self.messages) + 1
        self.messages.append(tuple(messages))
        self.last_call = SimpleNamespace(
            response_id=f"response:{index}",
            latency_ms=float(index),
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
        )
        self.last_transcript = {
            "llm.input_messages": [{"role": "user", "content": f"input:{index}"}],
            "llm.output_messages": [
                {"role": "assistant", "content": f"raw:{index}"}
            ],
        }
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _goal() -> RevisedTaskGoalModel:
    return RevisedTaskGoalModel(
        instruction="Inspect the current account and its owner.",
        constraints=(),
        allowed_effects=(),
        forbidden_effects=(),
        inputs={},
        success_criteria=(),
        requested_outputs=(),
        risk_profile="read_only",
        material_bindings=(),
        loop_budget=RevisionLoopBudgetModel(max_turns=20, max_observations=40),
        evaluation_spec=None,
    )


def _request() -> TaskRevisionRequest:
    return TaskRevisionRequest(
        TaskGoal("task:revision", "Inspect the current account."),
        "Also include its owner.",
    )


def test_model_compiler_returns_complete_ready_proposal_once() -> None:
    port = ScriptedModelPort(
        [TaskRevisionCompilerModelResponse(disposition="ready", goal=_goal())]
    )
    compiler = ModelBackedTaskRevisionCompiler(port)

    outcome = asyncio.run(compiler.compile(_request()))

    assert isinstance(outcome, RevisionReady)
    assert outcome.task_revision == 1
    assert outcome.proposal.instruction.endswith("owner.")
    assert outcome.proposal.boundary.risk_profile.value == "read_only"
    assert compiler.last_model_call_count == 1
    assert compiler.last_invocation_result is not None
    assert compiler.last_invocation_result.lineage["role"] == "TaskRevisionCompiler"


def test_model_compiler_preserves_all_nonready_dispositions() -> None:
    needs = ModelBackedTaskRevisionCompiler(
        ScriptedModelPort(
            [
                TaskRevisionCompilerModelResponse(
                    disposition="needs_input",
                    question="Which owner?",
                    missing_fields=("owner",),
                )
            ]
        )
    )
    no_change = ModelBackedTaskRevisionCompiler(
        ScriptedModelPort(
            [
                TaskRevisionCompilerModelResponse(
                    disposition="no_change",
                    reason="already_equivalent",
                )
            ]
        )
    )

    assert asyncio.run(needs.compile(_request())) == RevisionNeedsInput(
        1,
        "Which owner?",
        ("owner",),
    )
    assert asyncio.run(no_change.compile(_request())) == RevisionNoChange(
        1,
        "already_equivalent",
    )


def test_model_compiler_allows_one_structured_output_repair_with_transcripts() -> None:
    port = ScriptedModelPort(
        [
            StructuredOutputError(
                "invalid",
                violations=(StructuredOutputViolation("$", "json_invalid"),),
            ),
            TaskRevisionCompilerModelResponse(disposition="ready", goal=_goal()),
        ]
    )
    compiler = ModelBackedTaskRevisionCompiler(port)

    outcome = asyncio.run(compiler.compile(_request()))

    assert isinstance(outcome, RevisionReady)
    assert compiler.last_schema_repair_count == 1
    assert [attempt.phase for attempt in compiler.last_generation_attempts] == [
        "task_revision_compile_initial",
        "task_revision_compile_schema_repair",
    ]
    assert all(attempt.transcript is not None for attempt in compiler.last_generation_attempts)
