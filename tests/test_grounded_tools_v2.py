from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import numpy as np
import pytest
from browsergym_adapter_support import ax_node, raw_observation
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import (
    AgentDecisionPackage,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    EstablishObjectiveSequence,
    EstablishSetObjective,
    RequestObservation,
    SelectAction,
    SubmitSetPredicateAssessments,
)
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.benchmarks.external_smoke.browsergym_backend import _effective_visibility
from affordance_runtime.benchmarks.external_smoke.browsergym_entity_identity import BrowserGymEntityIdentityMap
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import project_browsergym_observation
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import PRIVATE_CONTROL_PROPERTIES_KEY
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import BrowserGymVerifierSnapshot
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingPolicy,
)
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary import AgentTurnView, ContextBuilder, ModelFailure, ProviderAttemptOrigin
from affordance_runtime.model_boundary.acquisition_projection import ObservationCapabilityView
from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.context import AgentSetControlView
from affordance_runtime.model_policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model_policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model_policy.grounded_tool_port_bridge import (
    GroundedToolCommandPayload,
    GroundedToolDecisionAdapter,
    _command_payload_type,
    _GroundedOperationPayload,
    _runtime_sequential_member_call,
)
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.policy import _build_request
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model_port import ModelCallRecord, ModelConfig
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.aggregate_objective import AggregateObjective
from affordance_runtime.task.task_program import TaskProgram
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
    CoverageState,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


def _context(*, with_boxes=True, mandatory_semantic_control=False):
    raw = raw_observation(
        ax_node("username", "textbox", ""),
        ax_node("password", "textbox", ""),
        ax_node("login", "button", "Login"),
        goal='Enter username "donovan", password "UV", then press Login.',
    )
    raw["screenshot"] = np.full((160, 320, 3), 255, dtype=np.uint8)
    if with_boxes:
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["username"]["bbox"] = [10, 10, 140, 30]
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["password"]["bbox"] = [10, 55, 140, 30]
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["login"]["bbox"] = [10, 100, 80, 30]
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["username"]["label_hint"] = "Username"
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["password"]["label_hint"] = "Password"
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:grounded",
        source_revision="revision:grounded",
        page_identity="page:grounded",
        episode_identity="episode:grounded",
        verifier=BrowserGymVerifierSnapshot(
            "run:grounded",
            "observation:grounded",
            "observation:grounded",
            VerifierFactSource.RESET,
            ExternalVerifierStatus.INCOMPLETE,
            ExternalVerifierReason.VERIFIED_RUNNING,
        ),
        entity_identity=_IDENTITY,
    )
    task = TaskGoal(
        "task:grounded",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    state = AgentLoopState(
        projection.world,
        remaining_turns=5,
        semantic_control_required=mandatory_semantic_control,
    )
    evaluation = TaskEvaluation(
        task.task_id,
        projection.world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projection.world),
        evaluation,
    )
    return context


def test_grounding_index_and_marked_screenshot_share_refs_without_private_geometry() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context)
    refs = [item.ref for item in context.grounding.entities]

    assert refs == ["E1", "E2", "E3"]
    assert all(item.marked for item in context.grounding.entities)
    assert context.image_inputs[0].data != _unmarked_png()
    public = json.dumps(
        to_json_compatible(
            {
                "view": {
                    "task": catalog.view.task_brief,
                    "index": catalog.view.grounding_index,
                    "state": catalog.view.current_state,
                },
                "tools": [item.input_schema for item in catalog.specs],
            }
        )
    )
    assert '"E1"' in public and '"E2"' in public and '"E3"' in public
    assert "bbox" not in public
    assert "entity:" not in public and "action:" not in public and "binding:" not in public


def test_aria_hidden_ancestor_removes_layout_only_control_from_execution_visibility() -> None:
    assert _effective_visibility(True, {"ariaHiddenByAncestor": True}) is False
    assert _effective_visibility(True, {"ariaHiddenByAncestor": False}) is True


