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
from affordance_runtime.agent.decisions import LocalToolResult, RequestActionPage, RequestObservation, SelectAction
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
from affordance_runtime.agent.workspace import AgentWorkspace, working_facts_digest
from affordance_runtime.evaluation.contracts import (
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest


@dataclass
class EpisodeMonitor:
    """Own one no-progress state machine; query and region identities are not progress."""

    profile: AgentLoopProfile = DEFAULT_AGENT_LOOP_PROFILE
    world_digest: str = ""
    current_findings_digest: str = ""
    working_facts_digest: str = ""
    observation_only_streak: int = 0
    recovery_count: int = 0
    latest_attempt_signature: PublicAttemptSignature | None = None
    same_attempt_streak: int = 0
    no_progress_count: int = 0

    def start_episode(self, world, task_evaluation, working_facts=()) -> None:
        del task_evaluation
        workspace = AgentWorkspace(working_facts=tuple(working_facts))
        self.world_digest = public_world_semantic_digest(world)
        self.current_findings_digest = current_findings_digest(world)
        self.working_facts_digest = working_facts_digest(workspace)
        self.observation_only_streak = 0
        self.recovery_count = 0
        self.latest_attempt_signature = None
        self.same_attempt_streak = 0
        self.no_progress_count = 0

    def evaluate(
        self,
        result: StepResult,
        findings_digest: str,
        facts_digest: str,
        information_delta: InformationDelta | None = None,
    ) -> EpisodeMonitorTransition:
        """Advance only from owner-produced digests and a typed dispatch receipt."""

        if not findings_digest or not facts_digest:
            raise ValueError("episode monitor requires nonblank owner digests")
        next_world_digest = result.public_world_delta.after_world_digest
        if not self.world_digest:
            self.world_digest = result.public_world_delta.before_world_digest
            self.current_findings_digest = current_findings_digest(result.before_world)
            self.working_facts_digest = facts_digest

        events = _diagnostic_events(result)
        information_changed = any(
            (
                next_world_digest != self.world_digest,
                findings_digest != self.current_findings_digest,
                facts_digest != self.working_facts_digest,
                information_delta is not None
                and information_delta.kind is InformationDeltaKind.NEW_INFORMATION,
            )
        )
        gui_dispatched = _gui_dispatched(result)

        self.world_digest = next_world_digest
        self.current_findings_digest = findings_digest
        self.working_facts_digest = facts_digest

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
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        if information_changed:
            self.observation_only_streak = 0
            self.recovery_count = 0
            self.latest_attempt_signature = None
            self.same_attempt_streak = 0
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        if gui_dispatched:
            self.observation_only_streak = 0
            signature = _gui_attempt_signature(result)
            if _gui_has_operational_result(result) or signature is None:
                self.latest_attempt_signature = None
                self.same_attempt_streak = 0
                return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)
            self.no_progress_count += 1
            self.same_attempt_streak = (
                self.same_attempt_streak + 1
                if signature == self.latest_attempt_signature
                else 1
            )
            self.latest_attempt_signature = signature
            if self.recovery_count:
                signal = _control_stall_signal(result, self, recovery_attempt=self.recovery_count)
                return EpisodeMonitorTransition(
                    tuple(dict.fromkeys(events)),
                    EpisodeMonitorRecommendation.BLOCK,
                    "control_stalled",
                    signal,
                )
            if self.same_attempt_streak < 2:
                return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)
            self.recovery_count += 1
            signal = _control_stall_signal(result, self, recovery_attempt=self.recovery_count)
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.CONTROL_STALL.value,
                signal,
            )

        if information_delta is not None and information_delta.kind is InformationDeltaKind.EXACT_REPLAY:
            self.observation_only_streak = 0
            self.no_progress_count += 1
            self.same_attempt_streak += 1
            signal = _control_stall_signal(result, self, recovery_attempt=max(1, self.recovery_count + 1))
            if self.recovery_count:
                return EpisodeMonitorTransition(
                    tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
                    EpisodeMonitorRecommendation.BLOCK,
                    "control_stalled",
                    signal,
                )
            self.recovery_count = 1
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
                EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.CONTROL_STALL.value,
                signal,
            )

        if self.recovery_count:
            signal = _control_stall_signal(result, self, recovery_attempt=self.recovery_count)
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys(events)),
                EpisodeMonitorRecommendation.BLOCK,
                "control_stalled",
                signal,
            )
        self.observation_only_streak += 1
        if self.observation_only_streak < self.profile.max_consecutive_observation_only:
            return EpisodeMonitorTransition(tuple(dict.fromkeys(events)), EpisodeMonitorRecommendation.CONTINUE)

        if self.recovery_count >= self.profile.max_recoveries_per_stall:
            return EpisodeMonitorTransition(
                tuple(dict.fromkeys(events)),
                EpisodeMonitorRecommendation.BLOCK,
                "control_stalled",
            )
        self.recovery_count += 1
        self.observation_only_streak = 0
        signal = _control_stall_signal(result, self, recovery_attempt=self.recovery_count)
        return EpisodeMonitorTransition(
            tuple(dict.fromkeys((*events, EpisodeMonitorEvent.REPEATED_ACTION))),
            EpisodeMonitorRecommendation.RECOVER,
            RecoveryKind.CONTROL_STALL.value,
            signal,
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
        batch is not None
        and any(item.result.dispatch_status is not DispatchStatus.NOT_SENT for item in batch.receipts)
    )


def _control_stall_signal(
    result: StepResult,
    monitor: EpisodeMonitor,
    *,
    recovery_attempt: int,
) -> RecoverySignal:
    prohibited_attempt_signature = _gui_attempt_signature(result) or _prohibited_attempt_signature(result)
    signature_payload: tuple[object, ...] = (
        monitor.world_digest,
        monitor.current_findings_digest,
        monitor.working_facts_digest,
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
            "working_facts_digest": monitor.working_facts_digest,
        },
        attempted_modes=(_attempted_mode(result),),
        prohibited_attempt_signature=prohibited_attempt_signature,
        human_instruction="Change strategy or dispatch a grounded GUI action; another observation without new information will stall.",
        recovery_attempt=recovery_attempt,
    )


def _attempted_mode(result: StepResult) -> str:
    if isinstance(result.decision, LocalToolResult):
        return result.decision.tool_name
    if isinstance(result.decision, RequestActionPage):
        return "find_controls"
    return getattr(getattr(result.decision, "kind", None), "value", "policy_failure")


def _prohibited_attempt_signature(result: StepResult):
    if isinstance(result.decision, LocalToolResult):
        return result.decision.rejected_attempt_signature
    return None


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
