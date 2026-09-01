from dataclasses import replace

from affordance_runtime.actions import ActionOption, ActionRisk, ActionSpace
from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldDocumentView,
    ActorWorldSnapshot,
    ActorWorldSourceView,
)
from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.agent.context.compact_world_renderer import render_compact_actor_world
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.world_projection import project_model_world as _project_model_world
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.surfaces.semantic_shape import explicit_role_semantic_shape
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationConflict,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from affordance_runtime.world import (
    ObservationStructureNode as _ObservationStructureNode,
)
from tests.support.action_contracts import verification_kwargs
from tests.support.canonical_world import canonical_world
from tests.support.model_delivery import catalog_for, resolve_catalog_call
from tests.support.world import fused_world


def ObservationStructureNode(*args, **kwargs):
    """Declare topology for hand-built source fixtures."""

    role = str(args[1] if len(args) > 1 else kwargs["role"])
    child_ids = args[5] if len(args) > 5 else kwargs.get("child_structure_ids", ())
    target_id = args[6] if len(args) > 6 else kwargs.get("semantic_target_id", "")
    kwargs.setdefault(
        "semantic_shape",
        explicit_role_semantic_shape(
            role,
            has_children=bool(child_ids),
            has_semantic_target=bool(target_id),
        ),
    )
    return _ObservationStructureNode(*args, **kwargs)


def project_model_world(observation, budget, *args, **kwargs):
    return _project_model_world(observation, budget, *args, canonical_projection=canonical_world(observation), **kwargs)


_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _evaluation(task: TaskGoal, observation_id: str) -> TaskEvaluation:
    return TaskEvaluation(
        task.task_id,
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "not complete",
    )


def test_model_world_projection_is_bounded_and_route_free() -> None:
    observation = fused_world(
        "world:private-observation",
        tuple(
            SemanticTarget(
                f"target:{index}",
                "button",
                "label " + "x" * 500,
                {**{f"field:{item}": "v" * 300 for item in range(12)}, "selector": "#private"},
                {f"relation:{item}": f"target:{item}" for item in range(12)},
            )
            for index in range(5)
        ),
        tuple(StateFact(f"fact:{index}", "target:0", "ready", True, "source:private") for index in range(9)),
        surface="dom",
    )
    observation = replace(
        observation,
        conflicts=(ObservationConflict("conflict:private", "target:0", "ready", "sources disagree"),),
    )

    view = project_model_world(
        observation,
        ContextProjectionBudget(max_targets=2, max_facts=3, max_facts_per_target=2),
    )

    assert len(view.targets.items) == 2 and view.targets.truncated
    assert len(view.facts.items) == 3 and view.facts.truncated
    representation = repr(view)
    for private in ("world:private-observation", "source:private", "selector", "#private", "conflict:private"):
        assert private not in representation


def test_action_decision_state_survives_unrelated_metadata_pressure() -> None:
    state = {
        **{f"semantic.metadata.{index:02d}": f"value-{index}" for index in range(20)},
        "value": "China",
        "selected_options": ("China",),
        "option_domain": ("China", "France", "Japan"),
        "expanded": False,
        "required": True,
    }
    observation = fused_world(
        "world:select-state",
        (SemanticTarget("target:country", "combobox", "Country", state),),
        surface="dom",
    )

    target = project_model_world(observation, ContextProjectionBudget()).targets.items[0]

    assert target.state_truncated
    assert {
        "value": "China",
        "selected_options": ("China",),
        "option_domain": ("China", "France", "Japan"),
        "expanded": False,
        "required": True,
    }.items() <= target.state.items()


def test_each_supported_decision_state_field_has_projection_priority() -> None:
    decision_values = {
        "value": "current",
        "selected_options": ("current",),
        "checked": True,
        "selected": True,
        "active": True,
        "expanded": True,
        "required": True,
        "option_domain": ("current", "other"),
        "grid_coordinate": {"x": 2, "y": 3},
    }
    metadata = {f"semantic.metadata.{index:02d}": index for index in range(32)}

    for field, value in decision_values.items():
        observation = fused_world(
            f"world:priority:{field}",
            (SemanticTarget("target:1", "control", "Control", {**metadata, field: value}),),
            surface="dom",
        )

        target = project_model_world(observation, ContextProjectionBudget()).targets.items[0]

        assert target.state[field] == value
        assert len(target.state) == 8
        assert target.state_total_count == 33
        assert target.state_truncated


