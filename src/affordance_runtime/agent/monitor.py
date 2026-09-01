"""Information-increment monitor for bounded long-horizon episodes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from affordance_runtime.agent.attempt_signature import (
    PublicAttemptSignature,
    public_attempt_signature,
    public_local_result_attempt_signature,
    public_observation_attempt_signature,
)
from affordance_runtime.agent.context.contracts import sanitize_history_arguments
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
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest

_MAX_SAME_WORLD_CONTROL_DISCOVERY_STEPS = 2
_MAX_RECENT_TRANSITIONS = 16


@dataclass(frozen=True)
class _TransitionRecord:
    signature: PublicAttemptSignature
    result_world_digest: str

    @property
    def digest(self) -> str:
        """Identify one attempted transition together with its actual result."""

        return (
            "sha256:"
            + hashlib.sha256(
                _canonical_json(("decision_transition", self.signature.digest, self.result_world_digest)).encode()
            ).hexdigest()
        )


@dataclass(frozen=True)
class _ActiveTransitionCycle:
    digest: str
    period: int
    member_digests: frozenset[str]


@dataclass
class EpisodeMonitor:
    """Own one no-progress state machine; query and region identities are not progress."""

    profile: AgentLoopProfile = DEFAULT_AGENT_LOOP_PROFILE
    world_digest: str = ""
    current_findings_digest: str = ""
    observation_only_streak: int = 0
    recovery_count: int = 0
    latest_attempt_signature: PublicAttemptSignature | None = None
    same_attempt_streak: int = 0
    no_progress_count: int = 0
    recent_transitions: tuple[_TransitionRecord, ...] = ()
    active_transition_cycle: _ActiveTransitionCycle | None = None
    active_recovery: RecoverySignal | None = None
    recovery_epoch_counter: int = 0

    def start_episode(self, world, task_evaluation) -> None:
        del task_evaluation
        self.world_digest = public_world_semantic_digest(world)
        self.current_findings_digest = current_findings_digest(world)
        self.observation_only_streak = 0
        self.recovery_count = 0
        self.latest_attempt_signature = None
        self.same_attempt_streak = 0
        self.no_progress_count = 0
        self.recent_transitions = ()
        self.active_transition_cycle = None
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
        """Restore one unconsumed next-decision signal at a pause boundary."""

        self.start_episode(world, task_evaluation)
        if recovery_signal is None:
            return
        self.active_recovery = recovery_signal
        self.recovery_count = recovery_signal.recovery_attempt
        self.latest_attempt_signature = (
            recovery_signal.prohibited_attempt_signatures[-1] if recovery_signal.prohibited_attempt_signatures else None
        )
        self.same_attempt_streak = int(self.latest_attempt_signature is not None)
        cycle_state = recovery_signal.monitor_state
        member_digests = tuple(cycle_state.get("cycle_member_digests", ()))
        cycle_digest = str(cycle_state.get("cycle_digest", ""))
        cycle_period = cycle_state.get("cycle_period", 0)
        if (
            recovery_signal.kind is RecoveryKind.STATE_OSCILLATION
            and cycle_digest.startswith("sha256:")
            and type(cycle_period) is int
            and cycle_period >= 1
            and member_digests
            and all(isinstance(item, str) and item.startswith("sha256:") for item in member_digests)
        ):
            self.active_transition_cycle = _ActiveTransitionCycle(
                cycle_digest,
                cycle_period,
                frozenset(member_digests),
            )
        parts = recovery_signal.epoch_id.split(":", 2)
        if len(parts) == 3 and parts[1].isdigit():
            self.recovery_epoch_counter = int(parts[1])

    def _open_recovery(
        self,
        candidate: RecoverySignal,
    ) -> RecoverySignal:
        """Install one signal for exactly the next ActionPolicy decision."""

        if self.active_recovery is not None:
            raise RuntimeError("cannot open a second unconsumed recovery signal")
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
        return signal

    def _recovery_transition(
        self,
        events: Sequence[EpisodeMonitorEvent],
        recommendation: EpisodeMonitorRecommendation,
        reason: str,
        candidate: RecoverySignal,
    ) -> EpisodeMonitorTransition:
        signal = self._open_recovery(candidate)
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys(events)),
            recommendation,
            reason,
            signal,
            RecoveryLifecycleTransition.STARTED,
        )

    def _continue_or_close(
        self,
        events: Sequence[EpisodeMonitorEvent],
        consumed_recovery: RecoverySignal | None,
    ) -> EpisodeMonitorTransition:
        if consumed_recovery is not None:
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys(events)),
                EpisodeMonitorRecommendation.CONTINUE,
                "recovery_consumed",
                None,
                RecoveryLifecycleTransition.CLOSED,
            )
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys(events)),
            EpisodeMonitorRecommendation.CONTINUE,
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
        # The signal visible to the just-completed ActionPolicy decision is now
        # consumed.  Any next signal must be justified independently by this
        # latest transition; stale recovery facts never carry across steps.
        consumed_recovery = self.active_recovery
        self.active_recovery = None
        self.recovery_count = 0
        world_delta = result.public_world_delta
        assert world_delta is not None  # StepResult establishes this committed invariant.
        next_world_digest = world_delta.after_world_digest
        if not self.world_digest:
            self.world_digest = world_delta.before_world_digest
            self.current_findings_digest = current_findings_digest(result.before_world)

        events = _diagnostic_events(result)
        world_semantic_changed = next_world_digest != self.world_digest
        state_changed = any(
            (
                world_semantic_changed,
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
            return self._continue_or_close(events, consumed_recovery)
        if result.task_evaluation.status not in {
            TaskEvaluationStatus.INCOMPLETE,
            TaskEvaluationStatus.UNKNOWN,
        }:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.same_attempt_streak = 0
            self.recent_transitions = ()
            self.active_transition_cycle = None
            return self._continue_or_close(events, consumed_recovery)

        if consumed_recovery is not None and result.feedback == "recovery_repeat_rejected":
            rejected_signature = _rejected_attempt_signature(result)
            signature = rejected_signature or _same_world_attempt_signature(result)
            repeats_latest = signature == self.latest_attempt_signature
            self.no_progress_count += 1
            self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
            self.latest_attempt_signature = signature
            self.recovery_count = min(consumed_recovery.recovery_attempt + 1, 3)
            signal = _control_stall_signal(
                result,
                self,
                recovery_attempt=self.recovery_count,
                prohibited_attempt_signature=rejected_signature,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.REPEATED_ACTION),
                EpisodeMonitorRecommendation.BLOCK,
                "control_stalled",
                signal,
            )

        if isinstance(result.decision, ToolRejectedResult):
            signature = _same_world_attempt_signature(result)
            repeats_latest = signature == self.latest_attempt_signature
            self.no_progress_count += 1
            self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
            self.latest_attempt_signature = signature
            self.recovery_count = 1
            signal = _control_stall_signal(
                result,
                self,
                recovery_attempt=self.recovery_count,
                prohibited_attempt_signature=result.decision.rejected_attempt_signature,
            )
            if consumed_recovery is not None and repeats_latest:
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

        transition_signature = _same_world_attempt_signature(result)
        transition_record = _TransitionRecord(transition_signature, next_world_digest)
        active_cycle = self.active_transition_cycle
        if active_cycle is not None and transition_record.digest not in active_cycle.member_digests:
            # One materially different transition/result is the mechanical
            # escape condition.  Merely consuming the one-turn feedback is not.
            self.active_transition_cycle = None
            active_cycle = None
        elif active_cycle is not None and consumed_recovery is not None:
            self.no_progress_count += 1
            self.latest_attempt_signature = transition_signature
            self.recovery_count = 2
            signal = _transition_cycle_recovery_signal(
                result,
                self,
                cycle=active_cycle,
                recovery_attempt=2,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.OSCILLATION),
                EpisodeMonitorRecommendation.BLOCK,
                "control_stalled",
                signal,
            )
        repeated_transition_result, cycle = self._record_transition(transition_record)
        gui_signature = _gui_attempt_signature(result) if gui_dispatched else None

        if repeated_transition_result and world_semantic_changed:
            self.observation_only_streak = 0
            self.no_progress_count += 1
            self.same_attempt_streak = 1
            self.latest_attempt_signature = transition_signature
            recurrence = _transition_recurrence(transition_record)
            repeated_cycle = active_cycle is not None and active_cycle.digest == recurrence.digest
            self.active_transition_cycle = recurrence
            self.recovery_count = 2 if repeated_cycle else 1
            signal = _transition_cycle_recovery_signal(
                result,
                self,
                cycle=recurrence,
                recovery_attempt=self.recovery_count,
                repeated_result_world=True,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.OSCILLATION),
                EpisodeMonitorRecommendation.BLOCK if repeated_cycle else EpisodeMonitorRecommendation.RECOVER,
                "control_stalled" if repeated_cycle else RecoveryKind.STATE_OSCILLATION.value,
                signal,
            )
        if cycle is not None:
            self.observation_only_streak = 0
            self.no_progress_count += 1
            self.same_attempt_streak = 1
            self.latest_attempt_signature = transition_signature
            repeated_cycle = active_cycle is not None and cycle.digest == active_cycle.digest
            self.active_transition_cycle = cycle
            signal = _transition_cycle_recovery_signal(
                result,
                self,
                cycle=cycle,
                recovery_attempt=2 if repeated_cycle else 1,
            )
            return self._recovery_transition(
                (*events, EpisodeMonitorEvent.OSCILLATION),
                EpisodeMonitorRecommendation.BLOCK if repeated_cycle else EpisodeMonitorRecommendation.RECOVER,
                "control_stalled" if repeated_cycle else RecoveryKind.STATE_OSCILLATION.value,
                signal,
            )

        if durable_progress:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = None
            self.same_attempt_streak = 0
            return self._continue_or_close(events, consumed_recovery)

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
            return self._continue_or_close(events, consumed_recovery)

        signature = _same_world_attempt_signature(result)
        repeats_latest = signature == self.latest_attempt_signature
        exact_replay = _has_exact_local_result_replay(
            result,
            information_delta,
            repeats_latest=repeats_latest,
        )
        self.no_progress_count += 1
        self.same_attempt_streak = self.same_attempt_streak + 1 if repeats_latest else 1
        self.latest_attempt_signature = signature
        if gui_dispatched or exact_replay:
            self.observation_only_streak = 0
        else:
            self.observation_only_streak += 1

        recovery_due = any(
            (
                exact_replay,
                consumed_recovery is not None and repeats_latest,
                information_delta is not None and information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION,
                information_delta is not None
                and information_delta.kind is InformationDeltaKind.NO_USABLE_INFORMATION
                and self.observation_only_streak >= 2,
                gui_dispatched and self.same_attempt_streak >= 2,
                control_discovery and self.observation_only_streak >= _MAX_SAME_WORLD_CONTROL_DISCOVERY_STEPS,
                not gui_dispatched
                and not control_discovery
                and not exact_replay
                and self.observation_only_streak >= self.profile.max_consecutive_observation_only,
            )
        )
        if not recovery_due:
            return self._continue_or_close(events, consumed_recovery)

        self.recovery_count = 1
        self.observation_only_streak = 0
        no_usable_observation = bool(
            information_delta is not None and information_delta.kind is InformationDeltaKind.NO_USABLE_INFORMATION
        )
        signal = _control_stall_signal(
            result,
            self,
            recovery_attempt=1,
            prohibited_attempt_signature=(
                signature
                if exact_replay
                or no_usable_observation
                or (consumed_recovery is not None and repeats_latest)
                or (gui_dispatched and repeats_latest)
                else None
            ),
        )
        prohibited_by_consumed = bool(
            consumed_recovery is not None
            and signature is not None
            and signature in consumed_recovery.prohibited_attempt_signatures
        )
        return self._recovery_transition(
            (*events, EpisodeMonitorEvent.REPEATED_ACTION),
            EpisodeMonitorRecommendation.BLOCK if prohibited_by_consumed else EpisodeMonitorRecommendation.RECOVER,
            "control_stalled" if prohibited_by_consumed else RecoveryKind.CONTROL_STALL.value,
            signal,
        )

    def _record_transition(
        self,
        record: _TransitionRecord,
    ) -> tuple[bool, _ActiveTransitionCycle | None]:
        """Record one mixed decision transition and find bounded recurrence/cycles."""

        repeated_result = any(
            item.signature.digest == record.signature.digest and item.result_world_digest == record.result_world_digest
            for item in self.recent_transitions
        )
        self.recent_transitions = (*self.recent_transitions, record)[-_MAX_RECENT_TRANSITIONS:]
        return repeated_result, _short_transition_cycle(self.recent_transitions)


def _has_exact_local_result_replay(
    result: StepResult,
    information_delta: InformationDelta | None,
    *,
    repeats_latest: bool,
) -> bool:
    if information_delta is not None and information_delta.kind is InformationDeltaKind.EXACT_REPLAY:
        return True
    return bool(
        repeats_latest and isinstance(result.decision, RequestActionPage) and result.action_page_result is not None
    )


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


def _control_stall_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    recovery_attempt: int,
    prohibited_attempt_signature: PublicAttemptSignature | None = None,
) -> RecoverySignal:
    prohibited_attempt_signature = (
        prohibited_attempt_signature
        or _rejected_attempt_signature(result)
        or _proven_failed_gui_attempt_signature(result)
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


def _transition_cycle_recovery_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    cycle: _ActiveTransitionCycle,
    recovery_attempt: int,
    repeated_result_world: bool = False,
) -> RecoverySignal:
    """Report a mechanical mixed-transition cycle without judging task progress."""

    return RecoverySignal(
        RecoveryKind.STATE_OSCILLATION,
        "state_oscillation:" + cycle.digest,
        {
            "attempt": _bounded_public_attempt(result),
            "dispatch": _dispatch_status(result),
            "cycle_period": cycle.period,
            "repeated_result_world": repeated_result_world,
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
            "Recent decisions repeated the same bounded transition cycle or returned to an already-seen result. "
            "Preserve completed results already present in tool history and choose an offered transition outside "
            "this cycle toward an unresolved requirement; do not revisit it merely to re-verify it."
        ),
        recovery_attempt=recovery_attempt,
        monitor_state={
            "cycle_digest": cycle.digest,
            "cycle_period": cycle.period,
            "cycle_member_digests": tuple(sorted(cycle.member_digests)),
        },
    )


def _transition_recurrence(record: _TransitionRecord) -> _ActiveTransitionCycle:
    digest = (
        "sha256:"
        + hashlib.sha256(
            _canonical_json(
                ("transition_result_recurrence", record.signature.digest, record.result_world_digest)
            ).encode()
        ).hexdigest()
    )
    return _ActiveTransitionCycle(digest, 1, frozenset((record.digest,)))


def _short_transition_cycle(
    attempts: Sequence[_TransitionRecord | PublicAttemptSignature],
) -> _ActiveTransitionCycle | None:
    """Return one phase-independent digest for any repeated suffix in the bounded window."""

    digests = tuple(item.digest for item in attempts[-_MAX_RECENT_TRANSITIONS:])
    for period in range(2, len(digests) // 2 + 1):
        previous = digests[-period * 2 : -period]
        current = digests[-period:]
        if previous != current or len(set(current)) < 2:
            continue
        rotations = tuple(current[index:] + current[:index] for index in range(period))
        canonical = min(rotations)
        digest = (
            "sha256:" + hashlib.sha256(_canonical_json(("decision_transition_cycle", canonical)).encode()).hexdigest()
        )
        return _ActiveTransitionCycle(digest, period, frozenset(current))
    return None


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
            "This read/search added no semantic record that is not already present in completed tool history. "
            "Preserve and use that evidence instead of reopening it for verification. If the requested output is "
            "already supported, finish; otherwise choose one materially different current route for a specific "
            "missing output. Follow continuation.cursor only when has_more is true, and stop with a typed no-progress outcome "
            "when no materially new route remains."
        )
    if isinstance(result.decision, RequestObservation):
        return (
            "The latest perception produced no new usable public fact; its typed unknown/failure reason is route "
            "evidence, not a task answer. Do not paraphrase the same perception request on the unchanged World. "
            "Use one materially different acquisition route, first reveal the target with an offered GUI action, "
            "finish when existing evidence is sufficient, or return a typed no-progress outcome when routes are "
            "exhausted."
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
    if not isinstance(result.decision, SelectAction):
        return None
    receipts = tuple(getattr(result.execution_receipts, "receipts", ()))
    if not receipts:
        return None
    intent = receipts[-1].request.intent
    return public_attempt_signature(
        intent.semantic_action,
        intent.target_id,
        intent.destination_id,
        intent.parameters,
        result.before_world,
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
        return public_local_result_attempt_signature(
            decision.tool_name,
            decision.arguments,
            decision.result,
            result.after_world,
        )
    elif isinstance(decision, RequestActionPage):
        if result.action_page_result is not None:
            return public_local_result_attempt_signature(
                "find_controls",
                {"query": decision.query},
                result.action_page_result.to_public_value(),
                result.after_world,
            )
        operation = "find_controls"
        parameters: Mapping[str, object] = {"query": decision.query}
    elif isinstance(decision, SelectAction):
        operation = "select_action"
        parameters = {
            "action_id": decision.action_id,
            "parameters": decision.parameters,
            "destination_id": decision.destination_id,
        }
    elif isinstance(decision, RequestObservation):
        return public_observation_attempt_signature(
            purpose=decision.purpose.value,
            subject_ids=decision.subject_ids,
            candidate_ids=decision.candidate_ids,
            atomic_query=decision.atomic_query,
            predicate=decision.predicate,
            max_results=decision.max_results,
            world=result.before_world,
        )
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


def _rejected_attempt_signature(result: StepResult) -> PublicAttemptSignature | None:
    decision = result.decision
    return decision.rejected_attempt_signature if isinstance(decision, ToolRejectedResult) else None


def _gui_has_operational_result(result: StepResult) -> bool:
    outcome = result.action_outcome
    world_delta = result.public_world_delta
    assert world_delta is not None  # StepResult establishes this committed invariant.
    return bool(
        outcome is not None
        and outcome.observed_change is ObservedChange.CHANGED
        and (outcome.local_postcondition is LocalPostconditionStatus.SATISFIED or world_delta.semantic_changed)
    )


def _proven_failed_gui_attempt_signature(result: StepResult) -> PublicAttemptSignature | None:
    """Return an exact hard constraint only from a sent, verified stable no-effect."""

    record = _gui_attempt_signature(result)
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
    return record if after_signature == record else None


def _bounded_public_attempt(result: StepResult) -> Mapping[str, object]:
    if isinstance(result.decision, LocalToolResult):
        return {
            "operation": result.decision.tool_name[:80],
            "arguments": _bounded_argument_summary(
                result.decision.arguments,
                ephemeral_paths=result.decision.ephemeral_argument_paths,
            ),
        }
    if isinstance(result.decision, RequestActionPage):
        return {
            "operation": "find_controls",
            "arguments": {"query": result.decision.query[:160]},
        }
    return {"operation": getattr(getattr(result.decision, "kind", None), "value", "policy_failure")[:80]}


def _bounded_argument_summary(
    arguments: Mapping[str, object],
    *,
    ephemeral_paths: tuple[tuple[str, ...], ...] = (),
) -> Mapping[str, object]:
    public_arguments = sanitize_history_arguments(arguments, ephemeral_paths=ephemeral_paths)
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
