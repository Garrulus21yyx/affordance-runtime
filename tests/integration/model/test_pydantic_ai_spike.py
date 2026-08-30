from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Mapping
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

pytest.importorskip("pydantic_ai")

from pydantic_ai import DeferredToolRequests, ToolDefinition
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.usage import RequestUsage

import affordance_runtime.model.policy.canonical_provider_envelope as canonical_envelope_module
import affordance_runtime.model.policy.pydantic_ai_bridge as pydantic_bridge
import affordance_runtime.model.policy.request_admission as request_admission_module
import affordance_runtime.model.policy.turn_packer as turn_packer_module
from affordance_runtime.actions import ActionBinding, ActionRisk, ActionSpace, ActionSpaceBuilder
from affordance_runtime.actions.schema_validation import (
    validate_parameter_schema_contract,
    validate_value,
)
from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.action_candidate_projection import (
    ActionRouteFragment,
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.contracts import (
    HISTORY_ARGUMENT_PATHS_METADATA_KEY,
    HISTORY_RETURN_PATHS_METADATA_KEY,
    sanitize_history_arguments,
    sanitize_history_value,
)
from affordance_runtime.agent.context.failures import ModelFailureKind, ProviderAttemptOrigin
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.observation_delivery import ObservationDeliveryStore
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.decisions import (
    FinalResponse,
    ReadRegionResult,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
)
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.policy import AgentDecisionPorts, PolicyFailure
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.benchmarks.webarena_verified import WebArenaVerifiedFinalResponseCodec
from affordance_runtime.evaluation import (
    ActionOutcome,
    EvaluatedOutput,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.factory import model_policy_from_environment
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    resolve_grounded_action_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
    ObservationToolExposureProfile,
)
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.prompt import (
    MODEL_POLICY_EVIDENCE_STATUS,
    MODEL_POLICY_INSTRUCTIONS,
)
from affordance_runtime.model.policy.provider_call_normalizer import (
    ToolCallReconciliationResult,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.pydantic_ai_bridge import (
    PydanticAIGroundedDecisionPort,
    pydantic_ai_model_from_environment,
    zhipu_pydantic_ai_policy_from_environment,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBreakdown,
    ModelRequestCapacityError,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model.providers.port import StructuredOutputFailureKind
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationCapabilities,
    ObservationOffer,
    ObservationPurpose,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.agent.core_loop_support import (
    SharedActionOutcomeProjector,
    SharedTaskEvaluator,
    shared_task,
    shared_world,
)
from tests.support.model.recording_pydantic_model import (
    RecordingPydanticModel,
    normalize_recorded_provider_input,
)

ScriptedModel = RecordingPydanticModel


def _history_response(
    parts: list[object] | tuple[object, ...],
    paths_by_call: Mapping[str, tuple[tuple[str, ...], ...]],
) -> ModelResponse:
    return ModelResponse(
        parts=parts,
        metadata={HISTORY_ARGUMENT_PATHS_METADATA_KEY: dict(paths_by_call)},
    )


def _history_return(
    tool_name: str,
    content: object,
    call_id: str,
    *,
    ephemeral_paths: tuple[tuple[str, ...], ...] = (),
    metadata: Mapping[str, object] | None = None,
) -> ToolReturnPart:
    return ToolReturnPart(
        tool_name,
        content,
        call_id,
        metadata={
            **dict(metadata or {}),
            HISTORY_RETURN_PATHS_METADATA_KEY: ephemeral_paths,
        },
    )


def _serve_openai_chat_responses(
    responses: tuple[dict[str, object], ...],
) -> tuple[ThreadingHTTPServer, threading.Thread, list[dict[str, object]]]:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
            payload = json.dumps(responses[len(requests) - 1]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, requests


def _deepseek_tool_response(
    ordinal: int,
    *,
    reasoning: str,
) -> dict[str, object]:
    return {
        "id": f"deepseek-response:{ordinal}",
        "object": "chat.completion",
        "created": ordinal,
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": reasoning,
                    "tool_calls": [
                        {
                            "id": f"deepseek-call:{ordinal}",
                            "type": "function",
                            "function": {"name": "act", "arguments": "{}"},
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 8 + 2 * ordinal,
            "completion_tokens": 4,
            "total_tokens": 12 + 2 * ordinal,
        },
    }


def _deepseek_text_response(
    ordinal: int,
    *,
    reasoning: str,
    content: str,
) -> dict[str, object]:
    return {
        "id": f"deepseek-response:{ordinal}",
        "object": "chat.completion",
        "created": ordinal,
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 8 + 2 * ordinal,
            "completion_tokens": 4,
            "total_tokens": 12 + 2 * ordinal,
        },
    }


def _progress_text(
    *,
    verified_facts: tuple[str, ...] = (),
    working_hypotheses: tuple[str, ...] = (),
    remaining_requirements: tuple[str, ...] = (),
    next_intent: str,
    avoid_repeating: tuple[str, ...] = (),
) -> str:
    return json.dumps(
        {
            "verified_facts": verified_facts,
            "working_hypotheses": working_hypotheses,
            "remaining_requirements": remaining_requirements,
            "next_intent": next_intent,
            "avoid_repeating": avoid_repeating,
        },
        sort_keys=True,
    )


def _policy(model) -> ModelBackedAgentPolicy:
    port = PydanticAIGroundedDecisionPort(
        model=model,
        provider_id="fixture",
        model_id="scripted",
        endpoint_host="fixture.invalid",
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
        transport_timeout_s=4.0,
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=5.0)


def test_deepseek_deliberate_thinking_uses_official_wire_and_roundtrips_tool_reasoning() -> None:
    responses = (
        _deepseek_tool_response(
            1,
            reasoning="The current route is exhausted; choose another source.",
        ),
        _deepseek_tool_response(
            2,
            reasoning="The alternative source is now active.",
        ),
    )
    server, thread, requests = _serve_openai_chat_responses(responses)

    async def scenario() -> None:
        configured = pydantic_ai_model_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "deepseek",
                "LLM_DEEPSEEK_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "LLM_DEEPSEEK_API_KEY": "test-secret",
                "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
            },
            call_timeout_s=10.0,
        )
        parameters = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="act",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    strict=True,
                )
            ],
            allow_text_output=True,
        )
        first_request = ModelRequest(parts=[UserPromptPart("Recover with one action.")])
        first = await configured.model.request(
            [first_request],
            {"thinking": True, "max_tokens": 64, "tool_choice": "auto"},
            parameters,
        )
        first_thinking = next(part for part in first.parts if isinstance(part, ThinkingPart))
        first_call = next(part for part in first.parts if isinstance(part, ToolCallPart))
        assert first_thinking.content == "The current route is exhausted; choose another source."
        assert first_call.tool_call_id == "deepseek-call:1"

        tool_return = ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="act",
                    content={"status": "complete"},
                    tool_call_id=first_call.tool_call_id,
                )
            ]
        )
        second = await configured.model.request(
            [first_request, first, tool_return],
            {"thinking": True, "max_tokens": 64, "tool_choice": "auto"},
            parameters,
        )
        assert any(isinstance(part, ThinkingPart) for part in second.parts)
        assert any(isinstance(part, ToolCallPart) for part in second.parts)

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(requests) == 2
    assert requests[0]["reasoning_effort"] == "medium"
    assert requests[1]["reasoning_effort"] == "medium"
    replayed_assistant = requests[1]["messages"][1]
    assert replayed_assistant["reasoning_content"] == ("The current route is exhausted; choose another source.")
    assert replayed_assistant["tool_calls"][0]["id"] == "deepseek-call:1"
    assert requests[1]["messages"][2] == {
        "role": "tool",
        "tool_call_id": "deepseek-call:1",
        "content": '{"status":"complete"}',
    }


def test_deepseek_deliberate_output_retry_disables_thinking_before_requiring_a_tool() -> None:
    responses = (
        _deepseek_text_response(
            1,
            reasoning="The stalled route needs reconsideration.",
            content="I should act on the current World.",
        ),
        {
            **_deepseek_tool_response(2, reasoning=""),
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "deepseek-call:2",
                                "type": "function",
                                "function": {"name": "list_regions", "arguments": "{}"},
                            }
                        ],
                    },
                }
            ],
        },
    )
    server, thread, requests = _serve_openai_chat_responses(responses)

    async def scenario() -> None:
        policy = model_policy_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "deepseek",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "LLM_DEEPSEEK_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "LLM_DEEPSEEK_API_KEY": "test-secret",
                "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
                "LLM_DECISION_PERCEPTION": "text-only.v1",
            },
            call_timeout_s=10.0,
        )
        task = shared_task()
        world = shared_world("deepseek-deliberate-retry-wire", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "deepseek:retry:wire",
                "recovery_attempt": 1,
            },
        )

        result = await policy.port.generate(ModelDecisionRequest("request:deepseek-retry-wire", context))

        assert result.failure is None and result.output is not None
        assert result.output.decision.tool_call_id == "deepseek-call:2"
        assert [attempt.thinking_effective for attempt in result.attempts] == ["enabled", "disabled"]

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(requests) == 2
    assert requests[0]["tool_choice"] == "auto"
    assert requests[0]["reasoning_effort"] == "medium"
    assert requests[1]["tool_choice"] == "required"
    assert requests[1].get("reasoning_effort") == "none"


def test_deepseek_deliberate_length_fallback_uses_same_world_and_required_tool_wire() -> None:
    responses = (
        {
            "id": "deepseek-response:length",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "The stalled route needs a different current action.",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2048,
                "total_tokens": 2058,
                "completion_tokens_details": {"reasoning_tokens": 2048},
            },
        },
        {
            **_deepseek_tool_response(2, reasoning=""),
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "deepseek-call:length-fallback",
                                "type": "function",
                                "function": {"name": "list_regions", "arguments": "{}"},
                            }
                        ],
                    },
                }
            ],
        },
    )
    server, thread, requests = _serve_openai_chat_responses(responses)

    async def scenario() -> None:
        policy = model_policy_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "deepseek",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "LLM_DEEPSEEK_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "LLM_DEEPSEEK_API_KEY": "test-secret",
                "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
                "LLM_DECISION_PERCEPTION": "text-only.v1",
            },
            call_timeout_s=10.0,
        )
        task = shared_task()
        world = shared_world("deepseek-deliberate-length-wire", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "deepseek:length:wire",
                "recovery_attempt": 1,
            },
        )

        result = await policy.port.generate(ModelDecisionRequest("request:deepseek-length-wire", context))

        assert result.failure is None and result.output is not None
        assert result.output.decision.tool_call_id == "deepseek-call:length-fallback"
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert [attempt.output_failure_kind for attempt in result.attempts] == [
            StructuredOutputFailureKind.OUTPUT_TRUNCATED,
            None,
        ]
        assert [attempt.thinking_effective for attempt in result.attempts] == ["enabled", "disabled"]
        assert [attempt.final_tool_call_present for attempt in result.attempts] == [False, True]
        assert len(policy.port.last_admitted_envelopes) == 1
        assert policy.port.last_model_delivery.action_candidates.world_observation_id == world.observation_id

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(requests) == 2
    assert requests[0]["tool_choice"] == "auto"
    assert requests[0]["reasoning_effort"] == "medium"
    assert requests[1]["tool_choice"] == "required"
    assert requests[1].get("reasoning_effort") == "none"
    assert requests[0]["messages"][0] == requests[1]["messages"][0]
    fallback_content = requests[1]["messages"][1]["content"]
    assert isinstance(fallback_content, list)
    fallback_text = "\n".join(str(item.get("text", "")) for item in fallback_content if isinstance(item, dict))
    assert requests[0]["messages"][1]["content"] in fallback_text
    assert "action_selection_recovery" in fallback_text
    assert "return exactly one complete offered tool call" in fallback_text
    assert "Complete any unfinished enumeration, classification, or record audit" in fallback_text
    assert "the truncation boundary never completes a set" in fallback_text


async def _bound_envelope_for_port(port: PydanticAIGroundedDecisionPort, request_id: str):
    task = shared_task()
    world = shared_world(request_id, False)
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        await SharedTaskEvaluator().evaluate(task, world),
    )
    profile = port.reasoning_policy.select(context)
    return (
        turn_packer_module.TurnPacker()
        .pack(
            ModelDecisionRequest(f"request:{request_id}", context),
            binder=port.envelope_binder,
            identity=pydantic_bridge.CanonicalProviderIdentity(
                port.provider_id,
                port.model_id,
                port.endpoint_host,
                port.perception_profile.value,
            ),
            call_profile=profile,
            supports_multimodal=False,
            perception_profile=port.perception_profile,
        )
        .admitted_envelope.envelope
    )


def _runtime(model) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(_policy(model)),
        SharedActionOutcomeProjector(),
        SharedTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
    )


