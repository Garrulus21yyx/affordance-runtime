from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from interaction_shell.assistant import (
    AssistantQuestion,
    AssistantTurnResult,
    _complete_gui_goal,
)
from interaction_shell.assistant_port import AssistantSessionPort
from interaction_shell.contracts import (
    Accepted,
    AnswerQuestion,
    AnswerQuestionOffer,
    CancelTask,
    CloseSessionOffer,
    Completion,
    CompletionBlock,
    ConversationTurn,
    FailureBlock,
    GoalAcceptedBlock,
    ReviseTask,
    RevisionAppliedBlock,
    RevisionConversationContext,
    RunStatus,
    RuntimeSessionSnapshot,
    SnapshotUpdated,
    StartTask,
    StartTaskOffer,
    UnavailableSurface,
)
from interaction_shell.port import PortRecoveryInspectionUnsupported


@dataclass
class FakeAssistantRunner:
    calls: int = 0

    async def run(
        self,
        prompt,
        *,
        conversation_id,
        message_history,
        run_gui_task,
    ):
        self.calls += 1
        gui_results = ()
        if prompt == "ask":
            output = AssistantQuestion(prompt="Which city should I use?")
        elif prompt.startswith("gui:"):
            result = await run_gui_task(prompt.removeprefix("gui:"))
            output = f"GUI finished: {result.message}"
            gui_results = (result,)
        else:
            output = f"Direct answer: {prompt}"
        return AssistantTurnResult(
            output=output,
            messages=(*message_history, (conversation_id, prompt, output)),
            gui_results=gui_results,
        )


class PersistentFakeAssistantRunner(FakeAssistantRunner):
    async def latest_checkpoint(self, conversation_id):
        return "assistant-run-1" if conversation_id == "assistant-recover" else None

    async def load_checkpoint(self, conversation_id, checkpoint_id):
        if (conversation_id, checkpoint_id) != ("assistant-recover", "assistant-run-1"):
            raise LookupError(checkpoint_id)
        return (("restored", "history"),)


