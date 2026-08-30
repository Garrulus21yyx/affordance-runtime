"""Information-increment monitor for bounded long-horizon episodes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from affordance_runtime.agent.attempt_signature import PublicAttemptSignature, public_attempt_signature
from affordance_runtime.agent.context.contracts import sanitize_history_value
from affordance_runtime.agent.context.observation_delivery import (
    InformationDelta,
    InformationDeltaKind,
    current_findings_digest,
)
from affordance_runtime.agent.decisions import (
    LocalToolResult,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.profile import DEFAULT_AGENT_LOOP_PROFILE, AgentLoopProfile
from affordance_runtime.agent.recovery import (
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    EpisodeMonitorTransition,
    RecoveryKind,
    RecoveryLifecycleTransition,
    RecoverySignal,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation.contracts import (
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.public_semantic_digest import (
    public_page_semantic_digest,
    public_world_semantic_digest,
)

_MAX_SAME_WORLD_CONTROL_DISCOVERY_STEPS = 2
_MAX_RECENT_GUI_ATTEMPTS = 16


@dataclass(frozen=True)
class _GuiAttemptRecord:
    signature: PublicAttemptSignature
    page_semantic_digest: str


@dataclass
class EpisodeMonitor:
    """Own one no-progress state machine; query and region identities are not progress."""

    profile: AgentLoopProfile = DEFAULT_AGENT_LOOP_PROFILE
    world_digest: str = ""
    current_findings_digest: str = ""
    observation_only_streak: int = 0
    recovery_count: int = 0
    closed_route_count: int = 0
    latest_attempt_signature: PublicAttemptSignature | None = None
    same_attempt_streak: int = 0
    no_progress_count: int = 0
    recent_gui_attempts: tuple[_GuiAttemptRecord, ...] = ()
    recent_gui_results: tuple[tuple[str, str], ...] = ()
    active_gui_cycle_digest: str = ""
    active_recovery: RecoverySignal | None = None
    recovery_epoch_counter: int = 0

    def start_episode(self, world, task_evaluation) -> None:
        del task_evaluation
        self.world_digest = public_world_semantic_digest(world)
        self.current_findings_digest = current_findings_digest(world)
        self.observation_only_streak = 0
        self.recovery_count = 0
        self.closed_route_count = 0
        self.latest_attempt_signature = None
        self.same_attempt_streak = 0
        self.no_progress_count = 0
        self.recent_gui_attempts = ()
        self.recent_gui_results = ()
        self.active_gui_cycle_digest = ""
        self.active_recovery = None
        self.recovery_epoch_counter = 0

    def end_episode(self) -> None:
        """Close Runtime recovery state at one terminal run boundary."""

        self.active_recovery = None

    def restore_episode(
        self,
        world: WorldObservation,
        task_evaluation: object,
        recovery_signal: RecoverySignal | None,
    ) -> None:
        """Rebase one durable recovery epoch onto a fresh reconnect World."""

        self.start_episode(world, task_evaluation)
        if recovery_signal is None:
            return
        self.active_recovery = recovery_signal
        self.recovery_count = recovery_signal.recovery_attempt
        self.latest_attempt_signature = (
            recovery_signal.prohibited_attempt_signatures[-1] if recovery_signal.prohibited_attempt_signatures else None
        )
        self.same_attempt_streak = int(self.latest_attempt_signature is not None)
        parts = recovery_signal.epoch_id.split(":", 2)
        if len(parts) == 3 and parts[1].isdigit():
            self.recovery_epoch_counter = int(parts[1])

    def _open_or_continue_recovery(
        self,
        candidate: RecoverySignal,
    ) -> tuple[RecoverySignal, RecoveryLifecycleTransition]:
        """Install one bounded signal while preserving the current recovery owner."""

        active = self.active_recovery
        if active is None:
            self.recovery_epoch_counter += 1
            digest = candidate.stable_signature.rsplit(":", 1)[-1][:32]
            evidence = dict(candidate.observed_evidence)
            evidence.setdefault("origin_dispatch", evidence.get("dispatch", DispatchStatus.NOT_SENT.value))
            signal = replace(
                candidate,
                observed_evidence=evidence,
                epoch_id=f"recovery:{self.recovery_epoch_counter}:{digest}",
                evidence_revision=1,
            )
            self.active_recovery = signal
            return signal, RecoveryLifecycleTransition.STARTED

        evidence = dict(active.observed_evidence)
        evidence.update(candidate.observed_evidence)
        evidence["latest_recovery_kind"] = candidate.kind.value
        attempted_modes = tuple(dict.fromkeys((*active.attempted_modes, *candidate.attempted_modes)))
        prohibited = tuple(
            dict.fromkeys((*active.prohibited_attempt_signatures, *candidate.prohibited_attempt_signatures))
        )[-_MAX_RECENT_GUI_ATTEMPTS:]
        signal = replace(
            active,
            kind=candidate.kind,
            observed_evidence=evidence,
            attempted_modes=attempted_modes,
            prohibited_attempt_signatures=prohibited,
            human_instruction=candidate.human_instruction or active.human_instruction,
            recovery_attempt=candidate.recovery_attempt,
            evidence_revision=active.evidence_revision + 1,
        )
        self.active_recovery = signal
        return signal, RecoveryLifecycleTransition.CONTINUED

    def _recovery_transition(
        self,
        events: Sequence[EpisodeMonitorEvent],
        recommendation: EpisodeMonitorRecommendation,
        reason: str,
        candidate: RecoverySignal,
    ) -> EpisodeMonitorTransition:
        signal, lifecycle = self._open_or_continue_recovery(candidate)
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys(events)),
            recommendation,
            reason,
            signal,
            lifecycle,
        )

    def _carry_recovery(
        self,
        result: StepResult,
        events: Sequence[EpisodeMonitorEvent],
        information_delta: InformationDelta | None,
        *,
        recommendation: EpisodeMonitorRecommendation = EpisodeMonitorRecommendation.RECOVER,
        reason: str = "",
    ) -> EpisodeMonitorTransition:
        """Keep an unresolved recovery active while a diagnostic action adds evidence."""

        active = self.active_recovery
        if active is None:
            raise RuntimeError("cannot carry an inactive recovery")
        evidence = dict(active.observed_evidence)
        evidence.update(
            {
                "latest_attempt": _bounded_public_attempt(result),
                "latest_dispatch": _dispatch_status(result),
                "world_digest": self.world_digest,
                "current_findings_digest": self.current_findings_digest,
            }
        )
        if information_delta is not None:
            evidence["latest_information_delta"] = information_delta.kind.value
        attempted_modes = tuple(dict.fromkeys((*active.attempted_modes, _attempted_mode(result))))
        signal = replace(
            active,
            observed_evidence=evidence,
            attempted_modes=attempted_modes,
            evidence_revision=active.evidence_revision + 1,
        )
        self.active_recovery = signal
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys(events)),
            recommendation,
            reason or active.kind.value,
            signal,
            RecoveryLifecycleTransition.CONTINUED,
        )

    def _close_recovery(
        self,
        events: Sequence[EpisodeMonitorEvent],
    ) -> EpisodeMonitorTransition:
        self.active_recovery = None
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys(events)),
            EpisodeMonitorRecommendation.CONTINUE,
            "recovery_closed",
            None,
            RecoveryLifecycleTransition.CLOSED,
        )

    def evaluate(
        self,
        result: StepResult,
        findings_digest: str,
        information_delta: InformationDelta | None = None,
    ) -> EpisodeMonitorTransition:
        """Advance only from owner-produced digests and a typed dispatch receipt."""

        if not findings_digest:
            raise ValueError("episode monitor requires a nonblank findings digest")
        world_delta = result.public_world_delta
        assert world_delta is not None  # StepResult establishes this committed invariant.
        next_world_digest = world_delta.after_world_digest
        if not self.world_digest:
            self.world_digest = world_delta.before_world_digest
            self.current_findings_digest = current_findings_digest(result.before_world)

        events = _diagnostic_events(result)
        state_changed = any(
            (
                next_world_digest != self.world_digest,
                findings_digest != self.current_findings_digest,
                information_delta is not None and information_delta.kind is InformationDeltaKind.NEW_INFORMATION,
            )
        )
        gui_dispatched = _gui_dispatched(result)
        control_discovery = isinstance(result.decision, RequestActionPage)
        durable_progress = bool(
            information_delta is not None and information_delta.kind is InformationDeltaKind.NEW_INFORMATION
        ) or (gui_dispatched and _gui_has_operational_result(result))

        self.world_digest = next_world_digest
        self.current_findings_digest = findings_digest

        if state_changed:
            events.append(EpisodeMonitorEvent.STATE_CHANGED)
        else:
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)

        # Native evaluation remains the only task-completion/impossibility authority.
        if result.task_evaluation is None:
            if self.active_recovery is not None:
                return self._carry_recovery(result, events, information_delta)
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)
        if result.task_evaluation.status not in {
            TaskEvaluationStatus.INCOMPLETE,
            TaskEvaluationStatus.UNKNOWN,
        }:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.closed_route_count = 0
            self.same_attempt_streak = 0
            self.recent_gui_attempts = ()
            self.recent_gui_results = ()
            self.active_gui_cycle_digest = ""
            if self.active_recovery is not None:
                return self._close_recovery(events)
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        if self.recovery_count and result.feedback == "recovery_repeat_rejected":
            signature = self.latest_attempt_signature or _same_world_attempt_signature(result)
            repeats_latest = signature == self.latest_attempt_signature
            self.no_progress_count += 1
            self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
            self.latest_attempt_signature = signature
            self.recovery_count = self.recovery_count + 1 if repeats_latest else 1
            signal = _control_stall_signal(
                result,
                self,
                recovery_attempt=self.recovery_count,
            )
            if self.recovery_count > self.profile.max_recovery_retries + 1:
                return self._recovery_transition(
                    (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                    EpisodeMonitorRecommendation.BLOCK,
                    "control_stalled",
                    signal,
                )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.CONTROL_STALL.value,
                signal,
            )

        if isinstance(result.decision, ToolRejectedResult):
            signature = _same_world_attempt_signature(result)
            repeats_latest = signature == self.latest_attempt_signature
            self.no_progress_count += 1
            self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
            self.latest_attempt_signature = signature
            self.recovery_count = self.recovery_count + 1 if repeats_latest else 1
            signal = _control_stall_signal(
                result,
                self,
                recovery_attempt=self.recovery_count,
            )
            if self.recovery_count > self.profile.max_recovery_retries + 1:
                return self._recovery_transition(
                    (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                    EpisodeMonitorRecommendation.BLOCK,
                    "control_stalled",
                    signal,
                )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.CONTROL_STALL.value,
                signal,
            )

        gui_record = _gui_attempt_record(result) if gui_dispatched else None
        gui_signature = gui_record.signature if gui_record is not None else None
        repeated_gui_result = self._record_gui_result(gui_signature, next_world_digest)
        route_origin, route_length = _closed_gui_route(
            self.recent_gui_attempts,
            gui_record,
            result.after_world,
        )
        cycle_digest, cycle_period = self._record_gui_attempt(gui_record)

        if self.active_recovery is not None and gui_dispatched and _gui_has_operational_result(result):
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = gui_signature
            self.same_attempt_streak = 1
            self.active_gui_cycle_digest = ""
            return self._close_recovery(events)

        if self.active_recovery is not None and not gui_dispatched:
            if (
                information_delta is not None
                and information_delta.kind is InformationDeltaKind.NEW_INFORMATION
                and _recovery_origin_is_local(self.active_recovery)
            ):
                self.observation_only_streak = 0
                self.recovery_count = 0
                self.latest_attempt_signature = None
                self.same_attempt_streak = 0
                self.active_gui_cycle_digest = ""
                return self._close_recovery(events)
            signature = _same_world_attempt_signature(result)
            repeats_latest = signature == self.latest_attempt_signature
            self.no_progress_count += 1
            self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
            self.latest_attempt_signature = signature
            self.recovery_count = 1
            if repeats_latest:
                return self._carry_recovery(
                    result,
                    (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                    information_delta,
                    recommendation=EpisodeMonitorRecommendation.BLOCK,
                    reason="control_stalled",
                )
            return self._carry_recovery(result, events, information_delta)

        if route_origin is not None:
            self.observation_only_streak = 0
            self.active_gui_cycle_digest = ""
            self.closed_route_count = min(3, self.closed_route_count + 1)
            if self.closed_route_count != 2:
                # Returning from a distinct page is a normal acquisition pattern
                # (for example open an item, read it, then return to the list).
                # Runtime cannot call it failed merely because the route closed.
                self.recovery_count = 0
                self.same_attempt_streak = 1
                self.latest_attempt_signature = gui_signature
                if self.active_recovery is not None:
                    return self._carry_recovery(result, events, information_delta)
                return EpisodeMonitorTransition(
                    tuple(dict.fromkeys(events)),
                    EpisodeMonitorRecommendation.CONTINUE,
                )
            self.same_attempt_streak = 1
            self.latest_attempt_signature = route_origin
            self.recovery_count = 1
            signal = _closed_route_review_signal(
                result,
                self,
                outbound_attempt=route_origin,
                route_length=route_length,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.ROUTE_REVIEW),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.STRATEGY_REVIEW.value,
                signal,
            )
        if repeated_gui_result and state_changed and gui_signature is not None:
            self.observation_only_streak = 0
            self.no_progress_count += 1
            self.same_attempt_streak = 1
            self.latest_attempt_signature = gui_signature
            self.recovery_count = 1
            self.active_gui_cycle_digest = ""
            signal = _repeated_gui_result_signal(
                result,
                self,
                gui_signature=gui_signature,
                result_world_digest=next_world_digest,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.OSCILLATION),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.STATE_OSCILLATION.value,
                signal,
            )
        if cycle_digest:
            self.observation_only_streak = 0
            self.no_progress_count += 1
            self.same_attempt_streak = 1
            self.latest_attempt_signature = gui_signature
            repeated_cycle = cycle_digest == self.active_gui_cycle_digest
            self.active_gui_cycle_digest = cycle_digest
            signal = _gui_cycle_recovery_signal(
                result,
                self,
                cycle_digest=cycle_digest,
                cycle_period=cycle_period,
                recovery_attempt=2 if repeated_cycle else 1,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.OSCILLATION),
                EpisodeMonitorRecommendation.BLOCK if repeated_cycle else EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.STATE_OSCILLATION.value,
                signal,
            )

        if durable_progress:
            if self.active_recovery is not None:
                return self._carry_recovery(result, events, information_delta)
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = None
            self.same_attempt_streak = 0
            if information_delta is not None and information_delta.kind is InformationDeltaKind.NEW_INFORMATION:
                # New public content closes a same-screen read stall, but it
                # does not prove that the surrounding GUI route advanced the
                # task.  Keep the bounded effectful route so a later return to
                # its origin can be reviewed by the ActionPolicy.
                self.active_gui_cycle_digest = ""
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        # A causally dispatched GUI attempt that reached a semantically
        # different fresh public World starts a new same-world attempt window,
        # even when its local postcondition is not mechanically decidable.
        # Sequential keyboard navigation and repeated scrolling may lawfully
        # use the same operation while each dispatch advances transient UI
        # state. Route/cycle detection above still observes the bounded GUI
        # sequence and therefore remains the strategy-regression authority.
        if gui_dispatched and state_changed:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = gui_signature
            self.same_attempt_streak = 1
            if self.active_recovery is not None:
                return self._carry_recovery(result, events, information_delta)
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        exact_replay = bool(
            information_delta is not None and information_delta.kind is InformationDeltaKind.EXACT_REPLAY
        )
        signature = _same_world_attempt_signature(result)
        repeats_latest = signature == self.latest_attempt_signature
        self.no_progress_count += 1
        self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
        self.latest_attempt_signature = signature
        if gui_dispatched or exact_replay:
            self.observation_only_streak = 0
        else:
            self.observation_only_streak += 1

        if self.recovery_count:
            if repeats_latest:
                signal = _control_stall_signal(result, self, recovery_attempt=self.recovery_count)
                return self._recovery_transition(
                    (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                    EpisodeMonitorRecommendation.BLOCK,
                    "control_stalled",
                    signal,
                )
            # A different attempt is not evidence of a repeated strategy.
            # Keep the recovery feedback active, but restart its local retry
            # phase instead of accumulating a hidden semantic-attempt budget.
            # The TaskGoal turn budget remains the sole total-loop bound.
            self.recovery_count = 1
            signal = _control_stall_signal(
                result,
                self,
                recovery_attempt=self.recovery_count,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.CONTROL_STALL.value,
                signal,
            )

        recovery_due = any(
            (
                exact_replay,
                gui_dispatched and self.same_attempt_streak >= 2,
                control_discovery and self.observation_only_streak >= _MAX_SAME_WORLD_CONTROL_DISCOVERY_STEPS,
                not gui_dispatched
                and not control_discovery
                and not exact_replay
                and self.observation_only_streak >= self.profile.max_consecutive_observation_only,
            )
        )
        if not recovery_due:
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        self.recovery_count = 1
        self.observation_only_streak = 0
        signal = _control_stall_signal(result, self, recovery_attempt=1)
        return self._recovery_transition(
            (*events, EpisodeMonitorEvent.REPEATED_ACTION),
            EpisodeMonitorRecommendation.RECOVER,
            RecoveryKind.CONTROL_STALL.value,
            signal,
        )

    def _record_gui_attempt(
        self,
        record: _GuiAttemptRecord | None,
    ) -> tuple[str, int]:
        """Record bounded effectful attempts and identify a repeated short cycle."""

        if record is None:
            return "", 0
        self.recent_gui_attempts = (*self.recent_gui_attempts, record)[-_MAX_RECENT_GUI_ATTEMPTS:]
        return _short_gui_cycle(self.recent_gui_attempts)

    def _record_gui_result(
        self,
        signature: PublicAttemptSignature | None,
        result_world_digest: str,
    ) -> bool:
        """Detect one repeated semantic action/result pair in the bounded window."""

        if signature is None:
            return False
        key = (signature.digest, result_world_digest)
        repeated = key in self.recent_gui_results
        self.recent_gui_results = (*self.recent_gui_results, key)[-_MAX_RECENT_GUI_ATTEMPTS:]
        return repeated


def _diagnostic_events(result: StepResult) -> list[EpisodeMonitorEvent]:
    events: list[EpisodeMonitorEvent] = []
    if isinstance(result.decision, PolicyFailure):
        events.append(EpisodeMonitorEvent.PROVIDER_FAILURE)
    elif result.runtime_failure is not None:
        events.append(EpisodeMonitorEvent.ENVIRONMENT_FAILURE)
    elif isinstance(result.decision, RequestObservation) and result.feedback.startswith("observation_unavailable"):
        events.append(EpisodeMonitorEvent.CAPABILITY_GAP)
    return events


def _gui_dispatched(result: StepResult) -> bool:
    batch = result.execution_receipts
    return bool(
        batch is not None and any(item.result.dispatch_status is not DispatchStatus.NOT_SENT for item in batch.receipts)
    )


def _dispatch_status(result: StepResult) -> str:
    """Project the strongest typed dispatch receipt without inventing state."""

    receipts = tuple(getattr(result.execution_receipts, "receipts", ()))
    statuses = tuple(item.result.dispatch_status for item in receipts)
    if DispatchStatus.SENT_UNKNOWN in statuses:
        return DispatchStatus.SENT_UNKNOWN.value
    if DispatchStatus.SENT in statuses:
        return DispatchStatus.SENT.value
    return DispatchStatus.NOT_SENT.value


def _recovery_origin_is_local(signal: RecoverySignal) -> bool:
    """Only same-call local information can resolve a local observation stall."""

    return signal.observed_evidence.get("origin_dispatch") == DispatchStatus.NOT_SENT.value


def _control_stall_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    recovery_attempt: int,
) -> RecoverySignal:
    prohibited_attempt_signature = (
        monitor.latest_attempt_signature
        if result.feedback == "recovery_repeat_rejected" and monitor.latest_attempt_signature is not None
        else _proven_failed_gui_attempt_signature(result)
    )
    signature_payload: tuple[object, ...] = (
        monitor.world_digest,
        monitor.current_findings_digest,
    )
    if prohibited_attempt_signature is not None:
        signature_payload += (prohibited_attempt_signature.digest,)
    signature = "control_stall:sha256:" + hashlib.sha256(_canonical_json(signature_payload).encode()).hexdigest()
    return RecoverySignal(
        RecoveryKind.CONTROL_STALL,
        signature,
        {
            "attempt": _bounded_public_attempt(result),
            "dispatch": _dispatch_status(result),
            "observation_only_streak": monitor.observation_only_streak,
            "world_digest": monitor.world_digest,
            "current_findings_digest": monitor.current_findings_digest,
        },
        attempted_modes=(_attempted_mode(result),),
        prohibited_attempt_signatures=(
            (prohibited_attempt_signature,) if prohibited_attempt_signature is not None else ()
        ),
        human_instruction=_control_stall_instruction(result),
        recovery_attempt=recovery_attempt,
    )


def _gui_cycle_recovery_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    cycle_digest: str,
    cycle_period: int,
    recovery_attempt: int,
) -> RecoverySignal:
    """Report a mechanical effectful-action cycle without judging task progress."""

    return RecoverySignal(
        RecoveryKind.STATE_OSCILLATION,
        "state_oscillation:" + cycle_digest,
        {
            "attempt": _bounded_public_attempt(result),
            "dispatch": _dispatch_status(result),
            "cycle_period": cycle_period,
            "world_digest": monitor.world_digest,
            "current_findings_digest": monitor.current_findings_digest,
        },
        attempted_modes=(_attempted_mode(result),),
        # A cycle is a sequence-level finding.  Blacklisting whichever action
        # happened to close it is both phase-dependent and usually useless on
        # the resulting fresh World.  The ActionPolicy receives the bounded
        # cycle finding and owns the semantic strategy change.
        prohibited_attempt_signatures=(),
        human_instruction=(
            "Recent effectful GUI attempts repeated a short cycle across fresh Worlds. Preserve completed results "
            "already present in tool history and choose an offered action outside this cycle toward an unresolved "
            "requirement; do not revisit the same sequence merely to re-verify it."
        ),
        recovery_attempt=recovery_attempt,
    )


def _repeated_gui_result_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    gui_signature: PublicAttemptSignature,
    result_world_digest: str,
) -> RecoverySignal:
    """Request a new route when one action reaches an already-seen public result."""

    digest = hashlib.sha256(_canonical_json((gui_signature.digest, result_world_digest)).encode()).hexdigest()
    return RecoverySignal(
        RecoveryKind.STATE_OSCILLATION,
        "state_oscillation:sha256:" + digest,
        {
            "attempt": _bounded_public_attempt(result),
            "dispatch": _dispatch_status(result),
            "repeated_result_world": True,
            "world_digest": monitor.world_digest,
            "current_findings_digest": monitor.current_findings_digest,
        },
        attempted_modes=(_attempted_mode(result),),
        prohibited_attempt_signatures=(),
        human_instruction=(
            "The same semantic GUI action has reached this public result before. Preserve current evidence and "
            "choose a materially different offered control or observation route; do not replay this action. If "
            "structural coverage is partial and the expected content is still absent, use offered entity_discovery "
            "once to inspect a visible blocker before trying alternate navigation."
        ),
        recovery_attempt=1,
    )


def _closed_route_review_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    outbound_attempt: PublicAttemptSignature,
    route_length: int,
) -> RecoverySignal:
    """Request one semantic review after the second distinct closed route."""

    returned_page_digest = public_page_semantic_digest(result.after_world)
    signature = (
        "strategy_review:sha256:"
        + hashlib.sha256(
            _canonical_json(
                (
                    outbound_attempt.digest,
                    returned_page_digest,
                )
            ).encode()
        ).hexdigest()
    )
    current_attempt = _gui_attempt_signature(result)
    attempted_modes = tuple(
        dict.fromkeys(
            item
            for item in (
                outbound_attempt.operation,
                current_attempt.operation if current_attempt is not None else "",
            )
            if item
        )
    )
    return RecoverySignal(
        RecoveryKind.STRATEGY_REVIEW,
        signature,
        {
            "returned_to_prior_semantic_page": True,
            "closed_route_count": monitor.closed_route_count,
            "route_effectful_attempt_count": route_length,
            "outbound_operation": outbound_attempt.operation,
            "return_operation": current_attempt.operation if current_attempt is not None else "",
            "world_digest": monitor.world_digest,
            "current_findings_digest": monitor.current_findings_digest,
        },
        attempted_modes=attempted_modes,
        prohibited_attempt_signatures=(),
        human_instruction=(
            "The latest effectful GUI excursion returned to the semantic page where an earlier outbound attempt "
            "began. Preserve facts acquired during the excursion and reassess them against the unresolved task "
            "requirements. Do not immediately replay that exact outbound attempt; choose a different current route, "
            "use the acquired result, or finish when the requested answer is already supported."
        ),
        recovery_attempt=2,
    )


def _closed_gui_route(
    prior_attempts: tuple[_GuiAttemptRecord, ...],
    current_attempt: _GuiAttemptRecord | None,
    after_world: WorldObservation,
) -> tuple[PublicAttemptSignature | None, int]:
    """Return the most recent outbound attempt whose semantic origin was revisited."""

    if current_attempt is None:
        return None, 0
    returned_page_digest = public_page_semantic_digest(after_world)
    if current_attempt.page_semantic_digest == returned_page_digest:
        return None, 0
    bounded_prior = prior_attempts[-(_MAX_RECENT_GUI_ATTEMPTS - 1) :]
    for offset, attempt in enumerate(reversed(bounded_prior)):
        if attempt.page_semantic_digest == returned_page_digest:
            return attempt.signature, offset + 2
    return None, 0


def _short_gui_cycle(
    attempts: Sequence[_GuiAttemptRecord | PublicAttemptSignature],
) -> tuple[str, int]:
    """Return one phase-independent digest for any repeated suffix in the bounded window."""

    digests = tuple(
        (item.signature if isinstance(item, _GuiAttemptRecord) else item).digest
        for item in attempts[-_MAX_RECENT_GUI_ATTEMPTS:]
    )
    for period in range(2, len(digests) // 2 + 1):
        previous = digests[-period * 2 : -period]
        current = digests[-period:]
        if previous != current or len(set(current)) < 2:
            continue
        rotations = tuple(current[index:] + current[:index] for index in range(period))
        canonical = min(rotations)
        digest = "sha256:" + hashlib.sha256(_canonical_json(("effectful_gui_cycle", canonical)).encode()).hexdigest()
        return digest, period
    return "", 0


def _control_stall_instruction(result: StepResult) -> str:
    """Describe the viable next route for the typed no-progress producer."""

    if isinstance(result.decision, RequestActionPage):
        return (
            "Use a nonempty returned current control. If no returned control can advance the task, materially change "
            "the query, read relevant page content, or use an offered browser navigation action; do not repeat control "
            "discovery on the unchanged World."
        )
    if isinstance(result.decision, ReadRegionResult | SearchPageContentResult):
        return (
            "This read/search result is already present in completed tool history. Do not request the same result "
            "again: use that tool's returned next_cursor when has_more is true, inspect a different relevant region, "
            "find a current executable control, or use an offered browser navigation action."
        )
    return (
        "Use a materially different current control, relevant page content, or offered browser navigation action; "
        "do not repeat the unchanged attempt. If structural coverage is partial and the expected content is still "
        "absent, use offered entity_discovery once to inspect a visible blocker before alternate navigation."
    )


def _attempted_mode(result: StepResult) -> str:
    if isinstance(result.decision, LocalToolResult):
        return result.decision.tool_name
    if isinstance(result.decision, RequestActionPage):
        return "find_controls"
    return getattr(getattr(result.decision, "kind", None), "value", "policy_failure")


def _gui_attempt_signature(result: StepResult) -> PublicAttemptSignature | None:
    record = _gui_attempt_record(result)
    return record.signature if record is not None else None


def _gui_attempt_record(result: StepResult) -> _GuiAttemptRecord | None:
    if not isinstance(result.decision, SelectAction):
        return None
    receipts = tuple(getattr(result.execution_receipts, "receipts", ()))
    if not receipts:
        return None
    intent = receipts[-1].request.intent
    return _GuiAttemptRecord(
        public_attempt_signature(
            intent.semantic_action,
            intent.target_id,
            intent.destination_id,
            intent.parameters,
            result.before_world,
        ),
        public_page_semantic_digest(result.before_world),
    )


def _same_world_attempt_signature(result: StepResult) -> PublicAttemptSignature:
    """Return one ref-free identity for the committed attempt on the current World."""

    gui_signature = _gui_attempt_signature(result)
    if gui_signature is not None:
        return gui_signature
    decision = result.decision
    if isinstance(decision, LocalToolResult):
        if decision.rejected_attempt_signature is not None:
            return decision.rejected_attempt_signature
        operation = decision.tool_name
        parameters: Mapping[str, object] = decision.arguments
    elif isinstance(decision, RequestActionPage):
        operation = "find_controls"
        parameters = {"query": decision.query}
    elif isinstance(decision, SelectAction):
        operation = "select_action"
        parameters = {
            "action_id": decision.action_id,
            "parameters": decision.parameters,
            "destination_id": decision.destination_id,
        }
    elif isinstance(decision, RequestObservation):
        operation = "request_observation"
        parameters = {
            "purpose": decision.purpose.value,
            "subject_ids": decision.subject_ids,
            "candidate_ids": decision.candidate_ids,
            "atomic_query": decision.atomic_query,
            "predicate": decision.predicate,
            "max_results": decision.max_results,
        }
    else:
        operation = getattr(getattr(decision, "kind", None), "value", "policy_failure")
        parameters = _bounded_public_attempt(result)
    return public_attempt_signature(
        operation,
        "",
        "",
        parameters,
        result.before_world,
    )


def _gui_has_operational_result(result: StepResult) -> bool:
    outcome = result.action_outcome
    world_delta = result.public_world_delta
    assert world_delta is not None  # StepResult establishes this committed invariant.
    return bool(
        outcome is not None
        and (
            outcome.local_postcondition is LocalPostconditionStatus.SATISFIED
            or (outcome.observed_change is ObservedChange.CHANGED and world_delta.semantic_changed)
        )
    )


def _proven_failed_gui_attempt_signature(result: StepResult) -> PublicAttemptSignature | None:
    """Return an exact hard constraint only from a sent, verified stable no-effect."""

    record = _gui_attempt_record(result)
    receipts = tuple(getattr(result.execution_receipts, "receipts", ()))
    outcome = result.action_outcome
    world_delta = result.public_world_delta
    assert world_delta is not None  # StepResult establishes this committed invariant.
    if record is None or not receipts or outcome is None:
        return None
    receipt = receipts[-1]
    if (
        receipt.result.dispatch_status is not DispatchStatus.SENT
        or not receipt.result.transport_success
        or receipt.result.error is not None
        or outcome.observed_change is not ObservedChange.UNCHANGED
        or outcome.local_postcondition is not LocalPostconditionStatus.UNSATISFIED
        or outcome.evidence_method is EvidenceMethod.NONE
        or world_delta.semantic_changed
    ):
        return None
    intent = receipt.request.intent
    after_signature = public_attempt_signature(
        intent.semantic_action,
        intent.target_id,
        intent.destination_id,
        intent.parameters,
        result.after_world,
    )
    return record.signature if after_signature == record.signature else None


def _bounded_public_attempt(result: StepResult) -> Mapping[str, object]:
    if isinstance(result.decision, LocalToolResult):
        return {
            "operation": result.decision.tool_name[:80],
            "arguments": _bounded_argument_summary(result.decision.arguments),
        }
    if isinstance(result.decision, RequestActionPage):
        return {
            "operation": "find_controls",
            "arguments": {"query": result.decision.query[:160]},
        }
    return {"operation": getattr(getattr(result.decision, "kind", None), "value", "policy_failure")[:80]}


def _bounded_argument_summary(arguments: Mapping[str, object]) -> Mapping[str, object]:
    public_arguments = sanitize_history_value(arguments)
    if not isinstance(public_arguments, Mapping):
        return {}
    summary: dict[str, object] = {}
    for raw_key, value in sorted(public_arguments.items(), key=lambda item: str(item[0]))[:8]:
        key = str(raw_key)
        if isinstance(value, str):
            summary[key] = value[:160]
        elif value is None or isinstance(value, bool | int | float):
            summary[key] = value
        elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
            summary[key] = f"[{len(value)} items]"
        elif isinstance(value, Mapping):
            summary[key] = f"{{{len(value)} fields}}"
        else:
            summary[key] = type(value).__name__
    return summary


def _canonical_json(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