def test_schema_valid_grounding_rejection_returns_on_same_call_before_next_policy() -> None:
    async def scenario() -> None:
        task = replace(
            shared_task(),
            allowed_effects=("shared_state_enabled", "query_changed"),
        )
        button = SemanticTarget("shared-toggle", "button", "Enable shared state", {"enabled": False})
        textbox = SemanticTarget("query", "textbox", "Search", {"focused": True})
        observation_id = "grounding-rejection"
        source = SurfaceObservation(
            observation_id,
            "dom",
            "revision:grounding-rejection",
            ObservationSourceProfile.dom(),
            (button, textbox),
            (StateFact("fact:grounding-rejection:enabled", button.target_id, "enabled", False, observation_id),),
            (
                ActionBinding(
                    "binding:grounding-rejection:button",
                    observation_id,
                    observation_id,
                    "revision:grounding-rejection",
                    "fingerprint:button",
                    button.target_id,
                    button.target_id,
                    "dom",
                    "dom",
                    "activate",
                    "click",
                    "local_reversible",
                    ("shared_state_enabled",),
                    {"type": "object", "properties": {}, "additionalProperties": False},
                    {"selector": "#shared"},
                    risk=ActionRisk.LOW,
                ),
                ActionBinding(
                    "binding:grounding-rejection:textbox",
                    observation_id,
                    observation_id,
                    "revision:grounding-rejection",
                    "fingerprint:textbox",
                    textbox.target_id,
                    textbox.target_id,
                    "dom",
                    "dom",
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
                    {"selector": "#query"},
                    risk=ActionRisk.LOW,
                ),
                ActionBinding(
                    "binding:grounding-rejection:textbox-key",
                    observation_id,
                    observation_id,
                    "revision:grounding-rejection",
                    "fingerprint:textbox",
                    textbox.target_id,
                    textbox.target_id,
                    "dom",
                    "dom",
                    "press_key",
                    "press",
                    "local_reversible",
                    ("query_changed",),
                    {
                        "type": "object",
                        "properties": {"key": {"type": "string", "enum": ["ENTER"]}},
                        "required": ["key"],
                        "additionalProperties": False,
                    },
                    {"selector": "#query"},
                    risk=ActionRisk.LOW,
                ),
            ),
        )
        fused = WorldFusion().fuse((source,))
        assert fused.observation is not None
        world = fused.observation
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        refs = context.grounding.target_refs
        textbox_ref = refs[textbox.target_id]
        subject_lines = tuple(
            line
            for line in build_model_turn_delivery(context, include_images=False).view.text.splitlines()
            if f"[{textbox_ref}]" in line and line.lstrip().startswith("rank=")
        )
        assert len(subject_lines) == 1
        assert '"press_key"' in subject_lines[0]
        assert '"type_text"' in subject_lines[0]
        plan = context.action_delivery_plan
        assert plan is not None
        base = plan.obligation(DeliveryObligationKind.BASE_ACTIONS)
        interaction = plan.obligation(DeliveryObligationKind.INTERACTION)
        assert base is not None and interaction is not None
        base_refs = {item.candidate.target_ref for item in base.records if isinstance(item, ActionRouteFragment)}
        interaction_refs = {
            item.candidate.target_ref for item in interaction.records if isinstance(item, ActionRouteFragment)
        }
        assert base_refs.isdisjoint(interaction_refs)
        delivery = build_model_turn_delivery(context, include_images=False)
        catalog = compile_grounded_action_catalog(context, delivery)
        type_text_spec = next(item for item in catalog.specs if item.name == "type_text")
        assert "Replace the editable value" in type_text_spec.description
        assert "An empty string clears the value" in type_text_spec.description
        with pytest.raises(GroundedToolResolutionError) as direct_rejection:
            resolve_grounded_action_call(
                catalog,
                ToolCall("activate", {"target": textbox_ref}, "call:direct"),
                expected_context_id=context.context_id,
                expected_delivery_id=delivery.delivery_id,
                expected_catalog_id=catalog.catalog_id,
            )
        assert direct_rejection.value.code is GroundedToolResolutionCode.GROUNDING_GAP
        scripted = ScriptedModel(
            [
                ("activate", {"target": textbox_ref}),
                ("activate", {"target": refs[button.target_id]}),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:grounding-rejection:1", context))

        assert first.failure is None and first.output is not None, (
            first.failure,
            policy.port.last_tool_resolution_code,
            policy.port.last_tool_resolution_detail,
            scripted.calls,
        )
        rejected = first.output.decision
        assert isinstance(rejected, ToolRejectedResult)
        assert rejected.tool_call_id == "recording-call:1"
        assert rejected.result["kind"] == "operation_mismatch"
        assert rejected.result["attempted_operation"] == "activate"
        assert set(rejected.result["supported_operations"]) == {"press_key", "type_text"}
        assert rejected.result["dispatch"] == "not_sent"
        assert scripted.calls == 1

        committed = StepResult(
            rejected,
            world,
            world,
            evaluation,
            RunStatus.RUNNING,
            feedback="local_tool_result",
        )
        second = await policy.port.generate(ModelDecisionRequest("request:grounding-rejection:2", context, committed))

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, SelectAction)
        assert scripted.calls == 2
        normalized = normalize_recorded_provider_input(scripted.records[1])
        returns = tuple(
            part
            for message in normalized["messages"]
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        )
        assert len(returns) == 1
        assert returns[0]["tool_name"] == "activate"
        assert returns[0]["tool_call_id"] == "recording-call:1"
        assert returns[0]["content"]["kind"] == "operation_mismatch"
        assert set(returns[0]["content"]["supported_operations"]) == {"press_key", "type_text"}

    asyncio.run(scenario())


def test_pydantic_ai_checkpoint_contains_only_official_message_history() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    history = (
        ModelRequest(parts=[UserPromptPart("current task")]),
        _history_response(
            [ToolCallPart("type_text", {"target": "E1", "text": "E6"}, "call:checkpoint")],
            {"call:checkpoint": (("target",),)},
        ),
        ModelRequest(
            parts=[
                _history_return(
                    "type_text",
                    {
                        "entered_text": "E6",
                        "target_ref": "E1",
                        "region_ref": "R2",
                        "status": "paused",
                    },
                    "call:checkpoint",
                    ephemeral_paths=(("target_ref",), ("region_ref",)),
                )
            ]
        ),
    )
    object.__setattr__(policy.port, "message_history", history)
    object.__setattr__(policy.port, "active_task_identity", ("task:checkpoint", 3))
    serialized = policy.export_checkpoint_history()
    canonical_history = policy.port.message_history

    assert serialized["format"] == "pydantic-ai.messages.v1"
    assert serialized["active_task_identity"] == ["task:checkpoint", 3]
    assert "strategy_revision" not in serialized
    assert [message["kind"] for message in serialized["messages"]] == ["response", "request"]

    restored = _policy(ScriptedModel(["first_gui_action"]).build())
    restored.restore_checkpoint_history(
        serialized,
        task_id="task:checkpoint",
        task_revision=3,
    )
    assert canonical_history != history
    closed_call = canonical_history[0]
    assert isinstance(closed_call, ModelResponse)
    assert tuple(part.args for part in closed_call.parts if isinstance(part, ToolCallPart)) == ({"text": "E6"},)
    closed_return = canonical_history[1]
    assert isinstance(closed_return, ModelRequest)
    assert tuple(part.content for part in closed_return.parts if isinstance(part, ToolReturnPart)) == (
        {"entered_text": "E6", "status": "paused"},
    )
    assert "E1" not in json.dumps(serialized)
    assert "R2" not in json.dumps(serialized)
    assert "E6" in json.dumps(serialized)
    assert ModelMessagesTypeAdapter.dump_json(
        list(restored.port.message_history)
    ) == ModelMessagesTypeAdapter.dump_json(list(canonical_history))
    assert restored.port.active_task_identity == ("task:checkpoint", 3)

    from affordance_runtime.immutable import freeze_json

    frozen = freeze_json(serialized)
    restored_from_checkpoint = _policy(ScriptedModel(["first_gui_action"]).build())
    restored_from_checkpoint.restore_checkpoint_history(
        frozen,
        task_id="task:checkpoint",
        task_revision=3,
    )
    assert ModelMessagesTypeAdapter.dump_json(
        list(restored_from_checkpoint.port.message_history)
    ) == ModelMessagesTypeAdapter.dump_json(list(canonical_history))
    assert "strategy_revision" not in restored_from_checkpoint.export_checkpoint_history()


def test_settled_checkpoint_removes_old_world_refs_and_media_but_keeps_task_anchor() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    current_turn = ModelRequest(
        parts=[
            UserPromptPart(
                [
                    '{"observation":"[E1] Product code R5 in region R2"}',
                    BinaryContent(b"old screenshot bytes", media_type="image/png"),
                ]
            )
        ]
    )
    history = (
        current_turn,
        _history_response(
            [ToolCallPart("activate", {"target": "E1"}, "call:settled-world")],
            {"call:settled-world": (("target",),)},
        ),
        ModelRequest(parts=[_history_return("activate", {"status": "stable"}, "call:settled-world")]),
    )
    normalized = pydantic_bridge._normalize_pydantic_history_for_current_task(
        history,
        task_plan={"task": {"instruction": "Use product code R5"}, "goal_plan": {"items": []}},
    )
    object.__setattr__(policy.port, "message_history", normalized)
    object.__setattr__(policy.port, "active_task_identity", ("task:settled-world", 1))

    checkpoint = policy.export_checkpoint_history()
    encoded = json.dumps(checkpoint, sort_keys=True)

    assert "Use product code R5" in encoded
    assert "old screenshot bytes" not in encoded
    assert "E1" not in encoded
    assert "R2" not in encoded
    assert encoded.count("R5") == 1
    assert not any(part.get("part_kind") == "binary" for message in checkpoint["messages"] for part in message["parts"])


def test_task_anchor_rejects_fresh_formal_evaluation_evidence() -> None:
    with pytest.raises(ValueError, match="revision-stable TaskGoal"):
        pydantic_bridge._normalize_pydantic_history_for_current_task(
            (ModelRequest(parts=[UserPromptPart('{"observation":"fresh"}')]),),
            task_plan={
                "task": {
                    "instruction": "Inspect status",
                    "formal_evaluation": {
                        "evidence": ({"evidence_ref": "F1", "field": "ready", "value": True},),
                    },
                },
                "goal_plan": {"items": ()},
            },
        )


def test_pydantic_ai_checkpoint_history_uses_settled_step_persistence_reference(
    tmp_path,
) -> None:
    async def scenario() -> None:
        step_persistence = pytest.importorskip("pydantic_ai_harness.step_persistence")
        database = tmp_path / "model-steps.sqlite3"
        store = step_persistence.SqliteStepStore(database=database)
        policy = _policy(ScriptedModel(["first_gui_action"]).build())
        object.__setattr__(policy.port, "step_store", store)
        object.__setattr__(policy.port, "step_conversation_id", "session:checkpoint")
        history = (
            ModelRequest(parts=[UserPromptPart("current task")]),
            _history_response(
                [ToolCallPart("activate", {"target": "E1"}, "call:settled")],
                {"call:settled": (("target",),)},
            ),
            ModelRequest(parts=[_history_return("activate", {"status": "paused"}, "call:settled")]),
        )
        object.__setattr__(policy.port, "message_history", history)
        object.__setattr__(policy.port, "active_task_identity", ("task:checkpoint", 3))

        reference = await policy.persist_checkpoint_history()
        canonical_history = policy.port.message_history

        assert reference["format"] == "pydantic-ai.step-persistence.v1"
        assert reference["conversation_id"] == "session:checkpoint"
        assert "messages" not in reference
        snapshot = await store.latest_snapshot(run_id=reference["run_id"])
        assert snapshot is not None
        assert snapshot.state == "complete"
        assert canonical_history != history
        assert ModelMessagesTypeAdapter.dump_json(snapshot.messages) == ModelMessagesTypeAdapter.dump_json(
            list(canonical_history)
        )

        restored = _policy(ScriptedModel(["first_gui_action"]).build())
        restarted_store = step_persistence.SqliteStepStore(database=database)
        object.__setattr__(restored.port, "step_store", restarted_store)
        object.__setattr__(
            restored.port,
            "step_conversation_id",
            "session:checkpoint",
        )
        await restored.restore_persisted_checkpoint_history(
            reference,
            task_id="task:checkpoint",
            task_revision=3,
        )
        assert ModelMessagesTypeAdapter.dump_json(
            list(restored.port.message_history)
        ) == ModelMessagesTypeAdapter.dump_json(list(canonical_history))

        tampered = {**reference, "message_digest": "f" * 64}
        with pytest.raises(ValueError, match="digest"):
            await restored.restore_persisted_checkpoint_history(
                tampered,
                task_id="task:checkpoint",
                task_revision=3,
            )

    asyncio.run(scenario())


def test_pydantic_ai_empty_history_binds_and_restores_before_first_policy(
    tmp_path,
) -> None:
    async def scenario() -> None:
        step_persistence = pytest.importorskip("pydantic_ai_harness.step_persistence")
        database = tmp_path / "empty-model-steps.sqlite3"
        store = step_persistence.SqliteStepStore(database=database)
        policy = _policy(ScriptedModel(["first_gui_action"]).build())
        object.__setattr__(policy.port, "step_store", store)
        object.__setattr__(policy.port, "step_conversation_id", "session:empty")

        policy.bind_checkpoint_history_identity(
            task_id="task:empty",
            task_revision=1,
        )
        reference = await policy.persist_checkpoint_history()

        assert policy.port.message_history == ()
        snapshot = await store.latest_snapshot(run_id=reference["run_id"])
        assert snapshot is not None
        assert snapshot.state == "complete"
        assert snapshot.messages == []

        restored = _policy(ScriptedModel(["first_gui_action"]).build())
        object.__setattr__(
            restored.port,
            "step_store",
            step_persistence.SqliteStepStore(database=database),
        )
        object.__setattr__(
            restored.port,
            "step_conversation_id",
            "session:empty",
        )
        await restored.restore_persisted_checkpoint_history(
            reference,
            task_id="task:empty",
            task_revision=1,
        )
        assert restored.port.message_history == ()
        assert restored.port.active_task_identity == ("task:empty", 1)

    asyncio.run(scenario())


def test_pydantic_ai_checkpoint_history_rejects_unclosed_tool_call() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    object.__setattr__(
        policy.port,
        "message_history",
        (ModelResponse(parts=[ToolCallPart("activate", {"target": "E1"}, "call:checkpoint")]),),
    )

    with pytest.raises(ValueError, match="unclosed tool call"):
        policy.export_checkpoint_history()


def test_pydantic_ai_checkpoint_history_starts_empty_at_one_revised_task() -> None:
    policy = _policy(ScriptedModel(["first_gui_action"]).build())
    history = (
        ModelRequest(parts=[UserPromptPart("current task")]),
        _history_response(
            [ToolCallPart("activate", {"target": "E1"}, "call:revision")],
            {"call:revision": (("target",),)},
        ),
        ModelRequest(parts=[_history_return("activate", {"status": "paused"}, "call:revision")]),
    )
    object.__setattr__(policy.port, "message_history", history)
    object.__setattr__(policy.port, "active_task_identity", ("task:checkpoint", 3))
    object.__setattr__(policy.port, "last_step_run_id", "old-revision-run")

    policy.rebind_checkpoint_history(
        task_id="task:checkpoint",
        current_revision=3,
        revised_revision=4,
    )

    assert policy.port.message_history == ()
    assert policy.port.last_step_run_id == ""
    checkpoint = policy.export_checkpoint_history()
    assert checkpoint["messages"] == []
    assert checkpoint["active_task_identity"] == ["task:checkpoint", 4]
    with pytest.raises(ValueError, match="consecutive"):
        policy.rebind_checkpoint_history(
            task_id="task:checkpoint",
            current_revision=4,
            revised_revision=6,
        )


def test_pydantic_ai_decision_executes_one_action_then_runtime_auto_completes() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert state.execution_count == 1
        assert scripted.calls == 1
        # FunctionModel strips unsupported thinking while preserving the
        # transport-level single-call prohibition and output/sampling budget.
        assert scripted.model_settings == [
            {
                "max_tokens": 1024,
                "temperature": 0.0,
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "timeout": 4.0,
            }
        ]
        assert dict(policy.port.last_admitted_envelopes[0].model_settings) == {
            "max_tokens": 1024,
            "temperature": 0.0,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "timeout": 4.0,
        }
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "recording-call:1"
        assert "ask_user" in scripted.offered_tools[0]
        assert "propose_done" not in scripted.offered_tools[0]
        attempt = policy.port.last_generation_attempts[0]
        assert attempt.phase == "ordinary"
        assert attempt.role == "action_policy"
        assert attempt.trigger == "ordinary"
        assert attempt.thinking_requested == "disabled"
        assert attempt.thinking_effective == "disabled"
        assert attempt.max_output_tokens == 1024
        assert attempt.final_tool_call_present is True
        assert attempt.final_content_tokens == attempt.completion_tokens
        assert attempt.transcript["llm.input_messages"][0]["parts"][0]["content"]
        assert attempt.transcript["llm.output_messages"][0]["parts"][0]["tool_name"]
        assert policy.last_metadata is not None
        assert policy.last_metadata.latency_ms >= attempt.latency_ms > 0

    asyncio.run(scenario())


def test_next_provider_request_closes_gui_call_with_effect_and_recent_trajectory() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                "first_gui_action",
                ("abort", {"reason": "effect observed", "category": "user_request"}),
            ]
        )
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("effect-before", False),
            post_observations=(shared_world("effect-after", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("working_outcome_delivery_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.CANCELLED
        assert state.execution_count == 1
        assert scripted.calls == 2
        recorded = normalize_recorded_provider_input(scripted.records[1])
        parts = tuple(part for message in recorded["messages"] for part in message["parts"])
        tool_call = next(part for part in parts if part["part_kind"] == "tool-call")
        tool_return = next(part for part in parts if part["part_kind"] == "tool-return")
        assert tool_return["tool_call_id"] == tool_call["tool_call_id"]
        assert tool_return["content"]["kind"] == "gui_action_result"
        assert tool_return["content"]["dispatch"]["receipts"][0]["dispatch_status"] == "sent"
        assert tool_return["content"]["effect"] == {
            "availability": "available",
            "observed_change": "unchanged",
            "local_postcondition": "unknown",
            "evidence_method": "structural",
            "reason": "state did not change",
            "evidence_refs": ["F1"],
        }
        current_prompt = next(part for part in recorded["messages"][-1]["parts"] if part["part_kind"] == "user-prompt")
        current = json.loads(current_prompt["content"][0]["content"])
        assert set(current) == {"observation", "recent_trajectory"}
        assert current["recent_trajectory"][-1]["result"]["transition"]["observed_change"] == "unchanged"
        assert "target_ref" not in json.dumps(current["recent_trajectory"])

    asyncio.run(scenario())


def test_runtime_rejection_closes_exact_replay_as_same_call_tool_return() -> None:
    class VerifiedNoEffectProjector:
        async def evaluate(self, task, before, request, result, after, public_world_delta):
            del task, result, public_world_delta
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNCHANGED,
                LocalPostconditionStatus.UNSATISFIED,
                EvidenceMethod.STRUCTURAL,
                "postcondition remained unsatisfied",
                (after.facts[0].fact_id,),
            )

    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"] * 4)
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("replay-before", False),
            post_observations=(
                shared_world("replay-after-1", False),
                shared_world("replay-after-2", False),
            ),
            results=tuple(ActionResult("*", DispatchStatus.SENT, "dom", True) for _ in range(2)),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            VerifiedNoEffectProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("runtime_exact_replay_admission_test"),
            episode_monitor=EpisodeMonitor(),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.BLOCKED
        assert state.execution_count == 2
        assert environment.execute_calls == 2
        assert scripted.calls == 4
        assert state.last_step is not None
        assert isinstance(state.last_step.decision, ToolRejectedResult)
        assert state.last_step.decision.result["kind"] == "prohibited_attempt_rejected"
        assert state.last_step.execution_receipts is None

        recorded = normalize_recorded_provider_input(scripted.records[3])
        parts = tuple(part for message in recorded["messages"] for part in message["parts"])
        rejected_call = next(
            part for part in parts if part["part_kind"] == "tool-call" and part["tool_call_id"] == "recording-call:3"
        )
        rejected_return = next(
            part for part in parts if part["part_kind"] == "tool-return" and part["tool_call_id"] == "recording-call:3"
        )
        assert rejected_return["tool_call_id"] == rejected_call["tool_call_id"]
        assert rejected_return["tool_name"] == rejected_call["tool_name"]
        assert rejected_return["content"]["kind"] == "prohibited_attempt_rejected"
        assert rejected_return["content"]["dispatch"] == "not_sent"
        assert rejected_return["content"]["transport_success"] is False

    asyncio.run(scenario())


def test_runtime_rejection_closes_exact_local_replay_as_same_call_tool_return() -> None:
    async def scenario() -> None:
        repeated = ("search_page_content", {"query": "Shared state"})
        scripted = ScriptedModel(
            [
                repeated,
                repeated,
                repeated,
                ("abort", {"reason": "local replay rejection observed", "category": "user_request"}),
            ]
        )
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("local-replay-tool-return", False),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("runtime_local_replay_admission_test"),
            episode_monitor=EpisodeMonitor(),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.CANCELLED
        assert state.execution_count == 0
        assert environment.execute_calls == 0
        assert scripted.calls == 4

        recorded = normalize_recorded_provider_input(scripted.records[3])
        parts = tuple(part for message in recorded["messages"] for part in message["parts"])
        rejected_call = next(
            part for part in parts if part["part_kind"] == "tool-call" and part["tool_call_id"] == "recording-call:3"
        )
        rejected_return = next(
            part for part in parts if part["part_kind"] == "tool-return" and part["tool_call_id"] == "recording-call:3"
        )
        assert rejected_return["tool_call_id"] == rejected_call["tool_call_id"]
        assert rejected_return["tool_name"] == rejected_call["tool_name"]
        assert rejected_return["content"]["kind"] == "prohibited_attempt_rejected"
        assert rejected_return["content"]["failure_kind"] == "recovery_prohibited_attempt_replay"
        assert rejected_return["content"]["dispatch"] == "not_sent"
        assert rejected_return["content"]["world_changed"] is False

    asyncio.run(scenario())


def test_diagnostic_read_keeps_gui_recovery_and_next_action_policy_deliberate() -> None:
    class VerifiedNoEffectProjector:
        async def evaluate(self, task, before, request, result, after, public_world_delta):
            del task, result, public_world_delta
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNCHANGED,
                LocalPostconditionStatus.UNSATISFIED,
                EvidenceMethod.STRUCTURAL,
                "postcondition remained unsatisfied",
                (after.facts[0].fact_id,),
            )

    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                "first_gui_action",
                "first_gui_action",
                ("list_regions", {}),
                ("abort", {"reason": "stop after recovery inspection", "category": "user_request"}),
            ]
        )
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("lease-before", False),
            post_observations=(
                shared_world("lease-after-1", False),
                shared_world("lease-after-2", False),
            ),
            results=tuple(ActionResult("*", DispatchStatus.SENT, "dom", True) for _ in range(2)),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            VerifiedNoEffectProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("persistent_deliberate_lease_test"),
            episode_monitor=EpisodeMonitor(),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.CANCELLED
        assert environment.execute_calls == 2
        assert scripted.calls == 4
        assert [settings["max_tokens"] for settings in scripted.model_settings] == [
            1024,
            1024,
            4096,
            4096,
        ]
        fourth = normalize_recorded_provider_input(scripted.records[3])
        current_prompt = next(part for part in fourth["messages"][-1]["parts"] if part["part_kind"] == "user-prompt")
        current = json.loads(current_prompt["content"][0]["content"])
        assert current["control_feedback"]["kind"] == "control_stall"
        assert current["control_feedback"]["epoch_id"].startswith("recovery:1:")
        assert current["recent_trajectory"][-1]["action"]["tool"] == "list_regions"

    asyncio.run(scenario())


def test_pydantic_ai_step_persistence_records_each_action_policy_run() -> None:
    async def scenario() -> None:
        step_persistence = pytest.importorskip("pydantic_ai_harness.step_persistence")
        store = step_persistence.InMemoryStepStore()
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        object.__setattr__(policy.port, "step_store", store)
        object.__setattr__(policy.port, "step_conversation_id", "session:steps")
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("step_persistence_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        runs = await store.list_runs(conversation_id="session:steps")
        assert len(runs) == 1
        assert runs[0].agent_name == "action-policy"
        events = await store.list_events(run_id=runs[0].run_id)
        assert [event.kind for event in events] == [
            "run_started",
            "model_request_started",
            "model_request_completed",
            "run_completed",
        ]
        assert policy.port.last_step_run_id == runs[0].run_id

    asyncio.run(scenario())


def test_pydantic_ai_action_policy_emits_native_open_telemetry_spans() -> None:
    async def scenario() -> None:
        trace_module = pytest.importorskip("opentelemetry.sdk.trace")
        export_module = pytest.importorskip("opentelemetry.sdk.trace.export")
        in_memory_module = pytest.importorskip("opentelemetry.sdk.trace.export.in_memory_span_exporter")
        exporter = in_memory_module.InMemorySpanExporter()
        tracer_provider = trace_module.TracerProvider()
        tracer_provider.add_span_processor(export_module.SimpleSpanProcessor(exporter))
        policy = _policy(ScriptedModel(["first_gui_action"]).build())
        object.__setattr__(policy.port, "tracer_provider", tracer_provider)
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("otel_test"),
        ).run_task(environment, shared_task())

        spans = exporter.get_finished_spans()
        assert {span.name for span in spans} == {
            "chat recording-scripted",
            "invoke_agent action-policy",
        }
        chat_span = next(span for span in spans if span.name == "chat recording-scripted")
        assert chat_span.attributes["gen_ai.agent.name"] == "action-policy"
        assert chat_span.attributes["gen_ai.operation.name"] == "chat"
        assert chat_span.attributes["gen_ai.usage.input_tokens"] > 0

    asyncio.run(scenario())