def test_schema_equivalent_actions_are_grouped_into_small_verb_tools_and_resolve_privately() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context)
    names = [item.name for item in catalog.specs]

    assert set(names) == {"fill", "click"}
    fill = next(item for item in catalog.specs if item.name == "fill")
    refs_by_label = {item.label: item.ref for item in context.grounding.entities}
    assert set(fill.input_schema["properties"]["target"]["enum"]) == {
        refs_by_label["Username"],
        refs_by_label["Password"],
    }
    assert fill.input_schema["required"] == ("target", "text")
    click = next(item for item in catalog.specs if item.name == "click")
    assert click.input_schema["properties"] == {}
    assert click.input_schema["required"] == ()
    click_package = resolve_grounded_tool_call(
        catalog,
        ToolCall("click", {}),
        expected_context_id=context.context_id,
    )
    assert isinstance(click_package.decision, SelectAction)
    assert click_package.decision.parameters == {}
    package = resolve_grounded_tool_call(
        catalog,
        ToolCall("fill", {"target": refs_by_label["Password"], "text": "UV"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(package, AgentDecisionPackage)
    assert isinstance(package.decision, SelectAction)
    assert package.decision.context_id == context.context_id
    assert package.decision.parameters == {"value": "UV"}
    assert package.decision.action_id.startswith("action:")


def test_mandatory_ingress_exposes_only_typed_objective_tools_and_preserves_value() -> None:
    context = _context(mandatory_semantic_control=True)
    catalog = compile_grounded_tool_catalog(context)
    names = {item.name for item in catalog.specs}

    assert names == {"establish_task_program"}

    def predicate(label: str) -> dict[str, object]:
        return {
            "any_of": [
                {
                    "all_of": [
                        {
                            "kind": "fact_equals",
                            "field_name": "identity.label",
                            "expected": label,
                            "negated": False,
                        }
                    ]
                }
            ]
        }

    package = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "establish_task_program",
            {
                "steps": [
                    {
                        "kind": "entity",
                        "predicate": predicate("Password"),
                        "semantic_action": "type",
                        "parameters": {"value": "UV"},
                    },
                    {
                        "kind": "entity",
                        "predicate": predicate("Login"),
                        "semantic_action": "click",
                    },
                ]
            },
        ),
        expected_context_id=context.context_id,
    )

    assert isinstance(package.decision, EstablishObjectiveSequence)
    assert isinstance(package.decision.sequence, TaskProgram)
    assert package.decision.sequence.steps[0].action_template.parameters == {"value": "UV"}


def test_aggregate_ingress_derives_count_contract_without_model_supplied_result() -> None:
    context = _context(mandatory_semantic_control=True)
    catalog = compile_grounded_tool_catalog(context)

    def predicate(field: str, value: str) -> dict[str, object]:
        return {
            "any_of": [
                {
                    "all_of": [
                        {
                            "kind": "fact_equals",
                            "field_name": field,
                            "expected": value,
                            "negated": False,
                        }
                    ]
                }
            ]
        }

    package = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "establish_task_program",
            {
                "steps": [
                    {
                        "kind": "aggregate",
                        "source_predicate": predicate("identity.role", "textbox"),
                        "operator": "count",
                        "value_field": "",
                        "destination_predicate": predicate("identity.label", "Username"),
                        "semantic_action": "type",
                    }
                ]
            },
        ),
        expected_context_id=context.context_id,
    )

    assert isinstance(package.decision, EstablishObjectiveSequence)
    assert isinstance(package.decision.sequence, TaskProgram)
    objective = package.decision.sequence.steps[0]
    assert isinstance(objective, AggregateObjective)
    assert objective.operator.value == "count"
    assert objective.value_extractor.kind.value == "constant"
    assert objective.destination_selector.expected == "Username"


def test_stale_and_unknown_grounded_refs_are_zero_decision() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context)
    with pytest.raises(GroundedToolResolutionError) as stale:
        resolve_grounded_tool_call(
            catalog,
            ToolCall("click", {"target": "E3"}),
            expected_context_id="context:stale",
        )
    assert stale.value.code is GroundedToolResolutionCode.STALE_CATALOG
    with pytest.raises(GroundedToolResolutionError) as unknown:
        resolve_grounded_tool_call(
            catalog,
            ToolCall("click", {"target": "E99"}),
            expected_context_id=context.context_id,
        )
    assert unknown.value.code is GroundedToolResolutionCode.INVALID_ARGUMENTS


def test_indistinguishable_unmarked_controls_fail_grounding_gap() -> None:
    context = _context(with_boxes=False)
    entities = tuple(
        replace(item, label="", state={}, relation_hints=(), marked=False) if item.role == "textbox" else item
        for item in context.grounding.entities
    )
    context = replace(context, grounding=replace(context.grounding, entities=entities))

    with pytest.raises(GroundedToolResolutionError) as gap:
        compile_grounded_tool_catalog(context)

    assert gap.value.code is GroundedToolResolutionCode.GROUNDING_GAP


def test_duplicate_label_controls_remain_distinct_when_both_are_marked() -> None:
    context = _context()
    entities = tuple(
        replace(item, label="Repeated field", state={}) if item.role == "textbox" else item
        for item in context.grounding.entities
    )
    context = replace(context, grounding=replace(context.grounding, entities=entities))

    catalog = compile_grounded_tool_catalog(context)
    fill = next(item for item in catalog.specs if item.name == "fill")

    assert set(fill.input_schema["properties"]["target"]["enum"]) == {
        item.ref for item in entities if item.role == "textbox"
    }


