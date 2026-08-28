from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from types import SimpleNamespace

import numpy as np
import pytest

from affordance_runtime.actions import (
    ActionBinding,
    ActionSpaceBuilder,
    verification_contract_for_action,
)
from affordance_runtime.actions.schema_validation import validate_value_issue
from affordance_runtime.agent import (
    Abort,
    AskUser,
    FinalResponse,
    LocalToolResult,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.action_candidate_projection import close_action_candidates
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldNodeView
from affordance_runtime.agent.context.compact_world_renderer import inspect_actor_world
from affordance_runtime.agent.context.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.agent.context.contracts import (
    AgentHistoricalTargetView,
    AgentTurnView,
)
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.observation_delivery import current_findings_digest
from affordance_runtime.agent.context.step_projection import _semantic_neighborhood
from affordance_runtime.agent.core_loop import CoreAgentLoop
from affordance_runtime.agent.monitor import EpisodeMonitor, EpisodeMonitorRecommendation, RecoveryKind
from affordance_runtime.agent.profile import AgentLoopProfile
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingDecisionPort,
    CountingPolicy,
    _policy_trace_event,
)
from affordance_runtime.benchmarks.webarena_verified import WebArenaVerifiedFinalResponseCodec
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import ModelGenerationAttempt
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import (
    GroundedLocalToolName,
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOL_CALL_ENVELOPE,
    GroundedActionResolution,
    GroundedToolPhase,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.grounded_tool_rejection import (
    grounded_tool_rejection_decision,
)
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
    ObservationToolExposureProfile,
)
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.policy import _build_request as _action_request
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.pydantic_ai_bridge import (
    _attempt_token_delta,
    _tool_resolution_failure,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model.providers.port import (
    ModelCallRecord,
    ModelConfig,
    ModelImageURLPart,
    ModelTextPart,
    ProviderFailureKind,
    ProviderModelError,
    ProviderTransportErrorCategory,
    StructuredOutputError,
    StructuredOutputFailureKind,
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
from affordance_runtime.world import CoverageState, ObservationSourceProfile, SemanticTarget, StateFact
from tests.support.legacy_compact_json_decision_port import (
    CompactJsonDecisionPort,
    GroundedToolCommandPayload,
    ProtocolFeedback,
    ProtocolFeedbackKind,
)
from tests.support.model.recording_pydantic_model import _schema_example
from tests.support.surfaces.browsergym.browsergym_adapter_support import ax_node, raw_observation, reset_task_state
from tests.support.surfaces.browsergym.projection_support import project_browsergym_observation
from tests.support.world import fused_world

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


def _delivery(context, *, include_images: bool = False):
    return build_model_turn_delivery(context, include_images=include_images)


def _compile_catalog(context, phase=GroundedToolPhase.ACTION_SELECTION):
    return compile_grounded_tool_catalog(context, phase, _delivery(context))


def _resolve_catalog_call(catalog, call, **kwargs):
    kwargs.setdefault("expected_delivery_id", catalog.delivery_id)
    return resolve_grounded_tool_call(catalog, call, **kwargs)


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


def _form_context():
    raw = raw_observation(
        ax_node("directions", "form", "Directions", child_ids=("from", "to", "go")),
        ax_node("from", "textbox", "From", parent_id="directions"),
        ax_node("to", "textbox", "To", parent_id="directions"),
        ax_node("go", "button", "Go", parent_id="directions"),
        goal="Set the route endpoints.",
    )
    projection = project_browsergym_observation(
        raw,
        observation_id="observation:form-fields",
        source_revision="revision:form-fields",
        page_identity="page:form-fields",
        episode_identity="episode:form-fields",
        task_state=reset_task_state("observation:form-fields", task_run_id="run:form-fields"),
        entity_identity=_IDENTITY,
    )
    task = TaskGoal(
        "task:form-fields",
        raw["goal"],
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
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
    delivery = _delivery(context)
    catalog = compile_grounded_tool_catalog(
        context,
        GroundedToolPhase.ACTION_SELECTION,
        delivery,
    )
    binder = GroundedPolicyContextBinder()
    public = dict(
        binder._public_context_sections(  # noqa: SLF001 - owner-boundary fixture
            context,
            False,
            delivery,
        )["public"]
    )
    public["tools"] = tuple(
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in catalog.specs
    )
    return json.loads(json.dumps(public, ensure_ascii=False))


def _evidence_handoff_context(*, visual: bool = False):
    world = fused_world(
        "source:evidence-handoff",
        (
            SemanticTarget("target:alpha", "StaticText", "Metric: 33 units"),
            SemanticTarget("target:beta", "StaticText", "Metric: 48 units"),
        ),
        profile=(ObservationSourceProfile.visual() if visual else ObservationSourceProfile.dom()),
    )
    task = TaskGoal("task:evidence-handoff", "Compare the two visible metrics.")
    return ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )


def _selector_context(*, operation: str, schema: dict[str, object]):
    context = _context()
    selected = []
    seen_refs = set()
    for option in context.complete_actions:
        if option.target_role not in {"button", "textbox"} or option.target_ref in seen_refs:
            continue
        selected.append(option)
        seen_refs.add(option.target_ref)
        if len(selected) == 2:
            break
    source_options = tuple(selected)
    assert len(source_options) == 2
    source = source_options[0]
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
        for index, option in enumerate(source_options, 1)
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
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    public = json.dumps(_bound_public_context(context))
    assert {(item.role, item.label) for item in context.grounding.entities} == {
        ("textbox", "Username"),
        ("textbox", "Password"),
        ("button", "Login"),
        ("focused_context", "Current keyboard focus"),
        ("viewport", "Current page viewport"),
    }
    assert all(item.marked for item in context.grounding.entities if item.role in {"button", "textbox"})
    subject_kinds = {
        (item.semantic_action, item.target_role, item.target_label): item.subject_kind
        for item in context.complete_actions
    }
    assert subject_kinds[("scroll", "viewport", "Current page viewport")] == "viewport"
    assert subject_kinds[("press_key", "focused_context", "Current keyboard focus")] == "focused_context"
    assert not hasattr(catalog, "view")
    assert "bbox" not in public
    assert "entity:" not in public and "action:" not in public and "binding:" not in public
    payload = _bound_public_context(context)
    assert "actions" not in payload
    assert not {"actions.entities", "actions.groups"}.intersection(public)
    observation = payload["observation"]
    assert isinstance(observation, str)
    assert '[E1] textbox "Username"' in observation
    assert '[E2] textbox "Password"' in observation
    assert '[E3] button "Login"' in observation
    focused_ref = next(item.ref for item in context.grounding.entities if item.role == "focused_context")
    viewport_ref = next(item.ref for item in context.grounding.entities if item.role == "viewport")
    assert f'[{focused_ref}] focused_context "Current keyboard focus"' in observation
    assert f'[{viewport_ref}] viewport "Current page viewport"' in observation
    assert "find_controls" in {item.name for item in catalog.specs}


def test_actor_world_delivers_boolean_state_without_model_visible_facets() -> None:
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
    assert "coverage=complete" in observation
    assert any(projection in observation for projection in ("projection=page_map", "projection=full"))
    assert "facets count=" not in observation
    assert "members=[" not in observation
    assert "selected" in observation and "=true" in observation


def test_structure_first_grounded_action_starts_from_public_structure_without_image() -> None:
    context = _context()
    port = _ActionPort(supports_multimodal=False)
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert outcome.metadata.perception_profile == "structure-first.v1"
    assert adapter.compatibility_key.split(":")[2] == "structure-first.v1"
    assert adapter.compatibility_key.endswith(f":{GROUNDED_TOOL_CALL_ENVELOPE}")
    assert adapter.last_image_input_count == 0
    assert port.calls == 1
    assert adapter.last_model_call_count == 1
    user_content = port.messages[1].content
    assert isinstance(user_content, str)
    public = json.loads(user_content)
    assert set(public) == {"task", "observation", "goal_plan", "tools"}
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
        "press_key",
        "scroll",
        "read_region",
        "search_page_content",
        "list_regions",
        "find_controls",
        "submit_final_response",
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

    assert outcome.failure is None
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
        workspace=AgentWorkspace(
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
        ),
        current_step_index=1,
    )
    port = _ActionPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
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
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    spec = next(item for item in catalog.specs if item.name == "request_evidence")

    assert (
        validate_value_issue(
            {
                "purpose": "target_disambiguation",
                "subject": "current_world",
                "property": "visual_state",
            },
            spec.input_schema,
        )
        is not None
    )
    assert (
        validate_value_issue(
            {"purpose": "target_disambiguation", "subject": "current_world"},
            spec.input_schema,
        )
        is None
    )
    assert (
        validate_value_issue(
            {"purpose": "visual_property", "subject": "current_world", "property": "visual_state"},
            spec.input_schema,
        )
        is None
    )


def test_dynamic_request_evidence_batches_exact_current_manifest_refs() -> None:
    base = _context()
    context = replace(
        base,
        actor_world=replace(
            base.actor_world,
            observation_capabilities=(
                {
                    "modality": "visual",
                    "assurance": "weak",
                    "purposes": ("visual_property",),
                },
            ),
        ),
    )
    delivery = _delivery(context)
    catalog = compile_grounded_tool_catalog(
        context,
        GroundedToolPhase.ACTION_SELECTION,
        delivery,
        ObservationToolExposureProfile.DYNAMIC_VISUAL,
    )
    spec = next(item for item in catalog.specs if item.name == "request_evidence")
    refs = tuple(
        ref
        for ref in context.grounding.private_subject_bindings()
        if ref in delivery.manifest.exact_refs
    )
    assert len(refs) >= 2
    arguments = {
        "purpose": "visual_property",
        "subject_refs": list(refs[:2]),
        "predicate": "visually selected",
        "public_intent": "I will verify the visible selection state.",
    }
    assert validate_value_issue(arguments, spec.input_schema) is None

    resolution = _resolve_catalog_call(
        catalog,
        ToolCall("request_evidence", arguments, call_id="call:batch-visual"),
        expected_context_id=context.context_id,
        expected_catalog_id=catalog.catalog_id,
    )

    decision = resolution.decision
    assert isinstance(decision, RequestObservation)
    bindings = context.grounding.private_subject_bindings()
    assert decision.subject_ids == tuple(bindings[ref] for ref in refs[:2])
    assert decision.predicate == "visually selected"
    assert decision.query_id.startswith("observation-query:")
    assert catalog.observation_tool_profile_id == "dynamic-visual.v1"
    assert catalog.observation_tool_profile_digest
    assert (
        validate_value_issue(
            {**arguments, "subject_refs": [refs[0], refs[0]]},
            spec.input_schema,
        )
        is None
    )
    with pytest.raises(GroundedToolResolutionError, match="unique current"):
        _resolve_catalog_call(
            catalog,
            ToolCall(
                "request_evidence",
                {**arguments, "subject_refs": [refs[0], refs[0]]},
                call_id="call:duplicate-visual",
            ),
            expected_context_id=context.context_id,
        )


def test_invalid_compact_arguments_make_only_one_provider_call() -> None:
    @dataclass
    class InvalidArgumentsPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = True
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config, kwargs
            self.calls += 1
            return GroundedToolCommandPayload(name="request_evidence", arguments={"target": "E1"})

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
    port = InvalidArgumentsPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, LocalToolResult)
    assert outcome.output.decision.tool_name == "tool_rejected"
    assert port.calls == 1


