from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace

import pytest

pytest.importorskip("pydantic_ai")

import affordance_runtime.model.policy.pydantic_ai_bridge as bridge_module
from PIL import Image

from affordance_runtime.actions import ActionBinding, ActionSpaceBuilder
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent import RunStatus, SelectAction
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.grounded_tool_catalog import resolve_grounded_tool_call
from affordance_runtime.model.policy.request_admission import estimate_canonical_envelope
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.model.policy.turn_packer import TurnPacker
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from tests.integration.model.test_recording_provider_gate import (
    _one_action_environment,
    _policy,
    _runtime,
)
from tests.support.agent.core_loop_support import shared_task, shared_world
from tests.support.model.recording_pydantic_model import (
    FrozenBoundaryObject,
    FrozenMapping,
    RecordingPydanticModel,
    normalize_recorded_provider_input,
)


def _route_tuple(route) -> tuple[str, str, str]:
    return route.operation, route.source_ref, route.destination_ref


def _ordered_union(*groups) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    for group in groups:
        for item in group:
            value = item if isinstance(item, tuple) else _route_tuple(item)
            if value not in result:
                result.append(value)
    return tuple(result)


def _thaw_recorded(value):
    if isinstance(value, FrozenMapping):
        return {key: _thaw_recorded(item) for key, item in value.items_in_order}
    if isinstance(value, FrozenBoundaryObject):
        return {key: _thaw_recorded(item) for key, item in value.fields_in_order}
    if isinstance(value, tuple):
        return tuple(_thaw_recorded(item) for item in value)
    return value


class _BinaryTaskEvaluator:
    async def evaluate(self, task, observation):
        complete = observation.observation_id.endswith(":after")
        evidence = (observation.facts[0].fact_id,) if complete else ()
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE,
            "binary route completed" if complete else "binary route pending",
            completion_evidence_refs=evidence,
        )


class _BinaryOutcomeProjector:
    async def evaluate(self, task, before, request, result, after, public_world_delta):
        del task, result
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED,
            LocalPostconditionStatus.SATISFIED,
            EvidenceMethod.STRUCTURAL,
            "binary relation changed",
            (after.facts[0].fact_id,),
            public_world_delta=public_world_delta,
        )


def _binary_task() -> TaskGoal:
    return TaskGoal(
        "move-public-item",
        "Move the public item to its available destination",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def _binary_world(phase: str, *, marked_operand: str | None = None):
    observation_id = f"gate-4-binary:{phase}"
    source_target = SemanticTarget("private-source", "listitem", "短!", {"phase": phase})
    destination = SemanticTarget("private-destination", "region", "目标✓", {"phase": phase})
    binding = ActionBinding(
        f"binding:{observation_id}:private-long-lineage",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{observation_id}",
        source_target.target_id,
        source_target.target_id,
        "dom",
        "dom",
        "drag_to",
        "drag",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"selector": "#private-source", "destination_selector": "#private-destination"},
        destination_required=True,
        eligible_destination_ids=(destination.target_id,),
    )
    media = ()
    if marked_operand is not None:
        output = io.BytesIO()
        Image.new("RGB", (24, 16), "white").save(output, format="JPEG")
        marked_target = source_target if marked_operand == "source" else destination
        media = (
            ObservationMedia(
                f"binary-{marked_operand}",
                "screenshot",
                "image/jpeg",
                output.getvalue(),
                (
                    ObservationGroundingRegion(
                        marked_target.target_id,
                        (2, 2, 6, 6),
                        1.0,
                        "viewport:binary",
                    ),
                ),
                capture_group_id="capture:binary",
                variant=ObservationMediaVariant.RAW,
                dimensions=(24, 16),
                coordinate_space_id="viewport:binary",
            ),
        )
    structure = (
        ObservationStructureNode("root", "document", "Board", child_structure_ids=("source", "destination")),
        ObservationStructureNode(
            "source", "listitem", source_target.label, parent_structure_id="root",
            semantic_target_id=source_target.target_id,
        ),
        ObservationStructureNode(
            "destination", "region", destination.label, parent_structure_id="root",
            semantic_target_id=destination.target_id,
        ),
    )
    fused = WorldFusion().fuse((
        SurfaceObservation(
            observation_id,
            "dom",
            f"revision:{observation_id}",
            ObservationSourceProfile.dom(),
            (source_target, destination),
            (StateFact(f"fact:{observation_id}:done", source_target.target_id, "done", phase == "after", observation_id),),
            (binding,),
            media=media,
            structure=structure,
            structure_total_count=len(structure),
        ),
    ))
    assert fused.observation is not None
    return fused.observation


def _binary_runtime(policy) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(policy),
        _BinaryOutcomeProjector(),
        _BinaryTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("gate_4_binary"),
    )