class FailingAssistantRunner(FakeAssistantRunner):
    async def run(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("private provider detail")


@dataclass
class FakeGuiHandle:
    session_id: str
    expires_at: datetime
    snapshot: RuntimeSessionSnapshot
    events: list[SnapshotUpdated]
    closed: bool = False


class FakeGuiPort:
    def __init__(
        self,
        *,
        wait_for_answer: bool = False,
        terminal_outcome: str = "success",
    ) -> None:
        self.wait_for_answer = wait_for_answer
        self.terminal_outcome = terminal_outcome
        self.open_count = 0
        self.close_count = 0
        self.commands = []
        self.revision_contexts = []

    async def open(self, session_id, expires_at):
        self.open_count += 1
        epoch = f"inner-{secrets.token_urlsafe(16)}"
        return FakeGuiHandle(
            session_id,
            expires_at,
            RuntimeSessionSnapshot(
                schema_version="interaction-shell.v4",
                session_id=session_id,
                event_epoch=epoch,
                expires_at=expires_at,
                command_offers=(
                    StartTaskOffer(kind="start_task"),
                    CloseSessionOffer(kind="close_session"),
                ),
                surface=UnavailableSurface(
                    status="unavailable", reason_code="fake_surface"
                ),
            ),
            [],
        )

    async def inspect(self, session_id):
        del session_id
        return PortRecoveryInspectionUnsupported(
            "recovery_inspection_unsupported", "recovery_reconnector_unavailable"
        )

    async def recover_absent(self, session_id, checkpoint_id, expires_at):
        raise AssertionError((session_id, checkpoint_id, expires_at))

    async def recover_live(self, handle, checkpoint_id):
        raise AssertionError((handle, checkpoint_id))

    async def snapshot(self, handle):
        return handle.snapshot

    async def events(self, handle, after):
        return tuple(event for event in handle.events if event.cursor > after)

    async def forward_viewer_input(self, handle, control_lease_id, forward):
        del handle, control_lease_id, forward
        return False

    async def command(self, handle, command, *, revision_conversation=None):
        self.commands.append(command)
        self.revision_contexts.append(revision_conversation)
        if isinstance(command, StartTask):
            if self.wait_for_answer:
                snapshot = handle.snapshot.model_copy(
                    update={
                        "task_id": "gui-task",
                        "task_revision": 1,
                        "task_text": command.task,
                        "run_status": RunStatus.WAITING_USER,
                        "command_offers": (
                            AnswerQuestionOffer(
                                kind="answer_question",
                                request_id="gui-question",
                                prompt="Continue?",
                            ),
                            CloseSessionOffer(kind="close_session"),
                        ),
                    }
                )
                blocks = (
                    GoalAcceptedBlock(
                        kind="goal_accepted",
                        block_id="inner-goal",
                        occurred_at=datetime.now(UTC),
                        task_revision=1,
                        summary=command.task,
                    ),
                )
            else:
                occurred_at = datetime.now(UTC)
                completion = Completion(
                    outcome=self.terminal_outcome,
                    code=(
                        "gui_done"
                        if self.terminal_outcome == "success"
                        else "gui_runtime_blocked"
                    ),
                    message=(
                        "the page operation completed"
                        if self.terminal_outcome == "success"
                        else "the page operation stopped before completion"
                    ),
                )
                terminal_status = {
                    "success": RunStatus.DONE,
                    "failure": RunStatus.FAILED,
                    "blocked": RunStatus.BLOCKED,
                    "cancelled": RunStatus.CANCELLED,
                }[self.terminal_outcome]
                snapshot = handle.snapshot.model_copy(
                    update={
                        "task_id": "gui-task",
                        "task_revision": 1,
                        "task_text": command.task,
                        "run_status": terminal_status,
                        "completion": completion,
                        "command_offers": (CloseSessionOffer(kind="close_session"),),
                    }
                )
                blocks = (
                    GoalAcceptedBlock(
                        kind="goal_accepted",
                        block_id="inner-goal",
                        occurred_at=occurred_at,
                        task_revision=1,
                        summary=command.task,
                    ),
                    *(
                        (
                            CompletionBlock(
                                kind="completion",
                                block_id="inner-completion",
                                occurred_at=occurred_at,
                                completion=completion,
                            ),
                        )
                        if self.terminal_outcome == "success"
                        else (
                            FailureBlock(
                                kind="failure",
                                block_id="inner-failure",
                                occurred_at=occurred_at,
                                code=completion.code,
                                message=completion.message,
                            ),
                        )
                    ),
                )
        elif isinstance(command, AnswerQuestion):
            completion = Completion(
                outcome="success",
                code="gui_done",
                message=f"continued with {command.answer}",
            )
            snapshot = handle.snapshot.model_copy(
                update={
                    "run_status": RunStatus.DONE,
                    "completion": completion,
                    "command_offers": (CloseSessionOffer(kind="close_session"),),
                }
            )
            blocks = (
                CompletionBlock(
                    kind="completion",
                    block_id="inner-completion-after-answer",
                    occurred_at=datetime.now(UTC),
                    completion=completion,
                ),
            )
        elif isinstance(command, ReviseTask):
            snapshot = handle.snapshot.model_copy(
                update={
                    "task_revision": handle.snapshot.task_revision + 1,
                    "task_text": command.text,
                    "run_status": RunStatus.PAUSED,
                    "command_offers": (CloseSessionOffer(kind="close_session"),),
                }
            )
            blocks = (
                RevisionAppliedBlock(
                    kind="revision_applied",
                    block_id="inner-revision",
                    occurred_at=datetime.now(UTC),
                    task_revision=snapshot.task_revision,
                    goal_description_changed=True,
                ),
            )
        else:
            raise AssertionError(command)
        occurred_at = blocks[0].occurred_at
        cursor = handle.snapshot.event_cursor + 1
        snapshot = snapshot.model_copy(update={"event_cursor": cursor})
        event = SnapshotUpdated(
            schema_version="interaction-shell.v4",
            type="snapshot.updated",
            session_id=handle.session_id,
            event_epoch=handle.snapshot.event_epoch,
            cursor=cursor,
            emitted_at=occurred_at,
            snapshot=snapshot,
            feed_delta=blocks,
        )
        handle.events.append(event)
        handle.snapshot = snapshot
        return Accepted(kind="accepted", command_id=command.command_id, snapshot=snapshot)

    async def close(self, handle):
        if not handle.closed:
            handle.closed = True
            self.close_count += 1


def start(snapshot: RuntimeSessionSnapshot, text: str) -> StartTask:
    return StartTask(
        kind="start_task",
        command_id=secrets.token_urlsafe(12),
        expected_task_revision=snapshot.task_revision,
        expected_run_status=snapshot.run_status,
        task=text,
    )


async def wait_for_status(port, handle, status: RunStatus):
    for _ in range(100):
        snapshot = await port.snapshot(handle)
        if snapshot.run_status is status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"Assistant did not reach {status}")


@pytest.mark.asyncio
async def test_direct_answer_never_opens_browser_and_preserves_follow_up_history():
    runner = FakeAssistantRunner()
    gui = FakeGuiPort()
    port = AssistantSessionPort(runner, gui)
    handle = await port.open("assistant-direct", datetime.now(UTC) + timedelta(hours=1))

    await port.command(handle, start(handle.snapshot, "hello"))
    first = await wait_for_status(port, handle, RunStatus.DONE)
    await port.command(handle, start(first, "follow up"))
    second = await wait_for_status(port, handle, RunStatus.DONE)

    assert gui.open_count == 0
    assert runner.calls == 2
    assert second.completion is not None
    assert second.completion.message == "Direct answer: follow up"
    assert len(handle.messages) == 2