def test_task_view_contains_only_evaluator_supported_facts() -> None:
    observation = fused_world(
        "world:progress",
        (SemanticTarget("target:1", "status", "Status"),),
        (
            StateFact("fact:weak", "target:1", "weak", True, "source:1"),
            StateFact("fact:verified", "target:1", "verified", True, "source:1"),
        ),
        surface="dom",
    )
    task = TaskGoal(
        "progress",
        "Inspect verified state",
        success_criteria=(
            {
                "id": "criterion:verified",
                "kind": "fact_equals",
                "subject_id": "target:1",
                "predicate": "verified",
                "expected_value": True,
            },
        ),
    )
    evaluation = TaskEvaluation(
        task.task_id,
        observation.observation_id,
        TaskEvaluationStatus.COMPLETE,
        "validated",
        criteria=(
            CriterionEvaluation(
                "criterion:verified",
                CriterionEvaluationStatus.SATISFIED,
                ("fact:verified",),
                "supported",
            ),
        ),
        completion_evidence_refs=("fact:verified",),
    )

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        evaluation,
    )

    verified_facts = context.task.evaluation.verified_public_facts
    assert tuple(item.fact_ref for item in verified_facts) == (context.canonical_world.fact_refs["fact:verified"],)
    assert tuple(item.subject_id for item in verified_facts) == ("N1",)
    verified = verified_facts[0]
    matching = tuple(
        fact
        for document in context.actor_world.documents
        for root in document.roots
        for fact in root.facts
        if fact.field == "verified"
    )
    assert matching[0].evidence_ref == verified.fact_ref
    delivery = build_model_turn_delivery(context, include_images=False)
    sections = GroundedPolicyContextBinder._public_context_sections(  # noqa: SLF001 - projection owner gate
        context,
        False,
        delivery,
    )
    assert sections["public"]["task"]["formal_evaluation"]["evidence"] == (
        {"evidence_ref": verified.fact_ref, "field": "verified", "value": True},
    )
    assert "formal_evaluation" not in sections["task_plan"]["task"]
    assert "formal_evaluation" not in GroundedPolicyContextBinder.public_task_plan(context)["task"]
    assert not hasattr(context, "budgets")


def test_model_artifact_is_resolvable_without_exposing_its_private_value() -> None:
    source = SurfaceObservation(
        "surface:artifact",
        "visual",
        "revision:1",
        ObservationSourceProfile.visual(),
        artifacts={"receipt": {"path": "/private/receipt.pdf", "credential": "secret"}},
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    observation = fused.observation
    task = TaskGoal("artifact", "Inspect receipt")

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )

    artifact = context.actor_world.artifacts[0]
    assert artifact["evidence_ref"] == "A1"
    assert artifact["kind"] == "receipt"
    assert "/private/receipt.pdf" not in repr(context)
    assert "secret" not in repr(context)


def test_actor_context_remains_lossless_under_legacy_total_byte_budget() -> None:
    observation = fused_world(
        "world:bounded",
        tuple(
            SemanticTarget(
                f"target:{index}",
                "region",
                "x" * 240,
                {f"field:{item}": "v" * 240 for item in range(8)},
                {f"relation:{item}": "r" * 240 for item in range(8)},
            )
            for index in range(64)
        ),
        tuple(
            StateFact(
                f"fact:{target_index}:{fact_index}",
                f"target:{target_index}",
                f"public_fact:{fact_index}",
                "f" * 240,
                "world:bounded",
            )
            for target_index in range(64)
            for fact_index in range(4)
        ),
        surface="dom",
    )
    task = TaskGoal("bounded", "Inspect the bounded context")
    budget = ContextProjectionBudget(max_total_serialized_bytes=8 * 1024)

    context = ContextBuilder(budget).build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )

    assert serialized_size(context) > budget.max_total_serialized_bytes
    assert sum(item.retained_node_count for item in context.actor_world.documents) == 64
    assert (
        sum(
            sum(fact.field.startswith("public_fact:") for fact in node.facts)
            for document in context.actor_world.documents
            for root in document.roots
            for node in _walk_actor(root)
        )
        == 256
    )
    assert context.actor_world.traversal is None


