"""Bounded one-way projection of the latest canonical ControlTransition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.control_transition_projection import (
    project_decision_summary,
)
from affordance_runtime.agent.control_transition import ControlTransition
from affordance_runtime.immutable import freeze_json

TRANSITION_DIGEST_SCHEMA_VERSION = "agent-transition@v1"
_MAX_REASON = 240


@dataclass(frozen=True)
class AgentTransitionLineageView:
    before_observation_id: str
    after_observation_id: str


@dataclass(frozen=True)
class AgentPreviousDecisionView:
    decision_kind: str
    semantic_action: str = ""
    target_ref: str = ""
    destination_ref: str = ""
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", freeze_json(self.details))


@dataclass(frozen=True)
class AgentExecutionOutcomeView:
    admission_status: str
    admission_reason_code: str
    dispatch_status: str
    transport_success: bool | None
    error_code: str
    attempt_count: int
    pending_kind: str
    resulting_status: str
    reason_code: str


@dataclass(frozen=True)
class AgentEffectAssessmentView:
    status: str
    reason: str
    evidence_refs: BoundedSection[str]


@dataclass(frozen=True)
class AgentCriterionTransitionView:
    criterion_id: str
    before_status: str
    after_status: str
    reason: str
    evidence_refs: BoundedSection[str]


@dataclass(frozen=True)
class AgentOutputTransitionView:
    output_id: str
    operation: str
    evidence_refs: BoundedSection[str]


@dataclass(frozen=True)
class AgentProgressDeltaView:
    before_task_status: str
    after_task_status: str
    criterion_transitions: BoundedSection[AgentCriterionTransitionView]
    output_transitions: BoundedSection[AgentOutputTransitionView]
    completion_evidence_added: BoundedSection[str]
    completion_evidence_removed: BoundedSection[str]


@dataclass(frozen=True)
class AgentTransitionDigestView:
    schema_version: str
    transition_id: str
    lineage: AgentTransitionLineageView
    previous_decision: AgentPreviousDecisionView
    execution_outcome: AgentExecutionOutcomeView
    effect_assessment: AgentEffectAssessmentView
    progress_delta: AgentProgressDeltaView

    def __post_init__(self) -> None:
        if self.schema_version != TRANSITION_DIGEST_SCHEMA_VERSION:
            raise ValueError("agent transition digest schema is unsupported")
        if not self.transition_id.startswith("transition:"):
            raise ValueError("agent transition digest requires root identity")


def project_latest_transition(
    transitions: tuple[ControlTransition, ...],
    grounding: AgentGroundingIndexView,
    *,
    max_progress_changes: int,
    max_evidence_refs: int,
) -> AgentTransitionDigestView | None:
    """Project only the latest root; never retain or reconstruct Runtime state."""

    if max_progress_changes <= 0 or max_evidence_refs <= 0:
        raise ValueError("transition projection bounds must be positive")
    if not transitions:
        return None
    transition = transitions[-1]
    refs = dict(grounding.target_refs)
    intent = transition.intent
    execution = transition.execution
    admission = transition.admission
    action = transition.action_evaluation
    return AgentTransitionDigestView(
        TRANSITION_DIGEST_SCHEMA_VERSION,
        transition.transition_id,
        AgentTransitionLineageView(
            transition.before_observation_id,
            transition.after_observation_id,
        ),
        AgentPreviousDecisionView(
            type(transition.decision).__name__.lower(),
            intent.semantic_action if intent is not None else "",
            refs.get(intent.target_id, "") if intent is not None else "",
            refs.get(intent.destination_id, "") if intent is not None else "",
            _bounded_details(
                project_decision_summary(transition.decision, transition.decision_result)
            ),
        ),
        AgentExecutionOutcomeView(
            str(admission.status) if admission is not None else "",
            admission.reason_code if admission is not None else "",
            str(execution.dispatch_status) if execution is not None else "",
            execution.transport_success if execution is not None else None,
            str(execution.error or "") if execution is not None else "",
            len(transition.execution_attempts),
            str(transition.pending_kind),
            str(transition.resulting_status or ""),
            transition.reason_code,
        ),
        AgentEffectAssessmentView(
            str(action.status) if action is not None else "",
            _bounded(action.reason) if action is not None else "",
            _bounded_refs(action.evidence_refs if action is not None else (), max_evidence_refs),
        ),
        _progress_delta(transition, max_progress_changes, max_evidence_refs),
    )


def _progress_delta(
    transition: ControlTransition,
    max_changes: int,
    max_evidence_refs: int,
) -> AgentProgressDeltaView:
    before = transition.before_task_evaluation
    after = transition.task_evaluation
    before_criteria = {item.criterion_id: item for item in before.criteria} if before else {}
    after_criteria = {item.criterion_id: item for item in after.criteria} if after else {}
    criterion_changes = []
    for criterion_id in sorted(before_criteria.keys() | after_criteria.keys()):
        prior = before_criteria.get(criterion_id)
        current = after_criteria.get(criterion_id)
        prior_status = str(prior.status) if prior is not None else ""
        current_status = str(current.status) if current is not None else ""
        if prior_status == current_status:
            continue
        criterion_source = current or prior
        criterion_changes.append(AgentCriterionTransitionView(
            criterion_id,
            prior_status,
            current_status,
            _bounded(criterion_source.reason) if criterion_source is not None else "",
            _bounded_refs(
                criterion_source.evidence_refs if criterion_source is not None else (),
                max_evidence_refs,
            ),
        ))

    before_outputs = {item.output_id: item for item in before.outputs} if before else {}
    after_outputs = {item.output_id: item for item in after.outputs} if after else {}
    output_changes = []
    for output_id in sorted(before_outputs.keys() | after_outputs.keys()):
        prior_output = before_outputs.get(output_id)
        current_output = after_outputs.get(output_id)
        if prior_output is None:
            operation = "became_available"
        elif current_output is None:
            operation = "became_unavailable"
        elif (
            prior_output.value != current_output.value
            or prior_output.evidence_refs != current_output.evidence_refs
        ):
            operation = "updated"
        else:
            continue
        output_source = current_output or prior_output
        output_changes.append(AgentOutputTransitionView(
            output_id,
            operation,
            _bounded_refs(
                output_source.evidence_refs if output_source is not None else (),
                max_evidence_refs,
            ),
        ))

    before_completion = set(before.completion_evidence_refs if before else ())
    after_completion = set(after.completion_evidence_refs if after else ())
    return AgentProgressDeltaView(
        str(before.status) if before is not None else "",
        str(after.status) if after is not None else "",
        _bounded_items(tuple(criterion_changes), max_changes),
        _bounded_items(tuple(output_changes), max_changes),
        _bounded_items(tuple(sorted(after_completion - before_completion)), max_evidence_refs),
        _bounded_items(tuple(sorted(before_completion - after_completion)), max_evidence_refs),
    )


def _bounded_refs(values: tuple[str, ...], limit: int) -> BoundedSection[str]:
    return _bounded_items(tuple(values), limit)


def _bounded_items(values: tuple, limit: int) -> BoundedSection:
    shown = values[:limit]
    return BoundedSection(shown, len(values), len(values) > len(shown))


def _bounded(value: str) -> str:
    return value if len(value) <= _MAX_REASON else value[: _MAX_REASON - 1] + "…"


def _bounded_details(value: Mapping[str, object]) -> Mapping[str, object]:
    return {str(key): _bounded_detail(item) for key, item in value.items()}


def _bounded_detail(value: object) -> object:
    if isinstance(value, str):
        return _bounded(value)
    if isinstance(value, Mapping):
        return _bounded_details(value)
    if isinstance(value, tuple | list):
        return tuple(_bounded_detail(item) for item in value[:32])
    return value
