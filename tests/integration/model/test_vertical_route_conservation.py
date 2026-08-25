from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace

import pytest

pytest.importorskip("pydantic_ai")

from PIL import Image

import affordance_runtime.model.policy.pydantic_ai_bridge as bridge_module
from affordance_runtime.actions import ActionBinding, ActionSpaceBuilder
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent import RunStatus, SelectAction
from affordance_runtime.agent.context.budgets import ModelRequestBudget
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
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
from tests.integration.model.test_recording_provider_gate import (
    _fanout_world,
    _IncompleteTaskEvaluator,
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


def _binary_world(phase: str, *, mark_mode: str | None = None):
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
    if mark_mode is not None:
        output = io.BytesIO()
        Image.new("RGB", (24, 16), "white").save(output, format="JPEG")
        marked_targets = {
            "none": (),
            "source": (source_target,),
            "destination": (destination,),
            "both": (source_target, destination),
        }[mark_mode]
        media = (
            ObservationMedia(
                f"binary-{mark_mode}",
                "screenshot",
                "image/jpeg",
                output.getvalue(),
                tuple(
                    ObservationGroundingRegion(
                        marked_target.target_id,
                        (2 + index * 10, 2, 6, 6),
                        1.0,
                        "viewport:binary",
                    )
                    for index, marked_target in enumerate(marked_targets)
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


def _fanout_world_with_unselected_mark(observation_id: str, enabled: bool):
    base = _fanout_world(observation_id, enabled, count=300)
    source = base.sources[0]
    marked_targets = tuple(
        replace(
            target,
            label=f"Recover marked control {index:02d} " + ("界!" * 40),
        )
        for index, target in enumerate(source.targets[-32:])
    )
    targets = (*source.targets[:-32], *marked_targets)
    output = io.BytesIO()
    Image.new("RGB", (330, 16), "white").save(output, format="JPEG")
    media = ObservationMedia(
        "fanout-unselected-mark",
        "screenshot",
        "image/jpeg",
        output.getvalue(),
        tuple(
            ObservationGroundingRegion(
                marked_target.target_id,
                (2 + index * 10, 2, 6, 6),
                1.0,
                "viewport:fanout",
            )
            for index, marked_target in enumerate(marked_targets)
        ),
        capture_group_id="capture:fanout",
        variant=ObservationMediaVariant.RAW,
        dimensions=(330, 16),
        coordinate_space_id="viewport:fanout",
    )
    fused = WorldFusion().fuse((replace(source, targets=targets, media=(media,)),))
    assert fused.observation is not None
    selected_target = marked_targets[-1]
    return fused.observation, selected_target.target_id, selected_target.label


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

        admitted_route_fragments = tuple(
            _route_tuple(item) for item in packed.delivery.manifest.action_routes
        )
        manifest_routes = tuple(_route_tuple(item) for item in envelope.catalog.manifest.action_routes)
        assert manifest_routes == admitted_route_fragments
        assert envelope.delivery_id == packed.delivery.delivery_id
        assert tuple(item.name for item in envelope.function_tools) == tuple(
            item.spec.name for item in packed.catalog.tools
        )
        assert tuple(
            (item.mime_type, item.digest, item.marks)
            for item in envelope.media
        ) == tuple(
            (
                item.mime_type,
                item.sha256,
                tuple((mark.ref, mark.bbox) for mark in item.actual_marks),
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


@pytest.mark.parametrize("mark_mode", ("source", "destination", "both", "none"))
def test_gate_4_selected_binary_route_is_atomic_independently_of_visual_marks(
    mark_mode: str,
) -> None:
    async def scenario() -> None:
        before = _binary_world("before", mark_mode=mark_mode)
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
        expected_marks = {
            "none": (),
            "source": ((source_ref, (2, 2, 6, 6)),),
            "destination": ((destination_ref, (2, 2, 6, 6)),),
            "both": ((source_ref, (2, 2, 6, 6)), (destination_ref, (12, 2, 6, 6))),
        }[mark_mode]
        assert envelope.media[0].marks == expected_marks
        public_text = envelope.user_text
        assert source_ref in public_text
        assert destination_ref in public_text
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


def test_gate_4_unselected_mark_does_not_authorize_route_and_find_controls_recovers_it() -> None:
    async def scenario() -> None:
        before, marked_target_id, marked_label = _fanout_world_with_unselected_mark(
            "gate-4-unselected-before", False
        )
        after = _fanout_world("gate-4-unselected-after", True, count=300)
        recorder = RecordingPydanticModel(
            [
                ("find_controls", {"query": marked_label}),
                f"schema_action_label:{marked_label}",
            ],
            scripted_phases=["recovery", "ordinary"],
        )
        policy = _policy(recorder, supports_multimodal=True)
        environment = ScriptedEnvironment(
            initial_observation=before,
            post_observations=(after,),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await _runtime(policy).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE, (
            policy.port.last_local_failure,
            recorder.last_gui_call,
        )
        assert recorder.calls == 2
        first_envelope, second_envelope = policy.port.envelope_history
        assert len(first_envelope.media) == 1
        assert len(first_envelope.media[0].marks) == 32
        assert state.last_step is not None
        assert state.last_step.before_public_world is not None
        marked_ref = state.last_step.before_public_world.target_refs[marked_target_id]
        assert marked_ref in {ref for ref, _bbox in first_envelope.media[0].marks}
        assert all(
            marked_ref not in (route.source_ref, route.destination_ref)
            for route in first_envelope.catalog.manifest.action_routes
        ), (
            marked_ref,
            len(first_envelope.catalog.manifest.action_routes),
            policy.port.last_request_breakdowns[0].estimated_input_tokens,
        )
        assert "find_controls" in recorder.offered_tools[0]
        assert any(
            marked_ref in (route.source_ref, route.destination_ref)
            for route in second_envelope.catalog.manifest.action_routes
        )
        assert normalize_recorded_provider_input(recorder.records[0]) == (
            first_envelope.model_boundary_projection()
        )
        assert normalize_recorded_provider_input(recorder.records[1]) == (
            second_envelope.model_boundary_projection()
        )
        historical_binary_parts = tuple(
            item
            for message in second_envelope.history_messages
            for part in message["parts"]
            if part["part_kind"] == "user-prompt"
            for item in part["content"]
            if item["part_kind"] == "binary"
        )
        assert historical_binary_parts
        assert all("data" not in item and item["digest"] for item in historical_binary_parts)
        assert len(environment.executed_requests) == 1
        assert environment.executed_requests[0].selection.target_id == marked_target_id

    asyncio.run(scenario())


def test_gate_4_current_turn_packing_selects_a_valid_owner_route_without_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        packed_turns = []
        plans = []
        production_packer = TurnPacker

        class RecordingTurnPacker:
            def pack(self, request, **kwargs):
                plans.append(request.agent_context.action_delivery_plan)
                packed = production_packer().pack(request, **kwargs)
                packed_turns.append(packed)
                return packed

        monkeypatch.setattr(bridge_module, "TurnPacker", RecordingTurnPacker)
        before = _fanout_world("gate-4-pages-before", False, count=84)
        after = _fanout_world("gate-4-pages-after", True, count=84)
        recorder = RecordingPydanticModel(["continue_until_action"])
        policy = _policy(recorder)
        environment = ScriptedEnvironment(
            initial_observation=before,
            post_observations=(after,),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        state = await _runtime(policy).run_task(environment, shared_task())

        assert state.status is RunStatus.DONE
        assert len(packed_turns) == recorder.calls == len(policy.port.envelope_history)
        assert len(packed_turns) == 1
        owner_candidates = plans[0].projection().candidates
        owner_routes = tuple(
            (
                candidate.operation,
                candidate.target_ref,
                destination.target_ref if destination is not None else "",
            )
            for candidate in owner_candidates
            for destination in (
                candidate.destinations if candidate.destination_required else (None,)
            )
        )
        delivered_pages = tuple(
            tuple(_route_tuple(route) for route in packed.delivery.manifest.action_routes)
            for packed in packed_turns
        )
        delivered_routes = tuple(route for page in delivered_pages for route in page)
        assert all(delivered_pages)
        assert len(delivered_routes) == len(set(delivered_routes))
        assert set(delivered_routes) <= set(owner_routes)
        assert all("action_results_next_page" not in tools for tools in recorder.offered_tools)
        assert all(
            normalize_recorded_provider_input(record) == envelope.model_boundary_projection()
            for record, envelope in zip(
                recorder.records,
                policy.port.envelope_history,
                strict=True,
            )
        )
        physical = json.dumps(
            tuple(envelope.model_boundary_projection() for envelope in policy.port.envelope_history),
            default=str,
            ensure_ascii=False,
        )
        assert "action_results_next_page" not in physical
        assert "read_next_page" not in physical
        assert before.observation_id not in physical
        assert all(
            item.action_id not in physical
            for item in ActionSpaceBuilder().build(shared_task(), before).options
        )

    asyncio.run(scenario())


def test_gate_4_final_physical_envelope_exact_fit_and_one_under_never_calls_recorder() -> None:
    async def invoke(request_budget: ModelRequestBudget | None = None):
        fused = WorldFusion().fuse((
            SurfaceObservation(
                "gate-4-capacity-world",
                "dom",
                "revision:gate-4-capacity-world",
                ObservationSourceProfile.dom(),
                (SemanticTarget("private-readonly", "note", "容量✓"),),
            ),
        ))
        assert fused.observation is not None
        recorder = RecordingPydanticModel(
            ["zero_calls", "zero_calls"],
            scripted_phases=["ordinary", "ordinary_output_retry"],
        )
        policy = _policy(recorder, request_budget=request_budget)
        state = await _runtime(policy, evaluator=_IncompleteTaskEvaluator()).run_task(
            ScriptedEnvironment(initial_observation=fused.observation),
            TaskGoal("capacity", "Inspect 容量✓", risk_profile=RiskProfile.READ_ONLY),
        )
        return state, recorder, policy

    async def scenario() -> None:
        _baseline_state, baseline_recorder, baseline_policy = await invoke()
        assert baseline_recorder.calls == 2
        baseline = baseline_policy.port.last_request_breakdowns[0]
        exact_budget = replace(
            ModelRequestBudget(),
            soft_target_tokens=max(8_000, baseline.estimated_input_tokens),
            admission_limit=baseline.estimated_input_tokens,
        )
        _exact_state, exact_recorder, exact_policy = await invoke(exact_budget)
        assert exact_recorder.calls == 2
        assert exact_policy.port.last_request_breakdowns[0].estimated_input_tokens == (
            baseline.estimated_input_tokens
        )

        rejected_budget = replace(
            exact_budget,
            admission_limit=baseline.estimated_input_tokens - 1,
        )
        rejected_state, rejected_recorder, rejected_policy = await invoke(rejected_budget)
        assert rejected_state.status is RunStatus.FAILED
        assert rejected_recorder.calls == 0
        assert rejected_policy.port.last_model_call_count == 0
        assert rejected_policy.port.last_generation_attempts == ()
        rejection = rejected_policy.port.last_request_breakdowns[0]
        assert rejection.estimated_input_tokens == baseline.estimated_input_tokens
        assert rejection.complete_request_tokens == (
            rejection.estimated_input_tokens + rejection.output_reserve_tokens
        )
        assert rejection.effective_input_limit == baseline.estimated_input_tokens - 1
        assert rejected_policy.port.last_invocation_result is not None
        assert rejected_policy.port.last_invocation_result.failure is not None
        assert rejected_policy.port.last_invocation_result.failure.kind.value == "context_capacity"

    asyncio.run(scenario())
