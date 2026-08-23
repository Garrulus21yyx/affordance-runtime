from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionSpaceBuilder
from affordance_runtime.agent import DecisionKind, RequestActionPage
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.action_candidate_projection import (
    ActionDeliveryFragment,
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.compact_world_renderer import (
    inspect_actor_world,
    inspect_outcome_public,
)
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.observation_delivery import ObservationDeliveryStore
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.core_loop import CoreAgentLoop
from affordance_runtime.agent.run_state import RunState
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.canonical_provider_envelope import (
    CanonicalProviderEnvelopeBinder,
    CanonicalProviderIdentity,
)
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyCallProfile,
    ActionPolicyInvocationPhase,
    ActionPolicyInvocationTrigger,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBudget,
    estimate_canonical_envelope,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.model.policy.turn_packer import TurnPacker
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.canonical_world import canonical_world

_IDENTITY = CanonicalProviderIdentity("fixture", "recording", "fixture.invalid", "text_only")
_PROFILE = ActionPolicyCallProfile(
    ActionPolicyInvocationPhase.ORDINARY,
    ActionPolicyInvocationTrigger.ORDINARY,
    1024,
    "disabled",
)


def _pack(request, *, binder=None, supports_multimodal=False, perception_profile=DecisionPerceptionProfile.TEXT_ONLY):
    if binder is None:
        binder = CanonicalProviderEnvelopeBinder()
    elif isinstance(binder, GroundedPolicyContextBinder):
        binder = CanonicalProviderEnvelopeBinder(context_binder=binder)
    return TurnPacker().pack(
        request,
        binder=binder,
        identity=_IDENTITY,
        call_profile=_PROFILE,
        supports_multimodal=supports_multimodal,
        perception_profile=perception_profile,
    )


def _binding(observation_id: str, target_id: str) -> ActionBinding:
    return ActionBinding(
        f"binding:{target_id}",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{target_id}",
        target_id,
        target_id,
        "browser",
        "browsergym",
        "activate",
        "click",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"private_bid": target_id},
    )


