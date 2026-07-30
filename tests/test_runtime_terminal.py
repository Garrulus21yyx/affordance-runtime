import pytest

from affordance_runtime.runtime_terminal import (
    TaskCompletionResult,
    TaskCompletionVerifier,
    commit_task_terminal_success,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification import VerificationReport, VerificationStatus


def _task_spec() -> TaskSpec:
    return TaskSpec(
        task_id="terminal-task",
        revision=1,
        objective="save settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("settings",),
        success_criteria=("settings saved",),
        source_request_ref="terminal-test",
    )


def test_task_completion_verifier_requires_independent_passed_verification_for_task_spec() -> None:
    state = StateKernel("terminal-task", "save settings")
    state.effectful_action_count = 1
    verifier = TaskCompletionVerifier()

    missing = verifier.verify(
        task_spec=_task_spec(),
        state=state,
        verification=None,
        result={"saved": True},
    )
    failed = verifier.verify(
        task_spec=_task_spec(),
        state=state,
        verification=VerificationReport(VerificationStatus.FAILED),
        result={"saved": True},
    )
    passed = verifier.verify(
        task_spec=_task_spec(),
        state=state,
        verification=VerificationReport(VerificationStatus.PASSED),
        result={"saved": True},
    )

    assert not missing.passed
    assert missing.reason == "task completion requires an independent passed verification"
    assert not failed.passed
    assert failed.reason == "task completion requires an independent passed verification"
    assert passed.passed
    assert passed.result == {"saved": True}


def test_terminal_success_commit_requires_passed_task_completion_result() -> None:
    state = StateKernel("terminal-task", "save settings")
    trace = TraceDag("run")
    parent = trace.add("TaskCreated", {"state": state.phase})

    with pytest.raises(ValueError, match="task completion verification did not pass"):
        commit_task_terminal_success(
            state=state,
            trace=trace,
            parent=parent,
            completion=TaskCompletionResult.failed("missing verification"),
        )

    assert state.phase != "done"
    assert [node.kind for node in trace.nodes] == ["TaskCreated"]


def test_legacy_task_without_task_spec_remains_compatibility_completion() -> None:
    state = StateKernel("legacy-task", "legacy task")
    result = TaskCompletionVerifier().verify(
        task_spec=None,
        state=state,
        verification=None,
        result={"legacy": True},
    )

    assert result.passed
    assert result.result == {"legacy": True}


def test_task_completion_result_freezes_source_result_payload() -> None:
    raw_result = {"items": ["done"]}
    completion = TaskCompletionResult.passed_with(raw_result)

    raw_result["items"].append("mutated")

    assert completion.result == {"items": ["done"]}