def test_multiple_provider_tool_calls_execute_first_and_preserve_every_proposal() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["multiple_gui_actions"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("multiple-calls", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:multiple-calls", context))

        assert result.failure is None
        assert result.output is not None
        decision = result.output.decision
        assert isinstance(decision, SelectAction)
        assert decision.tool_call_id == "recording-call:1"
        assert scripted.calls == 1
        assert [attempt.phase for attempt in result.attempts] == ["ordinary"]
        assert result.diagnostics["multiple_tool_call_attempt_count"] == 1
        assert result.diagnostics["discarded_protocol_call_count"] == 1
        assert len(policy.port.last_admitted_envelopes) == 1
        assert isinstance(policy.port.message_history[0], ModelRequest)
        assert any(isinstance(part, UserPromptPart) for part in policy.port.message_history[0].parts)
        retained = policy.port.message_history[1]
        assert isinstance(retained, ModelResponse)
        assert [part.tool_call_id for part in retained.parts if isinstance(part, ToolCallPart)] == [
            "recording-call:1",
            "recording-call:1:second",
        ]

    asyncio.run(scenario())


def test_text_only_output_uses_one_pydantic_retry_and_retains_only_the_accepted_exchange() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["zero_calls", "first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("text-only-output-retry", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:text-only-output-retry", context))

        assert result.failure is None and result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "ordinary_output_retry",
        ]
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert result.attempts[0].output_failure_kind is StructuredOutputFailureKind.NO_TOOL_CALL
        assert result.attempts[1].output_failure_kind is None
        assert result.diagnostics["policy_model_call_count"] == 2
        assert [record.model_settings["tool_choice"] for record in scripted.records] == [
            "auto",
            "required",
        ]
        assert [attempt.transcript["llm.model_settings"]["tool_choice"] for attempt in result.attempts] == [
            "auto",
            "required",
        ]
        canonical_history = json.dumps(policy.port.message_history, default=str)
        assert "no tool call" not in canonical_history
        assert "Return one offered tool call" not in canonical_history
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_historical_tool_name_uses_one_pydantic_retry_against_the_current_catalog() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("historical_type_text", {"target": "E23", "text": "stale"}),
                "first_gui_action",
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("historical-tool-name-retry", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:historical-tool-retry", context))

        assert result.failure is None and result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert scripted.calls == 2
        assert "historical_type_text" not in scripted.offered_tools[0]
        assert scripted.offered_tools[1] == scripted.offered_tools[0]
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert result.attempts[0].output_failure_kind is StructuredOutputFailureKind.JSON_INVALID
        retry_request = scripted.records[1].messages[-1]
        assert isinstance(retry_request, ModelRequest)
        retry_text = json.dumps(retry_request, default=str)
        assert "Unknown tool name" in retry_text
        assert "historical_type_text" in retry_text
        retained = json.dumps(policy.port.message_history, default=str)
        assert "historical_type_text" not in retained
        assert "Unknown tool name" not in retained

    asyncio.run(scenario())


def test_tool_and_output_retries_compose_within_one_bounded_policy_run() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("historical_type_text", {"target": "E23", "text": "stale"}),
                "zero_calls",
                "first_gui_action",
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("composed-protocol-retries", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:composed-retries", context))

        assert result.failure is None and result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert scripted.calls == 3
        assert [attempt.status for attempt in result.attempts] == [
            "invalid",
            "invalid",
            "accepted",
        ]
        assert [attempt.output_failure_kind for attempt in result.attempts] == [
            StructuredOutputFailureKind.JSON_INVALID,
            StructuredOutputFailureKind.NO_TOOL_CALL,
            None,
        ]
        assert result.diagnostics["policy_model_call_count"] == 3
        retained = json.dumps(policy.port.message_history, default=str)
        assert "historical_type_text" not in retained
        assert "no tool call" not in retained

    asyncio.run(scenario())


def test_sdk_request_limit_failure_is_local_invalid_response_not_provider_outage() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel([UsageLimitExceeded("synthetic local request guard")])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("local-protocol-limit", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:local-protocol-limit", context))

        assert result.output is None and result.failure is not None
        assert result.failure.kind is ModelFailureKind.INVALID_RESPONSE
        assert result.failure.retryable is False
        assert result.failure.attempt_origin is ProviderAttemptOrigin.LOCAL_RUNTIME
        assert result.failure.reason == "action_policy_protocol_retry_budget_exhausted"
        assert [attempt.status for attempt in result.attempts] == ["failed"]
        assert result.attempts[0].transcript["error.code"] == ("action_policy_protocol_retry_budget_exhausted")
        assert result.diagnostics["pre_provider_failure"]["phase"] == ("action_policy_protocol_retry_budget")

    asyncio.run(scenario())


def test_provider_bridge_does_not_own_recovery_replay_admission() -> None:
    async def scenario() -> None:
        repeated_call_id = "recording-call:prohibited-read"
        scripted = ScriptedModel(
            [
                ModelResponse(parts=[ToolCallPart("list_regions", {}, repeated_call_id)]),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("recovery-output-validator", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "epoch_id": "recovery:1:fixture",
                "evidence_revision": 1,
                "stable_signature": "control-stall:fixture",
                "recovery_attempt": 1,
                "prohibited_attempt_signatures": (),
            },
        )

        result = await policy.port.generate(ModelDecisionRequest("request:recovery-output-validator", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, ReadRegionResult)
        assert result.output.decision.tool_name == "list_regions"
        assert result.output.decision.tool_call_id == repeated_call_id
        assert scripted.calls == 1
        assert [attempt.phase for attempt in result.attempts] == ["deliberate"]
        assert [attempt.status for attempt in result.attempts] == ["accepted"]
        canonical_history = json.dumps(policy.port.message_history, default=str)
        assert repeated_call_id in canonical_history

    asyncio.run(scenario())


def test_text_only_output_retry_exhaustion_is_typed_no_tool_call() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["zero_calls", "zero_calls"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("text-only-output-exhausted", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:text-only-output-exhausted", context))

        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INVALID_RESPONSE
        assert result.failure.reason == "no_tool_call"
        assert scripted.calls == 2
        assert [attempt.status for attempt in result.attempts] == ["invalid", "failed"]
        assert all(
            attempt.output_failure_kind is StructuredOutputFailureKind.NO_TOOL_CALL for attempt in result.attempts
        )
        assert result.diagnostics["policy_model_call_count"] == 2
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_exhausted_output_retry_trace_excludes_prior_official_history() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                "zero_calls",
                "zero_calls",
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("output-retry-history-boundary", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:output-retry-history:first", first_context))
        assert first.failure is None and first.output is not None
        object.__setattr__(
            policy.port,
            "message_history",
            (
                ModelRequest(parts=[UserPromptPart("retained compaction summary")]),
                *policy.port.message_history,
            ),
        )
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:output-retry-history:second",
                second_context,
                last_step=first_step,
            )
        )

        assert second.failure is not None
        assert second.failure.reason == "no_tool_call"
        assert scripted.calls == 3
        assert [item.phase for item in second.attempts] == [
            "ordinary",
            "ordinary_output_retry",
        ]
        assert [item.status for item in second.attempts] == ["invalid", "failed"]
        assert all(
            not any(
                part.get("part_kind") == "tool-call"
                for message in item.transcript["llm.output_messages"]
                for part in message["parts"]
            )
            for item in second.attempts
        )

    asyncio.run(scenario())


def test_single_truncated_response_closes_pending_history_in_same_turn_fallback() -> None:
    async def scenario() -> None:
        truncated = ModelResponse(
            parts=[ThinkingPart("unfinished deliberate reasoning")],
            usage=RequestUsage(input_tokens=10, output_tokens=2048),
            finish_reason="length",
            provider_response_id="recording-single-truncated",
        )
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                truncated,
                ("list_regions", {}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("single-truncated-history-recovery", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:single-truncated:first", first_context))
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest("request:single-truncated:second", second_context, last_step=first_step)
        )

        assert second.failure is None and second.output is not None
        assert scripted.calls == 3
        assert len(second.attempts) == 2
        assert second.attempts[0].response_id == "recording-single-truncated"
        assert second.attempts[0].output_failure_kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED
        assert [attempt.status for attempt in second.attempts] == ["invalid", "accepted"]
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) == ToolCall(
            "list_regions",
            {},
            "recording-call:3",
        )
        canonical_envelope_module._project_pydantic_history(policy.port.message_history)
        recorded = normalize_recorded_provider_input(scripted.records[2])
        prior_calls = {
            (part["tool_name"], part["tool_call_id"])
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        }
        prior_returns = {
            (part["tool_name"], part["tool_call_id"])
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        }
        assert prior_calls <= prior_returns

    asyncio.run(scenario())


def test_exhausted_length_fallback_closes_pending_history_and_next_fresh_turn_recovers() -> None:
    async def scenario() -> None:
        first_truncated = ModelResponse(
            parts=[ThinkingPart("unfinished first deliberate reasoning")],
            usage=RequestUsage(
                input_tokens=10,
                output_tokens=2048,
                details={"reasoning_tokens": 2048},
            ),
            finish_reason="length",
            provider_response_id="recording-first-truncated",
        )
        fallback_truncated = ModelResponse(
            parts=[TextPart("unfinished required action envelope")],
            usage=RequestUsage(input_tokens=10, output_tokens=2048),
            finish_reason="length",
            provider_response_id="recording-fallback-truncated",
        )
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                first_truncated,
                fallback_truncated,
                ("list_regions", {}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("exhausted-length-fallback-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:exhausted-length:first", first_context))
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest("request:exhausted-length:second", second_context, last_step=first_step)
        )

        assert second.failure is not None
        assert second.failure.reason == "output_budget_exhausted"
        assert scripted.calls == 3
        assert [attempt.status for attempt in second.attempts] == ["invalid", "failed"]
        assert [attempt.output_failure_kind for attempt in second.attempts] == [
            StructuredOutputFailureKind.OUTPUT_TRUNCATED,
            StructuredOutputFailureKind.OUTPUT_TRUNCATED,
        ]
        assert [attempt.thinking_effective for attempt in second.attempts] == ["disabled", "disabled"]
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) is None
        canonical_envelope_module._project_pydantic_history(policy.port.message_history)
        failed_step = StepResult(
            PolicyFailure(ModelFailureKind.INVALID_RESPONSE, "model decision response was invalid"),
            world,
            world,
            evaluation,
            feedback="policy_failure:invalid_response",
        )
        third_context = builder.build(task, world, actions, evaluation, last_step=failed_step)

        third = await policy.port.generate(
            ModelDecisionRequest("request:exhausted-length:third", third_context, last_step=failed_step)
        )

        assert third.failure is None and third.output is not None
        assert scripted.calls == 4
        recorded = normalize_recorded_provider_input(scripted.records[3])
        prior_calls = {
            (part["tool_name"], part["tool_call_id"])
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        }
        prior_returns = {
            (part["tool_name"], part["tool_call_id"])
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        }
        assert prior_calls <= prior_returns

    asyncio.run(scenario())


def test_provider_failed_length_fallback_closes_pending_history_and_next_fresh_turn_recovers(
    monkeypatch,
) -> None:
    async def scenario() -> None:
        async def no_delay(_delay: float) -> None:
            return None

        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", no_delay)
        truncated = ModelResponse(
            parts=[ThinkingPart("unfinished action selection")],
            usage=RequestUsage(
                input_tokens=10,
                output_tokens=2048,
                details={"reasoning_tokens": 2048},
            ),
            finish_reason="length",
            provider_response_id="recording-provider-fallback-truncated",
        )
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                truncated,
                ModelHTTPError(503, "fallback transient"),
                ModelHTTPError(503, "fallback exhausted"),
                ("list_regions", {}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("provider-failed-length-fallback-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:provider-fallback:first", first_context))
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(task, world, actions, evaluation, last_step=first_step)

        second = await policy.port.generate(
            ModelDecisionRequest("request:provider-fallback:second", second_context, last_step=first_step)
        )

        assert second.failure is not None
        assert second.failure.reason == "model provider is unavailable"
        assert scripted.calls == 4
        assert policy.port.last_provider_retry_count == 1
        assert [attempt.status for attempt in second.attempts] == ["invalid", "failed", "failed"]
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) is None
        canonical_envelope_module._project_pydantic_history(policy.port.message_history)
        official_returns = tuple(
            part
            for message in policy.port.message_history
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        )
        official_calls = tuple(
            part
            for message in policy.port.message_history
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart)
        )
        assert [(part.tool_name, part.tool_call_id) for part in official_calls] == [
            ("list_regions", "recording-call:1")
        ]
        assert [(part.tool_name, part.tool_call_id) for part in official_returns] == [
            ("list_regions", "recording-call:1")
        ]
        assert "unfinished action selection" not in json.dumps(policy.port.message_history, default=str)

        failed_step = StepResult(
            PolicyFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "model provider is unavailable"),
            world,
            world,
            evaluation,
            feedback="policy_failure:provider_unavailable",
        )
        third_context = builder.build(task, world, actions, evaluation, last_step=failed_step)
        third = await policy.port.generate(
            ModelDecisionRequest("request:provider-fallback:third", third_context, last_step=failed_step)
        )

        assert third.failure is None and third.output is not None
        assert scripted.calls == 5
        recorded = normalize_recorded_provider_input(scripted.records[4])
        prior_calls = {
            (part["tool_name"], part["tool_call_id"])
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        }
        prior_returns = {
            (part["tool_name"], part["tool_call_id"])
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        }
        assert prior_calls <= prior_returns

    asyncio.run(scenario())


def test_initial_provider_failure_closes_dispatched_pending_history(monkeypatch) -> None:
    async def scenario() -> None:
        async def no_delay(_delay: float) -> None:
            return None

        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", no_delay)
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                ModelHTTPError(503, "initial transient"),
                ModelHTTPError(503, "initial exhausted"),
                ("list_regions", {}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("initial-provider-failed-pending-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()

        first = await policy.port.generate(
            ModelDecisionRequest(
                "request:initial-provider-failed:first",
                builder.build(task, world, actions, evaluation),
            )
        )
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(task, world, actions, evaluation, last_step=first_step)

        second = await policy.port.generate(
            ModelDecisionRequest("request:initial-provider-failed:second", second_context, last_step=first_step)
        )

        assert second.failure is not None
        assert second.failure.reason == "model provider is unavailable"
        assert scripted.calls == 3
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) is None
        canonical_envelope_module._project_pydantic_history(policy.port.message_history)
        official_pairs = [
            (part.tool_name, part.tool_call_id, type(part).__name__)
            for message in policy.port.message_history
            for part in message.parts
            if isinstance(part, (ToolCallPart, ToolReturnPart))
        ]
        assert official_pairs == [
            ("list_regions", "recording-call:1", "ToolCallPart"),
            ("list_regions", "recording-call:1", "ToolReturnPart"),
        ]

        failed_step = StepResult(
            PolicyFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "model provider is unavailable"),
            world,
            world,
            evaluation,
            feedback="policy_failure:provider_unavailable",
        )
        third = await policy.port.generate(
            ModelDecisionRequest(
                "request:initial-provider-failed:third",
                builder.build(task, world, actions, evaluation, last_step=failed_step),
                last_step=failed_step,
            )
        )
        assert third.failure is None and third.output is not None
        assert scripted.calls == 4

    asyncio.run(scenario())


def test_cancelled_length_fallback_closes_pending_history_without_rejected_output(monkeypatch) -> None:
    async def scenario() -> None:
        truncated = ModelResponse(
            parts=[ThinkingPart("cancelled fallback rejected marker")],
            usage=RequestUsage(
                input_tokens=10,
                output_tokens=2048,
                details={"reasoning_tokens": 2048},
            ),
            finish_reason="length",
            provider_response_id="recording-cancelled-fallback-truncated",
        )
        scripted = ScriptedModel([("list_regions", {}), truncated])
        policy = _policy(scripted.build())
        original_run_provider_call = PydanticAIGroundedDecisionPort._run_provider_call

        async def cancel_required_fallback(self, call, **kwargs):
            settings = kwargs.get("physical_settings")
            if isinstance(settings, Mapping) and settings.get("tool_choice") == "required":

                async def cancelled_call():
                    raise asyncio.CancelledError

                return await original_run_provider_call(self, cancelled_call, **kwargs)
            return await original_run_provider_call(self, call, **kwargs)

        monkeypatch.setattr(PydanticAIGroundedDecisionPort, "_run_provider_call", cancel_required_fallback)
        task = shared_task()
        world = shared_world("cancelled-length-fallback-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        first = await policy.port.generate(ModelDecisionRequest("request:cancelled-fallback:first", first_context))
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(task, world, actions, evaluation, last_step=first_step)

        with pytest.raises(asyncio.CancelledError):
            await policy.port.generate(
                ModelDecisionRequest("request:cancelled-fallback:second", second_context, last_step=first_step)
            )

        assert policy.port.last_invocation_result is not None
        assert policy.port.last_invocation_result.failure is not None
        assert policy.port.last_invocation_result.failure.reason == "model invocation was cancelled"
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) is None
        canonical_envelope_module._project_pydantic_history(policy.port.message_history)
        official_calls = tuple(
            part
            for message in policy.port.message_history
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart)
        )
        official_returns = tuple(
            part
            for message in policy.port.message_history
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        )
        assert [(part.tool_name, part.tool_call_id) for part in official_calls] == [
            ("list_regions", "recording-call:1")
        ]
        assert [(part.tool_name, part.tool_call_id) for part in official_returns] == [
            ("list_regions", "recording-call:1")
        ]
        assert "cancelled fallback rejected marker" not in json.dumps(policy.port.message_history, default=str)

    asyncio.run(scenario())


def test_text_only_length_exhaustion_is_typed_output_budget_failure() -> None:
    async def scenario() -> None:
        truncated = ModelResponse(
            parts=[TextPart("unfinished policy reasoning")],
            usage=RequestUsage(input_tokens=10, output_tokens=1024),
            finish_reason="length",
            provider_response_id="recording-truncated",
        )
        scripted = ScriptedModel([truncated, truncated])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("text-output-budget-exhausted", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:text-output-budget-exhausted", context))

        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INVALID_RESPONSE
        assert result.failure.reason == "output_budget_exhausted"
        assert scripted.calls == 2
        assert all(
            attempt.output_failure_kind is StructuredOutputFailureKind.OUTPUT_TRUNCATED for attempt in result.attempts
        )

    asyncio.run(scenario())


def test_wholly_unparseable_tool_call_fails_without_representation_repair() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["malformed_tool_call"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("malformed-tool-call", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:malformed-tool-call", context))

        assert result.failure is not None
        assert scripted.calls == 1
        assert len(result.attempts) == 1
        assert all(attempt.phase != "representation_repair" for attempt in result.attempts)

    asyncio.run(scenario())


def test_semantically_distinct_extra_call_is_not_a_fallback_but_remains_visible() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["multiple_distinct_gui_actions"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("multiple-call-reselection", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:multiple-reselection", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert result.output.decision.tool_call_id == "recording-call:1"
        assert scripted.calls == 1
        assert [attempt.phase for attempt in result.attempts] == ["ordinary"]
        assert result.diagnostics["multiple_tool_call_attempt_count"] == 1
        assert result.diagnostics["discarded_protocol_call_count"] == 1
        physical_history = json.dumps(policy.port.message_history, default=str)
        assert "recording-call:1:discarded" in physical_history

    asyncio.run(scenario())


def test_unexecuted_second_proposal_can_be_reissued_after_the_fresh_world() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("multiple-call-reissue", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        scripted = ScriptedModel(
            [
                [
                    ("list_regions", {}),
                    ("search_page_content", {"query": "scope"}),
                ],
                ("search_page_content", {"query": "scope"}),
            ]
        )
        policy = _policy(scripted.build())
        context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:multiple-reissue:first", context))

        assert first.failure is None and first.output is not None
        assert first.output.decision.tool_name == "list_regions"
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        fresh_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:multiple-reissue:second",
                fresh_context,
                last_step=step,
            )
        )

        assert second.failure is None and second.output is not None, json.dumps(second.diagnostics, default=str)
        assert second.output.decision.tool_name == "search_page_content"
        assert second.output.decision.arguments == {"query": "scope"}
        recorded = normalize_recorded_provider_input(scripted.records[1])
        proposal_ids = tuple(
            part["tool_call_id"]
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        )
        returns = tuple(
            part
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        )
        assert proposal_ids == (
            "recording-call:1",
            "recording-call:1:discarded:1",
        )
        assert tuple(item["tool_call_id"] for item in returns) == proposal_ids
        assert returns[1]["content"].startswith("Not executed:")

    asyncio.run(scenario())


def test_first_call_serialization_preserves_the_current_pending_tool_return_pair() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("multiple-call-with-pending-result", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                [
                    ("search_page_content", {"query": "scope"}),
                    ("list_regions", {}),
                ],
                (
                    "submit_final_response",
                    {"content": "Canonical pairs preserved."},
                ),
            ]
        )
        policy = _policy(scripted.build())
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:pending-pair:first", first_context))
        assert first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:pending-pair:second",
                second_context,
                last_step=first_step,
            )
        )

        assert second.failure is None and second.output is not None, json.dumps(second.diagnostics, default=str)
        assert second.output.decision.tool_call_id == "recording-call:2"
        assert [attempt.phase for attempt in second.attempts] == ["ordinary"]
        assert second.diagnostics["multiple_tool_call_attempt_count"] == 1
        assert second.diagnostics["discarded_protocol_call_count"] == 1
        assert len(policy.port.last_admitted_envelopes) == 1
        assert len(policy.port.message_history) == 4
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) == ToolCall(
            "search_page_content",
            {"query": "scope"},
            "recording-call:2",
        )

        second_step = StepResult(
            second.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        third_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=second_step,
        )
        final = await policy.port.generate(
            ModelDecisionRequest(
                "request:pending-pair:final",
                third_context,
                last_step=second_step,
            )
        )

        assert final.failure is None and final.output is not None
        assert isinstance(final.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[2])
        calls = [
            part
            for message in recorded["messages"]
            if message["kind"] == "response"
            for part in message["parts"]
            if part["part_kind"] == "tool-call"
        ]
        returns = [
            part
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        ]
        assert [(item["tool_name"], item["tool_call_id"]) for item in calls] == [
            ("list_regions", "recording-call:1"),
            ("search_page_content", "recording-call:2"),
            ("list_regions", "recording-call:2:discarded:1"),
        ]
        assert [(item["tool_name"], item["tool_call_id"]) for item in returns] == [
            ("list_regions", "recording-call:1"),
            ("search_page_content", "recording-call:2"),
            ("list_regions", "recording-call:2:discarded:1"),
        ]

    asyncio.run(scenario())


@given(call_count=st.integers(min_value=1, max_value=8))
@settings(max_examples=8, deadline=None)
def test_accepted_exchange_conserves_every_proposal_identity_across_the_next_provider_turn(
    call_count: int,
) -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world(f"accepted-exchange-{call_count}", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        raw_calls = [
            ("list_regions", {}),
            *(("search_page_content", {"query": f"discarded-{index}"}) for index in range(1, call_count)),
        ]
        scripts: list[object] = [raw_calls]
        scripts.append(
            (
                "submit_final_response",
                {"content": "Canonical exchange received."},
            )
        )
        scripted = ScriptedModel(scripts)
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:accepted-exchange:first", first_context))

        assert first.failure is None and first.output is not None
        assert first.output.decision.tool_name == "list_regions"
        accepted_call_id = "recording-call:1"
        assert first.output.decision.tool_call_id == accepted_call_id
        history = policy.port.message_history
        assert len(history) == 2
        assert pydantic_bridge._pending_call_from_history(history) == ToolCall("list_regions", {}, accepted_call_id)
        raw_response_parts = first.attempts[0].transcript["llm.output_messages"][0]["parts"]
        assert len([part for part in raw_response_parts if part["part_kind"] == "tool-call"]) == call_count

        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        assert step.decision is first.output.decision
        assert step.decision.tool_call_id == accepted_call_id
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:accepted-exchange:second",
                second_context,
                last_step=step,
            )
        )

        assert second.failure is None and second.output is not None, json.dumps(second.diagnostics, default=str)
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        assert recorded == policy.port.last_admitted_envelopes[0].model_boundary_projection()
        prior_calls = tuple(part for part in recorded["messages"][-2]["parts"] if part["part_kind"] == "tool-call")
        paired_results = tuple(part for part in recorded["messages"][-1]["parts"] if part["part_kind"] == "tool-return")
        assert prior_calls[0] == {
            "part_kind": "tool-call",
            "tool_name": "list_regions",
            "arguments": {},
            "tool_call_id": accepted_call_id,
        }
        assert len(prior_calls) == call_count
        assert len(paired_results) == call_count
        assert tuple((item["tool_name"], item["tool_call_id"]) for item in paired_results) == tuple(
            (item["tool_name"], item["tool_call_id"]) for item in prior_calls
        )
        physical = json.dumps(recorded, sort_keys=True)
        if call_count > 1:
            assert all(f"discarded-{index}" not in physical for index in range(1, call_count))
            assert all(f"recording-call:1:discarded:{index}" in physical for index in range(1, call_count))
            assert all("Not executed" in item["content"] for item in paired_results[1:])
        assert scripted.calls == 2

    asyncio.run(scenario())


def test_control_boundary_closes_pending_pydantic_history_before_another_model_turn() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("control-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        scripted = ScriptedModel(
            [
                "first_gui_action",
                (
                    "submit_final_response",
                    {"content": "Closed control boundary observed."},
                ),
            ]
        )
        policy = _policy(scripted.build())
        context = builder.build(task, world, actions, evaluation)
        first = await policy.port.generate(ModelDecisionRequest("request:control:first", context))
        assert first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="action_not_dispatched:control_pause_boundary_reached",
        )

        policy.close_deferred_call(step)

        assert len(policy.port.message_history) == 3
        assert pydantic_bridge._pending_call_from_history(policy.port.message_history) is None
        closed_request = policy.port.message_history[-1]
        assert isinstance(closed_request, ModelRequest)
        returned = tuple(part for part in closed_request.parts if isinstance(part, ToolReturnPart))
        assert len(returned) == 1
        assert returned[0].tool_call_id == first.output.decision.tool_call_id
        assert returned[0].content["dispatch"]["completion"] == "not_dispatched"
        assert returned[0].content["effect"] == {
            "availability": "unavailable",
            "reason": "not_dispatched",
        }

        next_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:control:second", next_context, last_step=step)
        )

        assert second.failure is None and second.output is not None, json.dumps(second.diagnostics, default=str)
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        paired = tuple(
            part for message in recorded["messages"] for part in message["parts"] if part["part_kind"] == "tool-return"
        )
        assert len(paired) == 1
        assert paired[0]["content"]["dispatch"]["completion"] == "not_dispatched"
        assert policy.port.message_history == ()

    asyncio.run(scenario())


def test_exact_model_reasoning_and_call_identities_survive_into_the_next_turn() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("progress-history", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        progress = _progress_text(
            verified_facts=("Verified names: Dibbins and Anglebert Dinkherhump",),
            next_intent="Submit the supported final answer",
        )
        discarded_id = "recording-call:progress:discarded"
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ThinkingPart("private deliberation " * 400),
                        TextPart(progress),
                        ToolCallPart("list_regions", {}, "recording-call:progress"),
                        ToolCallPart(
                            "search_page_content",
                            {"query": "unneeded recheck"},
                            discarded_id,
                        ),
                    ],
                    provider_response_id="recording-response:progress",
                ),
                (
                    "submit_final_response",
                    {"content": "Dibbins; Anglebert Dinkherhump"},
                ),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:progress:first", first_context))

        assert first.failure is None and first.output is not None
        assert first.output.decision.tool_call_id == "recording-call:progress"
        assert scripted.records[0].model_settings["tool_choice"] == "auto"
        retained = policy.port.message_history[1]
        assert isinstance(retained, ModelResponse)
        assert [type(part) for part in retained.parts] == [
            ThinkingPart,
            TextPart,
            ToolCallPart,
            ToolCallPart,
        ]
        assert retained.parts[1].content == progress
        raw_parts = first.attempts[0].transcript["llm.output_messages"][0]["parts"]
        assert any(part["part_kind"] == "thinking" and "private deliberation" in part["content"] for part in raw_parts)

        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:progress:second", second_context, last_step=step)
        )

        assert second.failure is None and second.output is not None, json.dumps(second.diagnostics, default=str)
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        prior_response = next(message for message in recorded["messages"] if message["kind"] == "response")
        assert prior_response["parts"] == (
            {
                "part_kind": "thinking",
                "content": retained.parts[0].content,
            },
            {
                "part_kind": "text",
                "content": retained.parts[1].content,
            },
            {
                "part_kind": "tool-call",
                "tool_name": "list_regions",
                "arguments": {},
                "tool_call_id": "recording-call:progress",
            },
            {
                "part_kind": "tool-call",
                "tool_name": "search_page_content",
                "arguments": {},
                "tool_call_id": discarded_id,
            },
        )
        physical = json.dumps(recorded, sort_keys=True)
        assert "private deliberation" in physical
        assert discarded_id in physical
        assert "unneeded recheck" not in physical
        assert "Not executed" in physical
        assert "Do not emit a separate memory" in str(scripted.records[0].instructions)
        assert "In the same response, briefly state" not in str(scripted.records[0].instructions)
        assert "Return exactly one offered tool call" in str(scripted.records[0].instructions)

    asyncio.run(scenario())


def test_action_narration_remains_while_only_the_fresh_world_prompt_is_sent() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("progress-carry-forward", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        progress = _progress_text(
            verified_facts=("Portland coordinates: 43.6600,-70.2550",),
            remaining_requirements=("Acadia coordinates", "OSRM distance"),
            next_intent="Resolve the Acadia location and route distance",
        )
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        TextPart(progress),
                        ToolCallPart("list_regions", {}, "call:progress:first"),
                    ]
                ),
                ModelResponse(
                    parts=[
                        ThinkingPart("hidden tool-only deliberation"),
                        TextPart("I will switch back to the Portland tab now."),
                        ToolCallPart(
                            "search_page_content",
                            {"query": "coordinates"},
                            "call:progress:second",
                        ),
                    ]
                ),
            ]
        )
        policy = _policy(scripted.build())
        first_context = builder.build(task, world, actions, evaluation)

        first = await policy.port.generate(ModelDecisionRequest("request:progress-carry:first", first_context))
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=first_step,
        )

        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:progress-carry:second",
                second_context,
                last_step=first_step,
            )
        )

        assert second.failure is None and second.output is not None
        history = policy.port.message_history
        assert len(history) == 4
        assert isinstance(history[0], ModelRequest)
        assert isinstance(history[1], ModelResponse)
        assert [part.content for part in history[1].parts if isinstance(part, TextPart)] == [progress]
        assert isinstance(history[2], ModelRequest)
        assert (
            sum(
                isinstance(part, UserPromptPart)
                for message in history
                if isinstance(message, ModelRequest)
                for part in message.parts
            )
            == 2
        )
        prompt_payloads = tuple(
            json.loads(part.content)
            for message in history
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart) and isinstance(part.content, str)
        )
        assert sum(set(payload) == {"task", "goal_plan"} for payload in prompt_payloads) == 1
        assert sum(set(payload) == {"observation"} for payload in prompt_payloads) == 1
        assert isinstance(history[-1], ModelResponse)
        assert [part.content for part in history[-1].parts if isinstance(part, TextPart)] == [
            "I will switch back to the Portland tab now."
        ]
        assert (
            sum(
                isinstance(part, TextPart)
                for message in history
                if isinstance(message, ModelResponse)
                for part in message.parts
            )
            == 2
        )
        assert "hidden tool-only deliberation" in json.dumps(history, default=str)
        assert "switch back to the Portland tab" in json.dumps(history, default=str)
        assert "switch back to the Portland tab" in json.dumps(
            second.attempts[0].transcript["llm.output_messages"],
            default=str,
        )

    asyncio.run(scenario())


