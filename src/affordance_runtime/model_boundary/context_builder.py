"""One-way construction of a fresh disposable AgentContext for each policy turn."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from affordance_runtime.agent.progress_projection import project_progress_events
from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus, TaskEvaluation
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.acquisition_projection import project_acquisition_offers
from affordance_runtime.model_boundary.budgets import (
    DEFAULT_MAX_TOTAL_WAIT_MS,
    BoundedSection,
    ContextProjectionBudget,
    serialized_size,
)
from affordance_runtime.model_boundary.context import (
    AgentBudgetView,
    AgentContext,
    AgentExecutionControlView,
    AgentPendingView,
    AgentProgressView,
    ContextIdentity,
    DecisionMode,
    IntentContextView,
    IntentExcerptView,
)
from affordance_runtime.model_boundary.contracts import AgentActionPageView
from affordance_runtime.model_boundary.control_feedback_projection import project_control_feedback
from affordance_runtime.model_boundary.control_transition_projection import (
    project_control_transitions,
)
from affordance_runtime.model_boundary.grounding_projection import GroundingProjection
from affordance_runtime.model_boundary.projection import project_action_page
from affordance_runtime.model_boundary.task_projection import project_task
from affordance_runtime.model_boundary.world_projection import fit_model_world, project_model_world
from affordance_runtime.task.aggregate_objective import (
    AggregateDisposition,
    AggregateObjectiveState,
    aggregate_objective_public_value,
)
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.task.execution_control import (
    step_execution_action_parameters,
    step_execution_allowed_action_ids,
    step_execution_authority_digest,
)
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.task.objective_sequence import ObjectiveSequenceState, SequenceDisposition
from affordance_runtime.task.set_objective import SetDisposition, predicate_public_value
from affordance_runtime.task.set_objective_state import (
    SetObjectiveState,
    set_evidence_obligations,
)
from affordance_runtime.world.acquisition import ObservationCapabilities
from affordance_runtime.world.action_paging import ActionPager, InternalActionPage
from affordance_runtime.world.contracts import ActionSpace
from affordance_runtime.world.view import build_agent_world_view

if TYPE_CHECKING:
    from affordance_runtime.agent.state import AgentLoopState


@dataclass(frozen=True)
class ContextBuilder:
    budget: ContextProjectionBudget = field(default_factory=ContextProjectionBudget)
    pager: ActionPager = field(default_factory=ActionPager)
    grounding_projection: GroundingProjection = field(default_factory=GroundingProjection)

    def build(
        self,
        task: TaskGoal,
        state: AgentLoopState,
        action_space: ActionSpace,
        task_evaluation: TaskEvaluation,
        intent_context: IntentContext | None = None,
        action_page: InternalActionPage | None = None,
        observation_count: int = 1,
        waited_ms: int = 0,
        context_generation: int = 0,
        observation_capabilities: ObservationCapabilities = ObservationCapabilities(False, False),
    ) -> AgentContext:
        default_page = self.page(action_space, state)
        page = action_page or default_page
        if page.action_space_id != action_space.action_space_id:
            raise ValueError("action page does not belong to the current Internal ActionSpace")
        if page.objective_digest != default_page.objective_digest:
            raise ValueError("action page relevance belongs to a previous LocalObjective")
        projected_actions = project_action_page(
            action_space,
            page,
            build_agent_world_view(state.current_observation),
            self.budget.max_destinations_per_option,
        )
        shown_actions = projected_actions.options
        pinned_targets = _pinned_targets(
            shown_actions,
            state,
            self.budget.observation_pinned_capacity,
        )
        world = project_model_world(
            state.current_observation,
            self.budget,
            pinned_targets,
            observation_capabilities=project_acquisition_offers(observation_capabilities),
            observation_cursor=state.observation_cursor,
        )
        visible_targets = {item.target_id for item in world.targets.items}
        if any(target_id not in visible_targets for target_id in pinned_targets):
            raise ValueError("current action page target is absent from ModelWorldView")
        actions = AgentActionPageView(
            shown_actions,
            page.total_count,
            len(shown_actions),
            page.total_count > len(shown_actions),
            page.has_more,
            ("target_id", "relevance_role", "query"),
            page.query,
            page.target_id,
            page.relevance_role.value if page.relevance_role else "",
            page.next_cursor,
        )
        history_items = project_control_transitions(state.recent_control_transitions)[-self.budget.max_history_turns :]
        identity = _context_identity(state, action_space, page, context_generation)
        truncation = {
            "intent": project_intent_context(intent_context, self.budget).excerpts.truncated,
            "targets": world.targets.truncated,
            "facts": world.facts.truncated,
            "conflicts": world.conflicts.truncated,
            "artifacts": world.artifact_summaries.truncated,
            "actions": actions.truncated,
            "history": state.control_transition_total_count > len(history_items),
        }
        grounding = self.grounding_projection.project(
            state.current_observation,
            world,
            actions,
        )
        context = AgentContext(
            identity.context_id,
            project_task(task),
            project_intent_context(intent_context, self.budget),
            _progress_view(task, state, task_evaluation, world.facts.items, self.budget.max_unresolved_items),
            world,
            actions,
            BoundedSection(
                history_items,
                state.control_transition_total_count,
                truncation["history"],
            ),
            _pending_view(state),
            AgentBudgetView(
                state.remaining_turns,
                max(0, task.loop_budget.max_observations - observation_count),
                max(0, DEFAULT_MAX_TOTAL_WAIT_MS - waited_ms),
                truncation,
            ),
            DecisionMode.ACT,
            project_control_feedback(state.pending_control_feedback),
            grounding.images,
            grounding.index,
            _execution_control_view(state, action_space),
        )
        return _fit_context(context, self.budget.max_total_serialized_bytes, pinned_targets)

    def page(
        self,
        action_space: ActionSpace,
        state: AgentLoopState,
        *,
        query: str = "",
        target_id: str = "",
        relevance_role: str = "",
        cursor: str = "",
    ) -> InternalActionPage:
        labels = {item.target_id: item.label for item in state.current_observation.targets}
        execution = state.active_step_execution
        allowed_action_ids = (
            step_execution_allowed_action_ids(execution, action_space)
            if execution is not None
            else frozenset()
            if state.semantic_control_required
            else None
        )
        return self.pager.page(
            action_space,
            None,
            query=query,
            target_id=target_id,
            relevance_role=relevance_role or None,
            labels=labels,
            cursor=cursor,
            page_size=self.budget.max_action_options,
            max_destinations_per_option=self.budget.max_destinations_per_option,
            max_targets=self.budget.observation_pinned_capacity,
            allowed_action_ids=allowed_action_ids,
            authority_digest=step_execution_authority_digest(execution, action_space),
        )

    def execution_page(
        self,
        action_space: ActionSpace,
        state: AgentLoopState,
        action_id: str,
        destination_id: str = "",
    ) -> InternalActionPage:
        return self.pager.single_action_page(
            action_space,
            None,
            action_id,
            destination_id,
            max_destinations_per_option=self.budget.max_destinations_per_option,
        )


def project_intent_context(
    intent: IntentContext | None,
    budget: ContextProjectionBudget,
) -> IntentContextView:
    excerpts = () if intent is None else intent.excerpts
    shown_count = min(len(excerpts), budget.max_intent_excerpts)
    per_excerpt = budget.max_intent_chars // shown_count if shown_count else budget.max_intent_chars
    items = []
    for excerpt in excerpts[: budget.max_intent_excerpts]:
        text = excerpt.text[:per_excerpt]
        source_id = f"source:{hashlib.sha256(excerpt.source_ref.encode()).hexdigest()}"
        digest = excerpt.digest.casefold()
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            digest = f"sha256:{hashlib.sha256(excerpt.text.encode()).hexdigest()}"
        items.append(IntentExcerptView(text, excerpt.source_kind, source_id, digest))
    return IntentContextView(BoundedSection(tuple(items), len(excerpts), len(items) < len(excerpts)))


def _context_identity(state, action_space, page, generation: int) -> ContextIdentity:
    return ContextIdentity(
        state.task_revision,
        state.current_observation.observation_id,
        action_space.action_space_id,
        page.page_id,
        state.progress_revision,
        state.pending_revision,
        generation,
    )


def _pinned_targets(actions, state, limit: int) -> tuple[str, ...]:
    values = [
        target_id
        for option in actions
        for target_id in (option.target_id, *(item.destination_id for item in option.destinations.items))
    ]
    if state.pending_confirmation is not None:
        values.append(state.pending_confirmation.intent.target_id)
    current = {item.target_id for item in state.current_observation.targets}
    return tuple(target_id for target_id in dict.fromkeys(values) if target_id in current)[:limit]


def _progress_view(task, state, evaluation, facts, max_unresolved: int) -> AgentProgressView:
    statuses = {item.criterion_id: item.status for item in evaluation.criteria}
    unresolved = tuple(
        criterion_id(item)
        for item in task.success_criteria
        if statuses.get(criterion_id(item)) != CriterionEvaluationStatus.SATISFIED
    )
    unresolved_outputs = tuple(
        item for item in task.requested_outputs if item not in {output.output_id for output in evaluation.outputs}
    )
    evidence_refs = {
        *evaluation.completion_evidence_refs,
        *(ref for item in evaluation.criteria for ref in item.evidence_refs),
        *(ref for item in evaluation.outputs for ref in item.evidence_refs),
    }
    verified = tuple(item for item in facts if item.fact_ref in evidence_refs)
    return AgentProgressView(
        validated_task_status=evaluation.status,
        verified_public_facts=verified,
        unresolved_criteria=BoundedSection(
            unresolved[:max_unresolved], len(unresolved), len(unresolved) > max_unresolved
        ),
        unresolved_outputs=BoundedSection(
            unresolved_outputs[:max_unresolved],
            len(unresolved_outputs),
            len(unresolved_outputs) > max_unresolved,
        ),
        events=project_progress_events(state),
        active_plan_step=state.active_step_execution is not None,
        truncated=(
            len(unresolved) > max_unresolved
            or len(unresolved_outputs) > max_unresolved
            or state.progress_event_total_count > len(state.recent_progress_events)
        ),
    )


def _pending_view(state: AgentLoopState) -> AgentPendingView:
    confirmation = ""
    if state.pending_confirmation is not None:
        confirmation = "confirmation required for current semantic action"
    return AgentPendingView(
        "user input required" if state.pending_user_question else "",
        confirmation,
        "effect outcome remains uncertain" if state.pending_unknown_request is not None else "",
    )


def _execution_control_view(
    state: AgentLoopState,
    action_space: ActionSpace,
) -> AgentExecutionControlView | None:
    execution = state.active_step_execution
    if execution is None:
        if not state.semantic_control_required:
            return None
        return AgentExecutionControlView(
            "control_only",
            state.semantic_control_mode.value,
            "no_active_plan_step",
            semantic_mode=state.semantic_control_mode.value,
        )
    allowed = tuple(sorted(step_execution_allowed_action_ids(execution, action_space)))
    parameters = step_execution_action_parameters(execution)
    if isinstance(execution, ObjectiveSequenceState):
        step = execution.active_step
        selector = step.selector if step is not None else execution.pending_postcondition
        mode = (
            "member_actions_only"
            if execution.disposition is SequenceDisposition.READY and allowed
            else "blocked"
            if execution.disposition is SequenceDisposition.BLOCKED
            else "control_only"
        )
        return AgentExecutionControlView(
            mode,
            execution.disposition.value,
            execution.reason_code,
            allowed if mode == "member_actions_only" else (),
            len(state.current_observation.targets),
            1 if execution.resolved_target_id else 0,
            execution.disposition is SequenceDisposition.COMPLETE,
            predicate_public_value(selector.predicate) if selector is not None else {},
            selector.digest if selector is not None else "",
            tuple(item.target_id for item in state.current_observation.targets),
            execution.unknown_target_ids,
            (
                ("classify_predicate",)
                if execution.disposition is SequenceDisposition.NEED_EVIDENCE
                else ("refresh_stability",)
                if execution.disposition is SequenceDisposition.WAITING_POSTCONDITION
                else ()
            ),
            state.semantic_control_mode.value,
            parameters,
        )
    if isinstance(execution, AggregateObjectiveState):
        mode = (
            "member_actions_only"
            if execution.disposition is AggregateDisposition.READY and allowed
            else "blocked"
            if execution.disposition is AggregateDisposition.BLOCKED
            else "control_only"
        )
        unknown = tuple(entity_id for entity_id, truth in execution.member_truth if truth.value == "unknown")
        evidence_need = {
            AggregateDisposition.NEED_SCOPE_CLOSURE: "enumerate_scope",
            AggregateDisposition.NEED_CLASSIFICATION: "classify_predicate",
            AggregateDisposition.NEED_VALUES: "extract_values",
            AggregateDisposition.NEED_DESTINATION: "resolve_destination",
            AggregateDisposition.NEED_EFFECT_RESOLUTION: "verify_item_effect",
        }.get(execution.disposition)
        return AgentExecutionControlView(
            mode,
            execution.disposition.value,
            execution.reason_code,
            allowed if mode == "member_actions_only" else (),
            len(execution.universe.entity_ids),
            sum(truth.value == "true" for _, truth in execution.member_truth),
            execution.disposition is AggregateDisposition.COMPLETE,
            aggregate_objective_public_value(execution.objective),
            execution.objective.digest,
            execution.universe.entity_ids,
            unknown,
            (evidence_need,) if evidence_need else (),
            state.semantic_control_mode.value,
            parameters,
        )
    assert isinstance(execution, SetObjectiveState)
    reduction = execution.reduction
    mode = (
        "member_actions_only"
        if reduction.disposition in {SetDisposition.READY_FOR_NEXT_MEMBER, SetDisposition.AGENT_SELECT_NEXT}
        and allowed
        else "blocked"
        if reduction.disposition is SetDisposition.BLOCKED
        else "control_only"
    )
    unknown = tuple(item.entity_id for item in execution.assessments if item.truth.value == "unknown")
    return AgentExecutionControlView(
        mode,
        reduction.disposition.value,
        reduction.reason_code,
        allowed if mode == "member_actions_only" else (),
        len(execution.universe.entity_ids),
        len(reduction.true_entity_ids),
        reduction.certificate is not None,
        predicate_public_value(execution.objective.predicate),
        execution.objective.predicate_digest,
        execution.candidate_entity_ids,
        unknown,
        tuple(item.kind.value for item in set_evidence_obligations(execution)),
        state.semantic_control_mode.value,
        parameters,
    )


def _fit_context(
    context: AgentContext,
    max_bytes: int,
    pinned_target_ids: tuple[str, ...],
) -> AgentContext:
    while _semantic_serialized_size(context) > max_bytes:
        try:
            smaller_world = fit_model_world(
                context.world,
                max(1, serialized_size(context.world) - 1),
                pinned_target_ids,
                allow_target_removal=False,
            )
        except ValueError:
            smaller_world = context.world
        if smaller_world != context.world:
            context = replace(context, world=smaller_world)
            continue
        if context.progress.verified_public_facts:
            progress = replace(context.progress, verified_public_facts=(), truncated=True)
            context = replace(context, progress=progress)
            continue
        if context.progress.events.items:
            events = BoundedSection(
                context.progress.events.items[1:],
                context.progress.events.total_count,
                True,
            )
            context = replace(
                context,
                progress=replace(context.progress, events=events, truncated=True),
            )
            continue
        if len(context.history.items) > 1:
            history = BoundedSection(
                context.history.items[1:],
                context.history.total_count,
                context.history.total_count > len(context.history.items) - 1,
            )
            context = replace(context, history=history)
            continue
        if context.intent.excerpts.items:
            excerpts = BoundedSection(
                context.intent.excerpts.items[1:],
                context.intent.excerpts.total_count,
                context.intent.excerpts.total_count > len(context.intent.excerpts.items) - 1,
            )
            context = replace(context, intent=replace(context.intent, excerpts=excerpts))
            continue
        raise ValueError("AgentContext fixed sections exceed the total serialized byte budget")
    flags = dict(context.budgets.section_truncation)
    flags.update(
        intent=context.intent.excerpts.truncated,
        targets=context.world.targets.truncated,
        facts=context.world.facts.truncated,
        conflicts=context.world.conflicts.truncated,
        artifacts=context.world.artifact_summaries.truncated,
        history=context.history.truncated,
        progress_events=context.progress.events.truncated,
    )
    return replace(context, budgets=replace(context.budgets, section_truncation=flags))


def _semantic_serialized_size(context: AgentContext) -> int:
    payload = to_json_compatible(replace(context, image_inputs=()))
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