@dataclass
class _CompactPort:
    commands: list[dict[str, object]]
    provider: str = "zhipu"
    model: str = "glm-4.1v-thinking-flashx"
    endpoint_class: str = "fixture"
    supports_multimodal: bool = True
    last_call: ModelCallRecord | None = None
    calls: int = 0
    messages: list = field(default_factory=list)

    async def generate_structured(self, messages, output_schema, config):
        self.messages = list(messages)
        payload = self.commands[self.calls]
        self.calls += 1
        assert issubclass(output_schema, _GroundedOperationPayload)
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name=output_schema.__name__,
            schema_version="grounded_tools.v2",
            latency_ms=1,
        )
        return output_schema.model_validate(payload)


def test_compact_grounded_bridge_uses_allowlist_flat_command_and_existing_decision() -> None:
    async def scenario():
        context = _context()
        password_ref = next(item.ref for item in context.grounding.entities if item.label == "Password")
        port = _CompactPort([{"op": "fill", "target": password_ref, "text": "UV"}])
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure), adapter.last_internal_error_code
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, SelectAction)
        assert parsed.parameters == {"value": "UV"}
        assert adapter.last_resolution_code is GroundedToolResolutionCode.ACCEPTED
        assert port.calls == 1
        user = port.messages[1].content
        assert isinstance(user, tuple)
        text = user[0].text
        assert "task_brief" in text and "grounding_index" in text and "tool_menu" in text
        assert "context_id" not in text and "action_id" not in text and "target_id" not in text
        assert "bbox" not in text and "selector" not in text

    asyncio.run(scenario())


def test_compact_schema_contains_only_current_operation_fields() -> None:
    payload_type = _command_payload_type(
        (
            ToolSpec(
                "choose_current_target",
                "choose",
                {
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ("target",),
                    "additionalProperties": False,
                },
            ),
        )
    )

    assert set(payload_type.model_json_schema()["properties"]) == {"op", "target"}


def test_compact_grounded_bridge_transports_typed_objective_decision() -> None:
    async def scenario():
        context = _context(mandatory_semantic_control=True)
        port = _CompactPort(
            [
                {
                    "op": "establish_task_program",
                    "steps": [
                        {
                            "kind": "entity",
                            "predicate": {
                                "any_of": [
                                    {
                                        "all_of": [
                                            {
                                                "kind": "fact_equals",
                                                "field_name": "identity.label",
                                                "expected": "Password",
                                            }
                                        ]
                                    }
                                ]
                            },
                            "semantic_action": "type",
                            "parameters": {"value": "UV"},
                        }
                    ],
                }
            ]
        )
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure), adapter.last_internal_error_code
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, EstablishObjectiveSequence)
        assert isinstance(parsed.sequence, TaskProgram)
        assert parsed.sequence.steps[0].action_template.parameters == {"value": "UV"}

    asyncio.run(scenario())


def test_compact_grounded_bridge_transports_future_resolvable_sequence() -> None:
    async def scenario():
        context = _context(mandatory_semantic_control=True)
        by_label = {"Username": "type", "Login": "click"}
        port = _CompactPort(
            [
                {
                    "op": "establish_task_program",
                    "steps": [
                        {
                            "kind": "entity",
                            "predicate": {
                                "any_of": [
                                    {
                                        "all_of": [
                                            {
                                                "kind": "fact_equals",
                                                "field_name": "identity.label",
                                                "expected": "Username",
                                                "negated": False,
                                            }
                                        ]
                                    }
                                ]
                            },
                            "semantic_action": by_label["Username"],
                            "parameters": {"value": "donovan"},
                            "postcondition_predicate": None,
                        },
                        {
                            "kind": "entity",
                            "predicate": {
                                "any_of": [
                                    {
                                        "all_of": [
                                            {
                                                "kind": "fact_equals",
                                                "field_name": "identity.label",
                                                "expected": "Login",
                                                "negated": False,
                                            }
                                        ]
                                    }
                                ]
                            },
                            "semantic_action": by_label["Login"],
                        },
                    ],
                }
            ]
        )
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure)
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, EstablishObjectiveSequence)
        assert isinstance(parsed.sequence, TaskProgram)
        assert len(parsed.sequence.steps) == 2
        assert parsed.sequence.steps[0].action_template.semantic_action == "type_text"
        assert parsed.sequence.steps[1].action_template.semantic_action == "activate"
        assert parsed.sequence.steps[0].action_template.parameters == {"value": "donovan"}

    asyncio.run(scenario())


def test_mandatory_ingress_rejects_old_single_objective_alias() -> None:
    context = _context(mandatory_semantic_control=True)
    catalog = compile_grounded_tool_catalog(context)

    with pytest.raises(GroundedToolResolutionError) as raised:
        resolve_grounded_tool_call(
            catalog,
            ToolCall("fill", {"text": "UV"}),
            expected_context_id=context.context_id,
        )

    assert raised.value.code is GroundedToolResolutionCode.UNKNOWN_OPERATION


def test_compact_command_accepts_typed_fact_value_and_quantifier() -> None:
    payload = GroundedToolCommandPayload.model_validate(
        {
            "op": "establish_click_where_grid_coordinate_equals",
            "value": {"x": 1, "y": -2},
            "quantifier": "exactly_one",
        }
    )

    assert payload.value == {"x": 1, "y": -2}
    assert payload.quantifier == "exactly_one"


