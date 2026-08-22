"""Deterministic episode monitor for bounded long-horizon episodes."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from affordance_runtime.agent.context.contracts import AgentTurnView, sanitize_history_value
from affordance_runtime.agent.decisions import (
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.recovery import (
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    EpisodeMonitorTransition,
    RecoveryKind,
    RecoverySignal,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation.contracts import (
    EvidenceMethod,
    LocalPostconditionStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import to_json_compatible


@dataclass(frozen=True)
class EpisodeMonitorConfig:
    repeated_action_threshold: int = 2
    no_change_threshold: int = 3
    repeated_failure_limit: int = 3

    def __post_init__(self) -> None:
        if self.repeated_action_threshold < 1 or self.no_change_threshold < 1 or self.repeated_failure_limit < 1:
            raise ValueError("episode monitor thresholds must be positive")


@dataclass(frozen=True)
class RouteSample:
    page_fingerprint: str
    full_world_fingerprint: str
    task_progress_fingerprint: str
    retained_evidence_fingerprint: str
    working_fact_fingerprint: str
    step_index: int


@dataclass
class EpisodeMonitor:
    config: EpisodeMonitorConfig = EpisodeMonitorConfig()
    repeated_failure_key: str = ""
    repeated_failure_count: int = 0
    recovery_in_progress_key: str = ""
    route_history: deque[RouteSample] = field(default_factory=lambda: deque(maxlen=64))
    episode_entry_page_fingerprint: str = ""
    route_recovery_page_fingerprint: str = ""
    _result_evidence_tokens: set[str] = field(default_factory=set, repr=False)
    _working_fact_tokens: set[str] = field(default_factory=set, repr=False)

    def start_episode(self, world, task_evaluation, working_facts=()) -> None:
        self.repeated_failure_key = ""
        self.repeated_failure_count = 0
        self.recovery_in_progress_key = ""
        self.route_recovery_page_fingerprint = ""
        self.route_history.clear()
        self._result_evidence_tokens = set(_result_evidence_tokens(world))
        self._working_fact_tokens = set(_working_fact_tokens(working_facts))
        sample = self._route_sample(world, task_evaluation, 0)
        self.episode_entry_page_fingerprint = sample.page_fingerprint
        self.route_history.append(sample)

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
        operational_progress = _has_operational_progress(result)
        if action is not None and operational_progress:
            events.append(EpisodeMonitorEvent.STATE_CHANGED)
        elif action is not None:
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)
        if result.task_evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
            events.append(EpisodeMonitorEvent.FORMAL_CRITERION_CHANGED)
        route_regression, route_progress = self._record_route_sample(result)
        if route_progress:
            self.route_recovery_page_fingerprint = ""
        if route_regression:
            events.append(EpisodeMonitorEvent.ROUTE_REGRESSION)
            failure_key = _stable_key(
                {
                    "kind": "route_regression",
                    "page": self.route_history[-1].page_fingerprint,
                }
            )
            signal = _recovery_signal(
                result,
                events,
                failure_key,
                kind=RecoveryKind.ROUTE_REGRESSION,
            )
            repeated = self.route_recovery_page_fingerprint == self.route_history[-1].page_fingerprint
            self.route_recovery_page_fingerprint = self.route_history[-1].page_fingerprint
            return EpisodeMonitorTransition(
                tuple(events),
                EpisodeMonitorRecommendation.BLOCK if repeated else EpisodeMonitorRecommendation.RECOVER,
                RecoveryKind.ROUTE_REGRESSION.value,
                signal,
            )
        failure_key = _repeated_failure_key(result, events)
        if failure_key:
            if failure_key == self.repeated_failure_key:
                self.repeated_failure_count += 1
            else:
                self.repeated_failure_key = failure_key
                self.repeated_failure_count = 1
            if failure_key == self.recovery_in_progress_key:
                signal = _recovery_signal(
                    result,
                    events,
                    failure_key,
                    same_result_count=self.repeated_failure_count,
                )
                return EpisodeMonitorTransition(
                    tuple(events),
                    EpisodeMonitorRecommendation.BLOCK,
                    signal.kind.value,
                    signal,
                )
            if self.repeated_failure_count == 2:
                signal = _recovery_signal(
                    result,
                    events,
                    failure_key,
                    same_result_count=self.repeated_failure_count,
                )
                self.recovery_in_progress_key = failure_key
                return EpisodeMonitorTransition(
                    tuple(events),
                    EpisodeMonitorRecommendation.RECOVER,
                    signal.kind.value,
                    signal,
                )
            if self.repeated_failure_count >= self.config.repeated_failure_limit:
                return EpisodeMonitorTransition(
                    tuple(events),
                    EpisodeMonitorRecommendation.BLOCK,
                    "repeated_failure_limit",
                )
        else:
            self.repeated_failure_key = ""
            self.repeated_failure_count = 0
        action_failed_or_unchanged = _action_failed_or_unchanged(result, events)
        if isinstance(result.decision, SelectAction):
            current_key = _action_key(result)
            previous = tuple(_turn_key(item) for item in recent_steps[-self.config.repeated_action_threshold :])
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
        if (
            _unchanged_streak(recent_steps) + int(EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events)
            >= self.config.no_change_threshold
        ):
            events.append(EpisodeMonitorEvent.NO_OBSERVED_CHANGE)
            events.append(EpisodeMonitorEvent.REPEATED_ACTION)
        if EpisodeMonitorEvent.OSCILLATION in events:
            failure_key = failure_key or _stable_key(
                {
                    "kind": "state_oscillation",
                    "world": fresh_world_fingerprint,
                    "attempt": _public_attempt(result),
                }
            )
            if failure_key == self.recovery_in_progress_key:
                signal = _recovery_signal(
                    result,
                    events,
                    failure_key,
                    kind=RecoveryKind.STATE_OSCILLATION,
                    same_result_count=max(2, self.repeated_failure_count),
                )
                return EpisodeMonitorTransition(
                    tuple(events),
                    EpisodeMonitorRecommendation.BLOCK,
                    RecoveryKind.STATE_OSCILLATION.value,
                    signal,
                )
            signal = _recovery_signal(result, events, failure_key, kind=RecoveryKind.STATE_OSCILLATION)
            self.recovery_in_progress_key = failure_key
            return EpisodeMonitorTransition(
                tuple(events),
                EpisodeMonitorRecommendation.RECOVER,
                signal.kind.value,
                signal,
            )
        if not failure_key and (
            EpisodeMonitorEvent.STATE_CHANGED in events
            or EpisodeMonitorEvent.FORMAL_CRITERION_CHANGED in events
            or (
                result.action_outcome is None
                and result.public_world_delta is not None
                and result.public_world_delta.changed
            )
        ):
            self.recovery_in_progress_key = ""
        return EpisodeMonitorTransition(tuple(events), EpisodeMonitorRecommendation.CONTINUE)

    def _record_route_sample(self, result: StepResult) -> tuple[bool, bool]:
        if not self.route_history:
            self.start_episode(result.before_world, result.task_evaluation)
        self._result_evidence_tokens.update(_result_evidence_tokens(result.after_world))
        fact = result.decision.working_fact if isinstance(result.decision, LocalToolResult) else None
        if fact is not None:
            self._working_fact_tokens.update(_working_fact_tokens((fact,)))
        sample = self._route_sample(
            result.after_world,
            result.task_evaluation,
            self.route_history[-1].step_index + 1,
        )
        prior_sample = self.route_history[-1]
        progress_changed = any(
            (
                sample.task_progress_fingerprint != prior_sample.task_progress_fingerprint,
                sample.retained_evidence_fingerprint != prior_sample.retained_evidence_fingerprint,
                sample.working_fact_fingerprint != prior_sample.working_fact_fingerprint,
            )
        )
        history = tuple(self.route_history)
        prior_index = next(
            (
                index
                for index in range(len(history) - 1, -1, -1)
                if history[index].page_fingerprint == sample.page_fingerprint
            ),
            -1,
        )
        returned = prior_index >= 0 and any(
            item.page_fingerprint != sample.page_fingerprint for item in history[prior_index + 1 :]
        )
        no_progress = bool(
            returned
            and all(
                (
                    sample.task_progress_fingerprint == history[prior_index].task_progress_fingerprint,
                    sample.retained_evidence_fingerprint == history[prior_index].retained_evidence_fingerprint,
                    sample.working_fact_fingerprint == history[prior_index].working_fact_fingerprint,
                )
            )
        )
        self.route_history.append(sample)
        return no_progress, progress_changed

    def _route_sample(self, world, evaluation, step_index: int) -> RouteSample:
        from affordance_runtime.world.public_semantic_digest import (
            public_page_semantic_digest,
            public_world_semantic_digest,
        )

        return RouteSample(
            public_page_semantic_digest(world),
            public_world_semantic_digest(world),
            _digest_value(_task_progress_digest(evaluation)),
            _digest_value(tuple(sorted(self._result_evidence_tokens))),
            _digest_value(tuple(sorted(self._working_fact_tokens))),
            step_index,
        )


def _action_key(result: StepResult) -> str:
    receipt = _last_receipt(result)
    if receipt is None:
        return getattr(getattr(result.decision, "kind", None), "value", "policy_failure")
    intent = receipt.request.intent
    payload = {
        "action": intent.semantic_action,
        "target": intent.target_id,
        "destination": intent.destination_id,
        "parameters": to_json_compatible(intent.parameters),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _semantic_action(result: StepResult) -> str:
    receipt = _last_receipt(result)
    return receipt.request.intent.semantic_action if receipt is not None else ""


def _action_failed_or_unchanged(result: StepResult, events: list[EpisodeMonitorEvent]) -> bool:
    action = result.action_outcome
    if result.runtime_failure is not None or result.failure_code is not None:
        return True
    if action is None:
        return False
    if action.local_postcondition is LocalPostconditionStatus.SATISFIED:
        return False
    return EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events


def _has_operational_progress(result: StepResult) -> bool:
    """Classify mechanically supported execution progress without task semantics."""

    action = result.action_outcome
    if action is None:
        return False
    if action.local_postcondition is LocalPostconditionStatus.SATISFIED:
        return True
    return bool(
        result.public_world_delta is not None
        and result.public_world_delta.changed
        and action.evidence_method is EvidenceMethod.STRUCTURAL
    )


def _repeated_failure_key(
    result: StepResult,
    events: list[EpisodeMonitorEvent],
) -> str:
    if result.task_evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
        return ""
    delta = result.public_world_delta
    after_world = delta.after_world_digest if delta is not None else _world_digest(result.after_world)
    if result.action_outcome is None and delta is not None and delta.changed:
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
    terminal_failure = result.execution_receipts.terminal_failure if result.execution_receipts is not None else None
    if terminal_failure is not None and terminal_failure.error is not None:
        return _stable_key(
            {
                "kind": "action_not_sent",
                "error": terminal_failure.error.value,
                "attempt": _public_attempt(result),
                "task": result.task_evaluation.task_id,
                "task_progress": _task_progress_digest(result.task_evaluation),
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
    if isinstance(result.decision, LocalToolResult):
        return _stable_key(
            {
                "kind": "local_tool_result",
                "world": after_world,
                "tool": result.decision.tool_name,
                "canonical_args": to_json_compatible(result.decision.arguments),
                "result": to_json_compatible(result.decision.result),
                "task_progress": _task_progress_digest(result.task_evaluation),
            }
        )
    if isinstance(result.decision, RequestActionPage):
        return _stable_key(
            {
                "kind": "action_page_result",
                "world": after_world,
                "filters": {
                    "query": result.decision.query,
                    "exact_target": result.decision.exact_target_ref,
                    "relevance_role": result.decision.relevance_role,
                    "cursor": bool(result.decision.cursor),
                },
                "result": to_json_compatible(result.action_page_result),
                "total_count": result.action_page_result.get("total_count", 0),
                "task_progress": _task_progress_digest(result.task_evaluation),
            }
        )
    action = result.action_outcome
    if action is None:
        return ""
    no_change = EpisodeMonitorEvent.NO_OBSERVED_CHANGE in events
    unsatisfied = action.local_postcondition is LocalPostconditionStatus.UNSATISFIED
    if not no_change and not unsatisfied:
        return ""
    return _stable_key(
        {
            "kind": "action_no_progress",
            "result": "unsatisfied" if unsatisfied else "unchanged",
            "attempt": _public_attempt(result),
            "task_progress": _task_progress_digest(result.task_evaluation),
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
    receipt = _last_receipt(result)
    if receipt is None:
        return {
            "operation": _semantic_action(result),
            "target": {},
            "destination": {},
            "parameters": {},
        }
    intent = receipt.request.intent
    return {
        "operation": intent.semantic_action,
        "target": _public_target(result, intent.target_id),
        "destination": _public_target(result, intent.destination_id),
        "parameters": to_json_compatible(intent.parameters),
    }


def _bounded_public_attempt(result: StepResult) -> dict[str, object]:
    attempt = _public_attempt(result)

    def bounded_target(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            return {}
        if not value:
            return {}
        context = value.get("context", ())
        return {
            "role": str(value.get("role", ""))[:80],
            "label": str(value.get("label", ""))[:160],
            **(
                {"context": tuple(context)[-4:]}
                if (isinstance(context, Sequence) and not isinstance(context, str | bytes) and context)
                else {}
            ),
        }

    parameters = attempt.get("parameters", {})
    return {
        "operation": str(attempt.get("operation", ""))[:80],
        "target": bounded_target(attempt.get("target")),
        "destination": bounded_target(attempt.get("destination")),
        "parameters": (_bounded_argument_summary(parameters) if isinstance(parameters, Mapping) else {}),
    }


def _public_target(result: StepResult, target_id: str) -> dict[str, object]:
    if not target_id:
        return {}
    if result.policy_observation is None:
        return _world_target(result, target_id)
    ref = result.policy_target_refs.get(target_id, "")
    if not ref:
        return _world_target(result, target_id)
    path = _node_path(result.policy_observation, ref)
    if not path:
        return _world_target(result, target_id)
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


def _world_target(result: StepResult, target_id: str) -> dict[str, object]:
    target = next((item for item in result.before_world.targets if item.target_id == target_id), None)
    if target is None:
        return {}
    return {
        "role": target.role,
        "label": target.label,
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


def _result_evidence_tokens(world) -> tuple[str, ...]:
    from affordance_runtime.world.public_semantic_digest import public_result_evidence_semantics

    return tuple(_canonical_json(item) for item in public_result_evidence_semantics(world))


def _working_fact_tokens(working_facts) -> tuple[str, ...]:
    return tuple(
        _canonical_json(
            {
                "key": getattr(item, "key", ""),
                "evidence_ref": getattr(getattr(item, "record", None), "evidence_ref", ""),
                "value": getattr(getattr(item, "record", None), "value", None),
            }
        )
        for item in working_facts
    )


def _digest_value(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _stable_key(payload: dict[str, object]) -> str:
    canonical = _canonical_json(payload)
    kind = str(payload.get("kind", "attempt"))[:80]
    return f"{kind}:sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _canonical_json(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _recovery_signal(
    result: StepResult,
    events: list[EpisodeMonitorEvent],
    failure_key: str,
    *,
    kind: RecoveryKind | None = None,
    same_result_count: int = 1,
) -> RecoverySignal:
    selected_kind = kind or _recovery_kind(result, events)
    attempted = _attempted_modes(result, events)
    return RecoverySignal(
        kind=selected_kind,
        stable_signature=failure_key,
        observed_evidence=_recovery_evidence(result, events, same_result_count),
        attempted_modes=attempted,
        prohibited_attempt_signature=_prohibited_attempt_signature(result),
        human_instruction=_prohibited_repeat(result),
        recovery_attempt=1,
    )


def _prohibited_attempt_signature(result: StepResult):
    if isinstance(result.decision, LocalToolResult):
        return result.decision.rejected_attempt_signature
    receipt = _last_receipt(result)
    if receipt is None:
        return None
    from affordance_runtime.agent.attempt_signature import public_attempt_signature

    intent = receipt.request.intent
    return public_attempt_signature(
        intent.semantic_action,
        intent.target_id,
        intent.destination_id,
        intent.parameters,
        result.before_world,
    )


def _recovery_evidence(
    result: StepResult,
    events: list[EpisodeMonitorEvent],
    same_result_count: int,
) -> Mapping[str, object]:
    base: dict[str, object] = {
        "attempt": _bounded_public_attempt(result),
        "feedback": result.feedback[:160],
        "events": tuple(item.value for item in events),
        "dispatch": _dispatch_status(result),
        "repeat_count": max(1, same_result_count),
        "task_evaluation": result.task_evaluation.status.value,
    }
    action = result.action_outcome
    if action is not None:
        base.update(
            {
                "observed_change": action.observed_change.value,
                "local_postcondition": action.local_postcondition.value,
                "evidence_method": action.evidence_method.value,
                "operational_progress": False,
                "new_structural_evidence": False,
            }
        )
    if not isinstance(result.decision, LocalToolResult):
        return base
    public_result = to_json_compatible(result.decision.result)
    result_mapping = public_result if isinstance(public_result, Mapping) else {}
    items = result_mapping.get("items", ())
    item_count = (
        len(items)
        if isinstance(items, Sequence) and not isinstance(items, str | bytes)
        else int(result_mapping.get("total_count", 0) or 0)
    )
    return {
        **base,
        "tool": result.decision.tool_name,
        "arguments": _bounded_argument_summary(result.decision.arguments),
        "result_kind": str(result_mapping.get("kind", type(public_result).__name__))[:80],
        "item_count": item_count,
        "coverage": str(result_mapping.get("coverage", ""))[:80],
        "result_digest": "sha256:" + hashlib.sha256(_canonical_json(public_result).encode()).hexdigest(),
        "same_result_count": max(1, same_result_count),
    }


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


def _recovery_kind(result: StepResult, events: list[EpisodeMonitorEvent]) -> RecoveryKind:
    if EpisodeMonitorEvent.OSCILLATION in events:
        return RecoveryKind.STATE_OSCILLATION
    if isinstance(result.decision, LocalToolResult | RequestActionPage):
        return RecoveryKind.CONTROL_STALL
    if EpisodeMonitorEvent.CAPABILITY_GAP in events:
        return RecoveryKind.CAPABILITY_GAP
    if result.feedback in {"binding_unavailable"} or result.feedback.startswith("action_not_sent:"):
        return RecoveryKind.GROUNDING_STALL
    if result.action_outcome is not None and (
        result.action_outcome.local_postcondition is LocalPostconditionStatus.UNSATISFIED
        or not _has_operational_progress(result)
    ):
        return RecoveryKind.EFFECT_STALL
    if result.execution_receipts is not None and result.execution_receipts.sent_unknown_count:
        return RecoveryKind.UNCERTAIN_EFFECT
    return RecoveryKind.STRATEGY_STALL


def _attempted_modes(result: StepResult, events: list[EpisodeMonitorEvent]) -> tuple[str, ...]:
    modes = []
    if isinstance(result.decision, LocalToolResult):
        modes.append(result.decision.tool_name)
    elif isinstance(result.decision, RequestActionPage):
        modes.append("find_controls")
    elif isinstance(result.decision, SelectAction):
        modes.append(_semantic_action(result) or "select_action")
    else:
        modes.append(getattr(getattr(result.decision, "kind", None), "value", "policy_failure"))
    modes.extend(item.value for item in events)
    return tuple(dict.fromkeys(item for item in modes if item))


def _prohibited_repeat(result: StepResult) -> str:
    if isinstance(result.decision, LocalToolResult):
        arguments = result.decision.arguments
        query = sanitize_history_value(str(arguments.get("query", "")))
        subject = str(query)[:120] if query else "the same semantic arguments"
        return f"Do not repeat {result.decision.tool_name} on {subject} without new evidence."
    if isinstance(result.decision, RequestActionPage):
        return "Do not repeat find_controls with the same query without new evidence."
    if isinstance(result.decision, SelectAction):
        operation = _semantic_action(result) or "the same action"
        receipt = _last_receipt(result)
        target_id = receipt.request.intent.target_id if receipt is not None else ""
        target = _public_target(result, target_id)
        label = str(target.get("label", "")).strip()[:120]
        suffix = f" on {label}" if label else ""
        return f"Do not repeat {operation}{suffix} without new evidence."
    return "Do not immediately repeat the same failed attempt without new evidence."


def _dispatch_status(result: StepResult) -> str:
    if result.execution_receipts is None:
        return "not_sent"
    if result.execution_receipts.terminal_failure is not None:
        return DispatchStatus.NOT_SENT.value
    receipt = _last_receipt(result)
    return receipt.result.dispatch_status.value if receipt is not None else "not_sent"


def _last_receipt(result: StepResult):
    batch = result.execution_receipts
    return batch.receipts[-1] if batch is not None and batch.receipts else None


def _turn_key(turn: AgentTurnView) -> str:
    payload = {
        "action": turn.semantic_action,
        "target": getattr(turn.target, "label", "") if turn.target is not None else "",
        "destination": getattr(turn.destination, "label", "") if turn.destination is not None else "",
        "parameters": to_json_compatible(turn.public_parameters),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _unchanged_streak(recent_steps: tuple[AgentTurnView, ...]) -> int:
    streak = 0
    for step in reversed(recent_steps):
        transition = step.transition
        if transition.get("observed_change") not in {"unchanged", "no_effect"}:
            break
        streak += 1
    return streak
