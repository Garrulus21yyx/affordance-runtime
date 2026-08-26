from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from affordance_runtime.task import (
    RevisionConversationContext,
    RevisionConversationTurn,
    RevisionFailed,
    RevisionNeedsInput,
    RevisionNewTaskSuggested,
    RevisionNoChange,
    RevisionReady,
    RevisionUnsupported,
    RiskProfile,
    TaskBoundary,
    TaskGoal,
    TaskRevisionBoundary,
    TaskRevisionProposal,
    revision_outcome_code,
)


def _task() -> TaskGoal:
    return TaskGoal("task:revision", "Inspect the current account.")


def _conversation(text: str) -> RevisionConversationContext:
    return RevisionConversationContext(
        (RevisionConversationTurn("turn:latest", "user", text),),
        "turn:latest",
    )


@dataclass
class Compiler:
    outcome: object
    calls: int = 0

    async def compile(self, request):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def test_revision_boundary_admits_one_complete_typed_proposal() -> None:
    proposal = TaskRevisionProposal(
        "Inspect the current account and its owner.",
        TaskBoundary(risk_profile=RiskProfile.READ_ONLY),
    )
    compiler = Compiler(RevisionReady(1, proposal))

    outcome = asyncio.run(
        TaskRevisionBoundary().resolve(
            compiler,
            _task(),
            _conversation("Also include the owner"),
        )
    )

    assert outcome == RevisionReady(1, proposal)
    assert compiler.calls == 1


@pytest.mark.parametrize(
    ("outcome", "code"),
    (
        (RevisionNeedsInput(1, "Which owner?", ("owner",)), "revision_needs_input"),
        (RevisionNoChange(1, "already_equivalent"), "revision_no_change"),
        (
            RevisionNewTaskSuggested(1, "separate_task"),
            "revision_new_task_suggested",
        ),
        (RevisionUnsupported(1, "not_representable"), "revision_unsupported"),
        (RevisionFailed(1, "compiler_failed"), "revision_failed"),
    ),
)
def test_revision_outcomes_have_one_closed_code(outcome, code) -> None:
    assert revision_outcome_code(outcome) == code
    assert (
        asyncio.run(
            TaskRevisionBoundary().resolve(
                Compiler(outcome),
                _task(),
                _conversation("change"),
            )
        )
        == outcome
    )


def test_revision_boundary_fails_closed_on_exception_or_revision_mismatch() -> None:
    failed = asyncio.run(
        TaskRevisionBoundary().resolve(
            Compiler(RuntimeError("boom")),
            _task(),
            _conversation("change"),
        )
    )
    mismatched = asyncio.run(
        TaskRevisionBoundary().resolve(
            Compiler(RevisionNoChange(2, "wrong revision")),
            _task(),
            _conversation("change"),
        )
    )

    assert failed == RevisionFailed(1, "task_revision_compiler_call_failed")
    assert mismatched == RevisionFailed(1, "task_revision_compiler_revision_mismatch")