def test_recording_model_can_consume_search_region_in_the_next_turn() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("search-follow-up-recording", False)
        action_space = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, action_space, evaluation)
        region = first_context.region_index.region_for_target("shared-toggle")
        assert region is not None
        region_ref = first_context.canonical_world.region_refs[region.key]
        scripted = ScriptedModel(
            [
                ("search_page_content", {"query": "false"}),
                ("read_region", {"region_ref": region_ref}),
                (
                    "submit_final_response",
                    {"content": "Observed the complete current result."},
                ),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:search", first_context))
        assert first.failure is None
        assert first.output is not None
        assert isinstance(first.output.decision, SearchPageContentResult)
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            action_space,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(ModelDecisionRequest("request:read", second_context, last_step=step))

        assert second.failure is None
        assert second.output is not None
        assert isinstance(second.output.decision, ReadRegionResult)
        assert second.output.decision.arguments == {"region_ref": region_ref}
        assert second.output.decision.result["kind"] == "Opened"
        second_step = StepResult(
            second.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        third_context = builder.build(
            task,
            world,
            action_space,
            evaluation,
            last_step=second_step,
        )
        third = await policy.port.generate(ModelDecisionRequest("request:answer", third_context, last_step=second_step))

        assert third.failure is None
        assert third.output is not None
        assert isinstance(third.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[2])
        history_parts = tuple(
            part
            for message in recorded["messages"]
            for part in message["parts"]
            if part["part_kind"] in {"tool-call", "tool-return"}
        )
        assert tuple(part["part_kind"] for part in history_parts) == (
            "tool-call",
            "tool-return",
            "tool-call",
            "tool-return",
        )
        assert tuple(part["tool_call_id"] for part in history_parts) == (
            "recording-call:1",
            "recording-call:1",
            "recording-call:2",
            "recording-call:2",
        )
        assert history_parts[1]["content"] == sanitize_history_arguments(
            first.output.decision.result,
            ephemeral_paths=first.output.decision.ephemeral_result_paths,
        )
        assert json.dumps(history_parts[3]["content"], sort_keys=True) == json.dumps(
            to_json_compatible(second.output.decision.result),
            sort_keys=True,
        )
        user_prompts = tuple(
            part for message in recorded["messages"] for part in message["parts"] if part["part_kind"] == "user-prompt"
        )
        assert len(user_prompts) == 2
        anchor_payload = json.loads(user_prompts[0]["content"][0]["content"])
        assert set(anchor_payload) == {"task", "goal_plan"}
        assert anchor_payload["task"]["instruction"] == task.instruction
        assert sum("task" in json.loads(item["content"][0]["content"]) for item in user_prompts) == 1
        assert all(
            set(json.loads(item["content"][0]["content"])) in ({"task", "goal_plan"}, {"observation"})
            for item in user_prompts
        )
        current_prompt_part = next(
            part for part in recorded["messages"][-1]["parts"] if part["part_kind"] == "user-prompt"
        )
        user_text = current_prompt_part["content"][0]["content"]
        payload = json.loads(user_text)
        assert set(payload) == {"observation"}
        assert "latest_public_results" not in payload
        assert scripted.calls == 3
        assert policy.port.message_history == ()

    asyncio.run(scenario())


def _official_history_with_pending_actions(turns: int) -> tuple[object, ...]:
    messages: list[object] = [
        ModelRequest(parts=[UserPromptPart("World 0: Portland task not started")]),
    ]
    for index in range(turns):
        messages.append(
            _history_response(
                [
                    ThinkingPart(f"step {index}: inspect the fresh World"),
                    TextPart(f"conclusion {index}: continue toward Acadia"),
                    ToolCallPart("activate", {"target": f"E{index}"}, f"call:{index}"),
                ],
                {f"call:{index}": (("target",),)},
            )
        )
        if index + 1 < turns:
            messages.append(
                ModelRequest(
                    parts=[
                        _history_return(
                            "activate",
                            {"status": "stable", "page": index + 1},
                            f"call:{index}",
                        ),
                        UserPromptPart(f"World {index + 1}: fresh observation after action {index}"),
                    ]
                )
            )
    return tuple(messages)


def _assert_summary_keeps_task_anchor_and_exact_suffix(
    compacted: tuple[object, ...],
    original: tuple[object, ...],
) -> None:
    assert compacted[1] == original[0]
    suffix = compacted[2:]
    assert suffix
    assert suffix == original[-len(suffix) :]


@given(turns=st.integers(min_value=5, max_value=12))
@settings(max_examples=12)
def test_history_projection_keeps_one_task_anchor_no_stale_world_and_all_pairs(
    turns: int,
) -> None:
    original = list(_official_history_with_pending_actions(turns))
    for index, message in enumerate(tuple(original)):
        if not isinstance(message, ModelRequest):
            continue
        parts = tuple(
            replace(
                part,
                content=json.dumps(
                    {
                        "task": {"instruction": "old duplicated task"},
                        "observation": f"World {index}",
                        "goal_plan": {"items": ["old duplicated plan"]},
                    },
                    separators=(",", ":"),
                ),
            )
            if isinstance(part, UserPromptPart)
            else part
            for part in message.parts
        )
        original[index] = replace(message, parts=parts)
    task_plan = {
        "task": {"instruction": "current task"},
        "goal_plan": {"items": ["current plan"]},
    }

    normalized = pydantic_bridge._normalize_pydantic_history_for_current_task(
        tuple(original),
        task_plan=task_plan,
    )
    folded = pydantic_bridge._fold_expired_world_prompts(
        normalized,
        max_estimated_tokens=1,
    )

    prompts = tuple(
        part
        for message in folded
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )
    assert len(prompts) == 1
    assert json.loads(prompts[0].content) == task_plan
    original_returns = tuple(
        part
        for message in normalized
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    folded_returns = tuple(
        part
        for message in folded
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    assert folded_returns == original_returns
    assert pydantic_bridge._pending_call_from_history(folded) == ToolCall(
        "activate",
        {"target": f"E{turns - 1}"},
        f"call:{turns - 1}",
    )
    canonical_envelope_module._project_pydantic_history(folded)


@given(turns=st.integers(min_value=5, max_value=12))
@settings(max_examples=12)
def test_history_projection_bounds_repeated_prose_and_conserves_calls_results_and_conclusions(
    turns: int,
) -> None:
    repeated_reasoning = "The current screen still needs the next control."
    repeated_narration = "I will inspect the next control now."
    stable_conclusion = "Verified fact: Portland coordinates are 43.6600,-70.2550."
    original = list(_official_history_with_pending_actions(turns))
    response_indices = tuple(index for index, message in enumerate(original) if isinstance(message, ModelResponse))
    for ordinal, index in enumerate(response_indices):
        response = original[index]
        assert isinstance(response, ModelResponse)
        prose = stable_conclusion if ordinal == 1 else repeated_narration
        original[index] = replace(
            response,
            parts=(
                ThinkingPart(repeated_reasoning),
                TextPart(prose),
                *(part for part in response.parts if isinstance(part, ToolCallPart)),
            ),
        )
    original_tuple = tuple(original)

    projected = pydantic_bridge._project_expired_history(
        original_tuple,
        max_estimated_tokens=1,
    )

    original_calls = tuple(
        part
        for message in original_tuple
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    projected_calls = tuple(
        part
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    original_returns = tuple(
        part
        for message in original_tuple
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    projected_returns = tuple(
        part
        for message in projected
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    projected_text = tuple(
        part.content
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, TextPart)
    )
    projected_thinking = tuple(
        part.content
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ThinkingPart)
    )

    assert tuple((part.tool_name, part.tool_call_id) for part in projected_calls) == tuple(
        (part.tool_name, part.tool_call_id) for part in original_calls
    )
    assert tuple(part.args for part in projected_calls[:-1]) == tuple(
        sanitize_history_arguments(part.args, ephemeral_paths=(("target",),)) for part in original_calls[:-1]
    )
    assert projected_calls[-1] == original_calls[-1]
    assert tuple(part.content for part in projected_returns) == tuple(
        sanitize_history_value(part.content) for part in original_returns
    )
    assert stable_conclusion in projected_text
    assert projected_text.count(repeated_narration) == 1
    assert projected_thinking.count(repeated_reasoning) == 1
    assert projected[-1] == original_tuple[-1]
    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "activate",
        {"target": f"E{turns - 1}"},
        f"call:{turns - 1}",
    )
    canonical_envelope_module._project_pydantic_history(projected)


@given(turns=st.integers(min_value=2, max_value=12))
@settings(max_examples=12)
def test_history_projection_expires_only_closed_private_reasoning_with_public_conclusions(
    turns: int,
) -> None:
    original = _official_history_with_pending_actions(turns)

    projected = pydantic_bridge._project_expired_history(
        original,
        max_estimated_tokens=1,
    )

    original_calls = tuple(
        part
        for message in original
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    projected_calls = tuple(
        part
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    original_returns = tuple(
        part
        for message in original
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    projected_returns = tuple(
        part
        for message in projected
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    projected_text = tuple(
        part.content
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, TextPart)
    )
    projected_thinking = tuple(
        part.content
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ThinkingPart)
    )

    assert tuple((part.tool_name, part.tool_call_id) for part in projected_calls) == tuple(
        (part.tool_name, part.tool_call_id) for part in original_calls
    )
    assert tuple(part.args for part in projected_calls[:-1]) == tuple(
        sanitize_history_arguments(part.args, ephemeral_paths=(("target",),)) for part in original_calls[:-1]
    )
    assert projected_calls[-1] == original_calls[-1]
    assert tuple(part.content for part in projected_returns) == tuple(
        sanitize_history_value(part.content) for part in original_returns
    )
    assert projected_text == tuple(f"conclusion {index}: continue toward Acadia" for index in range(turns))
    assert projected_thinking == (f"step {turns - 1}: inspect the fresh World",)
    assert projected[-1] == original[-1]
    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "activate",
        {"target": f"E{turns - 1}"},
        f"call:{turns - 1}",
    )
    canonical_envelope_module._project_pydantic_history(projected)


def test_history_projection_keeps_closed_tool_only_reasoning_until_semantic_compaction() -> None:
    original = list(_official_history_with_pending_actions(3))
    first_response = original[1]
    assert isinstance(first_response, ModelResponse)
    original[1] = replace(
        first_response,
        parts=tuple(part for part in first_response.parts if not isinstance(part, TextPart)),
    )

    projected = pydantic_bridge._project_expired_history(
        tuple(original),
        max_estimated_tokens=1,
    )

    first_projected = next(
        message
        for message in projected
        if isinstance(message, ModelResponse)
        and any(isinstance(part, ToolCallPart) and part.tool_call_id == "call:0" for part in message.parts)
    )
    assert any(isinstance(part, ThinkingPart) for part in first_projected.parts)
    canonical_envelope_module._project_pydantic_history(projected)


def test_history_projection_degrounds_only_handles_from_noncurrent_worlds() -> None:
    original = (
        ModelRequest(parts=[UserPromptPart("search results World")]),
        _history_response(
            [
                TextPart("Search found More results at E6."),
                ToolCallPart(
                    "search_page_content",
                    {"query": "More results"},
                    "call:search",
                ),
            ],
            {"call:search": (("cursor",),)},
        ),
        ModelRequest(
            parts=[
                _history_return(
                    "search_page_content",
                    {
                        "items": (
                            {
                                "label": "More results",
                                "target_ref": "E6",
                                "verbs": ("activate",),
                                "region_ref": "R2",
                                "state": {"semantic.link.destination": "https://example.test/results/6"},
                            },
                        ),
                        "next_cursor": "opaque-old-page",
                    },
                    "call:search",
                    ephemeral_paths=(
                        ("items", "*", "target_ref"),
                        ("items", "*", "verbs"),
                        ("items", "*", "region_ref"),
                        ("next_cursor",),
                    ),
                    metadata={
                        "before_world": "observation:search",
                        "after_world": "observation:search",
                    },
                )
            ]
        ),
        _history_response(
            [
                TextPart("Open More results E6."),
                ToolCallPart("activate", {"target": "E6"}, "call:activate"),
            ],
            {"call:activate": (("target",),)},
        ),
        ModelRequest(
            parts=[
                _history_return(
                    "activate",
                    {"status": "stable", "outcome": "Not Found page loaded"},
                    "call:activate",
                    metadata={
                        "before_world": "observation:search",
                        "after_world": "observation:not-found",
                    },
                )
            ]
        ),
        ModelResponse(parts=[ToolCallPart("find_controls", {"query": "different route"}, "call:pending")]),
    )

    projected = pydantic_bridge._project_expired_history(
        original,
        max_estimated_tokens=100_000,
    )

    calls = {
        part.tool_call_id: part
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }
    returns = {
        part.tool_call_id: part
        for message in projected
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    search_content = returns["call:search"].content
    assert calls["call:search"].args == {"query": "More results"}
    assert calls["call:activate"].args == {}
    assert calls["call:pending"].args == {"query": "different route"}
    assert search_content == {
        "items": (
            {
                "label": "More results",
                "state": {"semantic.link.destination": "https://example.test/results/6"},
            },
        )
    }
    assert returns["call:activate"].content == {
        "status": "stable",
        "outcome": "Not Found page loaded",
    }
    assert set(calls) == {"call:search", "call:activate", "call:pending"}
    assert set(returns) == {"call:search", "call:activate"}
    assert original[3].parts[1].args == {"target": "E6"}
    assert original[2].parts[0].content["items"][0]["target_ref"] == "E6"
    assert all(
        "E6" in part.content
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, TextPart)
    )
    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "find_controls",
        {"query": "different route"},
        "call:pending",
    )
    canonical_envelope_module._project_pydantic_history(projected)


def test_history_projection_degrounds_closed_same_world_read_and_keeps_pending_call_exact() -> None:
    tool_return = _history_return(
        "search_page_content",
        {"items": ({"label": "More results", "target_ref": "E6", "verbs": ("activate",)},)},
        "call:search",
        ephemeral_paths=(("items", "*", "target_ref"), ("items", "*", "verbs")),
        metadata={
            "before_world": "observation:search",
            "after_world": "observation:search",
        },
    )
    original = (
        _history_response(
            [
                TextPart("Use E6 More results."),
                ToolCallPart("search_page_content", {"query": "More results"}, "call:search"),
            ],
            {"call:search": (("cursor",),)},
        ),
        ModelRequest(parts=[tool_return]),
        ModelResponse(parts=[ToolCallPart("activate", {"target": "E6"}, "call:pending")]),
    )

    projected = pydantic_bridge._project_expired_history(
        original,
        max_estimated_tokens=100_000,
    )

    projected_search = next(
        part
        for message in projected
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id == "call:search"
    )
    assert projected_search.content == {"items": ({"label": "More results"},)}
    completed_response = projected[0]
    assert isinstance(completed_response, ModelResponse)
    assert isinstance(completed_response.parts[0], TextPart)
    assert completed_response.parts[0].content == "Use E6 More results."
    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "activate",
        {"target": "E6"},
        "call:pending",
    )


@given(
    business_kind=st.sampled_from(("E", "N", "F", "R")),
    business_index=st.integers(min_value=2, max_value=999),
    selector_index=st.integers(min_value=1_000, max_value=1_999),
)
@settings(max_examples=24)
def test_history_projection_preserves_ref_shaped_business_values(
    business_kind: str,
    business_index: int,
    selector_index: int,
) -> None:
    business_value = f"{business_kind}{business_index}"
    selector_ref = f"E{selector_index}"
    original = (
        _history_response(
            [
                TextPart(f"Enter business code {business_value} into {selector_ref}."),
                ToolCallPart(
                    "type_text",
                    {"target": selector_ref, "text": business_value},
                    "call:closed",
                ),
            ],
            {"call:closed": (("target",),)},
        ),
        ModelRequest(
            parts=[
                _history_return(
                    "type_text",
                    {
                        "entered_text": business_value,
                        "status": "stable",
                        "target_ref": selector_ref,
                    },
                    "call:closed",
                    ephemeral_paths=(("target_ref",),),
                )
            ]
        ),
        _history_response(
            [
                ToolCallPart(
                    "search_page_content",
                    {"query": business_value},
                    "call:pending",
                )
            ],
            {"call:pending": (("cursor",),)},
        ),
    )

    projected = pydantic_bridge._project_expired_history(
        original,
        max_estimated_tokens=100_000,
    )

    closed_response = projected[0]
    closed_return = projected[1]
    assert isinstance(closed_response, ModelResponse)
    assert isinstance(closed_return, ModelRequest)
    assert tuple(part.args for part in closed_response.parts if isinstance(part, ToolCallPart)) == (
        {"text": business_value},
    )
    assert tuple(part.content for part in closed_return.parts if isinstance(part, ToolReturnPart)) == (
        {"entered_text": business_value, "status": "stable"},
    )
    closed_prose = tuple(part.content for part in closed_response.parts if isinstance(part, TextPart))
    assert business_value in closed_prose[0]
    assert selector_ref in closed_prose[0]
    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "search_page_content",
        {"query": business_value},
        "call:pending",
    )


def test_schema_owned_paths_remove_request_evidence_subject_without_touching_property() -> None:
    spec = ToolSpec(
        "request_evidence",
        "Inspect one current subject.",
        {
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "enum": ["visual_property"]},
                "subject": {"type": "string", "enum": ["N1"]},
                "property": {"type": "string", "maxLength": 32},
            },
            "required": ["purpose", "subject", "property"],
            "additionalProperties": False,
        },
        ephemeral_argument_paths=(("subject",),),
    )
    call = ToolCallPart(
        "request_evidence",
        {"purpose": "visual_property", "subject": "N1", "property": "R5"},
        "call:evidence",
    )
    paths = dict(pydantic_bridge._argument_paths_by_call((call,), (spec,)))
    assert "ephemeral_argument_paths" not in to_json_compatible(spec)
    history = (
        _history_response([call], paths),
        ModelRequest(parts=[_history_return("request_evidence", {"status": "unknown"}, "call:evidence")]),
    )

    projected = pydantic_bridge._canonicalize_completed_history(history)
    response = projected[0]
    assert isinstance(response, ModelResponse)
    assert tuple(part.args for part in response.parts if isinstance(part, ToolCallPart)) == (
        {"purpose": "visual_property", "property": "R5"},
    )
    request = projected[1]
    assert isinstance(request, ModelRequest)
    returned = next(part for part in request.parts if isinstance(part, ToolReturnPart))
    assert returned.metadata is None
    assert pydantic_bridge._canonicalize_completed_history(projected) == projected


@pytest.mark.parametrize(
    ("raw_arguments", "canonical_arguments"),
    (
        (
            {"parameters": {"target": "E1", "text": "keep"}},
            {"target": "E1", "text": "keep"},
        ),
        (
            {"question": "Which?", "requested_fields": "not-an-array"},
            {"question": "Which?"},
        ),
    ),
)
def test_official_history_records_the_owner_normalized_accepted_call(
    raw_arguments,
    canonical_arguments,
) -> None:
    source = ModelResponse(
        parts=[
            ThinkingPart("Keep provider reasoning."),
            ToolCallPart("fixture", raw_arguments, "call:accepted"),
        ]
    )
    proposed = tuple(part for part in source.parts if isinstance(part, ToolCallPart))

    accepted = pydantic_bridge._accepted_model_response(
        source,
        ToolCall("fixture", canonical_arguments, "call:accepted"),
        proposed_calls=proposed,
    )

    assert accepted.parts[0] == source.parts[0]
    assert accepted.parts[1].args == canonical_arguments
    assert source.parts[1].args == raw_arguments


def test_settled_history_expires_every_unexecuted_proposal_argument_object() -> None:
    spec = ToolSpec(
        "activate",
        "fixture",
        {
            "type": "object",
            "properties": {"target": {"type": "string", "maxLength": 20}},
            "required": ["target"],
            "additionalProperties": False,
        },
        ephemeral_argument_paths=(("target",),),
    )
    accepted = ToolCallPart("activate", {"target": "E1"}, "call:accepted")
    discarded = ToolCallPart("activate", {"target": "E2"}, "call:discarded")
    paths = dict(pydantic_bridge._argument_paths_by_call((accepted, discarded), (spec,)))
    history = (
        _history_response((accepted, discarded), paths),
        ModelRequest(
            parts=[
                _history_return("activate", {"status": "stable"}, "call:accepted"),
                ToolReturnPart(
                    "activate",
                    canonical_envelope_module.UNEXECUTED_TOOL_CALL_MESSAGE,
                    "call:discarded",
                ),
            ]
        ),
    )

    projected = pydantic_bridge._canonicalize_completed_history(history)
    response = projected[0]

    assert isinstance(response, ModelResponse)
    assert tuple(part.args for part in response.parts if isinstance(part, ToolCallPart)) == ({}, {})


def test_history_projection_locates_completion_by_exchange_not_reused_call_id() -> None:
    original = (
        ModelResponse(parts=[ToolCallPart("activate", {"target": "E1"}, "same-id")]),
        ModelRequest(parts=[ToolReturnPart("activate", {"status": "stable"}, "same-id")]),
        _history_response(
            [
                ToolCallPart(
                    "type_text",
                    {"target": "E2", "text": "keep me"},
                    "same-id",
                )
            ],
            {"same-id": (("target",),)},
        ),
    )

    projected = pydantic_bridge._project_expired_history(
        original,
        max_estimated_tokens=100_000,
    )

    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "type_text",
        {"target": "E2", "text": "keep me"},
        "same-id",
    )
    assert projected[-1] == original[-1]


def test_history_projection_structurally_degrounds_closed_json_string_arguments() -> None:
    original = (
        _history_response(
            [
                ToolCallPart(
                    "type_text",
                    '{"target":"E1","text":"E6"}',
                    "call:string-args",
                )
            ],
            {"call:string-args": (("target",),)},
        ),
        ModelRequest(
            parts=[
                _history_return(
                    "type_text",
                    {"entered_text": "E6", "target_ref": "E1"},
                    "call:string-args",
                    ephemeral_paths=(("target_ref",),),
                )
            ]
        ),
    )

    projected = pydantic_bridge._canonicalize_completed_history(original)

    response = projected[0]
    request = projected[1]
    assert isinstance(response, ModelResponse)
    assert isinstance(request, ModelRequest)
    assert tuple(part.args for part in response.parts if isinstance(part, ToolCallPart)) == ({"text": "E6"},)
    assert tuple(part.content for part in request.parts if isinstance(part, ToolReturnPart)) == (
        {"entered_text": "E6"},
    )


@given(turns=st.integers(min_value=2, max_value=8))
@settings(max_examples=12)
def test_history_projection_conserves_pairs_and_semantics_while_degrounding_expired_worlds(
    turns: int,
) -> None:
    messages: list[object] = []
    for index in range(turns):
        ref = f"E{index + 1}"
        messages.extend(
            (
                _history_response(
                    [
                        TextPart(f"Inspect result {index} at {ref}."),
                        ToolCallPart("activate", {"target": ref}, f"call:{index}"),
                    ],
                    {f"call:{index}": (("target",),)},
                ),
                ModelRequest(
                    parts=[
                        _history_return(
                            "activate",
                            {
                                "label": f"Result {index}",
                                "target_ref": ref,
                                "verbs": ("activate",),
                                "outcome": "stable",
                            },
                            f"call:{index}",
                            ephemeral_paths=(("target_ref",), ("verbs",)),
                            metadata={
                                "before_world": f"observation:{index}",
                                "after_world": f"observation:{index + 1}",
                            },
                        )
                    ]
                ),
            )
        )
    messages.append(ModelResponse(parts=[ToolCallPart("activate", {"target": "E999"}, "call:pending")]))
    original = tuple(messages)

    projected = pydantic_bridge._project_expired_history(
        original,
        max_estimated_tokens=100_000,
    )

    calls = tuple(
        part
        for message in projected
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    returns = tuple(
        part
        for message in projected
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    assert tuple(part.tool_call_id for part in calls) == (
        *(f"call:{index}" for index in range(turns)),
        "call:pending",
    )
    assert tuple(part.tool_call_id for part in returns) == tuple(f"call:{index}" for index in range(turns))
    assert all(part.args == {} for part in calls[:-1])
    assert calls[-1].args == {"target": "E999"}
    assert tuple(part.content for part in returns) == tuple(
        {"label": f"Result {index}", "outcome": "stable"} for index in range(turns)
    )
    assert all(
        part.args == {"target": f"E{index + 1}"}
        for index, part in enumerate(
            part
            for message in original
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart) and part.tool_call_id != "call:pending"
        )
    )
    assert pydantic_bridge._pending_call_from_history(projected) == ToolCall(
        "activate",
        {"target": "E999"},
        "call:pending",
    )
    canonical_envelope_module._project_pydantic_history(projected)


def test_harness_summarizes_only_a_pressured_expired_trajectory_prefix() -> None:
    history = _official_history_with_pending_actions(7)
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("Verified Portland facts; next open Acadia.")])])
    model = scripted.build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.attempted is True
    assert run.error == ""
    assert len(scripted.records) == 1
    assert isinstance(run.messages[0], ModelRequest)
    assert isinstance(run.messages[0].parts[0], SystemPromptPart)
    assert "Verified Portland facts" in run.messages[0].parts[0].content
    _assert_summary_keeps_task_anchor_and_exact_suffix(run.messages, history)
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall("activate", {"target": "E6"}, "call:6")
    summary_input = normalize_recorded_provider_input(scripted.records[0])
    serialized_input = json.dumps(summary_input, sort_keys=True)
    assert "World 0" in serialized_input
    assert "stable" in serialized_input
    assert any(
        isinstance(part, ThinkingPart) and "inspect the fresh World" in part.content
        for message in run.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
    )
    assert "continue toward Acadia" in serialized_input
    canonical_envelope_module._project_pydantic_history(run.messages)


