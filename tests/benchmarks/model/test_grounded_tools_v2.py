from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace

import numpy as np
import pytest

from affordance_runtime.actions import (
    ActionSpaceBuilder,
    verification_contract_for_action,
)
from affordance_runtime.actions.schema_validation import validate_value_issue
from affordance_runtime.agent import (
    RequestObservation,
    SelectAction,
)
from affordance_runtime.agent.context import ContextBuilder, ModelFailure
from affordance_runtime.agent.context.acquisition_projection import ObservationCapabilityView
from affordance_runtime.agent.context.action_candidate_projection import close_action_candidates
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.benchmarks.target_loop.instrumentation import _policy_trace_event
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_compiler import (
    CompiledGroundedTool,
    CompiledSelectorField,
    PrivateResolutionEntry,
    SelectorMode,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOL_CALL_ENVELOPE,
    GroundedActionResolution,
    GroundedToolCatalog,
    GroundedToolPhase,
)
from affordance_runtime.model.policy.grounded_tool_port_bridge import (
    _TOOL_INTENT_REPAIR_CODES,
    GroundedActionAdapter,
    GroundedToolCommandPayload,
    _command_payload_type,
)
from affordance_runtime.model.policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import _build_request as _action_request
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallIssueCode,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.providers.port import (
    ModelCallRecord,
    ModelConfig,
    ModelImageURLPart,
    ModelMessage,
    ModelTextPart,
    StructuredOutputError,
    StructuredOutputViolation,
)
from affordance_runtime.model.providers.tool_transport_contracts import ToolCall, ToolSpec
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.surfaces.browsergym.backend import _effective_visibility
from affordance_runtime.surfaces.browsergym.entity_identity import BrowserGymEntityIdentityMap
from affordance_runtime.surfaces.browsergym.semantics import PRIVATE_CONTROL_PROPERTIES_KEY
from affordance_runtime.task import (
    RiskProfile,
    TaskGoal,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import ax_node, raw_observation, reset_task_state
from tests.support.surfaces.browsergym.projection_support import project_browsergym_observation

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


@dataclass
class _ActionPort:
    provider: str = "zhipu"
    model: str = "glm-4.1v-thinking-flashx"
    endpoint_class: str = "fixture"
    supports_multimodal: bool = True
    last_call: ModelCallRecord | None = None
    messages: tuple = ()
    calls: int = 0

    async def generate_structured(self, messages, output_schema, config):
        self.calls += 1
        self.messages = tuple(messages)
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name=output_schema.__name__,
            schema_version="grounded_tools.v2",
            latency_ms=1,
            response_id=f"response:{self.calls}",
        )
        return output_schema.model_validate({"name": "activate", "arguments": {}})


