from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from interaction_shell.contracts import (
    AnswerQuestion,
    ApproveAction,
    CancelTask,
    CloseSession,
    ConversationTurn,
    PauseTask,
    RejectAction,
    RespondInteraction,
    ResumeTask,
    ReturnControl,
    ReviseTask,
    RevisionConversationContext,
    RunStatus,
    SingleSelectInteractionResponse,
    StartTask,
    TakeOver,
)
from interaction_shell.core_runtime_port import CoreRuntimeSessionPort
from interaction_shell.port import PortRecoveredHandle
from interaction_shell.viewer import SurfaceChannelAvailable, SurfaceChannelUnavailable

from affordance_runtime.agent.interactions import (
    InteractionOption as RuntimeInteractionOption,
)
from affordance_runtime.agent.interactions import (
    SingleSelectionResponse as RuntimeSingleSelectionResponse,
)
from affordance_runtime.app.public_session import (
    LiveCheckpointConflict,
    LiveCheckpointCurrent,
    LiveCheckpointUnavailable,
    PublicCommandAccepted,
    PublicCommandConflict,
    PublicCommandRejected,
    PublicCommandUnsupported,
    PublicConflictCode,
    PublicInteractionRequest,
    PublicRejectedCode,
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionSnapshot,
    PublicSessionCommandCapability,
    PublicSessionCommandKind,
    PublicSessionControlOwner,
    PublicSessionStatus,
    PublicUserTurn,
    RecoverableCheckpoint,
    RecoveryInspectionUnavailable,
    RuntimeRecovered,
    RuntimeRecoveryConflict,
    RuntimeRecoveryFailed,
    RuntimeRecoveryUnavailable,
)

CHECKPOINT_ID = "runtime-checkpoint:" + "a" * 64

COMMANDS = (
    StartTask(
        kind="start_task",
        command_id="start",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        task="Task",
    ),
    AnswerQuestion(
        kind="answer_question",
        command_id="answer",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        request_id="question-1",
        answer="Answer",
    ),
    RespondInteraction(
        kind="respond_interaction",
        command_id="respond",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        request_id="interaction-1",
        response=SingleSelectInteractionResponse(
            kind="single_select",
            request_id="interaction-1",
            option_id="option-1",
        ),
    ),
    ApproveAction(
        kind="approve_action",
        command_id="approve",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        request_id="confirmation-1",
    ),
    RejectAction(
        kind="reject_action",
        command_id="reject",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        request_id="confirmation-1",
    ),
    CancelTask(kind="cancel_task", command_id="cancel", expected_task_revision=2, expected_run_status=RunStatus.PAUSED),
    PauseTask(kind="pause_task", command_id="pause", expected_task_revision=2, expected_run_status=RunStatus.PAUSED),
    ResumeTask(
        kind="resume_task",
        command_id="resume",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        checkpoint_id=CHECKPOINT_ID,
    ),
    ReviseTask(
        kind="revise_task",
        command_id="revise",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        expected_checkpoint_id=CHECKPOINT_ID,
        text="Revised task",
    ),
    TakeOver(
        kind="take_over",
        command_id="takeover",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        checkpoint_id=CHECKPOINT_ID,
    ),
    ReturnControl(
        kind="return_control",
        command_id="return",
        expected_task_revision=2,
        expected_run_status=RunStatus.PAUSED,
        control_lease_id="lease:" + "u" * 32,
    ),
    CloseSession(
        kind="close_session", command_id="close", expected_task_revision=2, expected_run_status=RunStatus.PAUSED
    ),
)

ADMISSION_CASES = st.one_of(
    st.just(("accepted", None)),
    st.sampled_from(tuple(("conflict", code) for code in get_args(PublicConflictCode))),
    st.just(("unsupported", "command_not_supported")),
    st.sampled_from(tuple(("rejected", code) for code in get_args(PublicRejectedCode))),
)


def runtime_snapshot(
    *,
    status: PublicSessionStatus = PublicSessionStatus.PAUSED,
    capabilities: tuple[PublicSessionCommandCapability, ...] = (),
    owner: PublicSessionControlOwner = PublicSessionControlOwner.AGENT,
    lease: str | None = None,
    pending_interaction: PublicInteractionRequest | None = None,
    event_cursor: int = 0,
    checkpoint_id: str | None = CHECKPOINT_ID,
) -> PublicRuntimeSessionSnapshot:
    return PublicRuntimeSessionSnapshot(
        session_id="session-1",
        expires_at=datetime.now(UTC),
        status=status,
        event_epoch="runtime-epoch-000001",
        event_cursor=event_cursor,
        command_capabilities=capabilities,
        task_revision=2,
        checkpoint_id=checkpoint_id,
        resume_eligible=checkpoint_id is not None,
        pending_interaction=pending_interaction,
        control_owner=owner,
        control_lease_id=lease,
    )