def test_harness_summary_contract_keeps_conclusions_without_action_narration() -> None:
    prompt = pydantic_bridge._HISTORY_COMPACTION_SUMMARY_PROMPT

    assert "## Completed outcomes" in prompt
    assert "At most eight stable user-requirement outcomes" in prompt
    assert "## Verified facts" in prompt
    assert "At most eight exact facts" in prompt
    assert "directly fill requested final-answer fields have highest priority" in prompt
    assert "Never omit such an output value" in prompt
    assert "current controls, form contents, selected modes" in prompt
    assert "## Failed strategies" in prompt
    assert "At most two terse strategy-level failures" in prompt
    assert "## Remaining questions" not in prompt
    assert "## Next intent" not in prompt
    assert "Do not write\nremaining questions" in prompt
    assert "the continuing ActionPolicy derives its next action" in prompt
    assert "## Action outcomes" not in prompt
    assert "Never enumerate attempted URLs" in prompt
    assert "Preserve an exact link destination when it is a requested" in prompt
    assert "do not preserve incidental current browser URLs" in prompt
    assert MODEL_POLICY_EVIDENCE_STATUS in prompt
    assert MODEL_POLICY_EVIDENCE_STATUS in MODEL_POLICY_INSTRUCTIONS
    assert "When all outputs are supported" in MODEL_POLICY_INSTRUCTIONS
    assert "Formatting does not require reopening a source" in MODEL_POLICY_INSTRUCTIONS
    assert "returned no usable control on unchanged World" in MODEL_POLICY_INSTRUCTIONS
    assert "point_grounding once for that target" in MODEL_POLICY_INSTRUCTIONS
    assert "immediately following ActionPolicy delivery" in MODEL_POLICY_INSTRUCTIONS
    assert "history retains its semantic values but no operational refs" in MODEL_POLICY_INSTRUCTIONS
    assert "current_activity" not in MODEL_POLICY_INSTRUCTIONS
    assert "visual_property immediately on current delivered subjects" in MODEL_POLICY_INSTRUCTIONS
    assert "verify the task-defining identity from" in MODEL_POLICY_INSTRUCTIONS
    assert "do not replay the same semantic action" in MODEL_POLICY_INSTRUCTIONS
    assert "visible unauthenticated state plus missing expected content" in MODEL_POLICY_INSTRUCTIONS
    assert "classify every complete in-scope record once" in MODEL_POLICY_INSTRUCTIONS
    assert "full supported result set" in MODEL_POLICY_INSTRUCTIONS
    assert "whether coverage is open" in MODEL_POLICY_INSTRUCTIONS
    assert "whether the proposed route is" in MODEL_POLICY_INSTRUCTIONS
    assert "use typed abort instead of self-verifying" in MODEL_POLICY_INSTRUCTIONS
    assert "local_postcondition=unknown is not a proven failure" in MODEL_POLICY_INSTRUCTIONS
    assert "do not retype merely to force an exact accessibility-value echo" in MODEL_POLICY_INSTRUCTIONS
    assert not {
        "Catso",
        "Dibbins",
        "Quest Lumaflex",
        "small ears",
        "MM/DD/YYYY",
        "sales_report_from",
    }.intersection(MODEL_POLICY_INSTRUCTIONS)
    assert "destination is unavailable" in MODEL_POLICY_EVIDENCE_STATUS
    assert "must not also appear unresolved" in MODEL_POLICY_EVIDENCE_STATUS
    assert pydantic_bridge._HISTORY_RECENT_EXACT_TOKENS_RATIO == 0.12
    assert pydantic_bridge._HISTORY_COMPACTION_MAX_OUTPUT_TOKENS == 1024


def test_grounded_action_policy_prepares_user_owned_challenge_before_handoff() -> None:
    prompt = MODEL_POLICY_INSTRUCTIONS

    assert "prepare the current interface for immediate user completion" in prompt
    assert "prefer a non-secret out-of-band method" in prompt
    assert "use ask_user to request takeover" in prompt
    assert "repeat a blocked task action" in prompt
    assert "do not activate search, content, or task-effect controls" in prompt
    assert "hand off only after that challenge is visible" in prompt
    assert "an action that only the user can safely complete" in prompt
    assert "never enter, request, interpret, copy, or" in prompt


def test_exact_link_identity_survives_destination_load_failure_compaction_boundary() -> None:
    history = list(_official_history_with_pending_actions(7))
    history[0] = ModelRequest(
        parts=[
            UserPromptPart("Return relation_id and driving distance for the selected place"),
        ]
    )
    history[2] = ModelRequest(
        parts=[
            ToolReturnPart(
                "activate",
                {
                    "status": "stable",
                    "result_label": "Selected national park",
                    "resolved_link_target": "/relation/2176999",
                },
                "call:0",
            ),
            UserPromptPart("World 1: selected result is now current"),
        ]
    )
    history[4] = ModelRequest(
        parts=[
            ToolReturnPart(
                "activate",
                {
                    "status": "stable",
                    "route": "/relation/2176999",
                    "page_title": "Not Found",
                },
                "call:1",
            ),
            UserPromptPart("World 2: destination page is unavailable"),
        ]
    )
    expected_summary = """## Verified facts
- relation_id = 2176999 (resolved result link)

## Remaining questions
- Driving distance

## Next intent
Compute the driving distance from the established coordinates."""
    scripted = ScriptedModel([ModelResponse(parts=[TextPart(expected_summary)])])

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            tuple(history),
            model=scripted.build(),
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.error == ""
    assert expected_summary in run.messages[0].parts[0].content
    recorded = json.dumps(
        normalize_recorded_provider_input(scripted.records[0]),
        sort_keys=True,
    )
    assert "An exact identifier encoded in a resolved link target" in recorded
    assert "must not also appear unresolved under Remaining" in recorded
    assert "## Completed outcomes" in recorded
    assert "## Remaining questions" not in recorded
    assert "## Next intent" not in recorded
    assert "remaining questions, working hypotheses" in recorded
    assert "/relation/2176999" in recorded
    assert "Not Found" in recorded
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall("activate", {"target": "E6"}, "call:6")


def test_compaction_does_not_treat_summary_text_as_runtime_fact_state() -> None:
    history = _official_history_with_pending_actions(7)
    invalid_summary = """## Verified facts
- The resolved link target encodes relation ID 2176999.

## Remaining questions
- Relation ID 2176999 because its destination returned Not Found.

## Next intent
- Re-open the relation page."""
    scripted = ScriptedModel([ModelResponse(parts=[TextPart(invalid_summary)])])

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=scripted.build(),
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.attempted is True
    assert run.error == ""
    assert invalid_summary in run.messages[0].parts[0].content
    _assert_summary_keeps_task_anchor_and_exact_suffix(run.messages, history)
    assert pydantic_bridge._pending_call_from_history(run.messages) == pydantic_bridge._pending_call_from_history(
        history
    )
    assert len(scripted.records) == 1


def test_harness_summary_keeps_stable_model_conclusion_past_tool_result_clip() -> None:
    coordinate = "43°39′36″N 70°15′18″W"
    long_result = {
        "kind": "Opened",
        "source_coverage": "partial",
        "has_more": True,
        "items": [
            {"kind": "complete_item", "text": "prefix-" + "x" * 700},
            {"kind": "complete_item", "text": f"Coordinates: {coordinate}"},
        ],
    }
    history = (
        ModelRequest(parts=[UserPromptPart("Find Portland's official coordinates")]),
        ModelResponse(
            parts=[
                ToolCallPart("read_region", {"region_ref": "R264"}, "call:read"),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart("read_region", long_result, "call:read"),
                UserPromptPart("Fresh World after the completed local read"),
            ]
        ),
        ModelResponse(
            parts=[
                ThinkingPart(f"The completed coordinate row confirms {coordinate}."),
                TextPart(f"Portland's official coordinates are {coordinate}."),
                ToolCallPart("wait", {"reason": "fixture"}, "call:pending"),
            ]
        ),
    )
    scripted = ScriptedModel([ModelResponse(parts=[TextPart(f"Verified Portland coordinates: {coordinate}.")])])

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=scripted.build(),
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.error == ""
    summary_input = json.dumps(
        normalize_recorded_provider_input(scripted.records[0]),
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "Tool [read_region]" in summary_input
    assert "Coverage or pagination metadata limits the result's scope" in summary_input
    _assert_summary_keeps_task_anchor_and_exact_suffix(run.messages, history)
    assert history[-1] in run.messages
    assert any(
        isinstance(part, TextPart) and coordinate in part.content
        for message in run.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
    )
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall(
        "wait", {"reason": "fixture"}, "call:pending"
    )


def test_harness_does_not_call_a_model_below_real_history_pressure() -> None:
    history = _official_history_with_pending_actions(3)
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("must not be used")])])
    model = scripted.build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=100_000,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is False
    assert run.error == ""
    assert scripted.records == []


def test_history_pressure_excludes_current_prompt_tools_and_provider_usage_anchor() -> None:
    history = _official_history_with_pending_actions(2)
    history = (
        *history[:-1],
        replace(history[-1], usage=RequestUsage(input_tokens=50_000, output_tokens=1_000)),
    )
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("must not be used")])])

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=scripted.build(),
            max_estimated_tokens=8_000,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is False
    assert scripted.records == []


def test_history_compaction_pressure_uses_complete_request_admission_accounting() -> None:
    below_pressure = ModelRequestBreakdown(
        "ordinary",
        history_tokens=35_000,
        estimated_input_tokens=49_000,
        effective_input_limit=62_904,
    )
    over_capacity = ModelRequestBreakdown(
        "ordinary",
        history_tokens=53_712,
        estimated_input_tokens=67_022,
        effective_input_limit=62_904,
        admission_action="context_capacity",
    )

    assert not pydantic_bridge._history_compaction_required(
        below_pressure,
        has_history=True,
    )
    assert pydantic_bridge._history_compaction_required(
        over_capacity,
        has_history=True,
    )
    assert pydantic_bridge._available_history_tokens(over_capacity) == 49_594


def test_history_economy_pressure_requires_both_high_water_and_reclaim_batch() -> None:
    history = list(_official_history_with_pending_actions(8))
    for index, message in enumerate(tuple(history)):
        if not isinstance(message, ModelResponse):
            continue
        calls = tuple(part for part in message.parts if isinstance(part, ToolCallPart))
        history[index] = replace(
            message,
            parts=(
                ThinkingPart(f"reasoning-{index}-" + "r" * 600),
                TextPart(f"narration-{index}-" + "n" * 600),
                *calls,
            ),
        )
    history_tuple = tuple(history)

    assert not pydantic_bridge._history_economy_compaction_required(
        history_tuple,
        max_estimated_tokens=500,
        available_history_tokens=4_000,
        observed_history_tokens=1_999,
    )
    assert not pydantic_bridge._history_economy_compaction_required(
        history_tuple,
        max_estimated_tokens=100_000,
        available_history_tokens=4_000,
        observed_history_tokens=3_000,
    )
    assert pydantic_bridge._history_economy_compaction_required(
        history_tuple,
        max_estimated_tokens=500,
        available_history_tokens=4_000,
        observed_history_tokens=3_000,
    )


def test_history_watermarks_are_independent_of_summary_output_cap() -> None:
    assert pydantic_bridge._HISTORY_COMPACTION_MAX_OUTPUT_TOKENS == 1024
    assert pydantic_bridge._HISTORY_ECONOMY_PRESSURE_RATIO == 0.5
    assert pydantic_bridge._HISTORY_COMPACTION_TARGET_RATIO == 0.3
    assert pydantic_bridge._HISTORY_COMPACTION_MIN_RECLAIM_RATIO == 0.15


def test_harness_compacts_reclaimable_history_before_whole_request_pressure() -> None:
    history = list(_official_history_with_pending_actions(8))
    for index, message in enumerate(tuple(history)):
        if not isinstance(message, ModelResponse):
            continue
        calls = tuple(part for part in message.parts if isinstance(part, ToolCallPart))
        history[index] = replace(
            message,
            parts=(
                TextPart(f"step-{index}: " + "repeated strategy narration " * 40),
                *calls,
            ),
        )
    history_tuple = tuple(history)
    scripted = ScriptedModel(
        [ModelResponse(parts=[TextPart("## Failed strategies\n- Re-reading the same page added no facts.")])]
    )

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history_tuple,
            model=scripted.build(),
            max_estimated_tokens=1_000,
            observed_estimated_tokens=600,
            timeout_s=2.0,
            trigger="history_pressure",
        )
    )

    assert run.attempted is True
    assert run.trigger == "history_pressure"
    assert run.error == ""
    assert len(scripted.records) == 1
    _assert_summary_keeps_task_anchor_and_exact_suffix(run.messages, history_tuple)
    assert pydantic_bridge._pending_call_from_history(run.messages) == pydantic_bridge._pending_call_from_history(
        history_tuple
    )


def test_action_envelope_recomputes_timeout_after_actual_compaction_elapsed(monkeypatch) -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("dynamic-deadline", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                (
                    "submit_final_response",
                    {"content": "Deadline propagated."},
                ),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="fixture",
            model_id="scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=42.25,
            policy_timeout_s=90.0,
            max_provider_retry_delay_s=5.0,
            history_compaction_timeout_s=42.25,
        )

        first = await port.generate(ModelDecisionRequest("request:deadline-first", first_context))
        assert first.failure is None and first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )

        async def preserve_history(messages, **_kwargs):
            return pydantic_bridge._HistoryCompactionRun(messages)

        timeouts = iter((42.25, 30.75))
        observed: list[float] = []

        def remaining_timeout(**_kwargs):
            timeout = next(timeouts)
            observed.append(timeout)
            return timeout

        monkeypatch.setattr(pydantic_bridge, "_history_compaction_required", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(pydantic_bridge, "_compact_pydantic_history", preserve_history)
        monkeypatch.setattr(pydantic_bridge, "_remaining_action_attempt_timeout", remaining_timeout)

        second = await port.generate(ModelDecisionRequest("request:deadline-second", second_context, last_step=step))

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, FinalResponse)
        assert observed == [42.25, 30.75]
        assert scripted.model_settings[-1]["timeout"] == 30.75
        assert dict(port.last_admitted_envelopes[-1].model_settings)["timeout"] == 30.75

    asyncio.run(scenario())


def test_harness_summary_failure_keeps_the_exact_raw_history() -> None:
    history = _official_history_with_pending_actions(7)
    scripted = ScriptedModel([RuntimeError("summary provider unavailable")])
    model = scripted.build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is True
    assert "summary provider unavailable" in run.error
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall("activate", {"target": "E6"}, "call:6")


def test_invalid_compacted_history_falls_back_to_the_exact_typed_history(monkeypatch) -> None:
    history = _official_history_with_pending_actions(7)
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("summary must be rejected")])])

    def reject_orphaned_history(_messages) -> None:
        raise ValueError("orphaned tool result")

    monkeypatch.setattr(pydantic_bridge, "_project_pydantic_history", reject_orphaned_history)
    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=scripted.build(),
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.messages == history
    assert run.attempted is True
    assert run.error == "ValueError: orphaned tool result"


def test_incremental_compaction_cutoff_preserves_every_completed_tool_pair() -> None:
    messages: list[object] = [
        ModelRequest(
            parts=[SystemPromptPart("Summary of previous conversation:\n\n## Verified facts\n- Earlier generic fact.")]
        ),
        ModelRequest(parts=[UserPromptPart("Generic long task " + "t" * 7_000)]),
    ]
    for index in range(6):
        messages.append(
            ModelResponse(
                parts=[
                    ThinkingPart(f"reasoning {index} " + "q" * 300),
                    TextPart(f"stable conclusion {index} " + "r" * 800),
                    ToolCallPart(
                        "read_region",
                        {"region_ref": f"R{index}"},
                        f"call:{index}",
                    ),
                ]
            )
        )
        if index < 5:
            messages.append(
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            "read_region",
                            {"items": [{"fact": f"value-{index}"}]},
                            f"call:{index}",
                        ),
                        UserPromptPart(f"World {index + 1} " + "w" * 5_000),
                    ]
                )
            )
    projected = pydantic_bridge._project_expired_history(
        tuple(messages),
        max_estimated_tokens=6_000,
    )
    projected_summary = projected[0]
    assert isinstance(projected_summary, ModelRequest)
    assert isinstance(projected_summary.parts[0], SystemPromptPart)
    assert projected_summary.parts[0].content.startswith("Summary of previous conversation:\n\n")
    scripted = ScriptedModel([ModelResponse(parts=[TextPart("## Verified facts\n- Stable generic fact.")])])

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            projected,
            model=scripted.build(),
            max_estimated_tokens=55_000,
            observed_estimated_tokens=999_999,
            timeout_s=2.0,
            trigger="history_pressure",
        )
    )

    call_ids = {
        part.tool_call_id
        for message in run.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }
    return_ids = {
        part.tool_call_id
        for message in run.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    pending_ids = {part.tool_call_id for part in pydantic_bridge._pending_tool_parts_from_history(run.messages)}

    assert run.error == ""
    assert return_ids == call_ids - pending_ids
    assert pending_ids == {"call:5"}
    canonical_envelope_module._project_pydantic_history(run.messages)


def test_compaction_summary_preserves_ref_shaped_semantics_and_incremental_prefix() -> None:
    summary = ModelRequest(
        parts=[
            SystemPromptPart("Summary of previous conversation:\n\n## Verified facts\n- Product code E23 is required.")
        ]
    )

    projected = pydantic_bridge._canonicalize_compaction_summaries((summary,))

    assert isinstance(projected[0], ModelRequest)
    part = projected[0].parts[0]
    assert isinstance(part, SystemPromptPart)
    assert part.content.startswith("Summary of previous conversation:\n\n")
    assert "Product code E23 is required." in part.content
    legacy = replace(
        summary,
        parts=[SystemPromptPart("Summary of previous conversation: ## Verified facts - stable value")],
    )
    migrated = pydantic_bridge._canonicalize_compaction_summaries((legacy,))
    assert isinstance(migrated[0], ModelRequest)
    migrated_part = migrated[0].parts[0]
    assert isinstance(migrated_part, SystemPromptPart)
    assert migrated_part.content.startswith("Summary of previous conversation:\n\n")


@given(turns=st.integers(min_value=5, max_value=12))
@settings(max_examples=12)
def test_harness_compaction_keeps_an_exact_pair_safe_suffix_and_pending_call(
    turns: int,
) -> None:
    history = _official_history_with_pending_actions(turns)
    model = ScriptedModel([ModelResponse(parts=[TextPart(f"summary for {turns} turns")])]).build()

    run = asyncio.run(
        pydantic_bridge._compact_pydantic_history(
            history,
            model=model,
            max_estimated_tokens=1,
            timeout_s=2.0,
        )
    )

    assert run.error == ""
    _assert_summary_keeps_task_anchor_and_exact_suffix(run.messages, history)
    assert pydantic_bridge._pending_call_from_history(run.messages) == ToolCall(
        "activate",
        {"target": f"E{turns - 1}"},
        f"call:{turns - 1}",
    )
    canonical_envelope_module._project_pydantic_history(run.messages)


def test_recording_model_receives_same_tool_cursor_page_as_direct_same_call_result() -> None:
    async def scenario() -> None:
        source_id = "source:long-reviews"
        targets = tuple(
            SemanticTarget(
                f"review:{index}",
                "listitem",
                f"Reviewer {index}: " + "深🙂" * 500,
            )
            for index in range(25)
        )
        fused = WorldFusion().fuse(
            (
                SurfaceObservation(
                    source_id,
                    "dom",
                    "revision:long-reviews",
                    ObservationSourceProfile.dom(),
                    targets,
                    (),
                ),
            )
        )
        assert fused.observation is not None
        world = fused.observation
        task = TaskGoal("read-long-reviews", "Inspect every review")
        evaluation = TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "more review pages remain",
        )
        builder = ContextBuilder()
        first_context = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            evaluation,
        )
        assert first_context.region_index.regions
        region = first_context.region_index.regions[0]
        region_ref = first_context.canonical_world.region_refs[region.key]
        scripted = ScriptedModel([("read_region", {"region_ref": region_ref})])
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:long-page-1", first_context))

        assert first.failure is None and first.output is not None
        assert isinstance(first.output.decision, ReadRegionResult)
        cursor = str(first.output.decision.result["next_cursor"])
        assert cursor
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        first_transition = ObservationDeliveryStore().reduce(first_step, step_index=1)
        assert not hasattr(first_transition.next_store, "public_result_inventory")
        scripted.decisions.extend(
            [
                ("read_region", {"region_ref": region_ref, "cursor": cursor}),
                (
                    "submit_final_response",
                    {"content": "Review pages inspected."},
                ),
            ]
        )
        second_context = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            evaluation,
            last_step=first_step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:long-page-2", second_context, last_step=first_step)
        )

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, ReadRegionResult)
        assert second.output.decision.arguments == {"region_ref": region_ref, "cursor": cursor}
        assert second.output.decision.result["items"]
        assert second.output.decision.result["items"] != first.output.decision.result["items"]
        second_step = StepResult(
            second.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_transition = first_transition.next_store.reduce(second_step, step_index=2)
        assert len(second_transition.next_store.local_deliveries) == 2
        assert all(not hasattr(item, "records") for item in second_transition.next_store.local_deliveries)
        third_context = builder.build(
            task,
            world,
            ActionSpace(world.observation_id, ()),
            evaluation,
            last_step=second_step,
        )
        third = await policy.port.generate(
            ModelDecisionRequest("request:long-finish", third_context, last_step=second_step)
        )

        assert third.failure is None and third.output is not None
        assert isinstance(third.output.decision, FinalResponse)
        assert policy.port.last_history_compaction_status == "not_triggered"
        recorded = normalize_recorded_provider_input(scripted.records[2])
        call = recorded["messages"][-2]["parts"][0]
        returned = recorded["messages"][-1]["parts"][0]
        assert call["part_kind"] == "tool-call"
        assert returned["part_kind"] == "tool-return"
        assert returned["tool_call_id"] == call["tool_call_id"]
        assert tuple(returned["content"]["items"]) == tuple(second.output.decision.result["items"])
        assert scripted.calls == 3

    asyncio.run(scenario())


def test_list_regions_returns_standard_call_correlated_tool_result() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("list-regions-tool-return", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                (
                    "submit_final_response",
                    {"content": "Region inventory received."},
                ),
            ]
        )
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:list-regions", first_context))
        assert first.failure is None and first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        second = await policy.port.generate(
            ModelDecisionRequest("request:list-regions-answer", second_context, last_step=step)
        )

        assert second.failure is None and second.output is not None
        assert isinstance(second.output.decision, FinalResponse)
        recorded = normalize_recorded_provider_input(scripted.records[1])
        call_part = recorded["messages"][-2]["parts"][0]
        return_part = recorded["messages"][-1]["parts"][0]
        assert call_part["tool_name"] == "list_regions"
        assert return_part["tool_call_id"] == call_part["tool_call_id"]
        assert return_part["content"]["kind"] == "Page"
        current_prompt = recorded["messages"][-1]["parts"][1]["content"][0]["content"]
        assert "latest_public_results" not in json.loads(current_prompt)
        physical = json.dumps(policy.port.envelope_history[1].physical_content(), default=str)
        assert "result_lineage" not in physical
        assert "record_digests" not in physical
        assert "origin_context_id" not in physical

    asyncio.run(scenario())


