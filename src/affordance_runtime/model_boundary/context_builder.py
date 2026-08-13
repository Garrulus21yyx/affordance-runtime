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
    AgentHypothesisRejectionView,
    AgentObjectiveCheckpointView,
    AgentObjectiveView,
    AgentPendingView,
    AgentProgressView,
    AgentRequirementHypothesisView,
    AgentRequirementStateView,
    AgentSetControlView,
    AgentTaskFrontierView,
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
from affordance_runtime.model_boundary.projection import (
    project_action_page,
    project_plan,
    project_public_value,
)
from affordance_runtime.model_boundary.task_projection import project_task
from affordance_runtime.model_boundary.world_projection import fit_model_world, project_model_world
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.task.frontier_contracts import (
    ActiveObjective,
    predicate_public_value,
)
from affordance_runtime.task.hypothesis_contracts import (
    HypothesisPredicateAssessment,
    RequirementHypothesisProposer,
    TrackedHypothesisStatus,
)
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.task.set_objective import SetDisposition
from affordance_runtime.task.set_objective import predicate_public_value as set_predicate_public_value
from affordance_runtime.task.set_objective_state import (
    set_allowed_action_ids,
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
    requirement_hypothesis_proposer: RequirementHypothesisProposer | None = None
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
            state.current_observation, world, actions,
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
            _set_control_view(state, action_space),
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
        return self.pager.page(
            action_space,
            state.active_objective,
            query=query,
            target_id=target_id,
            relevance_role=relevance_role or None,
            labels=labels,
            cursor=cursor,
            page_size=self.budget.max_action_options,
            max_destinations_per_option=self.budget.max_destinations_per_option,
            max_targets=self.budget.observation_pinned_capacity,
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
            state.active_objective,
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
    objective = state.active_objective
    if objective is not None:
        values.extend((*objective.direct_target_ids, *objective.enabling_target_ids))
    if state.pending_confirmation is not None:
        values.append(state.pending_confirmation.intent.target_id)
    values.extend(
        target_id
        for hypothesis in state.requirement_hypotheses.active[:8]
        if hypothesis.assessment is HypothesisPredicateAssessment.UNKNOWN
        for target_id in hypothesis.candidate_entity_ids
    )
    current = {item.target_id for item in state.current_observation.targets}
    return tuple(target_id for target_id in dict.fromkeys(values) if target_id in current)[:limit]


def _progress_view(task, state, evaluation, facts, max_unresolved: int) -> AgentProgressView:
    statuses = {item.criterion_id: item.status for item in evaluation.criteria}
    unresolved = tuple(
        criterion_id(item)
        for item in task.success_criteria
        if statuses.get(criterion_id(item)) != CriterionEvaluationStatus.SATISFIED
    )
    objective = ""
    if state.active_objective is not None:
        objective = str(project_public_value(state.active_objective.desired_state))[:240]
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
        plan_summary=project_plan(state.plan),
        active_objective=objective,
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
        task_frontier=_task_frontier_view(state),
        truncated=(
            len(unresolved) > max_unresolved
            or len(unresolved_outputs) > max_unresolved
            or state.progress_event_total_count > len(state.recent_progress_events)
        ),
    )


def _task_frontier_view(state) -> AgentTaskFrontierView | None:
    verified = state.verified_task_state
    if verified is None:
        return None
    active = state.active_objective
    active_view = (
        AgentObjectiveView(
            active.objective_id,
            active.intended_requirement_ids,
            predicate_public_value(active.predicate),
        )
        if isinstance(active, ActiveObjective)
        else None
    )
    latest = verified.objective_checkpoints[-1] if verified.objective_checkpoints else None
    must_advance = bool(
        active_view is None and verified.current_frontier and latest is not None and latest.status.value == "verified"
    )
    return AgentTaskFrontierView(
        tuple(
            AgentRequirementStateView(
                item.requirement_id,
                item.status.value,
                item.evidence_refs,
            )
            for item in verified.requirements
        ),
        verified.current_frontier,
        active_view,
        tuple(
            AgentObjectiveCheckpointView(
                item.objective_id,
                item.intended_requirement_ids,
                predicate_public_value(item.predicate),
                item.status.value,
                item.observation_id,
                item.evidence_refs,
            )
            for item in verified.objective_checkpoints[-8:]
        ),
        tuple(item.fact_ref for item in verified.values[-16:]),
        must_advance,
        latest.objective_id if must_advance and latest is not None else "",
        must_advance,
        tuple(
            AgentRequirementHypothesisView(
                item.hypothesis_id,
                item.summary,
                predicate_public_value(item.predicate),
                item.candidate_entity_ids,
                item.status.value,
                item.assessment.value,
                item.evidence_refs,
            )
            for item in state.requirement_hypotheses.hypotheses
            if item.status is TrackedHypothesisStatus.ACTIVE
        ),
        state.requirement_hypotheses.completeness.value,
        state.requirement_hypothesis_failure_reason,
        tuple(
            AgentHypothesisRejectionView(item.item_index, item.code.value)
            for item in state.recent_requirement_hypothesis_rejections
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


def _set_control_view(
    state: AgentLoopState,
    action_space: ActionSpace,
) -> AgentSetControlView | None:
    active = state.active_set_objective
    if active is None:
        if not state.semantic_control_required:
            return None
        return AgentSetControlView(
            "control_only",
            state.semantic_control_mode.value,
            "semantic_objective_required",
            semantic_mode=state.semantic_control_mode.value,
        )
    reduction = active.reduction
    if reduction.disposition in {
        SetDisposition.READY_FOR_NEXT_MEMBER,
        SetDisposition.AGENT_SELECT_NEXT,
    }:
        allowed = tuple(sorted(set_allowed_action_ids(active, action_space)))
        if allowed:
            mode = "member_actions_only"
        else:
            mode = "blocked"
            return AgentSetControlView(
                mode,
                "need_actionability_resolution",
                "true_member_action_unavailable",
                (),
                len(active.universe.entity_ids),
                len(reduction.true_entity_ids),
                False,
                set_predicate_public_value(active.objective.predicate),
                active.objective.predicate_digest,
                active.candidate_entity_ids,
                (),
                ("resolve_actionability",),
            )
    elif reduction.disposition is SetDisposition.CERTIFIED:
        if state.semantic_control_required:
            mode = "control_only"
            allowed = ()
        else:
            mode = "successor_actions"
            set_members = set(active.candidate_entity_ids) | {
                item.entity_id for item in active.obligations
            }
            allowed = tuple(
                option.action_id
                for option in action_space.options
                if option.target_id not in set_members
            )
    elif reduction.disposition is SetDisposition.BLOCKED:
        mode = "blocked"
        allowed = ()
    else:
        mode = "control_only"
        allowed = ()
    unknown = tuple(
        item.entity_id
        for item in active.assessments
        if item.truth.value == "unknown"
    )
    return AgentSetControlView(
        mode,
        reduction.disposition.value,
        reduction.reason_code,
        allowed,
        len(active.universe.entity_ids),
        len(reduction.true_entity_ids),
        reduction.certificate is not None,
        set_predicate_public_value(active.objective.predicate),
        active.objective.predicate_digest,
        active.candidate_entity_ids,
        unknown,
        tuple(item.kind.value for item in set_evidence_obligations(active)),
        state.semantic_control_mode.value if state.semantic_control_required else "",
        active.objective.action_template.parameters,
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
    if context.set_control is None:
        payload.pop("set_control", None)
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