def test_grounding_rejection_preserves_the_single_initial_attempt_in_trace() -> None:
    @dataclass
    class GroundingGapPort:
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
            return GroundedToolCommandPayload(name="activate", arguments={"target": "E99"})

    context = _context()
    port = GroundingGapPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))
    trace = _policy_trace_event(1, context, outcome, adapter)

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, LocalToolResult)
    assert outcome.output.decision.tool_name == "tool_rejected"
    assert tuple(item.phase for item in adapter.last_generation_attempts) == ("ordinary",)
    assert tuple(item.status for item in adapter.last_generation_attempts) == ("accepted",)
    assert len(trace["generation_attempts"]) == 1
    assert trace["generation_attempts"][0]["status"] == "accepted"


def test_compact_bridge_normalizes_nested_parameters_locally() -> None:
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

    assert outcome.failure is None
    assert isinstance(outcome.decision, SelectAction)
    assert port.calls == 1
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

    assert outcome.failure is None
    user_content = port.messages[1].content
    assert isinstance(user_content, str)
    public = json.loads(user_content)
    assert set(public) == {"task", "observation", "goal_plan", "tools"}
    assert {item["name"].split("_")[0] for item in public["tools"]} == {
        "type",
        "activate",
        "press",
        "scroll",
        "read",
        "search",
        "find",
        "list",
        "ask",
        "wait",
        "abort",
        "submit",
    }
    assert all("E1(" not in item["description"] for item in public["tools"])
    assert all(
        "current" in item["description"]
        for item in public["tools"]
        if item["name"] not in {"ask_user", "wait", "abort"}
    )
    assert all(
        "current executable" in item["description"]
        for item in public["tools"]
        if item["name"] in {"type_text", "activate"}
    )
    assert all('"memory"' not in json.dumps(item["input_schema"]) for item in public["tools"])
    assert tuple(public) == ("task", "observation", "goal_plan", "tools")


def test_unknown_tool_intent_is_rejected_after_one_provider_call() -> None:
    @dataclass
    class UnknownToolPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, config, kwargs
            self.calls += 1
            return output_schema.model_validate({"name": "click", "arguments": {}})

    context = _context()
    port = UnknownToolPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, LocalToolResult)
    assert outcome.output.decision.result["dispatch"] == "not_sent"
    assert port.calls == 1
    assert adapter.last_model_call_count == 1


