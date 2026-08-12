from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace

import numpy as np
import pytest
from browsergym_adapter_support import ax_node, raw_observation
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import AgentDecisionPackage, AgentEpisodeRunner, AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.benchmarks.external_smoke.browsergym_entity_identity import BrowserGymEntityIdentityMap
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import project_browsergym_observation
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import PRIVATE_CONTROL_PROPERTIES_KEY
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import BrowserGymVerifierSnapshot
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary import ContextBuilder, ModelFailure
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
)
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.policy import _build_request
from affordance_runtime.model_policy.tool_contracts import ToolCall
from affordance_runtime.model_port import ModelCallRecord, ModelConfig
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import ActionSpaceBuilder, ObservationGroundingRegion, ObservationMedia

_IDENTITY = BrowserGymEntityIdentityMap(b"grounded-tools-v2-tests")


def _context(*, with_boxes=True):
    raw = raw_observation(
        ax_node("username", "textbox", "Username"),
        ax_node("password", "textbox", "Password"),
        ax_node("login", "button", "Login"),
        goal='Enter username "donovan", password "UV", then press Login.',
    )
    raw["screenshot"] = np.full((160, 320, 3), 255, dtype=np.uint8)
    if with_boxes:
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["username"]["bbox"] = [10, 10, 140, 30]
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["password"]["bbox"] = [10, 55, 140, 30]
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["login"]["bbox"] = [10, 100, 80, 30]
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
    public = json.dumps(to_json_compatible({
        "view": {
            "task": catalog.view.task_brief,
            "index": catalog.view.grounding_index,
            "state": catalog.view.current_state,
        },
        "tools": [item.input_schema for item in catalog.specs],
    }))
    assert '"E1"' in public and '"E2"' in public and '"E3"' in public
    assert "bbox" not in public
    assert "entity:" not in public and "action:" not in public and "binding:" not in public


def test_schema_equivalent_actions_are_grouped_into_small_verb_tools_and_resolve_privately() -> None:
    context = _context()
    catalog = compile_grounded_tool_catalog(context)
    names = [item.name for item in catalog.specs]

    assert set(names) == {"fill", "click"}
    fill = next(item for item in catalog.specs if item.name == "fill")
    refs_by_label = {item.label: item.ref for item in context.grounding.entities}
    assert set(fill.input_schema["properties"]["target"]["enum"]) == {
        refs_by_label["Username"], refs_by_label["Password"],
    }
    assert fill.input_schema["required"] == ("target", "text")
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
        replace(item, label="", state={}, relation_hints=(), marked=False)
        if item.role == "textbox" else item
        for item in context.grounding.entities
    )
    context = replace(context, grounding=replace(context.grounding, entities=entities))

    with pytest.raises(GroundedToolResolutionError) as gap:
        compile_grounded_tool_catalog(context)

    assert gap.value.code is GroundedToolResolutionCode.GROUNDING_GAP


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
        assert output_schema is GroundedToolCommandPayload
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

        assert not isinstance(response, ModelFailure)
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


def test_selected_grounded_operation_gets_one_typed_argument_repair_without_changing_operation() -> None:
    async def scenario():
        context = _context()
        password_ref = next(item.ref for item in context.grounding.entities if item.label == "Password")
        port = _CompactPort([
            {"op": "fill", "target": password_ref},
            {"op": "fill", "target": password_ref, "text": "UV"},
        ])
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
        target = spec.input_schema["properties"]["target"]["enum"][0]
        arguments = {"target": target}
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

    assert result.status is AgentLoopStatus.DONE
    assert port.calls == 1
    assert result.execution_count == 1
    assert len(result.control_transitions) == 1


def _unmarked_png():
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.fromarray(np.full((160, 320, 3), 255, dtype=np.uint8)).save(output, format="PNG", optimize=True)
    return output.getvalue()
