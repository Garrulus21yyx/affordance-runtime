from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace

import numpy as np
import pytest
from browsergym_adapter_support import ax_node, raw_observation

from affordance_runtime.agent import (
    RequestObservation,
    SelectAction,
)
from affordance_runtime.agent.local_objective_proposal import (
    LocalObjectiveNeedsInput,
    LocalObjectiveNotRequired,
    LocalObjectiveProposal,
    LocalObjectiveUnsupported,
    LocalObjectiveUnsupportedReason,
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
from affordance_runtime.benchmarks.target_loop.instrumentation import _policy_trace_event
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary import ContextBuilder, ModelFailure
from affordance_runtime.model_boundary.acquisition_projection import ObservationCapabilityView
from affordance_runtime.model_boundary.action_candidate_projection import close_action_candidates
from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.model_boundary.contracts import AgentTurnView
from affordance_runtime.model_policy.contracts import ResolvedLocalObjectiveOutcome
from affordance_runtime.model_policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model_policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model_policy.grounded_tool_contracts import (
    GroundedActionResolution,
    GroundedToolPhase,
)
from affordance_runtime.model_policy.grounded_tool_port_bridge import (
    GroundedActionAdapter,
    GroundedObjectiveAdapter,
    GroundedObjectiveCommandPayload,
    GroundedToolCommandPayload,
    _command_payload_type,
)
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model_policy.objective_policy import _build_request as _objective_request
from affordance_runtime.model_policy.policy import _build_request as _action_request
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelImageURLPart,
    ModelTextPart,
    StructuredOutputError,
    StructuredOutputViolation,
)
from affordance_runtime.task import (
    ActionTemplate,
    FactEquals,
    RiskProfile,
    ScopeExtent,
    ScopeSpec,
    SetObjective,
    SetQuantifier,
    TaskGoal,
)
from affordance_runtime.task.local_objective import establish_local_objective
from affordance_runtime.world import ActionSpaceBuilder

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


@dataclass
class _ObjectivePort:
    provider: str = "zhipu"
    model: str = "glm-4.1v-thinking-flashx"
    endpoint_class: str = "fixture"
    supports_multimodal: bool = True
    last_call: ModelCallRecord | None = None
    last_output_schema: type | None = None

    async def generate_structured(self, messages, output_schema, config):
        del messages
        self.last_output_schema = output_schema
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name=output_schema.__name__,
            schema_version="grounded_tools.v2",
            latency_ms=1,
            response_id="response:objective",
        )
        return output_schema.model_validate({"op": "local_objective_not_required"})


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
        return output_schema.model_validate({"op": "activate"})


def _context(*, local_objective=None):
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
    state = AgentLoopState(projection.world, remaining_turns=5)
    if local_objective is not None:
        state.local_objective_state = establish_local_objective(
            local_objective,
            projection.world,
            enumerator=state.scope_enumerator,
        )
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
    nodes = [
        node
        for document in payload["world"]["documents"]
        for node in document["roots"]
    ]
    assert {item["ref"] for item in nodes} == {"E1", "E2", "E3"}
    assert {item["label"] for item in nodes} == {"Username", "Password", "Login"}


