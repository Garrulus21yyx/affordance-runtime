"""Pure v3 projection from the public Runtime session boundary into Shell contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from affordance_runtime.app.public_session import (
    LiveCheckpointConflict,
    LiveCheckpointCurrent,
    PublicCommandAccepted,
    PublicCommandConflict,
    PublicCommandRejected,
    PublicCommandUnsupported,
    PublicRevisionConversationContext,
    PublicRevisionConversationTurn,
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionFactory,
    PublicRuntimeSessionHandle,
    PublicRuntimeSessionSnapshot,
    PublicSessionCommand,
    PublicSessionCommandKind,
    PublicSessionOpenError,
    PublicSessionStatus,
    PublicTaskRevisionCommand,
    RecoverableCheckpoint,
    RecoveryInspectionUnavailable as RuntimeInspectionUnavailable,
    RecoveryInspectionUnsupported as RuntimeInspectionUnsupported,
    RuntimeRecovered,
    RuntimeRecoveryConflict as RuntimeAttemptConflict,
    RuntimeRecoveryFailed as RuntimeAttemptFailed,
    RuntimeRecoveryUnavailable as RuntimeAttemptUnavailable,
)

from .contracts import (
    Accepted,
    AnswerQuestion,
    AnswerQuestionOffer,
    ApproveAction,
    CancelTask,
    CancelTaskOffer,
    CloseSession,
    CloseSessionOffer,
    CommandAdmission,
    Completion,
    ConfirmActionOffer,
    Conflict,
    ControlOutcome,
    ControlOwner,
    EffectReconciliation,
    InteractiveSurface,
    PauseTask,
    PauseTaskOffer,
    PublicStep,
    ReadOnlySurface,
    Recovered,
    RecoveryAttempt,
    RecoveryAttemptUnavailable,
    RecoveryConflict,
    RecoveryFailed,
    Rejected,
    RejectAction,
    ResumeTask,
    ResumeTaskOffer,
    ReturnControl,
    ReturnControlOffer,
    ReviseTask,
    ReviseTaskOffer,
    RevisionConversationContext,
    RunStatus,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
    SnapshotUpdated,
    SCHEMA_VERSION,
    StartTask,
    StartTaskOffer,
    SurfaceView,
    TakeOver,
    TakeOverOffer,
    UnavailableSurface,
    Unsupported,
)
from .port import (
    PortRecoverableCheckpoint,
    PortRecoveredHandle,
    PortRecoveryInspection,
    PortRecoveryInspectionFailed,
    PortRecoveryInspectionUnavailable,
    PortRecoveryInspectionUnsupported,
    RuntimeSessionUnavailable,
)
from .viewer import SurfaceAvailability, SurfaceChannelAvailable, SurfaceChannelUnavailable


class SurfaceAvailabilityProjector(Protocol):
    def __call__(self, handle: PublicRuntimeSessionHandle) -> SurfaceAvailability: ...


def unavailable_surface(handle: PublicRuntimeSessionHandle) -> SurfaceAvailability:
    del handle
    return SurfaceChannelUnavailable(reason_code="surface_provider_not_configured")


# Backwards import name for deployment composition while Phase 2 switches atomically.
unavailable_viewer = unavailable_surface


@dataclass(frozen=True)
class CoreRuntimeSessionPort:
    factory: PublicRuntimeSessionFactory
    surface_projector: SurfaceAvailabilityProjector = unavailable_surface

    async def open(self, session_id: str, expires_at: datetime) -> PublicRuntimeSessionHandle:
        try:
            return await self.factory.open(session_id, expires_at)
        except PublicSessionOpenError as exc:
            raise RuntimeSessionUnavailable(exc.code) from exc

    async def inspect(self, session_id: str) -> PortRecoveryInspection:
        inspection = await self.factory.inspect(session_id)
        if isinstance(inspection, RecoverableCheckpoint):
            return PortRecoverableCheckpoint("recoverable_checkpoint", inspection.checkpoint_id)
        if isinstance(inspection, RuntimeInspectionUnavailable):
            return PortRecoveryInspectionUnavailable(
                "recovery_inspection_unavailable",
                inspection.reason_code,
            )
        if isinstance(inspection, RuntimeInspectionUnsupported):
            return PortRecoveryInspectionUnsupported(
                "recovery_inspection_unsupported",
                inspection.reason_code,
            )
        return PortRecoveryInspectionFailed(
            "recovery_inspection_failed",
            inspection.reason_code,
            inspection.retryable,
        )

    async def recover_absent(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> PortRecoveredHandle | RecoveryAttempt:
        attempt = await self.factory.recover_typed(session_id, checkpoint_id, expires_at)
        if isinstance(attempt, RuntimeRecovered):
            snapshot = await self.snapshot(attempt.handle)
            public = Recovered(kind="recovered", snapshot=snapshot)
            return PortRecoveredHandle(attempt.handle, public)
        if isinstance(attempt, RuntimeAttemptConflict):
            return RecoveryConflict(kind="recovery_conflict", reason_code=attempt.reason_code)
        if isinstance(attempt, RuntimeAttemptUnavailable):
            return RecoveryAttemptUnavailable(
                kind="recovery_unavailable", reason_code=attempt.reason_code
            )
        assert isinstance(attempt, RuntimeAttemptFailed)
        return RecoveryFailed(
            kind="recovery_failed", reason_code=attempt.reason_code, retryable=attempt.retryable
        )

    async def recover_live(
        self,
        handle: PublicRuntimeSessionHandle,
        checkpoint_id: str,
    ) -> RecoveryAttempt:
        admission = await handle.inspect_live_checkpoint(checkpoint_id)
        if isinstance(admission, LiveCheckpointCurrent):
            return Recovered(
                kind="recovered",
                snapshot=_snapshot(admission.snapshot, self.surface_projector(handle)),
            )
        if isinstance(admission, LiveCheckpointConflict):
            return RecoveryConflict(kind="recovery_conflict", reason_code=admission.reason_code)
        return RecoveryAttemptUnavailable(
            kind="recovery_unavailable", reason_code="checkpoint_unavailable"
        )

    async def snapshot(self, handle: PublicRuntimeSessionHandle) -> RuntimeSessionSnapshot:
        return _snapshot(await handle.snapshot(), self.surface_projector(handle))

    async def events(
        self,
        handle: PublicRuntimeSessionHandle,
        after: int,
    ) -> tuple[ShellEvent, ...]:
        availability = self.surface_projector(handle)
        return tuple(_event(event, availability) for event in await handle.events(after))

    async def forward_viewer_input(
        self,
        handle: PublicRuntimeSessionHandle,
        control_lease_id: str,
        forward: Callable[[], Awaitable[None]],
    ) -> bool:
        if not await handle.admits_surface_input(control_lease_id):
            return False
        if not _native_input_available(self.surface_projector(handle)):
            return False
        await forward()
        return True

    async def command(
        self,
        handle: PublicRuntimeSessionHandle,
        command: ShellCommand,
        *,
        revision_conversation: RevisionConversationContext | None = None,
    ) -> CommandAdmission:
        availability: SurfaceAvailability | None = None
        if isinstance(command, TakeOver):
            availability = self.surface_projector(handle)
            if not _native_input_available(availability):
                source = await handle.snapshot()
                return Unsupported(
                    kind="unsupported",
                    command_id=command.command_id,
                    code="deployment_capability_unavailable",
                    snapshot=_snapshot(source, availability),
                )
        runtime_command = _runtime_command(command, revision_conversation)
        admission = await handle.admit(runtime_command)
        projection_availability = availability or self.surface_projector(handle)
        return _admission(admission, projection_availability)

    async def close(self, handle: PublicRuntimeSessionHandle) -> None:
        await handle.close()


def _runtime_command(
    command: ShellCommand,
    revision_conversation: RevisionConversationContext | None,
) -> PublicSessionCommand:
    common = {
        "command_id": command.command_id,
        "kind": PublicSessionCommandKind(command.kind),
        "expected_task_revision": command.expected_task_revision,
        "expected_run_status": PublicSessionStatus(command.expected_run_status.value),
    }
    if isinstance(command, StartTask):
        return PublicSessionCommand(**common, task=command.task)
    if isinstance(command, AnswerQuestion):
        return PublicSessionCommand(
            **common,
            interaction_ref=command.request_id,
            answer=command.answer,
        )
    if isinstance(command, (ApproveAction, RejectAction)):
        return PublicSessionCommand(**common, interaction_ref=command.request_id)
    if isinstance(command, (ResumeTask, TakeOver)):
        return PublicSessionCommand(**common, checkpoint_id=command.checkpoint_id)
    if isinstance(command, ReturnControl):
        return PublicSessionCommand(**common, control_lease_id=command.control_lease_id)
    if isinstance(command, ReviseTask):
        if revision_conversation is None:
            raise TypeError("Shell manager must attach bounded revision conversation")
        revision = PublicTaskRevisionCommand(
            command_id=command.command_id,
            expected_task_revision=command.expected_task_revision,
            expected_run_status=PublicSessionStatus(command.expected_run_status.value),
            expected_checkpoint_id=command.expected_checkpoint_id,
            text=command.text,
            conversation=PublicRevisionConversationContext(
                turns=tuple(
                    PublicRevisionConversationTurn(turn.turn_id, turn.role, turn.text)
                    for turn in revision_conversation.turns
                ),
                latest_turn_id=revision_conversation.latest_turn_id,
            ),
        )
        return PublicSessionCommand(**common, revision=revision)
    assert isinstance(command, CancelTask | PauseTask | CloseSession)
    return PublicSessionCommand(**common)


def _admission(
    source: PublicCommandAccepted
    | PublicCommandConflict
    | PublicCommandUnsupported
    | PublicCommandRejected,
    availability: SurfaceAvailability,
) -> CommandAdmission:
    snapshot = _snapshot(source.snapshot, availability)
    if isinstance(source, PublicCommandAccepted):
        return Accepted(kind="accepted", command_id=source.command_id, snapshot=snapshot)
    if isinstance(source, PublicCommandConflict):
        return Conflict(
            kind="conflict", command_id=source.command_id, code=source.code, snapshot=snapshot
        )
    if isinstance(source, PublicCommandUnsupported):
        return Unsupported(
            kind="unsupported", command_id=source.command_id, code=source.code, snapshot=snapshot
        )
    return Rejected(
        kind="rejected", command_id=source.command_id, code=source.code, snapshot=snapshot
    )


def _snapshot(
    source: PublicRuntimeSessionSnapshot,
    availability: SurfaceAvailability,
) -> RuntimeSessionSnapshot:
    control_owner = ControlOwner(source.control_owner.value)
    surface = _surface_view(availability, control_owner, source.control_lease_id)
    return RuntimeSessionSnapshot(
        schema_version=SCHEMA_VERSION,
        session_id=source.session_id,
        task_id=source.task_id,
        task_revision=source.task_revision,
        task_text=source.task_text,
        run_status=RunStatus(source.status.value),
        event_epoch=source.event_epoch,
        event_cursor=source.event_cursor,
        completion=(
            Completion(
                outcome=source.completion.outcome,
                code=source.completion.code,
                message=source.completion.message,
                evidence_refs=source.completion.evidence_refs,
            )
            if source.completion is not None
            else None
        ),
        command_offers=_command_offers(source, availability),
        surface=surface,
        public_steps=tuple(
            PublicStep(step=step.step, stage="runtime", status=step.status, label=step.label)
            for step in source.progress
        ),
        checkpoint_id=source.checkpoint_id,
        resume_eligible=source.resume_eligible,
        last_control_outcome=(
            ControlOutcome(
                command_id=source.last_control_outcome.command_id,
                kind=source.last_control_outcome.kind,
                outcome=source.last_control_outcome.outcome,
                code=source.last_control_outcome.code,
                checkpoint_id=source.last_control_outcome.checkpoint_id,
                message=source.last_control_outcome.message,
            )
            if source.last_control_outcome is not None
            else None
        ),
        effect_reconciliation=(
            EffectReconciliation(
                status=source.effect_reconciliation.status,
                code=source.effect_reconciliation.code,
                original_effect_ref=source.effect_reconciliation.original_effect_ref,
                original_action=source.effect_reconciliation.original_action,
                resource_ref=source.effect_reconciliation.resource_ref,
                reversibility=source.effect_reconciliation.reversibility,
                compensation_effect_ref=source.effect_reconciliation.compensation_effect_ref,
            )
            if source.effect_reconciliation is not None
            else None
        ),
        control_owner=control_owner,
        control_lease_id=source.control_lease_id,
        expires_at=source.expires_at,
    )


def _command_offers(
    source: PublicRuntimeSessionSnapshot,
    availability: SurfaceAvailability,
):
    offers = []
    confirmation_added = False
    for capability in source.command_capabilities:
        kind = capability.kind
        if kind is PublicSessionCommandKind.TAKE_OVER and not _native_input_available(availability):
            continue
        if kind is PublicSessionCommandKind.START_TASK:
            offers.append(StartTaskOffer(kind="start_task"))
        elif kind is PublicSessionCommandKind.ANSWER_QUESTION:
            offers.append(
                AnswerQuestionOffer(
                    kind="answer_question",
                    request_id=cast(str, capability.interaction_ref),
                    prompt=capability.prompt,
                )
            )
        elif kind in {
            PublicSessionCommandKind.APPROVE_ACTION,
            PublicSessionCommandKind.REJECT_ACTION,
        }:
            if not confirmation_added:
                offers.append(
                    ConfirmActionOffer(
                        kind="confirm_action",
                        request_id=cast(str, capability.interaction_ref),
                        summary=capability.summary,
                        risk=capability.risk,
                    )
                )
                confirmation_added = True
        elif kind is PublicSessionCommandKind.CANCEL_TASK:
            offers.append(CancelTaskOffer(kind="cancel_task"))
        elif kind is PublicSessionCommandKind.PAUSE_TASK:
            offers.append(PauseTaskOffer(kind="pause_task"))
        elif kind is PublicSessionCommandKind.RESUME_TASK:
            offers.append(ResumeTaskOffer(kind="resume_task"))
        elif kind is PublicSessionCommandKind.REVISE_TASK:
            offers.append(ReviseTaskOffer(kind="revise_task"))
        elif kind is PublicSessionCommandKind.TAKE_OVER:
            offers.append(TakeOverOffer(kind="take_over"))
        elif kind is PublicSessionCommandKind.RETURN_CONTROL:
            offers.append(ReturnControlOffer(kind="return_control"))
        elif kind is PublicSessionCommandKind.CLOSE_SESSION:
            offers.append(CloseSessionOffer(kind="close_session"))
    return tuple(offers)


def _surface_view(
    availability: SurfaceAvailability,
    control_owner: ControlOwner,
    control_lease_id: str | None,
) -> SurfaceView:
    if isinstance(availability, SurfaceChannelUnavailable):
        return UnavailableSurface(status="unavailable", reason_code=availability.reason_code)
    if (
        control_owner is ControlOwner.USER
        and control_lease_id is not None
        and availability.input_mode == "native"
        and availability.presentation == "live_media"
    ):
        return InteractiveSurface(
            status="interactive",
            surface_kind=availability.surface_kind,
            presentation="live_media",
            protected_path=availability.protected_path,
            input_mode="native",
        )
    return ReadOnlySurface(
        status="read_only",
        surface_kind=availability.surface_kind,
        presentation=availability.presentation,
        protected_path=availability.protected_path,
    )


def _native_input_available(availability: SurfaceAvailability) -> bool:
    return (
        isinstance(availability, SurfaceChannelAvailable)
        and availability.input_mode == "native"
        and availability.presentation == "live_media"
    )


def _event(source: PublicRuntimeSessionEvent, availability: SurfaceAvailability) -> ShellEvent:
    return SnapshotUpdated(
        schema_version=SCHEMA_VERSION,
        type="snapshot.updated",
        session_id=source.session_id,
        event_epoch=source.event_epoch,
        cursor=source.cursor,
        emitted_at=source.emitted_at,
        snapshot=_snapshot(source.snapshot, availability),
    )
