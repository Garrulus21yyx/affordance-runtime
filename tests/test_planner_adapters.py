import asyncio
from dataclasses import dataclass
from typing import Any, Mapping

import pytest
from pydantic import ValidationError

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.planner_adapters import ParentAgentPlannerAdapter
from affordance_runtime.planner_context import PlannerContext, PlannerContextBuilder
from affordance_runtime.planning import PlannerProposalSource
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


def _inputs() -> tuple[TaskEnvelope, StateKernel, BrowserSnapshot]:
    model = DomAdapter().transduce(
        '<button id="save" bid="private-bid">Save</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-1", "Save")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Save",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Save",),
        success_criteria=("saved",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-1",
    )
    return TaskEnvelope(task_spec=spec, capabilities=["settings.write"]), state, BrowserSnapshot(observation, model)


@dataclass
class ParentSource:
    invalid: bool = False
    seen: Mapping[str, Any] | None = None

    async def propose(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        self.seen = context
        payload: dict[str, Any] = {
            "proposal_id": "parent-proposal-1",
            "based_on_task_revision": context["task_revision"],
            "based_on_state_version": context["state_version"],
            "snapshot_id": context["snapshot_id"],
            "subgoal": "Save",
            "action_kind": "activate",
            "target_affordance_id": "dom_button_1",
            "parameters": {},
            "expected_effects": ["saved"],
            "evidence_requirements": ["saved evidence"],
        }
        if self.invalid:
            payload["parameters"] = {"selector": "#save"}
        return payload


def test_parent_adapter_receives_bounded_context_and_returns_semantic_proposal() -> None:
    envelope, state, snapshot = _inputs()
    source = ParentSource()

    decision = asyncio.run(ParentAgentPlannerAdapter(source).propose_legacy(envelope, state, snapshot))

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_button_1"
    assert source.seen is not None
    assert "private-bid" not in str(source.seen)
    assert source.seen["granted_capabilities"] == ["settings.write"]
    assert decision.planner_context["adapter"] == "parent_agent"
    assert decision.proposal_provenance is not None
    assert decision.proposal_provenance.source == PlannerProposalSource.PARENT_AGENT
    assert decision.proposal_provenance.producer_id == "ParentSource"


def test_parent_adapter_rejects_primitive_locator_payload() -> None:
    envelope, state, snapshot = _inputs()

    with pytest.raises(ValidationError, match="surface or authority"):
        asyncio.run(ParentAgentPlannerAdapter(ParentSource(invalid=True)).propose_legacy(envelope, state, snapshot))


def test_parent_adapter_uses_immutable_request_context_path() -> None:
    envelope, state, snapshot = _inputs()

    @dataclass
    class RecordingRequestBuilder:
        inner: PlanningRequestBuilder = PlanningRequestBuilder()
        built: PlanningRequest | None = None

        def build(
            self,
            envelope: TaskEnvelope,
            state: StateKernel,
            snapshot: BrowserSnapshot,
        ) -> PlanningRequest:
            self.built = self.inner.build(envelope, state, snapshot)
            return self.built

    @dataclass
    class RequestOnlyContextBuilder:
        received: PlanningRequest | None = None

        def build(
            self,
            request: PlanningRequest,
            state: StateKernel | None = None,
            snapshot: BrowserSnapshot | None = None,
        ) -> PlannerContext:
            assert state is None
            assert snapshot is None
            self.received = request
            return PlannerContextBuilder().build(request)

    request_builder = RecordingRequestBuilder()
    context_builder = RequestOnlyContextBuilder()
    source = ParentSource()

    decision = asyncio.run(
        ParentAgentPlannerAdapter(
            source,
            planning_request_builder=request_builder,
            context_builder=context_builder,
        ).propose_legacy(envelope, state, snapshot)
    )

    assert request_builder.built is not None
    assert context_builder.received is request_builder.built
    assert source.seen is not None
    assert source.seen["state_version"] == request_builder.built.identity.evaluated_at_state_version
    assert source.seen["snapshot_id"] == request_builder.built.identity.snapshot_id
    assert decision.proposal is not None
