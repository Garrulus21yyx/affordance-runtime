from __future__ import annotations

import json
import re
from dataclasses import replace
from itertools import product
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic_ai.messages import ModelResponse, ToolCallPart

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionSpace, ActionSpaceBuilder
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent import DecisionKind, RequestActionPage, SelectAction
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context import context_builder as context_builder_module
from affordance_runtime.agent.context.action_candidate_projection import (
    ActionRouteFragment,
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget
from affordance_runtime.agent.context.canonical_world_projection import (
    CanonicalPublicWorldProjection,
)
from affordance_runtime.agent.context.compact_world_renderer import (
    inspect_actor_world,
    inspect_outcome_public,
)
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.observation_delivery import (
    ObservationDeliveryStore,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.core_loop import CoreAgentLoop
from affordance_runtime.agent.decisions import SearchPageContentResult
from affordance_runtime.agent.run_state import RunState, StepResult
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceipt,
    ExecutionReceiptBatch,
)
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
from affordance_runtime.model.policy.grounded_tool_compiler import GroundedToolCompiler
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.grounded_tool_rejection import (
    grounded_tool_rejection_decision,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyCallProfile,
    ActionPolicyInvocationPhase,
    ActionPolicyInvocationTrigger,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBudget,
    ModelRequestCapacityError,
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
    committed = request.last_step or request.agent_context.last_step
    if request.last_step is None and committed is not None:
        request = replace(request, last_step=committed)
    decision = getattr(committed, "decision", None)
    call_id = str(getattr(decision, "tool_call_id", ""))
    tool_name = str(getattr(decision, "tool_name", ""))
    history_messages = (ModelResponse(parts=[ToolCallPart(tool_name, {}, call_id)]),) if call_id and tool_name else ()
    return TurnPacker().pack(
        request,
        binder=binder,
        identity=_IDENTITY,
        call_profile=_PROFILE,
        supports_multimodal=supports_multimodal,
        perception_profile=perception_profile,
        history_messages=history_messages,
        pending_tool_call_id=call_id,
        pending_tool_name=tool_name,
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


def _text_binding(observation_id: str, target_id: str) -> ActionBinding:
    return ActionBinding(
        f"binding:{target_id}:type",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{target_id}",
        target_id,
        target_id,
        "browser",
        "browsergym",
        "type_text",
        "fill",
        "local_reversible",
        ("query_changed",),
        {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        {"private_bid": target_id},
    )


def _multi_verb_context():
    observation_id = "obs:multi-verb-focused-control"
    search = SemanticTarget(
        "target:search",
        "textbox",
        "Search",
        {"focused": True, "value": ""},
    )
    bindings = (
        ActionBinding(
            "binding:search:type",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            "fingerprint:search",
            search.target_id,
            search.target_id,
            "browser",
            "browsergym",
            "type_text",
            "fill",
            "local_reversible",
            ("query_changed",),
            {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            {"private_bid": "search"},
        ),
        ActionBinding(
            "binding:search:key",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            "fingerprint:search",
            search.target_id,
            search.target_id,
            "browser",
            "browsergym",
            "press_key",
            "press",
            "local_reversible",
            ("query_changed",),
            {
                "type": "object",
                "properties": {"key": {"type": "string", "enum": ["Enter"]}},
                "required": ["key"],
                "additionalProperties": False,
            },
            {"private_bid": "search"},
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (search,),
        bindings=bindings,
        structure=(
            ObservationStructureNode(
                "root",
                "document",
                "Search page",
                child_structure_ids=("search",),
            ),
            ObservationStructureNode(
                "search",
                "textbox",
                "Search",
                {"focused": True, "value": ""},
                parent_structure_id="root",
                semantic_target_id=search.target_id,
            ),
        ),
        structure_total_count=2,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation
    task = TaskGoal(
        "multi-verb-focused-control",
        "Search for Shanksville",
        allowed_effects=("query_changed",),
        risk_profile=RiskProfile.LOW,
    )
    actions = ActionSpaceBuilder().build(task, world)
    evaluation = TaskEvaluation(
        task.task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    return task, world, actions, evaluation, ContextBuilder().build(
        task,
        world,
        actions,
        evaluation,
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


def _context_with_direct_result(
    values: tuple[dict[str, object], ...],
):
    task, world, _actions, evaluation, _ = _context()
    actions = ActionSpace(world.observation_id, ())
    decision = SearchPageContentResult(
        "context:fixture",
        "read_region",
        {"region_ref": "R2"},
        {"kind": "Opened", "items": values, "next_cursor": None},
        "call:public-results",
    )
    committed = StepResult(
        decision,
        world,
        world,
        evaluation,
        feedback="local_tool_result",
    )
    context = ContextBuilder().build(
        task,
        world,
        actions,
        evaluation,
        last_step=committed,
    )
    return context


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
    interaction = context.action_delivery_plan.obligation(DeliveryObligationKind.INTERACTION)
    delivered_routes = {
        item.public_route
        for obligation in (base, interaction)
        if obligation is not None
        for item in obligation.records
        if isinstance(item, ActionRouteFragment)
    }
    base_page_routes = {
        (option.operation, option.target_ref, destination_ref)
        for option in context.actions.options
        for destination_ref in (
            tuple(item.grounding_ref for item in option.destinations.items) if option.destination_required else ("",)
        )
    }
    assert base.required_record_count == len(base.records)
    assert base_page_routes <= delivered_routes
    assert len(base.records) <= len(base_page_routes) + 5
    assert candidates == context.action_delivery_plan.projection(dict(first.admitted_record_counts)).candidates
    assert first.action_candidates.projection_id == second.action_candidates.projection_id
    assert candidates == second.action_candidates.candidates
    assert all(item.action_id in current for item in candidates)
    assert all(current[item.action_id].target_ref == item.target_ref for item in candidates)
    assert all(item.target_ref in first.manifest.executable_refs for item in candidates)
    assert all(item.target_ref in first_catalog.manifest.executable_refs for item in candidates)
    assert before_world == json.dumps(to_json_compatible(world), sort_keys=True)
    assert before_action_space == actions.action_space_id


def test_large_page_preserves_current_content_editor_without_promoting_private_binding_or_old_ref() -> None:
    observation_id = "obs:large-page-current-editor"
    links = tuple(
        SemanticTarget(f"target:link-{index:02d}", "link", f"Result {index:02d}", {"visible": True})
        for index in range(40)
    )
    global_search = SemanticTarget(
        "target:global-search",
        "textbox",
        "Search site",
        {"visible": True, "value": ""},
    )
    editor = SemanticTarget(
        "target:editor",
        "textbox",
        "Editor content",
        {"visible": True, "value": ""},
    )
    submit = SemanticTarget(
        "target:submit",
        "button",
        "Submit",
        {"visible": True},
    )
    sort_control = SemanticTarget(
        "target:sort",
        "button",
        "Sort by: Hot",
        {"expanded": False, "visible": True},
    )
    link_nodes = tuple(f"link-{index:02d}" for index in range(len(links)))
    structure = (
        ObservationStructureNode(
            "root",
            "document",
            "Workspace",
            child_structure_ids=(*link_nodes, "sort-list", "site-search", "content-form"),
        ),
        *(
            ObservationStructureNode(
                f"link-{index:02d}",
                "link",
                target.label,
                {"visible": True},
                parent_structure_id="root",
                semantic_target_id=target.target_id,
            )
            for index, target in enumerate(links)
        ),
        ObservationStructureNode(
            "sort-list",
            "list",
            "Sort controls",
            parent_structure_id="root",
            child_structure_ids=("sort-item",),
        ),
        ObservationStructureNode(
            "sort-item",
            "listitem",
            "",
            parent_structure_id="sort-list",
            child_structure_ids=("sort-button",),
        ),
        ObservationStructureNode(
            "sort-button",
            "button",
            sort_control.label,
            {"expanded": False, "visible": True},
            parent_structure_id="sort-item",
            semantic_target_id=sort_control.target_id,
        ),
        ObservationStructureNode(
            "site-search",
            "search",
            "Site search",
            parent_structure_id="root",
            child_structure_ids=("site-search-input",),
        ),
        ObservationStructureNode(
            "site-search-input",
            "textbox",
            global_search.label,
            {"visible": True, "value": ""},
            parent_structure_id="site-search",
            semantic_target_id=global_search.target_id,
        ),
        ObservationStructureNode(
            "content-form",
            "list",
            "Current editor",
            parent_structure_id="root",
            child_structure_ids=("editor-input", "editor-submit"),
        ),
        ObservationStructureNode(
            "editor-input",
            "textbox",
            editor.label,
            {"visible": True, "value": ""},
            parent_structure_id="content-form",
            semantic_target_id=editor.target_id,
        ),
        ObservationStructureNode(
            "editor-submit",
            "button",
            submit.label,
            {"visible": True},
            parent_structure_id="content-form",
            semantic_target_id=submit.target_id,
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (*links, sort_control, global_search, editor, submit),
        bindings=(
            *(_binding(observation_id, target.target_id) for target in links),
            _binding(observation_id, sort_control.target_id),
            _text_binding(observation_id, global_search.target_id),
            _text_binding(observation_id, editor.target_id),
            _binding(observation_id, submit.target_id),
        ),
        structure=structure,
        structure_total_count=len(structure),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation
    task = TaskGoal(
        "large-page-current-editor",
        "Open Result 00, Result 01, Result 02, Result 03, and Result 04",
        allowed_effects=("external_ui_interaction", "query_changed"),
        risk_profile=RiskProfile.LOW,
    )
    actions = ActionSpaceBuilder().build(task, world)
    evaluation = TaskEvaluation(
        task.task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(task, world, actions, evaluation)
    plan = context.action_delivery_plan
    assert plan is not None
    editor_ref = context.grounding.target_refs[editor.target_id]
    submit_ref = context.grounding.target_refs[submit.target_id]
    sort_ref = context.grounding.target_refs[sort_control.target_id]
    base = plan.obligation(DeliveryObligationKind.BASE_ACTIONS)
    interaction = plan.obligation(DeliveryObligationKind.INTERACTION)
    assert base is not None and interaction is not None
    base_refs = {
        record.candidate.target_ref
        for record in base.records
        if isinstance(record, ActionRouteFragment)
    }
    assert {editor_ref, submit_ref, sort_ref}.isdisjoint(base_refs)
    interaction_routes = tuple(
        record
        for record in interaction.records
        if isinstance(record, ActionRouteFragment)
    )
    assert interaction_routes[0].candidate.target_ref == editor_ref
    assert interaction_routes[0].inclusion_reason == "value_control"
    assert any(
        route.candidate.target_ref == submit_ref and route.inclusion_reason == "value_container"
        for route in interaction_routes
    )
    assert any(
        route.candidate.target_ref == sort_ref and route.inclusion_reason == "state_control"
        for route in interaction_routes
    )
    assert interaction.required_record_count == 1

    packed = _pack(ModelDecisionRequest("request:large-page-current-editor", context))
    counts = dict(packed.admitted_record_counts)
    assert counts[DeliveryObligationKind.INTERACTION.value] >= 1
    assert editor_ref in packed.delivery.manifest.executable_refs
    assert submit_ref in packed.delivery.manifest.executable_refs
    assert sort_ref in packed.delivery.manifest.executable_refs
    assert "private_bid" not in packed.delivery.view.text
    resolved = resolve_grounded_tool_call(
        packed.catalog,
        ToolCall("type_text", {"target": editor_ref, "text": "[]"}, "call:current-editor"),
        expected_context_id=context.context_id,
        expected_delivery_id=packed.delivery.delivery_id,
    )
    assert isinstance(resolved.decision, SelectAction)
    assert resolved.decision.action_id == interaction_routes[0].candidate.action_id
    resolved_submit = resolve_grounded_tool_call(
        packed.catalog,
        ToolCall("activate", {"target": submit_ref}, "call:current-submit"),
        expected_context_id=context.context_id,
        expected_delivery_id=packed.delivery.delivery_id,
    )
    assert isinstance(resolved_submit.decision, SelectAction)


@pytest.mark.parametrize("shared_label", ("Apply changes", "保存更改"))
def test_fresh_focused_form_is_an_atomic_foreground_ahead_of_same_label_background(
    shared_label: str,
) -> None:
    def build_context(observation_id: str):
        background_links = tuple(
            SemanticTarget(f"target:background-{index:02d}", "link", f"Background {index:02d}")
            for index in range(40)
        )
        background_action = SemanticTarget("target:background-action", "button", shared_label)
        editor = SemanticTarget(
            "target:active-editor",
            "textbox",
            "Change description",
            {"focused": True, "value": "ready"},
        )
        submit = SemanticTarget(
            "target:active-submit",
            "button",
            shared_label,
            {"semantic.dom.attribute.type": "submit"},
        )
        link_nodes = tuple(f"background-{index:02d}" for index in range(len(background_links)))
        structure = (
            ObservationStructureNode(
                "root",
                "document",
                "Generated workspace",
                child_structure_ids=("sidebar", *link_nodes, "active-form"),
            ),
            ObservationStructureNode(
                "sidebar",
                "navigation",
                "Background controls",
                parent_structure_id="root",
                child_structure_ids=("background-action",),
            ),
            ObservationStructureNode(
                "background-action",
                "button",
                shared_label,
                parent_structure_id="sidebar",
                semantic_target_id=background_action.target_id,
            ),
            *(
                ObservationStructureNode(
                    f"background-{index:02d}",
                    "link",
                    target.label,
                    parent_structure_id="root",
                    semantic_target_id=target.target_id,
                )
                for index, target in enumerate(background_links)
            ),
            ObservationStructureNode(
                "active-form",
                "form",
                "Current change",
                parent_structure_id="root",
                child_structure_ids=("active-editor", "active-submit"),
            ),
            ObservationStructureNode(
                "active-editor",
                "textbox",
                editor.label,
                {"focused": True, "value": "ready"},
                parent_structure_id="active-form",
                semantic_target_id=editor.target_id,
            ),
            ObservationStructureNode(
                "active-submit",
                "button",
                submit.label,
                {"semantic.dom.attribute.type": "submit"},
                parent_structure_id="active-form",
                semantic_target_id=submit.target_id,
            ),
        )
        source = SurfaceObservation(
            observation_id,
            "browser",
            f"revision:{observation_id}",
            ObservationSourceProfile.dom(),
            (*background_links, background_action, editor, submit),
            bindings=(
                *(_binding(observation_id, target.target_id) for target in background_links),
                _binding(observation_id, background_action.target_id),
                _text_binding(observation_id, editor.target_id),
                _binding(observation_id, submit.target_id),
            ),
            structure=structure,
            structure_total_count=len(structure),
        )
        fused = WorldFusion().fuse((source,))
        assert fused.observation is not None
        world = fused.observation
        task = TaskGoal(
            "generated-focused-form",
            f"Finish the current change using {shared_label}",
            allowed_effects=("external_ui_interaction", "query_changed"),
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
            ContextBuilder().build(task, world, actions, evaluation),
            editor,
            submit,
            background_action,
            task,
            world,
            actions,
            evaluation,
        )

    contexts = tuple(build_context(observation_id) for observation_id in ("obs:focused-form:1", "obs:focused-form:2"))
    assert contexts[0][0].context_id != contexts[1][0].context_id

    for context, editor, submit, background_action, task, world, actions, evaluation in contexts:
        plan = context.action_delivery_plan
        assert plan is not None
        interaction = plan.obligation(DeliveryObligationKind.INTERACTION)
        base = plan.obligation(DeliveryObligationKind.BASE_ACTIONS)
        assert interaction is not None and base is not None
        editor_ref = context.grounding.target_refs[editor.target_id]
        submit_ref = context.grounding.target_refs[submit.target_id]
        background_ref = context.grounding.target_refs[background_action.target_id]
        active_refs = {editor_ref, submit_ref}
        required_interaction = interaction.records[: interaction.required_record_count]

        assert plan.foreground_scope == interaction.scope == "interaction"
        assert {
            record.candidate.target_ref
            for record in required_interaction
            if isinstance(record, ActionRouteFragment)
        } == active_refs
        assert base.required_record_count == 0
        assert any(
            isinstance(record, ActionRouteFragment) and record.candidate.target_ref == background_ref
            for record in base.records
        )

        request = ModelDecisionRequest(f"request:{context.context_id}", context)
        wide = CanonicalProviderEnvelopeBinder()
        required_counts = {item.kind.value: 0 for item in plan.obligations}
        required_counts[DeliveryObligationKind.INTERACTION.value] = interaction.required_record_count
        required_delivery = build_model_turn_delivery(
            context,
            include_images=False,
            admitted_records=required_counts,
        )
        required_catalog = compile_grounded_action_catalog(context, required_delivery)
        required_envelope = wide.bind(
            request,
            required_delivery,
            required_catalog,
            identity=_IDENTITY,
            call_profile=_PROFILE,
            output_token_reserve=(
                _PROFILE.max_output_tokens
                + wide.request_budget.protocol_reserve_tokens
                + wide.request_budget.safety_margin_tokens
            ),
        )
        required_tokens = estimate_canonical_envelope(required_envelope).estimated_input_tokens
        packed = _pack(
            request,
            binder=CanonicalProviderEnvelopeBinder(
                request_budget=replace(ModelRequestBudget(), soft_target_tokens=required_tokens)
            ),
        )
        admitted = dict(packed.admitted_record_counts)
        ranks = {item.target_ref: item.rank for item in packed.delivery.action_candidates.candidates}

        assert admitted[DeliveryObligationKind.INTERACTION.value] >= interaction.required_record_count
        assert active_refs <= set(packed.delivery.manifest.executable_refs)
        assert ranks[editor_ref] < ranks[submit_ref]
        if background_ref in packed.delivery.manifest.executable_refs:
            assert ranks[submit_ref] < ranks[background_ref]
        assert "private_bid" not in packed.delivery.view.text
        resolved_submit = resolve_grounded_tool_call(
            packed.catalog,
            ToolCall("activate", {"target": submit_ref}, f"call:{context.context_id}:submit"),
            expected_context_id=context.context_id,
            expected_delivery_id=packed.delivery.delivery_id,
        )
        assert isinstance(resolved_submit.decision, SelectAction)

        builder = ContextBuilder()
        page = builder.page(actions, world, query=shared_label)
        discovery = builder.discovery_result(
            actions,
            world,
            page,
            canonical_world=context.canonical_world,
            grounding=context.grounding,
        )
        discovered = builder.build(
            task,
            world,
            actions,
            evaluation,
            canonical_world=context.canonical_world,
            action_discovery=discovery,
        )
        discovered_plan = discovered.action_delivery_plan
        assert discovered_plan is not None
        discovered_interaction = discovered_plan.obligation(DeliveryObligationKind.INTERACTION)
        discovered_query = discovered_plan.obligation(DeliveryObligationKind.EXPLICIT_QUERY)
        assert discovered_interaction is not None and discovered_query is not None
        assert discovered_interaction.required_record_count == interaction.required_record_count
        assert discovered_query.required_record_count == len(discovered_query.records)

        discovered_required = {
            item.kind.value: item.required_record_count
            for item in discovered_plan.obligations
        }
        discovered_request = ModelDecisionRequest(
            f"request:discovery:{discovered.context_id}",
            discovered,
        )
        discovered_delivery = build_model_turn_delivery(
            discovered,
            include_images=False,
            admitted_records=discovered_required,
        )
        discovered_catalog = compile_grounded_action_catalog(discovered, discovered_delivery)
        discovered_envelope = wide.bind(
            discovered_request,
            discovered_delivery,
            discovered_catalog,
            identity=_IDENTITY,
            call_profile=_PROFILE,
            output_token_reserve=(
                _PROFILE.max_output_tokens
                + wide.request_budget.protocol_reserve_tokens
                + wide.request_budget.safety_margin_tokens
            ),
        )
        discovered_tokens = estimate_canonical_envelope(discovered_envelope).estimated_input_tokens
        discovered_packed = _pack(
            discovered_request,
            binder=CanonicalProviderEnvelopeBinder(
                request_budget=replace(ModelRequestBudget(), soft_target_tokens=discovered_tokens)
            ),
        )
        discovered_counts = dict(discovered_packed.admitted_record_counts)
        assert discovered_counts[DeliveryObligationKind.EXPLICIT_QUERY.value] == len(
            discovered_query.records
        )
        assert (
            discovered_counts[DeliveryObligationKind.INTERACTION.value]
            >= discovered_interaction.required_record_count
        )
        assert active_refs <= set(discovered_packed.delivery.manifest.executable_refs)


def test_repeated_rows_inside_a_focused_form_do_not_become_an_unbounded_hard_bundle() -> None:
    observation_id = "obs:focused-repeated-form"
    editor = SemanticTarget(
        "target:row-editor",
        "textbox",
        "Current row value",
        {"focused": True, "value": "ready"},
    )
    row_actions = tuple(
        SemanticTarget(f"target:row-action:{index}", "button", f"Apply row {index}")
        for index in range(7)
    )
    row_ids = tuple(f"row:{index}" for index in range(len(row_actions)))
    structure = (
        ObservationStructureNode(
            "root",
            "document",
            "Generated repeated editor",
            child_structure_ids=("active-form",),
        ),
        ObservationStructureNode(
            "active-form",
            "form",
            "Current batch",
            parent_structure_id="root",
            child_structure_ids=row_ids,
        ),
        *(
            ObservationStructureNode(
                row_id,
                "listitem",
                f"Row {index}",
                parent_structure_id="active-form",
                child_structure_ids=(
                    ("row-editor", f"row-action:{index}")
                    if index == 0
                    else (f"row-action:{index}",)
                ),
            )
            for index, row_id in enumerate(row_ids)
        ),
        ObservationStructureNode(
            "row-editor",
            "textbox",
            editor.label,
            {"focused": True, "value": "ready"},
            parent_structure_id=row_ids[0],
            semantic_target_id=editor.target_id,
        ),
        *(
            ObservationStructureNode(
                f"row-action:{index}",
                "button",
                target.label,
                parent_structure_id=row_ids[index],
                semantic_target_id=target.target_id,
            )
            for index, target in enumerate(row_actions)
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (editor, *row_actions),
        bindings=(
            _text_binding(observation_id, editor.target_id),
            *(_binding(observation_id, target.target_id) for target in row_actions),
        ),
        structure=structure,
        structure_total_count=len(structure),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation
    task = TaskGoal(
        "focused-repeated-form",
        "Edit the current row and apply it",
        allowed_effects=("external_ui_interaction", "query_changed"),
        risk_profile=RiskProfile.LOW,
    )
    actions = ActionSpaceBuilder().build(task, world)
    region_index = WorldDeliveryIndex.from_observation(world, actions.options)
    editor_region = region_index.target_contexts[editor.target_id].primary_region_key
    region = next(item for item in region_index.regions if item.key == editor_region)
    assert len(region.repeated_item_roots) == len(row_actions)

    context = ContextBuilder().build(
        task,
        world,
        actions,
        TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
        region_index=region_index,
    )
    interaction = context.action_delivery_plan.obligation(DeliveryObligationKind.INTERACTION)
    assert interaction is not None
    assert interaction.required_record_count == 1
    assert interaction.required_record_count < len(row_actions)
    packed = _pack(ModelDecisionRequest("request:focused-repeated-form", context))
    assert context.grounding.target_refs[editor.target_id] in packed.delivery.manifest.executable_refs


def test_every_delivery_prefix_projects_one_subject_per_target_with_exact_manifest_verbs() -> None:
    _task, _world, _actions, _evaluation, context = _context()
    plan = context.action_delivery_plan
    assert plan is not None
    scenarios = [{item.kind.value: 0 for item in plan.obligations}]
    for obligation in plan.obligations:
        for count in range(1, len(obligation.records) + 1):
            counts = {item.kind.value: 0 for item in plan.obligations}
            counts[obligation.kind.value] = count
            scenarios.append(counts)
    scenarios.append({item.kind.value: len(item.records) for item in plan.obligations})

    for counts in scenarios:
        projection = plan.projection(counts)
        refs = tuple(item.target_ref for item in projection.candidates)
        assert len(refs) == len(set(refs))
        delivery = build_model_turn_delivery(
            context,
            include_images=False,
            admitted_records=counts,
        )
        operations_by_target: dict[str, list[str]] = {}
        for route in delivery.manifest.action_routes:
            operations = operations_by_target.setdefault(route.source_ref, [])
            if route.operation not in operations:
                operations.append(route.operation)
        candidate_lines = tuple(line for line in delivery.view.text.splitlines() if line.lstrip().startswith("rank="))
        for candidate in projection.candidates:
            matching = tuple(line for line in candidate_lines if f"[{candidate.target_ref}]" in line)
            assert len(matching) == 1
            rendered = re.search(r" verbs=(\[[^]]*\])", matching[0])
            assert rendered is not None
            assert json.loads(rendered.group(1)) == operations_by_target[candidate.target_ref]


@settings(max_examples=12, deadline=None)
@given(soft_target_tokens=st.integers(min_value=1, max_value=4_096))
def test_focused_multi_verb_target_is_one_atomic_manifest_catalog_and_resolver_capability(
    soft_target_tokens: int,
) -> None:
    _task, _world_value, _actions, _evaluation, context = _multi_verb_context()
    plan = context.action_delivery_plan
    assert plan is not None
    interaction = plan.obligation(DeliveryObligationKind.INTERACTION)
    assert interaction is not None
    assert interaction.required_record_count == len(interaction.records) == 2
    assert {item.public_route[0] for item in interaction.records} == {"press_key", "type_text"}

    with pytest.raises(ValueError, match="prefix"):
        build_model_turn_delivery(
            context,
            include_images=False,
            admitted_records={interaction.kind.value: 1},
        )

    packed = _pack(
        ModelDecisionRequest("request:multi-verb-focused-control", context),
        binder=CanonicalProviderEnvelopeBinder(
            request_budget=ModelRequestBudget(soft_target_tokens=soft_target_tokens),
        ),
    )
    target_ref = next(iter(context.grounding.target_refs.values()))
    routes = {
        (route.operation, route.source_ref, route.destination_ref)
        for route in packed.delivery.manifest.action_routes
    }
    assert routes == {
        ("press_key", target_ref, ""),
        ("type_text", target_ref, ""),
    }
    assert {item.name for item in packed.catalog.specs} >= {"press_key", "type_text"}
    candidate_line = next(
        line
        for line in packed.delivery.view.text.splitlines()
        if line.lstrip().startswith("rank=") and f"[{target_ref}]" in line
    )
    assert 'verbs=["press_key","type_text"]' in candidate_line
    selected = resolve_grounded_tool_call(
        packed.catalog,
        ToolCall(
            "type_text",
            {"target": target_ref, "text": "Shanksville"},
            "call:multi-verb-type",
        ),
        expected_context_id=context.context_id,
        expected_delivery_id=packed.delivery.delivery_id,
    ).decision
    assert isinstance(selected, SelectAction)
    assert selected.parameters == {"text": "Shanksville"}


def test_destination_required_candidate_closes_destination_in_same_manifest_and_resolver() -> None:
    task, world, actions, context = _drag_context()
    delivery, catalog = _catalog(context)
    candidate = context.action_candidates.candidates[0]

    assert candidate.operation == "drag_to"
    assert candidate.destination_required is True
    assert len(candidate.destinations) == 2
    destination = candidate.destinations[0]
    assert candidate.target_ref in delivery.manifest.executable_refs
    assert all(item.target_ref in delivery.manifest.executable_refs for item in candidate.destinations)
    assert all(f'"target":"{item.target_ref}"' in delivery.view.text for item in candidate.destinations)

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
    destination_records = context.action_delivery_plan.obligation(DeliveryObligationKind.BASE_ACTIONS).records
    assert len(destination_records) == 2
    assert {item.public_route[2] for item in destination_records} == {
        item.grounding_ref for item in context.complete_actions[0].destinations.items
    }
    assert bound.binding.binding_id == "binding:drag-card"


def test_sparse_public_schema_acceptance_equals_one_private_resolver_row() -> None:
    _task_value, _world_value, _actions, drag_context = _drag_context()
    drag = drag_context.complete_actions[0]
    first_destination, second_destination = drag.destinations.items
    second_source = replace(
        drag,
        action_id="private:drag:second-source-with-different-length",
        target_id="private:second-source",
        target_label="界!",
        target_ref="E9",
        destinations=BoundedSection((second_destination,), 1, False),
    )
    sparse = GroundedToolCompiler().compile(
        (drag, second_source),
        context_id=drag_context.context_id,
    )[0]

    source_refs = (drag.target_ref, second_source.target_ref)
    destination_refs = (
        first_destination.grounding_ref,
        second_destination.grounding_ref,
    )
    expected = {
        (drag.target_ref, first_destination.grounding_ref),
        (drag.target_ref, second_destination.grounding_ref),
        (second_source.target_ref, second_destination.grounding_ref),
    }
    for source_ref in source_refs:
        for destination_ref in destination_refs:
            arguments = {"source": source_ref, "destination": destination_ref}
            schema_accepts = True
            try:
                validate_value(arguments, sparse.public_spec.input_schema, path="command")
            except ValueError:
                schema_accepts = False
            matches = tuple(row for row in sparse.private_resolutions if dict(row.selector_values) == arguments)
            assert schema_accepts
            assert (len(matches) == 1) is ((source_ref, destination_ref) in expected)
            if matches:
                assert (
                    sparse.resolve(arguments, drag_context.context_id, "call:sparse").action_id == matches[0].action_id
                )
            else:
                with pytest.raises(GroundedToolResolutionError):
                    sparse.resolve(arguments, drag_context.context_id, "call:cartesian-gap")

    _task_value, _world_value, _actions, _evaluation, unary_context = _context()
    unary = unary_context.complete_actions[0]
    option_a = replace(
        unary,
        action_id="private:select:短",
        semantic_action="select_option",
        operation="select_option",
        target_id="private:duplicate-label-a",
        target_label="短!",
        target_ref="E20",
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "string", "enum": ["甲", "!"]}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    option_b = replace(
        option_a,
        action_id="private:select:longer-binding-identity",
        target_id="private:duplicate-label-b",
        target_label="短!",
        target_ref="E21",
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "string", "enum": ["乙✓"]}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    tools = {
        item.canonical_operation: item
        for item in GroundedToolCompiler().compile(
            (unary, option_a, option_b),
            context_id=unary_context.context_id,
        )
    }
    assert {"activate", "select_option"} == set(tools)
    select = tools["select_option"]
    for arguments, expected_acceptance in (
        ({"target": "E20", "value": "甲"}, True),
        ({"target": "E20", "value": "!"}, True),
        ({"target": "E20", "value": "乙✓"}, False),
        ({"target": "E21", "value": "乙✓"}, True),
        ({"target": "E21", "value": "甲"}, False),
    ):
        try:
            validate_value(arguments, select.public_spec.input_schema, path="command")
            accepted = True
        except ValueError:
            accepted = False
        matches = []
        for row in select.private_resolutions:
            if dict(row.selector_values) != {"target": arguments["target"]}:
                continue
            try:
                validate_value(
                    {"value": arguments["value"]},
                    row.parameter_schema,
                    path="command",
                )
            except ValueError:
                continue
            matches.append(row)
        assert accepted
        assert (len(matches) == 1) is expected_acceptance
        if matches:
            decision = select.resolve(arguments, unary_context.context_id, "call:business-domain")
            assert decision.action_id == matches[0].action_id
        else:
            with pytest.raises(GroundedToolResolutionError):
                select.resolve(arguments, unary_context.context_id, "call:wrong-domain")


def test_find_controls_returns_one_owner_bounded_page_without_store_inventory() -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    page = builder.page(actions, world, query="Zulu control")
    discovery = builder.discovery_result(
        actions,
        world,
        page,
        canonical_world=context_value.canonical_world,
        grounding=context_value.grounding,
    )
    state = RunState(world, evaluation, 2, action_page=builder.page(actions, world))
    state.install_canonical_world(context_value.canonical_world)
    request = RequestActionPage("context:test", "Zulu control")
    step = CoreAgentLoop(None, None, None, context_builder=builder)._action_page(
        task, state, actions, context_value, request
    )
    transition = state.delivery_store.reduce(step, step_index=1)
    state.apply(step, delivery_transition=transition)
    context = builder.build(
        task,
        world,
        actions,
        evaluation,
        action_page=state.action_page,
        action_discovery=state.action_discovery,
    )
    query = context.action_delivery_plan.obligation(DeliveryObligationKind.EXPLICIT_QUERY)

    assert discovery.result_coverage == "partial"
    assert len(discovery.matches) == 1
    assert not hasattr(state.delivery_store, "action_query")
    assert query is not None
    assert len(query.records) == len(discovery.matches)


def test_find_controls_reuses_current_world_derivations(monkeypatch) -> None:
    task, world, actions, evaluation, context = _context()
    builder = ContextBuilder()
    page = builder.page(
        actions,
        world,
        query="Settings",
        region_index=context.region_index,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("same-World discovery cannot rebuild the full model World")

    monkeypatch.setattr(context_builder_module, "project_model_world", forbidden)
    monkeypatch.setattr(context_builder_module, "project_actor_world_snapshot", forbidden)
    monkeypatch.setattr(
        context_builder_module.WorldDeliveryIndex,
        "from_observation",
        forbidden,
    )

    result = builder.discovery_result(
        actions,
        world,
        page,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        grounding=context.grounding,
    )

    assert result.matches
    assert {item.target_ref for item in result.matches} <= set(context.grounding.target_refs.values())

    state = RunState(world, evaluation, 2, action_page=builder.page(actions, world, region_index=context.region_index))
    state.install_canonical_world(context.canonical_world)
    step = CoreAgentLoop(None, None, None, context_builder=builder)._action_page(
        task,
        state,
        actions,
        context,
        RequestActionPage(context.context_id, "Settings"),
    )

    assert step.feedback == "action_page_ready"
    assert step.action_page_result is not None
    assert step.action_page_result.matches == result.matches


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
    step = CoreAgentLoop(None, None, None)._action_page(task, state, actions, context, request)
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


def test_find_controls_empty_result_does_not_redirect_to_readable_content_search() -> None:
    _task, world, actions, _evaluation, context = _context()
    builder = ContextBuilder()
    page = builder.page(actions, world, query="Portland Maine link activate")
    discovery = builder.discovery_result(
        actions,
        world,
        page,
        canonical_world=context.canonical_world,
        grounding=context.grounding,
    )

    assert discovery.matches == ()
    assert discovery.result_coverage == "empty"
    assert discovery.to_public_value()["searched_domain"] == "executable_controls"
    assert discovery.suggested_next == ""


def test_find_controls_projects_candidate_owned_unmatched_query_terms() -> None:
    _task, world, actions, _evaluation, context = _context()
    builder = ContextBuilder()
    page = builder.page(actions, world, query="Settings period")
    discovery = builder.discovery_result(
        actions,
        world,
        page,
        canonical_world=context.canonical_world,
        grounding=context.grounding,
    )

    assert discovery.matches
    assert discovery.unmatched_terms == ("period",)
    assert discovery.to_public_value()["unmatched_terms"] == ("period",)


def test_find_controls_tool_return_routes_are_all_callable_in_the_next_catalog() -> None:
    task, world, actions, evaluation, context = _context()
    builder = ContextBuilder()
    initial_delivery, initial_catalog = _catalog(context)
    request = resolve_grounded_tool_call(
        initial_catalog,
        ToolCall("find_controls", {"query": "Settings"}, "call:find-settings"),
        expected_context_id=context.context_id,
        expected_delivery_id=initial_delivery.delivery_id,
    ).decision
    state = RunState(world, evaluation, 1, action_page=builder.page(actions, world))
    state.install_canonical_world(context.canonical_world)
    step = CoreAgentLoop(None, None, None, context_builder=builder)._action_page(
        task,
        state,
        actions,
        context,
        request,
    )
    assert step.action_page_result is not None
    assert len(step.action_page_result.matches) > 1
    found = builder.build(
        task,
        world,
        actions,
        evaluation,
        canonical_world=context.canonical_world,
        action_discovery=step.action_page_result,
    )
    packed = TurnPacker().pack(
        ModelDecisionRequest("request:find-settings-result", found, step),
        binder=CanonicalProviderEnvelopeBinder(
            request_budget=ModelRequestBudget(soft_target_tokens=1),
        ),
        identity=_IDENTITY,
        call_profile=_PROFILE,
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
        history_messages=(
            ModelResponse(
                parts=[
                    ToolCallPart(
                        "find_controls",
                        {"query": "Settings"},
                        "call:find-settings",
                    )
                ]
            ),
        ),
        pending_tool_call_id="call:find-settings",
        pending_tool_name="find_controls",
    )
    query = found.action_delivery_plan.obligation(DeliveryObligationKind.EXPLICIT_QUERY)
    assert query is not None
    assert dict(packed.admitted_record_counts)[DeliveryObligationKind.EXPLICIT_QUERY.value] == len(query.records)
    assert packed.delivery.tool_result is not None
    assert to_json_compatible(packed.delivery.tool_result.return_value) == to_json_compatible(
        step.action_page_result.to_public_value()
    )

    offered_routes = {
        (route.operation, route.source_ref, route.destination_ref) for route in packed.delivery.manifest.action_routes
    }
    returned_routes = {
        (match.operation, match.target_ref, destination_ref)
        for match in step.action_page_result.matches
        for destination_ref in (match.destination_refs or ("",))
    }
    assert returned_routes <= offered_routes
    for operation, source_ref, destination_ref in returned_routes:
        arguments = (
            {"source": source_ref, "destination": destination_ref} if destination_ref else {"target": source_ref}
        )
        resolution = resolve_grounded_tool_call(
            packed.catalog,
            ToolCall(operation, arguments, f"call:returned:{source_ref}:{destination_ref or 'none'}"),
            expected_context_id=found.context_id,
            expected_delivery_id=packed.delivery.delivery_id,
        )
        assert resolution.decision.tool_call_id.startswith("call:returned:")


def test_action_delivery_fails_closed_if_a_discovery_route_is_not_current() -> None:
    task, world, actions, evaluation, context = _context()
    builder = ContextBuilder()
    page = builder.page(actions, world, query="Settings")
    discovery = builder.discovery_result(
        actions,
        world,
        page,
        canonical_world=context.canonical_world,
        grounding=context.grounding,
    )
    corrupted = replace(
        discovery,
        matches=(replace(discovery.matches[0], target_ref="E999"), *discovery.matches[1:]),
    )

    with pytest.raises(ValueError, match="must close every returned route"):
        builder.build(
            task,
            world,
            actions,
            evaluation,
            canonical_world=context.canonical_world,
            action_discovery=corrupted,
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


def test_bounded_base_page_and_fresh_focus_survive_a_one_route_soft_target() -> None:
    task, world, _actions, evaluation, _context_value = _context()
    focused_world = replace(
        world,
        targets=tuple(
            replace(target, state={**dict(target.state), "focused": True})
            if target.target_id == "target:alpha"
            else target
            for target in world.targets
        ),
    )
    actions = ActionSpaceBuilder().build(task, focused_world)
    context = ContextBuilder().build(task, focused_world, actions, evaluation)
    plan = context.action_delivery_plan
    assert plan is not None

    foreground = next(item for item in plan.obligations if item.scope == plan.foreground_scope)
    base = plan.obligation(DeliveryObligationKind.BASE_ACTIONS)
    interaction = plan.obligation(DeliveryObligationKind.INTERACTION)
    assert foreground.kind is DeliveryObligationKind.BASE_ACTIONS
    assert base is not None and interaction is not None
    ranked = base.records[0]
    focused = interaction.records[0]
    assert isinstance(ranked, ActionRouteFragment)
    assert isinstance(focused, ActionRouteFragment)
    assert ranked.candidate.label == "Settings"
    assert "Account Preferences" in ranked.candidate.functional_path
    assert ranked.inclusion_reason in {"automatic_relevance", "viewport_relevance"}
    assert focused.candidate.label == "Alpha control"
    assert focused.inclusion_reason == "focused"

    counts = {item.kind.value: 0 for item in plan.obligations}
    counts[DeliveryObligationKind.BASE_ACTIONS.value] = 1
    one_route_delivery = build_model_turn_delivery(
        context,
        include_images=False,
        admitted_records=counts,
    )
    one_route_catalog = compile_grounded_action_catalog(context, one_route_delivery)
    request = ModelDecisionRequest("request:focused-first", context)
    wide = CanonicalProviderEnvelopeBinder()
    one_route_envelope = wide.bind(
        request,
        one_route_delivery,
        one_route_catalog,
        identity=_IDENTITY,
        call_profile=_PROFILE,
        output_token_reserve=(
            _PROFILE.max_output_tokens
            + wide.request_budget.protocol_reserve_tokens
            + wide.request_budget.safety_margin_tokens
        ),
    )
    one_route_tokens = estimate_canonical_envelope(one_route_envelope).estimated_input_tokens
    packed = _pack(
        request,
        binder=CanonicalProviderEnvelopeBinder(
            request_budget=replace(
                ModelRequestBudget(),
                soft_target_tokens=one_route_tokens,
            )
        ),
    )
    resolved_ranked = resolve_grounded_tool_call(
        packed.catalog,
        ToolCall("activate", {"target": ranked.candidate.target_ref}, "call:ranked-anchor"),
        expected_context_id=context.context_id,
        expected_delivery_id=packed.delivery.delivery_id,
    )
    resolved_focused = resolve_grounded_tool_call(
        packed.catalog,
        ToolCall("activate", {"target": focused.candidate.target_ref}, "call:focused-anchor"),
        expected_context_id=context.context_id,
        expected_delivery_id=packed.delivery.delivery_id,
    )

    assert sum(dict(packed.admitted_record_counts).values()) == len(base.records) + 1
    assert (
        dict(packed.admitted_record_counts)[DeliveryObligationKind.BASE_ACTIONS.value]
        == len(base.records)
        == base.required_record_count
    )
    assert dict(packed.admitted_record_counts)[DeliveryObligationKind.INTERACTION.value] == 1
    assert ranked.candidate.target_ref in packed.delivery.manifest.executable_refs
    assert focused.candidate.target_ref in packed.delivery.manifest.executable_refs
    assert isinstance(resolved_ranked.decision, SelectAction)
    assert isinstance(resolved_focused.decision, SelectAction)
    assert resolved_ranked.decision.action_id == ranked.candidate.action_id
    assert resolved_focused.decision.action_id == focused.candidate.action_id


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
            replace(item, label=label) if item.target_id == "target:zulu" else item for item in world.targets
        ),
        sources=tuple(
            replace(
                source,
                targets=tuple(
                    replace(item, label=label) if item.target_id == "target:zulu" else item for item in source.targets
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
        actions,
        world,
        page,
        canonical_world=base.canonical_world,
        grounding=base.grounding,
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
    with pytest.raises(GroundedToolResolutionError) as stale_region:
        resolve_grounded_tool_call(
            catalog,
            ToolCall("read_region", {"region_ref": "R999999"}, "call:stale-region"),
            expected_context_id=context.context_id,
            expected_delivery_id=delivery.delivery_id,
        )

    assert selected.action_id == candidate.action_id
    assert opened.kind is DecisionKind.READ_REGION
    assert found_content.kind is DecisionKind.SEARCH_PAGE_CONTENT
    assert found_actions.kind is DecisionKind.FIND_CONTROLS
    assert stale_region.value.code is GroundedToolResolutionCode.GROUNDING_GAP
    assert "read_region" not in tuple(item.semantic_action for item in context.complete_actions)


def test_read_region_and_search_results_preserve_grounding_for_returned_readable_controls() -> None:
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
    forbidden = {"actionable", "action_refs"}
    opened_json = json.dumps(to_json_compatible(opened))
    content_json = json.dumps(to_json_compatible(content))

    assert all(value not in opened_json for value in forbidden)
    assert all(value not in content_json for value in forbidden)
    grounded = tuple(item for item in content["items"] if str(item.get("target_ref", "")).startswith("E"))
    assert grounded
    operations_by_ref = {
        ref: tuple(sorted({option.operation for option in context.complete_actions if option.target_ref == ref}))
        for ref in {str(item["target_ref"]) for item in grounded}
    }
    assert all(tuple(sorted(item["verbs"])) == operations_by_ref[item["target_ref"]] for item in grounded)
    assert opened["executable_grounding"] == "attached_to_returned_readable_targets"
    assert content["executable_grounding"] == "attached_to_returned_readable_targets"

    delivery, catalog = _catalog(context)
    selected = grounded[0]
    resolution = resolve_grounded_tool_call(
        catalog,
        ToolCall(selected["verbs"][0], {"target": selected["target_ref"]}, "call:read-grounding"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    )
    assert isinstance(resolution.decision, SelectAction)


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


def test_only_admitted_action_route_fragments_enter_manifest_and_rank_cannot_expand_region() -> None:
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
        if isinstance(fragment, ActionRouteFragment)
        for route in (fragment.public_route,)
    }
    assert actual == expected_mandatory
    assert rejected.isdisjoint(actual)

    assert mandatory_only.view.coverage["expanded_regions"] == 0
    assert mandatory_only.view.coverage["candidate_region_expansion_reason"] == "none"


def test_unadmitted_current_actions_cannot_bypass_the_delivery_manifest() -> None:
    _task, _world, _actions, _evaluation, context = _context()
    plan = context.action_delivery_plan
    assert plan is not None
    empty_counts = {item.kind.value: 0 for item in plan.obligations}
    hidden_delivery = build_model_turn_delivery(
        context,
        include_images=False,
        admitted_records=empty_counts,
    )
    visible_delivery = build_model_turn_delivery(context, include_images=False)
    assert hidden_delivery.manifest.action_routes == ()

    hidden_catalog = compile_grounded_action_catalog(context, hidden_delivery)
    visible_catalog = compile_grounded_action_catalog(context, visible_delivery)
    visible_activate = next(item for item in visible_catalog.specs if item.name == "activate")
    assert all(item.name != "activate" for item in hidden_catalog.specs)
    assert "enum" not in visible_activate.input_schema["properties"]["target"]

    current = next(item for item in context.complete_actions if item.operation == "activate")
    assert current.target_ref not in hidden_delivery.manifest.executable_refs
    with pytest.raises(GroundedToolResolutionError) as exc_info:
        resolve_grounded_tool_call(
            hidden_catalog,
            ToolCall("activate", {"target": current.target_ref}, "call:hidden-current-action"),
            expected_context_id=context.context_id,
            expected_delivery_id=hidden_delivery.delivery_id,
        )
    assert exc_info.value.code is GroundedToolResolutionCode.UNKNOWN_OPERATION


def test_unadmitted_ref_cannot_alias_a_delivered_route_of_the_same_operation() -> None:
    _task, _world, _actions, _evaluation, context = _context()
    plan = context.action_delivery_plan
    assert plan is not None
    counts = {item.kind.value: 0 for item in plan.obligations}
    counts[DeliveryObligationKind.BASE_ACTIONS.value] = 1
    delivery = build_model_turn_delivery(
        context,
        include_images=False,
        admitted_records=counts,
    )
    catalog = compile_grounded_action_catalog(context, delivery)
    delivered = {
        (route.operation, route.source_ref, route.destination_ref) for route in delivery.manifest.action_routes
    }
    omitted = next(
        option
        for option in context.complete_actions
        if option.destination_mode == "forbidden"
        and (option.operation, option.target_ref, "") not in delivered
        and any(route.operation == option.operation for route in delivery.manifest.action_routes)
    )

    with pytest.raises(GroundedToolResolutionError) as exc_info:
        stale_call = ToolCall(
            omitted.operation,
            {"target": omitted.target_ref},
            "call:stale-alias",
        )
        resolve_grounded_tool_call(
            catalog,
            stale_call,
            expected_context_id=context.context_id,
            expected_delivery_id=delivery.delivery_id,
        )
    assert exc_info.value.code is GroundedToolResolutionCode.GROUNDING_GAP
    feedback = grounded_tool_rejection_decision(
        exc_info.value,
        stale_call,
        context.context_id,
        context,
        delivery.manifest,
    )
    assert feedback.result["target"] == {}
    assert feedback.result["supported_operations"] == ()


def test_same_world_search_result_admits_its_exact_returned_action_route() -> None:
    _task, world, _actions, evaluation, context = _context()
    target = next(item for item in context.complete_actions if item.target_label == "Zulu control")
    result = inspect_outcome_public(
        inspect_actor_world(
            context.actor_world,
            context.grounding,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            observation=world,
            action="find",
            query="Zulu control",
        )
    )
    decision = SearchPageContentResult(
        context.context_id,
        "search_page_content",
        {"query": "Zulu control"},
        result,
        "call:same-world-search",
    )
    committed = StepResult(decision, world, world, evaluation, feedback="local_tool_result")
    empty_counts = {item.kind.value: 0 for item in context.action_delivery_plan.obligations}
    delivery = build_model_turn_delivery(
        context,
        include_images=False,
        admitted_records=empty_counts,
        committed_step=committed,
        pending_tool_call_id=decision.tool_call_id,
        pending_tool_name=decision.tool_name,
    )
    catalog = compile_grounded_action_catalog(context, delivery)

    assert target.target_ref not in delivery.view.text
    assert target.target_ref in json.dumps(to_json_compatible(delivery.tool_result.return_value))
    assert (target.operation, target.target_ref, "") in {
        (route.operation, route.source_ref, route.destination_ref) for route in delivery.manifest.action_routes
    }
    selected = resolve_grounded_tool_call(
        catalog,
        ToolCall(target.operation, {"target": target.target_ref}, "call:returned-route"),
        expected_context_id=context.context_id,
        expected_delivery_id=delivery.delivery_id,
    ).decision
    assert selected.action_id == target.action_id


def test_manifest_ref_conservation_for_zero_partial_and_full_prefixes_with_oversized_region() -> None:
    task, world, actions, evaluation, context = _context()
    index = context.region_index
    assert index is not None and index.regions
    oversized_index = replace(
        index,
        regions=(
            replace(index.regions[0], heading="Oversized current region " + "detail " * 2_000),
            *index.regions[1:],
        ),
    )
    canonical_world = CanonicalPublicWorldProjection.build(world, oversized_index, actions)
    context = ContextBuilder().build(
        task,
        world,
        actions,
        evaluation,
        region_index=oversized_index,
        canonical_world=canonical_world,
    )
    plan = context.action_delivery_plan
    assert plan is not None
    selections = tuple(
        dict(zip((item.kind.value for item in plan.obligations), counts, strict=True))
        for counts in product(*(range(len(item.remaining) + 1) for item in plan.obligations))
    )

    for counts in selections:
        delivery = build_model_turn_delivery(
            context,
            include_images=False,
            admitted_records=counts,
        )
        catalog = compile_grounded_action_catalog(context, delivery)
        manifest_refs = (
            *delivery.manifest.executable_refs,
            *delivery.manifest.readonly_refs,
            *delivery.manifest.fact_refs,
            *delivery.manifest.region_refs,
        )
        assert all(f"[{ref}]" in delivery.view.text for ref in manifest_refs)
        compiled_routes = {
            (
                binding.canonical_operation,
                str(
                    dict(row.selector_values).get("target") or dict(row.selector_values).get("source") or row.target_ref
                ),
                str(dict(row.selector_values).get("destination", "")),
            )
            for binding in catalog.bindings
            if hasattr(binding, "private_resolutions")
            for row in binding.private_resolutions
        }
        assert compiled_routes == {
            (route.operation, route.source_ref, route.destination_ref) for route in delivery.manifest.action_routes
        }


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


def test_turn_packer_hard_admits_bounded_base_capability_set_and_reprices_catalog() -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    context = builder.build(task, world, actions, evaluation)
    plan = context.action_delivery_plan
    assert plan is not None and sum(len(item.remaining) for item in plan.obligations) >= 2
    request = ModelDecisionRequest("request:packing-property", context)
    wide = CanonicalProviderEnvelopeBinder()

    foreground = next(item for item in plan.obligations if item.scope == plan.foreground_scope)

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

    required_count = foreground.required_record_count
    assert required_count == len(foreground.records) > 1
    required_total = total(required_count)
    exact = CanonicalProviderEnvelopeBinder(
        request_budget=ModelRequestBudget(
            model_context_window=required_total + 5_000,
            max_output_tokens=0,
            protocol_reserve_tokens=0,
            safety_margin_tokens=0,
            admission_limit=required_total,
        )
    )
    packed = _pack(
        request,
        binder=exact,
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )

    assert dict(packed.admitted_record_counts)[foreground.kind.value] == required_count
    assert packed.packing_backoff_count == 0
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
def test_changed_action_fanout_uses_only_the_fresh_world_projection(count: int) -> None:
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
    option = before_actions.options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    bound = ActionBinder().bind(selection, before, "context:fanout", tool_call_id="call:fanout")
    action_result = ActionResult(bound.request_id, DispatchStatus.SENT, "fixture", True)
    effect_step = StepResult(
        SelectAction("context:fanout", option.action_id, tool_call_id="call:fanout"),
        before,
        after,
        TaskEvaluation(
            task.task_id,
            after.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "generated fanout",
        ),
        execution_receipts=ExecutionReceiptBatch(
            (ExecutionReceipt(bound, action_result, before.observation_id, after.observation_id),),
            ExecutionCompletion.COMPLETE,
        ),
        feedback="action_dispatched",
        public_world_delta=delta,
        before_public_world=canonical_world(before, before_actions),
        after_public_world=canonical_world(after, after_actions),
    )
    store = ObservationDeliveryStore().reduce(effect_step, step_index=1).next_store
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
    )
    assert store == ObservationDeliveryStore()
    assert context.current_observation is not None
    assert context.current_observation.observation_id == after.observation_id
    assert {item.kind.value for item in context.action_delivery_plan.obligations}.isdisjoint(
        {"effect_actions", "page_directory"}
    )

    packed = _pack(
        ModelDecisionRequest(f"request:fanout:{count}", context),
        binder=GroundedPolicyContextBinder(),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )

    assert "PageMap regions=" in packed.delivery.view.text
    assert "LatestEffect" not in packed.delivery.view.text
    assert "ChangedRegions" not in packed.delivery.view.text
    assert "new_document" not in packed.delivery.view.text
    assert "read_next_page" not in {item.name for item in packed.catalog.specs}
    assert packed.admitted_envelope.token_breakdown.estimated_input_tokens <= ModelRequestBudget().soft_target_tokens
    assert packed.admitted_envelope.token_breakdown.estimated_input_tokens <= ModelRequestBudget().admission_limit
    assert packed.admitted_envelope.token_breakdown.complete_request_tokens <= ModelRequestBudget().model_context_window


def test_complete_query_capability_set_is_admitted_before_other_groups(
    monkeypatch,
) -> None:
    task, world, actions, evaluation, context_value = _context()
    builder = ContextBuilder()
    query_page = builder.page(actions, world, query="Settings")
    discovery = builder.discovery_result(
        actions,
        world,
        query_page,
        canonical_world=context_value.canonical_world,
        grounding=context_value.grounding,
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
    query_record_count = len(context.action_delivery_plan.obligation(DeliveryObligationKind.EXPLICIT_QUERY).records)
    required_index = next(
        index for index, counts in enumerate(attempts) if counts.get(query_kind) == query_record_count
    )
    first_extension = attempts[required_index + 1]
    assert first_extension[query_kind] == query_record_count
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


@pytest.mark.parametrize("count", (1, 2, 16, 32))
def test_owner_bounded_result_reaches_physical_request_without_store_projection(count: int) -> None:
    values = tuple(
        {
            "identity": {"display": f"Reader {index} 界🙂"},
            "content": {
                "text": f"complete entry {index} " + "深" * 80,
                "metadata": {"nested": {"ordinal": index, "retained": True}},
            },
        }
        for index in range(count)
    )
    context = _context_with_direct_result(values)
    packed = _pack(
        ModelDecisionRequest(f"request:public-results-{count}", context),
        binder=GroundedPolicyContextBinder(),
    )
    physical = packed.admitted_envelope.envelope.physical_content()
    delivered = tuple(physical["messages"][-1]["parts"][0]["return_value"]["items"])
    assert delivered == values
    assert packed.delivery.tool_result is not None
    assert tuple(packed.delivery.tool_result.return_value["items"]) == values
    assert not hasattr(packed.delivery, "public_results")
    assert "[TRUNCATED]" not in packed.admitted_envelope.envelope.user_text


@settings(max_examples=8, deadline=None)
@given(
    count=st.sampled_from((1, 2, 16, 32)),
    depth=st.integers(min_value=0, max_value=6),
    text_value=st.text(alphabet="abc 界🙂é", min_size=1, max_size=120),
)
def test_generated_public_result_shapes_remain_atomic_through_physical_request(
    count: int,
    depth: int,
    text_value: str,
) -> None:
    nested: object = {"text": text_value, "ordinal": 0}
    for level in range(depth):
        nested = {f"level_{level}": nested, "retained": True}
    values = tuple(
        {"record": nested, "ordinal": index, "pair": {"left": f"L{index}", "right": text_value}}
        for index in range(count)
    )
    context = _context_with_direct_result(values)
    packed = _pack(ModelDecisionRequest(f"request:generated-results-{count}-{depth}", context))
    physical = packed.admitted_envelope.envelope.physical_content()

    assert physical["messages"][-1]["parts"][0]["return_value"]["items"] == values


def test_current_tool_result_is_never_structurally_backed_off_by_turn_packer() -> None:
    values = tuple(
        {
            "author": f"Reader {index}",
            "comment": ("complete unicode evidence 界🙂 " * 60) + str(index),
        }
        for index in range(2)
    )
    context = _context_with_direct_result(values)
    request = ModelDecisionRequest("request:public-result-boundary", context)
    plan = context.action_delivery_plan
    assert plan is not None
    unconstrained = _pack(request)
    assert unconstrained.delivery.tool_result is not None
    assert tuple(unconstrained.delivery.tool_result.return_value["items"]) == values
    two_record_tokens = unconstrained.admitted_envelope.token_breakdown.estimated_input_tokens
    exact_fit = CanonicalProviderEnvelopeBinder(
        request_budget=ModelRequestBudget(
            soft_target_tokens=two_record_tokens,
            model_context_window=two_record_tokens + 5_000,
            max_output_tokens=0,
            protocol_reserve_tokens=0,
            safety_margin_tokens=0,
            admission_limit=two_record_tokens,
        )
    )
    one_token_short = replace(
        exact_fit,
        request_budget=replace(
            exact_fit.request_budget,
            soft_target_tokens=two_record_tokens - 1,
            admission_limit=two_record_tokens - 1,
        ),
    )
    exact = _pack(request, binder=exact_fit)
    assert exact.delivery.tool_result is not None
    assert tuple(exact.delivery.tool_result.return_value["items"]) == values
    with pytest.raises(ModelRequestCapacityError):
        _pack(request, binder=one_token_short)


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


def test_action_delivery_permutation_preserves_public_delivery() -> None:
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