def _world(observation_id: str = "obs:candidate-properties"):
    overview_scope = SemanticTarget("scope:overview", "navigation", "Overview")
    account_scope = SemanticTarget("scope:account", "region", "Account Preferences")
    auxiliary_scope = SemanticTarget("scope:auxiliary", "complementary", "Utilities")
    overview_settings = SemanticTarget(
        "target:overview-settings",
        "link",
        "Settings",
        relations={"parent_id": overview_scope.target_id},
    )
    account_settings = SemanticTarget(
        "target:account-settings",
        "menuitem",
        "Settings",
        {"enabled": True, "selected": False},
        {"parent_id": account_scope.target_id},
    )
    extra_labels = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Zulu")
    extras = tuple(
        SemanticTarget(
            f"target:{label.casefold()}",
            "button",
            f"{label} control",
            {"enabled": True},
            {"parent_id": auxiliary_scope.target_id},
        )
        for label in extra_labels
    )
    targets = (
        overview_scope,
        account_scope,
        auxiliary_scope,
        overview_settings,
        account_settings,
        *extras,
    )
    auxiliary_children = tuple(f"extra-{index}" for index in range(len(extras)))
    structure = (
        ObservationStructureNode(
            "root",
            "document",
            "Control Center",
            child_structure_ids=("nav", "main", "auxiliary"),
        ),
        ObservationStructureNode(
            "nav",
            "navigation",
            "Primary navigation",
            parent_structure_id="root",
            child_structure_ids=("overview-scope", "overview-settings"),
        ),
        ObservationStructureNode(
            "overview-scope",
            "group",
            "Overview",
            parent_structure_id="nav",
            semantic_target_id=overview_scope.target_id,
        ),
        ObservationStructureNode(
            "overview-settings",
            "link",
            "Settings",
            parent_structure_id="nav",
            semantic_target_id=overview_settings.target_id,
        ),
        ObservationStructureNode(
            "main",
            "main",
            "Account workspace",
            parent_structure_id="root",
            child_structure_ids=("account-scope", "account-settings"),
        ),
        ObservationStructureNode(
            "account-scope",
            "region",
            "Account Preferences",
            parent_structure_id="main",
            semantic_target_id=account_scope.target_id,
        ),
        ObservationStructureNode(
            "account-settings",
            "menuitem",
            "Settings",
            {"enabled": True, "selected": False},
            parent_structure_id="main",
            semantic_target_id=account_settings.target_id,
        ),
        ObservationStructureNode(
            "auxiliary",
            "complementary",
            "Utilities",
            parent_structure_id="root",
            child_structure_ids=auxiliary_children,
            semantic_target_id=auxiliary_scope.target_id,
        ),
        *(
            ObservationStructureNode(
                f"extra-{index}",
                "button",
                target.label,
                {"enabled": True},
                parent_structure_id="auxiliary",
                semantic_target_id=target.target_id,
            )
            for index, target in enumerate(extras)
        ),
    )
    action_targets = (overview_settings, account_settings, *extras)
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        bindings=tuple(_binding(observation_id, item.target_id) for item in action_targets),
        structure=structure,
        structure_total_count=len(structure),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _context():
    world = _world()
    task = TaskGoal(
        "candidate-properties",
        "Open Account Preferences Settings",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    actions = ActionSpaceBuilder().build(task, world)
    evaluation = TaskEvaluation(
        task.task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    return (
        task,
        world,
        actions,
        evaluation,
        ContextBuilder().build(
            task,
            world,
            actions,
            evaluation,
        ),
    )


def _changed_action_world(observation_id: str, count: int, phase: str):
    targets = tuple(
        SemanticTarget(
            f"target:generated:{index}",
            "button",
            f"Generated control {index:03d}",
            {"phase": phase, "enabled": True},
        )
        for index in range(count)
    )
    structure_ids = tuple(f"generated:{index}" for index in range(count))
    facts = [
        StateFact(
            f"fact:{observation_id}:status:{index}",
            target.target_id,
            "status",
            phase,
            observation_id,
        )
        for index, target in enumerate(targets)
    ]
    facts.append(
        StateFact(
            f"fact:{observation_id}:{'removed' if phase == 'before' else 'added'}",
            targets[0].target_id,
            "removed_marker" if phase == "before" else "added_marker",
            True,
            observation_id,
        )
    )
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        tuple(facts),
        tuple(_binding(observation_id, item.target_id) for item in targets),
        structure=(
            ObservationStructureNode(
                "generated-root",
                "document",
                "Generated page",
                child_structure_ids=structure_ids,
            ),
            *(
                ObservationStructureNode(
                    structure_id,
                    "button",
                    target.label,
                    parent_structure_id="generated-root",
                    semantic_target_id=target.target_id,
                )
                for structure_id, target in zip(structure_ids, targets, strict=True)
            ),
        ),
        structure_total_count=count + 1,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _drag_context():
    observation_id = "obs:candidate-destination"
    board = SemanticTarget("scope:board", "region", "Planning board")
    card = SemanticTarget(
        "target:card",
        "listitem",
        "Draft card",
        relations={"parent_id": board.target_id},
    )
    lane = SemanticTarget(
        "target:lane",
        "region",
        "Ready lane",
        relations={"parent_id": board.target_id},
    )
    archive_lane = SemanticTarget(
        "target:archive-lane",
        "region",
        "Archive lane",
        relations={"parent_id": board.target_id},
    )
    binding = ActionBinding(
        "binding:drag-card",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        "fingerprint:card",
        card.target_id,
        card.target_id,
        "browser",
        "browsergym",
        "drag_to",
        "drag",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"private_bid": "card"},
        destination_required=True,
        eligible_destination_ids=(lane.target_id, archive_lane.target_id),
    )
    structure = (
        ObservationStructureNode(
            "root",
            "document",
            "Work queue",
            child_structure_ids=("board",),
        ),
        ObservationStructureNode(
            "board",
            "region",
            "Planning board",
            parent_structure_id="root",
            child_structure_ids=("card", "lane", "archive-lane"),
            semantic_target_id=board.target_id,
        ),
        ObservationStructureNode(
            "card",
            "listitem",
            "Draft card",
            parent_structure_id="board",
            semantic_target_id=card.target_id,
        ),
        ObservationStructureNode(
            "lane",
            "region",
            "Ready lane",
            parent_structure_id="board",
            semantic_target_id=lane.target_id,
        ),
        ObservationStructureNode(
            "archive-lane",
            "region",
            "Archive lane",
            parent_structure_id="board",
            semantic_target_id=archive_lane.target_id,
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (board, card, lane, archive_lane),
        bindings=(binding,),
        structure=structure,
        structure_total_count=len(structure),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    task = TaskGoal(
        "candidate-destination",
        "Move Draft card to Ready lane",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    actions = ActionSpaceBuilder().build(task, fused.observation)
    evaluation = TaskEvaluation(
        task.task_id,
        fused.observation.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    return (
        task,
        fused.observation,
        actions,
        ContextBuilder().build(
            task,
            fused.observation,
            actions,
            evaluation,
        ),
    )


def _catalog(context):
    delivery = build_model_turn_delivery(context, include_images=False)
    return delivery, compile_grounded_action_catalog(context, delivery)


def test_automatic_candidates_are_deterministic_top5_and_closed_by_current_authorities() -> None:
    _task, world, actions, _evaluation, context = _context()
    before_world = json.dumps(to_json_compatible(world), sort_keys=True)
    before_action_space = actions.action_space_id
    first, first_catalog = _catalog(context)
    second, _second_catalog = _catalog(context)
    candidates = first.action_candidates.candidates
    current = {item.action_id: item for item in context.complete_actions}

    assert len(context.action_candidates.candidates) <= 5
    base = context.action_delivery_plan.obligation(DeliveryObligationKind.BASE_ACTIONS)
    assert base is not None
    assert len(tuple(item for item in base.records if isinstance(item, ActionDeliveryFragment))) == len(
        context.complete_actions
    )
    assert candidates == context.action_delivery_plan.projection(
        dict(first.admitted_record_counts)
    ).candidates
    assert first.action_candidates.projection_id == second.action_candidates.projection_id
    assert candidates == second.action_candidates.candidates
    assert all(item.action_id in current for item in candidates)
    assert all(current[item.action_id].target_ref == item.target_ref for item in candidates)
    assert all(item.target_ref in first.manifest.executable_refs for item in candidates)
    assert all(item.target_ref in first_catalog.manifest.executable_refs for item in candidates)
    assert before_world == json.dumps(to_json_compatible(world), sort_keys=True)
    assert before_action_space == actions.action_space_id


def test_destination_required_candidate_closes_destination_in_same_manifest_and_resolver() -> None:
    task, world, actions, context = _drag_context()
    delivery, catalog = _catalog(context)
    candidate = context.action_candidates.candidates[0]

    assert candidate.operation == "drag_to"
    assert candidate.destination_required is True
    assert len(candidate.destinations) == 1
    destination = candidate.destinations[0]
    assert candidate.target_ref in delivery.manifest.executable_refs
    assert destination.target_ref in delivery.manifest.executable_refs
    assert f'"target":"{destination.target_ref}"' in delivery.view.text

    selected = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "drag_to",
            {"source": candidate.target_ref, "destination": destination.target_ref},
            "call:drag",
        ),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    ).decision
    assert selected.action_id == candidate.action_id
    expected_destination_id = next(
        item.destination_id
        for item in context.complete_actions[0].destinations.items
        if item.grounding_ref == destination.target_ref
    )
    assert selected.destination_id == expected_destination_id
    option = actions.find(selected.action_id)
    assert option is not None
    admitted = ActionSpaceBuilder().admit(
        option,
        dict(selected.parameters),
        selected.destination_id,
    )
    bound = ActionBinder().bind_for_execution(
        admitted,
        world,
        context.context_id,
        task,
        tool_call_id=selected.tool_call_id,
    )
    assert bound.intent.target_id == "target:card"
    assert bound.intent.destination_id == expected_destination_id
    destination_records = context.action_delivery_plan.obligation(
        DeliveryObligationKind.DESTINATION_ROUTES
    ).records
    assert len(destination_records) == 2
    assert all(len(item.route_deltas) == 1 for item in destination_records)
    assert {item.route_deltas[0][2] for item in destination_records} == {
        item.grounding_ref for item in context.complete_actions[0].destinations.items
    }
    assert bound.binding.binding_id == "binding:drag-card"


def test_query_owner_stores_complete_inventory_and_plan_pages_the_lossless_suffix() -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    page = builder.page(actions, world, query="Zulu control")
    discovery = builder.discovery_result(
        actions, world, page, canonical_world=context_value.canonical_world
    )
    state = RunState(world, evaluation, 2, action_page=builder.page(actions, world))
    state.install_canonical_world(context_value.canonical_world)
    request = RequestActionPage("context:test", "Zulu control")
    step = CoreAgentLoop(None, None, None, context_builder=builder)._action_page(
        task, state, actions, request
    )
    transition = state.delivery_store.reduce(step, step_index=1)
    state.apply(step, next_delivery_store=transition.next_store)
    context = builder.build(
        task,
        world,
        actions,
        evaluation,
        action_page=state.action_page,
        action_discovery=state.action_discovery,
        delivery_store=state.delivery_store,
    )
    query = context.action_delivery_plan.obligation(DeliveryObligationKind.EXPLICIT_QUERY)

    assert discovery.continuation_available is True
    assert len(discovery.matches) == 1
    assert len(state.delivery_store.action_query.matches) == len(actions.options)
    assert len(query.records) == len(actions.options)


def test_duplicate_label_path_match_survives_base_page_packing() -> None:
    _task, _world_value, _actions, _evaluation, context = _context()
    candidates = context.action_candidates.candidates
    desired = next(
        item
        for item in candidates
        if item.action_id
        == next(
            option.action_id for option in context.complete_actions if option.target_id == "target:account-settings"
        )
    )
    unrelated = next(
        item
        for item in candidates
        if item.action_id
        == next(
            option.action_id for option in context.complete_actions if option.target_id == "target:overview-settings"
        )
    )

    assert desired.rank >= 1
    assert unrelated.rank >= 1
    assert desired.functional_path != unrelated.functional_path


def test_find_controls_prioritizes_exact_result_without_replacing_base_inventory() -> None:
    task, world, actions, evaluation, context = _context()
    omitted = next(item for item in context.complete_actions if item.target_label == "Zulu control")

    delivery, catalog = _catalog(context)
    request = resolve_grounded_tool_call(
        catalog,
        ToolCall("find_controls", {"query": "Zulu control"}, "call:find-zulu"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
        expected_catalog_id=catalog.catalog_id,
    ).decision
    base_page = ContextBuilder().page(actions, world)
    state = RunState(world, evaluation, 1, action_page=base_page)
    state.install_canonical_world(context.canonical_world)
    step = CoreAgentLoop(None, None, None)._action_page(task, state, actions, request)
    found = ContextBuilder().build(
        task,
        world,
        actions,
        evaluation,
        action_page=step.action_page,
        action_discovery=step.action_page_result,
    )
    found_delivery, _found_catalog = _catalog(found)

    assert found.action_candidates.scope == "delivery"
    assert step.action_page == base_page
    assert any(
        fragment.candidate.target_ref == omitted.target_ref
        and fragment.inclusion_reason in {"base_page", "query_exact"}
        for fragment in found.action_delivery_plan.obligation(DeliveryObligationKind.EXPLICIT_QUERY).records
    )
    assert omitted.target_ref in found_delivery.manifest.executable_refs
    assert found.action_delivery_plan.obligation(DeliveryObligationKind.BASE_ACTIONS).records == (
        context.action_delivery_plan.obligation(DeliveryObligationKind.BASE_ACTIONS).records
    )


def test_focused_field_recalls_same_container_sibling_routes_without_mandatory_fanout() -> None:
    task, world, _actions, evaluation, _context_value = _context()
    focused_world = replace(
        world,
        sources=tuple(
            replace(
                source,
                structure=tuple(
                    replace(node, role="form") if node.structure_id == "auxiliary" else node
                    for node in source.structure
                ),
            )
            for source in world.sources
        ),
        targets=tuple(
            replace(
                target,
                role="textbox",
                state={**dict(target.state), "focused": True},
            )
            if target.target_id == "target:alpha"
            else target
            for target in world.targets
        ),
    )
    actions = ActionSpaceBuilder().build(task, focused_world)
    context = ContextBuilder().build(task, focused_world, actions, evaluation)
    reasons = {
        fragment.candidate.label: fragment.inclusion_reason
        for fragment in context.action_delivery_plan.obligation(DeliveryObligationKind.INTERACTION).records
    }

    assert "Alpha control" in reasons
    assert reasons["Zulu control"] == "focus_container"


@pytest.mark.parametrize(
    ("label", "query"),
    (("A", "A"), ("!", "please use ! now"), ("保存", "请立即 保存 then continue"), ("界" * 240, "界" * 240)),
)
def test_exact_label_route_reaches_delivery_manifest_catalog_and_unique_resolver(
    label: str,
    query: str,
) -> None:
    task, world, _actions, evaluation, _context_value = _context()
    world = replace(
        world,
        targets=tuple(
            replace(item, label=label) if item.target_id == "target:zulu" else item
            for item in world.targets
        ),
        sources=tuple(
            replace(
                source,
                targets=tuple(
                    replace(item, label=label) if item.target_id == "target:zulu" else item
                    for item in source.targets
                ),
                structure=tuple(
                    replace(item, label=label) if item.semantic_target_id == "target:zulu" else item
                    for item in source.structure
                ),
            )
            for source in world.sources
        ),
    )
    actions = ActionSpaceBuilder().build(task, world)
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    base = builder.build(task, world, actions, evaluation)
    page = builder.page(actions, world, query=query)
    discovery = builder.discovery_result(
        actions, world, page, canonical_world=base.canonical_world
    )
    found = builder.build(
        task,
        world,
        actions,
        evaluation,
        canonical_world=base.canonical_world,
        action_discovery=discovery,
    )
    delivery, catalog = _catalog(found)
    option = next(item for item in found.complete_actions if item.target_label == label)
    route = next(
        item
        for item in delivery.manifest.action_routes
        if item.source_ref == option.target_ref and item.operation == option.operation
    )

    resolution = resolve_grounded_tool_call(
        catalog,
        ToolCall(route.operation, {"target": route.source_ref}, "call:generated-exact"),
        expected_context_id=found.context_id,
        expected_delivery_id=delivery.delivery_id,
    )

    assert resolution.decision.action_id == option.action_id


def test_candidate_executes_directly_and_discovery_tools_never_dispatch_gui_actions() -> None:
    _task, _world_value, _actions, _evaluation, context = _context()
    delivery, catalog = _catalog(context)
    candidate = context.action_candidates.candidates[0]
    selected = resolve_grounded_tool_call(
        catalog,
        ToolCall(candidate.operation, {"target": candidate.target_ref}, "call:execute"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    ).decision
    opened = resolve_grounded_tool_call(
        catalog,
        ToolCall("read_region", {"region_ref": delivery.manifest.region_refs[0]}, "call:open"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    ).decision
    found_content = resolve_grounded_tool_call(
        catalog,
        ToolCall("search_page_content", {"query": "Settings"}, "call:content"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    ).decision
    found_actions = resolve_grounded_tool_call(
        catalog,
        ToolCall("find_controls", {"query": "Settings"}, "call:actions"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    ).decision

    assert selected.action_id == candidate.action_id
    assert opened.kind is DecisionKind.READ_REGION
    assert found_content.kind is DecisionKind.SEARCH_PAGE_CONTENT
    assert found_actions.kind is DecisionKind.FIND_CONTROLS
    assert "read_region" not in tuple(item.semantic_action for item in context.complete_actions)


def test_read_region_and_search_page_content_results_never_publish_action_inventory() -> None:
    _task, world, _actions, _evaluation, context = _context()
    candidate = context.action_candidates.candidates[0]
    opened = inspect_outcome_public(
        inspect_actor_world(
            context.actor_world,
            context.grounding,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            observation=world,
            action="read_region",
            region_ref=candidate.region_ref,
        )
    )
    content = inspect_outcome_public(
        inspect_actor_world(
            context.actor_world,
            context.grounding,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            observation=world,
            action="find",
            query="Settings",
        )
    )
    forbidden = {"actionable", "verbs", "action_refs"}
    opened_json = json.dumps(to_json_compatible(opened))
    content_json = json.dumps(to_json_compatible(content))

    assert all(value not in opened_json for value in forbidden)
    assert all(value not in content_json for value in forbidden)
    assert not any(str(item.get("node_ref", "")).startswith("E") for item in content["items"])


def test_opened_region_does_not_depend_on_candidate_implied_region_expansion() -> None:
    task, world, actions, evaluation, context = _context()
    zulu = next(item for item in context.complete_actions if item.target_label == "Zulu control")
    region = context.region_index.region_for_target(zulu.target_id)
    assert region is not None
    initial = build_model_turn_delivery(
        context,
        include_images=False,
        admitted_records={item.kind.value: 0 for item in context.action_delivery_plan.obligations},
    )
    assert zulu.target_ref not in initial.manifest.executable_refs
    opened = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=world,
        action="read_region",
        region_ref=context.canonical_world.region_refs[region.key],
    )
    assert initial.view.coverage["candidate_region_expansion_reason"] == "none"
    assert opened.items
    assert zulu.target_ref not in initial.manifest.executable_refs
    assert f"[{zulu.target_ref}]" not in initial.view.text


def test_only_admitted_fragment_route_deltas_enter_manifest_and_rank_cannot_expand_region() -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    context = builder.build(task, world, actions, evaluation)
    plan = context.action_delivery_plan
    assert plan is not None and plan.obligations

    empty_counts = {item.kind.value: 0 for item in plan.obligations}
    mandatory_only = build_model_turn_delivery(context, include_images=False, admitted_records=empty_counts)
    expected_mandatory = ()
    actual = tuple(
        (route.operation, route.source_ref, route.destination_ref) for route in mandatory_only.manifest.action_routes
    )
    rejected = {
        route
        for obligation in plan.obligations
        for fragment in obligation.records
        if isinstance(fragment, ActionDeliveryFragment)
        for route in fragment.route_deltas
    }
    assert actual == expected_mandatory
    assert rejected.isdisjoint(actual)

    assert mandatory_only.view.coverage["expanded_regions"] == 0
    assert mandatory_only.view.coverage["candidate_region_expansion_reason"] == "none"


def test_recent_action_target_does_not_implicitly_expand_its_current_region() -> None:
    _task_value, world, _actions, _evaluation, context = _context()
    target = next(item for item in world.targets if item.target_id == "target:zulu")
    empty_counts = {item.kind.value: 0 for item in context.action_delivery_plan.obligations}
    baseline = build_model_turn_delivery(context, include_images=False, admitted_records=empty_counts)
    with_history = replace(
        context,
        workspace=AgentWorkspace(
            recent_steps=(
                AgentTurnView(
                    "select_action",
                    semantic_action="activate",
                    target=AgentHistoricalTargetView(target.role, target.label),
                ),
            ),
        ),
    )

    delivered = build_model_turn_delivery(with_history, include_images=False, admitted_records=empty_counts)

    assert delivered.view.text == baseline.view.text
    assert delivered.view.coverage["expanded_regions"] == baseline.view.coverage["expanded_regions"]
    assert delivered.view.coverage["candidate_region_expansion_reason"] == "none"


def test_turn_packer_reprices_actual_catalog_and_backs_off_only_optional_fragment() -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    context = builder.build(task, world, actions, evaluation)
    plan = context.action_delivery_plan
    assert plan is not None and sum(len(item.remaining) for item in plan.obligations) >= 2
    request = ModelDecisionRequest("request:packing-property", context)
    wide = CanonicalProviderEnvelopeBinder()

    foreground = next(item for item in plan.obligations if item.continuation_scope == plan.foreground_scope)

    def total(record_count: int) -> int:
        counts = {item.kind.value: 0 for item in plan.obligations}
        counts[foreground.kind.value] = record_count
        delivery = build_model_turn_delivery(
            context,
            include_images=False,
            admitted_records=counts,
        )
        catalog = compile_grounded_action_catalog(context, delivery)
        envelope = wide.bind(
            request,
            delivery,
            catalog,
            identity=_IDENTITY,
            call_profile=_PROFILE,
            output_token_reserve=_PROFILE.max_output_tokens,
        )
        return estimate_canonical_envelope(envelope).estimated_input_tokens

    mandatory_total = total(0)
    first_optional_total = total(1)
    second_optional_total = total(2)
    assert first_optional_total > mandatory_total
    limited = CanonicalProviderEnvelopeBinder(
        request_budget=ModelRequestBudget(
            model_context_window=second_optional_total + 5_000,
            max_output_tokens=0,
            protocol_reserve_tokens=0,
            safety_margin_tokens=0,
            admission_limit=second_optional_total - 1,
        )
    )
    packed = _pack(
        request,
        binder=limited,
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )

    assert dict(packed.admitted_record_counts)[foreground.kind.value] == 1
    assert packed.packing_backoff_count >= 1
    assert (
        packed.delivery.manifest.action_routes
        == build_model_turn_delivery(
            context,
            include_images=False,
            admitted_records=dict(packed.admitted_record_counts),
            packing_backoff_count=packed.packing_backoff_count,
        ).manifest.action_routes
    )
    breakdown = packed.admitted_envelope.token_breakdown
    assert breakdown.admitted_record_count == sum(dict(packed.admitted_record_counts).values())
    assert breakdown.manifest_route_count == len(packed.delivery.manifest.action_routes)
    assert breakdown.packing_backoff_count == packed.packing_backoff_count
    assert breakdown.tool_schema_bytes > 0
    assert breakdown.complete_request_tokens == (breakdown.estimated_input_tokens + breakdown.output_reserve_tokens)


@pytest.mark.parametrize("count", (1, 2, 16, 84, 167, 500))
def test_changed_action_and_fact_fanout_remains_bounded_and_cursor_conserved(count: int) -> None:
    task = TaskGoal(
        "generated-fanout",
        "Activate a generated control",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    before = _changed_action_world(f"fanout-before-{count}", count, "before")
    after = _changed_action_world(f"fanout-after-{count}", count, "after")
    before_actions = ActionSpaceBuilder().build(task, before)
    after_actions = ActionSpaceBuilder().build(task, after)
    delta = WorldTransitionProjector().project(before, after)
    store = ObservationDeliveryStore().advance(
        SimpleNamespace(
            before_world=before,
            after_world=after,
            before_public_world=canonical_world(before, before_actions),
            after_public_world=canonical_world(after, after_actions),
            public_world_delta=delta,
            execution_receipts=SimpleNamespace(
                receipts=(
                    SimpleNamespace(
                        request=SimpleNamespace(
                            intent=SimpleNamespace(
                                semantic_action="activate",
                                target_id=before.targets[0].target_id,
                            )
                        ),
                        result=SimpleNamespace(dispatch_status=DispatchStatus.SENT),
                    ),
                )
            ),
        ),
        step_index=1,
    )
    context = ContextBuilder().build(
        task,
        after,
        after_actions,
        TaskEvaluation(
            task.task_id,
            after.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "generated fanout",
        ),
        delivery_store=store,
    )
    effect = context.action_delivery_plan.obligation(DeliveryObligationKind.PUBLIC_EFFECT)
    assert effect is not None
    assert len(effect.records) >= count

    packed = _pack(
        ModelDecisionRequest(f"request:fanout:{count}", context),
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )

    admitted = dict(packed.admitted_record_counts)[DeliveryObligationKind.PUBLIC_EFFECT.value]
    assert admitted >= 1
    assert admitted <= len(effect.records)
    if count >= 84:
        assert admitted < len(effect.records)
        assert any(item.scope == "effect" for item in packed.delivery.continuation_capabilities)
    assert (
        packed.admitted_envelope.token_breakdown.estimated_input_tokens
        <= ModelRequestBudget().soft_target_tokens
    )
    assert packed.admitted_envelope.token_breakdown.estimated_input_tokens <= ModelRequestBudget().admission_limit
    assert (
        packed.admitted_envelope.token_breakdown.complete_request_tokens
        <= ModelRequestBudget().model_context_window
    )
    assert (*effect.records[:admitted], *effect.records[admitted:]) == effect.records
    changes = {item.change.value for item in store.latest_effect.inventory.atoms}
    assert {"added", "removed", "modified"} <= changes


def test_foreground_required_atom_does_not_receive_second_attempt_before_other_groups(
    monkeypatch,
) -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder()
    query_page = builder.page(actions, world, query="Settings")
    discovery = builder.discovery_result(
        actions, world, query_page, canonical_world=context_value.canonical_world
    )
    context = builder.build(
        task,
        world,
        actions,
        evaluation,
        canonical_world=context_value.canonical_world,
        action_discovery=discovery,
    )
    attempts = []
    original = TurnPacker._attempt

    def recording_attempt(*args, **kwargs):
        attempts.append(dict(kwargs["admitted_records"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(TurnPacker, "_attempt", staticmethod(recording_attempt))
    _pack(
        ModelDecisionRequest("request:depth-round", context),
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )

    query_kind = DeliveryObligationKind.EXPLICIT_QUERY.value
    required_index = next(index for index, counts in enumerate(attempts) if counts.get(query_kind) == 1)
    first_extension = attempts[required_index + 1]
    assert first_extension[query_kind] == 1
    assert any(count for kind, count in first_extension.items() if kind != query_kind)


def test_stale_context_and_unknown_legacy_operations_fail_typed() -> None:
    _task, _world_value, _actions, _evaluation, context = _context()
    delivery, catalog = _catalog(context)
    with pytest.raises(GroundedToolResolutionError) as stale:
        resolve_grounded_tool_call(
            catalog,
            ToolCall("find_controls", {"query": "Settings"}),
            expected_context_id="context:" + "0" * 64,
            expected_delivery_id=delivery.delivery_id,
        )
    assert stale.value.code is GroundedToolResolutionCode.STALE_CATALOG
    with pytest.raises(GroundedToolResolutionError) as unknown:
        resolve_grounded_tool_call(
            catalog,
            ToolCall("legacy_action_discovery", {"query": "Settings"}),
            expected_context_id=context.context_id,
            expected_delivery_id=delivery.delivery_id,
        )
    assert unknown.value.code is GroundedToolResolutionCode.UNKNOWN_OPERATION


def test_provider_bound_delivery_contains_no_private_cursor_identity_or_inventory_counts() -> None:
    _task_value, world, _actions, _evaluation, context = _context()
    request = ModelDecisionRequest("request:privacy", context)
    packed = _pack(
        request,
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )
    physical = json.dumps(
        to_json_compatible(
            {
                "envelope": packed.admitted_envelope.envelope.physical_content(),
                "delivery": packed.delivery,
            }
        ),
        sort_keys=True,
    )
    private_values = {
        world.observation_id,
        *(item.observation_id for item in world.sources),
        *(item.action_id for item in context.complete_actions),
    }
    forbidden_fields = {
        "private_cursor",
        "page_cursor",
        "next_cursor",
        "source_count",
        "matched_target_count",
        "action_variant_count",
        "member_count",
        "omitted_total",
        "raw_delta_lineage",
        "source_context",
    }

    assert all(value not in physical for value in private_values)
    assert all(value not in physical for value in forbidden_fields)
    assert "browsergym-observation:" not in physical


def test_zero_admitted_suffix_still_registers_unique_store_bound_continuation() -> None:
    _task_value, _world_value, _actions, _evaluation, context = _context()
    plan = context.action_delivery_plan
    assert plan is not None
    empty = {item.kind.value: 0 for item in plan.obligations}
    delivery = build_model_turn_delivery(context, include_images=False, admitted_records=empty)
    catalog = compile_grounded_action_catalog(context, delivery)
    continuation = next(
        spec for spec in catalog.specs if spec.name == "action_results_next_page"
    )
    scopes = tuple(
        item.scope
        for item in delivery.continuation_capabilities
        if item.scope not in {"effect", "page_directory", "active_read"}
    )
    arguments = {} if len(scopes) == 1 else {"scope": scopes[0]}

    resolution = resolve_grounded_tool_call(
        catalog,
        ToolCall("action_results_next_page", arguments, "call:zero-prefix"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    )

    assert continuation.input_schema["properties"] == (
        {} if len(scopes) == 1 else continuation.input_schema["properties"]
    )
    assert resolution.next_delivery_store is not None
    assert resolution.next_delivery_store.requested_continuation_scope == scopes[0]
    assert resolution.next_delivery_store.inventory(scopes[0]).offset == 0


def test_provider_binder_preserves_typed_task_public_inputs_and_criteria_exactly() -> None:
    task, world, actions, evaluation, _context_value = _context()
    public_inputs = {
        "selector": "#公开-目标",
        "path": ["根", "分支", "叶!"],
        "target_id": "business-target-17",
        "coordinates": {"x": 12, "y": 34},
        "rows": [{f"field_{index}": f"值-{index}"} for index in range(20)],
    }
    criterion = {
        "id": "exact-public-input",
        "selector": "#公开-目标",
        "predicate": "submitted",
    }
    public_task = replace(task, inputs=public_inputs, success_criteria=(criterion,))
    context = ContextBuilder().build(public_task, world, actions, evaluation)
    packed = _pack(
        ModelDecisionRequest("request:task-public", context),
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )
    physical = json.loads(packed.admitted_envelope.envelope.user_text)

    assert physical["task"]["public_inputs"] == public_inputs
    assert physical["task"]["success_criteria"]["items"][0]["definition"] == criterion


def test_observation_and_source_id_permutation_preserves_public_page_manifest_catalog_and_cost() -> None:
    task, _world_value, _actions, _evaluation, context_a = _context()
    world_b = _world("obs:permuted-observation-id-with-extra-length")
    actions_b = ActionSpaceBuilder().build(task, world_b)
    evaluation_b = TaskEvaluation(
        task.task_id,
        world_b.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context_b = ContextBuilder().build(task, world_b, actions_b, evaluation_b)

    packed_a = _pack(
        ModelDecisionRequest("request:id-a", context_a),
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )
    packed_b = _pack(
        ModelDecisionRequest("request:id-b", context_b),
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )

    assert packed_a.delivery.view.text == packed_b.delivery.view.text
    assert packed_a.delivery.delivery_id == packed_b.delivery.delivery_id
    assert packed_a.delivery.manifest == packed_b.delivery.manifest
    assert to_json_compatible(packed_a.catalog.specs) == to_json_compatible(packed_b.catalog.specs)
    assert packed_a.admitted_envelope.token_breakdown.complete_request_tokens == (
        packed_b.admitted_envelope.token_breakdown.complete_request_tokens
    )
    assert packed_a.delivery.admitted_record_counts == packed_b.delivery.admitted_record_counts


def test_private_inventory_enumeration_permutation_preserves_public_delivery() -> None:
    task, world_a, actions_a, evaluation_a, context_a = _context()
    world_b = replace(
        world_a,
        targets=tuple(reversed(world_a.targets)),
        bindings=tuple(reversed(world_a.bindings)),
    )
    actions_b = ActionSpaceBuilder().build(task, world_b)
    context_b = ContextBuilder().build(task, world_b, actions_b, evaluation_a)

    packed = tuple(
        _pack(
            ModelDecisionRequest(request_id, context),
            binder=GroundedPolicyContextBinder(),
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
        )
        for request_id, context in (("request:order-a", context_a), ("request:order-b", context_b))
    )
    first, second = packed

    assert first.delivery.view.text == second.delivery.view.text
    assert first.delivery.delivery_id == second.delivery.delivery_id
    assert first.delivery.manifest == second.delivery.manifest
    assert to_json_compatible(first.catalog.specs) == to_json_compatible(second.catalog.specs)
    assert first.admitted_envelope.token_breakdown.complete_request_tokens == (
        second.admitted_envelope.token_breakdown.complete_request_tokens
    )
    assert first.delivery.admitted_record_counts == second.delivery.admitted_record_counts


def test_current_source_and_tests_contain_no_removed_delivery_contracts() -> None:
    root = Path(__file__).resolve().parents[3]
    removed = (
        "Direct" + "Actions",
        "_preferred" + "_action_refs",
        "search" + "_world",
        "search" + "_actions",
    )
    for directory in (root / "src", root / "tests"):
        for path in directory.rglob("*"):
            if path.suffix not in {".py", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert not any(value in text for value in removed), path
