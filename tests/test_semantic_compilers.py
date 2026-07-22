import asyncio
from dataclasses import dataclass
from typing import Any

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.generalist_planner import (
    GeneralistLMPlanner,
    build_planner_context,
    default_semantic_compiler_registry,
)
from affordance_runtime.model_port import ModelCallRecord
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.semantic_compilers import SemanticCompilerRegistry
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


@dataclass
class DragProposalModel:
    provider: str = "fixture"
    model: str = "semantic-drag"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: list[Any],
        output_schema: type[Any],
        config: Any,
    ) -> Any:
        del messages, config
        self.calls += 1
        return output_schema.model_validate(
            {
                "action_kind": PlannerActionKind.DRAG,
                "target_affordance_id": "dom_li_2",
                "destination_affordance_id": "dom_li_3",
            }
        )


def _drag_fixture(objective: str) -> tuple[TaskEnvelope, StateKernel, BrowserSnapshot]:
    model = DomAdapter().transduce(
        '<li class="ui-sortable-handle">Alpha</li>'
        '<li class="ui-sortable-handle">Beta</li>'
        '<li class="ui-sortable-handle">Gamma</li>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    task = TaskSpec(
        task_id="generic-sortable",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("sortable list",),
        success_criteria=("requested item position is observed",),
        evidence_requirements=("post-action list order",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, objective)
    state.remember_observation(observation)
    return TaskEnvelope(task_spec=task), state, BrowserSnapshot(observation, model)


def test_default_semantic_compilers_declare_applicability_evidence_and_negative_examples() -> None:
    registry = default_semantic_compiler_registry()

    assert registry.rules
    assert registry.constraint_rules
    for rule in (*registry.rules, *registry.constraint_rules):
        assert rule.compiler_id
        assert rule.applicability_description
        assert rule.evidence.output_action_kinds
        assert rule.evidence.verifier_requirements
        assert rule.evidence.negative_examples
        assert rule.evidence.source
        assert rule.evidence.version
        serialized = repr(rule).casefold()
        assert "browsergym" not in serialized
        assert "miniwob" not in serialized


def test_constraint_registry_is_explicit_and_disabled_registry_is_neutral() -> None:
    envelope, state, snapshot = _drag_fixture("Review the current list without changing it")
    context = build_planner_context(envelope, state, snapshot)
    permitted = list(context.permitted_action_kinds)
    compatible = {
        "drag": [item.id for item in context.affordances if item.action == "drag"]
    }

    constrained = default_semantic_compiler_registry().constrain(
        context,
        permitted,
        compatible,
    )

    assert constrained is not None
    assert constrained.compiler_id == "typed-planner-constraints-v1"
    assert constrained.evidence_ref == "runtime-generic-planner-constraint-conformance@1"
    assert SemanticCompilerRegistry.disabled().constrain(context, permitted, compatible) is None


def test_registry_negative_control_does_not_compile_an_unrequested_list_action() -> None:
    envelope, state, snapshot = _drag_fixture("Review the current list without changing it")
    context = build_planner_context(envelope, state, snapshot)

    assert default_semantic_compiler_registry().compile(context) is None


def test_typed_incremental_control_compiles_one_verified_direction_without_backend_data() -> None:
    model = DomAdapter().transduce(
        '<div><span class="ui-slider-handle" tabindex="0"></span><div>-1</div></div>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    task = TaskSpec(
        task_id="portable-slider",
        revision=1,
        objective="Select 3 with the slider, then continue.",
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("slider value is 3",),
        source_request_ref="test",
    )
    state = StateKernel(task.task_id, task.objective)
    state.remember_observation(observation)
    context = build_planner_context(
        TaskEnvelope(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    compiled = default_semantic_compiler_registry().compile(context)

    assert compiled is not None
    assert compiled.compiler_id == "typed-incremental-control-v1"
    assert compiled.action_kind == "press_key"
    assert compiled.parameters == {"key": "ArrowRight"}


def test_disabling_semantic_compiler_profile_preserves_runtime_drag_capability() -> None:
    envelope, enabled_state, snapshot = _drag_fixture("Drag Beta down by one position")
    enabled_model = DragProposalModel()
    enabled = asyncio.run(
        GeneralistLMPlanner(enabled_model).propose(envelope, enabled_state, snapshot)
    )

    _, disabled_state, _ = _drag_fixture("Drag Beta down by one position")
    disabled_model = DragProposalModel()
    disabled = asyncio.run(
        GeneralistLMPlanner(
            disabled_model,
            semantic_compilers=SemanticCompilerRegistry.disabled(),
        ).propose(envelope, disabled_state, snapshot)
    )

    assert enabled.proposal is not None and disabled.proposal is not None
    assert enabled.proposal.action_kind == disabled.proposal.action_kind == PlannerActionKind.DRAG
    assert enabled.proposal.target_affordance_id == disabled.proposal.target_affordance_id == "dom_li_2"
    assert enabled.proposal.destination_affordance_id == disabled.proposal.destination_affordance_id == "dom_li_3"
    assert enabled_model.calls == 0
    assert disabled_model.calls == 1
    assert enabled.planner_context["semantic_compiler"]["compiler_id"] == "typed-affordance-semantics-v1"
    assert "semantic_compiler" not in disabled.planner_context
    assert "semantic_constraints" not in disabled.planner_context