def test_runtime_authorized_member_continuation_skips_model_inference() -> None:
    async def scenario():
        context = _context(mandatory_semantic_control=True)
        login_target = next(
            target_id
            for target_id, ref in context.grounding.target_refs.items()
            if next(item for item in context.grounding.entities if item.ref == ref).label == "Login"
        )
        login_action = next(item.action_id for item in context.actions.options if item.target_id == login_target)
        execution_context = replace(
            context,
            set_control=AgentSetControlView(
                mode="member_actions_only",
                disposition="ready_for_next_member",
                reason_code="member_action_required",
                allowed_action_ids=(login_action,),
                candidate_count=1,
                matched_count=1,
                predicate={"kind": "fact_equals", "field_name": "identity.entity_id"},
                predicate_digest="a" * 64,
                candidate_target_ids=(login_target,),
                semantic_mode="member_execution",
            ),
        )
        port = _CompactPort([])
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(execution_context))

        assert not isinstance(response, ModelFailure)
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, SelectAction)
        assert parsed.action_id == login_action
        assert port.calls == 0
        assert response.metadata.total_tokens == 0
        assert adapter.last_attempt_origin is ProviderAttemptOrigin.LOCAL_RUNTIME

    asyncio.run(scenario())


def test_selected_grounded_operation_gets_one_typed_argument_repair_without_changing_operation() -> None:
    async def scenario():
        context = _context()
        password_ref = next(item.ref for item in context.grounding.entities if item.label == "Password")
        port = _CompactPort(
            [
                {"op": "fill", "target": password_ref},
                {"op": "fill", "target": password_ref, "text": "UV"},
            ]
        )
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure)
        assert port.calls == 2
        assert adapter.last_schema_repair_count == 1
        assert adapter.last_argument_repair_count == 1
        repair = port.messages[0].content
        assert isinstance(repair, str)
        assert '"selected_operation":"fill"' in repair
        assert '"required":["target","text"]' in repair

    asyncio.run(scenario())


def test_public_workspace_is_task_id_invariant_and_does_not_expand_action_authority() -> None:
    context = _context()
    renamed = replace(context, task=replace(context.task, task_id="task:renamed"))

    original = compile_grounded_tool_catalog(context)
    changed = compile_grounded_tool_catalog(renamed)

    assert original.view == changed.view
    offered_ids = {item.action_id for item in context.actions.options}
    resolved_ids = set()
    for spec in original.specs:
        if spec.name == "next_actions":
            continue
        target_schema = spec.input_schema["properties"].get("target")
        arguments = {"target": target_schema["enum"][0]} if target_schema is not None else {}
        if spec.name.startswith("fill"):
            arguments["text"] = "value"
        elif spec.name.startswith("select"):
            arguments["value"] = spec.input_schema["properties"]["value"].get("enum", ("value",))[0]
        package = resolve_grounded_tool_call(
            original,
            ToolCall(spec.name, arguments),
            expected_context_id=context.context_id,
        )
        assert isinstance(package.decision, SelectAction)
        resolved_ids.add(package.decision.action_id)
    assert resolved_ids.issubset(offered_ids)


def test_compact_singleton_operation_does_not_require_or_trust_redundant_target() -> None:
    async def scenario():
        context = _context()
        port = _CompactPort([{"op": "click", "target": "E99"}])
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure), adapter.last_internal_error_code
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, SelectAction)
        assert parsed.parameters == {}
        assert adapter.last_resolution_code is GroundedToolResolutionCode.ACCEPTED
        assert adapter.last_argument_repair_count == 0

    asyncio.run(scenario())


def test_compact_singleton_operation_does_not_require_redundant_operation_name() -> None:
    async def scenario():
        context = _context()
        login_target = next(
            target_id
            for target_id, ref in context.grounding.target_refs.items()
            if next(item for item in context.grounding.entities if item.ref == ref).label == "Login"
        )
        context = replace(
            context,
            actions=replace(
                context.actions,
                options=tuple(item for item in context.actions.options if item.target_id == login_target),
                total_count=1,
                page_size=1,
            ),
        )
        port = _CompactPort([{"op": "submit", "target": "E99"}])
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure), adapter.last_internal_error_code
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, SelectAction)
        assert adapter.last_resolution_code is GroundedToolResolutionCode.ACCEPTED

    asyncio.run(scenario())


def test_unclassified_set_language_does_not_fake_structural_completion() -> None:
    context = _context()
    login = next(item for item in context.grounding.entities if item.label == "Login")
    entities = tuple(
        replace(item, state={"selected": True}) if item.ref == login.ref else item
        for item in context.grounding.entities
    )
    context = replace(
        context,
        task=replace(context.task, instruction="Select all the matching shades and press Login."),
        grounding=replace(context.grounding, entities=entities),
    )

    catalog = compile_grounded_tool_catalog(context)

    assert "click" in {item.name for item in catalog.specs}