@pytest.mark.asyncio
async def test_gui_capability_is_lazy_and_returns_one_bounded_result_to_outer_runner():
    gui = FakeGuiPort()
    port = AssistantSessionPort(FakeAssistantRunner(), gui)
    handle = await port.open("assistant-gui", datetime.now(UTC) + timedelta(hours=1))
    assert gui.open_count == 0

    await port.command(handle, start(handle.snapshot, "gui:book the selected option"))
    completed = await wait_for_status(port, handle, RunStatus.DONE)

    assert gui.open_count == 1
    assert completed.completion is not None
    assert completed.completion.message == "GUI finished: the page operation completed"
    assert completed.task_text == "gui:book the selected option"
    assert all(block.kind != "completion" or block.completion.code != "gui_done" for event in handle.events for block in event.feed_delta)
    assert any(block.kind == "goal_accepted" for event in handle.events for block in event.feed_delta)


def test_inner_goal_projection_hides_runtime_only_authentication_contract():
    block = GoalAcceptedBlock(
        kind="goal_accepted",
        block_id="inner-goal",
        occurred_at=datetime.now(UTC),
        task_revision=1,
        summary=_complete_gui_goal("在网页中完成用户要求的操作"),
    )

    projected = AssistantSessionPort._project_inner_block(block)

    assert isinstance(projected, GoalAcceptedBlock)
    assert projected.block_id == "gui:inner-goal"
    assert projected.summary == "在网页中完成用户要求的操作"


@pytest.mark.asyncio
async def test_gui_failure_remains_authoritative_over_outer_assistant_text():
    gui = FakeGuiPort(terminal_outcome="blocked")
    port = AssistantSessionPort(FakeAssistantRunner(), gui)
    handle = await port.open("assistant-gui-blocked", datetime.now(UTC) + timedelta(hours=1))

    await port.command(handle, start(handle.snapshot, "gui:open the page"))
    blocked = await wait_for_status(port, handle, RunStatus.BLOCKED)

    assert blocked.completion is not None
    assert blocked.completion.outcome == "blocked"
    assert blocked.completion.code == "gui_runtime_blocked"
    assert blocked.completion.message == "the page operation stopped before completion"
    assert not any(
        isinstance(block, CompletionBlock) and block.completion.code == "assistant_response"
        for event in handle.events
        for block in event.feed_delta
    )
    assert any(
        isinstance(block, FailureBlock) and block.code == "gui_runtime_blocked"
        for event in handle.events
        for block in event.feed_delta
    )


@pytest.mark.asyncio
async def test_public_assistant_failure_is_typed_without_private_exception_details():
    port = AssistantSessionPort(FailingAssistantRunner(), FakeGuiPort())
    handle = await port.open("assistant-failure", datetime.now(UTC) + timedelta(hours=1))

    await port.command(handle, start(handle.snapshot, "fail privately"))
    failed = await wait_for_status(port, handle, RunStatus.FAILED)

    assert failed.completion is not None
    assert failed.completion.code == "assistant_invocation_failed"
    failure = next(
        block
        for event in handle.events
        for block in event.feed_delta
        if block.kind == "failure"
    )
    assert "RuntimeError" not in failure.message
    assert "private provider detail" not in failure.message


@pytest.mark.asyncio
async def test_inner_gui_question_and_answer_remain_on_existing_typed_command_path():
    gui = FakeGuiPort(wait_for_answer=True)
    port = AssistantSessionPort(FakeAssistantRunner(), gui)
    handle = await port.open("assistant-question", datetime.now(UTC) + timedelta(hours=1))

    await port.command(handle, start(handle.snapshot, "gui:complete the form"))
    waiting = await wait_for_status(port, handle, RunStatus.WAITING_USER)
    offer = next(item for item in waiting.command_offers if item.kind == "answer_question")
    admission = await port.command(
        handle,
        AnswerQuestion(
            kind="answer_question",
            command_id="answer-1",
            expected_task_revision=waiting.task_revision,
            expected_run_status=waiting.run_status,
            request_id=offer.request_id,
            answer="yes",
        ),
    )
    assert admission.kind == "accepted"
    completed = await wait_for_status(port, handle, RunStatus.DONE)

    assert completed.completion is not None
    assert completed.completion.message == "GUI finished: continued with yes"
    assert any(isinstance(command, AnswerQuestion) for command in gui.commands)


