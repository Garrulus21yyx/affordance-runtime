"""One-way construction of a fresh disposable AgentContext for each policy turn."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from affordance_runtime.actions.paging import (
    ActionDiscoveryMatch,
    ActionDiscoveryResult,
    ActionPager,
    InternalActionPage,
    canonical_action_query,
)
from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.acquisition_projection import project_acquisition_offers
from affordance_runtime.agent.context.action_candidate_projection import (
    build_action_delivery_plan,
    close_action_candidates,
    project_action_candidates,
)
from affordance_runtime.agent.context.actor_world_snapshot import project_actor_world_snapshot
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.context import AgentContext, ContextIdentity
from affordance_runtime.agent.context.contracts import AgentActionPageView
from affordance_runtime.agent.context.grounding_projection import (
    GroundingProjection,
    GroundingProjectionResult,
)
from affordance_runtime.agent.context.projection import project_action_page, project_action_space
from affordance_runtime.agent.context.task_projection import project_task
from affordance_runtime.agent.context.world_projection import (
    ModelWorldView,
    project_model_world,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records
from affordance_runtime.goals.plan import Failed, GoalPlanResolution, NeedsInput
from affordance_runtime.goals.projection import project_agent_goal_plan
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import ObservationCapabilities
from affordance_runtime.world.contracts import CoverageState, WorldObservation


@dataclass(frozen=True)
class ContextBuilder:
    budget: ContextProjectionBudget = field(default_factory=ContextProjectionBudget)
    pager: ActionPager = field(default_factory=ActionPager)
    grounding_projection: GroundingProjection = field(default_factory=GroundingProjection)
    include_public_text_evidence: bool = True

    def build(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        action_space: ActionSpace,
        task_evaluation: TaskEvaluation,
        workspace: AgentWorkspace = AgentWorkspace(),
        action_page: InternalActionPage | None = None,
        context_generation: int = 0,
        current_step_index: int = 0,
        observation_capabilities: ObservationCapabilities = ObservationCapabilities(False, False),
        goal_resolution: GoalPlanResolution | None = None,
        runtime_controls: tuple[str, ...] = (),
        region_index: WorldDeliveryIndex | None = None,
        canonical_world: CanonicalPublicWorldProjection | None = None,
        control_feedback: dict[str, object] | None = None,
        action_discovery: ActionDiscoveryResult | None = None,
        last_step: StepResult | None = None,
    ) -> AgentContext:
        if task_evaluation.observation_id != observation.observation_id:
            raise ValueError("context task evaluation belongs to a previous observation")
        current_region_index = region_index or WorldDeliveryIndex.from_observation(
            observation,
            action_space.options,
        )
        canonical_world = canonical_world or CanonicalPublicWorldProjection.build(
            observation, current_region_index, action_space
        )
        canonical_world.assert_current(observation, current_region_index, action_space)
        page = action_page or self.page(
            action_space,
            observation,
            region_index=current_region_index,
        )
        if page.action_space_id != action_space.action_space_id:
            raise ValueError("action page does not belong to the current Internal ActionSpace")
        projected_actions = project_action_page(
            action_space,
            page,
            {item.target_id: item.label for item in observation.targets},
        )
        complete_projected_actions = project_action_space(
            action_space,
            {item.target_id: item.label for item in observation.targets},
        )
        complete_action_ids = {item.action_id for item in complete_projected_actions.options}
        if set(current_region_index.action_region_keys) != complete_action_ids:
            raise ValueError("delivery index does not contain the complete current ActionSpace")
        if current_region_index.world_observation_id != observation.observation_id:
            raise ValueError("region index belongs to a previous observation")
        shown_actions = projected_actions.options
        pinned_targets = _pinned_targets(
            shown_actions,
            observation,
            self.budget.observation_pinned_capacity(len(observation.targets)),
        )
        world = project_model_world(
            observation,
            self.budget,
            pinned_targets,
            observation_capabilities=project_acquisition_offers(observation_capabilities),
            observation_cursor="",
            lossless_public=True,
            canonical_projection=canonical_world,
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
            page.query,
            page.next_cursor,
        )
        if not isinstance(workspace, AgentWorkspace):
            raise TypeError("context builder requires typed AgentWorkspace")
        history_items = workspace.recent_steps
        complete_page = AgentActionPageView(
            complete_projected_actions.options,
            len(complete_projected_actions.options),
            len(complete_projected_actions.options),
            False,
            False,
        )
        grounding = self.grounding_projection.project(
            observation,
            canonical_world,
            world,
        )
        goal_plan = _current_goal_plan(
            task,
            goal_resolution,
            max_items=self.budget.max_unresolved_items,
        )
        identity = _context_identity(
            task.revision,
            observation,
            action_space,
            page,
            context_generation,
            goal_plan,
            _tool_catalog_digest(
                complete_page,
                world,
                grounding,
                runtime_controls,
            ),
        )
        actions = close_action_candidates(actions, grounding.index, context_id=identity.context_id)
        complete_page = close_action_candidates(
            complete_page,
            grounding.index,
            context_id=identity.context_id,
        )
        base_candidate_projection = project_action_candidates(
            complete_page.options,
            action_space_id=action_space.action_space_id,
            world_observation_id=observation.observation_id,
            region_index=current_region_index,
            region_refs=canonical_world.region_refs,
            instruction=task.instruction,
            objectives=tuple(item.objective for item in goal_plan.items),
            done_when=tuple(item.done_when for item in goal_plan.items),
            recent_outcomes=history_items,
            top_k=5,
        )
        action_delivery_plan = build_action_delivery_plan(
            action_space_id=action_space.action_space_id,
            world_observation_id=observation.observation_id,
            base_actions=actions.options,
            complete_actions=complete_page.options,
            automatic=base_candidate_projection,
            region_index=current_region_index,
            region_refs=canonical_world.region_refs,
            discovery=action_discovery,
            action_space_issues=action_space.issues,
            target_refs=grounding.index.target_refs,
        )
        candidate_projection = action_delivery_plan.projection(action_delivery_plan.bounded_preview_counts())
        return _fit_context(
            identity.context_id,
            task,
            task_evaluation,
            goal_plan,
            observation,
            canonical_world,
            world,
            actions,
            workspace,
            grounding,
            self.budget,
            current_step_index,
            runtime_controls,
            current_region_index,
            control_feedback or {},
            self.include_public_text_evidence,
            complete_page.options,
            action_space.action_space_id,
            candidate_projection,
            action_delivery_plan,
            last_step,
        )

    def page(
        self,
        action_space: ActionSpace,
        observation: WorldObservation,
        *,
        query: str = "",
        cursor: str = "",
        region_index: WorldDeliveryIndex | None = None,
    ) -> InternalActionPage:
        targets = {item.target_id: item for item in observation.targets}
        labels = {target_id: item.label for target_id, item in targets.items()}
        region_index = region_index or WorldDeliveryIndex.from_observation(
            observation,
            action_space.options,
        )
        if region_index.world_observation_id != observation.observation_id:
            raise ValueError("delivery index belongs to a previous observation")
        contexts = region_index.target_contexts
        return self.pager.page(
            action_space,
            None,
            query=query,
            labels=labels,
            roles={target_id: item.role for target_id, item in targets.items()},
            states={target_id: item.state for target_id, item in targets.items()},
            functional_paths={target_id: region_index.functional_path_for_target(target_id) for target_id in targets},
            focused_target_ids=frozenset(target_id for target_id, item in contexts.items() if item.focused),
            viewport_target_ids=frozenset(
                target_id for target_id, item in contexts.items() if item.viewport == "visible"
            ),
            cursor=cursor,
            page_size=min(
                self.budget.max_action_options,
                self.pager.page_size,
            ),
        )

    def discovery_result(
        self,
        action_space: ActionSpace,
        observation: WorldObservation,
        page: InternalActionPage,
        *,
        region_index: WorldDeliveryIndex | None = None,
        canonical_world: CanonicalPublicWorldProjection,
    ) -> ActionDiscoveryResult:
        """Close a page into its public typed result at the discovery owner."""

        current_index = region_index or WorldDeliveryIndex.from_observation(observation, action_space.options)
        if current_index.world_observation_id != observation.observation_id:
            raise ValueError("delivery index belongs to a previous observation")
        canonical_world.assert_current(observation, current_index, action_space)
        targets = {item.target_id: item for item in observation.targets}
        labels = {target_id: item.label for target_id, item in targets.items()}
        projected = project_action_page(action_space, page, labels)
        pinned = _pinned_targets(
            projected.options,
            observation,
            self.budget.observation_pinned_capacity(len(observation.targets)),
        )
        model_world = project_model_world(
            observation,
            self.budget,
            pinned,
            lossless_public=True,
            canonical_projection=canonical_world,
        )
        grounding = self.grounding_projection.project(observation, canonical_world, model_world)
        query = canonical_action_query(page.query)
        def page_matches(current_page: InternalActionPage) -> tuple[ActionDiscoveryMatch, ...]:
            current_projected = project_action_page(action_space, current_page, labels)
            current_labels = {item.action_id: item.target_label for item in current_projected.options}
            current_view = close_action_candidates(
                AgentActionPageView(
                    current_projected.options,
                    current_page.total_count,
                    len(current_projected.options),
                    current_page.total_count > len(current_projected.options),
                    current_page.has_more,
                    current_page.query,
                    current_page.next_cursor,
                ),
                grounding.index,
                context_id="context:action-discovery",
            )
            values = []
            for item in current_view.options:
                public_label = current_labels.get(item.action_id, "") or item.target_label
                target = targets.get(item.target_id)
                public_role = (target.role if target is not None else "") or item.target_role
                values.append(
                    ActionDiscoveryMatch(
                        item.target_ref,
                        public_label,
                        public_role,
                        item.operation,
                        tuple(destination.grounding_ref for destination in item.destinations.items),
                        _discovery_match_kinds(query, public_label, public_role, item.operation),
                    )
                )
            return tuple(values)

        matches = page_matches(page)
        coverage = (
            "complete"
            if all(source.coverage is CoverageState.COMPLETE for source in observation.sources)
            else "partial"
        )
        return ActionDiscoveryResult(
            matches,
            query,
            coverage,
            "empty" if not matches else "partial" if page.has_more else "complete",
            (),
            "",
        )

def _context_identity(
    task_revision,
    observation,
    action_space,
    page,
    generation: int,
    goal_plan,
    tool_catalog_digest: str,
) -> ContextIdentity:
    return ContextIdentity(
        task_revision,
        observation.observation_id,
        action_space.action_space_id,
        page.page_id,
        generation,
        goal_plan.resolution,
        goal_plan.plan_version,
        goal_plan.plan_digest,
        tool_catalog_digest,
    )


def _current_goal_plan(
    task: TaskGoal,
    resolution: GoalPlanResolution | None,
    *,
    max_items: int,
):
    effective = resolution or Failed(task.revision, "goal_guidance_unavailable")
    if isinstance(effective, NeedsInput):
        raise ValueError("NeedsInput cannot enter an ActionPolicy context")
    if effective.task_revision != task.revision:
        raise ValueError("goal plan resolution belongs to a previous task revision")
    return project_agent_goal_plan(effective, max_items=max_items)


def _tool_catalog_digest(
    actions,
    world,
    grounding: GroundingProjectionResult,
    runtime_controls: tuple[str, ...],
) -> str:
    """Bind identity to the exact current inputs that determine the public tool catalog."""

    payload = to_json_compatible(
        {
            "actions": actions,
            "observation_capabilities": world.observation_capabilities,
            "world_targets": world.targets,
            "grounding_entities": grounding.index.entities,
            "runtime_controls": tuple(runtime_controls),
        }
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _pinned_targets(
    actions,
    observation,
    limit: int,
    *,
    extra_target_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    page_values = [
        target_id
        for option in actions
        for target_id in (option.target_id, *(item.destination_id for item in option.destinations.items))
    ]
    values = [*extra_target_ids, *page_values]
    current = {item.target_id for item in observation.targets}
    return tuple(target_id for target_id in dict.fromkeys(values) if target_id in current)[:limit]


def _fit_context(
    context_id: str,
    task: TaskGoal,
    task_evaluation: TaskEvaluation,
    goal_plan,
    observation: WorldObservation,
    canonical_world: CanonicalPublicWorldProjection,
    world: ModelWorldView,
    actions: AgentActionPageView,
    workspace: AgentWorkspace,
    grounding: GroundingProjectionResult,
    budget: ContextProjectionBudget,
    current_step_index: int,
    runtime_controls: tuple[str, ...],
    region_index: WorldDeliveryIndex,
    control_feedback: dict[str, object],
    include_public_text_evidence: bool,
    complete_actions,
    action_space_id: str,
    action_candidates,
    action_delivery_plan,
    last_step: StepResult | None,
) -> AgentContext:
    evidence_index = _evidence_index(
        observation,
        include_public_text=include_public_text_evidence,
    )
    task_view = project_task(
        task,
        task_evaluation,
        world.facts.items,
        canonical_world.private_fact_resolver,
        grounding.index.target_refs,
    )
    private_fact_bindings = dict(canonical_world.private_fact_resolver)
    return AgentContext(
        context_id,
        task_view,
        goal_plan,
        actions,
        workspace,
        project_actor_world_snapshot(
            observation,
            canonical_world,
            world,
            grounding.index,
            grounding.images,
            # Actor is the lossless supported-public normalization. Model
            # delivery fitting belongs only to WorldDeliveryView.
            max_structure_nodes=None,
            max_structure_bytes=None,
        ),
        grounding.images,
        grounding.index,
        private_fact_bindings,
        evidence_index,
        observation,
        region_index,
        canonical_world,
        current_step_index,
        runtime_controls,
        control_feedback,
        complete_actions,
        action_space_id,
        action_candidates,
        action_delivery_plan,
        last_step,
    )


def _evidence_index(observation: WorldObservation, *, include_public_text: bool) -> WorldEvidenceIndex:
    index = WorldEvidenceIndex.from_observation(observation)
    if not include_public_text:
        return index
    records = tuple(
        sorted(
            (*index.records, *public_text_evidence_records(observation)),
            key=lambda item: item.evidence_ref,
        )
    )
    return WorldEvidenceIndex(
        observation.observation_id,
        tuple(sorted(item.evidence_ref for item in records)),
        records,
    )


def _discovery_match_kinds(
    query: str,
    label: str,
    role: str,
    operation: str,
) -> tuple[str, ...]:
    if not query:
        return ("inventory",)
    normalized_label = canonical_action_query(label) if len(label) <= 240 else ""
    kinds: list[str] = []
    if normalized_label and (
        normalized_label == query or normalized_label in query or query in normalized_label
    ):
        kinds.append("exact_label")
    if query == role.casefold():
        kinds.append("role")
    if query == operation.casefold():
        kinds.append("operation")
    if not kinds:
        kinds.append("lexical")
    return tuple(kinds)