def test_runtime_set_control_admits_one_member_then_releases_successors() -> None:
    context = _context()
    entities = tuple(
        replace(item, label="", state={"color_family": "red"})
        if item.label == "Username"
        else replace(item, label="", state={"color_family": "blue"})
        if item.label == "Password"
        else item
        for item in context.grounding.entities
    )
    context = replace(
        context,
        grounding=replace(context.grounding, entities=entities),
        actions=replace(
            context.actions,
            options=tuple(
                replace(
                    item,
                    semantic_action="activate",
                    parameter_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
                for item in context.actions.options
            ),
        ),
    )
    blue_target = next(
        target_id
        for target_id, ref in context.grounding.target_refs.items()
        if next(item for item in entities if item.ref == ref).state.get("color_family") == "blue"
    )
    blue_action = next(item.action_id for item in context.actions.options if item.target_id == blue_target)
    digest = "a" * 64
    context = replace(
        context,
        set_control=AgentSetControlView(
            mode="member_actions_only",
            disposition="ready_for_next_member",
            reason_code="member_action_required",
            allowed_action_ids=(blue_action,),
            candidate_count=2,
            matched_count=1,
            predicate={"kind": "fact_equals", "field_name": "color_family", "expected": "blue"},
            predicate_digest=digest,
            candidate_target_ids=tuple(
                target_id
                for target_id in context.grounding.target_refs
                if target_id
                != next(
                    item.target_id
                    for item in context.actions.options
                    if next(
                        entity for entity in entities if entity.ref == context.grounding.target_refs[item.target_id]
                    ).label
                    == "Login"
                )
            ),
        ),
    )

    catalog = compile_grounded_tool_catalog(context)
    click = next(item for item in catalog.specs if item.name == "execute_objective")

    assert click.input_schema["properties"] == {}
    package = resolve_grounded_tool_call(
        catalog,
        ToolCall("execute_objective", {}),
        expected_context_id=context.context_id,
    )
    assert (
        next(item for item in context.actions.options if item.action_id == package.decision.action_id).target_id
        == blue_target
    )

    settled = replace(
        context,
        set_control=replace(
            context.set_control,
            mode="successor_actions",
            disposition="certified",
            reason_code="closed_scope_set_complete",
            allowed_action_ids=tuple(
                item.action_id
                for item in context.actions.options
                if item.target_id not in context.set_control.candidate_target_ids
            ),
            certified=True,
        ),
    )
    successor_catalog = compile_grounded_tool_catalog(settled)
    successor_click = next(item for item in successor_catalog.specs if item.name == "click")
    assert successor_click.input_schema["properties"] == {}
    login_ref = next(item.ref for item in entities if item.label == "Login")
    package = resolve_grounded_tool_call(
        successor_catalog,
        ToolCall("click", {}),
        expected_context_id=settled.context_id,
    )
    selected = next(item for item in settled.actions.options if item.action_id == package.decision.action_id)
    assert settled.grounding.target_refs[selected.target_id] == login_ref


def test_mandatory_objective_transition_excludes_settled_member_actions() -> None:
    context = _context(mandatory_semantic_control=True)
    login_target = next(
        target_id
        for target_id, ref in context.grounding.target_refs.items()
        if next(item for item in context.grounding.entities if item.ref == ref).label == "Login"
    )
    login_action = next(item.action_id for item in context.actions.options if item.target_id == login_target)
    transitioned = replace(
        context,
        set_control=AgentSetControlView(
            mode="control_only",
            disposition="certified",
            reason_code="closed_scope_set_complete",
            certified=True,
            semantic_mode="objective_transition",
            objective_candidate_action_ids=(login_action,),
        ),
    )

    catalog = compile_grounded_tool_catalog(transitioned)
    assert tuple(item.name for item in catalog.specs) == ("establish_task_program",)


def test_objective_transition_does_not_repeat_same_observation_instead_of_ingress() -> None:
    context = _context(mandatory_semantic_control=True)
    transitioned = replace(
        context,
        world=replace(
            context.world,
            observation_capabilities=(ObservationCapabilityView("visual", "weak"),),
        ),
        set_control=AgentSetControlView(
            mode="control_only",
            disposition="certified",
            reason_code="closed_scope_set_complete",
            certified=True,
            semantic_mode="objective_transition",
            objective_candidate_action_ids=tuple(item.action_id for item in context.actions.options),
        ),
    )

    catalog = compile_grounded_tool_catalog(transitioned)

    assert catalog.specs
    assert tuple(item.name for item in catalog.specs) == ("establish_task_program",)


def test_model_can_establish_generic_fact_set_without_instruction_scanning() -> None:
    context = _context()
    entities = tuple(
        replace(item, label="", role="clickable", state={"appearance.color_family": "red"})
        if item.label == "Username"
        else replace(item, label="", role="clickable", state={"appearance.color_family": "blue"})
        if item.label == "Password"
        else item
        for item in context.grounding.entities
    )
    actions = tuple(
        replace(
            item,
            semantic_action="activate",
            parameter_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
        for item in context.actions.options
        if next(entity for entity in entities if entity.ref == context.grounding.target_refs[item.target_id]).role
        == "clickable"
    )
    context = replace(
        context,
        task=replace(context.task, instruction="Arbitrary paraphrase with no recognized quantifier token."),
        grounding=replace(
            context.grounding,
            entities=tuple(item for item in entities if item.role == "clickable"),
            target_refs={
                target_id: ref
                for target_id, ref in context.grounding.target_refs.items()
                if any(item.ref == ref and item.role == "clickable" for item in entities)
            },
        ),
        actions=replace(
            context.actions,
            options=actions,
            total_count=len(actions),
            page_size=len(actions),
        ),
    )
    catalog = compile_grounded_tool_catalog(context)
    establish = next(item for item in catalog.specs if 'public fact "appearance.color_family"' in item.description)
    renamed = replace(
        context,
        task=replace(
            context.task,
            task_id="task:held-out-renamed",
            instruction="请选择当前范围内所有符合目标视觉属性的对象。",
        ),
    )
    renamed_establish = next(
        item
        for item in compile_grounded_tool_catalog(renamed).specs
        if 'public fact "appearance.color_family"' in item.description
    )
    assert renamed_establish.input_schema == establish.input_schema

    package = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            establish.name,
            {"value": "blue", "quantifier": "all_in_closed_scope"},
        ),
        expected_context_id=context.context_id,
    )

    assert isinstance(package.decision, EstablishSetObjective)
    assert package.decision.predicate.field_name == "appearance.color_family"
    assert package.decision.predicate.expected == "blue"
    assert len(package.decision.candidate_target_ids) == 2


