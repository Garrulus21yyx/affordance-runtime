from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, replace

import numpy as np
import pytest

from affordance_runtime.actions import (
    ActionSpaceBuilder,
    verification_contract_for_action,
)
from affordance_runtime.actions.schema_validation import validate_value_issue
from affordance_runtime.agent import (
    Abort,
    AskUser,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.context import ContextBuilder, ModelFailure
from affordance_runtime.agent.context.action_candidate_projection import close_action_candidates
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
from affordance_runtime.agent.context.step_projection import _semantic_neighborhood
from affordance_runtime.benchmarks.target_loop.instrumentation import _policy_trace_event
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOL_CALL_ENVELOPE,
    GroundedActionResolution,
    GroundedToolPhase,
)
from affordance_runtime.model.policy.grounded_tool_port_bridge import (
    _TOOL_INTENT_REPAIR_CODES,
    CompactJsonDecisionPort,
    GroundedToolCommandPayload,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import _build_request as _action_request
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallIssueCode,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model.providers.port import (
    ModelCallRecord,
    ModelConfig,
    ModelImageURLPart,
    ModelTextPart,
    StructuredOutputError,
    StructuredOutputViolation,
)
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

    async def generate_structured(self, messages, output_schema, config, **kwargs):
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
        return output_schema.model_validate({"name": "activate", "arguments": {"target": "E3"}})


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
    return ContextBuilder().build(
        task,
        projection.world,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(task.task_id, projection.world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing"),
    )


def _nested_context():
    raw = raw_observation(
        ax_node("group", "generic", "Choices", child_ids=("one", "two")),
        ax_node("one", "graphics-symbol", "", parent_id="group"),
        ax_node("two", "graphics-symbol", "", parent_id="group"),
        goal="Count the choices.",
    )
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:nested",
        source_revision="revision:nested",
        page_identity="page:nested",
        episode_identity="episode:nested",
        task_state=reset_task_state("observation:nested", task_run_id="run:nested"),
        entity_identity=_IDENTITY,
    )
    task = TaskGoal("task:nested", raw["goal"], risk_profile=RiskProfile.READ_ONLY)
    return ContextBuilder().build(
        task,
        projection.world,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(
            task.task_id,
            projection.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )


def _bound_public_context(context) -> dict[str, object]:
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    messages = GroundedPolicyContextBinder().action_messages(
        _action_request(context),
        catalog.specs,
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
    observation = payload["observation"]
    assert isinstance(observation, str)
    assert "[E1] textbox \"Username\"" in observation
    assert "[E2] textbox \"Password\"" in observation
    assert "[E3] button \"Login\"" in observation


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
    context = ContextBuilder().build(
        task,
        projection.world,
        ActionSpaceBuilder().build(task, projection.world),
        TaskEvaluation(
            task.task_id,
            projection.world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )

    public = _bound_public_context(context)
    observation = public["observation"]
    assert "facets count=" in observation and "coverage=complete" in observation
    assert (
        'clickable.appearance.color_family="blue" members=["E1","E2","E3"]'
        " count=3 completeness=complete_for_snapshot"
    ) in observation
    assert 'selected true=["E1","E2"] false=["E3"]' in observation


def test_structure_first_grounded_action_starts_from_public_structure_without_image() -> None:
    context = _context()
    port = _ActionPort(supports_multimodal=False)
    adapter = CompactJsonDecisionPort(
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
    assert set(public) == {"task", "observation", "goal_plan", "recent_steps", "affordances", "tools"}
    assert public["task"]["instruction"] == context.task.instruction
    assert "actions" not in public
    assert "formal_evaluation" not in public["task"]
    assert public["goal_plan"]["resolution"] == "unavailable"
    system_content = port.messages[0].content
    assert isinstance(system_content, str)
    assert "Use exactly one offered tool and follow its current schema" in system_content
    assert {item["name"] for item in public["tools"]} == {
        "type_text",
        "activate",
        "ask_user",
        "wait",
        "abort",
    }
    assert set(public["goal_plan"]) == {
        "resolution",
        "plan_version",
        "plan_digest",
        "items",
    }
    trace = _policy_trace_event(1, context, outcome.decision, adapter)
    assert trace["model_image_input_count"] == 0
    assert trace["selected_grounding"]["marked"] is False


def test_structure_first_does_not_attach_image_just_because_world_has_visual_source() -> None:
    context = _context()
    visual_source = replace(
        context.actor_world.sources[0],
        source_ref="S2",
        modality="visual",
    )
    context = replace(
        context,
        actor_world=replace(
            context.actor_world,
            sources=(*context.actor_world.sources, visual_source),
        ),
    )
    port = _ActionPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    user_content = port.messages[1].content
    assert isinstance(user_content, str)
    assert adapter.last_image_input_count == 0
    public = json.loads(user_content)
    assert "actions" not in public
    trace = _policy_trace_event(1, context, outcome.decision, adapter)
    assert trace["model_image_input_count"] == 0


def test_structure_first_attaches_current_image_for_explicit_unresolved_visual_request() -> None:
    context = _context()
    visual_source = replace(
        context.actor_world.sources[0],
        source_ref="S2",
        modality="visual",
        projection_coverage="partial",
    )
    context = replace(
        context,
        actor_world=replace(
            context.actor_world,
            sources=(*context.actor_world.sources, visual_source),
        ),
        recent_steps=BoundedSection(
            (
                AgentTurnView(
                    "requestobservation",
                    "request_evidence",
                    semantic_summary={
                        "purpose": "visual_property",
                        "feedback_code": "observation_acquired",
                    },
                ),
            ),
            1,
            False,
        ),
    )
    port = _ActionPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    user_content = port.messages[1].content
    assert isinstance(user_content, tuple)
    assert isinstance(user_content[0], ModelTextPart)
    assert len(user_content) == 2
    assert isinstance(user_content[1], ModelImageURLPart)
    assert adapter.last_image_input_count == 1


def test_request_evidence_schema_matches_observation_property_contract() -> None:
    base = _context()
    context = replace(
        base,
        actor_world=replace(
            base.actor_world,
            observation_capabilities=(
                {
                    "modality": "visual",
                    "assurance": "weak",
                    "purposes": ("target_disambiguation", "visual_property"),
                },
            ),
        ),
    )
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    spec = next(item for item in catalog.specs if item.name == "request_evidence")

    assert validate_value_issue(
        {
            "purpose": "target_disambiguation",
            "subject": "current_world",
            "property": "visual_state",
        },
        spec.input_schema,
    ) is not None
    assert validate_value_issue(
        {"purpose": "target_disambiguation", "subject": "current_world"},
        spec.input_schema,
    ) is None
    assert validate_value_issue(
        {"purpose": "visual_property", "subject": "current_world", "property": "visual_state"},
        spec.input_schema,
    ) is None


def test_compact_argument_repair_keeps_the_selected_observation_tool() -> None:
    @dataclass
    class CompactRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = True
        last_call: ModelCallRecord | None = None
        calls: int = 0
        repair_messages: tuple = ()

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del config
            self.calls += 1
            if self.calls == 1:
                return GroundedToolCommandPayload(name="request_evidence", arguments={"target": "E1"})
            self.repair_messages = tuple(messages)
            return output_schema.model_validate({
                "name": "request_evidence",
                "arguments": {"purpose": "entity_discovery", "subject": "current_world"},
            })

    context = _context()
    context = replace(
        context,
        actor_world=replace(
            context.actor_world,
            observation_capabilities=(
                {"modality": "structural", "assurance": "structural", "purposes": ("criterion_verification",)},
                {"modality": "visual", "assurance": "weak", "purposes": ("entity_discovery",)},
            ),
        ),
    )
    port = CompactRepairPort()
    adapter = CompactJsonDecisionPort(
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
    assert adapter.last_argument_violation_paths == ("arguments.purpose",)
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
    assert '"field_paths":["arguments.purpose"]' in repair_system


def test_failed_argument_repair_preserves_response_and_violation_in_trace() -> None:
    @dataclass
    class FailedArgumentRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        last_transcript: object | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config
            self.calls += 1
            if self.calls == 1:
                return GroundedToolCommandPayload(
                    name="activate", arguments={"target": "E99"}
                )
            self.last_transcript = {
                "openinference.span.kind": "LLM",
                "llm.input_messages": [{"role": "system", "content": "repair"}],
                "llm.output_messages": [{"role": "assistant", "content": "{\"arguments\":{}}"}],
                "status": "schema_error",
            }
            raise StructuredOutputError(
                "repair response omitted name",
                violations=(StructuredOutputViolation("name", "missing"),),
            )

    context = _context()
    port = FailedArgumentRepairPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))
    trace = _policy_trace_event(1, context, outcome, adapter)

    assert isinstance(outcome, ModelFailure)
    assert tuple(item.phase for item in adapter.last_generation_attempts) == ("initial",)
    assert tuple(item.status for item in adapter.last_generation_attempts) == ("accepted",)
    assert adapter.last_structured_output_repair_failed is False
    assert len(trace["generation_attempts"]) == 1
    assert trace["generation_attempts"][0]["status"] == "accepted"


def test_compact_bridge_normalizes_nested_parameters_without_model_repair() -> None:
    @dataclass
    class NestedParametersPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config
            self.calls += 1
            return GroundedToolCommandPayload(
                name="activate",
                arguments={"parameters": {"target": "E3"}},
            )

    port = NestedParametersPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(_context())))

    assert not isinstance(outcome, ModelFailure)
    assert isinstance(outcome.decision, SelectAction)
    assert port.calls == 1
    assert adapter.last_argument_repair_count == 0
    assert adapter.last_resolution_code.value == "accepted"


def test_compact_transport_carries_unified_world_and_tool_menu_once() -> None:
    @dataclass
    class CompactPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = True
        last_call: ModelCallRecord | None = None
        messages: tuple = ()
        output_schema: object = None

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del config
            self.messages = tuple(messages)
            self.output_schema = output_schema
            return output_schema.model_validate({"name": "activate", "arguments": {"target": "E3"}})

    context = _context()
    port = CompactPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    user_content = port.messages[1].content
    assert isinstance(user_content, str)
    public = json.loads(user_content)
    assert set(public) == {"task", "observation", "goal_plan", "recent_steps", "affordances", "tools"}
    assert {item["name"].split("_")[0] for item in public["tools"]} == {
        "type",
        "activate",
        "ask",
        "wait",
        "abort",
    }
    assert all("E1(" not in item["description"] for item in public["tools"])
    assert all(
        "current observation" in item["description"]
        for item in public["tools"]
        if item["name"] not in {"ask_user", "wait", "abort"}
    )
    assert all(
        "Runtime revalidates existence, currentness, and legality" in item["description"]
        for item in public["tools"]
        if item["name"] in {"type_text", "activate"}
    )
    assert all("memory" not in item["input_schema"]["properties"] for item in public["tools"])
    assert tuple(public) == ("task", "observation", "goal_plan", "recent_steps", "affordances", "tools")


def test_unknown_tool_intent_gets_one_bounded_model_reemission() -> None:
    @dataclass
    class ToolIntentRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0
        repair_messages: tuple = ()

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del config
            self.calls += 1
            if self.calls == 1:
                return output_schema.model_validate({"name": "click", "arguments": {}})
            self.repair_messages = tuple(messages)
            return output_schema.model_validate(
                {"name": "activate", "arguments": {"target": "E3"}}
            )

    context = _context()
    port = ToolIntentRepairPort()
    adapter = CompactJsonDecisionPort(
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


def test_only_unknown_tool_names_use_the_did_you_mean_reemission_path() -> None:
    assert _TOOL_INTENT_REPAIR_CODES == {ToolCallIssueCode.UNKNOWN_TOOL}


def test_tool_intent_repair_is_never_retried_or_chained_to_argument_repair() -> None:
    @dataclass
    class FailedToolIntentRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config
            self.calls += 1
            return GroundedToolCommandPayload(name="click", arguments={})

    context = _context()
    port = FailedToolIntentRepairPort()
    adapter = CompactJsonDecisionPort(
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
            {"target": "E3"},
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
        "tools",
        "serialized_bytes",
    }
    assert tuple(item.spec for item in catalog.tools) == catalog.specs
    assert tuple(item.binding for item in catalog.tools) == catalog.bindings


def test_find_actions_exposes_search_filters_and_maps_current_refs_privately() -> None:
    context = _context()
    context = replace(
        context,
        actions=replace(
            context.actions,
            options=context.actions.options[:1],
            total_count=len(context.actions.options),
            page_size=1,
            truncated=True,
            has_more=True,
            next_cursor="cursor:test",
        ),
    )
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    spec = next(item for item in catalog.specs if item.name == "find_actions")
    target_ref = context.actions.options[0].target_ref

    assert set(spec.input_schema["properties"]) == {
        "query",
        "target",
        "relevance_role",
        "cursor",
    }
    resolution = resolve_grounded_tool_call(
        catalog,
        ToolCall("find_actions", {"query": "like", "target": target_ref}),
        expected_context_id=context.context_id,
    )
    assert isinstance(resolution.decision, RequestActionPage)
    assert resolution.decision.query == "like"
    assert resolution.decision.target_id == next(
        target_id for target_id, ref in context.grounding.target_refs.items() if ref == target_ref
    )


@pytest.mark.parametrize(
    ("name", "arguments", "decision_type"),
    (
        ("ask_user", {"question": "Which account?", "requested_fields": ["account"]}, AskUser),
        ("wait", {"reason": "page is loading", "max_wait_ms": 250}, Wait),
        ("abort", {"reason": "capability unavailable", "category": "unsupported"}, Abort),
    ),
)
def test_grounded_catalog_exposes_the_current_core_control_algebra(name, arguments, decision_type) -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall(name, arguments, "provider-call:control"),
        expected_context_id=context.context_id,
    )

    assert isinstance(outcome.decision, decision_type)
    assert outcome.decision.tool_call_id == "provider-call:control"


def test_grounded_catalog_does_not_expose_propose_done() -> None:
    catalog = compile_grounded_tool_catalog(_context(), GroundedToolPhase.ACTION_SELECTION)

    assert "propose_done" not in {item.name for item in catalog.specs}


def test_grounded_catalog_counts_complete_current_children_without_mutating_world() -> None:
    context = _nested_context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    spec = next(item for item in catalog.specs if item.name == "count_children")
    containers = spec.input_schema["properties"]["containers"]["items"]["enum"]
    assert containers == ("E1",) or containers == ["E1"]
    root = context.actor_world.documents[0].roots[0]
    assert "member_count" not in root.state

    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall("count_children", {"containers": ["E1"]}, "provider-call:count"),
        expected_context_id=context.context_id,
    )

    assert outcome.decision == LocalToolResult(
        context.context_id,
        "count_children",
        {"containers": ("E1",)},
        {"counts": {"E1": 2}, "total": 2},
        "provider-call:count",
    )


def test_count_result_is_nested_under_the_matching_recent_step_result() -> None:
    context = replace(
        _nested_context(),
        recent_steps=BoundedSection(
            (
                AgentTurnView(
                    "localtoolresult",
                    "count_children",
                    reason="local_tool_result",
                    semantic_summary={
                        "containers": ("E1",),
                        "result": {"counts": {"E1": 2}, "total": 2},
                    },
                ),
            ),
            1,
            False,
        ),
    )

    recent = _bound_public_context(context)["recent_steps"]["recent_trajectory"][0]

    assert recent["action"]["details"]["containers"] == ["<expired-ref>"]
    assert recent["result"]["details"] == {
        "counts": {"<expired-ref>": 2},
        "total": 2,
    }
    assert not re.search(r"\bE[1-9][0-9]{0,2}\b", json.dumps(recent))

    trace = _policy_trace_event(
        2,
        context,
        LocalToolResult(
            context.context_id,
            "count_children",
            {"containers": ("E1",)},
            {"counts": {"E1": 2}, "total": 2},
            "provider-call:count",
        ),
        object(),
    )
    assert trace["decision"]["tool_name"] == "count_children"
    assert trace["previous_runtime_tool_result"] == {"counts": {"E1": 2}, "total": 2}


def test_compact_transport_envelope_is_catalog_independent() -> None:
    schema = GroundedToolCommandPayload.model_json_schema()

    assert set(schema["properties"]) == {"name", "arguments"}
    assert schema["properties"]["name"] == {"title": "Name", "type": "string"}
    assert schema["properties"]["arguments"] == {
        "additionalProperties": True,
        "title": "Arguments",
        "type": "object",
    }
    assert "oneOf" not in json.dumps(schema)
    assert "enum" not in json.dumps(schema)
    assert GroundedToolCommandPayload.model_validate(
        {"name": "unknown_until_catalog_resolution", "arguments": {"opaque": "value"}}
    ).command_arguments() == {"opaque": "value"}
    for annotated in (
        {
            "name": "activate",
            "arguments": {"target": "E12"},
            "description": "must not become a business argument",
        },
        {
            "name": "activate",
            "arguments": {"target": "E12"},
            "required": ["target"],
        },
    ):
        payload = GroundedToolCommandPayload.model_validate(annotated)
        assert payload.command_arguments() == {"target": "E12"}
        assert set(payload.model_dump()) == {"name", "arguments"}
    with pytest.raises(ValueError):
        GroundedToolCommandPayload.model_validate({"name": "activate"})


def test_compact_action_payload_defers_tool_semantics_to_catalog_resolution() -> None:
    semantic_key = "(1,-2)"
    spec = ToolSpec(
        "activate",
        "Activate a current candidate.",
        {
            "type": "object",
            "properties": {"semantic_grid_cell": {"type": "string", "enum": [semantic_key]}},
            "required": ["semantic_grid_cell"],
            "additionalProperties": False,
        },
    )
    accepted = GroundedToolCommandPayload.model_validate(
        {"name": "activate", "arguments": {"semantic_grid_cell": semantic_key}}
    )
    invalid_for_tool = GroundedToolCommandPayload.model_validate(
        {"name": "activate", "arguments": {"semantic_grid_cell": "E38"}}
    )

    assert accepted.command_arguments() == {"semantic_grid_cell": semantic_key}
    assert invalid_for_tool.command_arguments() == {"semantic_grid_cell": "E38"}
    assert validate_value_issue(
        invalid_for_tool.command_arguments(), spec.input_schema, path="parameters"
    ) is not None


def test_provider_normalizer_unwraps_only_unambiguous_nested_parameters() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    target = next(item.ref for item in context.grounding.entities if "activate" in item.verbs)
    normalizer = ProviderCallNormalizer()

    normalized = normalizer.normalize(
        ToolCall("activate", {"parameters": {"target": target}}, "call:nested"),
        catalog,
    )
    conflicting = normalizer.normalize(
        ToolCall(
            "activate",
            {"target": target, "parameters": {"target": target}},
            "call:conflict",
        ),
        catalog,
    )

    assert normalized.status is ToolCallReconciliationStatus.EXACT
    assert normalized.exact_call == ToolCall("activate", {"target": target}, "call:nested")
    assert conflicting.status is ToolCallReconciliationStatus.REPAIR_REQUIRED
    assert conflicting.field_paths == ("arguments.parameters",)


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
    assert tool.input_schema["properties"]["target"]["pattern"] == "^E[1-9][0-9]{0,2}$"
    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall("activate", {"target": "E2"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(outcome, GroundedActionResolution)
    assert isinstance(outcome.decision, SelectAction)
    assert outcome.decision.action_id == actions.options[1].action_id


def test_invalid_compact_target_gets_one_bounded_repair_then_fails_closed() -> None:
    @dataclass
    class InvalidTargetPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config
            self.calls += 1
            return GroundedToolCommandPayload(name="activate", arguments={"target": "E99"})

    context = _selector_context(
        operation="activate",
        schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )
    port = InvalidTargetPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert isinstance(outcome, ModelFailure)
    assert port.calls == 1
    assert adapter.last_argument_repair_count == 0
    assert adapter.last_argument_violation_paths == ()


def test_compact_argument_repair_may_explicitly_reemit_a_different_current_target() -> None:
    @dataclass
    class DriftingRepairPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config
            self.calls += 1
            if self.calls == 1:
                return GroundedToolCommandPayload(name="type_text", arguments={"target": "E2"})
            return GroundedToolCommandPayload(
                name="type_text",
                arguments={"target": "E3", "text": "secret"},
            )

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
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert not isinstance(outcome, ModelFailure)
    assert port.calls == 2
    assert adapter.last_argument_repair_count == 1
    assert adapter.last_argument_violation_paths == ("arguments.text",)


def test_grounding_projection_carries_bounded_interaction_history_without_duplication() -> None:
    context = _context()
    targets = (
        AgentHistoricalTargetView("textbox", "User name", ("Account form",)),
        AgentHistoricalTargetView("textbox", "Code", ("Account form",)),
        AgentHistoricalTargetView("button", "Submit", ("Account form",)),
    )
    context = replace(
        context,
        recent_steps=BoundedSection(
            (
                AgentTurnView(
                    "selectaction",
                    "type_text",
                    targets[0],
                    destination=targets[1],
                    public_parameters={"text": "donovan"},
                    expected_outcome="value donovan is entered",
                    dispatch_status="sent",
                    local_postcondition="satisfied",
                    transition={"observed_change": "changed", "evidence_method": "native"},
                    task_evaluation_status="incomplete",
                    reason="action_postcondition_satisfied",
                ),
                AgentTurnView(
                    "selectaction",
                    "type_text",
                    targets[1],
                    public_parameters={"text": "UV"},
                    dispatch_status="sent",
                    local_postcondition="satisfied",
                    transition={"observed_change": "changed", "evidence_method": "native"},
                    task_evaluation_status="incomplete",
                    reason="action_postcondition_satisfied",
                ),
                AgentTurnView(
                    "selectaction",
                    "activate",
                    targets[2],
                    dispatch_status="sent",
                    local_postcondition="unknown",
                    transition={"observed_change": "unknown", "evidence_method": "none"},
                    task_evaluation_status="incomplete",
                    reason="action_unknown_low_local",
                    semantic_summary={"feedback_code": "action_outcome_unknown"},
                ),
            ),
            3,
            False,
        ),
    )

    history = _bound_public_context(context)["recent_steps"]

    assert history["earlier_actions"] == []
    assert history["retained_count"] == 3
    trajectory = history["recent_trajectory"]
    assert [item["action"]["target"]["label"] for item in trajectory] == [
        "User name",
        "Code",
        "Submit",
    ]
    assert all("task" not in item["result"] for item in trajectory)
    assert [item["action"]["tool"] for item in trajectory] == [
        "type_text",
        "type_text",
        "activate",
    ]
    assert trajectory[0]["result"]["transition"] == {
        "observed_change": "changed",
        "evidence_method": "native",
    }
    assert trajectory[-1]["action"]["details"] == {
        "feedback_code": "action_outcome_unknown"
    }


def test_grounded_history_retains_observation_modality_and_tool_describes_current_source() -> None:
    context = _context()
    context = replace(
        context,
        actor_world=replace(
            context.actor_world,
            observation_capabilities=(
                {"modality": "structural", "assurance": "structural", "purposes": ("criterion_verification",)},
                {"modality": "visual", "assurance": "weak", "purposes": ("entity_discovery",)},
            ),
        ),
        recent_steps=BoundedSection(
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

    previous = _bound_public_context(context)["recent_steps"]["recent_trajectory"][0]
    assert previous["action"]["details"]["purpose"] == "criterion_verification"
    descriptions = {item.name: item.description for item in catalog.specs}
    assert "request_evidence" in descriptions
    assert "Runtime admits the need" in descriptions["request_evidence"]


def test_grounded_recent_steps_keep_eight_pairs_and_only_latest_arguments() -> None:
    context = _context()
    target = AgentHistoricalTargetView("textbox", "Value", ("Form",))
    turns = tuple(
        AgentTurnView(
            "selectaction",
            "type_text",
            target,
            public_parameters={"text": str(index)},
            dispatch_status="sent",
            local_postcondition="satisfied",
            transition={"observed_change": "changed", "evidence_method": "native"},
            task_evaluation_status="incomplete",
            reason=f"step-{index}",
        )
        for index in range(10)
    )
    context = replace(context, recent_steps=BoundedSection(turns, len(turns), False))

    recent_steps = _bound_public_context(context)["recent_steps"]

    assert recent_steps["retained_count"] == 8
    assert len(recent_steps["earlier_actions"]) == 4
    assert recent_steps["earlier_actions"][0]["outcome"] == "step-2"
    assert len(recent_steps["recent_trajectory"]) == 4
    assert recent_steps["recent_trajectory"][-1]["action"]["arguments"] == {"text": "9"}


def test_grounded_trajectory_never_keeps_prior_observations_or_refs() -> None:
    context = _context()
    turns = tuple(
        AgentTurnView(
            "selectaction",
            "activate",
            AgentHistoricalTargetView("button", "Like", ("Rosie", "@nibh", "Id sit.")),
            reason=f"step-{index}",
        )
        for index in range(5)
    )
    context = replace(context, recent_steps=BoundedSection(turns, len(turns), False))

    history = _bound_public_context(context)["recent_steps"]

    assert len(history["earlier_actions"]) == 1
    assert {"observation", "target_ref", "destination_ref", "images"}.isdisjoint(
        AgentTurnView.__dataclass_fields__
    )
    assert "observation" not in history["earlier_actions"][0]
    assert len(history["recent_trajectory"]) == 4
    assert all("observation" not in item for item in history["recent_trajectory"])
    assert not re.search(r"\bE[1-9][0-9]{0,2}\b", json.dumps(history))
    assert history["recent_trajectory"][0]["action"]["target"] == {
        "role": "button",
        "label": "Like",
        "context": ["Rosie", "@nibh", "Id sit."],
    }


def test_historical_target_neighborhood_stops_at_nearest_semantic_group() -> None:
    target = ActorWorldNodeView(
        "E13",
        "clickable",
        "",
        {"semantic.dom.attribute.class_tokens": ("like",)},
    )
    controls = ActorWorldNodeView("E10", "generic", "", children=(target,))
    post = ActorWorldNodeView(
        "E5",
        "generic",
        "",
        children=(
            ActorWorldNodeView("N1", "StaticText", "Rosie"),
            ActorWorldNodeView("N2", "StaticText", "@nibh"),
            ActorWorldNodeView("N3", "StaticText", "Id sit."),
            controls,
        ),
    )
    root = ActorWorldNodeView(
        "E4",
        "generic",
        "",
        children=(post, ActorWorldNodeView("N4", "StaticText", "Ophelia")),
    )

    assert _semantic_neighborhood((root, post, controls, target)) == (
        "Rosie",
        "@nibh",
        "Id sit.",
    )


def test_grounded_recent_steps_keep_effect_details_for_nonlatest_actions() -> None:
    context = _context()
    target_id = next(iter(context.grounding.target_refs))
    target = AgentHistoricalTargetView("button", "Like", ("Rosie", "@nibh"))
    turns = (
        AgentTurnView(
            "selectaction",
            "activate",
            target,
            dispatch_status="sent",
            local_postcondition="unknown",
            transition={
                "role": "button",
                "label": "Like",
                "before_state": {"active": False},
                "after_state": {"active": True},
                "observed_change": "changed",
                "evidence_method": "structural",
                "target_changed": True,
                "fact_changes": (
                    {
                        "subject_id": target_id,
                        "predicate": "active",
                        "before": False,
                        "after": True,
                    },
                ),
            },
            task_evaluation_status="incomplete",
            reason="target changed",
        ),
        AgentTurnView(
            "selectaction",
            "activate",
            target,
            dispatch_status="sent",
            local_postcondition="unknown",
            transition={"observed_change": "changed", "evidence_method": "structural"},
            task_evaluation_status="incomplete",
            reason="target changed again",
        ),
    )
    context = replace(context, recent_steps=BoundedSection(turns, len(turns), False))

    first = _bound_public_context(context)["recent_steps"]["recent_trajectory"][0]

    assert first["result"]["transition"] == {
        "role": "button",
        "label": "Like",
        "before_state": {"active": False},
        "after_state": {"active": True},
        "observed_change": "changed",
        "evidence_method": "structural",
        "target_changed": True,
        "fact_changes": [
            {
                "predicate": "active",
                "before": False,
                "after": True,
            },
        ],
    }


def test_single_target_action_still_requires_the_current_public_reference() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    activate = next(item for item in catalog.specs if item.name == "activate")

    assert to_json_compatible(activate.input_schema)["required"] == ["target"]
    assert to_json_compatible(activate.input_schema)["properties"]["target"]["pattern"] == "^E[1-9][0-9]{0,2}$"
    outcome = resolve_grounded_tool_call(
        catalog,
        ToolCall("activate", {"target": "E3"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(outcome, GroundedActionResolution)


def test_action_schema_retry_repairs_the_same_model_decision() -> None:
    class RepairPort(_ActionPort):
        repair_messages: tuple = ()

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError(
                    "private action response",
                    violations=(StructuredOutputViolation("target", "string_type"),),
                )
            if self.calls == 1:
                self.repair_messages = tuple(messages)
            return await super().generate_structured(
                messages,
                output_schema,
                config,
                **kwargs,
            )

    context = _context()
    port = RepairPort()
    adapter = CompactJsonDecisionPort(
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
    assert tuple(item.phase for item in adapter.last_generation_attempts) == (
        "initial",
        "structured_output_repair",
    )
    assert tuple(item.status for item in adapter.last_generation_attempts) == (
        "schema_error",
        "accepted",
    )
    repair_system = port.repair_messages[0].content
    assert isinstance(repair_system, str)
    assert '"field_path":"target"' in repair_system
    assert "JSON tool call with fields name and arguments" in repair_system
    assert "private action response" not in repair_system


def test_grounded_schema_failure_preserves_safe_violation_path_after_failed_repair() -> None:
    class FailingRepairPort(_ActionPort):
        async def generate_structured(self, messages, output_schema, config, **kwargs):
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
    adapter = CompactJsonDecisionPort(
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
    assert tuple(item.phase for item in adapter.last_generation_attempts) == (
        "initial",
        "structured_output_repair",
    )
    assert all(item.status == "schema_error" for item in adapter.last_generation_attempts)
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