def test_unknown_tool_is_rejected_after_one_provider_call() -> None:
    @dataclass
    class UnknownToolPort:
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
    port = UnknownToolPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, LocalToolResult)
    assert outcome.output.decision.result["dispatch"] == "not_sent"
    assert port.calls == 1


def test_grounded_catalog_is_only_tools_and_private_bindings() -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    outcome = _resolve_catalog_call(
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
        "delivery_id",
        "manifest",
        "delivery_index",
        "tools",
        "serialized_bytes",
        "observation_tool_profile_id",
        "observation_tool_profile_digest",
    }
    assert tuple(item.spec for item in catalog.tools) == catalog.specs
    assert tuple(item.binding for item in catalog.tools) == catalog.bindings


@pytest.mark.parametrize("visual", (False, True))
def test_search_page_content_offers_one_runtime_evidence_ref_for_exact_public_scalar(
    visual: bool,
) -> None:
    context = _evidence_handoff_context(visual=visual)
    catalog = _compile_catalog(context)
    search_spec = next(item for item in catalog.specs if item.name == "search_page_content")
    assert "exact text substring" in search_spec.description
    assert "not semantic retrieval" in search_spec.description
    assert "or proof that a collection was fully reviewed" in search_spec.description
    assert search_spec.input_schema["properties"]["query"]["description"] == (
        "exact text substring to locate in current readable records"
    )
    found = _resolve_catalog_call(
        catalog,
        ToolCall("search_page_content", {"query": "33 units"}, "provider-call:find-alpha"),
        expected_context_id=context.context_id,
    ).decision

    assert isinstance(found, LocalToolResult)
    item = found.result["items"][0]
    assert item["node_ref"].startswith("N")
    assert item["evidence_ref"].startswith("F")
    assert item["value"] == item["label"] == "Metric: 33 units"
    assert item["region_ref"].startswith("R")
    assert item["coverage"] == "complete"
    assert item["evidence_method"] == ("visual" if visual else "structural")
    assert item["observation_lineage"] == {
        "scope": "current_observation",
        "status": "current",
    }
    encoded_item = json.dumps(to_json_compatible(item))
    assert context.current_observation.observation_id not in encoded_item
    assert "source_observation_id" not in encoded_item
    canonical = context.private_fact_bindings[item["evidence_ref"]]
    record = context.evidence_index.resolve_record(canonical)
    assert record is not None and record.value == item["value"]


def test_read_region_returns_compact_readable_records_without_memory_tool() -> None:
    context = _evidence_handoff_context()
    found = _resolve_catalog_call(
        _compile_catalog(context),
        ToolCall("search_page_content", {"query": "33 units"}, "provider-call:find-region"),
        expected_context_id=context.context_id,
    ).decision
    region_ref = found.result["items"][0]["region_ref"]
    opened = _resolve_catalog_call(
        _compile_catalog(context),
        ToolCall("read_region", {"region_ref": region_ref}, "provider-call:open-region"),
        expected_context_id=context.context_id,
    ).decision
    assert isinstance(opened, LocalToolResult)
    assert opened.result["items"]
    assert "Metric: 33 units" in json.dumps(to_json_compatible(opened.result["items"]))
    assert all("evidence" not in item for item in opened.result["items"])
    assert opened.result["searched_domain"] == "readable_content"
    assert opened.result["zero_browser_dispatch"] is True
    assert "remember_fact" not in {item.name for item in _compile_catalog(context).specs}


def test_stale_source_scalar_is_not_offered_as_pinnable_evidence() -> None:
    target = SemanticTarget("target:stale", "text", "Metric: 33 units")
    world = fused_world(
        "source:stale",
        (target,),
        (
            StateFact(
                "fact:stale:value",
                target.target_id,
                "value",
                "Metric: 33 units",
                "source:stale",
            ),
        ),
        coverage=CoverageState.STALE,
    )
    task = TaskGoal("task:stale", "Read the current metric.")
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        ),
    )
    found = _resolve_catalog_call(
        _compile_catalog(context),
        ToolCall("search_page_content", {"query": "33 units"}, "provider-call:stale-find"),
        expected_context_id=context.context_id,
    ).decision

    assert isinstance(found, LocalToolResult)
    assert found.result["items"]
    assert all("evidence_ref" not in item for item in found.result["items"])
    assert "remember_fact" not in {item.name for item in _compile_catalog(context).specs}
    stale_view = context
    assert _delivery(stale_view).manifest.fact_refs == ()


def test_pydantic_bridge_preserves_grounded_tool_failure_classification() -> None:
    grounding_gap = GroundedToolResolutionError(
        GroundedToolResolutionCode.GROUNDING_GAP,
        "evidence_ref is not a current public scalar fact",
    )
    invalid_arguments = GroundedToolResolutionError(
        GroundedToolResolutionCode.INVALID_ARGUMENTS,
        "command.evidence_ref is not in the allowed enum",
    )

    assert _tool_resolution_failure(grounding_gap).kind is ModelFailureKind.TOOL_GROUNDING_GAP
    invalid_failure = _tool_resolution_failure(invalid_arguments)
    assert invalid_failure.kind is ModelFailureKind.INVALID_TOOL_ARGUMENTS
    assert invalid_failure.reason.startswith("invalid_tool_arguments")