class FakeHandle:
    def __init__(
        self,
        snapshot: PublicRuntimeSessionSnapshot,
        admission=None,
        live=None,
        surface_input_admitted=False,
        events=(),
    ):
        self.current = snapshot
        self.admission = admission
        self.live = live
        self.admit_calls = 0
        self.surface_input_admitted = surface_input_admitted
        self.surface_input_calls = 0
        self.last_command = None
        self.source_events = tuple(events)

    async def snapshot(self):
        return self.current

    async def admit(self, command):
        self.admit_calls += 1
        self.last_command = command
        return self.admission or PublicCommandAccepted("accepted", command.command_id, self.current)

    async def events(self, after):
        return tuple(event for event in self.source_events if event.cursor > after)

    async def inspect_live_checkpoint(self, checkpoint_id):
        del checkpoint_id
        return self.live

    async def admits_surface_input(self, control_lease_id):
        del control_lease_id
        self.surface_input_calls += 1
        return self.surface_input_admitted

    async def close(self):
        return None


class FakeFactory:
    inspection = RecoveryInspectionUnavailable("recovery_inspection_unavailable", "checkpoint_not_found")
    recovery = RuntimeRecoveryUnavailable("recovery_unavailable", "checkpoint_not_found")

    async def open(self, session_id, expires_at):
        del session_id, expires_at
        raise AssertionError

    async def inspect(self, session_id):
        del session_id
        return self.inspection

    async def recover_typed(self, session_id, checkpoint_id, expires_at):
        del session_id, checkpoint_id, expires_at
        return self.recovery


def native_surface(_handle):
    return SurfaceChannelAvailable(
        surface_kind="web", presentation="live_media", protected_path="/viewer/session-1", input_mode="native"
    )


def unavailable_surface(_handle):
    return SurfaceChannelUnavailable(reason_code="native_input_unavailable")


@pytest.mark.asyncio
async def test_command_offer_projection_is_sound_complete_unique_and_ref_preserving():
    capabilities = (
        PublicSessionCommandCapability(
            PublicSessionCommandKind.ANSWER_QUESTION, interaction_ref="question-1", prompt="Question?"
        ),
        PublicSessionCommandCapability(
            PublicSessionCommandKind.APPROVE_ACTION, interaction_ref="confirmation-1", summary="Confirm", risk="medium"
        ),
        PublicSessionCommandCapability(
            PublicSessionCommandKind.REJECT_ACTION, interaction_ref="confirmation-1", summary="Confirm", risk="medium"
        ),
        PublicSessionCommandCapability(PublicSessionCommandKind.RESUME_TASK),
        PublicSessionCommandCapability(PublicSessionCommandKind.TAKE_OVER),
        PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION),
    )
    port = CoreRuntimeSessionPort(FakeFactory(), native_surface)
    projected = await port.snapshot(FakeHandle(runtime_snapshot(capabilities=capabilities)))
    kinds = [offer.kind for offer in projected.command_offers]
    assert kinds == ["answer_question", "confirm_action", "resume_task", "take_over", "close_session"]
    assert len(kinds) == len(set(kinds))
    assert projected.command_offers[0].request_id == "question-1"
    assert projected.command_offers[1].request_id == "confirmation-1"


@pytest.mark.asyncio
async def test_generic_interaction_offer_and_response_preserve_typed_ids() -> None:
    request = PublicInteractionRequest(
        "interaction:" + "a" * 32,
        "Choose a candidate",
        "single_select",
        options=(
            RuntimeInteractionOption(
                "option:" + "b" * 32,
                "Candidate A",
            ),
        ),
    )
    source = runtime_snapshot(
        status=PublicSessionStatus.WAITING_USER,
        capabilities=(
            PublicSessionCommandCapability(
                PublicSessionCommandKind.RESPOND_INTERACTION,
                interaction_ref=request.request_id,
                prompt=request.prompt,
            ),
        ),
        pending_interaction=request,
    )
    handle = FakeHandle(source)
    port = CoreRuntimeSessionPort(FakeFactory(), unavailable_surface)

    projected = await port.snapshot(handle)
    offer = projected.command_offers[0]
    assert offer.kind == "respond_interaction"
    assert offer.request.options[0].title == "Candidate A"

    admission = await port.command(
        handle,
        RespondInteraction(
            kind="respond_interaction",
            command_id="respond-typed",
            expected_task_revision=source.task_revision,
            expected_run_status=RunStatus.WAITING_USER,
            request_id=request.request_id,
            response=SingleSelectInteractionResponse(
                kind="single_select",
                request_id=request.request_id,
                option_id=request.options[0].option_id,
            ),
        ),
    )

    assert admission.kind == "accepted"
    assert isinstance(handle.last_command.response, RuntimeSingleSelectionResponse)
    assert handle.last_command.response.option_id == request.options[0].option_id


