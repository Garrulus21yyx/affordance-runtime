"""Information-increment monitor for bounded long-horizon episodes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.profile import DEFAULT_AGENT_LOOP_PROFILE, AgentLoopProfile
from affordance_runtime.agent.recovery import (
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    EpisodeMonitorTransition,
    RecoveryKind,
    RecoverySignal,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation.contracts import (
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest

_MAX_SAME_WORLD_CONTROL_DISCOVERY_STEPS = 2
_MAX_SHORT_GUI_CYCLE_PERIOD = 3
_MAX_RECENT_GUI_ATTEMPTS = _MAX_SHORT_GUI_CYCLE_PERIOD * 2


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
    recent_gui_attempts: tuple[PublicAttemptSignature, ...] = ()
    active_gui_cycle_digest: str = ""

    def start_episode(self, world, task_evaluation) -> None:
        del task_evaluation
        self.world_digest = public_world_semantic_digest(world)
        self.current_findings_digest = current_findings_digest(world)
        self.observation_only_streak = 0
        self.recovery_count = 0
        self.latest_attempt_signature = None
        self.same_attempt_streak = 0
        self.no_progress_count = 0
        self.recent_gui_attempts = ()
        self.active_gui_cycle_digest = ""

    def evaluate(
        self,
        result: StepResult,
        findings_digest: str,
        information_delta: InformationDelta | None = None,
    ) -> EpisodeMonitorTransition:
        """Advance only from owner-produced digests and a typed dispatch receipt."""

        if not findings_digest:
            raise ValueError("episode monitor requires a nonblank findings digest")
        next_world_digest = result.public_world_delta.after_world_digest
        if not self.world_digest:
            self.world_digest = result.public_world_delta.before_world_digest
            self.current_findings_digest = current_findings_digest(result.before_world)

        events = _diagnostic_events(result)
        information_changed = any(
            (
                next_world_digest != self.world_digest,
                findings_digest != self.current_findings_digest,
                information_delta is not None
                and information_delta.kind is InformationDeltaKind.NEW_INFORMATION,
            )
        )
        gui_dispatched = _gui_dispatched(result)
        control_discovery = isinstance(result.decision, RequestActionPage)

        self.world_digest = next_world_digest
        self.current_findings_digest = findings_digest

        if information_changed:
            events.append(EpisodeMonitorEvent.STATE_CHANGED)
        else:
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)

        # Native evaluation remains the only task-completion/impossibility authority.
        if result.task_evaluation is None:
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)
        if result.task_evaluation.status not in {
            TaskEvaluationStatus.INCOMPLETE,
            TaskEvaluationStatus.UNKNOWN,
        }:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.same_attempt_streak = 0
            self.recent_gui_attempts = ()
            self.active_gui_cycle_digest = ""
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        gui_signature = _gui_attempt_signature(result) if gui_dispatched else None
        cycle_digest, cycle_period = self._record_gui_attempt(gui_signature)
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
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys((*events, EpisodeMonitorEvent.OSCILLATION))),
                EpisodeMonitorRecommendation.BLOCK if repeated_cycle else EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.STATE_OSCILLATION.value,
                signal,
            )
        if gui_signature is not None:
            self.active_gui_cycle_digest = ""

        if information_changed:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = None
            self.same_attempt_streak = 0
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        if gui_dispatched and _gui_has_operational_result(result):
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = None
            self.same_attempt_streak = 0
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        if self.recovery_count and result.feedback == "recovery_repeat_rejected":
            signal = _control_stall_signal(result, self, recovery_attempt=self.recovery_count)
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
                EpisodeMonitorRecommendation.BLOCK,
                "control_stalled",
                signal,
            )

        exact_replay = bool(
            information_delta is not None
            and information_delta.kind is InformationDeltaKind.EXACT_REPLAY
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
                return EpisodeMonitorTransition(
                    tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
                    EpisodeMonitorRecommendation.BLOCK,
                    "control_stalled",
                    signal,
                )
            self.recovery_count = 0
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys(events)),
                EpisodeMonitorRecommendation.CONTINUE,
            )

        recovery_due = any(
            (
                exact_replay,
                gui_dispatched and self.same_attempt_streak >= 2,
                control_discovery
                and self.observation_only_streak >= _MAX_SAME_WORLD_CONTROL_DISCOVERY_STEPS,
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
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
            EpisodeMonitorRecommendation.RECOVER,
            RecoveryKind.CONTROL_STALL.value,
            signal,
        )

    def _record_gui_attempt(
        self,
        signature: PublicAttemptSignature | None,
    ) -> tuple[str, int]:
        """Record bounded effectful attempts and identify a repeated short cycle."""

        if signature is None:
            return "", 0
        self.recent_gui_attempts = (*self.recent_gui_attempts, signature)[-_MAX_RECENT_GUI_ATTEMPTS:]
        return _short_gui_cycle(self.recent_gui_attempts)


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
        batch is not None
        and any(item.result.dispatch_status is not DispatchStatus.NOT_SENT for item in batch.receipts)
    )


def _control_stall_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    recovery_attempt: int,
) -> RecoverySignal:
    prohibited_attempt_signature = (
        monitor.latest_attempt_signature
        if result.feedback == "recovery_repeat_rejected"
        and monitor.latest_attempt_signature is not None
        else _same_world_attempt_signature(result)
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
            "dispatch": "not_sent",
            "observation_only_streak": monitor.observation_only_streak,
            "world_digest": monitor.world_digest,
            "current_findings_digest": monitor.current_findings_digest,
        },
        attempted_modes=(_attempted_mode(result),),
        prohibited_attempt_signature=prohibited_attempt_signature,
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
            "dispatch": "sent",
            "cycle_period": cycle_period,
            "world_digest": monitor.world_digest,
            "current_findings_digest": monitor.current_findings_digest,
        },
        attempted_modes=(_attempted_mode(result),),
        prohibited_attempt_signature=monitor.latest_attempt_signature,
        human_instruction=(
            "Recent effectful GUI attempts repeated a short cycle across fresh Worlds. Preserve completed results "
            "already present in tool history and choose an offered action outside this cycle toward an unresolved "
            "requirement; do not revisit the same sequence merely to re-verify it."
        ),
        recovery_attempt=recovery_attempt,
    )


def _short_gui_cycle(
    attempts: tuple[PublicAttemptSignature, ...],
) -> tuple[str, int]:
    """Return one phase-independent digest for a repeated period-2/3 suffix."""

    digests = tuple(item.digest for item in attempts)
    for period in range(2, _MAX_SHORT_GUI_CYCLE_PERIOD + 1):
        if len(digests) < period * 2:
            continue
        previous = digests[-period * 2 : -period]
        current = digests[-period:]
        if previous != current or len(set(current)) < 2:
            continue
        rotations = tuple(current[index:] + current[:index] for index in range(period))
        canonical = min(rotations)
        digest = "sha256:" + hashlib.sha256(
            _canonical_json(("effectful_gui_cycle", canonical)).encode()
        ).hexdigest()
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
        "do not repeat the unchanged attempt."
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
            "purpose": decision.purpose,
            "subject_id": decision.subject_id,
            "evidence_property": decision.evidence_property,
            "cursor": decision.cursor,
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
    return bool(
        outcome is not None
        and (
            outcome.observed_change is ObservedChange.CHANGED
            or outcome.local_postcondition is LocalPostconditionStatus.SATISFIED
        )
    )


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
