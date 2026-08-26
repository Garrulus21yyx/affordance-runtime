"""Projection from the versioned public Runtime session port into Shell contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from affordance_runtime.app.public_session import (
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionFactory,
    PublicRuntimeSessionHandle,
    PublicRuntimeSessionSnapshot,
    PublicSessionCapability,
    PublicSessionConflict,
    PublicSessionOpenError,
)

from .contracts import (
    Accepted,
    AnswerQuestion,
    ApproveAction,
    Capability,
    Completion,
    Conflict,
    PendingConfirmation,
    PendingQuestion,
    OptionalCommand,
    PublicStep,
    RejectAction,
    RunStatus,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
    StartTask,
    ViewerState,
)
from .port import RuntimeSessionUnavailable


class ViewerStateProjector(Protocol):
    """Deployment-owned projection to a protected Steel/Browserbase route."""

    def __call__(self, handle: PublicRuntimeSessionHandle) -> ViewerState: ...


def unavailable_viewer(handle: PublicRuntimeSessionHandle) -> ViewerState:
    del handle
    return ViewerState(reason_code="viewer_provider_not_configured")


@dataclass(frozen=True)
class CoreRuntimeSessionPort:
    """Use only Core-owned public values; no Runtime state is retained here."""

    factory: PublicRuntimeSessionFactory
    viewer_projector: ViewerStateProjector = unavailable_viewer

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(
            {
                Capability.START_TASK,
                Capability.ANSWER_QUESTION,
                Capability.APPROVE_ACTION,
                Capability.REJECT_ACTION,
                Capability.CANCEL_TASK,
                Capability.CLOSE_SESSION,
            }
        )

    async def open(self, session_id: str, expires_at: datetime) -> PublicRuntimeSessionHandle:
        try:
            return await self.factory.open(session_id, expires_at)
        except PublicSessionOpenError as exc:
            raise RuntimeSessionUnavailable(exc.code) from exc

    async def snapshot(self, handle: PublicRuntimeSessionHandle) -> RuntimeSessionSnapshot:
        return _snapshot(await handle.snapshot(), self.viewer_projector(handle))

    async def events(
        self, handle: PublicRuntimeSessionHandle, after: int
    ) -> tuple[ShellEvent, ...]:
        viewer = self.viewer_projector(handle)
        return tuple(_event(event, viewer) for event in await handle.events(after))

    async def command(self, handle: PublicRuntimeSessionHandle, command: ShellCommand):
        before = (await handle.snapshot()).event_cursor
        try:
            if isinstance(command, StartTask):
                current = await handle.start(command.task)
            elif isinstance(command, AnswerQuestion):
                current = await handle.answer(command.request_id, command.answer)
            elif isinstance(command, ApproveAction):
                current = await handle.confirm(command.request_id, approved=True)
            elif isinstance(command, RejectAction):
                current = await handle.confirm(command.request_id, approved=False)
            elif isinstance(command, OptionalCommand) and command.kind == "cancel_task":
                current = await handle.cancel(command.command_id)
            else:
                raise TypeError("Core Runtime port received an unsupported command")
        except PublicSessionConflict as exc:
            return (
                Conflict(
                    command_id=command.command_id,
                    code="runtime_conflict",
                    snapshot=_snapshot(exc.snapshot, self.viewer_projector(handle)),
                ),
                (),
            )
        viewer = self.viewer_projector(handle)
        events = tuple(_event(event, viewer) for event in await handle.events(before))
        return Accepted(command_id=command.command_id, snapshot=_snapshot(current, viewer)), events

    async def close(self, handle: PublicRuntimeSessionHandle) -> None:
        await handle.close()


def _snapshot(source: PublicRuntimeSessionSnapshot, viewer: ViewerState) -> RuntimeSessionSnapshot:
    capabilities = frozenset(
        Capability(capability.value)
        for capability in source.capabilities
        if capability in _SUPPORTED_PUBLIC_CAPABILITIES
    )
    pending_question = (
        PendingQuestion(
            request_id=source.pending_question.interrupt_id, prompt=source.pending_question.prompt
        )
        if source.pending_question is not None
        else None
    )
    pending_confirmation = (
        PendingConfirmation(
            request_id=source.pending_confirmation.interrupt_id,
            summary=source.pending_confirmation.summary,
            risk=source.pending_confirmation.risk,
        )
        if source.pending_confirmation is not None
        else None
    )
    completion = (
        Completion(
            outcome=source.completion.outcome,
            code=source.completion.code,
            message=source.completion.message,
            evidence_refs=source.completion.evidence_refs,
        )
        if source.completion is not None
        else None
    )
    return RuntimeSessionSnapshot(
        session_id=source.session_id,
        task_id=source.task_id,
        task_revision=source.task_revision,
        task_text=source.task_text,
        run_status=RunStatus(source.status.value),
        event_epoch=source.event_epoch,
        event_cursor=source.event_cursor,
        pending_question=pending_question,
        pending_confirmation=pending_confirmation,
        completion=completion,
        capabilities=capabilities,
        viewer=viewer,
        public_steps=tuple(
            PublicStep(
                step=step.step,
                stage="runtime",
                status=step.status,
                label=step.label,
            )
            for step in source.progress
        ),
        expires_at=source.expires_at,
    )


def _event(source: PublicRuntimeSessionEvent, viewer: ViewerState) -> ShellEvent:
    snapshot = _snapshot(source.snapshot, viewer)
    return ShellEvent(
        session_id=source.session_id,
        event_epoch=source.event_epoch,
        cursor=source.cursor,
        type=source.type,
        emitted_at=source.emitted_at,
        data={"snapshot": snapshot.model_dump(mode="json")},
    )


_SUPPORTED_PUBLIC_CAPABILITIES = frozenset(
    {
        PublicSessionCapability.START_TASK,
        PublicSessionCapability.ANSWER_QUESTION,
        PublicSessionCapability.APPROVE_ACTION,
        PublicSessionCapability.REJECT_ACTION,
        PublicSessionCapability.CANCEL_TASK,
        PublicSessionCapability.CLOSE_SESSION,
    }
)