def test_find_controls_has_one_natural_language_input_and_no_generic_continuation() -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    spec = next(item for item in catalog.specs if item.name == "find_controls")

    assert set(spec.input_schema["properties"]) == {"query"}
    assert "action_results_next_page" not in {item.name for item in catalog.specs}
    resolution = _resolve_catalog_call(
        catalog,
        ToolCall("find_controls", {"query": "like"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(resolution.decision, RequestActionPage)
    assert resolution.decision.query == "like"
    assert not hasattr(resolution.decision, "continuation_scope")


def test_final_response_tool_accepts_content_without_world_fact_lineage() -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    spec = next(item for item in catalog.specs if item.name == "submit_final_response")

    assert set(spec.input_schema["properties"]) == {"content"}
    assert spec.input_schema["required"] == ["content"]
    resolution = _resolve_catalog_call(
        catalog,
        ToolCall("submit_final_response", {"content": "supported answer"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(resolution.decision, FinalResponse)
    assert resolution.decision.evidence_refs == ()


def test_final_response_codec_guidance_is_owned_by_the_tool_contract_not_task_projection() -> None:
    guidance = (
        "JSON object: task_type RETRIEVE|MUTATE|NAVIGATE. Derive task_type and payload from task, never goal_plan."
    )
    context = replace(_context(), final_response_guidance=guidance)
    catalog = _compile_catalog(context)
    spec = next(item for item in catalog.specs if item.name == "submit_final_response")

    assert guidance in spec.description
    assert not hasattr(context.task, "final_response_guidance")
    assert guidance not in context.task.instruction


def test_upstream_webarena_response_definitions_fit_the_final_tool_contract() -> None:
    pytest.importorskip("webarena_verified")
    guidance = WebArenaVerifiedFinalResponseCodec().model_guidance
    context = replace(_context(), final_response_guidance=guidance)

    catalog = _compile_catalog(context)

    spec = next(item for item in catalog.specs if item.name == "submit_final_response")
    assert guidance in spec.description
    assert "MUTATE: Use when creating, updating, or deleting data or state" in spec.description
    assert "NAVIGATE: Use when navigating or browsing to show a specific page or location" in spec.description


def test_every_registered_local_tool_resolver_produces_its_contract_decision_type() -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    expected = {
        GroundedLocalToolName.REQUEST_EVIDENCE.value: RequestObservation,
        GroundedLocalToolName.COUNT_CHILDREN.value: ReadRegionResult,
        GroundedLocalToolName.READ_REGION.value: ReadRegionResult,
        GroundedLocalToolName.SEARCH_PAGE_CONTENT.value: SearchPageContentResult,
        GroundedLocalToolName.LIST_REGIONS.value: ReadRegionResult,
        GroundedLocalToolName.FIND_CONTROLS.value: RequestActionPage,
        GroundedLocalToolName.SUBMIT_FINAL_RESPONSE.value: FinalResponse,
        GroundedLocalToolName.ASK_USER.value: AskUser,
        GroundedLocalToolName.WAIT.value: Wait,
        GroundedLocalToolName.ABORT.value: Abort,
    }
    registered = tuple(spec for spec in catalog.specs if spec.name in expected)

    assert registered
    assert "read_next_page" not in {item.name for item in catalog.specs}
    assert "action_results_next_page" not in {item.name for item in catalog.specs}
    region_ref = next(iter(context.canonical_world.region_refs.values()))
    for index, spec in enumerate(registered):
        arguments = _schema_example(spec.input_schema)
        assert isinstance(arguments, dict)
        if spec.name == GroundedLocalToolName.READ_REGION.value:
            arguments["region_ref"] = region_ref
        elif spec.name == GroundedLocalToolName.SEARCH_PAGE_CONTENT.value:
            arguments["query"] = "shared"
        elif spec.name == GroundedLocalToolName.FIND_CONTROLS.value:
            arguments["query"] = "like"
        resolution = _resolve_catalog_call(
            catalog,
            ToolCall(spec.name, arguments, f"producer-contract:{index}"),
            expected_context_id=context.context_id,
        )
        assert type(resolution.decision) is expected[spec.name]
        if isinstance(resolution.decision, LocalToolResult):
            assert resolution.decision.result


def test_readable_matches_attach_current_grounding_without_changing_discovery_authority() -> None:
    task = TaskGoal(
        "task:watch4-synthetic",
        "Open the requested navigation section.",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    source_id = "obs:duplicate-label-discovery"
    revision = f"revision:{source_id}"
    schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    def binding(target_id: str) -> ActionBinding:
        return ActionBinding(
            f"binding:{target_id}",
            source_id,
            source_id,
            revision,
            f"fingerprint:{target_id}",
            target_id,
            target_id,
            "browsergym",
            "browsergym",
            "activate",
            "click",
            "external_ui_interaction",
            ("external_ui_interaction",),
            schema,
            {"route": "fixture"},
        )

    world = fused_world(
        source_id,
        (
            SemanticTarget("target:readonly", "heading", "Settings"),
            SemanticTarget("target:close", "button", "Close menu"),
            SemanticTarget("target:settings-tab", "tab", "Settings"),
            SemanticTarget("target:settings-link", "link", "Settings"),
        ),
        bindings=(
            binding("target:close"),
            binding("target:settings-tab"),
            binding("target:settings-link"),
        ),
        surface="browsergym",
    )
    action_space = ActionSpaceBuilder().build(task, world)
    evaluation = TaskEvaluation(task.task_id, world.observation_id, TaskEvaluationStatus.INCOMPLETE, "ongoing")
    context = ContextBuilder().build(task, world, action_space, evaluation)
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    readonly_ref = context.grounding.target_refs["target:readonly"]
    close_ref = context.grounding.target_refs["target:close"]
    actionable_refs = {
        context.grounding.target_refs["target:settings-tab"],
        context.grounding.target_refs["target:settings-link"],
    }
    assert readonly_ref.startswith("N")
    assert close_ref.startswith("E")
    assert all(ref.startswith("E") for ref in actionable_refs)

    activate_spec = next(item for item in catalog.specs if item.name == "activate")
    activate_binding = catalog.bindings[catalog.specs.index(activate_spec)]
    admitted_refs = {item.selector_values["target"] for item in activate_binding.private_resolutions}
    assert admitted_refs == {close_ref, *actionable_refs}

    inspected = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=world,
        action="find",
        query="Settings",
    )
    matches = inspected.items
    assert any(match["node_ref"] == readonly_ref for match in matches)
    grounded_matches = tuple(match for match in matches if match.get("target_ref") in actionable_refs)
    assert {match["target_ref"] for match in grounded_matches} == actionable_refs
    assert all(tuple(match["verbs"]) == ("activate",) for match in grounded_matches)
    assert all("actionable" not in match and "action_refs" not in match for match in matches)
    assert not any(match.get("node_ref") in actionable_refs for match in matches)

    initial = ToolCall("activate", {"target": "E114"}, "call:initial")
    with pytest.raises(GroundedToolResolutionError) as captured:
        _resolve_catalog_call(catalog, initial, expected_context_id=context.context_id)
    assert captured.value.code is GroundedToolResolutionCode.GROUNDING_GAP

    feedback = grounded_tool_rejection_decision(
        captured.value,
        initial,
        context.context_id,
        context,
        catalog.manifest,
    )
    assert isinstance(feedback, LocalToolResult)
    assert feedback.result["failure_kind"] == "tool_grounding_gap"
    assert feedback.result["dispatch"] == "not_sent"
    assert feedback.result["world_changed"] is False
    assert feedback.result["supported_operations"] == ()

    request = _resolve_catalog_call(
        catalog,
        ToolCall("find_controls", {"query": "definitely-not-present"}, "call:find"),
        expected_context_id=context.context_id,
    ).decision
    assert isinstance(request, RequestActionPage)
    from affordance_runtime.agent.run_state import RunState

    base_page = ContextBuilder().page(action_space, world)
    state = RunState(world, evaluation, 4, action_page=base_page)
    state.install_canonical_world(context.canonical_world)
    search_step = CoreAgentLoop(None, None, None)._action_page(
        task,
        state,
        action_space,
        context,
        request,
    )
    assert search_step.feedback == "action_page_empty"
    assert search_step.action_page == base_page
    assert search_step.action_page_result.result_coverage == "empty"
    assert search_step.action_page_result.matches == ()
    assert not hasattr(search_step.action_page_result, "continuation_available")
    assert readonly_ref not in {item.target_ref for item in search_step.action_page_result.matches}

    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    local = SearchPageContentResult(
        context.context_id,
        "search_page_content",
        {"query": "definitely-not-present"},
        {"action": "find", "matches": (), "total_count": 0},
    )
    local_step = replace(search_step, decision=local, feedback="local_tool_result", action_page_result=None)
    monitor.start_episode(world, evaluation)
    findings_digest = current_findings_digest(world)
    assert monitor.evaluate(local_step, findings_digest).recommendation is EpisodeMonitorRecommendation.CONTINUE
    recovery = monitor.evaluate(local_step, findings_digest)
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.kind is RecoveryKind.CONTROL_STALL
    blocked = monitor.evaluate(local_step, findings_digest)
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK


def test_cumulative_provider_usage_is_delta_counted_across_physical_attempts() -> None:
    previous = (
        ModelGenerationAttempt(
            1,
            "initial",
            "grounded-tools",
            "accepted",
            prompt_tokens=15598,
            completion_tokens=100,
            total_tokens=15698,
        ),
    )

    next_input, raw_cumulative = _attempt_token_delta(
        previous,
        {},
        SimpleNamespace(input_tokens=31442),
        "input_tokens",
    )
    assert next_input == 15844
    assert raw_cumulative == 31442
    assert previous[0].prompt_tokens + next_input == 31442


@pytest.mark.parametrize(
    ("name", "arguments", "decision_type"),
    (
        ("ask_user", {"question": "Which account?", "requested_fields": ["account"]}, AskUser),
        ("wait", {"reason": "page is loading"}, Wait),
        ("abort", {"reason": "capability unavailable", "category": "unsupported"}, Abort),
    ),
)
def test_grounded_catalog_exposes_the_current_core_control_algebra(name, arguments, decision_type) -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    outcome = _resolve_catalog_call(
        catalog,
        ToolCall(name, arguments, "provider-call:control"),
        expected_context_id=context.context_id,
    )

    assert isinstance(outcome.decision, decision_type)
    assert outcome.decision.tool_call_id == "provider-call:control"


def test_grounded_catalog_does_not_expose_propose_done() -> None:
    catalog = _compile_catalog(_context(), GroundedToolPhase.ACTION_SELECTION)

    assert "propose_done" not in {item.name for item in catalog.specs}


def test_grounded_catalog_counts_complete_current_children_without_mutating_world() -> None:
    context = _nested_context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    group_ref = next(
        item.ref for item in context.grounding.entities if item.role == "generic" and item.label == "Choices"
    )
    group_target_id = next(
        target_id for target_id, public_ref in context.grounding.target_refs.items() if public_ref == group_ref
    )
    region = context.region_index.region_for_target(group_target_id)
    assert region is not None
    region_ref = context.canonical_world.region_refs[region.key]
    opened = inspect_actor_world(
        context.actor_world,
        context.grounding,
        region_index=context.region_index,
        canonical_world=context.canonical_world,
        observation=context.current_observation,
        action="read_region",
        region_ref=region_ref,
    )
    assert opened.items
    assert "count_children" not in {item.name for item in catalog.specs}
    root = context.actor_world.documents[0].roots[0]
    assert "member_count" not in root.state


def test_workspace_result_is_not_duplicated_into_model_context() -> None:
    context = replace(
        _nested_context(),
        workspace=AgentWorkspace(
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
        ),
        current_step_index=1,
    )

    assert "recent_steps" not in _bound_public_context(context)

    trace = _policy_trace_event(
        2,
        context,
        ReadRegionResult(
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
    assert validate_value_issue(invalid_for_tool.command_arguments(), spec.input_schema, path="parameters") is not None


def test_provider_normalizer_unwraps_only_unambiguous_nested_parameters() -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
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


def test_provider_normalizer_prunes_only_schema_invalid_optional_arguments() -> None:
    catalog = _compile_catalog(_context(), GroundedToolPhase.ACTION_SELECTION)
    normalizer = ProviderCallNormalizer()

    empty_optional = normalizer.normalize(
        ToolCall(
            "search_page_content",
            {"query": "Shanksville", "cursor": ""},
            "call:empty-optional",
        ),
        catalog,
    )
    valid_optional = normalizer.normalize(
        ToolCall(
            "search_page_content",
            {"query": "Shanksville", "cursor": "opaque-page-2"},
            "call:valid-optional",
        ),
        catalog,
    )
    invalid_required = normalizer.normalize(
        ToolCall(
            "search_page_content",
            {"query": "", "cursor": "opaque-page-2"},
            "call:invalid-required",
        ),
        catalog,
    )

    assert empty_optional.status is ToolCallReconciliationStatus.EXACT
    assert empty_optional.exact_call == ToolCall(
        "search_page_content",
        {"query": "Shanksville"},
        "call:empty-optional",
    )
    assert valid_optional.status is ToolCallReconciliationStatus.EXACT
    assert valid_optional.exact_call == ToolCall(
        "search_page_content",
        {"query": "Shanksville", "cursor": "opaque-page-2"},
        "call:valid-optional",
    )
    assert invalid_required.status is ToolCallReconciliationStatus.REPAIR_REQUIRED
    assert invalid_required.field_paths == ("arguments.query",)


def test_shared_target_semantics_are_hoisted_and_inconsistent_actor_refs_fail_closed() -> None:
    context = _context()
    selected = []
    seen_refs = set()
    for option in context.complete_actions:
        if option.target_role not in {"button", "textbox"} or option.target_ref in seen_refs:
            continue
        selected.append(option)
        seen_refs.add(option.target_ref)
        if len(selected) == 2:
            break
    source_options = tuple(selected)
    assert len(source_options) == 2
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
    with pytest.raises(ValueError, match="candidates are outside"):
        replace(
            context,
            actions=actions,
            complete_actions=actions.options,
        )


def test_invalid_compact_target_fails_after_one_provider_call() -> None:
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

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, LocalToolResult)
    assert outcome.output.decision.result["dispatch"] == "not_sent"
    assert port.calls == 1


def test_invalid_compact_call_cannot_trigger_a_second_provider_call() -> None:
    @dataclass
    class InvalidArgumentsPort:
        provider: str = "zhipu"
        model: str = "glm-4.1v-thinking-flashx"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = False
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config
            self.calls += 1
            return GroundedToolCommandPayload(name="type_text", arguments={"target": "E2"})

    context = _selector_context(
        operation="type_text",
        schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    port = InvalidArgumentsPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, LocalToolResult)
    assert outcome.output.decision.result["dispatch"] == "not_sent"
    assert outcome.output.decision.result["target"]["role"] == "textbox"
    assert "type_text" in outcome.output.decision.result["supported_operations"]
    assert "E2" not in repr(outcome.output.decision.result)
    assert port.calls == 1


def test_grounding_projection_carries_bounded_interaction_history_without_duplication() -> None:
    context = _context()
    targets = (
        AgentHistoricalTargetView("textbox", "User name", ("Account form",)),
        AgentHistoricalTargetView("textbox", "Code", ("Account form",)),
        AgentHistoricalTargetView("button", "Submit", ("Account form",)),
    )
    context = replace(
        context,
        workspace=AgentWorkspace(
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
        ),
        current_step_index=3,
    )

    assert "recent_steps" not in _bound_public_context(context)
    assert len(context.workspace.recent_steps) == 3


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
        workspace=AgentWorkspace(
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
        ),
        current_step_index=1,
    )

    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)

    assert "recent_steps" not in _bound_public_context(context)
    descriptions = {item.name: item.description for item in catalog.specs}
    assert "request_evidence" in descriptions
    assert "Runtime chooses how" in descriptions["request_evidence"]


def test_grounded_workspace_is_not_a_second_model_visible_history() -> None:
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
            reason=f"step-{index} used F{index + 1}",
        )
        for index in range(10)
    )
    context = replace(context, workspace=AgentWorkspace(turns[-4:]), current_step_index=len(turns))

    assert "recent_steps" not in _bound_public_context(context)
    assert len(context.workspace.recent_steps) == 4


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
    context = replace(context, workspace=AgentWorkspace(turns[-4:]), current_step_index=len(turns))

    assert "recent_steps" not in _bound_public_context(context)
    assert {"observation", "target_ref", "destination_ref", "images"}.isdisjoint(AgentTurnView.__dataclass_fields__)
    assert len(context.workspace.recent_steps) == 4


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


def test_workspace_effect_details_remain_non_authoritative_and_not_model_visible() -> None:
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
    context = replace(context, workspace=AgentWorkspace(turns), current_step_index=len(turns))

    assert "recent_steps" not in _bound_public_context(context)
    assert context.workspace.recent_steps[0].transition["target_changed"] is True


def test_single_target_action_still_requires_the_current_public_reference() -> None:
    context = _context()
    catalog = _compile_catalog(context, GroundedToolPhase.ACTION_SELECTION)
    activate = next(item for item in catalog.specs if item.name == "activate")

    assert to_json_compatible(activate.input_schema)["required"] == ["target"]
    assert "enum" not in to_json_compatible(activate.input_schema)["properties"]["target"]
    outcome = _resolve_catalog_call(
        catalog,
        ToolCall("activate", {"target": "E3"}),
        expected_context_id=context.context_id,
    )
    assert isinstance(outcome, GroundedActionResolution)


def test_action_schema_error_returns_same_episode_feedback_after_one_provider_call() -> None:
    class SchemaErrorPort(_ActionPort):
        async def generate_structured(self, messages, output_schema, config, **kwargs):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError(
                    "private action response",
                    violations=(StructuredOutputViolation("target", "string_type"),),
                )
            return await super().generate_structured(
                messages,
                output_schema,
                config,
                **kwargs,
            )

    context = _context()
    port = SchemaErrorPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert outcome.output is not None
    assert isinstance(outcome.output.decision, ProtocolFeedback)
    assert outcome.output.decision.feedback_kind is ProtocolFeedbackKind.JSON_INVALID
    assert port.calls == 1
    assert adapter.last_structured_output_violations == (StructuredOutputViolation("target", "string_type"),)
    assert tuple(item.phase for item in adapter.last_generation_attempts) == ("ordinary",)
    assert tuple(item.status for item in adapter.last_generation_attempts) == ("json_invalid",)


def test_grounded_schema_failure_preserves_safe_violation_path_after_one_provider_call() -> None:
    class FailingSchemaPort(_ActionPort):
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
        FailingSchemaPort(),
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert outcome.output is not None
    assert isinstance(outcome.output.decision, ProtocolFeedback)
    assert outcome.output.decision.feedback_kind is ProtocolFeedbackKind.JSON_INVALID
    assert adapter.last_model_call_count == 1
    assert tuple(item.phase for item in adapter.last_generation_attempts) == ("ordinary",)
    assert all(item.status == "json_invalid" for item in adapter.last_generation_attempts)
    trace = _policy_trace_event(1, context, outcome, adapter)
    assert trace["structured_output_validation_stage"] == "provider_response_to_grounded_command"
    assert trace["structured_output_violations"] == (
        {
            "field_path": "decision.action.tool_name",
            "code": "missing_required_field",
        },
    )


def test_truncated_action_output_without_semantic_anchor_does_not_rechoose_operation() -> None:
    class TruncatedThenActionPort:
        provider = "deepseek"
        model = "deepseek-v4-flash"
        endpoint_class = "fixture"
        supports_multimodal = False
        supports_thinking_control = True

        def __init__(self):
            self.calls = 0
            self.configs = []
            self.last_call = None
            self.last_transcript = None

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del kwargs
            self.calls += 1
            self.configs.append(config)
            self.last_call = ModelCallRecord(
                provider=self.provider,
                model=self.model,
                endpoint_class=self.endpoint_class,
                prompt_version=config.prompt_version,
                schema_name=output_schema.__name__,
                schema_version="grounded_tools.v2",
                latency_ms=1,
                prompt_tokens=100,
                completion_tokens=config.max_tokens if self.calls == 1 else 12,
                total_tokens=100 + (config.max_tokens if self.calls == 1 else 12),
                response_id=f"response:{self.calls}",
                finish_reason="length" if self.calls == 1 else "stop",
                max_output_tokens=config.max_tokens,
                final_content_present=self.calls > 1,
                reasoning_content_present=self.calls == 1,
                response_fields=("message.content", "message.reasoning_content"),
            )
            self.last_transcript = {
                "status": "output_truncated" if self.calls == 1 else "accepted",
                "error.code": "output_truncated" if self.calls == 1 else "",
            }
            if self.calls == 1:
                raise StructuredOutputError(
                    "budget exhausted",
                    kind=StructuredOutputFailureKind.OUTPUT_TRUNCATED,
                    violations=(StructuredOutputViolation("$", "output_truncated"),),
                )
            assert messages[-1].role == "user"
            return output_schema.model_validate(
                {
                    "name": "activate",
                    "arguments": {"target": "E3"},
                }
            )

    context = _context()
    port = TruncatedThenActionPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(
            max_tokens=4_096,
            timeout_s=1,
            rate_limit_retries=0,
            transient_retries=0,
        ),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    instrumentation = BenchmarkInstrumentation()
    policy = CountingPolicy(
        ModelBackedAgentPolicy(
            CountingDecisionPort(adapter, instrumentation),
            call_timeout_s=2,
        ),
        instrumentation,
    )

    decision = asyncio.run(policy.decide(context))
    outcome = policy.wrapped.last_invocation_result

    assert isinstance(decision, ProtocolFeedback)
    assert outcome is not None and outcome.failure is None
    assert port.calls == 1
    assert instrumentation.policy_calls == 1
    assert instrumentation.provider_attempts == 1
    assert tuple(item.max_tokens for item in port.configs) == (1_024,)
    assert tuple(item.thinking_mode for item in port.configs) == ("disabled",)
    assert tuple(item.phase for item in outcome.attempts) == ("ordinary",)
    assert tuple(item.status for item in outcome.attempts) == ("output_truncated",)


def test_representation_repair_preserves_operation_and_semantic_target() -> None:
    class RepairablePort(_ActionPort):
        supports_thinking_control = True

        def __init__(self):
            super().__init__()
            self.configs = []
            self.last_transcript = None

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del kwargs
            self.calls += 1
            self.configs.append(config)
            if self.calls == 1:
                self.last_transcript = {
                    "llm.output_messages": [
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "name": "activate",
                                    "arguments": {"target": "E3"},
                                    "unexpected": True,
                                }
                            ),
                        }
                    ],
                }
                raise StructuredOutputError(
                    "extra field",
                    kind=StructuredOutputFailureKind.JSON_INVALID,
                    violations=(StructuredOutputViolation("unexpected", "extra_forbidden"),),
                )
            return output_schema.model_validate(
                {
                    "name": "activate",
                    "arguments": {"target": "E3"},
                }
            )

    adapter = CompactJsonDecisionPort(
        RepairablePort(),
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )
    outcome = asyncio.run(adapter.generate(_action_request(_context())))
    assert isinstance(outcome.output.decision, SelectAction)
    assert tuple(item.phase for item in outcome.attempts) == (
        "ordinary",
        "representation_repair",
    )
    assert tuple(item.trigger for item in outcome.attempts) == (
        "ordinary",
        "representation_error",
    )
    assert tuple(config.max_tokens for config in adapter.port.configs) == (1024, 512)
    assert tuple(config.thinking_mode for config in adapter.port.configs) == (
        "disabled",
        "disabled",
    )
    assert outcome.diagnostics["representation_repair_count"] == 1


