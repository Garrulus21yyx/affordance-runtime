from __future__ import annotations

import json

from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import AgentLoopStatus, AskUser, SelectAction
from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
)
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.transition_digest_projection import (
    project_latest_transition,
)
from affordance_runtime.agent.control_reducer import (
    ApplyContinuation,
    ApplyUserInputContinuation,
    ControlAccepted,
    ControlRejected,
    ControlState,
    reduce_control,
)
from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    AdmissionSummary,
    ControlContinuation,
    ControlTransition,
    ControlTransitionScope,
    PendingKind,
    ProgressDelta,
)
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.agent.user_input import UserInputContinuation
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    EvaluatedOutput,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.model.policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import _build_request
from affordance_runtime.world.acquisition import AcquisitionOrigin, AcquisitionStatus
from tests.integration.agent.test_agent_loop import _task, _world


def _evaluation(observation_id: str, *, satisfied: bool) -> TaskEvaluation:
    status = (
        CriterionEvaluationStatus.SATISFIED
        if satisfied
        else CriterionEvaluationStatus.UNSATISFIED
    )
    evidence = (f"fact:{observation_id}:enabled",) if satisfied else ()
    return TaskEvaluation(
        _task().task_id,
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "task remains open",
        (CriterionEvaluation("shared_enabled", status, evidence, "verified state"),),
        outputs=(
            (EvaluatedOutput("enabled_value", True, evidence),)
            if satisfied
            else ()
        ),
    )


def test_context_projects_latest_root_once_and_removes_it_from_older_history() -> None:
    before = _world("before", False)
    after = _world("after", True)
    state = AgentLoopState(before, current_task_evaluation=_evaluation("before", satisfied=False))
    action_space = ActionSpaceBuilder().build(_task(), before)
    option = action_space.options[0]
    decision = SelectAction("context:one", option.action_id)
    scope = ControlTransitionScope(state, decision)
    scope.record_admission(AdmissionStatus.ADMITTED, "action_admitted")
    scope.record_execution_receipt(
        AttemptReceipt(
            "attempt:1",
            AttemptOperation.EXECUTE,
            "post_action",
            AcquisitionOrigin.POST_ACTION,
            AcquisitionOrigin.POST_ACTION,
            AttemptDisposition.RETURNED,
            "post_action_acquired",
            1,
            1,
            1,
            0,
            DispatchStatus.SENT,
            "request:one",
            "request:one",
            True,
            acquisition_status=AcquisitionStatus.ACQUIRED,
        ),
        "request:one",
        ActionIntent("activate", "shared-toggle"),
        ActionResult("request:one", DispatchStatus.SENT, "dom", True),
    )
    state.current_observation = after
    after_evaluation = _evaluation("after", satisfied=True)
    scope.record_after("after")
    scope.record_evaluations(
        ActionEvaluation(
            "request:one",
            "before",
            "after",
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            "shared state changed",
            ("fact:after:enabled",),
        ),
        after_evaluation,
    )
    transition = scope.finalize(state, None)
    state.current_task_evaluation = after_evaluation
    current_space = ActionSpaceBuilder().build(_task(), after)

    context = ContextBuilder().build(_task(), state, current_space, after_evaluation)

    assert context.history.items == ()
    assert context.history.total_count == 0
    digest = context.last_transition
    assert digest is not None
    assert digest.transition_id == transition.transition_id
    assert digest.lineage.before_observation_id == "before"
    assert digest.lineage.after_observation_id == "after"
    assert digest.previous_decision.semantic_action == "activate"
    assert digest.previous_decision.target_ref == "E1"
    assert digest.execution_outcome.dispatch_status == "sent"
    assert digest.effect_assessment.status == "effect_confirmed"
    criterion = digest.progress_delta.criterion_transitions.items[0]
    assert (criterion.before_status, criterion.after_status) == (
        "unsatisfied",
        "satisfied",
    )
    assert digest.progress_delta.output_transitions.items[0].operation == "became_available"

    catalog = compile_grounded_action_catalog(context)
    messages = GroundedPolicyContextBinder().action_messages(
        context,
        catalog.specs,
        _build_request(context),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        include_tool_menu=True,
    )
    content = messages[1].content
    assert isinstance(content, str)
    public = json.loads(content)
    assert public["last_transition"]["transition_id"] == transition.transition_id
    assert public["history"]["items"] == []