def _context():
    raw = raw_observation(
        ax_node("username", "textbox", ""),
        ax_node("password", "textbox", ""),
        ax_node("login", "button", "Login"),
        goal='Enter username "donovan", password "UV", then press Login.',
    )
    raw["screenshot"] = np.full((160, 320, 3), 255, dtype=np.uint8)
    for bid, bbox, label in (
        ("username", [10, 10, 140, 30], "Username"),
        ("password", [10, 55, 140, 30], "Password"),
        ("login", [10, 100, 80, 30], "Login"),
    ):
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = bbox
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["label_hint"] = label
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:grounded",
        source_revision="revision:grounded",
        page_identity="page:grounded",
        episode_identity="episode:grounded",
        task_state=reset_task_state("observation:grounded", task_run_id="run:grounded"),
        entity_identity=_IDENTITY,
    )
    task = TaskGoal(
        "task:grounded",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    state = AgentLoopState(projection.world, remaining_turns=5)
    return ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(task.task_id, projection.world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
    )


def _bound_public_context(context) -> dict[str, object]:
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    messages = GroundedPolicyContextBinder().action_messages(
        context,
        catalog.specs,
        _action_request(context),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        include_tool_menu=True,
    )
    content = messages[1].content
    assert isinstance(content, str)
    return json.loads(content)


def _selector_context(*, operation: str, schema: dict[str, object]):
    context = _context()
    source = context.actions.options[0]
    verification_digest = verification_contract_for_action(
        operation,
        schema_digest(schema),
        source.semantic_effects,
        source.observation_barrier,
    ).digest
    options = tuple(
        replace(
            option,
            semantic_action=operation,
            operation=operation,
            parameter_schema=schema,
            target_label="Same",
            target_role="button",
            target_semantics={"role": "button", "label": "Same", "state": {"ordinal": index}},
            target_state={"ordinal": index},
            verification_contract_digest=verification_digest,
        )
        for index, option in enumerate(context.actions.options[:2], 1)
    )
    return replace(
        context,
        actions=replace(
            context.actions,
            options=options,
            total_count=2,
            page_size=2,
            truncated=False,
            has_more=False,
            next_cursor="",
        ),
    )


def test_grounding_projection_is_public_and_contains_no_runtime_identity() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    public = json.dumps(_bound_public_context(context))
    assert [item.ref for item in context.grounding.entities] == ["E1", "E2", "E3"]
    assert all(item.marked for item in context.grounding.entities)
    assert not hasattr(catalog, "view")
    assert "bbox" not in public
    assert "entity:" not in public and "action:" not in public and "binding:" not in public
    payload = _bound_public_context(context)
    assert "actions" not in payload
    assert not {"actions.entities", "actions.groups"}.intersection(public)
    nodes = [node for document in payload["world"]["documents"] for node in document["roots"]]
    assert {item["ref"] for item in nodes} == {"E1", "E2", "E3"}
    assert {item["label"] for item in nodes} == {"Username", "Password", "Login"}


def test_actor_world_indexes_complete_public_facet_collections_and_boolean_state() -> None:
    shades = (
        ("blue-a", "blue", True),
        ("blue-b", "blue", True),
        ("blue-c", "blue", False),
        ("red-a", "red", False),
        ("red-b", "red", False),
    )
    raw = raw_observation(
        *(ax_node(bid, "graphics-symbol", "") for bid, _color, _selected in shades),
        ax_node("submit", "button", "Submit"),
        goal="Select all the blue shades and press Submit.",
    )
    raw["screenshot"] = np.full((120, 240, 3), 255, dtype=np.uint8)
    for index, (bid, color, selected) in enumerate(shades):
        raw["extra_element_properties"][bid].update(
            {"clickable": True, "visibility": 1.0, "bbox": [10 + index * 25, 20, 18, 18]}
        )
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid].update(
            {
                "bbox": [10 + index * 25, 20, 18, 18],
                "color_family": color,
                "selected": selected,
            }
        )
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:collections",
        source_revision="revision:collections",
        page_identity="page:collections",
        episode_identity="episode:collections",
        task_state=reset_task_state("observation:collections", task_run_id="run:collections"),
        entity_identity=_IDENTITY,
    )
    task = TaskGoal(
        "task:collections",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    state = AgentLoopState(projection.world, remaining_turns=5)
    context = ContextBuilder().build(
        task,
        state,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(
            task.task_id,
            projection.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    public = _bound_public_context(context)
    section = public["world"]["facet_collections"]
    blue = next(
        item
        for item in section["items"]
        if item["scope_role"] == "clickable"
        and item["field"] == "appearance.color_family"
        and item["value"] == "blue"
    )
    selected = next(item for item in blue["boolean_partitions"] if item["field"] == "selected")

    assert blue["member_count"] == 3
    assert blue["completeness"] == "complete_for_snapshot"
    assert len(selected["true_member_refs"]) == 2
    assert len(selected["false_member_refs"]) == 1
    assert set(selected["true_member_refs"] + selected["false_member_refs"]) == set(blue["member_refs"])
    assert section["truncated"] is False


def test_structure_first_grounded_action_starts_from_public_structure_without_image() -> None:
    context = _context()
    port = _ActionPort(supports_multimodal=False)
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    assert outcome.metadata.perception_profile == "structure-first.v1"
    assert adapter.compatibility_key.split(":")[2] == "structure-first.v1"
    assert adapter.compatibility_key.endswith(f":{GROUNDED_TOOL_CALL_ENVELOPE}")
    assert adapter.last_image_input_count == 0
    assert port.calls == 1
    assert adapter.last_model_call_count == 1
    user_content = port.messages[1].content
    assert isinstance(user_content, str)
    public = json.loads(user_content)
    assert public["last_transition"] is None
    assert set(public) == {"task", "last_transition", "world", "progress", "history", "control_feedback", "tools"}
    assert public["task"]["instruction"] == context.task.instruction
    assert "actions" not in public
    assert public["progress"]["validated_task_status"] == "incomplete"
    trace = _policy_trace_event(1, context, outcome.decision, adapter)
    assert trace["model_image_input_count"] == 0
    assert trace["selected_grounding"]["marked"] is False


def test_structure_first_grounded_action_adds_image_only_after_visual_source_acquisition() -> None:
    context = _context()
    visual_source = replace(context.world.sources[0], modality="visual")
    context = replace(
        context,
        world=replace(context.world, sources=(*context.world.sources, visual_source)),
    )
    port = _ActionPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    user_content = port.messages[1].content
    assert isinstance(user_content, tuple)
    assert isinstance(user_content[0], ModelTextPart)
    assert isinstance(user_content[1], ModelImageURLPart)
    assert adapter.last_image_input_count == 1
    public = json.loads(user_content[0].text)
    assert "actions" not in public
    trace = _policy_trace_event(1, context, outcome.decision, adapter)
    assert trace["model_image_input_count"] == 1
    assert trace["selected_grounding"]["marked"] is True


def test_native_argument_repair_keeps_the_selected_observation_tool_and_exact_schema() -> None:
    @dataclass
    class NativeRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = True
        last_call: ModelCallRecord | None = None
        calls: int = 0
        repair_messages: tuple = ()

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del config, require_one
            self.calls += 1
            if self.calls == 1:
                return (ToolCall("request_evidence", {"target": "E1"}),)
            self.repair_messages = tuple(messages)
            assert len(tools) == 1
            assert tools[0].name == "request_evidence"
            assert to_json_compatible(tools[0].input_schema) == {
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "enum": ["entity_discovery"]},
                    "subject": {
                        "type": "string", "enum": ["current_world", "E1", "E2", "E3"],
                    },
                    "property": {
                        "type": "string",
                        "enum": ["color", "icon", "visual_state", "appearance"],
                    },
                },
                "required": ["purpose", "subject"],
                "additionalProperties": False,
            }
            return (ToolCall("request_evidence", {
                "purpose": "entity_discovery", "subject": "current_world",
            }),)

    context = _context()
    context = replace(
        context,
        world=replace(
            context.world,
            observation_capabilities=(
                ObservationCapabilityView("structural", "structural", ("criterion_verification",)),
                ObservationCapabilityView("visual", "weak", ("entity_discovery",)),
            ),
        ),
    )
    port = NativeRepairPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    assert isinstance(outcome.decision, RequestObservation)
    assert outcome.decision.purpose == "entity_discovery"
    assert port.calls == 2
    assert adapter.last_argument_repair_count == 1
    assert adapter.last_argument_violation_code == "invalid_action_parameters"
    assert adapter.last_argument_violation_paths == ("parameters.purpose",)
    assert adapter.last_selected_operation == "request_evidence"
    assert adapter.last_repaired_operation_match is True
    trace = _policy_trace_event(1, context, outcome.decision, adapter)
    assert trace["decision"] == {
        "kind": "RequestObservation",
        "context_id": context.context_id,
        "purpose": "entity_discovery",
        "subject_id": "current_world",
    }
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"selected_operation":"request_evidence"' in repair_system
    assert '"field_paths":["parameters.purpose"]' in repair_system


def test_native_transport_carries_unified_world_and_tools_once() -> None:
    @dataclass
    class NativePort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = True
        last_call: ModelCallRecord | None = None
        messages: tuple = ()
        tools: tuple[ToolSpec, ...] = ()

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del config, require_one
            self.messages = tuple(messages)
            self.tools = tuple(tools)
            return (
                ToolCall(
                    "activate",
                    {},
                ),
            )

    context = _context()
    port = NativePort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    user_content = port.messages[1].content
    assert isinstance(user_content, str)
    public = json.loads(user_content)
    assert set(public) == {"task", "last_transition", "world", "progress", "history", "control_feedback"}
    assert {item.name.split("_")[0] for item in port.tools} == {"type", "activate"}
    assert all("E1(" not in item.description for item in port.tools)
    assert all("shared public semantics" in item.description for item in port.tools)
    assert all("memory" not in item.input_schema["properties"] for item in port.tools)
    assert tuple(public)[:5] == ("task", "world", "progress", "last_transition", "history")


def test_unknown_tool_intent_gets_one_bounded_model_reemission() -> None:
    @dataclass
    class ToolIntentRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0
        repair_messages: tuple = ()

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del tools, config, require_one
            self.calls += 1
            if self.calls == 1:
                return (ToolCall("click", {}),)
            self.repair_messages = tuple(messages)
            return (ToolCall("activate", {}),)

    context = _context()
    port = ToolIntentRepairPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    assert port.calls == 2
    assert adapter.last_model_call_count == 2
    assert adapter.last_tool_intent_repair_count == 1
    assert adapter.last_argument_repair_count == 0
    assert adapter.last_routing_normalization == "bounded_model_reemission"
    assert adapter.last_routing_original_operation == "click"
    assert adapter.last_routing_normalized_operation == "activate"
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"issue_code":"unknown_tool"' in repair_system
    assert '"emit_one_complete_call":true' in repair_system


def test_all_typed_did_you_mean_intent_failures_share_the_bounded_reemission_path() -> None:
    assert _TOOL_INTENT_REPAIR_CODES == {
        ToolCallIssueCode.UNKNOWN_TOOL,
        ToolCallIssueCode.TOOL_ARGUMENT_OWNER_MISMATCH,
        ToolCallIssueCode.AMBIGUOUS_TOOL_INTENT,
        ToolCallIssueCode.NON_EQUIVALENT_TOOL_INTENT,
    }


def test_tool_intent_repair_is_never_retried_or_chained_to_argument_repair() -> None:
    @dataclass
    class FailedToolIntentRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del messages, tools, config, require_one
            self.calls += 1
            return (ToolCall("click", {}),)

    context = _context()
    port = FailedToolIntentRepairPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert isinstance(outcome, ModelFailure)
    assert port.calls == 2
    assert adapter.last_tool_intent_repair_count == 1
    assert adapter.last_argument_repair_count == 0


def test_grounded_catalog_is_only_tools_and_private_bindings() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "activate",
            {},
        ),
        expected_context_id=context.context_id,
        expected_catalog_id=catalog.catalog_id,
    )

    assert isinstance(outcome, GroundedActionResolution)
    assert isinstance(outcome.decision, SelectAction)
    assert outcome.decision.context_id == context.context_id
    assert set(catalog.__dataclass_fields__) == {
        "catalog_id",
        "context_id",
        "specs",
        "bindings",
        "serialized_bytes",
    }