def test_one_typed_recovery_event_uses_one_deliberate_provider_configuration() -> None:
    class ConfigPort(_ActionPort):
        supports_thinking_control = True

        def __init__(self):
            super().__init__()
            self.configs = []

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            self.configs.append(config)
            return await super().generate_structured(messages, output_schema, config, **kwargs)

    context = replace(
        _context(),
        control_feedback={
            "kind": "control_stall",
            "stable_signature": "recovery:synthetic-one",
            "recovery_attempt": 1,
        },
    )
    port = ConfigPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )
    first = asyncio.run(adapter.generate(_action_request(context)))
    second = asyncio.run(adapter.generate(_action_request(context)))
    assert tuple(config.max_tokens for config in port.configs) == (2048, 1024)
    assert tuple(config.thinking_mode for config in port.configs) == ("enabled", "disabled")
    assert first.attempts[0].phase == "deliberate"
    assert first.attempts[0].trigger == "control_stall"
    assert second.attempts[0].phase == "ordinary"
    assert second.attempts[0].trigger == "ordinary"


def test_exhausted_provider_retry_keeps_failure_attempt_observable() -> None:
    class FailedProviderPort:
        provider = "deepseek"
        model = "deepseek-v4-flash"
        endpoint_class = "remote"
        supports_multimodal = False
        supports_thinking_control = True
        last_call = None
        last_transcript = None

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config, kwargs
            self.last_transcript = {
                "status": "provider_failure",
                "error.code": "provider_capacity",
                "error.http_status": 503,
                "error.category": "http_5xx",
                "error.exception_class": "HTTPError",
                "error.latency_ms": 321.5,
                "network_dispatched": True,
                "network.physical_attempt_count": 2,
                "network.second_request_sent": True,
                "network.rate_limit_retry_count": 0,
                "network.transient_retry_count": 1,
            }
            raise ProviderModelError(
                ProviderFailureKind.PROVIDER_CAPACITY,
                http_status=503,
                error_category=ProviderTransportErrorCategory.HTTP_5XX,
                exception_class="HTTPError",
                latency_ms=321.5,
                physical_attempt_count=2,
                transient_retry_count=1,
            )

    context = _context()
    adapter = CompactJsonDecisionPort(
        FailedProviderPort(),
        ModelConfig(
            timeout_s=1,
            rate_limit_retries=1,
            transient_retries=1,
        ),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.output is None
    assert outcome.failure is not None
    assert outcome.failure.kind is ModelFailureKind.PROVIDER_UNAVAILABLE
    assert outcome.failure.retryable is True
    assert len(outcome.attempts) == 1
    attempt = outcome.attempts[0]
    assert attempt.status == "failed"
    assert attempt.role == "action_policy"
    assert attempt.phase == "ordinary"
    assert attempt.trigger == "ordinary"
    assert attempt.thinking_requested == "disabled"
    assert attempt.thinking_effective == "disabled"
    assert attempt.max_output_tokens == 1024
    assert attempt.latency_ms == 321.5
    assert attempt.exception_class == "HTTPError"
    assert attempt.transcript["error.http_status"] == 503
    assert attempt.transcript["network.second_request_sent"] is True
    assert attempt.transcript["llm.output.max_tokens"] == 1024
    assert outcome.metadata.latency_ms == 321.5
    assert outcome.metadata.transient_retry_count == 1
    assert outcome.diagnostics["provider_retry_count"] == 1
    assert outcome.diagnostics["provider_physical_attempt_count"] == 2


def test_timeout_fast_retry_uses_same_world_with_compact_disabled_thinking() -> None:
    class TimeoutThenActionPort:
        provider = "deepseek"
        model = "deepseek-v4-flash"
        endpoint_class = "remote"
        supports_multimodal = False
        supports_thinking_control = True
        last_call = None
        last_transcript = None

        def __init__(self) -> None:
            self.calls = 0
            self.configs: list[ModelConfig] = []
            self.messages = []

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del kwargs
            self.calls += 1
            self.configs.append(config)
            self.messages.append(messages)
            if self.calls == 1:
                self.last_transcript = {
                    "status": "provider_failure",
                    "error.code": "provider_capacity",
                    "error.category": "timeout",
                    "error.exception_class": "TimeoutError",
                    "network.physical_attempt_count": 1,
                    "network.second_request_sent": False,
                    "network.rate_limit_retry_count": 0,
                    "network.transient_retry_count": 0,
                }
                raise ProviderModelError(
                    ProviderFailureKind.PROVIDER_CAPACITY,
                    error_category=ProviderTransportErrorCategory.TIMEOUT,
                    exception_class="TimeoutError",
                    latency_ms=55_000,
                    physical_attempt_count=1,
                )
            self.last_call = ModelCallRecord(
                provider=self.provider,
                model=self.model,
                endpoint_class=self.endpoint_class,
                prompt_version=config.prompt_version,
                schema_name=output_schema.__name__,
                schema_version="grounded_tools.v2",
                latency_ms=1_000,
                max_output_tokens=config.max_tokens,
                final_content_present=True,
            )
            self.last_transcript = {
                "status": "accepted",
                "network.physical_attempt_count": 1,
                "network.second_request_sent": False,
                "network.rate_limit_retry_count": 0,
                "network.transient_retry_count": 0,
            }
            return output_schema.model_validate(
                {
                    "name": "activate",
                    "arguments": {"target": "E3"},
                }
            )

    context = _context()
    port = TimeoutThenActionPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(
            max_tokens=4_096,
            timeout_s=55,
            provider_total_timeout_s=55,
            rate_limit_retries=1,
            transient_retries=1,
            timeout_retries=0,
        ),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        timeout_fast_retry_timeout_s=33,
        timeout_fast_retry_max_tokens=512,
        timeout_fast_retry_thinking_mode="disabled",
        semantic_call_deadline_s=89,
    )

    instrumentation = BenchmarkInstrumentation()
    policy = CountingPolicy(
        ModelBackedAgentPolicy(
            CountingDecisionPort(adapter, instrumentation),
            call_timeout_s=90,
        ),
        instrumentation,
    )

    decision = asyncio.run(policy.decide(context))
    outcome = policy.wrapped.last_invocation_result

    assert isinstance(decision, SelectAction)
    assert outcome is not None and outcome.failure is None
    assert port.calls == 2
    assert instrumentation.policy_calls == 1
    assert instrumentation.provider_attempts == 2
    assert instrumentation.provider_retry_count == 1
    assert port.messages[1][:-1] == port.messages[0]
    assert "same current World" in port.messages[1][-1].content
    assert tuple(item.max_tokens for item in port.configs) == (1_024, 512)
    assert tuple(item.timeout_s for item in port.configs) == (55, 33)
    assert tuple(item.thinking_mode for item in port.configs) == ("disabled", "disabled")
    assert tuple(item.timeout_retries for item in port.configs) == (0, 0)
    assert tuple(item.phase for item in outcome.attempts) == ("ordinary", "ordinary")
    assert tuple(item.trigger for item in outcome.attempts) == (
        "ordinary",
        "transport_timeout_retry",
    )
    assert outcome.diagnostics["timeout_fast_retry_count"] == 1
    assert outcome.diagnostics["provider_retry_count"] == 1
    assert outcome.diagnostics["provider_physical_attempt_count"] == 2


