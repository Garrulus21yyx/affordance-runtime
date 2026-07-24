import asyncio
from dataclasses import dataclass
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.state_kernel import StateKernel
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
        envelope: Any,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        active = state.plan_progress.active_subgoal_id if state.plan_progress is not None else ""
        label, evidence_key = {
            "discover": ("Discover", "discovered"),
            "confirm": ("Confirm", "confirmed"),
        }[active]
        affordance = next(item for item in snapshot.affordance_model.affordances if item.label == label)
        return PlannerDecision(
            contract=ActionContract.from_affordance(
                affordance,
                intent=state.active_subgoal(),
                backend="dom",
                verifier_plan=[VerifierSpec("observation_metadata", evidence_key, True)],
            )
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
                    "task_structure": "multi_stage",
                }
            )
        if output_schema.__name__ == "TaskPlanCandidate":
            return output_schema.model_validate(
                {
                    "subgoals": [
                        {
                            "subgoal_id": "discover",
                            "objective": "Discover the current state",
                            "success_criteria": ["the state is discovered"],
                            "evidence_requirements": ["fresh discovered-state observation"],
                            "operation_class": "read_only",
                        },
                        {
                            "subgoal_id": "confirm",
                            "objective": "Confirm the discovered state",
                            "depends_on": ["discover"],
                            "success_criteria": ["the state is confirmed"],
                            "evidence_requirements": ["fresh confirmed-state observation"],
                            "operation_class": "read_only",
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
        coordinator=RunCoordinator(
            observer=MultiStageObserver(world),
            planner=MultiStageActionPlanner(),
            executor=MultiStageExecutor(world),
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
    completed = [node.payload["subgoal_id"] for node in result.trace.nodes if node.kind == "SubgoalCompleted"]
    assert completed == ["discover", "confirm"]
    assert "ActivePerceptionPlanned" not in [node.kind for node in result.trace.nodes]
