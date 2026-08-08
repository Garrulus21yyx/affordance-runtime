"""One-way construction of a fresh disposable AgentContext for each policy turn."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus, TaskEvaluation
from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.model_boundary.context import (
    AgentBudgetView,
    AgentContext,
    AgentPendingView,
    AgentProgressView,
    ContextIdentity,
    DecisionMode,
    IntentContextView,
    IntentExcerptView,
)
from affordance_runtime.model_boundary.contracts import AgentActionPageView
from affordance_runtime.model_boundary.projection import (
    project_action_space,
    project_plan,
    project_public_value,
    project_task,
    project_turns,
)
from affordance_runtime.model_boundary.world_projection import fit_model_world, project_model_world
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.action_paging import ActionPager, InternalActionPage
from affordance_runtime.world.contracts import ActionSpace
from affordance_runtime.world.view import build_agent_world_view

if TYPE_CHECKING:
    from affordance_runtime.agent.state import AgentLoopState


@dataclass(frozen=True)
class ContextBuilder:
    budget: ContextProjectionBudget = field(default_factory=ContextProjectionBudget)
    pager: ActionPager = field(default_factory=ActionPager)

    def build(
        self,
        task: TaskGoal,
        state: AgentLoopState,
        action_space: ActionSpace,
        task_evaluation: TaskEvaluation,
        intent_context: IntentContext | None = None,
        action_page: InternalActionPage | None = None,
        observation_count: int = 1,
        context_generation: int = 0,
    ) -> AgentContext:
        world = project_model_world(state.current_observation, self.budget)
        labels = {item.target_id: item.label for item in state.current_observation.targets}
        page = action_page or self.pager.page(
            action_space,
            state.active_objective,
            labels=labels,
        )
        if page.action_space_id != action_space.action_space_id:
            raise ValueError("action page does not belong to the current Internal ActionSpace")
        relevance = dict(page.relevance)
        projected_actions = project_action_space(
            action_space,
            build_agent_world_view(state.current_observation),
            relevance,
        )
        by_id = {item.action_id: item for item in projected_actions.options}
        shown_actions = tuple(by_id[item] for item in page.visible_action_ids if item in by_id)
        actions = AgentActionPageView(
            shown_actions,
            page.total_count,
            len(shown_actions),
            page.has_more,
            page.has_more,
            ("target_id", "relevance_role", "query"),
        )
        history_items = project_turns(state.recent_turns)[-self.budget.max_history_turns :]
        identity = ContextIdentity(
            state.task_revision,
            state.current_observation.observation_id,
            action_space.action_space_id,
            page.page_id,
            state.progress_revision,
            state.pending_revision,
            context_generation,
        )
        truncation = {
            "intent": project_intent_context(intent_context, self.budget).excerpts.truncated,
            "targets": world.targets.truncated,
            "facts": world.facts.truncated,
            "conflicts": world.conflicts.truncated,
            "artifacts": world.artifact_summaries.truncated,
            "actions": actions.truncated,
            "history": len(state.recent_turns) > len(history_items),
        }
        context = AgentContext(
            identity.context_id,
            project_task(task),
            project_intent_context(intent_context, self.budget),
            _progress_view(task, state, task_evaluation, world.facts.items),
            world,
            actions,
            BoundedSection(history_items, len(state.recent_turns), truncation["history"]),
            _pending_view(state),
            AgentBudgetView(
                state.remaining_turns,
                max(0, task.loop_budget.max_observations - observation_count),
                truncation,
            ),
            DecisionMode.ACT,
        )
        return _fit_context(context, self.budget.max_total_serialized_bytes)


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
        items.append(IntentExcerptView(text, excerpt.source_kind, excerpt.source_ref[:240], excerpt.digest[:240]))
    return IntentContextView(BoundedSection(tuple(items), len(excerpts), len(items) < len(excerpts)))


def _progress_view(task, state, evaluation, facts) -> AgentProgressView:
    statuses = {item.criterion_id: item.status for item in evaluation.criteria}
    unresolved = tuple(
        criterion_id(item)
        for item in task.success_criteria
        if statuses.get(criterion_id(item)) != CriterionEvaluationStatus.SATISFIED
    )
    objective = ""
    if state.active_objective is not None:
        objective = str(project_public_value(state.active_objective.desired_state))[:240]
    return AgentProgressView(
        project_plan(state.plan),
        objective,
        evaluation.status,
        tuple(facts),
        unresolved,
        tuple(item for item in task.requested_outputs if item not in {output.output_id for output in evaluation.outputs}),
        False,
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


def _fit_context(context: AgentContext, max_bytes: int) -> AgentContext:
    while serialized_size(context) > max_bytes:
        if context.progress.verified_public_facts:
            progress = replace(context.progress, verified_public_facts=(), truncated=True)
            context = replace(context, progress=progress)
            continue
        if context.history.items:
            history = BoundedSection(
                context.history.items[:-1],
                context.history.total_count,
                context.history.total_count > len(context.history.items) - 1,
            )
            context = replace(context, history=history)
            continue
        if context.intent.excerpts.items:
            excerpts = BoundedSection(
                context.intent.excerpts.items[:-1],
                context.intent.excerpts.total_count,
                context.intent.excerpts.total_count > len(context.intent.excerpts.items) - 1,
            )
            context = replace(context, intent=replace(context.intent, excerpts=excerpts))
            continue
        smaller_world = fit_model_world(context.world, max(1, serialized_size(context.world) - 1))
        if smaller_world != context.world:
            context = replace(context, world=smaller_world)
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
    )
    return replace(context, budgets=replace(context.budgets, section_truncation=flags))