def test_unclosed_set_scope_exposes_only_real_control_tools() -> None:
    context = _context()
    entities = tuple(
        replace(item, label="", state={"color_family": "blue"})
        if item.label == "Password"
        else replace(item, label="", state={"color_family": "red"})
        if item.label == "Username"
        else item
        for item in context.grounding.entities
    )
    context = replace(
        context,
        grounding=replace(context.grounding, entities=entities),
        world=replace(
            context.world,
            targets=BoundedSection(
                context.world.targets.items,
                context.world.targets.total_count + 1,
                True,
            ),
            observation_capabilities=(ObservationCapabilityView("screenshot", "semantic"),),
        ),
    )
    context = replace(
        context,
        set_control=AgentSetControlView(
            mode="control_only",
            disposition="need_scope_closure",
            reason_code="scope_not_closed",
            candidate_count=2,
            predicate={"kind": "fact_equals", "field_name": "color_family", "expected": "blue"},
            predicate_digest="b" * 64,
            candidate_target_ids=tuple(context.grounding.target_refs)[:2],
        ),
    )

    catalog = compile_grounded_tool_catalog(context)

    assert [item.name for item in catalog.specs] == ["observe_screenshot"]
    assert catalog.view.current_state["quantified_objective"]["disposition"] == "need_scope_closure"


def test_zero_true_members_pending_stability_exposes_no_effectful_action() -> None:
    context = _context()
    context = replace(
        context,
        world=replace(
            context.world,
            observation_capabilities=(ObservationCapabilityView("screenshot", "semantic"),),
        ),
        set_control=AgentSetControlView(
            mode="control_only",
            disposition="need_stability_check",
            reason_code="fresh_scope_stability_required",
            candidate_count=3,
            predicate={"kind": "visual_concept", "concept": "apple"},
            predicate_digest="c" * 64,
            candidate_target_ids=tuple(context.grounding.target_refs),
        ),
    )

    catalog = compile_grounded_tool_catalog(context)

    assert [item.name for item in catalog.specs] == ["observe_screenshot"]
    assert catalog.view.current_state["quantified_objective"]["disposition"] == "need_stability_check"


def test_grounded_bridge_serializes_observation_request_without_internal_failure() -> None:
    async def scenario() -> None:
        context = _context()
        context = replace(
            context,
            world=replace(
                context.world,
                observation_capabilities=(ObservationCapabilityView("visual", "weak"),),
            ),
            set_control=AgentSetControlView(
                mode="control_only",
                disposition="need_stability_check",
                reason_code="fresh_scope_stability_required",
                candidate_count=3,
                predicate={"kind": "visual_concept", "concept": "held-out fruit"},
                predicate_digest="c" * 64,
                candidate_target_ids=tuple(context.grounding.target_refs),
            ),
        )
        port = _CompactPort([{"op": "observe_visual"}])
        adapter = GroundedToolDecisionAdapter(
            port,
            ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure), adapter.last_internal_error_code
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, RequestObservation)
        assert adapter.last_internal_error_code == ""

    asyncio.run(scenario())