def test_confirmation_continuation_replaces_same_root_projection_exactly_once() -> None:
    before_evaluation = _evaluation("observation:1", satisfied=False)
    after_evaluation = _evaluation("observation:2", satisfied=True)
    root = ControlTransition(
        "transition:1",
        1,
        "observation:1",
        SelectAction("context:one", "action:one"),
        AdmissionSummary(AdmissionStatus.CONFIRMATION_REQUIRED, "confirmation_required"),
        None,
        (),
        None,
        (),
        (),
        "observation:1",
        None,
        None,
        ProgressDelta(),
        PendingKind.CONFIRMATION,
        AgentLoopStatus.WAITING_CONFIRMATION,
        "confirmation_required",
        before_task_evaluation=before_evaluation,
    )
    state = ControlState((root,), 1, (("SelectAction", 1),))
    continuation = ControlContinuation(
        root.transition_id,
        "observation:2",
        None,
        (),
        (),
        None,
        (),
        None,
        "",
        None,
        after_evaluation,
        ProgressDelta(),
        PendingKind.NONE,
        None,
        "confirmation_resolved",
    )

    accepted = reduce_control(state, ApplyContinuation(continuation))

    assert isinstance(accepted, ControlAccepted)
    assert accepted.state.total_count == 1
    assert len(accepted.state.recent_transitions) == 1
    updated = accepted.state.recent_transitions[0]
    assert updated.transition_id == root.transition_id
    assert updated.before_task_evaluation is before_evaluation
    digest = project_latest_transition(
        accepted.state.recent_transitions,
        AgentGroundingIndexView(),
        max_progress_changes=32,
        max_evidence_refs=16,
    )
    assert digest is not None
    assert digest.transition_id == root.transition_id
    assert digest.lineage.after_observation_id == "observation:2"
    assert digest.progress_delta.criterion_transitions.items[0].after_status == "satisfied"
    assert isinstance(
        reduce_control(accepted.state, ApplyContinuation(continuation)),
        ControlRejected,
    )


def test_progress_transition_sections_are_truthfully_bounded() -> None:
    criteria_before = tuple(
        CriterionEvaluation(
            f"criterion:{index}",
            CriterionEvaluationStatus.UNSATISFIED,
            (),
            "pending",
        )
        for index in range(5)
    )
    criteria_after = tuple(
        CriterionEvaluation(
            f"criterion:{index}",
            CriterionEvaluationStatus.SATISFIED,
            (f"fact:observation:2:{index}",),
            "verified",
        )
        for index in range(5)
    )
    before = TaskEvaluation(
        "task",
        "observation:1",
        TaskEvaluationStatus.INCOMPLETE,
        "before",
        criteria_before,
    )
    after = TaskEvaluation(
        "task",
        "observation:2",
        TaskEvaluationStatus.INCOMPLETE,
        "after",
        criteria_after,
    )
    transition = ControlTransition(
        "transition:1",
        1,
        "observation:1",
        SelectAction("context:one", "action:one"),
        AdmissionSummary(AdmissionStatus.ADMITTED, "action_admitted"),
        None,
        (),
        None,
        (),
        (),
        "observation:2",
        None,
        after,
        ProgressDelta(),
        PendingKind.NONE,
        AgentLoopStatus.RUNNING,
        "action_evaluated",
        before_task_evaluation=before,
    )

    digest = project_latest_transition(
        (transition,),
        AgentGroundingIndexView(),
        max_progress_changes=2,
        max_evidence_refs=1,
    )

    assert digest is not None
    section = digest.progress_delta.criterion_transitions
    assert len(section.items) == 2
    assert section.total_count == 5
    assert section.truncated is True
    assert all(item.evidence_refs.total_count == 1 for item in section.items)


def test_user_input_continuation_replaces_same_root_projection_exactly_once() -> None:
    root = ControlTransition(
        "transition:1",
        1,
        "observation:1",
        AskUser("context:one", "Which value?", ("value",)),
        None,
        None,
        (),
        None,
        (),
        (),
        "observation:1",
        None,
        None,
        ProgressDelta(),
        PendingKind.USER,
        AgentLoopStatus.WAITING_USER,
        "user_input_requested",
    )
    state = ControlState((root,), 1, (("AskUser", 1),))
    continuation = UserInputContinuation(
        "user-input:0123456789abcdef01234567",
        root.transition_id,
        "task",
        1,
        2,
    )

    accepted = reduce_control(state, ApplyUserInputContinuation(continuation))

    assert isinstance(accepted, ControlAccepted)
    assert accepted.state.total_count == 1
    updated = accepted.state.recent_transitions[0]
    assert updated.transition_id == root.transition_id
    digest = project_latest_transition(
        accepted.state.recent_transitions,
        AgentGroundingIndexView(),
        max_progress_changes=32,
        max_evidence_refs=16,
    )
    assert digest is not None
    assert digest.execution_outcome.reason_code == "user_input_submitted"
    assert isinstance(
        reduce_control(accepted.state, ApplyUserInputContinuation(continuation)),
        ControlRejected,
    )