@pytest.mark.asyncio
async def test_runtime_feed_source_projects_to_closed_shell_block_without_guessing() -> None:
    snapshot = runtime_snapshot(event_cursor=1)
    event = PublicRuntimeSessionEvent(
        snapshot.session_id,
        snapshot.event_epoch,
        1,
        "RUN_STARTED",
        snapshot,
        (
            PublicUserTurn(
                f"feed:{snapshot.event_epoch}:1:0",
                "Compare the visible candidates",
            ),
        ),
    )
    port = CoreRuntimeSessionPort(FakeFactory(), unavailable_surface)

    projected = await port.events(FakeHandle(snapshot, events=(event,)), 0)

    assert len(projected) == 1
    assert projected[0].feed_delta[0].kind == "user_turn"
    assert projected[0].feed_delta[0].content == "Compare the visible candidates"
    assert projected[0].feed_delta[0].block_id == event.feed_sources[0].source_id


@pytest.mark.asyncio
async def test_takeover_fresh_deployment_race_returns_unsupported_without_runtime_call():
    source = runtime_snapshot(capabilities=(PublicSessionCommandCapability(PublicSessionCommandKind.TAKE_OVER),))
    handle = FakeHandle(source)
    port = CoreRuntimeSessionPort(FakeFactory(), unavailable_surface)
    admission = await port.command(
        handle,
        TakeOver(
            kind="take_over",
            command_id="takeover-1",
            expected_task_revision=2,
            expected_run_status=RunStatus.PAUSED,
            checkpoint_id=source.checkpoint_id or "",
        ),
    )
    assert admission.kind == "unsupported"
    assert admission.code == "deployment_capability_unavailable"
    assert handle.admit_calls == 0


@pytest.mark.asyncio
async def test_waiting_user_takeover_reaches_runtime_without_a_preexisting_checkpoint():
    source = runtime_snapshot(
        status=PublicSessionStatus.WAITING_USER,
        capabilities=(PublicSessionCommandCapability(PublicSessionCommandKind.TAKE_OVER),),
        checkpoint_id=None,
    )
    handle = FakeHandle(source)
    port = CoreRuntimeSessionPort(FakeFactory(), native_surface)

    admission = await port.command(
        handle,
        TakeOver(
            kind="take_over",
            command_id="takeover-direct",
            expected_task_revision=source.task_revision,
            expected_run_status=RunStatus.WAITING_USER,
        ),
    )

    assert admission.kind == "accepted"
    assert handle.admit_calls == 1
    assert handle.last_command.kind is PublicSessionCommandKind.TAKE_OVER
    assert handle.last_command.checkpoint_id == ""


@pytest.mark.asyncio
async def test_return_control_reaches_runtime_when_surface_is_unavailable():
    lease = "user-control-lease:" + "u" * 32
    source = runtime_snapshot(
        capabilities=(PublicSessionCommandCapability(PublicSessionCommandKind.RETURN_CONTROL),),
        owner=PublicSessionControlOwner.USER,
        lease=lease,
    )
    handle = FakeHandle(source)
    port = CoreRuntimeSessionPort(FakeFactory(), unavailable_surface)
    admission = await port.command(
        handle,
        ReturnControl(
            kind="return_control",
            command_id="return-1",
            expected_task_revision=2,
            expected_run_status=RunStatus.PAUSED,
            control_lease_id=lease,
        ),
    )
    assert admission.kind == "accepted"
    assert handle.admit_calls == 1
    assert admission.snapshot.surface.status == "unavailable"