def test_action_page_reports_runtime_membership_and_truncation_truthfully() -> None:
    observation = fused_world(
        "world:actions",
        (SemanticTarget("target:0", "form", "Target"),),
        surface="dom",
    )
    options = tuple(
        ActionOption(
            f"action:{index}",
            observation.observation_id,
            "read",
            "target:0",
            "observation",
            _EMPTY_SCHEMA,
            schema_digest(_EMPTY_SCHEMA),
            (f"binding:{index}",),
            f"read target {index}",
            (),
            ActionRisk.LOW,
            **verification_kwargs("read", schema_digest(_EMPTY_SCHEMA), ()),
        )
        for index in range(5)
    )
    task = TaskGoal("bounded-actions", "Inspect actions")
    budget = ContextProjectionBudget(max_action_options=2)

    context = ContextBuilder(budget).build(
        task,
        observation,
        ActionSpace(observation.observation_id, options),
        _evaluation(task, observation.observation_id),
    )

    assert len(context.actions.options) == 2
    assert context.actions.total_count == 5
    assert context.actions.truncated and context.actions.has_more


def test_tool_targets_actor_state_and_verbs_are_conserved_to_model_input() -> None:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "enum": ["China", "France"]}},
        "required": ["value"],
        "additionalProperties": False,
    }
    target = SemanticTarget(
        "target:country",
        "combobox",
        "Country",
        {
            **{f"semantic.metadata.{index:02d}": index for index in range(20)},
            "value": "China",
            "selected_options": ("China",),
            "option_domain": ("China", "France"),
            "expanded": False,
            "required": True,
        },
    )
    observation = fused_world("world:country", (target,), surface="dom")
    option = ActionOption(
        "action:country",
        observation.observation_id,
        "select_option",
        target.target_id,
        "external_ui_interaction",
        schema,
        schema_digest(schema),
        ("binding:country",),
        "select country",
        ("external_ui_interaction",),
        ActionRisk.LOW,
        **verification_kwargs("select_option", schema_digest(schema), ("external_ui_interaction",)),
    )
    task = TaskGoal("country", "Select a country")

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, (option,)),
        _evaluation(task, observation.observation_id),
    )
    _, catalog = catalog_for(context)
    rendered = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=context.current_observation,
    )

    tool = next(item for item in catalog.specs if item.name == "select_option")
    target_ref = context.actions.options[0].target_ref
    assert "enum" not in tool.input_schema["properties"]["target"]
    assert any(
        item.selector_values["target"] == target_ref
        for item in catalog.bindings[catalog.specs.index(tool)].private_resolutions
    )
    assert target_ref not in rendered.manifest.executable_refs
    actor_nodes = {
        node.ref: node
        for document in context.actor_world.documents
        for root in document.roots
        for node in _walk_actor(root)
    }
    node = actor_nodes[target_ref]
    assert context.actions.options[0].target_ref == target_ref
    assert context.actions.options[0].operation in next(
        item.verbs for item in context.grounding.entities if item.ref == target_ref
    )
    for field in ("value", "selected_options", "option_domain", "expanded", "required"):
        assert node.state[field] == context.actions.options[0].target_state[field]
    assert "state_coverage=" not in rendered
    assert target_ref not in rendered
    assert "binding:country" not in rendered


def test_complete_delivered_action_inventory_does_not_offer_redundant_find_controls() -> None:
    observation = fused_world(
        "world:single-action",
        (SemanticTarget("target:1", "button", "Submit"),),
        surface="dom",
    )
    option = ActionOption(
        "action:submit",
        observation.observation_id,
        "activate",
        "target:1",
        "external_ui_interaction",
        _EMPTY_SCHEMA,
        schema_digest(_EMPTY_SCHEMA),
        ("binding:submit",),
        "activate submit",
        ("external_ui_interaction",),
        ActionRisk.LOW,
        **verification_kwargs("activate", schema_digest(_EMPTY_SCHEMA), ("external_ui_interaction",)),
    )
    task = TaskGoal("single-action", "Submit")

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, (option,)),
        _evaluation(task, observation.observation_id),
    )
    _, catalog = catalog_for(context)

    assert not context.actions.has_more
    assert {item.action_id for item in context.actions.options} == {"action:submit"}
    assert "find_controls" not in {item.name for item in catalog.specs}


