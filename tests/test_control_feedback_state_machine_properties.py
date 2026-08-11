from __future__ import annotations

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st
from test_control_state_machine_properties import _root

from affordance_runtime.agent.control_feedback import (
    ControlFeedback,
    ControlFeedbackKind,
    ControlFeedbackSource,
    FeedbackBudgetDisposition,
    NextDecisionDisposition,
    apply_feedback_budget,
)
from affordance_runtime.agent.control_reducer import (
    AppendRoot,
    ControlAccepted,
    ControlRejected,
    ControlState,
    reduce_control,
)
from affordance_runtime.agent.control_transition import AdmissionStatus, AdmissionSummary
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.state import AgentLoopState


def _feedback(scope: str, issue: str, source: ControlFeedbackSource) -> ControlFeedback:
    no_gain = source is not ControlFeedbackSource.ACTION_ADMISSION
    return ControlFeedback(
        ControlFeedbackKind.NO_INFORMATION_GAIN if no_gain else ControlFeedbackKind.REPAIRABLE_REJECTION,
        "control_no_gain" if no_gain else "invalid_action_parameters",
        source,
        NextDecisionDisposition.CHANGE_STRATEGY if no_gain else NextDecisionDisposition.CORRECT_OR_REPLAN,
        no_gain,
        None,
        ("observation",) if source is ControlFeedbackSource.POLICY_OBSERVATION else (
            ("actions",) if source is ControlFeedbackSource.ACTION_PAGE else ("parameters",)
        ),
        scope,
        issue,
        "c" * 64 if no_gain else "",
        "d" * 64 if no_gain else "",
    )


@given(st.lists(st.sampled_from(("1", "2", "3")), min_size=1, max_size=12))
@settings(max_examples=80)
def test_generated_shared_budget_is_history_suffix_independent(sequence: list[str]) -> None:
    scope = "a" * 64
    consumed: tuple[str, ...] = ()
    seen: set[str] = set()
    terminated = False
    sources = (
        ControlFeedbackSource.ACTION_ADMISSION,
        ControlFeedbackSource.ACTION_PAGE,
        ControlFeedbackSource.POLICY_OBSERVATION,
    )
    for index, token in enumerate(sequence):
        issue = token * 64
        decision = apply_feedback_budget(scope, consumed, _feedback(scope, issue, sources[index % 3]))
        expected_terminal = issue in seen or len(seen) >= 2
        assert (decision.disposition is FeedbackBudgetDisposition.TERMINATE) is expected_terminal
        if expected_terminal:
            terminated = True
            break
        seen.add(issue)
        consumed = decision.issue_digests
        assert len(consumed) <= 2
    if terminated:
        assert len(seen) <= 2


def test_strategy_feedback_does_not_consume_shared_issue_budget() -> None:
    feedback = ControlFeedback(
        ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED,
        "already_satisfied_change_strategy",
        ControlFeedbackSource.PROGRESS_EVENT,
        NextDecisionDisposition.CHANGE_STRATEGY,
        True,
        None,
        (),
        "a" * 64,
        "b" * 64,
    )

    result = apply_feedback_budget("a" * 64, ("c" * 64,), feedback)

    assert result.disposition is FeedbackBudgetDisposition.STRATEGY
    assert result.issue_digests == ("c" * 64,)


def test_reducer_accepts_only_zero_call_rejected_root_with_repair_feedback() -> None:
    feedback = _feedback(
        "a" * 64,
        "b" * 64,
        ControlFeedbackSource.ACTION_ADMISSION,
    )
    root = _root(1)
    root = replace(
        root,
        decision=SelectAction("context:1", "outside"),
        admission=AdmissionSummary(
            AdmissionStatus.REJECTED, "invalid_action_parameters",
        ),
        after_observation_id=root.before_observation_id,
        reason_code="invalid_action_parameters",
        control_feedback=feedback,
    )

    accepted = reduce_control(ControlState(), AppendRoot(root, 3))
    mismatched = reduce_control(
        ControlState(), AppendRoot(replace(root, control_feedback=None), 3),
    )

    assert isinstance(accepted, ControlAccepted)
    assert isinstance(mismatched, ControlRejected)
    assert mismatched.code == "rejected_admission_lifecycle_mismatch"


@given(st.lists(st.integers(min_value=0, max_value=8), min_size=1, max_size=30))
@settings(max_examples=80)
def test_page_result_gain_is_once_only_within_a_control_epoch(
    result_tokens: list[int],
) -> None:
    from test_agent_loop import _world

    state = AgentLoopState(_world("epoch", False))
    epoch = "a" * 64
    initial = "0" * 64
    state.begin_control_epoch(epoch, initial)
    seen = {initial}

    for token in result_tokens:
        digest = f"{token + 1:064x}"
        expected_gain = digest not in seen
        assert state.record_action_page_result(digest) is expected_gain
        seen.add(digest)

    assert set(state.seen_action_page_result_digests) == seen
    assert state.begin_control_epoch(epoch, "f" * 64) is False
    assert set(state.seen_action_page_result_digests) == seen
    assert state.begin_control_epoch("b" * 64, "f" * 64) is True
    assert state.seen_action_page_result_digests == ("f" * 64,)
