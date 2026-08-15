"""One-way construction of a fresh disposable AgentContext for each policy turn."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from affordance_runtime.actions.paging import ActionPager, InternalActionPage
from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.acquisition_projection import project_acquisition_offers
from affordance_runtime.agent.context.action_candidate_projection import close_action_candidates
from affordance_runtime.agent.context.actor_world_snapshot import project_actor_world_snapshot
from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.agent.context.context import (
    AgentContext,
    AgentProgressView,
    ContextIdentity,
)
from affordance_runtime.agent.context.contracts import AgentActionPageView, AgentTurnView
from affordance_runtime.agent.context.grounding_projection import GroundingProjection
from affordance_runtime.agent.context.projection import project_action_page
from affordance_runtime.agent.context.task_projection import project_task
from affordance_runtime.agent.context.world_projection import fit_model_world, project_model_world
from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus, TaskEvaluation
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.world.acquisition import ObservationCapabilities
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.view import build_agent_world_view

_PINNED_ACTION_WORLD_RESERVE_BYTES = 4_096


@dataclass(frozen=True)
class ContextBuilder:
    budget: ContextProjectionBudget = field(default_factory=ContextProjectionBudget)
    pager: ActionPager = field(default_factory=ActionPager)
    grounding_projection: GroundingProjection = field(default_factory=GroundingProjection)

    def build(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        action_space: ActionSpace,
        task_evaluation: TaskEvaluation,
        recent_steps: tuple[AgentTurnView, ...] = (),
        recent_step_total_count: int | None = None,
        action_page: InternalActionPage | None = None,
        context_generation: int = 0,
        observation_capabilities: ObservationCapabilities = ObservationCapabilities(False, False),
    ) -> AgentContext:
        default_page = self.page(action_space, observation)
        page = action_page or default_page
        if page.action_space_id != action_space.action_space_id:
            raise ValueError("action page does not belong to the current Internal ActionSpace")
        if page.objective_digest != default_page.objective_digest:
            raise ValueError("action page relevance belongs to a previous context")
        projected_actions = project_action_page(
            action_space,
            page,
            build_agent_world_view(observation),
            self.budget.max_destinations_per_option,
        )
        shown_actions = projected_actions.options
        pinned_targets = _pinned_targets(
            shown_actions,
            observation,
            self.budget.observation_pinned_capacity,
        )
        world = project_model_world(
            observation,
            self.budget,
            pinned_targets,
            observation_capabilities=project_acquisition_offers(observation_capabilities),
            observation_cursor="",
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
        history_items = tuple(recent_steps[-self.budget.max_history_turns :])
        history_total = len(recent_steps) if recent_step_total_count is None else recent_step_total_count
        if history_total < len(recent_steps):
            raise ValueError("recent step total cannot be smaller than the retained steps")
        identity = _context_identity(task.revision, observation, action_space, page, context_generation)
        grounding = self.grounding_projection.project(
            observation,
            world,
            actions,
        )
        actions = close_action_candidates(actions, grounding.index, context_id=identity.context_id)
        progress = _progress_view(
            task,
            task_evaluation,
            world.facts.items,
            self.budget.max_unresolved_items,
        )
        actor_world = project_actor_world_snapshot(
            observation,
            world,
            grounding.index,
            grounding.images,
            max_structure_nodes=self.budget.max_targets * 2,
        )
        context = AgentContext(
            identity.context_id,
            project_task(task),
            progress,
            world,
            actions,
            BoundedSection(
                history_items,
                history_total,
                history_total > len(history_items),
            ),
            actor_world,
            grounding.images,
            grounding.index,
        )
        context = _fit_context(context, self.budget.max_total_serialized_bytes, pinned_targets)
        actor_world = project_actor_world_snapshot(
            observation,
            context.world,
            grounding.index,
            grounding.images,
            max_structure_nodes=self.budget.max_targets * 2,
        )
        return replace(context, actor_world=actor_world)

    def page(
        self,
        action_space: ActionSpace,
        observation: WorldObservation,
        *,
        query: str = "",
        target_id: str = "",
        relevance_role: str = "",
        cursor: str = "",
    ) -> InternalActionPage:
        labels = {item.target_id: item.label for item in observation.targets}
        return self.pager.page(
            action_space,
            None,
            query=query,
            target_id=target_id,
            relevance_role=relevance_role or None,
            labels=labels,
            cursor=cursor,
            page_size=min(
                self.budget.max_action_options,
                max(
                    1,
                    self.budget.max_total_serialized_bytes
                    // _PINNED_ACTION_WORLD_RESERVE_BYTES,
                ),
            ),
            max_destinations_per_option=self.budget.max_destinations_per_option,
            max_targets=self.budget.observation_pinned_capacity,
        )


def _context_identity(task_revision, observation, action_space, page, generation: int) -> ContextIdentity:
    return ContextIdentity(
        task_revision,
        observation.observation_id,
        action_space.action_space_id,
        page.page_id,
        generation,
    )


def _pinned_targets(actions, observation, limit: int) -> tuple[str, ...]:
    values = [
        target_id
        for option in actions
        for target_id in (option.target_id, *(item.destination_id for item in option.destinations.items))
    ]
    current = {item.target_id for item in observation.targets}
    return tuple(target_id for target_id in dict.fromkeys(values) if target_id in current)[:limit]


def _progress_view(task, evaluation, facts, max_unresolved: int) -> AgentProgressView:
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
        truncated=(
            len(unresolved) > max_unresolved
            or len(unresolved_outputs) > max_unresolved
        ),
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
        if len(context.recent_steps.items) > 1:
            history = BoundedSection(
                context.recent_steps.items[1:],
                context.recent_steps.total_count,
                context.recent_steps.total_count > len(context.recent_steps.items) - 1,
            )
            context = replace(context, recent_steps=history)
            continue
        raise ValueError("AgentContext fixed sections exceed the total serialized byte budget")
    return context


def _semantic_serialized_size(context: AgentContext) -> int:
    payload = to_json_compatible({
        "task": context.task,
        "observation": context.actor_world,
        "progress": context.progress,
        "recent_steps": context.recent_steps,
    })
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