def test_search_page_content_resolves_as_zero_dispatch_local_tool() -> None:
    observation = fused_world(
        "world:inspect",
        (
            SemanticTarget("target:panel", "region", "Details"),
            SemanticTarget("target:issue", "StaticText", "Issue ID ABC-123"),
        ),
        surface="dom",
    )
    task = TaskGoal("inspect", "Read the issue id")
    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )
    _, catalog = catalog_for(context)

    resolution = resolve_catalog_call(
        catalog,
        ToolCall("search_page_content", {"query": "ABC-123"}),
        expected_context_id=context.context_id,
        expected_catalog_id=catalog.catalog_id,
    )

    decision = resolution.decision
    assert decision.tool_name == "search_page_content"
    assert decision.result["kind"] == "Matches"
    assert decision.result["items"][0]["label"] == "Issue ID ABC-123"


def test_search_page_content_recovers_fact_missing_from_actor_snapshot() -> None:
    observation = fused_world(
        "world:full-recovery",
        (SemanticTarget("target:issue", "StaticText", "Visible shell"),),
        (StateFact("fact:issue-id", "target:issue", "issue_id", "ABC-123", "source:fact"),),
        surface="dom",
    )
    task = TaskGoal("inspect-full", "Read the issue id")
    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )
    context = replace(
        context,
        actor_world=ActorWorldSnapshot(
            (
                ActorWorldDocumentView(
                    "S1",
                    "structural",
                    (),
                    0,
                    1,
                    True,
                ),
            ),
            (
                ActorWorldSourceView(
                    "S1",
                    "structural",
                    "structural",
                    "current",
                    "complete",
                    "partial",
                    "not_available",
                ),
            ),
            (),
            (),
            BoundedSection((), 0, False),
            (),
            (),
            (),
        ),
    )
    _, catalog = catalog_for(context)

    resolution = resolve_catalog_call(
        catalog,
        ToolCall("search_page_content", {"query": "ABC-123"}),
        expected_context_id=context.context_id,
        expected_catalog_id=catalog.catalog_id,
    )

    assert resolution.decision.result["coverage"] == "complete"
    assert resolution.decision.result["items"][0]["label"] == "issue_id"
    assert resolution.decision.result["items"][0]["value"] == "ABC-123"


def test_search_page_content_reports_partial_world_coverage() -> None:
    observation = fused_world(
        "world:partial-recovery",
        (SemanticTarget("target:issue", "StaticText", "Issue ABC-123"),),
        surface="dom",
        coverage=CoverageState.TRUNCATED,
    )
    task = TaskGoal("inspect-partial", "Read the issue id")
    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
    )
    _, catalog = catalog_for(context)

    resolution = resolve_catalog_call(
        catalog,
        ToolCall("search_page_content", {"query": "ABC-123"}),
        expected_context_id=context.context_id,
        expected_catalog_id=catalog.catalog_id,
    )

    assert resolution.decision.result["coverage"] == "partial"


