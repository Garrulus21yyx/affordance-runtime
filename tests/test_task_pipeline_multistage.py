import asyncio
from dataclasses import dataclass
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.action_contract_builder import ActionContractMaterializer as ContractBuilder
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.choice_contracts import ChoicePlanningRequest, SelectChoice
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import FallbackModelPort, ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import PlannerProposalResponse
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.task_intake import UserRequest
from affordance_runtime.task_pipeline import GeneralistTaskPipeline
from affordance_runtime.task_planner import PlanningRouter, StrictTaskPlanner

T = TypeVar("T", bound=BaseModel)


@dataclass
class MultiStageWorld:
    discovered: bool = False
    confirmed: bool = False


class MultiStageObserver:
    def __init__(self, world: MultiStageWorld) -> None:
        self.world = world
        self.sequence = 0

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        snapshot_id = f"snapshot-{self.sequence}"
        model = DomAdapter().transduce(
            '<button id="discover">Discover</button><button id="confirm">Confirm</button>',
            environment_revision=f"revision-{int(self.world.discovered)}-{int(self.world.confirmed)}",
            snapshot_id=snapshot_id,
            page_revision="page-1",
        )
        observation = Observation(
            model.environment_revision,
            snapshot_id=snapshot_id,
            page_revision="page-1",
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            metadata={
                "discovered": self.world.discovered,
                "confirmed": self.world.confirmed,
                "criterion_evaluations": {
                    "criterion:confirmed": {
                        "status": "satisfied" if self.world.confirmed else "unsatisfied",
                        "evidence_refs": [f"observation:{snapshot_id}:confirmed"],
                    }
                },
            },
        )
        return BrowserSnapshot(observation, model)


@dataclass
class MultiStageExecutor:
    world: MultiStageWorld
    backend: str = "dom"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        del observation
        target = str(contract.locator.get("selector") or "")
        if target == "#discover":
            self.world.discovered = True
        elif target == "#confirm":
            self.world.confirmed = True
        else:
            raise AssertionError(f"unexpected target: {target}")
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            contract.environment_revision,
            contract.environment_revision,
            1.0,
        )


class MultiStageActionPlanner:
    def select(self, request: ChoicePlanningRequest) -> SelectChoice:
        label = {"discover": "Discover", "confirm": "Confirm"}[request.active_step_id]
        choice = next(item for item in request.page.choices if item.target_label == label)
        return SelectChoice(choice.choice_id, "match accepted active step")

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse:
        active_step = request.step.active_step
        assert active_step is not None
        active_description = active_step.objective
        label, evidence_key = {
            "current state is available": ("Discover", "discovered"),
            "discovered state is completed": ("Confirm", "confirmed"),
        }[active_description]
        affordance = next(item for item in request.observation.affordances if item.label == label)
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id=f"multi-stage-{active_step.step_id}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal=active_description,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=affordance.target_id,
                expected_effects=(f"{evidence_key} becomes true",),
                evidence_requirements=(f"independent {evidence_key} metadata",),
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="multi-stage-test-planner",
                profile_id="canonical-request",
            ),
        )


@dataclass
class MultiStageIntentAndPlanModel:
    provider: str = "fixed"
    model: str = "fixed-multi-stage"
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
            request = __import__("json").loads(messages[-1].content)
            source_ref = request["source_envelope"]["anchors"][0]["anchor_id"]
            return output_schema.model_validate(
                {
                    "objective": "Discover the current state, then confirm it",
                    "requested_effects": [
                        {
                            "operation_class": "read_only",
                            "target": "Discover",
                            "source_ref": source_ref,
                        },
                        {
                            "operation_class": "read_only",
                            "target": "Confirm",
                            "source_ref": source_ref,
                        },
                    ],
                    "success": {
                        "expression_id": "success:confirmed",
                        "operator": "criterion",
                        "criterion_id": "criterion:confirmed",
                        "requirement_refs": ["requirement:effect:2"],
                    },
                }
            )
        if output_schema.__name__ == "TaskPlanProviderResponse":
            return output_schema.model_validate(
                {
                    "steps": [
                        {
                            "step_id": "discover",
                            "objective": "Discover current state",
                            "subject": "current state",
                            "relation": "is_visible",
                            "requirement_refs": ["requirement:effect:1"],
                            "effect_authorization_refs": ["requirement:effect:1"],
                            "effectful": True,
                        },
                        {
                            "step_id": "confirm",
                            "objective": "Confirm discovered state",
                            "subject": "discovered state",
                            "relation": "is_completed",
                            "requirement_refs": ["requirement:effect:2"],
                            "effect_authorization_refs": ["requirement:effect:2"],
                            "effectful": True,
                            "depends_on": ["discover"],
                        },
                    ],
                }
            )
        raise AssertionError(f"unexpected schema: {output_schema.__name__}")


def test_raw_multi_stage_request_uses_common_router_and_verified_serial_subgoals() -> None:
    world = MultiStageWorld()
    model = MultiStageIntentAndPlanModel()
    pipeline = GeneralistTaskPipeline(
        compiler=LLMIntentCompiler(model),
        coordinator=compose_run_coordinator(
            observer=MultiStageObserver(world),
            step_choice_planner=MultiStageActionPlanner(),
            executor=MultiStageExecutor(world),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "observation_metadata",
                                "discovered",
                                True,
                                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                            ),
                        )
                    ),
                    "dom_button_2": ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "observation_metadata",
                                "confirmed",
                                True,
                                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                            ),
                        )
                    ),
                }
            ),
            task_planner=PlanningRouter(complex_planner=StrictTaskPlanner(model)),
        ),
    )

    result = asyncio.run(
        pipeline.run(
            UserRequest(
                request_id="multi-stage-request",
                raw_text="Discover the current state, then confirm it",
            )
        )
    )

    assert result.status == RuntimeStep.DONE.value
    assert world == MultiStageWorld(discovered=True, confirmed=True)
    assert model.calls == 2
    task_plan = next(node for node in result.trace.nodes if node.kind == "TaskPlanProposed")
    assert task_plan.payload["generated_by"] == "llm"
    completed = [node.payload["step_id"] for node in result.trace.nodes if node.kind == "StepCompleted"]
    assert len(completed) == 2
    assert completed == ["discover", "confirm"]
    assert result.coordinator is not None
    progress = result.coordinator.state.task_progress
    assert progress is not None
    assert progress.completed_step_ids == tuple(completed)
    assert all(progress.evidence_for_step(identifier) for identifier in completed)
    assert "ActivePerceptionPlanned" not in [node.kind for node in result.trace.nodes]


def test_task_pipeline_wires_only_a_real_configured_provider_fallback() -> None:
    primary = MultiStageIntentAndPlanModel(provider="primary", model="primary-model")
    fallback = MultiStageIntentAndPlanModel(provider="fallback", model="fallback-model")
    pipeline = GeneralistTaskPipeline(
        compiler=LLMIntentCompiler(FallbackModelPort((primary, fallback))),
        coordinator=compose_run_coordinator(
            observer=MultiStageObserver(MultiStageWorld()),
            executor=MultiStageExecutor(MultiStageWorld()),
        ),
    )

    dispatcher = pipeline.coordinator.recovery_stage.owner_dispatcher

    assert dispatcher.available_kinds == frozenset({RecoveryKind.SWITCH_PROVIDER})
    assert dispatcher.target_ref(RecoveryKind.SWITCH_PROVIDER) == "fallback:fallback-model"