def test_gate_4_ordered_request_and_response_conservation_through_real_runtime(monkeypatch) -> None:
    async def scenario() -> None:
        packed_turns = []
        production_packer = TurnPacker

        class RecordingTurnPacker:
            def pack(self, *args, **kwargs):
                packed = production_packer().pack(*args, **kwargs)
                packed_turns.append(packed)
                return packed

        monkeypatch.setattr(bridge_module, "TurnPacker", RecordingTurnPacker)
        recorder = RecordingPydanticModel(["first_schema_action"], scripted_phases=["ordinary"])
        policy = _policy(recorder)
        environment = _one_action_environment()

        state = await _runtime(policy).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert recorder.calls == 1
        assert len(packed_turns) == 1
        packed = packed_turns[0]
        envelope = policy.port.last_admitted_envelopes[0]
        record = recorder.records[0]
        assert packed.admitted_envelope.envelope is envelope
        assert packed.catalog is envelope.catalog
        assert normalize_recorded_provider_input(record) == envelope.model_boundary_projection()

        text_routes = tuple(_route_tuple(item) for item in packed.delivery.manifest.action_routes)
        media_routes = tuple(
            route
            for media in packed.delivery.media
            for route in (
                tuple(_route_tuple(item) for item in media.route_deltas)
            )
        )
        manifest_routes = tuple(_route_tuple(item) for item in envelope.catalog.manifest.action_routes)
        assert manifest_routes == _ordered_union(text_routes, media_routes)
        assert envelope.delivery_id == packed.delivery.delivery_id
        assert tuple(item.name for item in envelope.function_tools) == tuple(
            item.spec.name for item in packed.catalog.tools
        )
        assert tuple(
            (item.mime_type, item.digest, item.marks, item.operand_roles, item.route_deltas)
            for item in envelope.media
        ) == tuple(
            (
                item.mime_type,
                item.sha256,
                tuple((mark.ref, mark.bbox) for mark in item.actual_marks),
                tuple((mark.ref, tuple(role.value for role in mark.operand_roles)) for mark in item.actual_marks),
                tuple(_route_tuple(route) for route in item.route_deltas),
            )
            for item in packed.delivery.media
        )

        assert recorder.last_gui_call is not None
        tool_name, arguments = recorder.last_gui_call
        recorded_tool = next(item for item in record.function_tools if item.name == tool_name)
        recorded_schema = to_json_compatible(_thaw_recorded(recorded_tool.parameters_json_schema))
        validate_value(arguments, recorded_schema, path="provider_call")
        resolution = resolve_grounded_tool_call(
            packed.catalog,
            ToolCall(tool_name, arguments, "recording-call:1"),
            expected_context_id=packed.catalog.context_id,
            expected_delivery_id=packed.delivery.delivery_id,
            expected_catalog_id=packed.catalog.catalog_id,
        )
        assert isinstance(resolution.decision, SelectAction)
        assert state.last_step is not None
        assert isinstance(state.last_step.decision, SelectAction)
        assert (
            resolution.decision.action_id,
            resolution.decision.destination_id,
            dict(resolution.decision.parameters),
        ) == (
            state.last_step.decision.action_id,
            state.last_step.decision.destination_id,
            dict(state.last_step.decision.parameters),
        )
        selected_route = next(
            item
            for item in envelope.catalog.manifest.action_routes
            if item.operation == tool_name
            and item.source_ref == str(arguments.get("target", arguments.get("source", "")))
            and item.destination_ref == str(arguments.get("destination", ""))
        )
        assert _route_tuple(selected_route) in manifest_routes

        assert len(environment.executed_requests) == 1
        bound = environment.executed_requests[0]
        option = ActionSpaceBuilder().build(shared_task(), state.last_step.before_world).find(
            state.last_step.decision.action_id
        )
        assert option is not None
        assert bound.selection.action_id == option.action_id
        assert bound.intent.semantic_action == selected_route.operation
        assert bound.binding.binding_id in option.eligible_binding_ids

        physical = json.dumps(envelope.model_boundary_projection(), default=str, ensure_ascii=False)
        assert bound.binding.binding_id not in physical
        assert str(bound.binding.payload["selector"]) not in physical
        assert option.action_id not in physical

        breakdown = policy.port.last_request_breakdowns[0]
        counted = estimate_canonical_envelope(envelope)
        assert breakdown == counted
        assert breakdown.estimated_input_tokens == sum(
            (
                breakdown.system_tokens,
                breakdown.actor_world_tokens,
                breakdown.history_tokens,
                breakdown.tool_schema_tokens,
                breakdown.image_estimated_tokens,
                breakdown.model_settings_tokens,
                breakdown.output_contract_tokens,
                    breakdown.provider_envelope_tokens,
            )
        )
        assert breakdown.complete_request_tokens == (
            breakdown.estimated_input_tokens + breakdown.output_reserve_tokens
        )
        assert breakdown.effective_input_limit == min(62_904, 67_000 - 4_096)

    asyncio.run(scenario())