def test_open_vocabulary_batch_evidence_admits_true_refs_without_point_execution() -> None:
    context = _context()
    digest = "d" * 64
    target_ids = tuple(context.grounding.target_refs)
    truth_by_target = {target_id: "true" if index == 0 else "false" for index, target_id in enumerate(target_ids)}
    context = replace(
        context,
        set_control=AgentSetControlView(
            mode="control_only",
            disposition="need_unknown_resolution",
            reason_code="predicate_unknown",
            candidate_count=len(target_ids),
            predicate={"kind": "visual_concept", "concept": "apple"},
            predicate_digest=digest,
            candidate_target_ids=target_ids,
            unknown_target_ids=target_ids,
        ),
    )

    catalog = compile_grounded_tool_catalog(context)
    classify = next(item for item in catalog.specs if item.name == "classify_set_candidates")
    by_ref = {ref: truth_by_target[target_id] for target_id, ref in context.grounding.target_refs.items()}
    package = resolve_grounded_tool_call(
        catalog,
        ToolCall(classify.name, by_ref),
        expected_context_id=context.context_id,
    )
    assert isinstance(package.decision, SubmitSetPredicateAssessments)
    assert package.decision.predicate_digest == digest
    assert {item.target_id: item.truth.value for item in package.decision.assessments} == truth_by_target


def test_confirmed_current_fill_is_removed_from_next_model_tool_menu() -> None:
    context = _context()
    username = next(item for item in context.grounding.entities if item.label == "Username")
    entities = tuple(
        replace(item, state={"value": "10"}) if item.ref == username.ref else item
        for item in context.grounding.entities
    )
    target_id = next(target_id for target_id, ref in context.grounding.target_refs.items() if ref == username.ref)
    turn = AgentTurnView(
        "selectaction",
        "fill",
        target_id,
        public_parameters={"value": "10"},
        dispatch_status="sent",
        action_evaluation_status="effect_confirmed",
        task_evaluation_status="incomplete",
    )
    context = replace(
        context,
        grounding=replace(context.grounding, entities=entities),
        history=replace(context.history, items=(turn,), total_count=1),
    )

    catalog = compile_grounded_tool_catalog(context)
    fill = next(item for item in catalog.specs if item.name == "fill")

    assert "target" not in fill.input_schema["properties"]
    package = resolve_grounded_tool_call(
        catalog,
        ToolCall("fill", {"text": "UV"}),
        expected_context_id=context.context_id,
    )
    password_target = next(
        target_id
        for target_id, ref in context.grounding.target_refs.items()
        if ref == next(item.ref for item in entities if item.label == "Password")
    )
    password_action = next(item.action_id for item in context.actions.options if item.target_id == password_target)
    assert isinstance(package.decision, SelectAction)
    assert package.decision.action_id == password_action


def test_direct_model_select_action_records_selected_public_e_ref() -> None:
    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario():
        context = _context()
        instrumentation = BenchmarkInstrumentation()
        outcome = await CountingPolicy(Policy(), instrumentation).decide(context)

        assert isinstance(outcome, SelectAction)
        expected = context.grounding.target_refs[context.actions.options[0].target_id]
        assert instrumentation.policy_trace[0]["selected_grounding"]["ref"] == expected
        assert "target_id" not in instrumentation.policy_trace[0]["selected_grounding"]

    asyncio.run(scenario())


def test_grounded_normal_path_is_one_model_call_one_runtime_transition_and_no_proposer() -> None:
    def with_screenshot(world):
        source = world.sources[0]
        media = ObservationMedia(
            "screenshot",
            "screenshot",
            "image/png",
            _unmarked_png(),
            (ObservationGroundingRegion("shared-toggle", (10, 10, 80, 30)),),
        )
        return replace(world, sources=(replace(source, media=(media,)),))

    before = with_screenshot(_world("before", False))
    after = with_screenshot(_world("after", True))
    port = _CompactPort([{"op": "click", "target": "E1"}])
    adapter = GroundedToolDecisionAdapter(
        port,
        ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
    )
    loop = AgentLoop(
        __import__(
            "affordance_runtime.model_policy",
            fromlist=["ModelBackedAgentPolicy"],
        ).ModelBackedAgentPolicy(adapter, call_timeout_s=3),
        SharedActionEvaluator(),
        SharedTaskEvaluator(),
    )
    assert loop.context_builder.requirement_hypothesis_proposer is None

    result = asyncio.run(
        AgentEpisodeRunner(loop).run(
            StaticEnvironment([before, after], results=[_sent()]),
            _task(),
        )
    )

    assert result.status is AgentLoopStatus.DONE, (
        result.message,
        result.failure_code,
        result.execution_count,
        port.calls,
        adapter.last_internal_error_code,
        adapter.last_resolution_code,
        tuple(
            (
                item.reason_code,
                item.decision_result,
                item.action_evaluation.status if item.action_evaluation is not None else None,
                item.after_observation_id,
            )
            for item in result.control_transitions
        ),
        result.control_transitions,
    )
    assert port.calls == 1
    assert result.execution_count == 1
    assert len(result.control_transitions) == 1