def test_read_region_returns_directly_without_changing_next_context_action_authority() -> None:
    targets = tuple(SemanticTarget(f"target:{index}", "button", f"Button {index}") for index in range(1, 6))
    observation = fused_world("world:lens", targets, surface="dom")
    options = tuple(
        ActionOption(
            f"action:{index}",
            observation.observation_id,
            "activate",
            f"target:{index}",
            "external_ui_interaction",
            _EMPTY_SCHEMA,
            schema_digest(_EMPTY_SCHEMA),
            (f"binding:{index}",),
            f"activate button {index}",
            ("external_ui_interaction",),
            ActionRisk.LOW,
            **verification_kwargs("activate", schema_digest(_EMPTY_SCHEMA), ("external_ui_interaction",)),
        )
        for index in range(1, 6)
    )
    action_space = ActionSpace(observation.observation_id, options)
    task = TaskGoal("lens", "Open region five then activate it")
    evaluation = _evaluation(task, observation.observation_id)
    builder = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1))
    first = builder.build(task, observation, action_space, evaluation)
    _, first_catalog = catalog_for(first)
    opened_resolution = resolve_catalog_call(
        first_catalog,
        ToolCall("read_region", {"region_ref": "R1"}),
        expected_context_id=first.context_id,
        expected_catalog_id=first_catalog.catalog_id,
    )
    opened = opened_resolution.decision
    state = RunState(observation, evaluation, 3)
    state.apply(
        StepResult(
            opened,
            observation,
            observation,
            evaluation,
            RunStatus.RUNNING,
            feedback="local_tool_result",
        )
    )

    assert opened.result["kind"] == "Opened"
    second = builder.build(
        task,
        observation,
        action_space,
        evaluation,
        context_generation=state.next_context_generation(),
    )
    _, second_catalog = catalog_for(second)
    rendered = render_compact_actor_world(
        second.actor_world,
        second.grounding,
        include_images=False,
        region_index=second.region_index,
        canonical_world=second.canonical_world,
        observation=second.current_observation,
        selected_region_keys=frozenset(),
    )
    activate = next(item for item in second_catalog.specs if item.name == "activate")

    assert any(projection in rendered for projection in ("projection=page_map", "projection=full"))
    activate_binding = second_catalog.bindings[second_catalog.specs.index(activate)]
    assert {item.selector_values["target"] for item in activate_binding.private_resolutions} == {
        item.target_ref for item in second.complete_actions if item.operation == "activate"
    }
    assert f'[{second.grounding.target_refs["target:1"]}] button "Button 1" verbs=["activate"]' not in rendered


def test_expanded_region_projects_source_structure_sibling_and_current_refs() -> None:
    source = SurfaceObservation(
        "world:lens-proof",
        "dom",
        "revision:proof",
        ObservationSourceProfile.dom(),
        (SemanticTarget("target:buy", "button", "Buy", {"pressed": False}),),
        (),
        (),
        CoverageState.COMPLETE,
        structure=(
            ObservationStructureNode("root", "document", "", child_structure_ids=("row",)),
            ObservationStructureNode(
                "row",
                "group",
                "Offer",
                child_structure_ids=("price-text", "buy-button"),
                parent_structure_id="root",
            ),
            ObservationStructureNode("price-text", "StaticText", "Price $9", parent_structure_id="row"),
            ObservationStructureNode(
                "buy-button",
                "button",
                "Buy",
                parent_structure_id="row",
                semantic_target_id="target:buy",
            ),
        ),
        structure_total_count=4,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    observation = fused.observation
    target_id = observation.targets[0].target_id
    option = ActionOption(
        "action:buy",
        observation.observation_id,
        "activate",
        target_id,
        "external_ui_interaction",
        _EMPTY_SCHEMA,
        schema_digest(_EMPTY_SCHEMA),
        ("binding:buy",),
        "activate buy",
        ("external_ui_interaction",),
        ActionRisk.LOW,
        **verification_kwargs("activate", schema_digest(_EMPTY_SCHEMA), ("external_ui_interaction",)),
    )
    task = TaskGoal("lens-proof", "Buy the offer")
    context = ContextBuilder(replace(ContextProjectionBudget(), max_action_options=1)).build(
        task,
        observation,
        ActionSpace(observation.observation_id, (option,)),
        _evaluation(task, observation.observation_id),
    )
    region = context.region_index.regions[0]

    rendered = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=context.current_observation,
        selected_region_keys=frozenset({region.key}),
    )

    current_ref = context.grounding.target_refs[target_id]
    assert region.source_id == "world:lens-proof"
    assert context.actor_world.documents[0].source_ref == "S1"
    assert 'StaticText "Price $9"' in rendered
    assert f'[{current_ref}] button "Buy" pressed=false verbs=["activate"]' in rendered


