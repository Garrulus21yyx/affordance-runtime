from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent import (
    Abort,
    AgentLoopStatus,
    AskUser,
    UserInputResumed,
    UserInputResumeRejected,
    UserInputResumeRejectionCode,
)
from affordance_runtime.agent.control_transition import PendingKind
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.user_input import (
    build_user_input_request,
    user_input_revision_rejection,
)
from affordance_runtime.app import (
    TargetRuntime,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.task import (
    NaturalLanguageTaskRequest,
    RiskProfile,
    TaskBoundary,
    TaskGoal,
    TaskInputRequired,
)
from affordance_runtime.world import SemanticTarget, StateFact, WorldObservation
from tests.support.agent.static_environment import StaticEnvironment
from tests.support.world import fused_world


def _world() -> WorldObservation:
    target = SemanticTarget("page", "document", "Current page")
    fact = StateFact("fact:page:available", "page", "available", True, "observation:initial")
    return fused_world(
        "observation:initial", (target,), (fact,), surface="static"
    )


class UnusedActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, before, request, result, after
        raise AssertionError("user-input continuation fixture must not execute")


class InputAwareTaskEvaluator:
    async def evaluate(self, task, observation):
        ready = task.inputs.get("account") == "primary"
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if ready else TaskEvaluationStatus.INCOMPLETE,
            "input present" if ready else "account input required",
            completion_evidence_refs=("fact:page:available",) if ready else (),
        )


class AlwaysIncompleteTaskEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "fixture remains incomplete",
        )


@dataclass
class AskForAccountPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        return AskUser(context.context_id, "Which account should I use?", ("inputs.account",))


@dataclass
class AskThenAbortPolicy:
    identities: list[tuple[str, object]]

    async def decide(self, context):
        self.identities.append((context.context_id, context.task.public_inputs.get("account")))
        if len(self.identities) == 1:
            return AskUser(context.context_id, "Clarify the task", ("inputs.answer",))
        return Abort(context.context_id, "fixture stopped after resume", "user_request")


def _request(*, task_id: str = "task:clarify", revision: int = 1, account: str = ""):
    inputs = {"account": account} if account else {}
    return NaturalLanguageTaskRequest(
        task_id,
        "Inspect the selected account",
        TaskBoundary(inputs=inputs),
        revision=revision,
    )


def test_waiting_user_resumes_with_one_admitted_task_revision() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment((_world(),))
        policy = AskForAccountPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            UnusedActionEvaluator(),
            InputAwareTaskEvaluator(),
        )
        started = await runtime.start_request(environment, _request())
        assert started.session is not None
        session = started.session

        paused = await session.run_until_pause()
        repeated = await session.run_until_pause()

        assert repeated is paused
        assert paused.status is AgentLoopStatus.WAITING_USER
        assert paused.execution_count == 0
        assert paused.user_input_request is not None
        pending = paused.user_input_request
        assert pending.task_id == "task:clarify"
        assert pending.based_on_task_revision == 1
        assert pending.requested_fields == ("inputs.account",)

        resumed = await runtime.submit_user_input(
            session,
            pending.input_request_id,
            _request(revision=2, account="primary"),
        )

        assert isinstance(resumed, UserInputResumed)
        assert resumed.result.status is AgentLoopStatus.DONE
        assert resumed.result.execution_count == 0
        assert resumed.result.task.revision == 2
        assert session.state.task_revision == 2
        assert session.state.pending_user_request is None
        assert environment.task is session.task
        assert policy.calls == 1
        assert session.state.continued_control_root_ids == (pending.source_transition_id,)
        assert len(resumed.result.control_transitions) == 1
        resolved_root = resumed.result.control_transitions[0]
        assert resolved_root.pending_kind is PendingKind.NONE
        assert resolved_root.resulting_status is None
        assert resolved_root.reason_code == "user_input_submitted"

        duplicate = await runtime.submit_user_input(
            session,
            pending.input_request_id,
            _request(revision=2, account="primary"),
        )
        assert isinstance(duplicate, UserInputResumeRejected)
        assert duplicate.code is UserInputResumeRejectionCode.ALREADY_SUBMITTED
        assert session.last_result is resumed.result

    asyncio.run(scenario())


