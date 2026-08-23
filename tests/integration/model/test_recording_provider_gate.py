from __future__ import annotations

import asyncio
import io
import json
import re
from dataclasses import replace

import pytest

pytest.importorskip("pydantic_ai")

from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import FunctionModel

import affordance_runtime.model.policy.canonical_provider_envelope as canonical_envelope_module
from affordance_runtime.actions import ActionBinding, ActionSpaceBuilder
from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.pydantic_ai_bridge import PydanticAIGroundedDecisionPort
from affordance_runtime.world import (
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
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
    FrozenBoundaryObject,
    RecordingPydanticModel,
    normalize_recorded_provider_input,
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


def _fanout_world(observation_id: str, enabled: bool, *, count: int = 84):
    base = shared_world(observation_id, enabled)
    source = base.sources[0]
    extras = tuple(
        SemanticTarget(
            f"zz-fanout-target-{index}",
            "button",
            f"Generated control {index:03d}",
            {"enabled": True},
        )
        for index in range(count - 1)
    )
    extra_bindings = tuple(
        ActionBinding(
            f"binding:{observation_id}:fanout:{index}",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            f"fingerprint:{observation_id}:fanout:{index}",
            target.target_id,
            target.target_id,
            "dom",
            "dom",
            "activate",
            "click",
            "local_reversible",
            ("shared_state_enabled",),
            {"type": "object", "properties": {}, "additionalProperties": False},
            {"selector": f"#private-fanout-{index}"},
        )
        for index, target in enumerate(extras)
    )
    extra_facts = tuple(
        StateFact(
            f"fact:{observation_id}:zz-fanout:{index}",
            target.target_id,
            "enabled",
            True,
            observation_id,
        )
        for index, target in enumerate(extras)
    )
    fused = WorldFusion().fuse((
        SurfaceObservation(
            source.observation_id,
            source.surface,
            source.revision,
            source.source_profile,
            (*source.targets, *extras),
            (*source.facts, *extra_facts),
            (*source.bindings, *extra_bindings),
        ),
    ))
    assert fused.observation is not None
    return fused.observation


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
        envelope = policy.port.last_admitted_envelopes[0]
        assert normalize_recorded_provider_input(record) == envelope.model_boundary_projection()
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
        projection = state.last_step.before_public_world
        assert projection is not None
        provider_payload = _actual_public_text(record) + json.dumps(
            to_json_compatible(policy.port.last_catalog_specs), ensure_ascii=False
        )
        provider_refs = set(re.findall(r"\b[ENFR][1-9][0-9]*\b", provider_payload))
        assert provider_refs
        assert provider_refs <= projection.public_refs

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
        policy = _policy(recorder, supports_multimodal=True)

        state = await _runtime(policy).run_task(
            _one_action_environment(before=before),
            shared_task(),
        )

        assert state.status is RunStatus.DONE
        assert recorder.calls == 1
        request = recorder.records[0].messages[0]
        envelope = policy.port.last_admitted_envelopes[0]
        assert normalize_recorded_provider_input(recorder.records[0]) == envelope.model_boundary_projection()
        assert isinstance(request, ModelRequest)
        user_part = next(part for part in request.parts if isinstance(part, UserPromptPart))
        assert not isinstance(user_part.content, str)
        media_parts = [item for item in user_part.content if isinstance(item, BinaryContent)]
        assert len(media_parts) == 1
        assert media_parts[0].media_type == "image/png"
        assert media_parts[0].data == png
        assert media_parts[0].data is png
        assert envelope.media[0].data == png
        assert envelope.media[0].mime_type == "image/png"
        assert envelope.media[0].dimensions == (20, 20)

    asyncio.run(scenario())


def test_gate_2_annotated_media_route_and_operand_role_reach_real_recording_boundary() -> None:
    async def scenario() -> None:
        output = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(output, format="JPEG")
        media = ObservationMedia(
            "gate-2-annotated-screenshot",
            "screenshot",
            "image/jpeg",
            output.getvalue(),
            (
                ObservationGroundingRegion(
                    "shared-toggle",
                    (1, 1, 5, 5),
                    1.0,
                    "viewport:gate-2",
                ),
            ),
            capture_group_id="capture:gate-2",
            variant=ObservationMediaVariant.RAW,
            dimensions=(20, 20),
            coordinate_space_id="viewport:gate-2",
        )
        base = shared_world("gate-2-media-before", False)
        before = WorldFusion().fuse((replace(base.sources[0], media=(media,)),)).observation
        assert before is not None
        recorder = RecordingPydanticModel(["first_gui_action"], scripted_phases=["ordinary"])
        policy = _policy(recorder, supports_multimodal=True)
        environment = _one_action_environment(before=before)

        state = await _runtime(policy).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert recorder.calls == 1
        envelope = policy.port.last_admitted_envelopes[0]
        assert normalize_recorded_provider_input(recorder.records[0]) == envelope.model_boundary_projection()
        assert len(envelope.media) == 1
        recorded_media = envelope.media[0]
        assert recorded_media.mime_type == "image/png"
        assert recorded_media.data.startswith(b"\x89PNG\r\n\x1a\n")
        assert recorded_media.dimensions == (20, 20)
        assert recorded_media.marks == (("E1", (1, 1, 5, 5)),)
        assert recorded_media.operand_roles == (("E1", ("source",)),)
        assert recorded_media.route_deltas == (("activate", "E1", ""),)
        assert tuple(
            (route.operation, route.source_ref, route.destination_ref)
            for route in envelope.catalog.manifest.action_routes
        ) == recorded_media.route_deltas
        assert len(environment.executed_requests) == 1
        bound = environment.executed_requests[0]
        assert bound.intent.semantic_action == "activate"
        assert bound.selection.target_id == "shared-toggle"
        assert bound.binding.binding_id.startswith("binding:")
        provider_payload = json.dumps(envelope.model_boundary_projection(), default=str)
        assert bound.binding.binding_id not in provider_payload
        assert bound.binding.payload["selector"] not in provider_payload

    asyncio.run(scenario())


def test_gate_3_media_bind_fault_is_local_total_and_never_reaches_function_model(monkeypatch) -> None:
    async def scenario() -> None:
        output = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(output, format="PNG")
        media = ObservationMedia(
            "gate-3-media-fault",
            "screenshot",
            "image/png",
            output.getvalue(),
            capture_group_id="capture:gate-3-fault",
            variant=ObservationMediaVariant.RAW,
            dimensions=(20, 20),
            coordinate_space_id="viewport:gate-3-fault",
        )
        base = shared_world("gate-3-media-fault", False)
        before = WorldFusion().fuse((replace(base.sources[0], media=(media,)),)).observation
        assert before is not None
        recorder = RecordingPydanticModel(["first_gui_action"])
        policy = _policy(recorder, supports_multimodal=True)

        def fail(_item):
            raise RuntimeError("synthetic media bind fault")

        monkeypatch.setattr(canonical_envelope_module, "_media_record", fail)
        state = await _runtime(policy).run_task(_one_action_environment(before=before), shared_task())

        assert state.status is RunStatus.FAILED
        assert recorder.calls == 0
        assert policy.port.last_model_call_count == 0
        assert policy.port.last_generation_attempts == ()
        assert policy.port.last_local_failure["exception_class"] == "RuntimeError"

    asyncio.run(scenario())


def test_gate_3_representation_repair_has_its_own_admitted_exact_envelope() -> None:
    async def scenario() -> None:
        recorder = RecordingPydanticModel(
            ["first_gui_action_invalid_extra", "repeat_last_gui_call"],
            scripted_phases=["ordinary", "representation_repair"],
        )
        policy = _policy(recorder)

        state = await _runtime(policy).run_task(_one_action_environment(), shared_task())

        assert state.status is RunStatus.DONE
        assert recorder.calls == 2
        envelopes = policy.port.last_admitted_envelopes
        assert len(envelopes) == 2
        assert tuple(normalize_recorded_provider_input(item) for item in recorder.records) == tuple(
            item.model_boundary_projection() for item in envelopes
        )
        assert envelopes[0].envelope_id != envelopes[1].envelope_id
        assert tuple(item.attempt_phase for item in envelopes) == ("ordinary", "representation_repair")
        assert tuple(item.phase for item in policy.port.last_generation_attempts) == (
            "ordinary",
            "representation_repair",
        )

    asyncio.run(scenario())


def test_gate_2_two_turn_production_path_advances_store_and_records_new_suffix_routes() -> None:
    async def scenario() -> None:
        before = _fanout_world("gate-2-fanout-before", False)
        after = _fanout_world("gate-2-fanout-after", True)
        recorder = RecordingPydanticModel(
            [("action_results_next_page", {}), "first_gui_action"],
            scripted_phases=["continuation", "ordinary"],
        )
        environment = ScriptedEnvironment(
            initial_observation=before,
            post_observations=(after,),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        policy = _policy(recorder)

        state = await _runtime(policy).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert state.execution_count == 1
        assert recorder.calls == 2
        assert "action_results_next_page" in recorder.offered_tools[0]
        first = json.loads(_actual_public_text(recorder.records[0]))["observation"]
        second = json.loads(_actual_public_text(recorder.records[1]))["observation"]
        first_routes = set(re.findall(r"rank=\d+ \[(E\d+)\]", first))
        second_routes = set(re.findall(r"rank=\d+ \[(E\d+)\]", second))
        assert first_routes
        assert second_routes
        assert second_routes - first_routes
        assert "action_results_next_page" in recorder.offered_tools[0]
        assert recorder.records[0].scripted_phase == "continuation"
        assert recorder.records[1].scripted_phase == "ordinary"
        envelopes = policy.port.envelope_history
        assert len(envelopes) == 2
        assert envelopes[0].envelope_id != envelopes[1].envelope_id
        assert tuple(normalize_recorded_provider_input(item) for item in recorder.records) == tuple(
            item.model_boundary_projection() for item in envelopes
        )
        assert policy.port.last_generation_attempts[0].envelope_id == envelopes[-1].envelope_id
        assert recorder.calls == len(envelopes)
        recorded_public = "\n".join(
            _actual_public_text(record)
            + json.dumps(
                [tool.parameters_json_schema for tool in record.function_tools],
                default=str,
                ensure_ascii=False,
            )
            for record in recorder.records
        )
        assert before.observation_id not in recorded_public
        assert after.observation_id not in recorded_public
        action_ids = {
            item.action_id
            for item in ActionSpaceBuilder().build(shared_task(), before).options
        }
        assert all(item not in recorded_public for item in action_ids)

    asyncio.run(scenario())