def test_unexpected_value_error_is_internal_not_invalid_tool_arguments() -> None:
    async def scenario() -> None:
        policy = _policy(ScriptedModel([ValueError("unexpected local invariant")]).build())
        task = shared_task()
        world = shared_world("unexpected-value-error", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:unexpected-value-error", context))

        assert result.output is None
        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INTERNAL_ERROR

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "fault_stage",
    (
        "delivery",
        "catalog",
        "envelope_bind",
        "schema_bind",
        "token_count",
        "admission",
        "provider_bind",
        "trace_record",
    ),
)
def test_pre_provider_ordinary_faults_are_total_and_never_attempt_provider(monkeypatch, fault_stage) -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world(f"pre-provider-{fault_stage}", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        def fail(*_args, **_kwargs):
            raise RuntimeError(f"synthetic {fault_stage} fault")

        if fault_stage == "delivery":
            monkeypatch.setattr(turn_packer_module, "build_model_turn_delivery", fail)
        elif fault_stage == "catalog":
            monkeypatch.setattr(turn_packer_module, "compile_grounded_action_catalog", fail)
        elif fault_stage == "envelope_bind":
            monkeypatch.setattr(canonical_envelope_module.CanonicalProviderEnvelopeBinder, "bind", fail)
        elif fault_stage == "schema_bind":
            monkeypatch.setattr(canonical_envelope_module, "CanonicalFunctionTool", fail)
        elif fault_stage == "token_count":
            monkeypatch.setattr(request_admission_module, "estimate_canonical_envelope", fail)
        elif fault_stage == "admission":
            monkeypatch.setattr(pydantic_bridge.RequestAdmission, "admit", fail)
        elif fault_stage == "provider_bind":
            monkeypatch.setattr(pydantic_bridge, "_pydantic_model_boundary_codec", fail)
        else:
            monkeypatch.setattr(pydantic_bridge.PydanticAIGroundedDecisionPort, "_record_attempt_started", fail)

        result = await policy.port.generate(ModelDecisionRequest(f"request:{fault_stage}", context))

        assert result.output is None
        assert result.failure is not None
        assert result.failure.kind is ModelFailureKind.INTERNAL_ERROR
        assert result.failure.attempt_origin is ProviderAttemptOrigin.LOCAL_RUNTIME
        assert result.attempts == ()
        assert result.diagnostics["pre_provider_failure"]["phase"] == "local_runtime"
        assert result.diagnostics["policy_model_call_count"] == 0
        assert policy.port.last_model_call_count == 0
        assert scripted.calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("fault_stage", "fault", "expected_kind"),
    (
        (
            "catalog",
            GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID),
            ModelFailureKind.SCHEMA_ERROR,
        ),
        (
            "admission",
            ModelRequestCapacityError(
                ModelRequestBreakdown(
                    "initial",
                    admission_action="context_capacity",
                    effective_input_limit=1,
                )
            ),
            ModelFailureKind.CONTEXT_CAPACITY,
        ),
    ),
)
def test_pre_provider_typed_schema_and_capacity_faults_remain_local(
    monkeypatch,
    fault_stage,
    fault,
    expected_kind,
) -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world(f"typed-pre-provider-{fault_stage}", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        def fail(*_args, **_kwargs):
            raise fault

        if fault_stage == "catalog":
            monkeypatch.setattr(turn_packer_module, "compile_grounded_action_catalog", fail)
        else:
            monkeypatch.setattr(pydantic_bridge.RequestAdmission, "admit", fail)

        result = await policy.port.generate(ModelDecisionRequest(f"request:typed-{fault_stage}", context))

        assert result.failure is not None
        assert result.failure.kind is expected_kind
        assert result.failure.attempt_origin is ProviderAttemptOrigin.LOCAL_RUNTIME
        assert policy.port.last_model_call_count == 0
        assert scripted.calls == 0

    asyncio.run(scenario())


def test_pending_official_exchange_survives_pre_provider_capacity_rejection(monkeypatch) -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("pending-capacity", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(task, world, actions, evaluation)
        scripted = ScriptedModel([("list_regions", {})])
        policy = _policy(scripted.build())

        first = await policy.port.generate(ModelDecisionRequest("request:pending-first", first_context))
        assert first.failure is None and first.output is not None
        step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        history_before = policy.port.message_history

        def reject(*_args, **_kwargs):
            raise ModelRequestCapacityError(
                ModelRequestBreakdown(
                    "initial",
                    admission_action="context_capacity",
                    effective_input_limit=1,
                )
            )

        monkeypatch.setattr(pydantic_bridge.RequestAdmission, "admit", reject)
        second = await policy.port.generate(
            ModelDecisionRequest("request:pending-rejected", second_context, last_step=step)
        )

        assert second.output is None
        assert second.failure is not None
        assert second.failure.kind is ModelFailureKind.CONTEXT_CAPACITY
        assert second.attempts == ()
        assert policy.port.last_model_call_count == 0
        assert scripted.calls == 1
        assert policy.port.message_history is history_before
        assert policy.port.message_history == history_before

    asyncio.run(scenario())


def test_native_action_policy_keeps_deliberate_profile_for_active_recovery_epoch() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action", "first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("recovery", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "grounding_stall",
                "stable_signature": "generic:recovery:1",
                "recovery_attempt": 1,
            },
        )

        first = await policy.port.generate(ModelDecisionRequest("request:deliberate-1", context))
        assert first.output is not None
        committed = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="provider_free_committed_action",
        )
        next_context = replace(context, last_step=committed)
        second = await policy.port.generate(
            ModelDecisionRequest("request:deliberate-2", next_context, last_step=committed)
        )

        assert first.attempts[0].phase == "deliberate"
        assert first.attempts[0].trigger == "grounding_gap"
        assert first.attempts[0].thinking_requested == "enabled"
        assert first.attempts[0].max_output_tokens == 4096
        assert second.attempts[0].phase == "deliberate"
        assert second.attempts[0].trigger == "grounding_gap"
        assert second.attempts[0].thinking_requested == "enabled"
        assert second.attempts[0].max_output_tokens == 4096
        assert [settings["max_tokens"] for settings in scripted.model_settings] == [4096, 4096]

    asyncio.run(scenario())


def test_native_action_policy_uses_one_bounded_review_at_a_collection_evidence_boundary() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("collection-evidence-boundary", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        read_result = ReadRegionResult(
            context.context_id,
            "read_region",
            {"region_ref": "R1"},
            {
                "kind": "Opened",
                "items": ({"kind": "complete_item", "content": ({"text": "record"},)},),
                "has_more": False,
                "next_cursor": None,
                "source_coverage": "partial",
                "region_membership": "complete",
                "result_page": "1/1",
                "scope": {"role": "list", "heading": "Results"},
            },
        )
        committed = StepResult(
            read_result,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        next_context = replace(context, last_step=committed)

        result = await policy.port.generate(
            ModelDecisionRequest("request:evidence-review", next_context, last_step=committed)
        )

        assert result.output is not None
        assert result.attempts[0].phase == "deliberate"
        assert result.attempts[0].trigger == "evidence_review"
        assert result.attempts[0].thinking_requested == "enabled"
        assert result.attempts[0].max_output_tokens == 2048
        assert [settings["max_tokens"] for settings in scripted.model_settings] == [2048]

    asyncio.run(scenario())


def test_native_action_policy_deliberates_for_a_new_later_recovery_event() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action", "first_gui_action"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("later-recovery", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        base_context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        first_context = replace(
            base_context,
            control_feedback={
                "kind": "strategy_review",
                "stable_signature": "route:first",
                "recovery_attempt": 1,
            },
        )
        second_context = replace(
            base_context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "control:second",
                "recovery_attempt": 2,
            },
        )

        first = await policy.port.generate(ModelDecisionRequest("request:recovery:first", first_context))
        assert first.output is not None
        committed = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="provider_free_committed_action",
        )
        second = await policy.port.generate(
            ModelDecisionRequest(
                "request:recovery:second",
                replace(second_context, last_step=committed),
                last_step=committed,
            )
        )

        assert first.attempts[0].phase == "deliberate"
        assert first.attempts[0].trigger == "operational_stall"
        assert second.attempts[0].phase == "deliberate"
        assert second.attempts[0].trigger == "control_stall"
        assert [settings["max_tokens"] for settings in scripted.model_settings] == [4096, 4096]

    asyncio.run(scenario())


def test_deepseek_deliberate_attempt_records_returned_reasoning() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ThinkingPart("The previous route is exhausted, so inspect the current regions."),
                        ToolCallPart("list_regions", {}, "recording-call:deliberate"),
                    ],
                    usage=RequestUsage(
                        input_tokens=20,
                        output_tokens=8,
                        details={"reasoning_tokens": 3},
                    ),
                    provider_response_id="recording-response:deliberate",
                )
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        world = shared_world("deepseek-reasoning-observation", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "grounding_stall",
                "stable_signature": "deepseek:reasoning:1",
                "recovery_attempt": 1,
            },
        )

        result = await port.generate(ModelDecisionRequest("request:deepseek-reasoning", context))

        assert result.failure is None and result.output is not None
        attempt = result.attempts[0]
        assert attempt.phase == "deliberate"
        assert attempt.thinking_requested == "enabled"
        assert attempt.thinking_effective == "enabled"
        assert attempt.reasoning_content_present is True
        assert attempt.reasoning_tokens == 3
        assert attempt.final_content_tokens == 5
        assert attempt.transcript["llm.output.reasoning_content_present"] is True
        assert attempt.transcript["llm.token_count.reasoning"] == 3
        assert attempt.transcript["llm.token_count.final_content"] == 5

    asyncio.run(scenario())


def test_deepseek_deliberate_output_retry_records_each_reasoning_response() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ThinkingPart("The route needs reconsideration."),
                        TextPart("I should use a current tool."),
                    ],
                    usage=RequestUsage(
                        input_tokens=20,
                        output_tokens=7,
                        details={"reasoning_tokens": 2},
                    ),
                    provider_response_id="recording-response:deliberate-invalid",
                ),
                ModelResponse(
                    parts=[
                        ToolCallPart("list_regions", {}, "recording-call:deliberate-retry"),
                    ],
                    usage=RequestUsage(
                        input_tokens=24,
                        output_tokens=5,
                    ),
                    provider_response_id="recording-response:deliberate-accepted",
                ),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        world = shared_world("deepseek-reasoning-output-retry", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "deepseek:reasoning:retry",
                "recovery_attempt": 1,
            },
        )

        result = await port.generate(ModelDecisionRequest("request:deepseek-reasoning-retry", context))

        assert result.failure is None and result.output is not None
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert [attempt.phase for attempt in result.attempts] == [
            "deliberate",
            "deliberate_output_retry",
        ]
        assert [record.model_settings["tool_choice"] for record in scripted.records] == [
            "auto",
            "required",
        ]
        assert [attempt.reasoning_content_present for attempt in result.attempts] == [True, False]
        assert [attempt.reasoning_tokens for attempt in result.attempts] == [2, 0]
        assert [attempt.final_content_tokens for attempt in result.attempts] == [5, 5]
        assert [attempt.thinking_effective for attempt in result.attempts] == ["enabled", "disabled"]
        assert [attempt.transcript["llm.model_settings"]["thinking"] for attempt in result.attempts] == [
            True,
            False,
        ]

    asyncio.run(scenario())


def test_deepseek_deliberate_length_retries_with_one_nonthinking_required_action() -> None:
    async def scenario() -> None:
        checkpoint = (
            "The complete positive set already supported by the current evidence must be preserved. "
            + ('intermediate "reasoning" \\ newline\n中 ' * 300)
            + "The next action should use the complete set without narrowing it."
        )
        truncated = ModelResponse(
            parts=[ThinkingPart(checkpoint)],
            usage=RequestUsage(
                input_tokens=20,
                output_tokens=2048,
                details={"reasoning_tokens": 2048},
            ),
            finish_reason="length",
            provider_response_id="recording-response:deliberate-length",
        )
        scripted = ScriptedModel(
            [
                truncated,
                ("list_regions", {}),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        world = shared_world("deepseek-reasoning-length-retry", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "deepseek:reasoning:length-retry",
                "recovery_attempt": 1,
            },
        )

        result = await port.generate(ModelDecisionRequest("request:deepseek-reasoning-length-retry", context))

        assert result.failure is None and result.output is not None
        assert result.output.decision.tool_call_id == "recording-call:2"
        assert scripted.calls == 2
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert [attempt.phase for attempt in result.attempts] == [
            "deliberate",
            "deliberate_output_retry",
        ]
        assert [attempt.output_failure_kind for attempt in result.attempts] == [
            StructuredOutputFailureKind.OUTPUT_TRUNCATED,
            None,
        ]
        assert [attempt.thinking_effective for attempt in result.attempts] == ["enabled", "disabled"]
        assert [attempt.final_tool_call_present for attempt in result.attempts] == [False, True]
        assert [record.model_settings["tool_choice"] for record in scripted.records] == ["auto", "required"]
        fallback_prompt = json.dumps(scripted.records[1].messages, default=str)
        assert "action_selection_recovery" in fallback_prompt
        assert "return exactly one complete offered tool call" in fallback_prompt
        assert "Complete any unfinished enumeration, classification, or record audit" in fallback_prompt
        assert "the truncation boundary never completes a set" in fallback_prompt
        assert "The complete positive set already supported" in fallback_prompt
        assert "The next action should use the complete set" in fallback_prompt
        assert "truncated reasoning omitted" in fallback_prompt
        checkpoint_payload = next(
            item
            for item in scripted.records[1].messages[0].parts[0].content
            if isinstance(item, str) and "action_selection_recovery" in item
        )
        projected = json.loads(checkpoint_payload)["action_selection_recovery"]["incomplete_reasoning_checkpoint"]
        assert (
            pydantic_bridge._json_string_payload_bytes(projected)
            <= pydantic_bridge._ACTION_SELECTION_RECOVERY_CHECKPOINT_MAX_JSON_BYTES
        )
        assert len(checkpoint_payload.encode("utf-8")) <= (pydantic_bridge._ACTION_SELECTION_RECOVERY_PROMPT_MAX_BYTES)
        assert "non-authoritative same-call reasoning" in checkpoint_payload
        assert pydantic_bridge._pending_call_from_history(port.message_history) == ToolCall(
            "list_regions",
            {},
            "recording-call:2",
        )
        official_history = json.dumps(port.message_history, default=str)
        assert "The complete positive set already supported" not in official_history
        assert "action_selection_recovery" not in official_history

    asyncio.run(scenario())


@given(
    fragment=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=0,
        max_size=96,
    ),
    repetitions=st.integers(min_value=0, max_value=160),
)
@settings(max_examples=100, deadline=None)
def test_reasoning_checkpoint_and_recovery_prompt_obey_the_wire_byte_contract(
    fragment: str,
    repetitions: int,
) -> None:
    reasoning = fragment * repetitions
    normalized_reasoning = reasoning.strip()
    messages = [
        {
            "kind": "response",
            "finish_reason": "length",
            "parts": [{"part_kind": "thinking", "content": reasoning}],
        }
    ]

    projected = pydantic_bridge._truncated_reasoning_checkpoint(messages)
    projected_bytes = pydantic_bridge._json_string_payload_bytes(projected)
    assert projected_bytes <= pydantic_bridge._ACTION_SELECTION_RECOVERY_CHECKPOINT_MAX_JSON_BYTES

    recovery_prompt = pydantic_bridge._pydantic_decision_recovery_prompt(
        [],
        reasoning_checkpoint=projected,
    )[-1]
    assert len(recovery_prompt.encode("utf-8")) <= (pydantic_bridge._ACTION_SELECTION_RECOVERY_PROMPT_MAX_BYTES)

    original_bytes = pydantic_bridge._json_string_payload_bytes(normalized_reasoning)
    if original_bytes <= pydantic_bridge._ACTION_SELECTION_RECOVERY_CHECKPOINT_MAX_JSON_BYTES:
        assert projected == normalized_reasoning
        return

    marker = "\n[...truncated reasoning omitted...]\n"
    tail_budget = (
        pydantic_bridge._ACTION_SELECTION_RECOVERY_CHECKPOINT_MAX_JSON_BYTES
        - pydantic_bridge._ACTION_SELECTION_RECOVERY_CHECKPOINT_HEAD_JSON_BYTES
        - pydantic_bridge._json_string_payload_bytes(marker)
    )
    assert projected == (
        pydantic_bridge._bounded_json_string_edge(
            normalized_reasoning,
            pydantic_bridge._ACTION_SELECTION_RECOVERY_CHECKPOINT_HEAD_JSON_BYTES,
            suffix=False,
        )
        + marker
        + pydantic_bridge._bounded_json_string_edge(normalized_reasoning, tail_budget, suffix=True)
    )


def test_length_recovery_preserves_the_single_current_operation_exposed_before_truncation() -> None:
    async def scenario() -> None:
        truncated = ModelResponse(
            parts=[
                TextPart("The current evidence is sufficient; return the selected operation."),
                ToolCallPart(
                    "list_regions",
                    {},
                    "recording-call:truncated-operation",
                ),
            ],
            usage=RequestUsage(input_tokens=20, output_tokens=1024),
            finish_reason="length",
            provider_response_id="recording-response:truncated-operation",
        )
        scripted = ScriptedModel(
            [
                truncated,
                ("read_region", {"region_ref": "R999"}),
                ("list_regions", {}),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        world = shared_world("truncated-operation-preservation", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await port.generate(ModelDecisionRequest("request:truncated-operation-preservation", context))

        assert result.failure is None and result.output is not None
        assert isinstance(result.output.decision, ReadRegionResult)
        assert result.output.decision.tool_name == "list_regions"
        assert result.output.decision.tool_call_id == "recording-call:3"
        assert scripted.calls == 3
        assert [attempt.status for attempt in result.attempts] == [
            "invalid",
            "invalid",
            "accepted",
        ]
        assert [record.model_settings["tool_choice"] for record in scripted.records] == [
            "auto",
            "required",
            "required",
        ]
        assert scripted.offered_tools == [
            scripted.offered_tools[0],
            ("list_regions",),
            ("list_regions",),
        ]
        for record in scripted.records[1:]:
            schema = record.function_tools[0].parameters_json_schema
            assert tuple(schema["properties"]) == ()
            assert tuple(schema["required"]) == ()
            prompt_text = json.dumps(record.messages, default=str)
            assert "representation_recovery" in prompt_text
            assert "selected_operation" in prompt_text
            assert "list_regions" in prompt_text
        retry_text = json.dumps(scripted.records[2].messages[-1], default=str)
        assert "Unknown tool name" in retry_text
        assert "list_regions" in retry_text
        retained = json.dumps(port.message_history, default=str)
        assert "recording-call:2" not in retained
        assert "R999" not in retained
        assert "representation_recovery" not in retained

    asyncio.run(scenario())


def test_length_recovery_executes_a_catalog_request_evidence_one_of_branch() -> None:
    async def scenario() -> None:
        arguments = {
            "purpose": "entity_discovery",
            "entity_query": "visible controls missing from structure",
            "max_results": 5,
        }
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        TextPart("Use the current visual evidence operation."),
                        ToolCallPart(
                            "request_evidence",
                            arguments,
                            "recording-call:truncated-evidence",
                        ),
                    ],
                    usage=RequestUsage(input_tokens=20, output_tokens=1024),
                    finish_reason="length",
                    provider_response_id="recording-response:truncated-evidence",
                ),
                ("request_evidence", arguments),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            observation_tool_profile=ObservationToolExposureProfile.DYNAMIC_VISUAL,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        base = shared_world("truncated-evidence-union", False)
        fused = WorldFusion().fuse(
            (replace(base.sources[0], coverage=CoverageState.TRUNCATED),)
        )
        assert fused.observation is not None
        world = fused.observation
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
            observation_capabilities=ObservationCapabilities(
                True,
                True,
                (
                    ObservationOffer(
                        "visual",
                        "visual",
                        "weak",
                        "high",
                        supported_purposes=(
                            ObservationPurpose.ENTITY_DISCOVERY,
                            ObservationPurpose.VISUAL_PROPERTY,
                            ObservationPurpose.POINT_GROUNDING,
                        ),
                    ),
                ),
            ),
        )

        result = await port.generate(ModelDecisionRequest("request:truncated-evidence-union", context))

        assert result.failure is None and result.output is not None
        assert result.output.decision.kind.value == "request_observation"
        assert result.output.decision.purpose is ObservationPurpose.ENTITY_DISCOVERY
        assert scripted.calls == 2
        assert scripted.offered_tools[1] == ("request_evidence",)
        projected = scripted.records[1].function_tools[0].parameters_json_schema
        assert "oneOf" in projected
        validate_parameter_schema_contract(projected)
        validate_value(arguments, projected)
        assert all("public_intent" not in branch["properties"] for branch in projected["oneOf"])

    asyncio.run(scenario())


def test_required_parameter_projection_is_a_valid_sublanguage_of_the_catalog_schema() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "record": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "identity": {"type": "string", "minLength": 1},
                    "annotation": {"type": "string"},
                },
                "required": ["identity"],
            },
            "optional_explanation": {"type": "string"},
        },
        "required": ["record"],
    }

    projected = pydantic_bridge._required_parameter_projection(schema)
    minimal = {"record": {"identity": "record-1"}}

    assert tuple(projected["properties"]) == ("record",)
    assert tuple(projected["required"]) == ("record",)
    assert "optional_explanation" in schema["properties"]
    validate_value(minimal, projected)
    validate_value(minimal, schema)
    with pytest.raises(ValueError, match="unknown semantic parameters"):
        validate_value(
            {**minimal, "optional_explanation": "not part of recovery"},
            projected,
        )


