import asyncio
from dataclasses import dataclass
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
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
    ContractBuilder,
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
        del messages, config
        self.calls += 1
        if output_schema.__name__ == "LLMIntentDraft":
            return output_schema.model_validate(
                {
                    "objective": "Discover the current state, then confirm it",
                    "requested_effects": [
                        {
                            "operation_class": "read_only",
                            "target": "current state",
                            "source_ref": "multi-stage-request",
                        }
                    ],
                    "candidate_success_criteria": ["the current state is confirmed"],
                    "candidate_evidence_requirements": ["fresh state observations"],
                    "candidate_source_claims": [
                        {
                            "claim_id": "claim-discover",
                            "kind": "dependency",
                            "statement": "discover the current state",
                            "source_ref": "multi-stage-request",
                        },
                        {
                            "claim_id": "claim-confirm",
                            "kind": "terminal",
                            "statement": "confirm the discovered state",
                            "source_ref": "multi-stage-request",
                        },
                    ],
                    "candidate_obligations": [
                        {
                            "obligation_id": "obligation-discover",
                            "kind": "predicate",
                            "subject": "current state",
                            "relation": "is_available",
                            "value_source": "observation",
                            "claim_ids": ["claim-discover"],
                            "evidence_requirements": ["fresh discovered-state observation"],
                        },
                        {
                            "obligation_id": "obligation-confirm",
                            "kind": "effect",
                            "subject": "discovered state",
                            "relation": "is_completed",
                            "claim_ids": ["claim-confirm"],
                            "depends_on": ["obligation-discover"],
                            "evidence_requirements": ["fresh confirmed-state observation"],
                            "terminal": True,
                        },
                    ],
                    "task_structure": "multi_stage",
                }
            )
        if output_schema.__name__ == "TaskObligationCoverageReview":
            return output_schema.model_validate(
                {
                    "status": "complete",
                    "covered_claim_ids": ["claim-discover", "claim-confirm"],
                }
            )
        if output_schema.__name__ == "TaskPlanProviderEnvelope":
            return output_schema.model_validate(
                {
                    "entry_subgoal": {
                        "subgoal_id": "discover",
                        "outcome": {
                            "subject": "current state",
                            "relation": "is_visible",
                        },
                        "evidence_requirements": ["fresh discovered-state observation"],
                        "operation_class": "read_only",
                        "action_family": "activate",
                    },
                    "remaining_subgoals": [
                        {
                            "subgoal_id": "confirm",
                            "outcome": {
                                "subject": "discovered state",
                                "relation": "is_completed",
                            },
                            "depends_on": ["discover"],
                            "evidence_requirements": ["fresh confirmed-state observation"],
                            "operation_class": "read_only",
                            "action_family": "activate",
                        },
                    ]
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
            planner=MultiStageActionPlanner(),
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
    assert task_plan.payload["generated_by"] == "rule"
    completed = [node.payload["subgoal_id"] for node in result.trace.nodes if node.kind == "SubgoalCompleted"]
    assert len(completed) == 2
    assert all(identifier.startswith("obligation:") for identifier in completed)
    assert result.coordinator is not None
    progress = result.coordinator.state.task_progress
    assert progress is not None
    assert progress.completed_subgoal_ids == completed
    assert all(progress.evidence_by_subgoal[identifier] for identifier in completed)
    assert "ActivePerceptionPlanned" not in [node.kind for node in result.trace.nodes]


def test_task_pipeline_wires_only_a_real_configured_provider_fallback() -> None:
    primary = MultiStageIntentAndPlanModel(provider="primary", model="primary-model")
    fallback = MultiStageIntentAndPlanModel(provider="fallback", model="fallback-model")
    pipeline = GeneralistTaskPipeline(
        compiler=LLMIntentCompiler(FallbackModelPort((primary, fallback))),
        coordinator=compose_run_coordinator(
            observer=MultiStageObserver(MultiStageWorld()),
            planner=MultiStageActionPlanner(),
            executor=MultiStageExecutor(MultiStageWorld()),
        ),
    )

    dispatcher = pipeline.coordinator.recovery_stage.owner_dispatcher

    assert dispatcher.available_kinds == frozenset({RecoveryKind.SWITCH_PROVIDER})
    assert dispatcher.target_ref(RecoveryKind.SWITCH_PROVIDER) == "fallback:fallback-model"
