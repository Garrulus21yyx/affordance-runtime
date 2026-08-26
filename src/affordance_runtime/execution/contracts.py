"""Small action-intent, bound request, and transport-result contracts."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from affordance_runtime.immutable import freeze_json
from affordance_runtime.schema_digest import schema_digest

if TYPE_CHECKING:
    from affordance_runtime.actions.space_contracts import AdmittedActionSelection
    from affordance_runtime.world.acquisition import ObservationAcquisition
    from affordance_runtime.world.contracts import ActionBinding
    from affordance_runtime.world.observation_needs import ObservationNeed


class DispatchStatus(StrEnum):
    NOT_SENT = "not_sent"
    SENT = "sent"
    SENT_UNKNOWN = "sent_unknown"


class ExecutionTransition(StrEnum):
    """Typed causal transition established by an execution boundary."""

    STABLE_NAVIGATION = "stable_navigation"


class ExecutionCompletion(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ExecutionCancellationPhase(StrEnum):
    DISPATCH = "dispatch"
    POST_CAPTURE = "post_capture"
    EVALUATION = "evaluation"


class ActionError(StrEnum):
    STALE_BINDING = "stale_binding"
    CURRENTNESS_UNAVAILABLE = "currentness_unavailable"
    RATE_LIMITED = "rate_limited"
    INVALID_PARAMETERS = "invalid_parameters"
    EXECUTION_FAILED = "execution_failed"
    UNSUPPORTED_ACTION = "unsupported_action"
    CANCELLED = "cancelled"


class ExecutionDiagnosticPhase(StrEnum):
    PRE_DISPATCH = "pre_dispatch"
    DISPATCH_WAIT = "dispatch_wait"
    POST_CAPTURE = "post_capture"
    CLEANUP = "cleanup"


class SessionHealthStatus(StrEnum):
    ALIVE = "alive"
    LOST = "lost"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SessionHealth:
    status: SessionHealthStatus
    page_closed: bool | None = None
    browser_connected: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SessionHealthStatus):
            raise TypeError("session health status must be typed")
        if any(
            value is not None and type(value) is not bool
            for value in (
                self.page_closed,
                self.browser_connected,
            )
        ):
            raise TypeError("session health facts must be boolean or unknown")


@dataclass(frozen=True)
class ExecutionDiagnostic:
    diagnostic_ref: str
    phase: ExecutionDiagnosticPhase
    exception_type: str
    exception_module: str
    safe_message: str
    elapsed_ms: float
    dispatch_crossed: bool
    page_closed: bool | None = None
    browser_connected: bool | None = None
    traceback_ref: str = ""

    def __post_init__(self) -> None:
        if re.fullmatch(r"execution-diagnostic:[0-9a-f]{24}", self.diagnostic_ref) is None:
            raise ValueError("execution diagnostic identity is invalid")
        if not isinstance(self.phase, ExecutionDiagnosticPhase):
            raise TypeError("execution diagnostic phase must be typed")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", self.exception_type) is None:
            raise ValueError("execution diagnostic exception type is invalid")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,199}", self.exception_module) is None:
            raise ValueError("execution diagnostic exception module is invalid")
        if (
            not isinstance(self.safe_message, str)
            or len(self.safe_message) > 500
            or any(ord(character) < 32 for character in self.safe_message)
        ):
            raise ValueError("execution diagnostic message must be bounded public text")
        if isinstance(self.elapsed_ms, bool) or not isinstance(self.elapsed_ms, int | float) or self.elapsed_ms < 0:
            raise ValueError("execution diagnostic elapsed time is invalid")
        if type(self.dispatch_crossed) is not bool:
            raise TypeError("execution diagnostic dispatch flag must be boolean")
        if any(
            value is not None and type(value) is not bool
            for value in (
                self.page_closed,
                self.browser_connected,
            )
        ):
            raise TypeError("execution diagnostic session facts must be boolean or unknown")
        if self.traceback_ref and re.fullmatch(r"traceback:sha256:[0-9a-f]{64}", self.traceback_ref) is None:
            raise ValueError("execution diagnostic traceback reference is invalid")


@dataclass(frozen=True)
class ActionIntent:
    semantic_action: str
    target_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""
    expected_outcome: str = ""

    def __post_init__(self) -> None:
        if not self.semantic_action.strip() or not self.target_id.strip():
            raise ValueError("action intent requires semantic action and target")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        if not isinstance(self.expected_outcome, str) or len(self.expected_outcome) > 240:
            raise ValueError("action intent expected outcome must be one bounded string")
        object.__setattr__(self, "expected_outcome", self.expected_outcome.strip())


@dataclass(frozen=True)
class BoundActionRequest:
    request_id: str
    context_id: str
    world_observation_id: str
    intent: ActionIntent
    selection: AdmittedActionSelection
    binding: ActionBinding
    timeout_ms: int = 5_000
    verification_needs: tuple[ObservationNeed, ...] = ()
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        if (
            not self.request_id.strip()
            or not self.context_id.strip()
            or self.world_observation_id != self.binding.world_observation_id
        ):
            raise ValueError("bound request must identify its binding observation")
        if self.tool_call_id and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", self.tool_call_id) is None:
            raise ValueError("bound request tool call identity is invalid")
        if (
            self.selection.observation_id != self.world_observation_id
            or self.selection.action_id.strip() == ""
            or self.intent.semantic_action != self.selection.semantic_action
            or self.intent.target_id != self.selection.target_id
            or self.intent.parameters != self.selection.parameters
            or self.intent.destination_id != self.selection.destination_id
            or self.intent.expected_outcome != self.selection.expected_outcome
            or self.binding.binding_id not in self.selection.eligible_binding_ids
            or self.selection.semantic_action != self.binding.semantic_action
            or self.selection.target_id != self.binding.target_id
            or self.selection.effect_category != self.binding.effect_category
            or self.selection.semantic_effects != self.binding.semantic_effects
            or self.selection.schema_digest != schema_digest(self.binding.parameter_schema)
            or _risk_rank(self.binding.risk) > _risk_rank(self.selection.risk)
            or self.binding.observation_barrier != self.selection.observation_barrier
            or self.binding.destination_required != self.selection.destination_required
            or (
                self.selection.destination_id not in self.binding.eligible_destination_ids
                if self.selection.destination_id
                else self.binding.eligible_destination_ids != self.selection.eligible_destination_ids
            )
            or self.binding.verification_family != self.selection.verification_family
            or self.binding.verification_contract_digest != self.selection.verification_contract_digest
            or self.binding.verification_contract != self.selection.verification_contract
            or (
                self.selection.destination_id
                and self.selection.destination_id not in self.selection.eligible_destination_ids
            )
            or (self.selection.destination_required and not self.selection.destination_id)
        ):
            raise ValueError("bound request must retain its admitted option and binding group")
        if self.timeout_ms <= 0:
            raise ValueError("timeout must be positive")
        object.__setattr__(self, "verification_needs", tuple(self.verification_needs))
        if len({item.need_id for item in self.verification_needs}) != len(self.verification_needs):
            raise ValueError("bound request verification need IDs cannot repeat")

    @property
    def observation_id(self) -> str:
        """Compatibility read; world identity is canonical."""

        return self.world_observation_id


def _risk_rank(risk: object) -> int:
    return ("low", "medium", "high", "irreversible").index(str(risk))


@dataclass(frozen=True)
class ActionResult:
    request_id: str
    dispatch_status: DispatchStatus
    backend: str
    transport_success: bool
    error: ActionError | None = None
    adapter_evidence: dict[str, Any] = field(default_factory=dict)
    diagnostics: tuple[ExecutionDiagnostic, ...] = ()
    causal_transition: ExecutionTransition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch_status, DispatchStatus):
            raise TypeError("action result dispatch status must be typed")
        if self.error is not None and not isinstance(self.error, ActionError):
            raise TypeError("action result error must be typed")
        if self.causal_transition is not None and not isinstance(
            self.causal_transition,
            ExecutionTransition,
        ):
            raise TypeError("action result causal transition must be typed")
        if type(self.transport_success) is not bool:
            raise TypeError("action result transport success must be boolean")
        if not self.request_id.strip() or not self.backend.strip():
            raise ValueError("action result requires request and backend identity")
        inconsistent = (
            (self.dispatch_status in {DispatchStatus.NOT_SENT, DispatchStatus.SENT_UNKNOWN} and self.transport_success)
            or (self.transport_success and self.error is not None)
            or (not self.transport_success and self.error is None)
            or (self.error is ActionError.CANCELLED and self.dispatch_status is DispatchStatus.SENT)
        )
        if inconsistent:
            raise ValueError("action result dispatch status, transport success, and error are inconsistent")
        if self.causal_transition is not None and (
            self.dispatch_status is not DispatchStatus.SENT
            or not self.transport_success
            or self.error is not None
        ):
            raise ValueError("a causal transition requires a successful sent action")
        object.__setattr__(self, "adapter_evidence", freeze_json(self.adapter_evidence))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if (
            len(self.diagnostics) > 8
            or any(not isinstance(item, ExecutionDiagnostic) for item in self.diagnostics)
            or len({item.diagnostic_ref for item in self.diagnostics}) != len(self.diagnostics)
        ):
            raise ValueError("action result execution diagnostics are invalid")

    @property
    def permits_reselection(self) -> bool:
        """Whether a different model selection can safely follow this zero-dispatch result."""

        return (
            self.dispatch_status is DispatchStatus.NOT_SENT
            and self.error is ActionError.INVALID_PARAMETERS
        )


@dataclass(frozen=True)
class ExecutionAttempt:
    request: BoundActionRequest
    result: ActionResult
    post_acquisition: ObservationAcquisition | None
    recovery_acquisitions: tuple[ObservationAcquisition, ...] = ()

    def __post_init__(self) -> None:
        _validate_execution_attempt(
            self.request,
            self.result,
            self.post_acquisition,
            self.recovery_acquisitions,
        )


@dataclass(frozen=True)
class ExecutionObservationRecovery:
    acquisition: ObservationAcquisition
    diagnostics: tuple[ExecutionDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        from affordance_runtime.world.acquisition import AcquisitionOrigin, ObservationAcquisition

        if not isinstance(self.acquisition, ObservationAcquisition):
            raise TypeError("execution recovery acquisition must be typed")
        if self.acquisition.origin is not AcquisitionOrigin.INDEPENDENT_CAPTURE:
            raise ValueError("execution recovery requires an independent capture")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if (
            len(self.diagnostics) > 8
            or any(not isinstance(item, ExecutionDiagnostic) for item in self.diagnostics)
            or len({item.diagnostic_ref for item in self.diagnostics}) != len(self.diagnostics)
        ):
            raise ValueError("execution recovery diagnostics are invalid")


@dataclass(frozen=True)
class ExecutionOutcome:
    """Exact immutable closure of one bound dispatch attempt."""

    request: BoundActionRequest
    result: ActionResult
    post_acquisition: ObservationAcquisition | None
    recovery_acquisitions: tuple[ObservationAcquisition, ...] = ()
    prior_attempts: tuple[ExecutionAttempt, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.request, BoundActionRequest):
            raise TypeError("execution outcome request must be typed")
        _validate_execution_attempt(
            self.request,
            self.result,
            self.post_acquisition,
            self.recovery_acquisitions,
        )
        object.__setattr__(self, "prior_attempts", tuple(self.prior_attempts))
        if len(self.prior_attempts) > 1 or any(not isinstance(item, ExecutionAttempt) for item in self.prior_attempts):
            raise ValueError("execution outcome recovery is bounded to one replay")

    @property
    def current_attempt(self) -> ExecutionAttempt:
        return ExecutionAttempt(
            self.request,
            self.result,
            self.post_acquisition,
            self.recovery_acquisitions,
        )

    @property
    def attempts(self) -> tuple[ExecutionAttempt, ...]:
        return (*self.prior_attempts, self.current_attempt)

    @property
    def attempt_count(self) -> int:
        return len(self.prior_attempts) + 1

    @property
    def all_diagnostics(self) -> tuple[ExecutionDiagnostic, ...]:
        return tuple(diagnostic for attempt in self.attempts for diagnostic in attempt.result.diagnostics)


@dataclass(frozen=True)
class ExecutionReceipt:
    """One dispatch-crossing primitive retained by the single execution algebra."""

    request: BoundActionRequest
    result: ActionResult
    before_observation_id: str
    after_observation_id: str

    def __post_init__(self) -> None:
        if self.result.request_id != self.request.request_id:
            raise ValueError("execution receipt request/result lineage mismatch")
        if self.result.dispatch_status is DispatchStatus.NOT_SENT:
            raise ValueError("a non-dispatched attempt is not an execution receipt")
        if self.before_observation_id != self.request.world_observation_id:
            raise ValueError("execution receipt before-world lineage mismatch")
        if not self.after_observation_id.strip():
            raise ValueError("execution receipt requires after-world lineage")


@dataclass(frozen=True)
class ExecutionReceiptBatch:
    """The sole effectful outcome committed into one StepResult."""

    receipts: tuple[ExecutionReceipt, ...]
    completion: ExecutionCompletion
    terminal_failure: ActionResult | None = None
    cancellation_phase: ExecutionCancellationPhase | None = None

    def __post_init__(self) -> None:
        receipts = tuple(self.receipts)
        if any(not isinstance(item, ExecutionReceipt) for item in receipts):
            raise TypeError("execution receipt batch requires typed receipts")
        if not isinstance(self.completion, ExecutionCompletion):
            raise TypeError("execution receipt completion must be typed")
        if self.cancellation_phase is not None and not isinstance(self.cancellation_phase, ExecutionCancellationPhase):
            raise TypeError("execution cancellation phase must be typed")
        if self.terminal_failure is not None and (
            not isinstance(self.terminal_failure, ActionResult)
            or self.terminal_failure.dispatch_status is not DispatchStatus.NOT_SENT
        ):
            raise ValueError("execution batch terminal failure must be a non-dispatched result")
        statuses = tuple(item.result.dispatch_status for item in receipts)
        if self.completion is ExecutionCompletion.COMPLETE and (
            not receipts
            or self.terminal_failure is not None
            or any(status is not DispatchStatus.SENT for status in statuses)
        ):
            raise ValueError("complete execution requires only known dispatched receipts")
        if self.completion is ExecutionCompletion.UNKNOWN and (
            not receipts
            or self.terminal_failure is not None
            or DispatchStatus.SENT_UNKNOWN not in statuses
            or any(item.result.error is ActionError.CANCELLED for item in receipts)
            or any(status not in {DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN} for status in statuses)
        ):
            raise ValueError("unknown execution requires retained SENT_UNKNOWN dispatch truth")
        if self.completion is ExecutionCompletion.PARTIAL and (
            self.terminal_failure is None
            or self.terminal_failure.error is ActionError.CANCELLED
            or any(status is not DispatchStatus.SENT for status in statuses)
        ):
            raise ValueError("partial execution requires known receipts and a terminal failure")
        if self.completion is ExecutionCompletion.CANCELLED:
            dispatch_cancelled = (
                self.terminal_failure is not None and self.terminal_failure.error is ActionError.CANCELLED
            ) or (
                bool(receipts)
                and receipts[-1].result.dispatch_status is DispatchStatus.SENT_UNKNOWN
                and receipts[-1].result.error is ActionError.CANCELLED
            )
            if (
                self.cancellation_phase is None
                or (self.cancellation_phase is ExecutionCancellationPhase.DISPATCH and not dispatch_cancelled)
                or (
                    self.cancellation_phase is ExecutionCancellationPhase.POST_CAPTURE
                    and (
                        not receipts
                        or self.terminal_failure is not None
                        or any(status is not DispatchStatus.SENT for status in statuses)
                    )
                )
                or (
                    self.cancellation_phase is ExecutionCancellationPhase.EVALUATION
                    and (
                        not receipts
                        or (self.terminal_failure is not None and self.terminal_failure.error is ActionError.CANCELLED)
                        or any(status not in {DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN} for status in statuses)
                        or any(item.result.error is ActionError.CANCELLED for item in receipts)
                    )
                )
            ):
                raise ValueError("cancelled execution requires exact typed cancellation truth")
        elif self.cancellation_phase is not None:
            raise ValueError("cancellation phase is only legal for cancelled execution")
        object.__setattr__(self, "receipts", receipts)

    @property
    def execution_count(self) -> int:
        return len(self.receipts)

    @property
    def sent_unknown_count(self) -> int:
        return sum(item.result.dispatch_status is DispatchStatus.SENT_UNKNOWN for item in self.receipts)

    @classmethod
    def from_atomic(
        cls,
        outcome: ExecutionOutcome,
        after_observation_id: str,
        *,
        completion: ExecutionCompletion | None = None,
        cancellation_phase: ExecutionCancellationPhase | None = None,
    ) -> ExecutionReceiptBatch:
        attempts = outcome.attempts
        receipts = tuple(
            ExecutionReceipt(
                item.request,
                item.result,
                item.request.world_observation_id,
                after_observation_id,
            )
            for item in attempts
            if item.result.dispatch_status is not DispatchStatus.NOT_SENT
        )
        terminal_failure = outcome.result if outcome.result.dispatch_status is DispatchStatus.NOT_SENT else None
        resolved_completion = completion or (
            ExecutionCompletion.PARTIAL
            if terminal_failure is not None
            else ExecutionCompletion.UNKNOWN
            if outcome.result.dispatch_status is DispatchStatus.SENT_UNKNOWN
            else ExecutionCompletion.COMPLETE
        )
        resolved_cancellation_phase = cancellation_phase
        if resolved_completion is ExecutionCompletion.CANCELLED and resolved_cancellation_phase is None:
            from affordance_runtime.world.acquisition import AcquisitionStatus

            resolved_cancellation_phase = (
                ExecutionCancellationPhase.DISPATCH
                if outcome.result.error is ActionError.CANCELLED
                else ExecutionCancellationPhase.POST_CAPTURE
                if any(
                    item.status is AcquisitionStatus.CANCELLED
                    for item in (
                        *((outcome.post_acquisition,) if outcome.post_acquisition is not None else ()),
                        *outcome.recovery_acquisitions,
                    )
                )
                else None
            )
        return cls(receipts, resolved_completion, terminal_failure, resolved_cancellation_phase)


def _validate_execution_attempt(
    request: BoundActionRequest,
    result: ActionResult,
    post_acquisition: ObservationAcquisition | None,
    recovery_acquisitions: tuple[ObservationAcquisition, ...],
) -> None:
    from affordance_runtime.world.acquisition import AcquisitionOrigin, ObservationAcquisition

    if not isinstance(request, BoundActionRequest) or not isinstance(result, ActionResult):
        raise TypeError("execution attempt request and result must be typed")
    if result.request_id != request.request_id or result.backend != request.binding.executor_id:
        raise ValueError("execution attempt request/result lineage mismatch")
    dispatched = result.dispatch_status is not DispatchStatus.NOT_SENT
    if dispatched != (post_acquisition is not None):
        raise ValueError("execution attempt dispatch/post-acquisition shape mismatch")
    if post_acquisition is not None and (
        not isinstance(post_acquisition, ObservationAcquisition)
        or post_acquisition.origin is not AcquisitionOrigin.POST_ACTION
    ):
        raise ValueError("execution post acquisition must be typed POST_ACTION")
    recovery = tuple(recovery_acquisitions)
    if len(recovery) > 1 or any(
        not isinstance(item, ObservationAcquisition) or item.origin is not AcquisitionOrigin.INDEPENDENT_CAPTURE
        for item in recovery
    ):
        raise ValueError("execution recovery permits one independent fresh capture")
    if recovery and (
        result.dispatch_status is DispatchStatus.NOT_SENT
        or post_acquisition is None
        or post_acquisition.status.value == "acquired"
    ):
        raise ValueError("execution recovery requires a dispatched action with a failed normal post acquisition")


class ActionDispatchCancelled(asyncio.CancelledError):
    """Adapter cancellation carrying its exact dispatch-boundary result."""

    def __init__(self, result: ActionResult) -> None:
        if result.error is not ActionError.CANCELLED or result.dispatch_status not in {
            DispatchStatus.NOT_SENT,
            DispatchStatus.SENT_UNKNOWN,
        }:
            raise ValueError("dispatch cancellation must retain NOT_SENT or SENT_UNKNOWN truth")
        self.result = result


class ExecutionCancelled(asyncio.CancelledError):
    """Host cancellation propagated only after exact execution closure."""

    def __init__(self, outcome: ExecutionOutcome) -> None:
        from affordance_runtime.world.acquisition import AcquisitionStatus

        action_cancelled = outcome.result.error is ActionError.CANCELLED and outcome.result.dispatch_status in {
            DispatchStatus.NOT_SENT,
            DispatchStatus.SENT_UNKNOWN,
        }
        post_cancelled = (
            outcome.result.dispatch_status is not DispatchStatus.NOT_SENT
            and outcome.post_acquisition is not None
            and outcome.post_acquisition.status is AcquisitionStatus.CANCELLED
        )
        if not (action_cancelled or post_cancelled):
            raise ValueError("execution cancellation requires exact action or post-acquisition cancellation")
        self.outcome = outcome