def test_required_parameter_projection_preserves_discriminated_catalog_union() -> None:
    schema = {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "purpose": {"type": "string", "enum": ["entity_discovery"]},
                    "entity_query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 32},
                    "public_intent": {"type": "string", "maxLength": 240},
                },
                "required": ["purpose", "entity_query", "max_results"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "purpose": {"type": "string", "enum": ["visual_property"]},
                    "subject_refs": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["E1", "E2"]},
                        "minItems": 1,
                        "maxItems": 2,
                    },
                    "predicate": {"type": "string", "minLength": 1, "maxLength": 500},
                    "public_intent": {"type": "string", "maxLength": 240},
                },
                "required": ["purpose", "subject_refs", "predicate"],
            },
        ],
    }

    projected = pydantic_bridge._required_parameter_projection(schema)
    discovery = {
        "purpose": "entity_discovery",
        "entity_query": "visible rating marks",
        "max_results": 5,
    }
    visual_property = {
        "purpose": "visual_property",
        "subject_refs": ["E1", "E2"],
        "predicate": "filled",
    }

    validate_parameter_schema_contract(projected)
    for value in (discovery, visual_property):
        validate_value(value, projected)
        validate_value(value, schema)
    for branch in projected["oneOf"]:
        assert "public_intent" not in branch["properties"]


@pytest.mark.parametrize(
    ("response", "offered_names", "expected"),
    [
        (
            {
                "kind": "response",
                "finish_reason": "length",
                "parts": [{"part_kind": "tool-call", "tool_name": "current_action"}],
            },
            frozenset({"current_action"}),
            "current_action",
        ),
        (
            {
                "kind": "response",
                "finish_reason": "stop",
                "parts": [{"part_kind": "tool-call", "tool_name": "current_action"}],
            },
            frozenset({"current_action"}),
            "",
        ),
        (
            {
                "kind": "response",
                "finish_reason": "length",
                "parts": [{"part_kind": "tool-call", "tool_name": "historical_action"}],
            },
            frozenset({"current_action"}),
            "",
        ),
        (
            {
                "kind": "response",
                "finish_reason": "length",
                "parts": [
                    {"part_kind": "tool-call", "tool_name": "first_action"},
                    {"part_kind": "tool-call", "tool_name": "second_action"},
                ],
            },
            frozenset({"first_action", "second_action"}),
            "",
        ),
    ],
)
def test_truncated_operation_anchor_requires_one_unambiguous_current_tool(
    response: dict[str, object],
    offered_names: frozenset[str],
    expected: str,
) -> None:
    assert (
        pydantic_bridge._truncated_current_tool_name(
            [response],
            offered_names=offered_names,
        )
        == expected
    )


def test_length_fallback_shares_one_transport_retry_budget(monkeypatch) -> None:
    async def scenario() -> None:
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", fake_sleep)
        truncated = ModelResponse(
            parts=[ThinkingPart("The current route needs one complete action.")],
            usage=RequestUsage(
                input_tokens=20,
                output_tokens=2048,
                details={"reasoning_tokens": 2048},
            ),
            finish_reason="length",
            provider_response_id="recording-response:shared-retry-length",
        )
        scripted = ScriptedModel(
            [
                ModelHTTPError(503, "initial transient"),
                truncated,
                ModelHTTPError(503, "fallback transient"),
                ("list_regions", {}),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
            provider_retry_backoff_s=0.25,
            max_provider_retry_delay_s=1.0,
        )
        task = shared_task()
        world = shared_world("shared-output-transport-retry", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "shared:output:transport:retry",
                "recovery_attempt": 1,
            },
        )

        result = await port.generate(ModelDecisionRequest("request:shared-output-transport-retry", context))

        assert result.failure is not None
        assert result.failure.reason == "model provider is unavailable"
        assert scripted.calls == 3
        assert len(scripted.decisions) == 1
        assert delays == [0.25]
        assert port.last_provider_retry_count == 1
        assert [attempt.status for attempt in result.attempts] == ["failed", "invalid", "failed"]
        assert [attempt.phase for attempt in result.attempts] == [
            "deliberate",
            "deliberate_provider_retry",
            "deliberate_output_retry",
        ]

    asyncio.run(scenario())


def test_pending_tool_return_is_delivered_once_when_deliberate_length_fallback_succeeds() -> None:
    async def scenario() -> None:
        truncated = ModelResponse(
            parts=[ThinkingPart("Reconsider the route before choosing the next tool.")],
            usage=RequestUsage(
                input_tokens=20,
                output_tokens=2048,
                details={"reasoning_tokens": 2048},
            ),
            finish_reason="length",
            provider_response_id="recording-response:pending-deliberate-length",
        )
        scripted = ScriptedModel(
            [
                ("list_regions", {}),
                truncated,
                ("list_regions", {}),
            ]
        )
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        world = shared_world("pending-deliberate-length", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        first_context = builder.build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        first = await port.generate(ModelDecisionRequest("request:pending-deliberate-length:first", first_context))
        assert first.failure is None and first.output is not None
        first_step = StepResult(
            first.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        second_context = builder.build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
            last_step=first_step,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "pending:deliberate:length-retry",
                "recovery_attempt": 1,
            },
        )

        second = await port.generate(
            ModelDecisionRequest("request:pending-deliberate-length:second", second_context, first_step)
        )

        assert second.failure is None and second.output is not None
        assert second.output.decision.tool_call_id == "recording-call:3"
        assert [attempt.status for attempt in second.attempts] == ["invalid", "accepted"]
        assert [attempt.thinking_effective for attempt in second.attempts] == ["enabled", "disabled"]
        assert pydantic_bridge._pending_call_from_history(port.message_history) == ToolCall(
            "list_regions",
            {},
            "recording-call:3",
        )
        # OpenAI-compatible requests are stateless: both physical requests
        # replay the same logical context.  Each payload therefore contains
        # the pending return once, while official accepted history commits it
        # only once.
        for record in scripted.records[1:3]:
            provider_input = normalize_recorded_provider_input(record)
            returned = tuple(
                part
                for message in provider_input["messages"]
                for part in message["parts"]
                if part["part_kind"] == "tool-return"
            )
            assert len(returned) == 1
            assert returned[0]["tool_call_id"] == "recording-call:1"
        official_returns = tuple(
            part
            for message in port.message_history
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        )
        assert [(part.tool_name, part.tool_call_id) for part in official_returns] == [
            ("list_regions", "recording-call:1")
        ]
        canonical_envelope_module._project_pydantic_history(port.message_history)
        assert "Reconsider the route before choosing the next tool." not in json.dumps(
            port.message_history,
            default=str,
        )

    asyncio.run(scenario())


@given(
    pending_result=st.booleans(),
    first_output=st.sampled_from(("text_only", "thinking_length")),
)
@settings(max_examples=4, deadline=None)
def test_logical_action_turn_generated_conserves_world_catalog_and_history(
    pending_result: bool,
    first_output: str,
) -> None:
    async def scenario() -> None:
        marker = f"rejected-{first_output}-must-remain-transcript-only"
        if first_output == "thinking_length":
            rejected = ModelResponse(
                parts=[ThinkingPart(marker)],
                usage=RequestUsage(
                    input_tokens=20,
                    output_tokens=2048,
                    details={"reasoning_tokens": 2048},
                ),
                finish_reason="length",
                provider_response_id=f"recording-response:{first_output}",
            )
        else:
            rejected = ModelResponse(
                parts=[ThinkingPart("bounded reasoning"), TextPart(marker)],
                usage=RequestUsage(
                    input_tokens=20,
                    output_tokens=8,
                    details={"reasoning_tokens": 2},
                ),
                finish_reason="stop",
                provider_response_id=f"recording-response:{first_output}",
            )
        decisions = [rejected, "first_gui_action"]
        if pending_result:
            decisions.insert(0, ("list_regions", {}))
        scripted = ScriptedModel(decisions)
        port = PydanticAIGroundedDecisionPort(
            model=scripted.build(),
            provider_id="deepseek",
            model_id="deepseek-v4-flash",
            endpoint_host="api.deepseek.com",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=4.0,
        )
        task = shared_task()
        world = shared_world(f"logical-turn-{pending_result}-{first_output}", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        actions = ActionSpaceBuilder().build(task, world)
        builder = ContextBuilder()
        context = builder.build(task, world, actions, evaluation)
        last_step = None
        if pending_result:
            first = await port.generate(ModelDecisionRequest("request:logical-turn:pending", context))
            assert first.failure is None and first.output is not None
            last_step = StepResult(
                first.output.decision,
                world,
                world,
                evaluation,
                feedback="local_tool_result",
            )
            context = builder.build(task, world, actions, evaluation, last_step=last_step)
        context = replace(
            context,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": f"logical-turn:{pending_result}:{first_output}",
                "recovery_attempt": 1,
            },
        )

        result = await port.generate(ModelDecisionRequest("request:logical-turn:action", context, last_step))

        assert result.failure is None and result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert result.output.decision.context_id == context.context_id
        assert len(port.last_admitted_envelopes) == 1
        envelope = port.last_admitted_envelopes[0]
        assert envelope.context_id == context.context_id
        assert envelope.delivery_id == port.last_model_delivery.delivery_id
        assert port.last_model_delivery.action_candidates.world_observation_id == world.observation_id
        assert [attempt.status for attempt in result.attempts] == ["invalid", "accepted"]
        assert [attempt.thinking_effective for attempt in result.attempts] == ["enabled", "disabled"]
        pending = pydantic_bridge._pending_call_from_history(port.message_history)
        assert pending is not None
        resolved = resolve_grounded_action_call(
            envelope.catalog,
            pending,
            expected_context_id=context.context_id,
            expected_delivery_id=envelope.delivery_id,
            expected_catalog_id=envelope.catalog.catalog_id,
        )
        assert resolved.decision.action_id == result.output.decision.action_id
        assert marker not in json.dumps(port.message_history, default=str)
        canonical_envelope_module._project_pydantic_history(port.message_history)
        for record in scripted.records[-2:]:
            returned = tuple(
                part
                for message in record.messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, ToolReturnPart)
            )
            assert len(returned) == int(pending_result)
        official_returns = tuple(
            part
            for message in port.message_history
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        )
        assert len(official_returns) == int(pending_result)

    asyncio.run(scenario())


def test_standalone_native_path_does_not_invent_a_context_only_final_response_turn() -> None:
    class OutputTaskEvaluator(SharedTaskEvaluator):
        async def evaluate(self, task, observation):
            evaluation = await super().evaluate(task, observation)
            if evaluation.status.value != "complete":
                return evaluation
            return replace(
                evaluation,
                outputs=(
                    EvaluatedOutput(
                        "answer",
                        "enabled",
                        (observation.facts[0].fact_id,),
                    ),
                ),
            )

    async def scenario() -> None:
        scripted = ScriptedModel([])
        policy = _policy(scripted.build())
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            OutputTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
        )
        task = replace(shared_task(), requested_outputs=("answer",))
        environment = ScriptedEnvironment(initial_observation=shared_world("complete", True))

        state = await runtime.run_task(environment, task)

        assert state.status is RunStatus.DONE
        assert state.execution_count == 0
        assert state.step_count == 0
        assert state.last_step is None
        assert scripted.offered_tools == []

    asyncio.run(scenario())


def test_pydantic_ai_ask_user_preserves_question_and_runtime_resume() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("ask_user", {"question": "Which value should I enter?", "requested_fields": ["value"]}),
                ("abort", {"reason": "resume observed", "category": "user_request"}),
            ]
        )
        runtime = _runtime(scripted.build())
        environment = ScriptedEnvironment(initial_observation=shared_world("before", False))
        task = shared_task()

        paused = await runtime.run_task(environment, task)

        assert paused.status is RunStatus.WAITING_USER
        assert paused.last_step is not None
        assert paused.last_step.decision.question == "Which value should I enter?"
        assert paused.last_step.decision.requested_fields == ("value",)

        resumed = await runtime.resume_user(
            environment,
            replace(task, inputs={"value": "provided"}, revision=2),
            paused,
        )

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.task_revision == 2
        assert scripted.calls == 2
        assert "provided" in repr(scripted.messages[-1])

    asyncio.run(scenario())


def test_pydantic_ai_rejects_repair_that_invents_missing_semantic_content() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                ("ask_user", {}),
                ("ask_user", {"question": "Which value?", "requested_fields": ["value"]}),
                ("ask_user", {"question": "Which value?", "requested_fields": ["value"]}),
            ]
        )
        environment = ScriptedEnvironment(initial_observation=shared_world("before", False))
        runtime = replace(_runtime(scripted.build()), episode_monitor=EpisodeMonitor())

        state = await runtime.run_task(environment, shared_task())

        assert state.status is RunStatus.WAITING_USER
        assert scripted.calls == 3
        assert "representation-only repaired tool call" in repr(scripted.messages)
        assert state.workspace.recent_steps
        assert state.workspace.recent_steps[0].semantic_action == "tool_rejected"
        assert scripted.records[2].model_settings["max_tokens"] == 4096

    asyncio.run(scenario())


def test_pydantic_ai_repairs_invalid_representation_without_changing_target() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(["first_gui_action_invalid_extra", "repeat_last_gui_call"])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("invalid-extra", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:invalid-extra", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, SelectAction)
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == ["ordinary", "representation_repair"]

    asyncio.run(scenario())


def test_representation_repair_accepts_new_provider_call_id_and_pairs_that_identity() -> None:
    async def scenario() -> None:
        initial_call_id = "provider-call:initial-invalid"
        repaired_call_id = "provider-call:representation-repair"
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_page_content",
                            {
                                "query": "Vinalhaven",
                                "cursor": "",
                                "region_ref": "R3",
                            },
                            initial_call_id,
                        )
                    ]
                ),
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_page_content",
                            {"query": "Vinalhaven"},
                            repaired_call_id,
                        )
                    ]
                ),
                ModelResponse(parts=[ToolCallPart("list_regions", {}, "provider-call:next-turn")]),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("repair-new-provider-call-id", False)
        actions = ActionSpaceBuilder().build(task, world)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        builder = ContextBuilder()
        context = builder.build(
            task,
            world,
            actions,
            evaluation,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:repair-new-call-id", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, SearchPageContentResult)
        assert result.output.decision.tool_call_id == repaired_call_id
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "representation_repair",
        ]
        pending = pydantic_bridge._pending_call_from_history(policy.port.message_history)
        assert pending == ToolCall(
            "search_page_content",
            {"query": "Vinalhaven"},
            repaired_call_id,
        )

        step = StepResult(
            result.output.decision,
            world,
            world,
            evaluation,
            feedback="local_tool_result",
        )
        next_context = builder.build(
            task,
            world,
            actions,
            evaluation,
            last_step=step,
        )
        next_result = await policy.port.generate(
            ModelDecisionRequest("request:after-repaired-call", next_context, last_step=step)
        )

        assert next_result.failure is None
        recorded = normalize_recorded_provider_input(scripted.records[2])
        returned_ids = {
            part["tool_call_id"]
            for message in recorded["messages"]
            if message["kind"] == "request"
            for part in message["parts"]
            if part["part_kind"] == "tool-return"
        }
        assert repaired_call_id in returned_ids
        assert initial_call_id not in returned_ids

    asyncio.run(scenario())


def test_representation_repair_prunes_invalid_empty_optional_cursor() -> None:
    async def scenario() -> None:
        repaired_call_id = "provider-call:empty-cursor-repair"
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_page_content",
                            {"query": "Shanksville", "cursor": "", "region_ref": "R14"},
                            "provider-call:empty-cursor-invalid",
                        )
                    ]
                ),
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "search_page_content",
                            {"query": "Shanksville"},
                            repaired_call_id,
                        )
                    ]
                ),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("repair-invalid-empty-cursor", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:repair-invalid-empty-cursor", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, SearchPageContentResult)
        assert result.output.decision.tool_call_id == repaired_call_id
        assert result.output.decision.arguments == {"query": "Shanksville"}
        assert [attempt.phase for attempt in result.attempts] == ["ordinary", "representation_repair"]

    asyncio.run(scenario())


def test_empty_first_page_cursor_is_accepted_once_and_canonicalized_by_the_tool_owner() -> None:
    async def scenario() -> None:
        task = shared_task()
        world = shared_world("empty-first-page-cursor", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )
        region = context.region_index.regions[0]
        region_ref = context.canonical_world.region_refs[region.key]
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "read_region",
                            {"region_ref": region_ref, "cursor": ""},
                            "provider-call:empty-first-page",
                        )
                    ]
                )
            ]
        )
        policy = _policy(scripted.build())

        result = await policy.port.generate(ModelDecisionRequest("request:empty-first-page-cursor", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, ReadRegionResult)
        assert result.output.decision.arguments == {"region_ref": region_ref}
        assert scripted.calls == 1
        assert [attempt.phase for attempt in result.attempts] == ["ordinary"]

    asyncio.run(scenario())


def test_final_response_prunes_non_contractual_world_fact_refs_without_losing_content() -> None:
    async def scenario() -> None:
        call_id = "recording-call:final-with-stale-ref"
        content = '{"task_type":"RETRIEVE","status":"SUCCESS","retrieved_data":[{"value":287}]}'
        scripted = ScriptedModel(
            [
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "submit_final_response",
                            {"content": content, "evidence_refs": ["F408"]},
                            call_id,
                        )
                    ]
                ),
                ModelResponse(parts=[ToolCallPart("submit_final_response", {"content": content}, call_id)]),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("final-response-stale-ref", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:final-stale-ref", context))

        assert result.failure is None
        assert result.output is not None
        assert isinstance(result.output.decision, FinalResponse)
        assert result.output.decision.content == content
        assert result.output.decision.evidence_refs == ()
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "representation_repair",
        ]
        final_spec = next(tool for tool in scripted.records[0].function_tools if tool.name == "submit_final_response")
        assert set(final_spec.parameters_json_schema["properties"]) == {"content"}

    asyncio.run(scenario())


def test_webarena_contradictory_final_response_becomes_recoverable_same_call_rejection() -> None:
    async def scenario() -> None:
        codec = WebArenaVerifiedFinalResponseCodec()
        scripted = ScriptedModel(
            [
                (
                    "submit_final_response",
                    {
                        "response": {
                            "task_type": "RETRIEVE",
                            "status": "SUCCESS",
                            "retrieved_data": [],
                            "error_details": None,
                        }
                    },
                ),
                ("list_regions", {}),
                ("list_regions", {}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("webarena-final-cross-field-retry", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
            final_response_guidance=codec.model_guidance,
            final_response_contract=codec.model_tool_contract,
        )

        result = await policy.port.generate(ModelDecisionRequest("request:final-cross-field-reject", context))

        assert result.failure is None and result.output is not None
        rejected = result.output.decision
        assert isinstance(rejected, ToolRejectedResult)
        assert rejected.tool_call_id == "recording-call:1"
        assert rejected.result["kind"] == GroundedToolResolutionCode.INVALID_ARGUMENTS.value
        assert rejected.result["dispatch"] == "not_sent"
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "representation_repair",
        ]

        committed = StepResult(
            rejected,
            world,
            world,
            await SharedTaskEvaluator().evaluate(task, world),
            RunStatus.RUNNING,
            feedback="local_tool_result",
        )
        next_context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
            last_step=committed,
            control_feedback={
                "kind": "control_stall",
                "stable_signature": "recovery:final-response-contract",
                "recovery_attempt": 1,
            },
            final_response_guidance=codec.model_guidance,
            final_response_contract=codec.model_tool_contract,
        )
        recovered = await policy.port.generate(
            ModelDecisionRequest("request:final-cross-field-recover", next_context, committed)
        )

        assert recovered.failure is None and recovered.output is not None
        assert isinstance(recovered.output.decision, ReadRegionResult)
        assert scripted.calls == 3
        assert [attempt.phase for attempt in recovered.attempts] == ["deliberate"]
        recorded = normalize_recorded_provider_input(scripted.records[2])
        returns = tuple(
            part for message in recorded["messages"] for part in message["parts"] if part["part_kind"] == "tool-return"
        )
        assert len(returns) == 1
        assert returns[0]["tool_call_id"] == rejected.tool_call_id
        assert returns[0]["content"]["kind"] == GroundedToolResolutionCode.INVALID_ARGUMENTS.value
        assert returns[0]["content"]["dispatch"] == "not_sent"

    asyncio.run(scenario())


def test_representation_repair_cannot_change_effect_bearing_leaf_values() -> None:
    preserves = pydantic_bridge._repair_preserves_rejected_semantics
    invalid = GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    type_text = ToolSpec(
        "type_text",
        "fixture",
        {
            "type": "object",
            "properties": {"target": {"type": "string"}, "text": {"type": "string"}},
            "required": ["target", "text"],
            "additionalProperties": False,
        },
    )
    update_profile = ToolSpec(
        "update_profile",
        "fixture",
        {
            "type": "object",
            "properties": {
                "form_ref": {"type": "string"},
                "fields": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["target", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["form_ref", "fields"],
            "additionalProperties": False,
        },
    )

    assert not preserves(
        invalid,
        (ToolCall("type_text", {"target": "E1", "text": "original", "unexpected": True}),),
        ToolCall("type_text", {"target": "E1", "text": "CHANGED"}),
        (type_text,),
    )
    assert not preserves(
        invalid,
        (
            ToolCall(
                "update_profile",
                {"form_ref": "N1", "fields": [{"target": "E1", "value": "old"}]},
            ),
        ),
        ToolCall(
            "update_profile",
            {"form_ref": "N1", "fields": [{"target": "E1", "value": "new"}]},
        ),
        (update_profile,),
    )
    assert preserves(
        invalid,
        (ToolCall("type_text", {"target": "E1", "text": "same", "unexpected": True}),),
        ToolCall("type_text", {"target": "E1", "text": "same"}),
        (type_text,),
    )


def test_representation_repair_cannot_select_among_multiple_semantic_calls() -> None:
    first = ToolCall("read_region", {"region_ref": "R1"})
    second = ToolCall("search_page_content", {"query": "different operation"})
    specs = (
        ToolSpec(
            "read_region",
            "fixture",
            {
                "type": "object",
                "properties": {"region_ref": {"type": "string"}},
                "required": ["region_ref"],
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            "search_page_content",
            "fixture",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
    )

    assert not pydantic_bridge._repair_preserves_rejected_semantics(
        GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS),
        (first, second),
        second,
        specs,
    )


def test_representation_repair_cannot_delete_legal_optional_operands() -> None:
    spec = ToolSpec(
        "ask_user",
        "fixture",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "requested_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 32,
                },
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    )
    rejected = ToolCall(
        "ask_user",
        {
            "question": "Which value?",
            "requested_fields": ["account"],
            "unexpected": "x",
        },
    )

    assert not pydantic_bridge._repair_preserves_rejected_semantics(
        GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS),
        (rejected,),
        ToolCall("ask_user", {"question": "Which value?"}),
        (spec,),
    )
    assert pydantic_bridge._repair_preserves_rejected_semantics(
        GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS),
        (rejected,),
        ToolCall(
            "ask_user",
            {"question": "Which value?", "requested_fields": ["account"]},
        ),
        (spec,),
    )


def test_provider_repair_dropping_legal_optional_operand_becomes_same_call_rejection() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel(
            [
                (
                    "ask_user",
                    {
                        "question": "Which value?",
                        "requested_fields": ["account"],
                        "unexpected": {
                            "target_ref": "E9",
                            "request_id": "req:old",
                        },
                        "region_ref": "R8",
                    },
                ),
                ("ask_user", {"question": "Which value?"}),
            ]
        )
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("optional-operand-pruning", False)
        context = ContextBuilder().build(
            task,
            world,
            ActionSpaceBuilder().build(task, world),
            await SharedTaskEvaluator().evaluate(task, world),
        )

        result = await policy.port.generate(ModelDecisionRequest("request:optional-pruning", context))

        assert result.failure is None
        assert result.output is not None
        rejected = result.output.decision
        assert isinstance(rejected, ToolRejectedResult)
        assert rejected.tool_name == "tool_rejected"
        assert rejected.arguments == {
            "operation": "ask_user",
            "arguments": {
                "question": "Which value?",
                "requested_fields": ["account"],
                "unexpected": {
                    "target_ref": "E9",
                    "request_id": "req:old",
                },
                "region_ref": "R8",
            },
        }
        assert rejected.result["kind"] == GroundedToolResolutionCode.INVALID_ARGUMENTS.value
        assert rejected.result["dispatch"] == "not_sent"
        assert scripted.calls == 2
        assert [attempt.phase for attempt in result.attempts] == [
            "ordinary",
            "representation_repair",
        ]

        step = StepResult(
            rejected,
            world,
            world,
            await SharedTaskEvaluator().evaluate(task, world),
            feedback="local_tool_result",
        )
        projected = project_step_result(step)
        assert projected.semantic_summary["operation"] == "ask_user"
        assert projected.semantic_summary["arguments"] == {
            "question": "Which value?",
            "requested_fields": ["account"],
        }

        policy.port.close_deferred_call(step)
        closed_calls = tuple(
            part
            for message in policy.port.message_history
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart)
        )
        assert tuple(part.args for part in closed_calls) == (
            {
                "question": "Which value?",
                "requested_fields": ("account",),
            },
        )
        assert pydantic_bridge._canonicalize_completed_history(
            policy.port.message_history
        ) == policy.port.message_history

    asyncio.run(scenario())


