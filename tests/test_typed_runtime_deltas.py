from __future__ import annotations

import pytest

from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.stage_protocol import (
    CompletionDelta,
    ProgressDelta,
    RecoveryDelta,
    ResultDelta,
    RuntimeTransition,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag


def test_unknown_runtime_delta_fails_closed() -> None:
    transition = RuntimeTransition(expected_state_version=0, deltas=(object(),))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="unknown runtime delta"):
        RuntimeCommitter().commit(
            StateKernel("run", "goal"),
            TraceDag("run"),
            TraceDag("run").add("root", {}),
            type("Result", (), {"failure": None, "transition": transition, "events": (), "terminal": None})(),
        )


def test_recovery_delta_cannot_mutate_task_plan() -> None:
    delta = RecoveryDelta(disproved_assumption="recovery-only")
    assert not hasattr(delta, "task_plan")


def test_completion_delta_has_no_authority_fields() -> None:
    delta = CompletionDelta(evaluation=object())  # type: ignore[arg-type]
    assert not hasattr(delta, "approval_tokens")
    assert not hasattr(delta, "capabilities")


def test_progress_delta_has_no_recovery_authority() -> None:
    delta = ProgressDelta(latest_verification=None)
    assert not hasattr(delta, "current_recovery_decision")


def test_runtime_transition_rejects_legacy_mutation_channel() -> None:
    with pytest.raises(TypeError):
        RuntimeTransition(expected_state_version=0, phase="acting")  # type: ignore[call-arg]


def test_failed_later_delta_leaves_state_and_trace_unchanged() -> None:
    state = StateKernel("run", "goal")
    trace = TraceDag("run")
    parent = trace.add("root", {})
    before_state = repr(state)
    before_nodes = tuple(trace.nodes)
    result = type(
        "Result",
        (),
        {
            "failure": None,
            "transition": RuntimeTransition(
                expected_state_version=state.version,
                deltas=(ResultDelta({"candidate": "must-not-commit"}), object()),  # type: ignore[arg-type]
            ),
            "events": (),
            "terminal": None,
        },
    )()
    with pytest.raises(TypeError, match="unknown runtime delta"):
        RuntimeCommitter().commit(state, trace, parent, result)
    assert repr(state) == before_state
    assert tuple(trace.nodes) == before_nodes
    assert trace.artifact_index == []
