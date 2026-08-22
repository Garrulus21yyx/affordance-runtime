from __future__ import annotations

import json
from pathlib import Path

import pytest

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionSpaceBuilder
from affordance_runtime.agent import DecisionKind
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.compact_world_renderer import (
    inspect_actor_world,
    inspect_outcome_public,
)
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.core_loop import CoreAgentLoop
from affordance_runtime.agent.run_state import RunState
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    SurfaceObservation,
    WorldFusion,
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
        eligible_destination_ids=(lane.target_id,),
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
            child_structure_ids=("card", "lane"),
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
    )
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (board, card, lane),
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

    assert len(candidates) <= 5
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
    assert selected.destination_id == "target:lane"
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
    assert bound.intent.destination_id == "target:lane"
    assert bound.binding.binding_id == "binding:drag-card"


def test_duplicate_label_path_match_has_recall_at_5_and_rank_at_most_3() -> None:
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

    assert desired.rank <= 3
    assert desired.rank < unrelated.rank
    assert "path_match" in desired.reasons
    assert desired.functional_path != unrelated.functional_path


def test_find_controls_reuses_ranker_and_recovers_an_action_omitted_from_top5() -> None:
    task, world, actions, evaluation, context = _context()
    automatic_refs = {item.target_ref for item in context.action_candidates.candidates}
    omitted = next(item for item in context.complete_actions if item.target_label == "Zulu control")
    assert omitted.target_ref not in automatic_refs

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
    step = CoreAgentLoop(None, None, None)._action_page(task, state, actions, request)
    found = ContextBuilder().build(
        task,
        world,
        actions,
        evaluation,
        action_page=step.action_page,
    )
    found_delivery, _found_catalog = _catalog(found)

    assert found.action_candidates.scope == "search"
    assert found.action_candidates.candidates[0].action_id == omitted.action_id
    assert tuple(item.action_id for item in found.action_candidates.candidates) == tuple(
        step.action_page.visible_action_ids
    )
    assert found.action_candidates.candidates[0].target_ref == omitted.target_ref
    assert omitted.target_ref in found_delivery.manifest.executable_refs
    assert "SearchResults exact=true" in found_delivery.view.text


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
        ToolCall("read_region", {"region_ref": candidate.region_ref}, "call:open"),
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


def test_opened_region_controls_enter_the_next_normal_manifest() -> None:
    task, world, actions, evaluation, context = _context()
    zulu = next(item for item in context.complete_actions if item.target_label == "Zulu control")
    region = context.region_index.region_for_target(zulu.target_id)
    assert region is not None
    initial, catalog = _catalog(context)
    assert zulu.target_ref not in initial.manifest.executable_refs
    opened = resolve_grounded_tool_call(
        catalog,
        ToolCall("read_region", {"region_ref": region.public_ref}, "call:open-utilities"),
        expected_context_id=context.context_id,
        expected_delivery_id=initial.delivery_id,
    ).decision
    page = ContextBuilder().page_for_delivery_lens(
        actions,
        world,
        opened.delivery_lens,
        context.region_index,
    )
    next_context = ContextBuilder().build(
        task,
        world,
        actions,
        evaluation,
        action_page=page,
        delivery_lens=opened.delivery_lens,
        region_index=context.region_index,
    )
    next_delivery, _next_catalog = _catalog(next_context)

    assert zulu.target_ref in next_delivery.manifest.executable_refs
    assert f"[{zulu.target_ref}]" in next_delivery.view.text


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