def test_objective_context_does_not_expose_action_selection_candidates() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.OBJECTIVE_PROPOSAL)
    messages = GroundedPolicyContextBinder().objective_messages(
        context,
        catalog.specs,
        _objective_request(context),
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        include_tool_menu=True,
    )
    content = messages[1].content
    assert isinstance(content, str)
    public = json.loads(content)

    assert "actions" not in public
    nodes = [
        node
        for document in public["world"]["documents"]
        for node in document["roots"]
    ]
    assert {item["ref"] for item in nodes} == {
        item.ref for item in context.grounding.entities
    }
    assert not {"activate", "type_text", "select_option", "read"}.intersection(
        item["op"] for item in public["tools"]
    )


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
                return (ToolCall("observe_visual", {"target": "E1"}),)
            self.repair_messages = tuple(messages)
            assert len(tools) == 1
            assert tools[0].name == "observe_visual"
            assert to_json_compatible(tools[0].input_schema) == {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            }
            return (ToolCall("observe_visual", {}),)

    context = _context()
    context = replace(
        context,
        world=replace(
            context.world,
            observation_capabilities=(
                ObservationCapabilityView("structural", "structural"),
                ObservationCapabilityView("visual", "weak"),
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
    assert outcome.decision.modality == "visual"
    assert port.calls == 2
    assert adapter.last_argument_repair_count == 1
    assert adapter.last_argument_violation_code == "invalid_action_parameters"
    assert adapter.last_argument_violation_paths == ("parameters.target",)
    assert adapter.last_selected_operation == "observe_visual"
    assert adapter.last_repaired_operation_match is True
    trace = _policy_trace_event(1, context, outcome.decision, adapter)
    assert trace["decision"] == {
        "kind": "RequestObservation",
        "context_id": context.context_id,
        "subject_id": "current_world",
        "modality": "visual",
        "required_assurance": "weak",
    }
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"selected_operation":"observe_visual"' in repair_system
    assert '"field_paths":["parameters.target"]' in repair_system


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

    operation_schema = payload_type.model_json_schema()["properties"]["op"]
    assert operation_schema["const"] == "observe_visual"


def test_compact_action_schema_is_generated_from_flat_tool_properties() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    payload_type = _command_payload_type(catalog.specs)

    properties = payload_type.model_json_schema()["properties"]
    assert "target" not in properties
    assert properties["text"]["anyOf"][0]["type"] == "string"


def test_compact_action_payload_accepts_semantic_selection_key_and_rejects_off_menu_value() -> None:
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

    accepted = payload_type.model_validate({"op": "activate", "semantic_grid_coordinate": semantic_key})

    assert accepted.semantic_grid_coordinate == semantic_key
    with pytest.raises(ValueError):
        payload_type.model_validate({"op": "activate", "semantic_grid_coordinate": "E38"})


def test_shared_target_semantics_are_hoisted_and_actor_selects_only_scope_difference() -> None:
    context = _context()
    source_options = context.actions.options[:2]
    raw_options = tuple(
        replace(
            option,
            semantic_action="activate",
            parameter_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            operation="",
            target_ref="",
            target_semantics={},
            target_role="",
            target_state={},
            target_marked=False,
            destination_mode="",
            grounding_context_id="",
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
                ObservationCapabilityView("structural", "structural"),
                ObservationCapabilityView("visual", "weak"),
            ),
        ),
        history=BoundedSection(
            (
                AgentTurnView(
                    "requestobservation",
                    reason="observation_no_information_gain",
                    semantic_summary={
                        "subject_id": "current_world",
                        "modality": "structural",
                        "required_assurance": "structural",
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
    assert previous["decision_details"]["modality"] == "structural"
    descriptions = {item.name: item.description for item in catalog.specs}
    assert "current structural source is already present" in descriptions["observe_structural"]
    assert "No current visual source is present" in descriptions["observe_visual"]


def test_schema_equivalent_actions_resolve_privately_to_current_action_ids() -> None:
    context = _context(
        local_objective=SetObjective(
            "set-objective:type-password",
            ScopeSpec("scope:viewport", "current-viewport", ScopeExtent.CURRENT_VIEWPORT),
            FactEquals("identity.label", "Password"),
            SetQuantifier.EXACTLY_ONE,
            ActionTemplate("type_text", parameters={"text": "UV"}),
        )
    )
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    assert {item.name for item in catalog.specs} == {"type_text"}
    type_text = catalog.specs[0]
    assert to_json_compatible(type_text.input_schema) == {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
        "additionalProperties": False,
    }
    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "type_text",
            {
                "text": "UV",
            },
        ),
        expected_context_id=context.context_id,
    )
    assert isinstance(outcome, GroundedActionResolution)
    decision = outcome.decision
    assert isinstance(decision, SelectAction)
    assert decision.parameters == {"text": "UV"}
    assert decision.action_id.startswith("action:")


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


def test_objective_catalog_has_closed_outcomes_and_a_stable_command_envelope() -> None:
    catalog = compile_grounded_tool_catalog(_context(), GroundedToolPhase.OBJECTIVE_PROPOSAL)
    assert [item.name for item in catalog.specs] == [
        "propose_local_objective",
        "local_objective_not_required",
        "local_objective_needs_input",
        "local_objective_unsupported",
    ]
    assert set(GroundedToolCommandPayload.model_json_schema()["properties"]) == {"op"}
    assert "memory" not in GroundedToolCommandPayload.model_json_schema()["properties"]
    assert set(GroundedObjectiveCommandPayload.model_json_schema()["properties"]) == {"op", "value"}
    assert all(item.name not in {"click", "fill", "select"} for item in catalog.specs)


def test_objective_nonproposal_tools_resolve_to_typed_outcomes() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.OBJECTIVE_PROPOSAL)

    not_required = resolve_grounded_tool_call(
        catalog,
        ToolCall("local_objective_not_required", {}),
        expected_context_id=context.context_id,
    )
    needs_input = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "local_objective_needs_input",
            {"value": {"question": "Which account?", "requested_fields": ["account"]}},
        ),
        expected_context_id=context.context_id,
    )
    unsupported = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "local_objective_unsupported",
            {
                "value": {
                    "reason_code": "task_semantics_unsupported",
                    "reason": "task cannot be expressed as a supported objective",
                }
            },
        ),
        expected_context_id=context.context_id,
    )

    assert isinstance(not_required, LocalObjectiveNotRequired)
    assert isinstance(needs_input, LocalObjectiveNeedsInput)
    assert needs_input.requested_fields == ("account",)
    assert isinstance(unsupported, LocalObjectiveUnsupported)
    assert unsupported.reason_code is LocalObjectiveUnsupportedReason.TASK_SEMANTICS_UNSUPPORTED