def test_task_program_executes_multiple_freshly_resolved_steps_with_one_network_call() -> None:
    def world(observation_id: str, value: str):
        target = SemanticTarget("program-input", "textbox", "Program input", {"value": value})
        fact = StateFact(f"fact:{observation_id}:value", target.target_id, "value", value, observation_id)
        binding = ActionBinding(
            f"binding:{observation_id}",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            f"fingerprint:{observation_id}",
            target.target_id,
            target.target_id,
            "dom",
            "dom",
            "fill",
            "type_text",
            "local_reversible",
            ("value_entered",),
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            {"selector": "#program-input"},
            risk=ActionRisk.LOW,
        )
        media = ObservationMedia(
            "screenshot",
            "screenshot",
            "image/png",
            _unmarked_png(),
            (ObservationGroundingRegion(target.target_id, (10, 10, 120, 30)),),
        )
        source = SurfaceObservation(
            observation_id,
            "dom",
            f"revision:{observation_id}",
            ObservationSourceProfile.dom(),
            (target,),
            (fact,),
            (binding,),
            media=(media,),
        )
        return WorldObservation(
            observation_id,
            (target,),
            (fact,),
            (binding,),
            {"dom": CoverageState.COMPLETE},
            sources=(source,),
        )

    class ConfirmEveryEffect:
        async def evaluate(self, task, before, request, result, after):
            del task, before, result
            return ActionEvaluation(
                request.request_id,
                request.observation_id,
                after.observation_id,
                ActionEvaluationStatus.EFFECT_CONFIRMED,
                "fixture effect confirmed",
                (after.facts[0].fact_id,),
            )

    class CompleteAfterSecondValue:
        async def evaluate(self, task, observation):
            complete = observation.facts[0].value == "second"
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE,
                "second value entered" if complete else "value entry remains incomplete",
                completion_evidence_refs=((observation.facts[0].fact_id,) if complete else ()),
            )

    def predicate(label):
        return {
            "any_of": [
                {
                    "all_of": [
                        {
                            "kind": "fact_equals",
                            "field_name": "identity.label",
                            "expected": label,
                        }
                    ]
                }
            ]
        }

    before = world("program-before", "")
    middle = world("program-middle", "first")
    after = world("program-after", "second")
    task = TaskGoal(
        "task-program-value-entry",
        "Enter first, then replace it with second.",
        allowed_effects=("value_entered",),
        risk_profile=RiskProfile.LOW,
    )
    port = _CompactPort(
        [
            {
                "op": "establish_task_program",
                "steps": [
                    {
                        "kind": "entity",
                        "predicate": predicate("Program input"),
                        "semantic_action": "type",
                        "parameters": {"value": "first"},
                    },
                    {
                        "kind": "entity",
                        "predicate": predicate("Program input"),
                        "semantic_action": "type",
                        "parameters": {"value": "second"},
                    },
                ],
            }
        ]
    )
    adapter = GroundedToolDecisionAdapter(
        port,
        ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
    )
    policy = __import__(
        "affordance_runtime.model_policy",
        fromlist=["ModelBackedAgentPolicy"],
    ).ModelBackedAgentPolicy(adapter, call_timeout_s=3)
    loop = AgentLoop(policy, ConfirmEveryEffect(), CompleteAfterSecondValue(), semantic_control_required=True)

    result = asyncio.run(
        AgentEpisodeRunner(loop).run(
            StaticEnvironment([before, middle, after], results=[_sent(), _sent()]),
            task,
        )
    )

    assert result.status is AgentLoopStatus.DONE, (
        result.message,
        result.failure_code,
        result.execution_count,
        port.calls,
        adapter.last_internal_error_code,
        adapter.last_resolution_code,
        tuple(
            (
                item.reason_code,
                item.decision_result,
                item.action_evaluation.status if item.action_evaluation is not None else None,
                item.after_observation_id,
            )
            for item in result.control_transitions
        ),
        result.control_transitions,
    )
    assert port.calls == 1
    assert result.execution_count == 2
    assert result.control_transition_kind_counts == (
        ("EstablishObjectiveSequence", 1),
        ("SelectAction", 2),
    )


def test_agent_selected_set_member_is_not_forced_through_singleton_runtime_worker() -> None:
    context = SimpleNamespace(
        set_control=SimpleNamespace(
            semantic_mode="member_execution",
            disposition="agent_select_next",
        )
    )
    catalog = SimpleNamespace(specs=(ToolSpec("click", "choose a current admitted member", {}),))

    assert _runtime_sequential_member_call(context, catalog) is None


def _unmarked_png():
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.fromarray(np.full((160, 320, 3), 255, dtype=np.uint8)).save(output, format="PNG", optimize=True)
    return output.getvalue()