def test_exhausted_timeout_fast_retry_projects_provider_timeout() -> None:
    class AlwaysTimeoutPort:
        provider = "deepseek"
        model = "deepseek-v4-flash"
        endpoint_class = "remote"
        supports_multimodal = False
        supports_thinking_control = True
        last_call = None
        last_transcript = None

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, config, kwargs
            self.last_transcript = {
                "status": "provider_failure",
                "error.code": "provider_capacity",
                "error.category": "timeout",
                "error.exception_class": "TimeoutError",
                "network.physical_attempt_count": 1,
                "network.second_request_sent": False,
                "network.rate_limit_retry_count": 0,
                "network.transient_retry_count": 0,
            }
            raise ProviderModelError(
                ProviderFailureKind.PROVIDER_CAPACITY,
                error_category=ProviderTransportErrorCategory.TIMEOUT,
                exception_class="TimeoutError",
                latency_ms=33_000,
                physical_attempt_count=1,
            )

    adapter = CompactJsonDecisionPort(
        AlwaysTimeoutPort(),
        ModelConfig(
            timeout_s=55,
            provider_total_timeout_s=55,
            rate_limit_retries=1,
            transient_retries=1,
            timeout_retries=0,
        ),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
        timeout_fast_retry_timeout_s=33,
        semantic_call_deadline_s=89,
    )

    outcome = asyncio.run(adapter.generate(_action_request(_context())))

    assert outcome.output is None
    assert outcome.failure is not None
    assert outcome.failure.kind is ModelFailureKind.TIMEOUT
    assert outcome.failure.provider_code.value == "timeout"
    assert tuple(item.phase for item in outcome.attempts) == ("ordinary", "ordinary")
    assert outcome.diagnostics["provider_retry_count"] == 1
    assert outcome.diagnostics["provider_physical_attempt_count"] == 2