@pytest.mark.asyncio
async def test_outer_assistant_question_uses_shell_answer_offer_without_gui():
    gui = FakeGuiPort()
    port = AssistantSessionPort(FakeAssistantRunner(), gui)
    handle = await port.open("assistant-ask", datetime.now(UTC) + timedelta(hours=1))

    await port.command(handle, start(handle.snapshot, "ask"))
    waiting = await wait_for_status(port, handle, RunStatus.WAITING_USER)
    offer = next(item for item in waiting.command_offers if item.kind == "answer_question")
    await port.command(
        handle,
        AnswerQuestion(
            kind="answer_question",
            command_id="answer-outer",
            expected_task_revision=waiting.task_revision,
            expected_run_status=waiting.run_status,
            request_id=offer.request_id,
            answer="Berlin",
        ),
    )
    completed = await wait_for_status(port, handle, RunStatus.DONE)

    assert gui.open_count == 0
    assert completed.completion is not None
    assert completed.completion.message == "Direct answer: Berlin"
    assert any(
        block.kind == "interaction_request"
        for event in handle.events
        for block in event.feed_delta
    )


@pytest.mark.asyncio
async def test_outer_question_rejects_a_stale_request_identity():
    port = AssistantSessionPort(FakeAssistantRunner(), FakeGuiPort())
    handle = await port.open("assistant-stale-question", datetime.now(UTC) + timedelta(hours=1))
    await port.command(handle, start(handle.snapshot, "ask"))
    waiting = await wait_for_status(port, handle, RunStatus.WAITING_USER)

    admission = await port.command(
        handle,
        AnswerQuestion(
            kind="answer_question",
            command_id="stale-answer",
            expected_task_revision=waiting.task_revision,
            expected_run_status=waiting.run_status,
            request_id="not-the-current-question",
            answer="Berlin",
        ),
    )

    assert admission.kind == "conflict"
    assert admission.code == "interaction_ref_mismatch"
    await port.close(handle)


@pytest.mark.asyncio
async def test_recovery_reuses_pydantic_history_checkpoint_without_shell_transcript_rebuild():
    runner = PersistentFakeAssistantRunner()
    port = AssistantSessionPort(runner, FakeGuiPort())
    inspection = await port.inspect("assistant-recover")
    assert inspection.kind == "recoverable_checkpoint"
    assert inspection.checkpoint_id == "assistant-run-1"

    recovered = await port.recover_absent(
        "assistant-recover",
        "assistant-run-1",
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert recovered.attempt.kind == "recovered"
    assert recovered.handle.messages == (("restored", "history"),)

    await port.command(recovered.handle, start(recovered.handle.snapshot, "follow up"))
    await wait_for_status(port, recovered.handle, RunStatus.DONE)
    assert recovered.handle.messages[0] == ("restored", "history")


@pytest.mark.asyncio
async def test_gui_revision_context_is_forwarded_unchanged_to_existing_runtime_owner():
    gui = FakeGuiPort(wait_for_answer=True)
    port = AssistantSessionPort(FakeAssistantRunner(), gui)
    handle = await port.open("assistant-revise", datetime.now(UTC) + timedelta(hours=1))
    await port.command(handle, start(handle.snapshot, "gui:complete the form"))
    waiting = await wait_for_status(port, handle, RunStatus.WAITING_USER)
    context = RevisionConversationContext(
        turns=(
            ConversationTurn(turn_id="original", role="user", text="complete the form"),
            ConversationTurn(turn_id="revision", role="user", text="use the second option"),
        ),
        latest_turn_id="revision",
    )
    admission = await port.command(
        handle,
        ReviseTask(
            kind="revise_task",
            command_id="revision",
            expected_task_revision=waiting.task_revision,
            expected_run_status=waiting.run_status,
            text="use the second option",
        ),
        revision_conversation=context,
    )

    assert admission.kind == "accepted"
    assert gui.revision_contexts[-1] == context
    assert admission.snapshot.run_status is RunStatus.PAUSED
    await port.close(handle)


@pytest.mark.asyncio
async def test_cancel_stops_outer_turn_and_forwards_to_active_gui_runtime():
    gui = FakeGuiPort(wait_for_answer=True)
    port = AssistantSessionPort(FakeAssistantRunner(), gui)
    handle = await port.open("assistant-cancel", datetime.now(UTC) + timedelta(hours=1))
    await port.command(handle, start(handle.snapshot, "gui:complete the form"))
    waiting = await wait_for_status(port, handle, RunStatus.WAITING_USER)

    admission = await port.command(
        handle,
        CancelTask(
            kind="cancel_task",
            command_id="cancel-1",
            expected_task_revision=waiting.task_revision,
            expected_run_status=waiting.run_status,
        ),
    )

    assert admission.kind == "accepted"
    assert admission.snapshot.run_status is RunStatus.CANCELLED
    assert admission.snapshot.completion is not None
    assert admission.snapshot.completion.code == "user_cancelled"
    assert any(isinstance(command, CancelTask) for command in gui.commands)