@pytest.mark.asyncio
async def test_viewer_input_requires_runtime_lease_admission_and_fresh_native_surface():
    forwarded = 0

    async def forward():
        nonlocal forwarded
        forwarded += 1

    admitted = FakeHandle(runtime_snapshot(), surface_input_admitted=True)
    port = CoreRuntimeSessionPort(FakeFactory(), native_surface)
    assert await port.forward_viewer_input(admitted, "opaque-lease", forward)
    assert admitted.surface_input_calls == 1
    assert forwarded == 1

    withdrawn = FakeHandle(runtime_snapshot(), surface_input_admitted=True)
    port = CoreRuntimeSessionPort(FakeFactory(), unavailable_surface)
    assert not await port.forward_viewer_input(withdrawn, "opaque-lease", forward)
    assert withdrawn.surface_input_calls == 1
    assert forwarded == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime_admission,expected_kind,expected_code",
    [
        (PublicCommandAccepted("accepted", "command-1", runtime_snapshot()), "accepted", None),
        (
            PublicCommandConflict("conflict", "command-1", "stale_command", runtime_snapshot()),
            "conflict",
            "stale_command",
        ),
        (
            PublicCommandUnsupported("unsupported", "command-1", "command_not_supported", runtime_snapshot()),
            "unsupported",
            "command_not_supported",
        ),
        (
            PublicCommandRejected("rejected", "command-1", "command_processing_failed", runtime_snapshot()),
            "rejected",
            "command_processing_failed",
        ),
    ],
)
async def test_all_runtime_outcome_variants_project_exhaustively(runtime_admission, expected_kind, expected_code):
    handle = FakeHandle(runtime_snapshot(), admission=runtime_admission)
    port = CoreRuntimeSessionPort(FakeFactory(), unavailable_surface)
    result = await port.command(
        handle,
        CloseSession(
            kind="close_session", command_id="command-1", expected_task_revision=2, expected_run_status=RunStatus.PAUSED
        ),
    )
    assert result.kind == expected_kind
    assert getattr(result, "code", None) == expected_code


@pytest.mark.asyncio
@pytest.mark.parametrize("command", COMMANDS, ids=lambda command: command.kind)
@given(admission_case=ADMISSION_CASES)
async def test_every_command_projects_every_closed_runtime_admission_without_reclassification(
    command,
    admission_case,
):
    kind, code = admission_case
    source = runtime_snapshot()
    if kind == "accepted":
        runtime_admission = PublicCommandAccepted("accepted", command.command_id, source)
    elif kind == "conflict":
        runtime_admission = PublicCommandConflict("conflict", command.command_id, code, source)
    elif kind == "unsupported":
        runtime_admission = PublicCommandUnsupported("unsupported", command.command_id, code, source)
    else:
        runtime_admission = PublicCommandRejected("rejected", command.command_id, code, source)
    revision_conversation = (
        RevisionConversationContext(
            turns=(ConversationTurn(turn_id="revision-1", role="user", text="Revised task"),),
            latest_turn_id="revision-1",
        )
        if command.kind == "revise_task"
        else None
    )
    result = await CoreRuntimeSessionPort(FakeFactory(), native_surface).command(
        FakeHandle(source, admission=runtime_admission),
        command,
        revision_conversation=revision_conversation,
    )
    assert result.kind == kind
    assert getattr(result, "code", None) == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "live,expected_kind,expected_reason",
    [
        (LiveCheckpointCurrent("live_checkpoint_current", runtime_snapshot()), "recovered", None),
        (
            LiveCheckpointConflict("live_checkpoint_conflict", "checkpoint_mismatch"),
            "recovery_conflict",
            "checkpoint_mismatch",
        ),
        (
            LiveCheckpointUnavailable("live_checkpoint_unavailable", "checkpoint_unavailable"),
            "recovery_unavailable",
            "checkpoint_unavailable",
        ),
    ],
)
async def test_live_recovery_algebra_is_fully_typed(live, expected_kind, expected_reason):
    result = await CoreRuntimeSessionPort(FakeFactory(), unavailable_surface).recover_live(
        FakeHandle(runtime_snapshot(), live=live), "checkpoint"
    )
    assert result.kind == expected_kind
    assert getattr(result, "reason_code", None) == expected_reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt,expected_type,expected_kind",
    [
        (RuntimeRecovered("recovered", FakeHandle(runtime_snapshot())), PortRecoveredHandle, None),
        (RuntimeRecoveryConflict("recovery_conflict", "checkpoint_mismatch"), object, "recovery_conflict"),
        (RuntimeRecoveryUnavailable("recovery_unavailable", "checkpoint_not_found"), object, "recovery_unavailable"),
        (RuntimeRecoveryFailed("recovery_failed", "checkpoint_store_failed"), object, "recovery_failed"),
    ],
)
async def test_absent_recovery_algebra_is_fully_typed(attempt, expected_type, expected_kind):
    factory = FakeFactory()
    factory.recovery = attempt
    result = await CoreRuntimeSessionPort(factory, unavailable_surface).recover_absent(
        "session-1", "checkpoint", datetime.now(UTC)
    )
    assert isinstance(result, expected_type)
    if expected_kind is not None:
        assert result.kind == expected_kind


@pytest.mark.asyncio
async def test_inspector_conversion_has_no_manager_checkpoint_logic():
    factory = FakeFactory()
    factory.inspection = RecoverableCheckpoint("recoverable_checkpoint", "checkpoint-1")
    result = await CoreRuntimeSessionPort(factory, unavailable_surface).inspect("session-1")
    assert result.kind == "recoverable_checkpoint"
    assert result.checkpoint_id == "checkpoint-1"