def test_pydantic_ai_records_rate_limit_then_retries_once(monkeypatch) -> None:
    async def scenario() -> None:
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", fake_sleep)
        scripted = ScriptedModel(
            [
                ModelHTTPError(
                    429,
                    "scripted",
                    {"error": "redacted fixture body"},
                    headers={"Retry-After": "9"},
                ),
                "first_gui_action",
            ]
        )
        policy = _policy(scripted.build())
        environment = ScriptedEnvironment(
            initial_observation=shared_world("before", False),
            post_observations=(shared_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await TargetRuntime(
            AgentDecisionPorts(policy),
            SharedActionOutcomeProjector(),
            SharedTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_pydantic_test"),
        ).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert scripted.calls == 2
        assert delays == [5.0]
        assert policy.port.last_model_call_count == 2
        assert policy.port.last_provider_retry_count == 1
        assert policy.last_metadata is not None
        assert policy.last_metadata.rate_limit_retry_count == 1
        assert policy.last_metadata.transient_retry_count == 0
        attempts = policy.port.last_generation_attempts
        assert [item.phase for item in attempts] == ["ordinary", "ordinary_provider_retry"]
        assert all(item.role == "action_policy" for item in attempts)
        assert all(item.trigger == "ordinary" for item in attempts)
        assert all(item.thinking_requested == "disabled" for item in attempts)
        assert all(item.max_output_tokens == 1024 for item in attempts)
        assert [item.status for item in attempts] == ["failed", "accepted"]
        assert attempts[0].exception_class == "ModelHTTPError"
        assert attempts[0].transcript["error.code"] == "rate_limited"
        assert attempts[0].transcript["error.http_status"] == 429
        assert attempts[0].transcript["error.retry_after_s"] == 9.0
        assert "redacted fixture body" not in repr(attempts[0].transcript)

    asyncio.run(scenario())


def test_pydantic_ai_provider_classification_keeps_nonretryable_failures_typed() -> None:
    auth = pydantic_bridge._classify_provider_failure(ModelHTTPError(401, "scripted"))
    invalid = pydantic_bridge._classify_provider_failure(ModelHTTPError(422, "scripted"))
    unavailable = pydantic_bridge._classify_provider_failure(ModelHTTPError(503, "scripted"))

    assert (auth.code.value, auth.retryable) == ("authentication", False)
    assert (invalid.code.value, invalid.retryable) == ("invalid_request", False)
    assert (unavailable.code.value, unavailable.retryable) == ("unavailable", True)


def test_pydantic_ai_does_not_count_retry_cancelled_during_backoff(monkeypatch) -> None:
    async def scenario() -> None:
        port = PydanticAIGroundedDecisionPort(
            model=object(),
            provider_id="fixture",
            model_id="scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=2.0,
        )

        async def provider_call():
            raise ModelHTTPError(503, "scripted")

        async def cancelled_backoff(_delay: float) -> None:
            raise asyncio.CancelledError

        envelope = await _bound_envelope_for_port(port, "retry-backoff-envelope")
        monkeypatch.setattr(pydantic_bridge.asyncio, "sleep", cancelled_backoff)
        with pytest.raises(asyncio.CancelledError):
            await port._run_provider_call(
                provider_call,
                phase="initial",
                envelope=envelope,
                provider_error_type=ModelHTTPError,
            )

        assert port.last_model_call_count == 1
        assert port.last_provider_retry_count == 0
        assert len(port.last_generation_attempts) == 1

    asyncio.run(scenario())


def test_pydantic_ai_records_inflight_provider_cancellation() -> None:
    async def scenario() -> None:
        port = PydanticAIGroundedDecisionPort(
            model=object(),
            provider_id="fixture",
            model_id="scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            transport_timeout_s=2.0,
        )

        async def provider_call():
            raise asyncio.CancelledError

        envelope = await _bound_envelope_for_port(port, "inflight-cancellation")
        with pytest.raises(asyncio.CancelledError):
            await port._run_provider_call(
                provider_call,
                phase="initial_provider_retry",
                envelope=envelope,
                provider_error_type=ModelHTTPError,
            )

        assert port.last_model_call_count == 1
        attempt = port.last_generation_attempts[0]
        assert attempt.phase == "initial_provider_retry"
        assert attempt.status == "cancelled"
        assert attempt.exception_class == "CancelledError"
        assert attempt.transcript["network_dispatched"] is True
        assert attempt.transcript["error.code"] == "cancelled"

    asyncio.run(scenario())


def test_pydantic_ai_resolves_the_normalizer_call_not_the_raw_call(monkeypatch) -> None:
    normalized = ToolCall("activate_selector", {"grounding_ref": "E5"}, "call:1")
    resolved_decision = SearchPageContentResult(
        "context:test",
        normalized.name,
        normalized.arguments,
        {"kind": "Matches", "items": []},
        normalized.call_id,
    )
    monkeypatch.setattr(
        pydantic_bridge.ProviderCallNormalizer,
        "normalize",
        lambda *_args: ToolCallReconciliationResult(
            ToolCallReconciliationStatus.EXACT,
            exact_call=normalized,
        ),
    )
    captured = {}
    monkeypatch.setattr(
        pydantic_bridge,
        "resolve_grounded_action_call",
        lambda _catalog, call, **_kwargs: captured.setdefault(
            "resolution", SimpleNamespace(decision=resolved_decision)
        ),
    )
    output = DeferredToolRequests(calls=[ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1")])

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
    )

    assert exchange is not None
    assert exchange.call == normalized
    assert exchange.decision is resolved_decision
    assert len(exchange.response.parts) == 1
    assert error is None
    assert parsed == ()
    assert captured["resolution"].decision is resolved_decision


def test_multiple_deferred_calls_resolve_only_the_first_and_record_discarded_count(monkeypatch) -> None:
    normalized = ToolCall("read_region", {"region_ref": "R1"}, "call:1")
    resolved_decision = SearchPageContentResult(
        "context:test",
        normalized.name,
        normalized.arguments,
        {"kind": "Matches", "items": []},
        normalized.call_id,
    )
    normalized_calls = []
    resolved_calls = []

    def normalize(_self, call, _catalog):
        normalized_calls.append(call)
        return ToolCallReconciliationResult(
            ToolCallReconciliationStatus.EXACT,
            exact_call=normalized,
        )

    def resolve(_catalog, call, **_kwargs):
        resolved_calls.append(call)
        return SimpleNamespace(decision=resolved_decision)

    monkeypatch.setattr(pydantic_bridge.ProviderCallNormalizer, "normalize", normalize)
    monkeypatch.setattr(pydantic_bridge, "resolve_grounded_action_call", resolve)
    output = DeferredToolRequests(
        calls=[
            ToolCallPart("read_region", {"region_ref": "R1"}, "call:1"),
            ToolCallPart("search_page_content", {"query": "scope"}, "call:2"),
        ]
    )

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
    )

    assert exchange is not None
    assert exchange.call == normalized
    assert exchange.decision is resolved_decision
    assert exchange.discarded_call_count == 1
    assert [
        (part.tool_name, part.tool_call_id) for part in exchange.response.parts if isinstance(part, ToolCallPart)
    ] == [
        ("read_region", "call:1"),
        ("search_page_content", "call:2"),
    ]
    assert error is None
    assert parsed == ()
    assert normalized_calls == [ToolCall("read_region", {"region_ref": "R1"}, "call:1")]
    assert resolved_calls == [normalized]


def test_invalid_first_deferred_call_never_falls_through_to_a_later_call(monkeypatch) -> None:
    normalized_calls = []

    def normalize(_self, call, _catalog):
        normalized_calls.append(call)
        return SimpleNamespace(
            status=ToolCallReconciliationStatus.REPAIR_REQUIRED,
            issue_code="invalid_argument",
            field_paths=("parameters.region_ref",),
            argument_code="invalid_value",
        )

    monkeypatch.setattr(pydantic_bridge.ProviderCallNormalizer, "normalize", normalize)
    monkeypatch.setattr(
        pydantic_bridge,
        "resolve_grounded_action_call",
        lambda *_args, **_kwargs: pytest.fail("an invalid first call must not resolve or fall through"),
    )
    output = DeferredToolRequests(
        calls=[
            ToolCallPart("read_region", {"region_ref": "invalid"}, "call:1"),
            ToolCallPart("search_page_content", {"query": "scope"}, "call:2"),
        ]
    )

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(catalog_id="grounded-catalog:test", delivery_id="delivery:" + "d" * 64),
        "context:test",
    )

    assert exchange is None
    assert error is not None
    assert error.code is GroundedToolResolutionCode.INVALID_ARGUMENTS
    assert parsed == (ToolCall("read_region", {"region_ref": "invalid"}, "call:1"),)
    assert normalized_calls == [ToolCall("read_region", {"region_ref": "invalid"}, "call:1")]


def test_accepted_response_preserves_reasoning_and_records_canonical_call(monkeypatch) -> None:
    normalized = ToolCall("activate_selector", {"grounding_ref": "E5"}, "call:1")
    resolved_decision = SearchPageContentResult(
        "context:test",
        normalized.name,
        normalized.arguments,
        {"kind": "Matches", "items": []},
        normalized.call_id,
    )
    monkeypatch.setattr(
        pydantic_bridge.ProviderCallNormalizer,
        "normalize",
        lambda *_args: ToolCallReconciliationResult(
            ToolCallReconciliationStatus.EXACT,
            exact_call=normalized,
        ),
    )
    monkeypatch.setattr(
        pydantic_bridge,
        "resolve_grounded_action_call",
        lambda *_args, **_kwargs: SimpleNamespace(decision=resolved_decision),
    )
    narration = "I will click the next visible control now."
    source = ModelResponse(
        parts=[
            ThinkingPart("hidden chain " * 1_000),
            TextPart(narration),
            ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1"),
            ToolCallPart("discarded", {"target": "E99"}, "call:discarded"),
        ]
    )
    output = DeferredToolRequests(
        calls=[
            ToolCallPart("activate_constant", {"grounding_ref": "E5"}, "call:1"),
            ToolCallPart("discarded", {"target": "E99"}, "call:discarded"),
        ]
    )

    exchange, error, parsed = pydantic_bridge._resolve_deferred(
        output,
        SimpleNamespace(
            catalog_id="grounded-catalog:test",
            delivery_id="delivery:" + "d" * 64,
        ),
        "context:test",
        source_response=source,
    )

    assert exchange is not None
    assert error is None
    assert parsed == ()
    assert exchange.response is not source
    assert [type(part) for part in exchange.response.parts] == [
        ThinkingPart,
        TextPart,
        ToolCallPart,
        ToolCallPart,
    ]
    assert narration in repr(exchange.response)
    assert exchange.response.parts[:2] == tuple(source.parts[:2])
    assert exchange.response.parts[2].tool_call_id == normalized.call_id
    assert exchange.response.parts[2].tool_name == normalized.name
    assert exchange.response.parts[2].args == normalized.arguments
    assert exchange.response.parts[3].tool_name == source.parts[3].tool_name
    assert exchange.response.parts[3].tool_call_id == source.parts[3].tool_call_id
    assert exchange.response.parts[3].args == {}
    assert source.parts[3].args == {"target": "E99"}


def test_provider_metadata_cannot_preclaim_runtime_history_canonicalization() -> None:
    call = ToolCall("activate", {"target": "E1", "note": "keep"}, "call:x")
    source = ModelResponse(
        parts=[ToolCallPart(call.name, dict(call.arguments), call.call_id)],
        metadata={
            HISTORY_ARGUMENT_PATHS_METADATA_KEY: {call.call_id: (("target",),)},
            pydantic_bridge.HISTORY_CANONICAL_METADATA_KEY: True,
            "provider_marker": "keep",
        },
    )
    accepted_response = pydantic_bridge._accepted_model_response(
        source,
        call,
        proposed_calls=tuple(part for part in source.parts if isinstance(part, ToolCallPart)),
    )
    decision = SearchPageContentResult(
        "context:test",
        call.name,
        call.arguments,
        {"kind": "Matches", "items": []},
        call.call_id,
    )
    exchange = pydantic_bridge.AcceptedToolExchange(
        call,
        decision,
        accepted_response,
        argument_paths_by_call=((call.call_id, (("target",),)),),
    )
    history = (
        pydantic_bridge._history_response(exchange),
        ModelRequest(parts=[_history_return(call.name, {"status": "stable"}, call.call_id)]),
    )

    projected = pydantic_bridge._canonicalize_completed_history(history)
    response = projected[0]

    assert isinstance(response, ModelResponse)
    assert response.metadata == {
        "provider_marker": "keep",
        pydantic_bridge.HISTORY_CANONICAL_METADATA_KEY: True,
    }
    assert tuple(part.args for part in response.parts if isinstance(part, ToolCallPart)) == (
        {"note": "keep"},
    )


def test_zhipu_pydantic_ai_factory_is_selected_by_wire_capability() -> None:
    base = {
        "LLM_ACTIVE_PROFILE": "zhipu",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
        "LLM_ZHIPU_BASE_URL": "https://example.invalid/v1",
        "LLM_ZHIPU_API_KEY": "fixture-secret",
        "LLM_ZHIPU_MODEL": "glm-4.7-flash",
        "LLM_DECISION_PERCEPTION": "text-only.v1",
    }

    policy = zhipu_pydantic_ai_policy_from_environment(base, call_timeout_s=5.0)

    assert policy.port.provider_id == "zhipu"
    assert policy.port.model_id == "glm-4.7-flash"
    assert policy.port.supports_multimodal is False
    assert type(policy.port.model).__name__ == "ZaiModel"
    assert policy.port.transport_timeout_s == 2.0
    assert policy.port.policy_timeout_s == 5.0
    assert policy.port.max_provider_retry_delay_s == 0.5
    assert policy.port.history_compaction_timeout_s == 2.0
    assert policy.port.model._provider.client.timeout == 2.0
    prepared, _ = policy.port.model.prepare_request(
        {
            "thinking": False,
            "max_tokens": policy.port.reasoning_policy.repair().max_output_tokens,
            "temperature": 0.0,
            "parallel_tool_calls": False,
        },
        ModelRequestParameters(),
    )
    assert prepared["extra_body"]["thinking"]["type"] == "disabled"
    assert prepared["max_tokens"] == 512
    assert prepared["temperature"] == 0.0
    assert prepared["parallel_tool_calls"] is False

    selected = model_policy_from_environment(
        {**base, "LLM_ACTION_POLICY_WIRE_CAPABILITY": "native_single_tool"},
        call_timeout_s=5.0,
    )
    assert isinstance(selected.port, PydanticAIGroundedDecisionPort)

    with pytest.raises(ValueError, match="WIRE_CAPABILITY"):
        model_policy_from_environment(
            {**base, "LLM_ACTION_POLICY_WIRE_CAPABILITY": "json_single_command"},
            call_timeout_s=5.0,
        )


def test_zhipu_visual_model_capability_matches_provider_transport() -> None:
    policy = zhipu_pydantic_ai_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "zhipu",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            "LLM_ZHIPU_BASE_URL": "https://example.invalid/v1",
            "LLM_ZHIPU_API_KEY": "fixture-secret",
            "LLM_ZHIPU_MODEL": "glm-4.1v-thinking-flashx",
            "LLM_DECISION_PERCEPTION": "screenshot-ax.v1",
        },
        call_timeout_s=5.0,
    )

    assert policy.port.supports_multimodal is True


def test_compaction_and_provider_recovery_fit_one_policy_deadline() -> None:
    compaction, retry, transport = pydantic_bridge._provider_time_budgets(90.0)

    assert (compaction, retry, transport) == (42.25, 5.0, 42.25)
    assert retry + (2 * transport) + 0.5 == 90.0
    assert (
        pydantic_bridge._remaining_action_attempt_timeout(
            deadline_s=89.5,
            now_s=0.0,
            retry_delay_reserve_s=retry,
            maximum_timeout_s=transport,
        )
        == 42.25
    )
    # run25's final compactor used 23 seconds. The old static partition still
    # limited each action attempt to 21.125 seconds; deadline propagation gives
    # both remaining attempts 30.75 seconds without exceeding the same total.
    assert (
        pydantic_bridge._remaining_action_attempt_timeout(
            deadline_s=89.5,
            now_s=23.0,
            retry_delay_reserve_s=retry,
            maximum_timeout_s=transport,
        )
        == 30.75
    )


def test_pydantic_ai_factory_selects_separate_aliyun_profile() -> None:
    policy = zhipu_pydantic_ai_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "aliyun",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            "LLM_ALIYUN_BASE_URL": "https://aliyun.invalid/compatible-mode/v1",
            "LLM_ALIYUN_API_KEY": "fixture-secret",
            "LLM_ALIYUN_MODEL": "glm-5.2",
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=5.0,
    )

    assert policy.port.provider_id == "aliyun"
    assert policy.port.model_id == "glm-5.2"
    assert policy.port.endpoint_host == "aliyun.invalid"
    assert policy.port.supports_multimodal is False
    assert type(policy.port.model).__name__ == "ZaiModel"


@pytest.mark.parametrize(
    ("profile", "prefix", "base_url", "model_id"),
    (
        ("mistral", "LLM_MISTRAL", "https://mistral.invalid/v1", "mistral-small"),
        ("gemini", "LLM_GEMINI", "https://gemini.invalid/v1beta/openai", "gemini-flash"),
    ),
)
def test_openai_compatible_profiles_use_the_single_pydantic_ai_policy(
    profile: str,
    prefix: str,
    base_url: str,
    model_id: str,
) -> None:
    policy = model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": profile,
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            f"{prefix}_BASE_URL": base_url,
            f"{prefix}_API_KEY": "fixture-secret",
            f"{prefix}_MODEL": model_id,
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=5.0,
    )

    assert isinstance(policy.port, PydanticAIGroundedDecisionPort)
    assert policy.port.provider_id == profile
    assert policy.port.model_id == model_id


def test_strategy_review_signal_goes_directly_to_one_deliberate_action_policy_call() -> None:
    async def scenario() -> None:
        scripted = ScriptedModel([("list_regions", {})])
        policy = _policy(scripted.build())
        task = shared_task()
        world = shared_world("direct-deliberate-recovery", False)
        evaluation = await SharedTaskEvaluator().evaluate(task, world)
        context = replace(
            ContextBuilder().build(
                task,
                world,
                ActionSpaceBuilder().build(task, world),
                evaluation,
            ),
            control_feedback={
                "kind": "strategy_review",
                "stable_signature": "route:second-distinct-failure",
                "recovery_attempt": 2,
                "observed_evidence": {"returned_to_prior_semantic_page": True},
            },
        )

        decision = await policy.decide(context)

        assert isinstance(decision, ReadRegionResult)
        assert scripted.calls == 1
        assert not hasattr(policy, "last_strategy_revision_invocation")
        assert not hasattr(policy.port, "revise_strategy")
        assert policy.port.last_call_profile is not None
        assert policy.port.last_call_profile.phase.value == "deliberate"
        assert [record.model_settings["max_tokens"] for record in scripted.records] == [4096]
        action_input = json.dumps(
            normalize_recorded_provider_input(scripted.records[0]),
            sort_keys=True,
        )
        assert "strategy_revision" not in action_input
        assert "route:second-distinct-failure" in action_input

    asyncio.run(scenario())


def test_local_openai_compatible_profile_uses_the_single_pydantic_ai_policy() -> None:
    policy = model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "local",
            "LLM_LOCAL_PROVIDER": "openai_compatible",
            "LLM_LOCAL_BASE_URL": "http://127.0.0.1:11434/v1",
            "LLM_LOCAL_MODEL": "qwen-test",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
        },
        call_timeout_s=5.0,
    )

    assert isinstance(policy.port, PydanticAIGroundedDecisionPort)
    assert policy.port.provider_id == "local"
    assert policy.port.model_id == "qwen-test"


def test_factory_selects_deepseek_pydantic_ai_profile_by_default() -> None:
    selected = model_policy_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "deepseek",
            "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY": "fixture-secret",
            "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
            "LLM_DECISION_PERCEPTION": "text-only.v1",
        },
        call_timeout_s=5.0,
    )

    assert isinstance(selected.port, PydanticAIGroundedDecisionPort)
    assert selected.port.provider_id == "deepseek"
    assert selected.port.model_id == "deepseek-v4-flash"
    assert selected.port.supports_multimodal is False
    assert selected.port.transport_timeout_s == 2.0
    assert selected.port.policy_timeout_s == 5.0
    assert selected.port.reasoning_policy.repair_max_tokens == 512
    assert selected.port.history_compaction_timeout_s == 2.0
    assert selected.port.model._provider.client.timeout == 2.0
    assert selected.port.model.settings == {
        "max_tokens": 1024,
        "temperature": 0.0,
        "thinking": False,
    }
    assert selected.port.model.profile["openai_chat_supports_max_completion_tokens"] is False
    assert selected.port.model.profile["openai_supports_tool_choice_required"] is True
    prepared, parameters = selected.port.model.prepare_request(
        {
            "thinking": False,
            "max_tokens": 1024,
            "temperature": 0.0,
            "parallel_tool_calls": False,
            "tool_choice": "required",
        },
        ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="fixture_action",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
            ]
        ),
    )
    assert prepared["tool_choice"] == "required"
    assert parameters.thinking is False
    with pytest.raises(ValueError, match="WIRE_CAPABILITY"):
        model_policy_from_environment(
            {
                "LLM_ACTIVE_PROFILE": "deepseek",
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "LLM_ACTION_POLICY_WIRE_CAPABILITY": "json_single_command",
            },
            call_timeout_s=5.0,
        )