@pytest.mark.parametrize(
    ("failure_kind", "expected_calls"),
    (
        (StructuredOutputFailureKind.OUTPUT_TRUNCATED, 1),
        (StructuredOutputFailureKind.EMPTY_FINAL_CONTENT, 1),
        (StructuredOutputFailureKind.JSON_INVALID, 1),
    ),
)
def test_action_output_failure_categories_preserve_feedback_and_retry_boundary(
    failure_kind: StructuredOutputFailureKind,
    expected_calls: int,
) -> None:
    class FailedOutputPort(_ActionPort):
        supports_thinking_control = True

        async def generate_structured(self, messages, output_schema, config, **kwargs):
            del messages, output_schema, kwargs
            self.calls += 1
            self.last_call = ModelCallRecord(
                provider=self.provider,
                model=self.model,
                endpoint_class=self.endpoint_class,
                prompt_version=config.prompt_version,
                schema_name="GroundedToolCommandPayload",
                schema_version="grounded_tools.v2",
                latency_ms=1,
                completion_tokens=config.max_tokens,
                total_tokens=config.max_tokens,
                finish_reason=("length" if failure_kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED else "stop"),
                max_output_tokens=config.max_tokens,
                final_content_present=(failure_kind is StructuredOutputFailureKind.JSON_INVALID),
            )
            raise StructuredOutputError(
                failure_kind.value,
                kind=failure_kind,
                violations=(StructuredOutputViolation("$", failure_kind.value),),
            )

    context = _context()
    port = FailedOutputPort()
    adapter = CompactJsonDecisionPort(
        port,
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        perception_profile=DecisionPerceptionProfile.STRUCTURE_FIRST,
    )

    outcome = asyncio.run(adapter.generate(_action_request(context)))

    assert outcome.failure is None
    assert isinstance(outcome.output.decision, ProtocolFeedback)
    assert outcome.output.decision.feedback_kind.value == failure_kind.value
    assert outcome.output.decision.detail == failure_kind.value
    assert port.calls == expected_calls
    assert adapter.last_model_call_count == expected_calls


def test_aria_hidden_ancestor_removes_layout_only_control_from_execution_visibility() -> None:
    assert _effective_visibility(True, {"ariaHiddenByAncestor": True}) is False
    assert _effective_visibility(True, {"ariaHiddenByAncestor": False}) is True
