"""Deterministic episode monitor for bounded long-horizon episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.decisions import RequestObservation, SelectAction
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation.contracts import (
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluationStatus,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import (
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    EpisodeMonitorTransition,
)

_WORLD_OSCILLATION_WINDOW = 4


@dataclass(frozen=True)
class EpisodeMonitorConfig:
    repeated_action_threshold: int = 2
    no_change_threshold: int = 3

    def __post_init__(self) -> None:
        if self.repeated_action_threshold < 1 or self.no_change_threshold < 1:
            raise ValueError("episode monitor thresholds must be positive")


@dataclass(frozen=True)
class EpisodeMonitor:
    config: EpisodeMonitorConfig = EpisodeMonitorConfig()

    def evaluate(
        self,
        result: StepResult,
        recent_steps: tuple[AgentTurnView, ...],
        fresh_world_fingerprint: str,
    ) -> EpisodeMonitorTransition:
        events: list[EpisodeMonitorEvent] = []
        if isinstance(result.decision, PolicyFailure):
            events.append(EpisodeMonitorEvent.PROVIDER_FAILURE)
            return EpisodeMonitorTransition(
                tuple(events),
                EpisodeMonitorRecommendation.YIELD,
                "stalled",
            )
        if result.runtime_failure is not None:
            events.append(EpisodeMonitorEvent.ENVIRONMENT_FAILURE)
            return EpisodeMonitorTransition(
                tuple(events),
                EpisodeMonitorRecommendation.YIELD,
                "stalled",
            )
        if isinstance(result.decision, RequestObservation) and result.feedback.startswith("observation_unavailable"):
            events.append(EpisodeMonitorEvent.CAPABILITY_GAP)
            return EpisodeMonitorTransition(
                tuple(events),
                EpisodeMonitorRecommendation.YIELD,
                "capability_gap",
            )
        action = result.action_outcome
        if action is not None and (
            action.observed_change is ObservedChange.CHANGED
            or action.local_postcondition
            in {LocalPostconditionStatus.SATISFIED, LocalPostconditionStatus.UNSATISFIED}
        ):
            events.append(EpisodeMonitorEvent.STATE_CHANGED)
        elif action is not None and action.observed_change is ObservedChange.UNCHANGED:
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)
        if result.task_evaluation.status is not TaskEvaluationStatus.UNKNOWN:
            events.append(EpisodeMonitorEvent.FORMAL_CRITERION_CHANGED)
        if isinstance(result.decision, SelectAction):
            current_key = _action_key(result)
            previous = tuple(
                _turn_key(item)
                for item in recent_steps[-self.config.repeated_action_threshold :]
            )
            previous_semantic = tuple(
                item.semantic_action for item in recent_steps[-self.config.repeated_action_threshold :]
            )
            current_semantic = _semantic_action(result)
            if previous and all(item == current_key for item in previous):
                events.append(EpisodeMonitorEvent.REPEATED_ACTION)
            elif (
                current_semantic
                and previous_semantic
                and all(item == current_semantic for item in previous_semantic)
                and EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events
            ):
                events.append(EpisodeMonitorEvent.REPEATED_ACTION)
            if (
                len(previous) >= self.config.repeated_action_threshold
                and len(set(previous + (current_key,))) <= 2
                and EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events
            ):
                events.append(EpisodeMonitorEvent.OSCILLATION)
            if _returns_to_recent_world(recent_steps, fresh_world_fingerprint):
                events.append(EpisodeMonitorEvent.OSCILLATION)
        if _unchanged_streak(recent_steps) + int(EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events) >= self.config.no_change_threshold:
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)
            events.append(EpisodeMonitorEvent.REPEATED_ACTION)
        if EpisodeMonitorEvent.OSCILLATION in events:
            return EpisodeMonitorTransition(tuple(events), EpisodeMonitorRecommendation.YIELD, "oscillation")
        if EpisodeMonitorEvent.REPEATED_ACTION in events:
            return EpisodeMonitorTransition(tuple(events), EpisodeMonitorRecommendation.YIELD, "stalled")
        return EpisodeMonitorTransition(tuple(events), EpisodeMonitorRecommendation.CONTINUE)


def _action_key(result: StepResult) -> str:
    if result.execution is None:
        return type(result.decision).__name__
    intent = result.execution.request.intent
    payload = {
        "action": intent.semantic_action,
        "target": intent.target_id,
        "destination": intent.destination_id,
        "parameters": to_json_compatible(intent.parameters),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _semantic_action(result: StepResult) -> str:
    if result.execution is None:
        return ""
    return result.execution.request.intent.semantic_action


def _turn_key(turn: AgentTurnView) -> str:
    payload = {
        "action": turn.semantic_action,
        "target": getattr(turn.target, "label", "") if turn.target is not None else "",
        "destination": getattr(turn.destination, "label", "") if turn.destination is not None else "",
        "parameters": to_json_compatible(turn.public_parameters),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _returns_to_recent_world(recent_steps: tuple[AgentTurnView, ...], fresh_world_fingerprint: str) -> bool:
    if not fresh_world_fingerprint:
        return False
    seen = []
    for step in recent_steps[-_WORLD_OSCILLATION_WINDOW:]:
        before = step.transition.get("before_world")
        after = step.transition.get("after_world")
        for value in (before, after):
            if isinstance(value, str) and value and value not in seen:
                seen.append(value)
    return len(seen) >= 2 and fresh_world_fingerprint in set(seen[:-1])


def _unchanged_streak(recent_steps: tuple[AgentTurnView, ...]) -> int:
    streak = 0
    for step in reversed(recent_steps):
        transition = step.transition
        if transition.get("observed_change") not in {"unchanged", "no_effect"}:
            break
        streak += 1
    return streak