def test_explicit_region_lens_keeps_navigation_region_folded_while_candidates_remain_executable() -> None:
    source = SurfaceObservation(
        "world:scoped-lens",
        "dom",
        "revision:scoped-lens",
        ObservationSourceProfile.dom(),
        (
            SemanticTarget("target:home", "link", "Home"),
            SemanticTarget("target:filter", "button", "Filter"),
        ),
        structure=(
            ObservationStructureNode(
                "root",
                "document",
                "Report",
                child_structure_ids=("nav", "main"),
            ),
            ObservationStructureNode(
                "nav",
                "navigation",
                "Primary",
                parent_structure_id="root",
                child_structure_ids=("home",),
            ),
            ObservationStructureNode(
                "home",
                "link",
                "Home",
                parent_structure_id="nav",
                semantic_target_id="target:home",
            ),
            ObservationStructureNode(
                "main",
                "main",
                "Filtered report",
                parent_structure_id="root",
                child_structure_ids=("filter",),
            ),
            ObservationStructureNode(
                "filter",
                "button",
                "Filter",
                parent_structure_id="main",
                semantic_target_id="target:filter",
            ),
        ),
        structure_total_count=5,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    observation = fused.observation
    options = tuple(
        ActionOption(
            f"action:{name}",
            observation.observation_id,
            "activate",
            f"target:{name}",
            "external_ui_interaction",
            _EMPTY_SCHEMA,
            schema_digest(_EMPTY_SCHEMA),
            (f"binding:{name}",),
            f"activate {name}",
            ("external_ui_interaction",),
            ActionRisk.LOW,
            **verification_kwargs(
                "activate",
                schema_digest(_EMPTY_SCHEMA),
                ("external_ui_interaction",),
            ),
        )
        for name in ("home", "filter")
    )
    task = TaskGoal("scoped-lens", "Inspect the filtered report")
    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, options),
        _evaluation(task, observation.observation_id),
    )
    navigation_region = next(item for item in context.region_index.regions if item.role == "navigation")
    main_region = next(item for item in context.region_index.regions if item.role == "main")
    rendered = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=False,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=context.current_observation,
        selected_region_keys=frozenset({main_region.key}),
        action_candidates=context.action_candidates,
    )

    home_ref = context.grounding.target_refs["target:home"]
    filter_ref = context.grounding.target_refs["target:filter"]
    assert home_ref in rendered.manifest.executable_refs
    assert filter_ref in rendered.manifest.executable_refs
    navigation_ref = context.canonical_world.region_refs[navigation_region.key]
    assert navigation_ref in rendered.manifest.region_refs
    assert rendered.coverage["folded_regions"] >= 1
    assert f"region [{navigation_ref}]" not in rendered.text


def test_context_delivers_only_the_workspace_latest_eight_detailed_steps() -> None:
    observation = fused_world("world:history", surface="dom")
    task = TaskGoal("history", "Inspect recent steps")
    steps = tuple(AgentTurnView("abort", reason=f"step:{index}") for index in range(10))

    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
        AgentWorkspace(steps[-8:]),
        current_step_index=len(steps),
    )

    assert tuple(item.reason for item in context.workspace.recent_steps) == tuple(
        f"step:{index}" for index in range(2, 10)
    )
    assert context.current_step_index == 10


def test_policy_places_only_the_latest_transition_beside_the_fresh_world() -> None:
    observation = fused_world("world:policy-history", surface="dom")
    task = TaskGoal("policy-history", "Inspect recent steps")
    steps = tuple(AgentTurnView("abort", reason=f"step:{index}") for index in range(4))
    workspace = AgentWorkspace(steps)
    context = ContextBuilder().build(
        task,
        observation,
        ActionSpace(observation.observation_id, ()),
        _evaluation(task, observation.observation_id),
        workspace,
        current_step_index=len(steps),
    )
    delivery = build_model_turn_delivery(context, include_images=False)

    sections = GroundedPolicyContextBinder._public_context_sections(  # noqa: SLF001 - projection owner gate
        context,
        False,
        delivery,
    )

    previous = sections["current_turn"]["previous_transition"]
    assert previous["result"]["reason"] == "step:3"
    assert sections["public"]["previous_transition"] == previous
    assert tuple(item["result"]["reason"] for item in sections["public"]["recent_trajectory"]) == (
        "step:0",
        "step:1",
        "step:2",
    )
    assert "recent_trajectory" not in sections["current_turn"]
    assert "current_activity" not in sections["current_turn"]
    assert "current_activity" not in sections["public"]
    assert "semantic_events" not in sections["current_turn"]
    assert "activity_summaries" not in sections["current_turn"]
    assert "workspace" not in sections["current_turn"]


def _walk_actor(root):
    yield root
    for child in root.children:
        yield from _walk_actor(child)
