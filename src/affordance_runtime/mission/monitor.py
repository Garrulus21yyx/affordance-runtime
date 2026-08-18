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
    TaskEvaluation,
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
    repeated_failure_limit: int = 3

    def __post_init__(self) -> None:
        if (
            self.repeated_action_threshold < 1
            or self.no_change_threshold < 1
            or self.repeated_failure_limit < 1
        ):
            raise ValueError("episode monitor thresholds must be positive")


@dataclass
class EpisodeMonitor:
    config: EpisodeMonitorConfig = EpisodeMonitorConfig()
    repeated_failure_key: str = ""
    repeated_failure_count: int = 0

    def evaluate(
        self,
        result: StepResult,
        recent_steps: tuple[AgentTurnView, ...],
        fresh_world_fingerprint: str,
    ) -> EpisodeMonitorTransition:
        events: list[EpisodeMonitorEvent] = []
        if isinstance(result.decision, PolicyFailure):
            events.append(EpisodeMonitorEvent.PROVIDER_FAILURE)
        elif result.runtime_failure is not None:
            events.append(EpisodeMonitorEvent.ENVIRONMENT_FAILURE)
        elif isinstance(result.decision, RequestObservation) and result.feedback.startswith("observation_unavailable"):
            events.append(EpisodeMonitorEvent.CAPABILITY_GAP)
        action = result.action_outcome
        if action is not None and (
            action.observed_change is ObservedChange.CHANGED
            or action.local_postcondition
            in {LocalPostconditionStatus.SATISFIED, LocalPostconditionStatus.UNSATISFIED}
        ):
            events.append(EpisodeMonitorEvent.STATE_CHANGED)
        elif action is not None and action.observed_change is ObservedChange.UNCHANGED:
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)
        if result.task_evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
            events.append(EpisodeMonitorEvent.FORMAL_CRITERION_CHANGED)
        failure_key = _repeated_failure_key(result, events, fresh_world_fingerprint)
        if failure_key:
            if failure_key == self.repeated_failure_key:
                self.repeated_failure_count += 1
            else:
                self.repeated_failure_key = failure_key
                self.repeated_failure_count = 1
            if self.repeated_failure_count >= self.config.repeated_failure_limit:
                return EpisodeMonitorTransition(
                    tuple(events),
                    EpisodeMonitorRecommendation.YIELD,
                    "repeated_failure_limit",
                )
        else:
            self.repeated_failure_key = ""
            self.repeated_failure_count = 0
        action_failed_or_unchanged = _action_failed_or_unchanged(result, events)
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
            if action_failed_or_unchanged and previous and all(item == current_key for item in previous):
                events.append(EpisodeMonitorEvent.REPEATED_ACTION)
            elif (
                action_failed_or_unchanged
                and current_semantic
                and previous_semantic
                and all(item == current_semantic for item in previous_semantic)
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


def _action_failed_or_unchanged(result: StepResult, events: list[EpisodeMonitorEvent]) -> bool:
    action = result.action_outcome
    if result.runtime_failure is not None or result.failure_code is not None:
        return True
    if action is None:
        return False
    if action.local_postcondition is LocalPostconditionStatus.SATISFIED:
        return False
    return EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events


def _repeated_failure_key(
    result: StepResult,
    events: list[EpisodeMonitorEvent],
    fresh_world_fingerprint: str,
) -> str:
    if result.task_evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
        return ""
    before_world = _world_digest(result.before_world)
    after_world = _world_digest(result.after_world) or fresh_world_fingerprint
    if before_world and after_world and before_world != after_world:
        return ""
    if isinstance(result.decision, PolicyFailure):
        return _stable_key(
            {
                "kind": "policy_failure",
                "failure": result.decision.kind.value,
                "reason": result.decision.reason,
                "task_progress": _task_progress_digest(result.task_evaluation),
                "world": after_world,
            }
        )
    if result.runtime_failure is not None:
        return _stable_key(
            {
                "kind": "runtime_failure",
                "stage": result.runtime_failure.stage.value,
                "failure": result.runtime_failure.kind.value,
                "code": result.runtime_failure.code,
                "attempt": _public_attempt(result),
                "task_progress": _task_progress_digest(result.task_evaluation),
                "world": after_world,
            }
        )
    if result.failure_code is not None:
        return _stable_key(
            {
                "kind": "agent_failure",
                "code": result.failure_code.value,
                "attempt": _public_attempt(result),
                "task_progress": _task_progress_digest(result.task_evaluation),
                "world": after_world,
            }
        )
    action = result.action_outcome
    if action is None:
        return ""
    no_change = action.observed_change is ObservedChange.UNCHANGED
    unsatisfied = action.local_postcondition is LocalPostconditionStatus.UNSATISFIED
    if not no_change and not unsatisfied:
        return ""
    return _stable_key(
        {
            "kind": "action_no_progress",
            "result": "unsatisfied" if unsatisfied else "unchanged",
            "attempt": _public_attempt(result),
            "task_progress": _task_progress_digest(result.task_evaluation),
            "world": after_world,
            "events": tuple(item.value for item in events),
        }
    )


def _task_progress_digest(evaluation: TaskEvaluation) -> object:
    return to_json_compatible(
        {
            "status": evaluation.status.value,
            "criteria": tuple(
                {
                    "criterion_id": item.criterion_id,
                    "status": item.status.value,
                    "evidence_refs": item.evidence_refs,
                }
                for item in evaluation.criteria
            ),
            "completion_evidence_refs": evaluation.completion_evidence_refs,
            "outputs": tuple(
                {
                    "output_id": item.output_id,
                    "value": item.value,
                    "evidence_refs": item.evidence_refs,
                }
                for item in evaluation.outputs
            ),
            "outcome": (
                {
                    "kind": evaluation.outcome.kind.value,
                    "code": evaluation.outcome.code,
                    "evidence_refs": evaluation.outcome.evidence_refs,
                }
                if evaluation.outcome is not None
                else None
            ),
        }
    )


def _public_attempt(result: StepResult) -> dict[str, object]:
    execution = result.execution
    if execution is None:
        return {
            "operation": _semantic_action(result),
            "target": {},
            "destination": {},
            "parameters": {},
        }
    intent = execution.request.intent
    return {
        "operation": intent.semantic_action,
        "target": _public_target(result, intent.target_id),
        "destination": _public_target(result, intent.destination_id),
        "parameters": to_json_compatible(intent.parameters),
    }


def _public_target(result: StepResult, target_id: str) -> dict[str, object]:
    if not target_id or result.policy_observation is None:
        return {}
    ref = result.policy_target_refs.get(target_id, "")
    if not ref:
        return {}
    path = _node_path(result.policy_observation, ref)
    if not path:
        return {}
    node = path[-1]
    return {
        "role": node.role,
        "label": node.label,
        "context": tuple(
            {
                "role": item.role,
                "label": item.label,
            }
            for item in path[:-1]
            if item.label.strip() or item.role.strip()
        )[-4:],
    }


def _node_path(snapshot, ref: str) -> tuple[object, ...]:
    def visit(node, parents: tuple[object, ...]):
        path = (*parents, node)
        if node.ref == ref:
            return path
        for child in node.children:
            if found := visit(child, path):
                return found
        return ()

    for document in snapshot.documents:
        for root in document.roots:
            if found := visit(root, ()):
                return found
    return ()


def _world_digest(world) -> str:
    try:
        from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest

        return public_world_semantic_digest(world)
    except Exception:
        return str(getattr(world, "observation_id", ""))


def _stable_key(payload: dict[str, object]) -> str:
    return json.dumps(to_json_compatible(payload), sort_keys=True, separators=(",", ":"))


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
