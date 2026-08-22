"""One-way construction of a fresh disposable AgentContext for each policy turn."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from affordance_runtime.actions.paging import ActionPager, InternalActionPage
from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.acquisition_projection import project_acquisition_offers
from affordance_runtime.agent.context.action_candidate_projection import (
    close_action_candidates,
    project_action_candidates,
)
from affordance_runtime.agent.context.actor_world_snapshot import project_actor_world_snapshot
from affordance_runtime.agent.context.budgets import (
    BoundedSection,
    ContextProjectionBudget,
)
from affordance_runtime.agent.context.context import AgentContext, ContextIdentity
from affordance_runtime.agent.context.contracts import (
    AgentActionPageView,
    AgentTurnView,
)
from affordance_runtime.agent.context.evidence_candidate_projection import (
    project_evidence_candidates,
)
from affordance_runtime.agent.context.grounding_projection import (
    GroundingProjection,
    GroundingProjectionResult,
)
from affordance_runtime.agent.context.projection import project_action_page, project_action_space
from affordance_runtime.agent.context.task_projection import project_task
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.context.world_projection import (
    ModelWorldView,
    project_model_world,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.working_facts import WorkingFact, is_public_scalar
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
        recent_steps: tuple[AgentTurnView, ...] = (),
        recent_step_total_count: int | None = None,
        action_page: InternalActionPage | None = None,
        context_generation: int = 0,
        observation_capabilities: ObservationCapabilities = ObservationCapabilities(False, False),
        goal_resolution: GoalPlanResolution | None = None,
        working_facts: tuple[WorkingFact, ...] = (),
        runtime_controls: tuple[str, ...] = (),
        delivery_lens: WorldDeliveryLens | None = None,
        region_index: WorldDeliveryIndex | None = None,
        control_feedback: dict[str, object] | None = None,
    ) -> AgentContext:
        if task_evaluation.observation_id != observation.observation_id:
            raise ValueError("context task evaluation belongs to a previous observation")
        if delivery_lens is not None and delivery_lens.world_observation_id != observation.observation_id:
            raise ValueError("delivery lens belongs to a previous observation")
        current_region_index = region_index or WorldDeliveryIndex.from_observation(
            observation,
            action_space.options,
        )
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
            self.budget.max_destinations_per_option,
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
            extra_target_ids=(
                current_region_index.member_target_ids(delivery_lens.selected_region_key)
                if delivery_lens is not None and delivery_lens.selected_region_key
                else ()
            ),
        )
        world = project_model_world(
            observation,
            self.budget,
            pinned_targets,
            observation_capabilities=project_acquisition_offers(observation_capabilities),
            observation_cursor="",
            lossless_public=True,
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
            ("exact_target", "query", "cursor"),
            page.query,
            page.target_id,
            page.relevance_role.value if page.relevance_role else "",
            page.next_cursor,
        )
        history_items = tuple(recent_steps)
        history_total = len(recent_steps) if recent_step_total_count is None else recent_step_total_count
        if history_total < len(recent_steps):
            raise ValueError("recent step total cannot be smaller than the retained steps")
        complete_page = AgentActionPageView(
            complete_projected_actions.options,
            len(complete_projected_actions.options),
            len(complete_projected_actions.options),
            False,
            False,
            ("exact_target", "query", "cursor"),
        )
        grounding = self.grounding_projection.project(
            observation,
            world,
            complete_page,
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
            _tool_catalog_digest(complete_page, world, grounding, runtime_controls, delivery_lens),
        )
        actions = close_action_candidates(actions, grounding.index, context_id=identity.context_id)
        complete_page = close_action_candidates(
            complete_page,
            grounding.index,
            context_id=identity.context_id,
        )
        candidate_projection = project_action_candidates(
            complete_page.options,
            action_space_id=action_space.action_space_id,
            world_observation_id=observation.observation_id,
            region_index=current_region_index,
            query=actions.active_query,
            instruction=task.instruction,
            objectives=tuple(item.objective for item in goal_plan.items),
            done_when=tuple(item.done_when for item in goal_plan.items),
            recent_outcomes=history_items,
            allowed_action_ids=(
                frozenset(item.action_id for item in actions.options) if actions.active_query else None
            ),
            top_k=None if actions.active_query else 5,
        )
        return _fit_context(
            identity.context_id,
            task,
            task_evaluation,
            goal_plan,
            observation,
            world,
            actions,
            BoundedSection(
                history_items,
                len(history_items),
                False,
            ),
            grounding,
            self.budget,
            working_facts,
            history_total,
            runtime_controls,
            delivery_lens,
            current_region_index,
            control_feedback or {},
            self.include_public_text_evidence,
            complete_page.options,
            action_space.action_space_id,
            candidate_projection,
        )

    def page(
        self,
        action_space: ActionSpace,
        observation: WorldObservation,
        *,
        query: str = "",
        target_id: str = "",
        relevance_role: str = "",
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
        return self.pager.page(
            action_space,
            None,
            query=query,
            target_id=target_id,
            relevance_role=relevance_role or None,
            labels=labels,
            roles={target_id: item.role for target_id, item in targets.items()},
            states={target_id: item.state for target_id, item in targets.items()},
            functional_paths={target_id: region_index.functional_path_for_target(target_id) for target_id in targets},
            cursor=cursor,
            page_size=min(
                self.budget.max_action_options,
                self.pager.page_size,
            ),
            max_destinations_per_option=self.budget.max_destinations_per_option,
            max_targets=self.budget.observation_pinned_capacity(len(observation.targets)),
        )

    def page_for_delivery_lens(
        self,
        action_space: ActionSpace,
        observation: WorldObservation,
        lens: WorldDeliveryLens,
        region_index: WorldDeliveryIndex,
    ) -> InternalActionPage:
        if lens.world_observation_id != observation.observation_id:
            raise ValueError("delivery lens belongs to a previous observation")
        if region_index.world_observation_id != observation.observation_id:
            raise ValueError("region index belongs to a previous observation")
        selected_targets = set(region_index.member_target_ids(lens.selected_region_key))
        allowed = {
            option.action_id
            for option in action_space.options
            if option.target_id in selected_targets or bool(set(option.eligible_destination_ids) & selected_targets)
        }
        if not allowed:
            return self.page(action_space, observation, region_index=region_index)
        labels = {item.target_id: item.label for item in observation.targets}
        return self.pager.page(
            action_space,
            None,
            labels=labels,
            page_size=min(self.budget.max_action_options, self.pager.page_size),
            max_destinations_per_option=self.budget.max_destinations_per_option,
            max_targets=self.budget.observation_pinned_capacity(len(observation.targets)),
            allowed_action_ids=frozenset(allowed),
            authority_digest="delivery-lens:" + lens.selected_region_key,
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
    delivery_lens: WorldDeliveryLens | None,
) -> str:
    """Bind identity to the exact current inputs that determine the public tool catalog."""

    payload = to_json_compatible(
        {
            "actions": actions,
            "observation_capabilities": world.observation_capabilities,
            "world_targets": world.targets,
            "grounding_entities": grounding.index.entities,
            "runtime_controls": tuple(runtime_controls),
            "delivery_lens": delivery_lens,
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
    world: ModelWorldView,
    actions: AgentActionPageView,
    history: BoundedSection[AgentTurnView],
    grounding: GroundingProjectionResult,
    budget: ContextProjectionBudget,
    working_facts: tuple[WorkingFact, ...],
    current_step_index: int,
    runtime_controls: tuple[str, ...],
    delivery_lens: WorldDeliveryLens | None,
    region_index: WorldDeliveryIndex,
    control_feedback: dict[str, object],
    include_public_text_evidence: bool,
    complete_actions,
    action_space_id: str,
    action_candidates,
) -> AgentContext:
    evidence_index = _evidence_index(
        observation,
        include_public_text=include_public_text_evidence,
    )
    fact_refs = _public_fact_refs(
        world.facts.items,
        task_evaluation,
        evidence_index,
        observation,
    )
    evidence_candidates = project_evidence_candidates(
        observation,
        evidence_index,
        fact_refs,
        region_index,
        intent=" ".join(
            (
                task.instruction,
                *(item.objective for item in goal_plan.items),
                *(item.done_when for item in goal_plan.items),
            )
        ),
    )
    task_view = project_task(
        task,
        task_evaluation,
        world.facts.items,
        fact_refs,
        grounding.index.target_refs,
        include_final_response_contract=True,
    )
    private_fact_bindings = _current_public_fact_bindings(
        observation,
        evidence_index,
        fact_refs,
    )
    return AgentContext(
        context_id,
        task_view,
        goal_plan,
        actions,
        history,
        project_actor_world_snapshot(
            observation,
            world,
            grounding.index,
            grounding.images,
            # Actor is the lossless supported-public normalization. Model
            # delivery fitting belongs only to WorldDeliveryView.
            max_structure_nodes=None,
            max_structure_bytes=None,
            fact_refs=fact_refs,
        ),
        grounding.images,
        grounding.index,
        working_facts,
        private_fact_bindings,
        evidence_index,
        observation,
        delivery_lens,
        region_index,
        current_step_index,
        budget.max_history_serialized_bytes,
        runtime_controls,
        control_feedback,
        complete_actions,
        action_space_id,
        action_candidates,
        evidence_candidates,
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


def _current_public_fact_bindings(
    observation: WorldObservation,
    evidence_index: WorldEvidenceIndex,
    canonical_to_public: dict[str, str],
) -> dict[str, str]:
    sources = {item.observation_id: item for item in observation.sources}
    result: dict[str, str] = {}
    for canonical, public in canonical_to_public.items():
        record = evidence_index.resolve_record(canonical)
        source = sources.get(record.source_observation_id) if record is not None else None
        if (
            record is not None
            and record.kind == "fact"
            and record.observation_id == observation.observation_id
            and source is not None
            and source.coverage is not CoverageState.STALE
        ):
            result[public] = canonical
    return result


def _public_fact_refs(
    facts,
    task_evaluation: TaskEvaluation,
    evidence_index: WorldEvidenceIndex,
    observation: WorldObservation,
) -> dict[str, str]:
    sources = {item.observation_id: item for item in observation.sources}
    current_refs = {
        record.evidence_ref
        for record in evidence_index.records
        if (
            record.kind == "fact"
            and record.observation_id == observation.observation_id
            and (
                (source := sources.get(record.source_observation_id)) is None
                or source.coverage is not CoverageState.STALE
            )
        )
    }
    present = {item.fact_ref for item in facts if item.fact_ref in current_refs}
    prioritized: list[str] = []

    def add(ref: str) -> None:
        if ref in present and ref not in prioritized:
            prioritized.append(ref)

    for ref in task_evaluation.completion_evidence_refs:
        add(ref)
    for criterion in task_evaluation.criteria:
        for ref in criterion.evidence_refs:
            add(ref)
    for output in task_evaluation.outputs:
        for ref in output.evidence_refs:
            add(ref)
    ordered = [
        *prioritized,
        *(item.fact_ref for item in facts if item.fact_ref in current_refs and item.fact_ref not in prioritized),
    ]
    ordered.extend(
        record.evidence_ref
        for record in evidence_index.records
        if (
            record.kind == "fact"
            and record.evidence_ref in current_refs
            and is_public_scalar(record.value)
            and record.evidence_ref not in ordered
        )
    )
    return {ref: f"F{index}" for index, ref in enumerate(ordered, 1)}
