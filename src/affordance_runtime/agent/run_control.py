"""Runtime-owned cooperative control requests and closed boundary outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.execution.contracts import DispatchStatus


class RunControlKind(StrEnum):
    PAUSE = "pause"
    CANCEL = "cancel"


class RunControlBoundary(StrEnum):
    BEFORE_POLICY = "before_policy"
    AFTER_POLICY = "after_policy"
    BEFORE_DISPATCH = "before_dispatch"
    AFTER_DISPATCH = "after_dispatch"
    AFTER_CAPTURE = "after_capture"
    AFTER_EVALUATION = "after_evaluation"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"


class RunControlOutcomeKind(StrEnum):
    PAUSE_BOUNDARY_REACHED = "pause_boundary_reached"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    RUN_ALREADY_TERMINAL = "run_already_terminal"
    BOUNDARY_FAILED = "boundary_failed"
    RESUMED = "resumed"


class RunControlAdmissionKind(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class RunControlRequest:
    command_id: str
    kind: RunControlKind

    def __post_init__(self) -> None:
        if not self.command_id.strip() or len(self.command_id) > 128:
            raise ValueError("run control command identity is invalid")
        if not isinstance(self.kind, RunControlKind):
            raise TypeError("run control request kind must be typed")


@dataclass(frozen=True)
class RunControlAdmission:
    command_id: str
    kind: RunControlKind
    outcome: RunControlAdmissionKind


@dataclass(frozen=True)
class RunControlOutcome:
    command_id: str
    kind: RunControlKind
    outcome: RunControlOutcomeKind
    boundary: RunControlBoundary | None = None
    dispatch_status: DispatchStatus | None = None
    failure_code: str = ""

    def __post_init__(self) -> None:
        if not self.command_id.strip() or len(self.command_id) > 128:
            raise ValueError("run control outcome command identity is invalid")
        if not isinstance(self.kind, RunControlKind):
            raise TypeError("run control outcome kind must be typed")
        if not isinstance(self.outcome, RunControlOutcomeKind):
            raise TypeError("run control outcome must be typed")
        reached = self.outcome in {
            RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED,
            RunControlOutcomeKind.CANCELLED,
        }
        if reached != (self.boundary is not None):
            raise ValueError("a reached control outcome requires exactly one boundary")
        if self.boundary is not None and not isinstance(self.boundary, RunControlBoundary):
            raise TypeError("run control boundary must be typed")
        if self.dispatch_status is not None and not isinstance(
            self.dispatch_status, DispatchStatus
        ):
            raise TypeError("run control dispatch status must be typed")
        failed = self.outcome is RunControlOutcomeKind.BOUNDARY_FAILED
        if failed != bool(self.failure_code.strip()):
            raise ValueError("failed control outcome requires exactly one failure code")


@dataclass
class CooperativeRunControl:
    """One in-memory control owner for one Runtime session.

    This is deliberately not a checkpoint or a second run state.  It owns only
    the command request until Core commits one boundary into ``RunState``.
    """

    _pending: RunControlRequest | None = field(default=None, init=False, repr=False)
    _paused: RunControlOutcome | None = field(default=None, init=False, repr=False)
    _outcomes: dict[str, RunControlOutcome] = field(default_factory=dict, init=False, repr=False)
    _outcome_order: list[str] = field(default_factory=list, init=False, repr=False)
    _max_outcomes: int = field(default=128, repr=False)

    def __post_init__(self) -> None:
        if self._max_outcomes < 1:
            raise ValueError("run control outcome history must be bounded")

    @property
    def pending(self) -> RunControlRequest | None:
        return self._pending

    @property
    def paused(self) -> RunControlOutcome | None:
        return self._paused

    def outcome(self, command_id: str) -> RunControlOutcome | None:
        return self._outcomes.get(command_id)

    def request(self, command_id: str, kind: RunControlKind) -> RunControlAdmission:
        request = RunControlRequest(command_id, kind)
        if command_id in self._outcomes or (
            self._pending is not None and self._pending.command_id == command_id
        ):
            return RunControlAdmission(command_id, kind, RunControlAdmissionKind.DUPLICATE)
        if self._paused is not None:
            if kind is RunControlKind.PAUSE:
                return RunControlAdmission(command_id, kind, RunControlAdmissionKind.CONFLICT)
            self._pending = request
            return RunControlAdmission(command_id, kind, RunControlAdmissionKind.ACCEPTED)
        pending = self._pending
        if pending is not None:
            if pending.kind is RunControlKind.PAUSE and kind is RunControlKind.CANCEL:
                self._record(
                    RunControlOutcome(
                        pending.command_id,
                        pending.kind,
                        RunControlOutcomeKind.SUPERSEDED,
                    )
                )
                self._pending = request
                return RunControlAdmission(command_id, kind, RunControlAdmissionKind.ACCEPTED)
            return RunControlAdmission(command_id, kind, RunControlAdmissionKind.CONFLICT)
        self._pending = request
        return RunControlAdmission(command_id, kind, RunControlAdmissionKind.ACCEPTED)

    def acknowledge(
        self,
        boundary: RunControlBoundary,
        *,
        dispatch_status: DispatchStatus | None = None,
    ) -> RunControlOutcome | None:
        request = self._pending
        if request is None:
            return None
        outcome = self.preview(boundary, dispatch_status=dispatch_status)
        assert outcome is not None
        self._pending = None
        if request.kind is RunControlKind.PAUSE:
            self._paused = outcome
        else:
            self._paused = None
        self._record(outcome)
        return outcome

    def preview(
        self,
        boundary: RunControlBoundary,
        *,
        dispatch_status: DispatchStatus | None = None,
    ) -> RunControlOutcome | None:
        request = self._pending
        if request is None:
            return None
        return RunControlOutcome(
            request.command_id,
            request.kind,
            (
                RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
                if request.kind is RunControlKind.PAUSE
                else RunControlOutcomeKind.CANCELLED
            ),
            boundary,
            dispatch_status,
        )

    def fail_pending(self, failure_code: str) -> RunControlOutcome | None:
        request = self._pending
        if request is None:
            return None
        outcome = RunControlOutcome(
            request.command_id,
            request.kind,
            RunControlOutcomeKind.BOUNDARY_FAILED,
            failure_code=failure_code,
        )
        self._pending = None
        self._record(outcome)
        return outcome

    def resolve_terminal(self) -> RunControlOutcome | None:
        request = self._pending
        if request is None:
            return None
        outcome = RunControlOutcome(
            request.command_id,
            request.kind,
            RunControlOutcomeKind.RUN_ALREADY_TERMINAL,
        )
        self._pending = None
        self._record(outcome)
        return outcome

    def resume(self, command_id: str) -> RunControlOutcome:
        paused = self._paused
        if paused is None:
            raise ValueError("run has no internal pause boundary")
        if not command_id.strip() or len(command_id) > 128:
            raise ValueError("run control command identity is invalid")
        if command_id in self._outcomes:
            return self._outcomes[command_id]
        outcome = RunControlOutcome(
            command_id,
            RunControlKind.PAUSE,
            RunControlOutcomeKind.RESUMED,
        )
        self._paused = None
        self._record(outcome)
        return outcome

    def _record(self, outcome: RunControlOutcome) -> None:
        self._outcomes[outcome.command_id] = outcome
        self._outcome_order.append(outcome.command_id)
        while len(self._outcome_order) > self._max_outcomes:
            expired = self._outcome_order.pop(0)
            self._outcomes.pop(expired, None)
