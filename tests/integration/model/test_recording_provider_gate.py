from __future__ import annotations

import asyncio
import io
from dataclasses import replace

import pytest

pytest.importorskip("pydantic_ai")

from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.pydantic_ai_bridge import PydanticAIGroundedDecisionPort
from affordance_runtime.world import ObservationMedia, ObservationMediaVariant, WorldFusion
from tests.support.agent.core_loop_support import (
    SharedActionOutcomeProjector,
    SharedTaskEvaluator,
    shared_task,
    shared_world,
)
from tests.support.model.recording_pydantic_model import (
    FrozenBoundaryObject,
    RecordingPydanticModel,
)


def _policy(recorder: RecordingPydanticModel, *, supports_multimodal: bool = False) -> ModelBackedAgentPolicy:
    model = recorder.build()
    assert isinstance(model, FunctionModel)
    return ModelBackedAgentPolicy(
        PydanticAIGroundedDecisionPort(
            model=model,
            provider_id="gate-0-fixture",
            model_id="recording-scripted",
            endpoint_host="fixture.invalid",
            supports_multimodal=supports_multimodal,
            perception_profile=(
                DecisionPerceptionProfile.SCREENSHOT_AX
                if supports_multimodal
                else DecisionPerceptionProfile.TEXT_ONLY
            ),
            transport_timeout_s=4.0,
        ),
        call_timeout_s=5.0,
    )


def _runtime(policy: ModelBackedAgentPolicy) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(policy),
        SharedActionOutcomeProjector(),
        SharedTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("gate_0_recording_provider"),
    )


def _one_action_environment(*, before=None) -> ScriptedEnvironment:
    return ScriptedEnvironment(
        initial_observation=before or shared_world("gate-0-before", False),
        post_observations=(shared_world("gate-0-after", True),),
        results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
    )


def _actual_public_text(record) -> str:
    assert len(record.messages) == 1
    request = record.messages[0]
    assert isinstance(request, ModelRequest)
    user_parts = [part for part in request.parts if isinstance(part, UserPromptPart)]
    assert len(user_parts) == 1
    content = user_parts[0].content
    if isinstance(content, str):
        return content
    return next(item for item in content if isinstance(item, str))


def test_gate_0_records_text_request_and_executes_one_current_tool_call_through_runtime() -> None:
    async def scenario() -> None:
        recorder = RecordingPydanticModel(["first_gui_action"], scripted_phases=["ordinary"])
        policy = _policy(recorder)

        state = await _runtime(policy).run_task(_one_action_environment(), shared_task())

        assert state.status is RunStatus.DONE
        assert state.execution_count == 1
        assert state.step_count == 1
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "recording-call:1"
        assert recorder.calls == 1
        record = recorder.records[0]
        assert (record.ordinal, record.scripted_phase) == (1, "ordinary")
        assert record.instructions
        assert record.instruction_parts is not None
        assert all(isinstance(item, FrozenBoundaryObject) for item in record.message_snapshot)
        assert _actual_public_text(record)
        assert record.function_tools
        assert tuple(tool.name for tool in record.function_tools) == tuple(
            spec.name for spec in policy.port.last_catalog_specs
        )
        assert all(tool.description and tool.parameters_json_schema["type"] == "object" for tool in record.function_tools)
        assert all(tool.strict is True for tool in record.function_tools)
        assert record.allow_text_output is True
        assert record.output_tools == ()
        assert record.model_request_parameters.field("output_mode") == "text"
        assert dict(record.model_settings or {}) == {
            "max_tokens": 1024,
            "temperature": 0.0,
            "parallel_tool_calls": False,
        }
        assert policy.port.last_model_call_count == 1
        assert len(policy.port.last_generation_attempts) == 1
        assert policy.port.last_generation_attempts[0].final_tool_call_present is True

    asyncio.run(scenario())


def test_gate_0_preserves_arbitrary_public_text_without_lexical_privacy_interpretation() -> None:
    async def scenario() -> None:
        public_text = "Customer fields: private_cursor observation_id raw_delta_lineage"
        task = replace(shared_task(), instruction=f"Enable shared state. {public_text}")
        recorder = RecordingPydanticModel(["first_gui_action"], scripted_phases=["ordinary"])

        state = await _runtime(_policy(recorder)).run_task(_one_action_environment(), task)

        assert state.status is RunStatus.DONE
        assert recorder.calls == 1
        actual_text = _actual_public_text(recorder.records[0])
        assert public_text in actual_text
        assert "private_cursor" in actual_text
        assert "observation_id" in actual_text
        assert "raw_delta_lineage" in actual_text

    asyncio.run(scenario())


@pytest.mark.parametrize("scripted", ["final_response", "zero_calls"])
def test_gate_0_text_or_no_tool_response_keeps_current_runtime_failure_algebra(scripted: str) -> None:
    async def scenario() -> None:
        recorder = RecordingPydanticModel([scripted], scripted_phases=["ordinary"])
        environment = ScriptedEnvironment(initial_observation=shared_world(f"gate-0-{scripted}", False))

        state = await _runtime(_policy(recorder)).run_task(environment, shared_task())

        assert recorder.calls == 1
        assert state.status is RunStatus.FAILED
        assert state.execution_count == 0
        assert state.policy_failure is not None
        assert state.policy_failure.kind is ModelFailureKind.SCHEMA_ERROR
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_gate_0_local_scripted_exception_uses_existing_typed_failure_path() -> None:
    async def scenario() -> None:
        recorder = RecordingPydanticModel(
            [ValueError("gate-0 local scripted exception")],
            scripted_phases=["ordinary"],
        )
        environment = ScriptedEnvironment(initial_observation=shared_world("gate-0-exception", False))

        state = await _runtime(_policy(recorder)).run_task(environment, shared_task())

        assert recorder.calls == 1
        assert state.status is RunStatus.FAILED
        assert state.execution_count == 0
        assert state.policy_failure is not None
        assert state.policy_failure.kind is ModelFailureKind.INTERNAL_ERROR
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_gate_0_records_actual_media_part_mime_and_bytes_identity() -> None:
    async def scenario() -> None:
        output = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(output, format="PNG")
        png = output.getvalue()
        media = ObservationMedia(
            "gate-0-screenshot",
            "screenshot",
            "image/png",
            png,
            capture_group_id="capture:gate-0",
            variant=ObservationMediaVariant.RAW,
            dimensions=(20, 20),
            coordinate_space_id="viewport:gate-0",
        )
        base = shared_world("gate-0-media-before", False)
        source = replace(base.sources[0], media=(media,))
        before = WorldFusion().fuse((source,)).observation
        assert before is not None
        recorder = RecordingPydanticModel(["first_gui_action"], scripted_phases=["ordinary"])

        state = await _runtime(_policy(recorder, supports_multimodal=True)).run_task(
            _one_action_environment(before=before),
            shared_task(),
        )

        assert state.status is RunStatus.DONE
        assert recorder.calls == 1
        request = recorder.records[0].messages[0]
        assert isinstance(request, ModelRequest)
        user_part = next(part for part in request.parts if isinstance(part, UserPromptPart))
        assert not isinstance(user_part.content, str)
        media_parts = [item for item in user_part.content if isinstance(item, BinaryContent)]
        assert len(media_parts) == 1
        assert media_parts[0].media_type == "image/png"
        assert media_parts[0].data == png
        assert media_parts[0].data is png

    asyncio.run(scenario())