def test_resume_invalidates_old_context_and_appends_a_new_revision_root() -> None:
    async def scenario() -> None:
        policy = AskThenAbortPolicy([])
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            UnusedActionEvaluator(),
            AlwaysIncompleteTaskEvaluator(),
        )
        started = await runtime.start_request(StaticEnvironment((_world(),)), _request())
        assert started.session is not None
        session = started.session
        paused = await session.run_until_pause()
        assert paused.user_input_request is not None

        resumed = await runtime.submit_user_input(
            session,
            paused.user_input_request.input_request_id,
            _request(revision=2, account="primary"),
        )

        assert isinstance(resumed, UserInputResumed)
        assert resumed.result.status is AgentLoopStatus.FAILED
        assert resumed.result.reason_code == "abort_user_request"
        assert [account for _, account in policy.identities] == [None, "primary"]
        assert policy.identities[0][0] != policy.identities[1][0]
        assert resumed.result.execution_count == 0
        assert [type(item.decision).__name__ for item in resumed.result.control_transitions] == [
            "AskUser",
            "Abort",
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("pending_id", "task_id", "revision", "expected"),
    (
        ("wrong", "task:clarify", 2, UserInputResumeRejectionCode.REQUEST_ID_MISMATCH),
        ("pending", "other-task", 2, UserInputResumeRejectionCode.TASK_ID_MISMATCH),
        ("pending", "task:clarify", 1, UserInputResumeRejectionCode.TASK_REVISION_NOT_CONSECUTIVE),
        ("pending", "task:clarify", 3, UserInputResumeRejectionCode.TASK_REVISION_NOT_CONSECUTIVE),
    ),
)
def test_rejected_submission_keeps_the_waiting_session_unchanged(
    pending_id: str,
    task_id: str,
    revision: int,
    expected: UserInputResumeRejectionCode,
) -> None:
    async def scenario() -> None:
        environment = StaticEnvironment((_world(),))
        runtime = TargetRuntime(
            AgentDecisionPorts(AskForAccountPolicy()),
            UnusedActionEvaluator(),
            InputAwareTaskEvaluator(),
        )
        started = await runtime.start_request(environment, _request())
        assert started.session is not None
        session = started.session
        paused = await session.run_until_pause()
        assert paused.user_input_request is not None
        actual_id = paused.user_input_request.input_request_id

        outcome = await runtime.submit_user_input(
            session,
            actual_id if pending_id == "pending" else pending_id,
            _request(task_id=task_id, revision=revision, account="primary"),
        )

        assert isinstance(outcome, UserInputResumeRejected)
        assert outcome.code is expected
        assert session.last_result is paused
        assert session.state.task_revision == 1
        assert session.state.pending_user_request is paused.user_input_request
        assert environment.task is session.task
        assert environment.task is not None and environment.task.revision == 1
        assert session.execution_count == 0

    asyncio.run(scenario())


def test_nonready_revised_intake_never_mutates_the_waiting_session() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment((_world(),))
        runtime = TargetRuntime(
            AgentDecisionPorts(AskForAccountPolicy()),
            UnusedActionEvaluator(),
            InputAwareTaskEvaluator(),
        )
        started = await runtime.start_request(environment, _request())
        assert started.session is not None
        session = started.session
        paused = await session.run_until_pause()
        assert paused.user_input_request is not None

        outcome = await runtime.submit_user_input(
            session,
            paused.user_input_request.input_request_id,
            NaturalLanguageTaskRequest(
                "task:clarify",
                "Modify the selected account",
                TaskBoundary(risk_profile=RiskProfile.LOW),
                revision=2,
            ),
        )

        assert isinstance(outcome, TaskInputRequired)
        assert session.last_result is paused
        assert session.state.task_revision == 1
        assert environment.task is session.task

    asyncio.run(scenario())


def test_environment_without_revision_port_fails_closed() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment((_world(),))
        environment.revise_task = None
        runtime = TargetRuntime(
            AgentDecisionPorts(AskForAccountPolicy()),
            UnusedActionEvaluator(),
            InputAwareTaskEvaluator(),
        )
        started = await runtime.start_request(environment, _request())
        assert started.session is not None
        session = started.session
        paused = await session.run_until_pause()
        assert paused.user_input_request is not None

        outcome = await runtime.submit_user_input(
            session,
            paused.user_input_request.input_request_id,
            _request(revision=2, account="primary"),
        )

        assert isinstance(outcome, UserInputResumeRejected)
        assert outcome.code is UserInputResumeRejectionCode.ENVIRONMENT_REVISION_UNSUPPORTED
        assert session.last_result is paused
        assert session.state.task_revision == 1
        assert session.execution_count == 0

    asyncio.run(scenario())


def test_terminal_session_rejects_new_user_input_without_mutation() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment((_world(),))
        policy = AskForAccountPolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            UnusedActionEvaluator(),
            InputAwareTaskEvaluator(),
        )
        started = await runtime.start_request(
            environment,
            _request(revision=1, account="primary"),
        )
        assert started.session is not None
        session = started.session
        terminal = await session.run_until_pause()
        assert terminal.status is AgentLoopStatus.DONE

        outcome = await runtime.submit_user_input(
            session,
            "user-input:0123456789abcdef01234567",
            _request(revision=2, account="primary"),
        )

        assert isinstance(outcome, UserInputResumeRejected)
        assert outcome.code is UserInputResumeRejectionCode.TERMINAL_SESSION
        assert session.last_result is terminal
        assert environment.task is session.task
        assert session.state.task_revision == 1
        assert policy.calls == 0

    asyncio.run(scenario())


@given(
    current_revision=st.integers(min_value=1, max_value=100),
    delta=st.integers(min_value=-3, max_value=4),
    same_task=st.booleans(),
)
def test_revision_validation_accepts_only_same_task_exactly_plus_one(
    current_revision: int,
    delta: int,
    same_task: bool,
) -> None:
    current = TaskGoal("task", "Inspect", revision=current_revision)
    proposed_revision = max(1, current_revision + delta)
    proposed = TaskGoal(
        "task" if same_task else "other",
        "Inspect",
        revision=proposed_revision,
    )
    pending = build_user_input_request(
        task_id="task",
        task_revision=current_revision,
        context_id="context:current",
        source_transition_id="transition:1",
        question="Clarify",
        requested_fields=(),
    )

    rejection = user_input_revision_rejection(
        pending,
        submitted_request_id=pending.input_request_id,
        current_task=current,
        current_task_revision=current_revision,
        proposed_task=proposed,
    )

    assert (rejection is None) is (same_task and proposed_revision == current_revision + 1)
