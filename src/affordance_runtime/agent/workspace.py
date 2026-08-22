"""Bounded, total model workspace for one continuous GUI-agent episode."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from affordance_runtime.agent.context.contracts import (
    AgentHistoricalTargetView,
    AgentTurnView,
    sanitize_history_value,
)
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.context.world_transition import PublicChangeKind, PublicWorldDelta
from affordance_runtime.agent.working_facts import WorkingFact, validate_working_fact_collection
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.contracts import CoverageState

MAX_WORKSPACE_RECENT_STEPS = 4
MAX_WORKSPACE_SEMANTIC_EVENTS = 24
MAX_WORKSPACE_EVENT_VALUES = 32


@dataclass(frozen=True)
class CurrentFinding:
    evidence_ref: str
    predicate: str
    exact_value: object
    source_context: str
    coverage: CoverageState

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.evidence_ref, self.predicate, self.source_context)):
            raise ValueError("current finding requires public evidence identity and context")
        if not isinstance(self.coverage, CoverageState):
            raise TypeError("current finding coverage must be typed")
        object.__setattr__(self, "exact_value", freeze_json(self.exact_value))


class SemanticEventKind(StrEnum):
    GUI_EFFECT = "gui_effect"
    PUBLIC_RESULT = "public_result"
    WORKING_FACT = "working_fact"
    TYPED_FAILURE = "typed_failure"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class SemanticEvent:
    step_index: int
    kind: SemanticEventKind
    summary: str
    exact_public_values: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("semantic event step index must be non-negative")
        if (
            not isinstance(self.kind, SemanticEventKind)
            or not self.summary.strip()
            or len(self.summary) > 240
        ):
            raise TypeError("semantic event requires typed kind and summary")
        values = tuple(freeze_json(dict(item)) for item in self.exact_public_values)
        if len(values) > MAX_WORKSPACE_EVENT_VALUES:
            raise ValueError("semantic event exact values exceed the workspace bound")
        object.__setattr__(self, "exact_public_values", values)


class ActivityFamily(StrEnum):
    READ_REGION = "read_region"
    SEARCH_PAGE_CONTENT = "search_page_content"
    FIND_CONTROLS = "find_controls"
    WAIT = "wait"
    NO_EFFECT = "no_effect"


_ACTIVITY_BY_TOOL = {
    "read_region": ActivityFamily.READ_REGION,
    "search_page_content": ActivityFamily.SEARCH_PAGE_CONTENT,
    "find_controls": ActivityFamily.FIND_CONTROLS,
    "wait": ActivityFamily.WAIT,
}


@dataclass(frozen=True)
class ActivitySummary:
    family: ActivityFamily
    world_digest: str
    attempt_count: int
    new_finding_count: int
    last_outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.family, ActivityFamily):
            raise TypeError("activity family must be typed")
        if (
            not self.world_digest.strip()
            or not self.last_outcome.strip()
            or len(self.last_outcome) > 240
        ):
            raise ValueError("activity summary requires digest and outcome")
        if (
            type(self.attempt_count) is not int
            or self.attempt_count < 1
            or type(self.new_finding_count) is not int
            or self.new_finding_count < 0
        ):
            raise ValueError("activity counts are invalid")


@dataclass(frozen=True)
class AgentWorkspace:
    recent_steps: tuple[AgentTurnView, ...] = ()
    semantic_events: tuple[SemanticEvent, ...] = ()
    activities: tuple[ActivitySummary, ...] = ()
    working_facts: tuple[WorkingFact, ...] = ()

    def __post_init__(self) -> None:
        recent = tuple(self.recent_steps)
        events = tuple(self.semantic_events)
        activities = tuple(self.activities)
        if len(recent) > MAX_WORKSPACE_RECENT_STEPS or any(not isinstance(item, AgentTurnView) for item in recent):
            raise ValueError("workspace retains at most four typed detailed steps")
        if any(not isinstance(item, SemanticEvent) for item in events):
            raise TypeError("workspace semantic events must be typed")
        if any(not isinstance(item, ActivitySummary) for item in activities):
            raise TypeError("workspace activities must be typed")
        if len(events) > MAX_WORKSPACE_SEMANTIC_EVENTS:
            raise ValueError("workspace semantic events exceed their fixed bound")
        if len(activities) > len(ActivityFamily) or len({item.family for item in activities}) != len(activities):
            raise ValueError("workspace activities must have one bounded summary per family")
        object.__setattr__(self, "recent_steps", recent)
        object.__setattr__(self, "semantic_events", events)
        object.__setattr__(self, "activities", activities)
        object.__setattr__(self, "working_facts", validate_working_fact_collection(self.working_facts))


class WorkspaceReducer(Protocol):
    """Total reduction port over one committed step."""

    def reduce(
        self,
        previous: AgentWorkspace,
        step: object,
        detailed_step: AgentTurnView | None,
        step_index: int,
        current_findings: tuple[CurrentFinding, ...] = (),
    ) -> AgentWorkspace: ...

    def fit(self, workspace: AgentWorkspace, allocation_bytes: int) -> AgentWorkspace: ...


class WorkspaceCapacityError(ValueError):
    """The exact irreducible workspace cannot fit its assigned request allocation."""


def working_facts_digest(
    workspace: AgentWorkspace,
    pending_fact: WorkingFact | None = None,
) -> str:
    """Digest exact retained facts, including a fact produced by the current step."""

    if not isinstance(workspace, AgentWorkspace):
        raise TypeError("working-facts digest requires typed workspace")
    facts = {item.key: item for item in workspace.working_facts}
    if pending_fact is not None:
        if not isinstance(pending_fact, WorkingFact):
            raise TypeError("pending working fact must be typed")
        facts[pending_fact.key] = pending_fact
    encoded = json.dumps(
        tuple(
            (
                key,
                fact.record.predicate,
                to_json_compatible(fact.value),
                fact.record.evidence_ref,
            )
            for key, fact in sorted(facts.items())
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class DefaultWorkspaceReducer:
    """Retain detail, exact significant values, and compact activity without growth failure."""

    def reduce(
        self,
        previous: AgentWorkspace,
        step: object,
        detailed_step: AgentTurnView | None,
        step_index: int,
        current_findings: tuple[CurrentFinding, ...] = (),
    ) -> AgentWorkspace:
        if not isinstance(previous, AgentWorkspace):
            raise TypeError("workspace reducer requires typed previous state")
        if detailed_step is not None and not isinstance(detailed_step, AgentTurnView):
            raise TypeError("workspace detailed step must be typed")
        if type(step_index) is not int or step_index < 0:
            raise ValueError("workspace reducer step index must be non-negative")
        delta = getattr(step, "public_world_delta", None)
        if not isinstance(delta, PublicWorldDelta):
            raise TypeError("workspace reducer requires the authoritative public World delta")

        recent = previous.recent_steps
        if detailed_step is not None:
            recent = (*recent, detailed_step)[-MAX_WORKSPACE_RECENT_STEPS:]

        events = list(previous.semantic_events)
        receipts = tuple(getattr(getattr(step, "execution_receipts", None), "receipts", ()))
        if receipts:
            values = _significant_values(delta, current_findings)
            if delta.changed:
                _append_event(
                    events,
                    SemanticEvent(
                        step_index,
                        SemanticEventKind.GUI_EFFECT,
                        _event_summary(detailed_step, getattr(step, "feedback", "GUI effect")),
                    ),
                )
            if values:
                _append_event(
                    events,
                    SemanticEvent(
                        step_index,
                        SemanticEventKind.PUBLIC_RESULT,
                        f"exact public values after {_event_summary(detailed_step, 'GUI effect')}"[:240],
                        values,
                    ),
                )

        decision = getattr(step, "decision", None)
        working_fact = getattr(decision, "working_fact", None)
        working_facts = {item.key: item for item in previous.working_facts}
        if isinstance(working_fact, WorkingFact):
            working_facts[working_fact.key] = working_fact
            _append_event(
                events,
                SemanticEvent(
                    step_index,
                    SemanticEventKind.WORKING_FACT,
                    f"retained exact working fact {working_fact.key}",
                    (
                        {
                            "key": working_fact.key,
                            "predicate": working_fact.record.predicate,
                            "value": working_fact.value,
                        },
                    ),
                ),
            )

        recovery = getattr(step, "recovery_signal", None)
        if recovery is not None:
            _append_event(
                events,
                SemanticEvent(
                    step_index,
                    SemanticEventKind.RECOVERY,
                    str(getattr(recovery, "reason", None) or getattr(step, "feedback", "recovery"))[:240],
                ),
            )
        if _is_typed_failure(step):
            _append_event(
                events,
                SemanticEvent(
                    step_index,
                    SemanticEventKind.TYPED_FAILURE,
                    _failure_summary(step),
                ),
            )

        activities = _reduce_activity(previous.activities, detailed_step, delta)
        return AgentWorkspace(
            recent,
            tuple(events[-MAX_WORKSPACE_SEMANTIC_EVENTS:]),
            activities,
            tuple(working_facts.values()),
        )

    def fit(self, workspace: AgentWorkspace, allocation_bytes: int) -> AgentWorkspace:
        if not isinstance(workspace, AgentWorkspace):
            raise TypeError("workspace fit requires typed state")
        if type(allocation_bytes) is not int or allocation_bytes < 1:
            raise WorkspaceCapacityError("workspace allocation is irreducible")
        candidate = workspace
        if _workspace_bytes(candidate) <= allocation_bytes:
            return candidate
        candidate = AgentWorkspace(
            candidate.recent_steps,
            candidate.semantic_events,
            (),
            candidate.working_facts,
        )
        if _workspace_bytes(candidate) <= allocation_bytes:
            return candidate
        significant = tuple(item for item in candidate.semantic_events if item.exact_public_values)
        candidate = AgentWorkspace(
            candidate.recent_steps,
            significant,
            (),
            candidate.working_facts,
        )
        if _workspace_bytes(candidate) <= allocation_bytes:
            return candidate
        raise WorkspaceCapacityError("exact workspace exceeds its request allocation")


def render_agent_workspace(workspace: AgentWorkspace, *, total_step_count: int) -> dict[str, object]:
    """Render the bounded workspace without imposing a second capacity decision."""

    if not isinstance(workspace, AgentWorkspace):
        raise TypeError("workspace renderer requires typed state")
    if type(total_step_count) is not int or total_step_count < 0:
        raise ValueError("workspace total step count is invalid")
    return {
        "semantic_events": tuple(
            {
                "step_index": item.step_index,
                "kind": item.kind.value,
                "summary": sanitize_history_value(item.summary),
                "exact_public_values": project_public_value(item.exact_public_values),
            }
            for item in workspace.semantic_events
        ),
        "activity_summaries": tuple(
            {
                "family": item.family.value,
                "world_digest": item.world_digest,
                "attempt_count": item.attempt_count,
                "new_finding_count": item.new_finding_count,
                "last_outcome": sanitize_history_value(item.last_outcome),
            }
            for item in workspace.activities
        ),
        "recent_trajectory": tuple(_render_turn(item) for item in workspace.recent_steps),
        "retained_count": max(total_step_count, len(workspace.recent_steps)),
    }


def _significant_values(
    delta: PublicWorldDelta,
    findings: tuple[CurrentFinding, ...],
) -> tuple[Mapping[str, object], ...]:
    values: list[Mapping[str, object]] = [
        {
            "predicate": item.predicate,
            "value": item.exact_value,
            "source_context": item.source_context,
        }
        for item in findings
    ]
    values.extend(
        {
            "kind": item.kind.value,
            "predicate": item.predicate,
            "value": item.after.value,
        }
        for item in delta.fact_changes
        if item.after is not None and item.kind is not PublicChangeKind.REMOVED
    )
    values.extend(
        {
            "kind": item.kind.value,
            "predicate": "public.label",
            "value": item.after.label,
            "source_context": item.after.role,
        }
        for item in delta.target_changes
        if item.after is not None and item.kind is not PublicChangeKind.REMOVED
    )
    unique: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for item in values:
        frozen = freeze_json(dict(item))
        key = repr(frozen)
        if key not in seen:
            seen.add(key)
            unique.append(frozen)
        if len(unique) >= MAX_WORKSPACE_EVENT_VALUES:
            break
    return tuple(unique)


def _append_event(events: list[SemanticEvent], event: SemanticEvent) -> None:
    if events and events[-1].kind is event.kind and events[-1].exact_public_values == event.exact_public_values:
        events[-1] = event
    else:
        events.append(event)


def _reduce_activity(
    previous: tuple[ActivitySummary, ...],
    detailed_step: AgentTurnView | None,
    delta: PublicWorldDelta,
) -> tuple[ActivitySummary, ...]:
    family = _ACTIVITY_BY_TOOL.get(detailed_step.semantic_action if detailed_step is not None else "")
    if family is None and not delta.changed and detailed_step is not None and detailed_step.dispatch_status:
        family = ActivityFamily.NO_EFFECT
    if family is None:
        return previous
    current = next((item for item in previous if item.family is family), None)
    count = current.attempt_count + 1 if current is not None and current.world_digest == delta.after_world_digest else 1
    summary = ActivitySummary(
        family,
        delta.after_world_digest,
        count,
        0,
        detailed_step.reason if detailed_step is not None and detailed_step.reason else "unchanged",
    )
    return tuple(item for item in previous if item.family is not family) + (summary,)


def _event_summary(step: AgentTurnView | None, fallback: str) -> str:
    if step is not None:
        target = f' {step.target.role} "{step.target.label}"' if step.target is not None else ""
        return f"{step.semantic_action or step.decision_kind}{target}"[:240]
    return str(fallback or "GUI effect")[:240]


def _is_typed_failure(step: object) -> bool:
    status = str(getattr(getattr(step, "status_after", ""), "value", getattr(step, "status_after", "")))
    return status in {"blocked", "failed"} or getattr(step, "failure_code", None) is not None or getattr(
        step, "runtime_failure", None
    ) is not None


def _failure_summary(step: object) -> str:
    code = getattr(step, "failure_code", None)
    value = getattr(code, "value", code)
    return str(value or getattr(step, "feedback", "typed failure"))[:240]


def _render_turn(item: AgentTurnView) -> dict[str, object]:
    action: dict[str, object] = {
        "kind": sanitize_history_value(item.decision_kind),
        "tool": sanitize_history_value(item.semantic_action),
        "arguments": sanitize_history_value(project_public_value(item.public_parameters)),
    }
    if item.target is not None:
        action["target"] = _historical_target(item.target)
    if item.destination is not None:
        action["destination"] = _historical_target(item.destination)
    if item.expected_outcome:
        action["expected_outcome"] = sanitize_history_value(item.expected_outcome)
    result_details = None
    if item.semantic_summary:
        details = sanitize_history_value(project_public_value(item.semantic_summary))
        if isinstance(details, Mapping):
            details = dict(details)
            result_details = details.pop("result", None)
        if details:
            action["details"] = details
    result: dict[str, object] = {
        "dispatch": sanitize_history_value(item.dispatch_status),
        "local_postcondition": sanitize_history_value(item.local_postcondition),
        "reason": sanitize_history_value(item.reason),
    }
    if item.task_evaluation_status not in {"", "unknown", "incomplete"}:
        result["task"] = sanitize_history_value(item.task_evaluation_status)
    transition = _render_transition(item.transition)
    if transition:
        result["transition"] = transition
    if result_details is not None:
        result["details"] = result_details
    return {"action": action, "result": result}


def _historical_target(value: AgentHistoricalTargetView) -> dict[str, object]:
    result: dict[str, object] = {
        "role": sanitize_history_value(value.role),
        "label": sanitize_history_value(value.label),
    }
    if value.context:
        result["context"] = tuple(sanitize_history_value(item) for item in value.context)
    return result


def _render_transition(transition: Mapping[str, object]) -> dict[str, object]:
    public = sanitize_history_value(transition)
    if not isinstance(public, Mapping):
        return {}
    keys = (
        "role",
        "label",
        "observed_change",
        "evidence_method",
        "local_postcondition",
        "target_changed",
        "structural_world_changed",
        "before_state",
        "after_state",
    )
    return {key: public[key] for key in keys if key in public}


def _workspace_bytes(workspace: AgentWorkspace) -> int:
    return len(
        json.dumps(
            to_json_compatible(render_agent_workspace(workspace, total_step_count=0)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