def test_single_operation_compact_schema_constrains_the_operation_name() -> None:
    payload_type = _command_payload_type(
        (
            ToolSpec(
                "observe_visual",
                "Acquire visual evidence.",
                {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            ),
        )
    )

    operation_schema = payload_type.model_json_schema()["properties"]["name"]
    assert operation_schema["const"] == "observe_visual"

    accepted = payload_type.model_validate({"name": "observe_visual", "arguments": {}})
    assert accepted.command_arguments() == {}
    assert payload_type.model_validate({"name": "observe_visual"}).command_arguments() == {}
    assert payload_type.model_validate({"op": "observe_visual"}).name == "observe_visual"
    assert payload_type.model_validate({"op": "observe_visual", "arguments": {}}).name == "observe_visual"
    with pytest.raises(ValueError):
        payload_type.model_validate({"name": "observe_visual", "op": "different"})


def test_compact_action_schema_has_one_stable_envelope_without_catalog_union() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    payload_type = _command_payload_type(catalog.specs)

    schema = payload_type.model_json_schema()
    assert set(schema["properties"]) == {"name", "arguments"}
    assert schema["properties"]["arguments"] == {
        "additionalProperties": True,
        "title": "Arguments",
        "type": "object",
    }
    assert "$defs" not in schema
    assert "anyOf" not in json.dumps(schema)
    assert "$ref" not in json.dumps(schema)


def test_compact_action_payload_defers_exact_arguments_to_selected_tool_validator() -> None:
    semantic_key = "(1,-2)"
    spec = ToolSpec(
        "activate",
        "Activate a current candidate.",
        {
            "type": "object",
            "properties": {"semantic_grid_coordinate": {"type": "string", "enum": [semantic_key]}},
            "required": ["semantic_grid_coordinate"],
            "additionalProperties": False,
        },
    )
    payload_type = _command_payload_type((spec,))

    accepted = payload_type.model_validate(
        {"name": "activate", "arguments": {"semantic_grid_coordinate": semantic_key}}
    )
    legacy_flat = payload_type.model_validate({"op": "activate", "semantic_grid_coordinate": semantic_key})

    assert accepted.arguments["semantic_grid_coordinate"] == semantic_key
    assert legacy_flat.command_arguments() == {"semantic_grid_coordinate": semantic_key}
    invalid_for_tool = payload_type.model_validate(
        {"name": "activate", "arguments": {"semantic_grid_coordinate": "E38"}}
    )
    assert invalid_for_tool.command_arguments() == {"semantic_grid_coordinate": "E38"}
    assert validate_value_issue(
        invalid_for_tool.command_arguments(), spec.input_schema, path="parameters"
    ) is not None


def test_unique_same_operation_selector_owner_normalizes_only_compiler_routing() -> None:
    submit_spec = ToolSpec(
        "activate_submit",
        "Activate Submit.",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )
    blue_schema = {
        "type": "object",
        "properties": {"grounding_ref": {"type": "string", "enum": ["E5", "E10"]}},
        "required": ["grounding_ref"],
        "additionalProperties": False,
    }
    blue_spec = ToolSpec("activate_blue", "Activate a blue target.", blue_schema)
    submit_binding = CompiledGroundedTool(
        "activate",
        submit_spec,
        SelectorMode.CONSTANT_TARGET,
        (),
        (PrivateResolutionEntry({}, "action:submit", None, "E17", {"grounding_ref": "E17"}),),
        "sha256:equivalent",
    )
    selector = CompiledSelectorField(
        "grounding_ref",
        ("target.grounding_ref",),
        blue_schema["properties"]["grounding_ref"],
    )
    blue_binding = CompiledGroundedTool(
        "activate",
        blue_spec,
        SelectorMode.GROUNDING_FALLBACK,
        (selector,),
        (
            PrivateResolutionEntry({"grounding_ref": "E5"}, "action:blue-1", None, "E5", {"grounding_ref": "E5"}),
            PrivateResolutionEntry({"grounding_ref": "E10"}, "action:blue-2", None, "E10", {"grounding_ref": "E10"}),
        ),
        "sha256:equivalent",
    )
    catalog = GroundedToolCatalog(
        "grounded-catalog:test", "context:test",
        (submit_spec, blue_spec), (submit_binding, blue_binding), 1,
    )

    normalized = ProviderCallNormalizer().normalize(
        ToolCall("activate_submit", {"grounding_ref": "E10"}),
        catalog,
    )

    assert normalized.status is ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT
    assert normalized.exact_call == ToolCall("activate_blue", {"grounding_ref": "E10"})


def test_routing_normalization_telemetry_retains_original_and_normalized_operations() -> None:
    request = _action_request(_context())
    submit_spec = ToolSpec(
        "activate_submit",
        "Activate Submit.",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )
    blue_schema = {
        "type": "object",
        "properties": {"grounding_ref": {"type": "string", "enum": ["E10"]}},
        "required": ["grounding_ref"],
        "additionalProperties": False,
    }
    blue_spec = ToolSpec("activate_blue", "Activate blue.", blue_schema)
    submit_binding = CompiledGroundedTool(
        "activate",
        submit_spec,
        SelectorMode.CONSTANT_TARGET,
        (),
        (PrivateResolutionEntry({}, "action:submit", None, "E17", {"grounding_ref": "E17"}),),
        "sha256:equivalent",
    )
    blue_binding = CompiledGroundedTool(
        "activate",
        blue_spec,
        SelectorMode.GROUNDING_FALLBACK,
        (
            CompiledSelectorField(
                "grounding_ref",
                ("target.grounding_ref",),
                blue_schema["properties"]["grounding_ref"],
            ),
        ),
        (
            PrivateResolutionEntry(
                {"grounding_ref": "E10"},
                "action:blue",
                None,
                "E10",
                {"grounding_ref": "E10"},
            ),
        ),
        "sha256:equivalent",
    )
    catalog = GroundedToolCatalog(
        "grounded-catalog:test",
        request.context_id,
        (submit_spec, blue_spec),
        (submit_binding, blue_binding),
        1,
    )

    @dataclass
    class TelemetryPort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del messages, tools, config, require_one
            return (ToolCall("activate_submit", {"grounding_ref": "E10"}),)

    adapter = GroundedActionAdapter(
        TelemetryPort(),
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
    )
    resolved, _metadata = asyncio.run(
        adapter._resolve_catalog(
            request,
            catalog,
            (ModelMessage(role="system", content="Select one current tool."),),
            lambda _catalog, call, **_kwargs: call,
            GroundedToolCommandPayload,
        )
    )

    assert resolved == ToolCall("activate_blue", {"grounding_ref": "E10"})
    assert adapter.last_routing_original_operation == "activate_submit"
    assert adapter.last_routing_normalized_operation == "activate_blue"


def test_unique_constant_target_accepts_a_redundant_current_grounding_ref() -> None:
    selected_spec = ToolSpec(
        "activate_blue",
        "Activate a blue target.",
        {
            "type": "object",
            "properties": {"grounding_ref": {"type": "string", "enum": ["E5"]}},
            "required": ["grounding_ref"],
            "additionalProperties": False,
        },
    )
    submit_spec = ToolSpec(
        "activate_submit",
        "Activate Submit.",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )
    selected_binding = CompiledGroundedTool(
        "activate",
        selected_spec,
        SelectorMode.GROUNDING_FALLBACK,
        (
            CompiledSelectorField(
                "grounding_ref",
                ("grounding_ref",),
                {"type": "string", "enum": ["E5"]},
            ),
        ),
        (PrivateResolutionEntry({"grounding_ref": "E5"}, "action:blue", None, "E5", {"grounding_ref": "E5"}),),
        "sha256:equivalent",
    )
    submit_binding = CompiledGroundedTool(
        "activate",
        submit_spec,
        SelectorMode.CONSTANT_TARGET,
        (),
        (PrivateResolutionEntry({}, "action:submit", None, "E17", {"grounding_ref": "E17"}),),
        "sha256:equivalent",
    )
    catalog = GroundedToolCatalog(
        "grounded-catalog:test", "context:test",
        (selected_spec, submit_spec), (selected_binding, submit_binding), 1,
    )

    accepted = ProviderCallNormalizer().normalize(
        ToolCall("activate_blue", {"grounding_ref": "E17"}),
        catalog,
    )
    assert accepted.status is ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT
    assert accepted.exact_call == ToolCall("activate_submit", {})
    rejected = ProviderCallNormalizer().normalize(
        ToolCall("activate_blue", {"grounding_ref": "E99"}),
        catalog,
    )
    assert rejected.issue_code is ToolCallIssueCode.INVALID_ARGUMENT


def test_routing_normalization_fails_closed_when_selector_owner_is_ambiguous() -> None:
    schema = {
        "type": "object",
        "properties": {"grounding_ref": {"type": "string", "enum": ["E5"]}},
        "required": ["grounding_ref"],
        "additionalProperties": False,
    }
    selected_spec = ToolSpec(
        "activate_submit",
        "Activate Submit.",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )
    selector = CompiledSelectorField(
        "grounding_ref",
        ("target.grounding_ref",),
        schema["properties"]["grounding_ref"],
    )
    alternatives = tuple(
        CompiledGroundedTool(
            "activate",
            ToolSpec(name, f"Activate {name}.", schema),
            SelectorMode.GROUNDING_FALLBACK,
            (selector,),
            (PrivateResolutionEntry({"grounding_ref": "E5"}, f"action:{name}", None, "E5", {"grounding_ref": "E5"}),),
            "sha256:equivalent",
        )
        for name in ("activate_first", "activate_second")
    )
    selected_binding = CompiledGroundedTool(
        "activate",
        selected_spec,
        SelectorMode.CONSTANT_TARGET,
        (),
        (PrivateResolutionEntry({}, "action:submit", None, "E17", {"grounding_ref": "E17"}),),
        "sha256:equivalent",
    )
    catalog = GroundedToolCatalog(
        "grounded-catalog:test", "context:test",
        (selected_spec, *(item.public_spec for item in alternatives)),
        (selected_binding, *alternatives), 1,
    )
    original = ToolCall("activate_submit", {"grounding_ref": "E5"})

    result = ProviderCallNormalizer().normalize(original, catalog)
    assert result.status is ToolCallReconciliationStatus.REPAIR_REQUIRED
    assert result.issue_code is ToolCallIssueCode.AMBIGUOUS_TOOL_INTENT
    assert tuple(item.tool_name for item in result.did_you_mean) == (
        "activate_first",
        "activate_second",
    )


def test_shared_target_semantics_are_hoisted_and_actor_selects_only_scope_difference() -> None:
    context = _context()
    source_options = context.actions.options[:2]
    empty_schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    verification_digest = verification_contract_for_action(
        "activate",
        schema_digest(empty_schema),
        source_options[0].semantic_effects,
        source_options[0].observation_barrier,
    ).digest
    raw_options = tuple(
        replace(
            option,
            semantic_action="activate",
            parameter_schema=empty_schema,
            operation="",
            target_ref="",
            target_semantics={},
            target_role="",
            target_state={},
            target_marked=False,
                destination_mode="",
                grounding_context_id="",
                verification_contract_digest=verification_digest,
        )
        for option in source_options
    )
    target_ids = tuple(option.target_id for option in raw_options)
    grounding = AgentGroundingIndexView(
        (
            AgentGroundingEntityView("E1", "button", "加入购物车", relation_hints=("parent:E3",)),
            AgentGroundingEntityView("E2", "button", "加入购物车", relation_hints=("parent:E4",)),
            AgentGroundingEntityView("E3", "product", "MacBook Air"),
            AgentGroundingEntityView("E4", "product", "MacBook Pro"),
        ),
        {
            target_ids[0]: "E1",
            target_ids[1]: "E2",
            "product:air": "E3",
            "product:pro": "E4",
        },
    )
    raw_page = replace(
        context.actions,
        options=raw_options,
        total_count=2,
        page_size=2,
        truncated=False,
        has_more=False,
        next_cursor="",
    )
    actions = close_action_candidates(raw_page, grounding, context_id=context.context_id)
    context = replace(context, actions=actions)

    public = _bound_public_context(context)
    assert "actions" not in public
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    tool = next(item for item in catalog.specs if item.name == "activate")
    assert to_json_compatible(tool.input_schema["properties"]["within_label"]["enum"]) == [
        "MacBook Air",
        "MacBook Pro",
    ]
    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall("activate", {"within_label": "MacBook Pro"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(outcome, GroundedActionResolution)
    assert isinstance(outcome.decision, SelectAction)
    assert outcome.decision.action_id == actions.options[1].action_id


def test_invalid_native_semantic_choice_is_not_repaired_as_argument_format() -> None:
    @dataclass
    class InvalidTargetPort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del messages, tools, config, require_one
            self.calls += 1
            return (ToolCall("activate", {"ordinal": 99}),)

    context = _selector_context(
        operation="activate",
        schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )
    port = InvalidTargetPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert isinstance(outcome, ModelFailure)
    assert port.calls == 1
    assert adapter.last_argument_repair_count == 0
    assert adapter.last_argument_violation_paths == ("parameters.ordinal",)


def test_native_business_argument_repair_cannot_change_a_valid_semantic_choice() -> None:
    @dataclass
    class DriftingRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.6v"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0
        repair_tools: tuple[ToolSpec, ...] = ()

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del messages, config, require_one
            self.calls += 1
            if self.calls == 1:
                return (ToolCall("type_text", {"ordinal": 2}),)
            self.repair_tools = tuple(tools)
            return (ToolCall("type_text", {"ordinal": 1, "text": "secret"}),)

    context = _selector_context(
        operation="type_text",
        schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    port = DriftingRepairPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert isinstance(outcome, ModelFailure)
    assert port.calls == 2
    assert adapter.last_argument_repair_count == 1
    assert adapter.last_argument_violation_paths == ("parameters.text",)
    selector_schema = port.repair_tools[0].input_schema["properties"]["ordinal"]
    assert selector_schema["enum"] == (2,)


def test_grounding_projection_carries_bounded_interaction_history_without_duplication() -> None:
    context = _context()
    target_ids = tuple(context.grounding.target_refs)
    refs = tuple(context.grounding.target_refs[target_id] for target_id in target_ids)
    context = replace(
        context,
        history=BoundedSection(
            (
                AgentTurnView(
                    "selectaction",
                    "type_text",
                    target_ids[0],
                    public_parameters={"text": "donovan"},
                    dispatch_status="sent",
                    action_evaluation_status="effect_confirmed",
                    task_evaluation_status="incomplete",
                    reason="action_effect_confirmed",
                ),
                AgentTurnView(
                    "selectaction",
                    "type_text",
                    target_ids[1],
                    public_parameters={"text": "UV"},
                    dispatch_status="sent",
                    action_evaluation_status="effect_confirmed",
                    task_evaluation_status="incomplete",
                    reason="action_effect_confirmed",
                ),
                AgentTurnView(
                    "selectaction",
                    "activate",
                    target_ids[2],
                    dispatch_status="sent",
                    action_evaluation_status="unknown",
                    task_evaluation_status="incomplete",
                    reason="action_unknown_low_local",
                ),
            ),
            3,
            False,
        ),
    )

    history = _bound_public_context(context)["history"]

    assert history["items"] == [
        {
            "decision": "selectaction",
            "semantic_action": "type_text",
            "target": refs[0],
            "parameters": {"text": "donovan"},
            "dispatch": "sent",
            "effect": "effect_confirmed",
            "task": "incomplete",
            "reason": "action_effect_confirmed",
        },
        {
            "decision": "selectaction",
            "semantic_action": "type_text",
            "target": refs[1],
            "parameters": {"text": "UV"},
            "dispatch": "sent",
            "effect": "effect_confirmed",
            "task": "incomplete",
            "reason": "action_effect_confirmed",
        },
        {
            "decision": "selectaction",
            "semantic_action": "activate",
            "target": refs[2],
            "parameters": {},
            "dispatch": "sent",
            "effect": "unknown",
            "task": "incomplete",
            "reason": "action_unknown_low_local",
        },
    ]
    assert history["total_count"] == 3
    assert history["truncated"] is False


def test_grounded_history_retains_observation_modality_and_tool_describes_current_source() -> None:
    context = _context()
    context = replace(
        context,
        world=replace(
            context.world,
            observation_capabilities=(
                ObservationCapabilityView("structural", "structural", ("criterion_verification",)),
                ObservationCapabilityView("visual", "weak", ("entity_discovery",)),
            ),
        ),
        history=BoundedSection(
            (
                AgentTurnView(
                    "requestobservation",
                    reason="observation_no_information_gain",
                    semantic_summary={
                        "subject_id": "current_world",
                        "purpose": "criterion_verification",
                        "evidence_property": "",
                        "reason": "refresh public state",
                    },
                ),
            ),
            1,
            False,
        ),
    )

    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    previous = _bound_public_context(context)["history"]["items"][0]
    assert previous["decision_details"]["purpose"] == "criterion_verification"
    descriptions = {item.name: item.description for item in catalog.specs}
    assert "request_evidence" in descriptions
    assert "Runtime admits the need" in descriptions["request_evidence"]


def test_single_target_action_is_a_private_constant() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    activate = next(item for item in catalog.specs if item.name == "activate")

    assert to_json_compatible(activate.input_schema) == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    outcome = resolve_grounded_tool_call(catalog, ToolCall("activate", {}), expected_context_id=context.context_id)
    assert isinstance(outcome, GroundedActionResolution)


def test_action_schema_retry_repairs_the_same_model_decision() -> None:
    class RepairPort(_ActionPort):
        repair_messages: tuple = ()

        async def generate_structured(self, messages, output_schema, config):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError(
                    "private action response",
                    violations=(StructuredOutputViolation("target", "string_type"),),
                )
            if self.calls == 1:
                self.repair_messages = tuple(messages)
            return await super().generate_structured(messages, output_schema, config)

    context = _context()
    port = RepairPort()
    adapter = GroundedActionAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    assert port.calls == 2
    assert adapter.last_schema_repair_count == 1
    assert adapter.last_structured_output_violations == (StructuredOutputViolation("target", "string_type"),)
    assert adapter.last_structured_output_repair_attempted is True
    assert adapter.last_structured_output_repair_failed is False
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"field_path":"target"' in repair_system
    assert "JSON tool call with fields name and arguments" in repair_system
    assert "private action response" not in repair_system


def test_grounded_schema_failure_preserves_safe_violation_path_after_failed_repair() -> None:
    class FailingRepairPort(_ActionPort):
        async def generate_structured(self, messages, output_schema, config):
            del messages, output_schema, config
            self.calls += 1
            raise StructuredOutputError(
                "private provider response",
                violations=(
                    StructuredOutputViolation(
                        "decision.action.tool_name",
                        "missing_required_field",
                    ),
                ),
            )

    context = _context()
    adapter = GroundedActionAdapter(
        FailingRepairPort(),
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert isinstance(outcome, ModelFailure)
    assert outcome.kind.value == "schema_error"
    assert outcome.attempt_origin.value == "network"
    assert adapter.last_model_call_count == 2
    assert adapter.last_structured_output_repair_attempted is True
    assert adapter.last_structured_output_repair_failed is True
    trace = _policy_trace_event(1, context, outcome, adapter)
    assert trace["structured_output_validation_stage"] == "provider_response_to_grounded_command"
    assert trace["structured_output_violations"] == (
        {
            "field_path": "decision.action.tool_name",
            "code": "missing_required_field",
        },
        {
            "field_path": "decision.action.tool_name",
            "code": "missing_required_field",
        },
    )
    assert trace["structured_output_repair_attempted"] is True
    assert trace["structured_output_repair_failed"] is True


def test_aria_hidden_ancestor_removes_layout_only_control_from_execution_visibility() -> None:
    assert _effective_visibility(True, {"ariaHiddenByAncestor": True}) is False
    assert _effective_visibility(True, {"ariaHiddenByAncestor": False}) is True