def test_grounded_objective_adapter_returns_only_objective_envelopes() -> None:
    context = _context()
    port = _ObjectivePort()
    adapter = GroundedObjectiveAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
    )

    outcome = asyncio.run(adapter.generate(_objective_request(context)))

    assert isinstance(outcome, ResolvedLocalObjectiveOutcome)
    assert isinstance(outcome.outcome, LocalObjectiveNotRequired)
    assert port.last_output_schema is not None
    assert set(port.last_output_schema.model_json_schema()["properties"]) == {"op", "value"}


def test_grounded_schema_retry_returns_the_safe_field_violation_to_the_model() -> None:
    class RepairPort(_ObjectivePort):
        calls: int = 0
        repair_messages: tuple = ()

        async def generate_structured(self, messages, output_schema, config):
            self.calls += 1
            if self.calls == 1:
                raise StructuredOutputError(
                    "private provider response",
                    violations=(StructuredOutputViolation("target", "value_error"),),
                )
            self.repair_messages = tuple(messages)
            return await super().generate_structured(messages, output_schema, config)

    context = _context()
    port = RepairPort()
    adapter = GroundedObjectiveAdapter(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
    )

    outcome = asyncio.run(adapter.generate(_objective_request(context)))

    assert isinstance(outcome, ResolvedLocalObjectiveOutcome)
    assert port.calls == 2
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"field_path":"target"' in repair_system
    assert '"code":"value_error"' in repair_system
    assert "private provider response" not in repair_system


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
    assert adapter.last_structured_output_violations == (
        StructuredOutputViolation("target", "string_type"),
    )
    assert adapter.last_structured_output_repair_attempted is True
    assert adapter.last_structured_output_repair_failed is False
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"field_path":"target"' in repair_system
    assert "Return exactly one flat JSON object" in repair_system
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


def test_local_objective_tool_carries_semantics_without_pre_observation_target_identity() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.OBJECTIVE_PROPOSAL)
    decision = resolve_grounded_tool_call(
        catalog,
        ToolCall(
            "propose_local_objective",
            {
                "value": {
                    "kind": "set",
                    "predicate": {
                        "any_of": [
                            {
                                "all_of": [
                                    {
                                        "kind": "fact_equals",
                                        "field_name": "grid_coordinate",
                                        "expected": {"x": 1, "y": -2},
                                    }
                                ]
                            }
                        ]
                    },
                    "quantifier": "exactly_one",
                    "semantic_action": "activate",
                }
            },
        ),
        expected_context_id=context.context_id,
    )

    assert isinstance(decision, LocalObjectiveProposal)
    assert decision.objective.scope.root_entity_id == "current-viewport"


def test_aria_hidden_ancestor_removes_layout_only_control_from_execution_visibility() -> None:
    assert _effective_visibility(True, {"ariaHiddenByAncestor": True}) is False
    assert _effective_visibility(True, {"ariaHiddenByAncestor": False}) is True