def test_gate_4_private_identity_permutation_preserves_physical_request_and_public_change_does_not() -> None:
    async def invoke(observation_id: str, *, changed_label: bool = False):
        before = shared_world(observation_id, False)
        if changed_label:
            source = before.sources[0]
            changed_target = replace(
                source.targets[0],
                label="Enable the publicly described shared state using this materially changed control label",
            )
            fused = WorldFusion().fuse((replace(source, targets=(changed_target,)),))
            assert fused.observation is not None
            before = fused.observation
        recorder = RecordingPydanticModel(["first_schema_action"], scripted_phases=["ordinary"])
        policy = _policy(recorder)
        state = await _runtime(policy).run_task(_one_action_environment(before=before), shared_task())
        assert state.status is RunStatus.DONE
        envelope = policy.port.last_admitted_envelopes[0]
        return state, recorder, envelope, policy.port.last_request_breakdowns[0]

    async def scenario() -> None:
        first = await invoke("gate-4-private-short")
        second = await invoke("gate-4-private-identity-with-a-much-longer-value")
        changed = await invoke("gate-4-public-change", changed_label=True)

        first_state, first_recorder, first_envelope, first_cost = first
        second_state, second_recorder, second_envelope, second_cost = second
        first_projection = first_state.last_step.before_public_world
        second_projection = second_state.last_step.before_public_world
        assert first_projection is not None and second_projection is not None
        assert (
            first_projection.ordered_target_records,
            first_projection.ordered_fact_records,
            first_projection.ordered_region_records,
        ) == (
            second_projection.ordered_target_records,
            second_projection.ordered_fact_records,
            second_projection.ordered_region_records,
        )
        assert tuple(_route_tuple(item) for item in first_envelope.catalog.manifest.action_routes) == tuple(
            _route_tuple(item) for item in second_envelope.catalog.manifest.action_routes
        )
        assert tuple(to_json_compatible(item.parameters_json_schema) for item in first_envelope.function_tools) == tuple(
            to_json_compatible(item.parameters_json_schema) for item in second_envelope.function_tools
        )
        assert first_envelope.envelope_id == second_envelope.envelope_id
        assert first_cost.estimated_input_tokens == second_cost.estimated_input_tokens
        assert normalize_recorded_provider_input(first_recorder.records[0]) == (
            normalize_recorded_provider_input(second_recorder.records[0])
        )

        _changed_state, changed_recorder, changed_envelope, changed_cost = changed
        assert changed_envelope.envelope_id != first_envelope.envelope_id
        assert normalize_recorded_provider_input(changed_recorder.records[0]) != (
            normalize_recorded_provider_input(first_recorder.records[0])
        )
        assert changed_cost.estimated_input_tokens != first_cost.estimated_input_tokens

    asyncio.run(scenario())


@pytest.mark.parametrize("marked_operand", ("source", "destination"))
def test_gate_4_binary_single_mark_joint_visibility_reaches_schema_resolver_and_binder(
    marked_operand: str,
) -> None:
    async def scenario() -> None:
        before = _binary_world("before", marked_operand=marked_operand)
        after = _binary_world("after")
        recorder = RecordingPydanticModel(["first_schema_action"], scripted_phases=["ordinary"])
        policy = _policy(recorder, supports_multimodal=True)
        environment = ScriptedEnvironment(
            initial_observation=before,
            post_observations=(after,),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await _binary_runtime(policy).run_task(environment, _binary_task())

        assert state.status is RunStatus.DONE
        assert recorder.calls == 1
        envelope = policy.port.last_admitted_envelopes[0]
        record = recorder.records[0]
        assert normalize_recorded_provider_input(record) == envelope.model_boundary_projection()
        assert recorder.last_gui_call is not None
        tool_name, arguments = recorder.last_gui_call
        assert tool_name == "drag_to"
        source_ref = str(arguments["source"])
        destination_ref = str(arguments["destination"])
        route = ("drag_to", source_ref, destination_ref)
        assert tuple(_route_tuple(item) for item in envelope.catalog.manifest.action_routes) == (route,)
        assert envelope.media[0].route_deltas == (route,)
        assert envelope.media[0].marks == ((source_ref if marked_operand == "source" else destination_ref, (2, 2, 6, 6)),)
        assert envelope.media[0].operand_roles == (
            (
                source_ref if marked_operand == "source" else destination_ref,
                (marked_operand,),
            ),
        )
        public_text = envelope.user_text
        unmarked_ref = destination_ref if marked_operand == "source" else source_ref
        assert unmarked_ref in public_text
        assert route in tuple(_route_tuple(item) for item in envelope.catalog.manifest.action_routes)
        recorded_tool = next(item for item in record.function_tools if item.name == "drag_to")
        validate_value(
            arguments,
            to_json_compatible(_thaw_recorded(recorded_tool.parameters_json_schema)),
            path="provider_call",
        )
        assert len(environment.executed_requests) == 1
        bound = environment.executed_requests[0]
        assert bound.intent.semantic_action == "drag_to"
        assert bound.intent.target_id == "private-source"
        assert bound.intent.destination_id == "private-destination"
        physical = json.dumps(envelope.model_boundary_projection(), default=str, ensure_ascii=False)
        assert bound.binding.binding_id not in physical
        assert "#private-source" not in physical
        assert "#private-destination" not in physical

    asyncio.run(scenario())
