from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Sequence, TypeVar

import pytest
from pydantic import BaseModel, ValidationError
from test_agent_loop import _task, _world

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.agent.task_plan_preparation import CanonicalAgentTaskPlanPreparer
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.task.objective_sequence import ObjectiveSequenceState, SequenceDisposition
from affordance_runtime.task.step_execution import SetStepExecution
from affordance_runtime.task_planner import (
    StrictTaskPlanner,
    TaskPlanProviderResponse,
    _canonical_execution,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class _PlanningModel:
    provider: str = "fixed"
    model: str = "canonical-agent-plan"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del config
        self.calls += 1
        if output_schema.__name__ == "LLMMinimalIntentProposal":
            payload = json.loads(messages[-1].content)
            source_ref = payload["source_envelope"]["anchors"][0]["anchor_id"]
            return output_schema.model_validate({
                "objective": "Enable shared state",
                "requested_effects": [{
                    "operation_class": "reversible_write",
                    "target": "shared-toggle",
                    "source_ref": source_ref,
                    "operation_ref": "resource.update@v1",
                }],
                "success": {
                    "expression_id": "success:enabled",
                    "operator": "criterion",
                    "criterion_id": "criterion:enabled",
                    "requirement_refs": ["requirement:effect:1"],
                },
            })
        if output_schema.__name__ == "TaskPlanProviderResponse":
            return output_schema.model_validate({
                "steps": [{
                    "step_id": "enable",
                    "objective": "Enable shared state",
                    "subject": "shared-toggle",
                    "relation": "is_completed",
                    "requirement_refs": ["requirement:effect:1"],
                    "effect_authorization_refs": ["requirement:effect:1"],
                    "effectful": True,
                    "operation_class": "reversible_write",
                    "execution": {
                        "kind": "entity",
                        "predicate": {
                            "kind": "fact_equals",
                            "field_name": "identity.entity_id",
                            "expected": "shared-toggle",
                        },
                        "semantic_action": "activate",
                    },
                }],
            })
        raise AssertionError(output_schema.__name__)


def test_canonical_preparer_is_the_only_task_semantic_entry_for_agent_loop() -> None:
    model = _PlanningModel()
    preparer = CanonicalAgentTaskPlanPreparer(
        LLMIntentCompiler(model),
        StrictTaskPlanner(model),
    )
    world = _world("observation:initial", False)

    prepared = asyncio.run(preparer.prepare(_task(), world))

    assert model.calls == 2
    assert prepared.admitted_task.task_spec.identity
    assert prepared.plan.task_id == _task().task_id
    assert prepared.plan.based_on_observation_ref == world.observation_id
    assert len(prepared.plan.steps) == 1
    assert prepared.plan.steps[0].execution is not None

    state = AgentLoopState(world, semantic_control_required=True)
    state.install_plan(
        prepared.plan,
        task_spec_identity=prepared.admitted_task.task_spec.identity,
    )
    assert isinstance(state.active_step_execution, ObjectiveSequenceState)
    assert state.active_step_execution.disposition is SequenceDisposition.READY
    assert state.active_step_execution.resolved_target_id == "shared-toggle"


def test_planner_execution_transport_is_discriminated_and_lossless() -> None:
    payload = {
        "steps": [{
            "step_id": "select-all",
            "objective": "Select every matching item",
            "subject": "matching items",
            "relation": "is_completed",
            "requirement_refs": ["requirement:effect:1"],
            "effect_authorization_refs": ["requirement:effect:1"],
            "effectful": True,
            "execution": {
                "kind": "set",
                "predicate": {
                    "kind": "visual_concept",
                    "concept": "apple",
                },
                "semantic_action": "activate",
                "quantifier": "all_in_closed_scope",
                "postcondition": {
                    "kind": "fact_equals",
                    "field_name": "state.selected",
                    "expected": True,
                },
            },
        }],
    }
    response = TaskPlanProviderResponse.model_validate(payload)
    planned = _canonical_execution(response.steps[0])

    assert isinstance(planned, SetStepExecution)
    assert planned.objective.action_template.item_postcondition is not None

    payload["steps"][0]["execution"]["aggregate_operator"] = "sum"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TaskPlanProviderResponse.model_validate(payload)
