from __future__ import annotations

import pytest

from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.stage_protocol import (
    CompletionDelta,
    ProgressDelta,
    RecoveryDelta,
    RuntimeTransition,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag


def test_unknown_runtime_delta_fails_closed() -> None:
    transition = RuntimeTransition(deltas=(object(),))  # type: ignore[arg-type]

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
    delta = CompletionDelta(result_payload={"ok": True})
    assert not hasattr(delta, "approval_tokens")
    assert not hasattr(delta, "capabilities")


def test_progress_delta_has_no_recovery_authority() -> None:
    delta = ProgressDelta(latest_verification=None)
    assert not hasattr(delta, "current_recovery_decision")
